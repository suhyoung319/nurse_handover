"""
routes/audit.py — 감사 로그 웹 뷰 (관리자/수간호사 전용)
"""

from flask import Blueprint, render_template, request
from flask_login import login_required
from app.models import AuditLog, User
from app.middleware.rbac import require_permission

audit_bp = Blueprint('audit', __name__, url_prefix='/audit')


@audit_bp.route('/')
@login_required
@require_permission('audit_log', 'read')
def index():
    """감사 로그 목록"""
    page       = request.args.get('page', 1, type=int)
    action     = request.args.get('action', '')
    resource   = request.args.get('resource', '')
    user_id    = request.args.get('user_id', type=int)

    q = AuditLog.query
    if action:
        q = q.filter_by(action=action)
    if resource:
        q = q.filter_by(resource=resource)
    if user_id:
        q = q.filter_by(user_id=user_id)

    logs  = q.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=30)
    users = User.query.order_by(User.name).all()

    return render_template('audit/index.html',
                           logs=logs, users=users,
                           action=action, resource=resource, user_id=user_id)
