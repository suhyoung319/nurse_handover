"""
services/risk_service.py — 위험도 자동 분석 엔진

[깊은 설명 — 위험도 자동 분석 시스템]

## 왜 단순 키워드 매칭이 부족한가?

현재 방식의 문제:
    "낙상" 단어가 있으면 → has_danger = True
    
이 경우 "낙상 위험 없음" 이라고 써도 위험으로 분류됨 (오탐)
또한 "혈압이 약간 높음" 같은 바이탈 이상은 감지 못함

## 개선된 설계: 가중치 기반 점수 시스템 (Rule Engine)

### 점수 계산 방식
1. 키워드 카테고리별 기본 점수
   - CRITICAL 키워드 (심정지, DNR, 사망): +40점
   - HIGH 키워드 (낙상, 쇼크, 경련): +25점  
   - MEDIUM 키워드 (통증, 발열, 부종): +10점

2. 바이탈 이상 감지: +20점
   - 수축기 혈압 > 180 or < 90
   - 맥박 > 120 or < 50
   - 산소포화도 < 95%
   - 체온 > 38.5°C

3. 복합 조건 보너스
   - 2개 이상 카테고리 동시: +10점
   - 동일 환자 24시간 내 반복: +15점

4. 네거티브 컨텍스트 감지: -10점
   - "없음", "정상", "해결됨" 등이 키워드 앞뒤에 있으면 감점
   (완벽하지 않지만 오탐률 유의미하게 감소)

### 점수 → 레벨 변환
- 80~100: CRITICAL (즉시 대응 필요)
- 60~79:  HIGH (우선 확인 필요)  
- 40~59:  MEDIUM (주의 관찰)
- 0~39:   LOW (일반 인수인계)
"""

import re
import json
from datetime import datetime, timedelta
from flask import current_app
from app import db
from app.models import Handover, RiskAssessment


# ── 키워드 룰 테이블 ────────────────────────────────────────────
# (score: 기본 점수, category: 분류, description: 설명)

KEYWORD_RULES = {
    # CRITICAL: 생명 위협 수준
    'CRITICAL': {
        'keywords': [
            '심정지', 'CPR', '사망', 'DNR', '무의식', '혼수', '호흡정지',
            '쇼크', '아나필락시스', '과민반응',
        ],
        'score': 40,
    },
    # HIGH: 즉각 대응 필요
    'HIGH': {
        'keywords': [
            '낙상', '자살', '자해', '경련', '발작', '패혈증',
            '급격', '악화', '응급', '즉시', '출혈', '혼미',
            '인공호흡기', '수혈', '투석',
        ],
        'score': 25,
    },
    # MEDIUM: 주의 관찰
    'MEDIUM': {
        'keywords': [
            '호흡곤란', '흉통', '섬망', '고열', '저혈압', '부종',
            '알레르기', '위험', '주의', '불안',
        ],
        'score': 10,
    },
}

# 네거티브 컨텍스트 패턴 (키워드 앞뒤 15자 이내에 있으면 감점)
NEGATIVE_CONTEXT_PATTERNS = [
    r'없음', r'정상', r'해결', r'호전', r'안정', r'아니', r'부재',
]

# 바이탈 파싱 패턴
VITAL_PATTERNS = {
    'bp_systolic': re.compile(r'BP\s*:?\s*(\d+)/\d+', re.IGNORECASE),
    'bp_diastolic': re.compile(r'BP\s*:?\s*\d+/(\d+)', re.IGNORECASE),
    'hr': re.compile(r'HR\s*:?\s*(\d+)', re.IGNORECASE),
    'rr': re.compile(r'RR\s*:?\s*(\d+)', re.IGNORECASE),
    'bt': re.compile(r'BT\s*:?\s*(\d+\.?\d*)', re.IGNORECASE),
    'spo2': re.compile(r'SpO2\s*:?\s*(\d+)', re.IGNORECASE),
}


