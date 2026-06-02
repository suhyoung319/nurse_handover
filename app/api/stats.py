"""
api/stats.py — 통계 대시보드 API

병동 관리자/수간호사용 통계 데이터를 제공합니다.
"""

from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_login import login_required
from sqlalchemy import func
from app import db
from app.models import Handover, Patient, RiskAssessment, AuditLog
from app.middleware.rbac import require_permission

api_stats_bp = Blueprint('api_stats', __name__, url_prefix='/api/v1/stats')


@api_stats_bp.route('/dashboard', methods=['GET'])
@login_required
@require_permission('stats', 'read')
def dashboard_stats():
    """
    대시보드용 핵심 통계 한 번에 조회.
    7일 기준 집계.
    """
    days = request.args.get('days', 7, type=int)
    cutoff = datetime.utcnow() - timedelta(days=days)

    # 1. 전체 현황
    total_patients  = Patient.query.filter_by(status='입원중').count()
    total_handovers = Handover.query.filter(Handover.created_at >= cutoff).count()
    danger_handovers = Handover.query.filter(
        Handover.has_danger == True,
        Handover.created_at >= cutoff
    ).count()

    # 2. 위험도 레벨 분포
    risk_dist = (db.session.query(
                     RiskAssessment.risk_level,
                     func.count(RiskAssessment.id)
                 )
                 .join(Handover)
                 .filter(Handover.created_at >= cutoff)
                 .group_by(RiskAssessment.risk_level)
                 .all())
    risk_distribution = {level: count for level, count in risk_dist}

    # 3. 교대별 인수인계 수
    shift_dist = (db.session.query(
                      Handover.shift,
                      func.count(Handover.id)
                  )
                  .filter(Handover.created_at >= cutoff)
                  .group_by(Handover.shift)
                  .all())
    shift_distribution = {shift: count for shift, count in shift_dist}

    # 4. 일별 위험 인수인계 추이 (최근 7일)
    daily_danger = []
    for i in range(days - 1, -1, -1):
        day_start = datetime.utcnow().replace(hour=0, minute=0, second=0) - timedelta(days=i)
        day_end   = day_start + timedelta(days=1)
        count = Handover.query.filter(
            Handover.has_danger == True,
            Handover.created_at >= day_start,
            Handover.created_at < day_end
        ).count()
        daily_danger.append({
            'date':  day_start.strftime('%m/%d'),
            'count': count,
        })

    # 5. 병동별 위험 발생률
    ward_stats = (db.session.query(
                      Patient.ward,
                      func.count(Handover.id).label('total'),
                      func.sum(
                          db.case((Handover.has_danger == True, 1), else_=0)
                      ).label('danger_count')
                  )
                  .join(Handover, Handover.patient_id == Patient.id)
                  .filter(Handover.created_at >= cutoff)
                  .group_by(Patient.ward)
                  .all())

    ward_danger_rates = []
    for ward, total, danger_count in ward_stats:
        danger_count = danger_count or 0
        rate = round(danger_count / total * 100, 1) if total > 0 else 0
        ward_danger_rates.append({
            'ward':         ward,
            'total':        total,
            'danger_count': danger_count,
            'danger_rate':  rate,
        })

    # 6. 미확인 인수인계 (to_user 기준)
    unconfirmed = Handover.query.filter_by(is_confirmed=False).count()

    return jsonify({
        'period_days':       days,
        'total_patients':    total_patients,
        'total_handovers':   total_handovers,
        'danger_handovers':  danger_handovers,
        'unconfirmed':       unconfirmed,
        'danger_rate':       round(danger_handovers / total_handovers * 100, 1)
                             if total_handovers > 0 else 0,
        'risk_distribution': risk_distribution,
        'shift_distribution': shift_distribution,
        'daily_danger_trend': daily_danger,
        'ward_stats':        ward_danger_rates,
    }), 200


@api_stats_bp.route('/top-risk-patients', methods=['GET'])
@login_required
@require_permission('stats', 'read')
def top_risk_patients():
    """최근 N일 내 위험 인수인계가 가장 많은 환자 Top 10"""
    days = request.args.get('days', 7, type=int)
    cutoff = datetime.utcnow() - timedelta(days=days)

    results = (db.session.query(
                   Patient.id,
                   Patient.name,
                   Patient.ward,
                   Patient.patient_number,
                   func.count(Handover.id).label('danger_count'),
                   func.max(RiskAssessment.risk_score).label('max_score'),
               )
               .join(Handover, Handover.patient_id == Patient.id)
               .join(RiskAssessment, RiskAssessment.handover_id == Handover.id)
               .filter(Handover.has_danger == True)
               .filter(Handover.created_at >= cutoff)
               .group_by(Patient.id, Patient.name, Patient.ward, Patient.patient_number)
               .order_by(func.count(Handover.id).desc())
               .limit(10)
               .all())

    return jsonify({
        'data': [{
            'patient_id':     r.id,
            'name':           r.name,
            'ward':           r.ward,
            'patient_number': r.patient_number,
            'danger_count':   r.danger_count,
            'max_risk_score': r.max_score,
        } for r in results]
    }), 200
