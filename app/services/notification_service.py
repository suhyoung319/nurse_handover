"""
services/notification_service.py — 알림 시스템

[설계 원칙]
현재: DB 기반 Polling (5초마다 미확인 수 확인)
확장: Flask-SocketIO로 WebSocket 전환 시 이 서비스만 수정하면 됨

Polling API: GET /api/v1/notifications/unread-count
→ navbar 배지 숫자 실시간 업데이트
→ CRITICAL 인수인계 있으면 팝업 알림 표시
"""

from datetime import datetime, timedelta
from app.models import Handover


class NotificationService:

    @staticmethod
    def get_unread_summary(user_id: int) -> dict:
        """
        미확인 인수인계 요약.
        Polling API가 5초마다 호출하는 경량 엔드포인트.

        Returns:
            {
                'unread_count':   int,   # 전체 미확인
                'critical_count': int,   # CRITICAL 위험도 미확인
                'urgent_count':   int,   # URGENT 우선순위 미확인
                'has_new':        bool,  # 최근 1분 내 새 인수인계 도착 여부
                'latest': {             # 가장 최근 미확인 정보
                    'patient_name': str,
                    'from_user':    str,
                    'risk_level':   str,
                    'created_at':   str,
                } | None
            }
        """
        pending = (Handover.query
                   .filter_by(to_user_id=user_id, is_confirmed=False)
                   .order_by(Handover.created_at.desc())
                   .all())

        unread_count  = len(pending)
        critical_count = 0
        urgent_count   = 0
        has_new        = False
        latest         = None
        one_min_ago    = datetime.utcnow() - timedelta(minutes=1)

        for h in pending:
            if h.risk_assessment and h.risk_assessment.risk_level == 'CRITICAL':
                critical_count += 1
            if h.priority == 'URGENT':
                urgent_count += 1
            if h.created_at and h.created_at >= one_min_ago:
                has_new = True

        if pending:
            first = pending[0]
            latest = {
                'patient_name': first.patient.name if first.patient else '?',
                'from_user':    first.from_user.name if first.from_user else '?',
                'risk_level':   first.risk_assessment.risk_level if first.risk_assessment else 'LOW',
                'created_at':   first.created_at.strftime('%H:%M') if first.created_at else '',
            }

        return {
            'unread_count':   unread_count,
            'critical_count': critical_count,
            'urgent_count':   urgent_count,
            'has_new':        has_new,
            'latest':         latest,
        }
