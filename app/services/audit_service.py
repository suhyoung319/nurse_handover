"""
services/audit_service.py — 감사 로그 서비스

[깊은 설명 — Audit Log 시스템]

## 왜 Audit Log가 의료 시스템에서 필수인가?

1. 법적 요건
   - 의료법 시행규칙: 전자의무기록 접근 이력 보존 의무 (3년)
   - HIPAA (미국) / 국내 개인정보보호법: 민감 정보 접근 추적

2. 의료 사고 대응
   - "누가 이 인수인계를 마지막으로 수정했나?"
   - "이 환자 정보를 누가 언제 조회했나?"
   - 분쟁 발생 시 책임 소재 명확화

3. 내부 감사
   - 비정상 접근 패턴 탐지 (새벽 3시에 대량 조회 등)
   - 퇴직 직원 계정 접근 탐지

## 구현 설계 결정

## 방법 1: 각 라우트에서 수동 호출 (현재 방식)
   → 개발자가 까먹으면 로그 누락 발생
   → 권장하지 않음

## 방법 2: SQLAlchemy Event Listener (우리가 선택)
   → 모델 레이어에서 자동으로 감지
   → 코드 누락 위험 없음
   → 단, Flask request context가 없는 환경에서도 동작해야 함

## 방법 3: Flask before/after_request 훅
   → HTTP 요청 단위로 기록
   → 읽기(GET)까지 모두 기록 가능
   → 과도한 로그 생성 위험

우리는 방법 2 + 방법 3을 혼합:
- 데이터 변경 (CREATE/UPDATE/DELETE): SQLAlchemy 이벤트
- 민감 데이터 조회 (VIEW): 명시적 호출
- 인증 이벤트 (LOGIN/LOGOUT): 명시적 호출
"""

import json
from datetime import datetime
from flask import request as flask_request, g, has_request_context
from app import db
from app.models import AuditLog


class AuditService:
    """
    감사 로그 기록 서비스.
    
    사용 예시:
        AuditService.log(
            action='UPDATE',
            resource='handover',
            resource_id=handover.id,
            old_value=old_dict,
            new_value=new_dict,
            description='인수인계 내용 수정'
        )
    """

    @staticmethod
    def _get_user_id():
        """현재 로그인 사용자 ID 추출 (request context 없어도 안전)"""
        try:
            from flask_login import current_user
            if current_user and current_user.is_authenticated:
                return current_user.id
        except Exception:
            pass
        return None

    @staticmethod
    def _get_ip():
        """클라이언트 IP 추출 (프록시 환경 고려)"""
        if not has_request_context():
            return None
        # X-Forwarded-For: 프록시/로드밸런서 뒤에 있을 때 실제 IP
        forwarded_for = flask_request.headers.get('X-Forwarded-For')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        return flask_request.remote_addr

    @staticmethod
    def _get_user_agent():
        if not has_request_context():
            return None
        return flask_request.headers.get('User-Agent', '')[:500]

    @staticmethod
    def _serialize(value):
        """dict/list를 JSON 문자열로 변환 (None 안전)"""
        if value is None:
            return None
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(value)

    @classmethod
    def log(cls,
            action: str,
            resource: str,
            resource_id: int = None,
            old_value: dict = None,
            new_value: dict = None,
            description: str = None,
            user_id: int = None):
        """
        감사 로그 기록.
        
        Args:
            action: 행위 유형 (CREATE/READ/UPDATE/DELETE/LOGIN/LOGOUT/ACCESS_DENIED)
            resource: 대상 리소스 ('handover', 'patient', 'user', 'auth')
            resource_id: 대상 레코드 ID
            old_value: 변경 전 값 (dict)
            new_value: 변경 후 값 (dict)
            description: 사람이 읽기 좋은 설명
            user_id: 행위자 ID (None이면 현재 로그인 사용자)
        """
        try:
            log = AuditLog(
                user_id     = user_id or cls._get_user_id(),
                action      = action,
                resource    = resource,
                resource_id = resource_id,
                old_value   = cls._serialize(old_value),
                new_value   = cls._serialize(new_value),
                ip_address  = cls._get_ip(),
                user_agent  = cls._get_user_agent(),
                description = description,
                created_at  = datetime.utcnow(),
            )
            db.session.add(log)
            db.session.commit()
        except Exception as e:
            # 감사 로그 실패가 실제 업무를 막으면 안 됨
            # 실제 운영에서는 별도 파일/외부 시스템에 백업 기록
            db.session.rollback()
            import logging
            logging.getLogger('audit').error(f'AuditLog 기록 실패: {e}')

    # ── 편의 메서드 ──────────────────────────────────────────

    @classmethod
    def log_create(cls, resource, resource_id, new_value=None, description=None):
        cls.log('CREATE', resource, resource_id,
                new_value=new_value, description=description)

    @classmethod
    def log_update(cls, resource, resource_id, old_value, new_value, description=None):
        cls.log('UPDATE', resource, resource_id,
                old_value=old_value, new_value=new_value, description=description)

    @classmethod
    def log_delete(cls, resource, resource_id, old_value=None, description=None):
        cls.log('DELETE', resource, resource_id,
                old_value=old_value, description=description)

    @classmethod
    def log_view(cls, resource, resource_id, description=None):
        """민감한 데이터 조회 시 기록 (환자 정보, 상세 인수인계 등)"""
        cls.log('READ', resource, resource_id, description=description)

    @classmethod
    def log_login(cls, user_id, success: bool):
        cls.log(
            action='LOGIN' if success else 'LOGIN_FAILED',
            resource='auth',
            user_id=user_id,
            description='로그인 성공' if success else '로그인 실패',
        )

    @classmethod
    def log_logout(cls):
        cls.log('LOGOUT', resource='auth', description='로그아웃')

    @classmethod
    def log_access_denied(cls, resource, resource_id=None):
        cls.log(
            action='ACCESS_DENIED',
            resource=resource,
            resource_id=resource_id,
            description=f'권한 없음: {resource}',
        )

    # ── 조회 메서드 ──────────────────────────────────────────

    @staticmethod
    def get_logs_for_resource(resource: str, resource_id: int, limit: int = 50):
        """특정 리소스의 감사 로그 조회"""
        return (AuditLog.query
                .filter_by(resource=resource, resource_id=resource_id)
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
                .all())

    @staticmethod
    def get_logs_for_user(user_id: int, limit: int = 100):
        """특정 사용자의 행위 이력 조회"""
        return (AuditLog.query
                .filter_by(user_id=user_id)
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
                .all())

    @staticmethod
    def get_recent_danger_events(hours: int = 24, limit: int = 20):
        """최근 위험 이벤트 조회 (ACCESS_DENIED 등)"""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return (AuditLog.query
                .filter(AuditLog.action.in_(['ACCESS_DENIED', 'LOGIN_FAILED']))
                .filter(AuditLog.created_at >= cutoff)
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
                .all())
