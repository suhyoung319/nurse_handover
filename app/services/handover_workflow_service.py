"""
services/handover_workflow_service.py

인수인계 워크플로우 핵심 비즈니스 로직.

Route는 HTTP만 처리하고, 실제 업무 로직은 전부 여기서 처리합니다.
같은 로직을 웹뷰/REST API 양쪽에서 재사용할 수 있습니다.

[상태 흐름도]
  작성
   ↓
PENDING ──→ ACKNOWLEDGED (인계받은 사람이 확인)
   ↓
CANCELLED   (작성자 또는 관리자가 취소)
   ↓
TRANSFERRED (다른 사람에게 재인계 → 기존 건은 TRANSFERRED, 새 건 PENDING 생성)
"""

from datetime import datetime
from app import db
from app.models import Handover, Patient, User, HandoverAck
from app.services.audit_service import AuditService
from app.services.risk_service import RiskService


# 인수인계 타입
class HandoverType:
    ASSIGNMENT  = 'ASSIGNMENT'   # 실제 담당 인계 (active 중복 제한)
    NOTICE      = 'NOTICE'       # 참고 공유
    ESCALATION  = 'ESCALATION'   # 상급자 보고


# 인수인계 상태
class HandoverStatus:
    PENDING      = 'PENDING'
    ACKNOWLEDGED = 'ACKNOWLEDGED'
    CANCELLED    = 'CANCELLED'
    TRANSFERRED  = 'TRANSFERRED'


