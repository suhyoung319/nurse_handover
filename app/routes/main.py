from datetime import datetime
from flask import Blueprint, render_template
from flask_login import login_required
from app.models import Patient, Handover

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@main_bp.route('/dashboard')
@login_required
def dashboard():
    total_patients  = Patient.query.filter_by(status='입원중').count()
    total_handovers = Handover.query.count()
    danger_handovers = Handover.query.filter_by(has_danger=True).count()

    today = datetime.utcnow().date()
    today_start = datetime.combine(today, datetime.min.time())
    today_handovers = Handover.query.filter(Handover.created_at >= today_start).count()

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
        recent_handovers=recent_handovers,
        danger_list=danger_list,
    )
