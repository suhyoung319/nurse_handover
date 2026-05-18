"""
routes/main.py

변경: 로그인 후 기본 첫 화면을 받은 인수인계함으로 리다이렉트.
대시보드는 /dashboard 로 분리 유지.
"""

from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from app.models import Patient, Handover, RiskAssessment
from sqlalchemy import func
from app import db

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@login_required
def index():
    # 로그인 후 첫 화면 = 받은 인수인계함
    return redirect(url_for('inbox.index'))


@main_bp.route('/dashboard')
@login_required
def dashboard():
    total_patients   = Patient.query.filter_by(status='입원중').count()
    total_handovers  = Handover.query.count()
    danger_handovers = Handover.query.filter_by(has_danger=True).count()

    today       = datetime.utcnow().date()
    today_start = datetime.combine(today, datetime.min.time())
    today_handovers = Handover.query.filter(Handover.created_at >= today_start).count()

    # 미확인 인수인계 (내가 받은 것 중 미확인)
    my_unread = Handover.query.filter_by(
        to_user_id=current_user.id,
        is_confirmed=False
    ).count()

    recent_handovers = (Handover.query
                        .order_by(Handover.created_at.desc())
                        .limit(5).all())

    danger_list = (Handover.query
                   .filter_by(has_danger=True)
                   .order_by(Handover.created_at.desc())
                   .limit(5).all())

    return render_template('main/dashboard.html',
        total_patients=total_patients,
        total_handovers=total_handovers,
        danger_handovers=danger_handovers,
        today_handovers=today_handovers,
        my_unread=my_unread,
        recent_handovers=recent_handovers,
        danger_list=danger_list,
    )