class HandoverWorkflowService:

    # ── 1. 인수인계 생성 ──────────────────────────────────────

    @classmethod
    def create_handover(cls, form_data: dict, from_user_id: int) -> tuple:
        """
        인수인계 생성.
        - ASSIGNMENT 타입이면 중복 active 여부 먼저 검사
        - 위험도 자동 분석
        - 감사 로그 기록

        Returns:
            (handover, error_message)
            성공 시 error_message = None
        """
        patient_id    = form_data.get('patient_id')
        to_user_id    = form_data.get('to_user_id')
        handover_type = form_data.get('handover_type', HandoverType.NOTICE)
        content       = form_data.get('content', '').strip()

        if not patient_id or not content:
            return None, '환자와 인수인계 내용은 필수입니다.'

        patient = Patient.query.get(patient_id)
        if not patient:
            return None, '존재하지 않는 환자입니다.'

        # ASSIGNMENT 타입: 동일 환자 active 중복 방지
        if handover_type == HandoverType.ASSIGNMENT and to_user_id:
            conflict = cls._get_active_assignment(patient_id)
            if conflict:
                to_name = conflict.to_user.name if conflict.to_user else '미지정'
                return None, (
                    f'이미 {to_name}에게 진행 중인 담당 인수인계가 있습니다. '
                    f'기존 인수인계를 확인하거나 대상자를 변경하세요.'
                )

        handover = Handover(
            patient_id    = patient_id,
            from_user_id  = from_user_id,
            to_user_id    = to_user_id,
            shift         = form_data.get('shift', '주간'),
            content       = content,
            vital_signs   = form_data.get('vital_signs', '').strip(),
            medications   = form_data.get('medications', '').strip(),
            procedures    = form_data.get('procedures', '').strip(),
            handover_type = handover_type,
            status        = HandoverStatus.PENDING,
            priority      = 'NORMAL',
        )
        db.session.add(handover)
        db.session.flush()  # ID 확보

        # 위험도 분석
        assessment = RiskService.analyze_and_save(handover)

        # 감사 로그
        AuditService.log_create(
            resource='handover',
            resource_id=handover.id,
            new_value={
                'patient': patient.name,
                'type':    handover_type,
                'shift':   handover.shift,
                'risk':    assessment.risk_level,
            },
            description=f'인수인계 작성 [{handover_type}] 환자: {patient.name}, 위험도: {assessment.risk_level}'
        )

        db.session.commit()
        return handover, None

    # ── 2. 인수인계 확인 (PENDING → ACKNOWLEDGED) ─────────────

    @classmethod
    def acknowledge(cls, handover_id: int, user_id: int, note: str = '') -> tuple:
        """
        인수인계 확인 처리.
        - 중복 확인 방지
        - 감사 로그에 기록
        Returns: (success: bool, message: str)
        """
        handover = Handover.query.get(handover_id)
        if not handover:
            return False, '인수인계를 찾을 수 없습니다.'

        if handover.status == HandoverStatus.CANCELLED:
            return False, '취소된 인수인계입니다.'

        # 이미 확인했는지 체크
        already = HandoverAck.query.filter_by(
            handover_id=handover_id, user_id=user_id
        ).first()
        if already:
            return False, '이미 확인한 인수인계입니다.'

        # 확인 기록 저장
        ack = HandoverAck(
            handover_id=handover_id,
            user_id=user_id,
            note=note,
            ack_at=datetime.utcnow(),
        )
        db.session.add(ack)

        # 인계받은 사람이 확인한 경우 → 상태 ACKNOWLEDGED 전환
        if handover.to_user_id == user_id:
            handover.status       = HandoverStatus.ACKNOWLEDGED
            handover.is_confirmed = True
            handover.confirmed_at = datetime.utcnow()
            handover.confirmed_by = user_id

        user = User.query.get(user_id)
        AuditService.log(
            action='ACKNOWLEDGE',
            resource='handover',
            resource_id=handover_id,
            description=f'{user.name if user else "?"} 가 인수인계 확인 (환자: {handover.patient.name})'
        )

        db.session.commit()
        return True, '인수인계를 확인했습니다.'

    # ── 3. 인수인계 취소 (→ CANCELLED) ───────────────────────

    @classmethod
    def cancel_handover(cls, handover_id: int, cancelled_by_id: int, reason: str = '') -> tuple:
        """
        인수인계 취소.
        작성자 본인 또는 admin/charge_nurse만 가능.
        """
        handover = Handover.query.get(handover_id)
        if not handover:
            return False, '인수인계를 찾을 수 없습니다.'

        if handover.status in (HandoverStatus.CANCELLED, HandoverStatus.TRANSFERRED):
            return False, f'이미 {handover.status} 상태입니다.'

        if handover.status == HandoverStatus.ACKNOWLEDGED:
            return False, '이미 확인된 인수인계는 취소할 수 없습니다.'

        old_value = handover.to_dict()
        handover.status       = HandoverStatus.CANCELLED
        handover.cancelled_at = datetime.utcnow()
        handover.cancelled_by = cancelled_by_id

        AuditService.log_update(
            resource='handover',
            resource_id=handover_id,
            old_value=old_value,
            new_value={'status': 'CANCELLED', 'reason': reason},
            description=f'인수인계 취소 (환자: {handover.patient.name}) 사유: {reason}'
        )

        db.session.commit()
        return True, '인수인계가 취소되었습니다.'

    # ── 4. 인수인계 대상 변경 (TRANSFERRED → 새 PENDING 생성) ─

    @classmethod
    def transfer_handover(cls, handover_id: int, new_to_user_id: int,
                          transferred_by_id: int, note: str = '') -> tuple:
        """
        인수인계 대상 변경.

        흐름:
        기존 A→B 인수인계 → TRANSFERRED 처리
        새로운 A→C 인수인계 → PENDING 으로 생성

        Returns: (new_handover, error_message)
        """
        original = Handover.query.get(handover_id)
        if not original:
            return None, '인수인계를 찾을 수 없습니다.'

        if original.status not in (HandoverStatus.PENDING,):
            return None, 'PENDING 상태의 인수인계만 대상을 변경할 수 있습니다.'

        new_user = User.query.get(new_to_user_id)
        if not new_user:
            return None, '변경할 대상 의료진을 찾을 수 없습니다.'

        # ASSIGNMENT 타입 중복 체크
        if original.handover_type == HandoverType.ASSIGNMENT:
            conflict = cls._get_active_assignment(original.patient_id)
            if conflict and conflict.id != handover_id:
                return None, f'이미 {conflict.to_user.name}에게 active 인수인계가 있습니다.'

        # 기존 건 TRANSFERRED 처리
        old_to_user = original.to_user.name if original.to_user else '미지정'
        original.status        = HandoverStatus.TRANSFERRED
        original.transferred_at = datetime.utcnow()
        original.transferred_to = new_to_user_id

        # 새 인수인계 생성 (내용 복사)
        new_handover = Handover(
            patient_id    = original.patient_id,
            from_user_id  = original.from_user_id,
            to_user_id    = new_to_user_id,
            shift         = original.shift,
            content       = original.content,
            vital_signs   = original.vital_signs,
            medications   = original.medications,
            procedures    = original.procedures,
            handover_type = original.handover_type,
            status        = HandoverStatus.PENDING,
            has_danger    = original.has_danger,
            danger_keywords = original.danger_keywords,
            priority      = original.priority,
        )
        db.session.add(new_handover)
        db.session.flush()

        # 위험도 복사 (재분석 생략)
        if original.risk_assessment:
            from app.models import RiskAssessment
            import json
            new_ra = RiskAssessment(
                handover_id    = new_handover.id,
                risk_score     = original.risk_assessment.risk_score,
                risk_level     = original.risk_assessment.risk_level,
                triggered_rules = original.risk_assessment.triggered_rules,
                vital_flag     = original.risk_assessment.vital_flag,
                keyword_flag   = original.risk_assessment.keyword_flag,
                frequency_flag = original.risk_assessment.frequency_flag,
            )
            db.session.add(new_ra)

        AuditService.log(
            action='TRANSFER',
            resource='handover',
            resource_id=handover_id,
            new_value={'from': old_to_user, 'to': new_user.name, 'new_id': new_handover.id},
            description=f'인수인계 대상 변경: {old_to_user} → {new_user.name} (환자: {original.patient.name})'
        )

        db.session.commit()
        return new_handover, None

    # ── 5. 받은 인수인계함 조회 ──────────────────────────────

    @classmethod
    def get_inbox(cls, user_id: int, filter_status: str = '') -> dict:
        """
        로그인 사용자의 받은 인수인계함.
        Returns:
            {
                'pending':      [...],  # 미확인
                'acknowledged': [...],  # 확인 완료
                'all':          [...],  # 전체
                'unread_count': int,
                'critical_count': int,
            }
        """
        base_q = Handover.query.filter_by(to_user_id=user_id)

        pending_list = (base_q
                        .filter_by(status=HandoverStatus.PENDING)
                        .order_by(Handover.created_at.desc())
                        .all())

        acked_list = (base_q
                      .filter_by(status=HandoverStatus.ACKNOWLEDGED)
                      .order_by(Handover.created_at.desc())
                      .limit(30)
                      .all())

        # 위험도 CRITICAL인 미확인
        critical_count = sum(
            1 for h in pending_list
            if h.risk_assessment and h.risk_assessment.risk_level == 'CRITICAL'
        )

        return {
            'pending':       pending_list,
            'acknowledged':  acked_list,
            'unread_count':  len(pending_list),
            'critical_count': critical_count,
        }

    @classmethod
    def get_unread_count(cls, user_id: int) -> int:
        """navbar 배지용 미확인 인수인계 수"""
        return Handover.query.filter_by(
            to_user_id=user_id,
            status=HandoverStatus.PENDING
        ).count()

    # ── 6. 환자별 인수인계 이력 ──────────────────────────────

    @classmethod
    def get_patient_history(cls, patient_id: int, limit: int = 20) -> list:
        """특정 환자의 인수인계 전체 이력 (최신순)"""
        return (Handover.query
                .filter_by(patient_id=patient_id)
                .order_by(Handover.created_at.desc())
                .limit(limit)
                .all())

    # ── 내부 헬퍼 ─────────────────────────────────────────────

    @classmethod
    def _get_active_assignment(cls, patient_id: int):
        """특정 환자의 현재 active ASSIGNMENT 인수인계 반환"""
        return (Handover.query
                .filter_by(
                    patient_id=patient_id,
                    handover_type=HandoverType.ASSIGNMENT,
                    status=HandoverStatus.PENDING,
                )
                .first())
