"""
[적용 방법]
기존 app/routes/handover.py 의 create() 함수를
이 파일의 create() 함수로 교체하세요.

변경사항:
- HandoverWorkflowService.create_handover() 호출로 교체
- handover_type 폼 필드 추가 처리
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Handover, Patient, User, HandoverAck
from app.services.handover_workflow_service import HandoverWorkflowService, HandoverStatus
from app.services.audit_service import AuditService
from app.services.risk_service import RiskService
from app.middleware.rbac import require_permission
from datetime import datetime

handover_bp = Blueprint('handover', __name__, url_prefix='/handovers')


@handover_bp.route('/')
@login_required
def index():
    page        = request.args.get('page', 1, type=int)
    shift       = request.args.get('shift', '')
    danger_only = request.args.get('danger_only', '')
    risk_level  = request.args.get('risk_level', '')
    status      = request.args.get('status', '')         # NEW: 상태 필터

    q = Handover.query
    if shift:
        q = q.filter_by(shift=shift)
    if danger_only:
        q = q.filter_by(has_danger=True)
    if status:
        q = q.filter_by(status=status)
    if risk_level:
        from app.models import RiskAssessment
        q = q.join(RiskAssessment).filter(RiskAssessment.risk_level == risk_level)

    handovers = q.order_by(Handover.created_at.desc()).paginate(page=page, per_page=15)
    return render_template('handover/index.html',
                           handovers=handovers, shift=shift,
                           danger_only=danger_only, risk_level=risk_level,
                           status=status)


@handover_bp.route('/create', methods=['GET', 'POST'])
@handover_bp.route('/create/<int:patient_id>', methods=['GET', 'POST'])
@login_required
@require_permission('handover', 'write')
def create(patient_id=None):
    patients = Patient.query.filter_by(status='입원중').order_by(Patient.name).all()
    users    = User.query.filter(User.id != current_user.id, User.is_active == True).all()

    if request.method == 'POST':
        form_data = {
            'patient_id':    request.form.get('patient_id', type=int),
            'to_user_id':    request.form.get('to_user_id', type=int),
            'handover_type': request.form.get('handover_type', 'NOTICE'),
            'shift':         request.form.get('shift', '주간'),
            'content':       request.form.get('content', '').strip(),
            'vital_signs':   request.form.get('vital_signs', '').strip(),
            'medications':   request.form.get('medications', '').strip(),
            'procedures':    request.form.get('procedures', '').strip(),
        }

        handover, error = HandoverWorkflowService.create_handover(
            form_data, current_user.id
        )

        if error:
            flash(error, 'danger')
            return render_template('handover/form.html',
                                   handover=None, patients=patients,
                                   users=users, selected_patient_id=patient_id)

        # 위험도에 따른 메시지
        level = handover.risk_assessment.risk_level if handover.risk_assessment else 'LOW'
        if level == 'CRITICAL':
            flash(f'🚨 [CRITICAL] 즉각 대응 필요! 위험 점수: {handover.risk_assessment.risk_score}점', 'danger')
        elif level == 'HIGH':
            flash(f'⚠️ [HIGH] 위험 인수인계 저장됨. 점수: {handover.risk_assessment.risk_score}점', 'warning')
        else:
            flash('인수인계가 저장되었습니다.', 'success')

        return redirect(url_for('handover.detail', id=handover.id))

    return render_template('handover/form.html',
                           handover=None, patients=patients,
                           users=users, selected_patient_id=patient_id)


@handover_bp.route('/<int:id>')
@login_required
def detail(id):
    handover = Handover.query.get_or_404(id)

    AuditService.log_view(
        resource='handover',
        resource_id=id,
        description=f'인수인계 상세 조회 (환자: {handover.patient.name})'
    )

    if not handover.risk_assessment:
        RiskService.analyze_and_save(handover)

    already_acked = HandoverAck.query.filter_by(
        handover_id=id, user_id=current_user.id
    ).first() is not None

    return render_template('handover/detail.html',
                           handover=handover,
                           already_acked=already_acked,
                           HandoverStatus=HandoverStatus)


@handover_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@require_permission('handover', 'write')
def edit(id):
    handover = Handover.query.get_or_404(id)

    if (handover.from_user_id != current_user.id and
            current_user.role not in ('admin', 'charge_nurse')):
        flash('본인이 작성한 인수인계만 수정할 수 있습니다.', 'danger')
        return redirect(url_for('handover.index'))

    if handover.status == HandoverStatus.ACKNOWLEDGED:
        flash('이미 확인된 인수인계는 수정할 수 없습니다.', 'warning')
        return redirect(url_for('handover.detail', id=id))

    patients = Patient.query.filter_by(status='입원중').all()
    users    = User.query.filter(User.id != current_user.id).all()

    if request.method == 'POST':
        old_value = handover.to_dict()

        handover.patient_id    = request.form.get('patient_id', type=int)
        handover.to_user_id    = request.form.get('to_user_id', type=int)
        handover.shift         = request.form.get('shift', '주간')
        handover.content       = request.form.get('content', '').strip()
        handover.vital_signs   = request.form.get('vital_signs', '').strip()
        handover.medications   = request.form.get('medications', '').strip()
        handover.procedures    = request.form.get('procedures', '').strip()
        handover.handover_type = request.form.get('handover_type', 'NOTICE')
        handover.updated_at    = datetime.utcnow()

        assessment = RiskService.analyze_and_save(handover)
        AuditService.log_update(
            resource='handover',
            resource_id=id,
            old_value=old_value,
            new_value=handover.to_dict(),
            description=f'인수인계 수정 → 위험도: {assessment.risk_level}'
        )

        db.session.commit()
        flash('인수인계가 수정되었습니다.', 'success')
        return redirect(url_for('handover.detail', id=handover.id))

    return render_template('handover/form.html',
                           handover=handover, patients=patients,
                           users=users, selected_patient_id=None)


@handover_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@require_permission('handover', 'delete')
def delete(id):
    handover = Handover.query.get_or_404(id)

    if (handover.from_user_id != current_user.id and
            current_user.role != 'admin'):
        flash('권한이 없습니다.', 'danger')
        return redirect(url_for('handover.index'))

    AuditService.log_delete(
        resource='handover',
        resource_id=id,
        old_value=handover.to_dict(),
        description=f'인수인계 삭제 (환자: {handover.patient.name})'
    )

    db.session.delete(handover)
    db.session.commit()
    flash('인수인계가 삭제되었습니다.', 'warning')
    return redirect(url_for('handover.index'))


@handover_bp.route('/check-keywords', methods=['POST'])
@login_required
def check_keywords():
    text = request.json.get('text', '')
    temp = Handover(
        content=text,
        vital_signs=request.json.get('vital_signs', ''),
        medications=request.json.get('medications', ''),
        procedures=request.json.get('procedures', ''),
        patient_id=1,
        from_user_id=current_user.id,
    )
    result = RiskService.analyze(temp)
    return jsonify({
        'has_danger':  result['score'] >= 40,
        'keywords':    result['found_keywords'],
        'risk_score':  result['score'],
        'risk_level':  result['level'],
        'vital_flag':  result['vital_flag'],
        'rules':       result['rules'][:5],
    })