class RiskService:
    """
    인수인계 위험도 분석 서비스.
    
    사용 예시:
        result = RiskService.analyze(handover)
        # result = {'score': 75, 'level': 'HIGH', 'rules': [...]}
    """

    @classmethod
    def analyze_and_save(cls, handover: Handover) -> RiskAssessment:
        """
        인수인계를 분석하고 결과를 DB에 저장.
        기존 분석 결과가 있으면 업데이트.
        """
        result = cls.analyze(handover)

        # 기존 결과 업데이트 or 신규 생성
        assessment = handover.risk_assessment
        if not assessment:
            assessment = RiskAssessment(handover_id=handover.id)
            db.session.add(assessment)

        assessment.risk_score      = result['score']
        assessment.risk_level      = result['level']
        assessment.triggered_rules = json.dumps(result['rules'], ensure_ascii=False)
        assessment.vital_flag      = result['vital_flag']
        assessment.keyword_flag    = result['keyword_flag']
        assessment.frequency_flag  = result['frequency_flag']
        assessment.created_at      = datetime.utcnow()

        # Handover의 has_danger와 priority도 업데이트
        handover.has_danger     = result['score'] >= 40
        handover.danger_keywords = ', '.join(result['found_keywords'])
        handover.priority       = cls._score_to_priority(result['score'])

        db.session.commit()
        return assessment

    @classmethod
    def analyze(cls, handover: Handover) -> dict:
        """
        인수인계 위험도 분석 (DB 저장 없이 결과만 반환).
        
        Returns:
            {
                'score': int,           # 0~100
                'level': str,           # CRITICAL/HIGH/MEDIUM/LOW
                'rules': list,          # 발동된 규칙 목록
                'found_keywords': list, # 감지된 키워드
                'vital_flag': bool,
                'keyword_flag': bool,
                'frequency_flag': bool,
            }
        """
        # 분석할 전체 텍스트 합치기
        full_text = ' '.join(filter(None, [
            handover.content or '',
            handover.vital_signs or '',
            handover.medications or '',
            handover.procedures or '',
        ]))

        total_score    = 0
        triggered_rules = []
        found_keywords  = []
        keyword_flag   = False
        vital_flag     = False
        frequency_flag = False
        detected_categories = set()

        # ── 1. 키워드 분석 ────────────────────────────────────
        for category, rule in KEYWORD_RULES.items():
            for keyword in rule['keywords']:
                if keyword in full_text:
                    # 네거티브 컨텍스트 확인 (오탐 방지)
                    if cls._has_negative_context(full_text, keyword):
                        # 네거티브 컨텍스트가 있으면 점수 절반만 부여
                        adjusted_score = rule['score'] // 2
                        triggered_rules.append({
                            'type':     'KEYWORD_NEGATED',
                            'keyword':  keyword,
                            'category': category,
                            'score':    adjusted_score,
                            'note':     '네거티브 컨텍스트 감지 (부분 감점)',
                        })
                        total_score += adjusted_score
                    else:
                        triggered_rules.append({
                            'type':     'KEYWORD',
                            'keyword':  keyword,
                            'category': category,
                            'score':    rule['score'],
                        })
                        total_score    += rule['score']
                        keyword_flag    = True
                        found_keywords.append(keyword)
                        detected_categories.add(category)

        # ── 2. 바이탈 이상 감지 ───────────────────────────────
        if handover.vital_signs:
            vital_issues = cls._analyze_vitals(handover.vital_signs)
            for issue in vital_issues:
                triggered_rules.append({
                    'type':  'VITAL_ABNORMAL',
                    'field': issue['field'],
                    'value': issue['value'],
                    'score': 20,
                    'note':  issue['note'],
                })
                total_score += 20
                vital_flag   = True

        # ── 3. 복합 조건 보너스 ──────────────────────────────
        if len(detected_categories) >= 2:
            bonus = 10
            triggered_rules.append({
                'type':  'MULTI_CATEGORY_BONUS',
                'score': bonus,
                'note':  f'{len(detected_categories)}개 위험 카테고리 동시 감지',
            })
            total_score += bonus

        # ── 4. 반복 위험 감지 ────────────────────────────────
        if handover.patient_id and found_keywords:
            repeat_count = cls._check_repeat_danger(
                handover.patient_id,
                found_keywords,
                exclude_id=handover.id,
            )
            if repeat_count >= 2:
                bonus = 15
                triggered_rules.append({
                    'type':   'REPEAT_DANGER',
                    'score':  bonus,
                    'count':  repeat_count,
                    'note':   f'24시간 내 동일 위험 키워드 {repeat_count}회 반복',
                })
                total_score    += bonus
                frequency_flag  = True

        # ── 5. 점수 정규화 및 레벨 결정 ───────────────────────
        total_score = min(total_score, 100)  # 최대 100점
        level = cls._score_to_level(total_score)

        return {
            'score':          total_score,
            'level':          level,
            'rules':          triggered_rules,
            'found_keywords': list(set(found_keywords)),
            'vital_flag':     vital_flag,
            'keyword_flag':   keyword_flag,
            'frequency_flag': frequency_flag,
        }

    @staticmethod
    def _has_negative_context(text: str, keyword: str) -> bool:
        """
        키워드 주변 15자 이내에 네거티브 컨텍스트가 있는지 확인.
        예: "낙상 위험 없음" → "낙상" 주변에 "없음"이 있으므로 True 반환
        """
        idx = text.find(keyword)
        if idx == -1:
            return False

        # 키워드 전후 15자 추출
        start = max(0, idx - 15)
        end   = min(len(text), idx + len(keyword) + 15)
        context = text[start:end]

        for pattern in NEGATIVE_CONTEXT_PATTERNS:
            if re.search(pattern, context):
                return True
        return False

    @staticmethod
    def _analyze_vitals(vital_text: str) -> list:
        """
        활력징후 텍스트에서 이상 수치 감지.
        
        입력 예: "BP: 185/110  HR: 130  BT: 39.2  SpO2: 91%"
        """
        issues = []

        # 수축기 혈압
        m = VITAL_PATTERNS['bp_systolic'].search(vital_text)
        if m:
            val = int(m.group(1))
            if val >= 180:
                issues.append({'field': 'BP(수축기)', 'value': val,
                               'note': f'고혈압 위기: {val}mmHg'})
            elif val <= 90:
                issues.append({'field': 'BP(수축기)', 'value': val,
                               'note': f'저혈압: {val}mmHg'})

        # 맥박
        m = VITAL_PATTERNS['hr'].search(vital_text)
        if m:
            val = int(m.group(1))
            if val >= 120:
                issues.append({'field': 'HR', 'value': val,
                               'note': f'빈맥: {val}회/분'})
            elif val <= 50:
                issues.append({'field': 'HR', 'value': val,
                               'note': f'서맥: {val}회/분'})

        # 체온
        m = VITAL_PATTERNS['bt'].search(vital_text)
        if m:
            val = float(m.group(1))
            if val >= 38.5:
                issues.append({'field': 'BT', 'value': val,
                               'note': f'고열: {val}°C'})
            elif val <= 36.0:
                issues.append({'field': 'BT', 'value': val,
                               'note': f'저체온: {val}°C'})

        # 산소포화도
        m = VITAL_PATTERNS['spo2'].search(vital_text)
        if m:
            val = int(m.group(1))
            if val < 95:
                issues.append({'field': 'SpO2', 'value': val,
                               'note': f'산소포화도 저하: {val}%'})

        return issues

    @staticmethod
    def _check_repeat_danger(patient_id: int, keywords: list,
                             exclude_id: int = None, hours: int = 24) -> int:
        """
        동일 환자에 대해 지난 N시간 내 같은 위험 키워드가 포함된
        인수인계 수를 반환.
        """
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        query = (Handover.query
                 .filter(Handover.patient_id == patient_id)
                 .filter(Handover.has_danger == True)
                 .filter(Handover.created_at >= cutoff))

        if exclude_id:
            query = query.filter(Handover.id != exclude_id)

        recent = query.all()

        # 같은 키워드가 포함된 인수인계 수 계산
        count = 0
        for h in recent:
            if h.danger_keywords:
                for kw in keywords:
                    if kw in h.danger_keywords:
                        count += 1
                        break  # 한 인수인계당 1회만 카운트
        return count

    @staticmethod
    def _score_to_level(score: int) -> str:
        if score >= 80:
            return 'CRITICAL'
        elif score >= 60:
            return 'HIGH'
        elif score >= 40:
            return 'MEDIUM'
        return 'LOW'

    @staticmethod
    def _score_to_priority(score: int) -> str:
        if score >= 60:
            return 'URGENT'
        elif score >= 40:
            return 'HIGH'
        return 'NORMAL'

    # ── 통계 메서드 ──────────────────────────────────────────────

    @staticmethod
    def get_ward_risk_stats(ward: str, days: int = 7) -> dict:
        """병동별 위험도 통계 (대시보드용)"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        from app.models import Patient

        # 해당 병동 환자들의 인수인계 조회
        handovers = (Handover.query
                     .join(Patient)
                     .filter(Patient.ward == ward)
                     .filter(Handover.created_at >= cutoff)
                     .all())

        stats = {
            'total': len(handovers),
            'critical': 0, 'high': 0, 'medium': 0, 'low': 0,
            'danger_rate': 0.0,
        }

        for h in handovers:
            if h.risk_assessment:
                level = h.risk_assessment.risk_level
                stats[level.lower()] = stats.get(level.lower(), 0) + 1

        if stats['total'] > 0:
            danger_count = stats['critical'] + stats['high'] + stats['medium']
            stats['danger_rate'] = round(danger_count / stats['total'] * 100, 1)

        return stats
