"""
api/notifications.py — 알림 Polling API

프론트엔드 JS가 5초마다 호출해서 미확인 인수인계 수를 확인합니다.
Flask-SocketIO 전환 시 이 파일만 수정하면 됩니다.
"""

from flask import Blueprint, jsonify
from flask_login import login_required, current_user
from app.services.notification_service import NotificationService

api_notifications_bp = Blueprint('api_notifications', __name__,
                                  url_prefix='/api/v1/notifications')


@api_notifications_bp.route('/unread-count')
@login_required
def unread_count():
    """
    미확인 인수인계 요약 (navbar 배지 + 팝업용).
    5초마다 폴링 — 응답이 가벼워야 함.
    """
    summary = NotificationService.get_unread_summary(current_user.id)
    return jsonify(summary), 200
