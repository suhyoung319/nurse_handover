"""
routes/handover.py

변경사항:
- 전체 인수인계 목록: nurse는 자기 병동만, admin/charge_nurse/doctor는 전체
- 환자 삭제: admin/charge_nurse만 가능
- 회원가입 role: 기본값 nurse (선택 UI 제거)
"""

from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Handover, Patient, User, HandoverAck, RiskAssessment
from app.services.audit_service import AuditService
from app.services.risk_service import RiskService
from app.middleware.rbac import require_permission

handover_bp = Blueprint('handover', __name__, url_prefix='/handovers')

RISK_COLOR = {
    'CRITICAL': 'danger',
    'HIGH':     'warning',
    'MEDIUM':   'info',
    'LOW':      'success',
}


@handover_bp.route('/')
@login_required
def index():
    """
    전체 인수인계 목록.
    - nurse: 자기 병동 환자 관련 인수인계만 조회
    - charge_nurse / doctor / admin: 전체 조회
    """
    page        = request.args.get('page', 1, type=int)
    shift       = request.args.get('shift', '')
    danger_only = request.args.get('danger_only', '')
    risk_level  = request.args.get('risk_level', '')
    ward_filter = request.args.get('ward', '')

    q = Handover.query

    # ── 병동 접근 제한 ───────────────────────────────────────
    if current_user.role == 'nurse':
        # nurse는 자기 병동 환자 인수인계만
        if current_user.ward:
            q = (q.join(Patient, Handover.patient_id == Patient.id)
                   .filter(Patient.ward == current_user.ward))
        else:
            # 병동 미지정 nurse는 본인 관련만
            q = q.filter(
                (Handover.from_user_id == current_user.id) |
                (Handover.to_user_id   == current_user.id)
            )

    # ── 필터 ─────────────────────────────────────────────────
    if shift:
        q = q.filter(Handover.shift == shift)
    if danger_only:
        q = q.filter(Handover.has_danger == True)
    if risk_level:
        q = q.join(RiskAssessment, isouter=True).filter(
            RiskAssessment.risk_level == risk_level
        )
    if ward_filter and current_user.role != 'nurse':
        q = q.join(Patient, Handover.patient_id == Patient.id, isouter=True).filter(
            Patient.ward == ward_filter
        )

    handovers = q.order_by(Handover.created_at.desc()).paginate(page=page, per_page=15)

    # 병동 목록 (필터용)
    wards = [r[0] for r in db.session.query(Patient.ward).distinct().all()]

    return render_template('handover/index.html',
        handovers=handovers,
        shift=shift,
        danger_only=danger_only,
        risk_level=risk_level,
        ward_filter=ward_filter,
        wards=wards,
        RISK_COLOR=RISK_COLOR,
        is_restricted=(current_user.role == 'nurse'),
    )


@handover_bp.route('/create', methods=['GET', 'POST'])
@handover_bp.route('/create/<int:patient_id>', methods=['GET', 'POST'])
@login_required
@require_permission('handover', 'write')
def create(patient_id=None):
    patients = Patient.query.filter_by(status='입원중').order_by(Patient.name).all()
    users    = User.query.filter(
        User.id != current_user.id,
        User.is_active == True
    ).order_by(User.name).all()

    if request.method == 'POST':
        pid     = request.form.get('patient_id', type=int)
        content = request.form.get('content', '').strip()

        if not pid or not content:
            flash('환자와 인수인계 내용은 필수입니다.', 'danger')
            return render_template('handover/form.html',
                handover=None, patients=patients,
                users=users, selected_patient_id=patient_id)

        handover = Handover(
            patient_id   = pid,
            from_user_id = current_user.id,
            to_user_id   = request.form.get('to_user_id', type=int),
            shift        = request.form.get('shift', '주간'),
            content      = content,
            vital_signs  = request.form.get('vital_signs', '').strip(),
            medications  = request.form.get('medications', '').strip(),
            procedures   = request.form.get('procedures',  '').strip(),
        )
        db.session.add(handover)
        db.session.flush()

        assessment = RiskService.analyze_and_save(handover)
        patient    = Patient.query.get(pid)

        AuditService.log_create(
            resource='handover',
            resource_id=handover.id,
            new_value={'patient': patient.name if patient else '?',
                       'shift': handover.shift,
                       'risk_level': assessment.risk_level},
            description=f'인수인계 작성 (환자: {patient.name if patient else "?"}, 위험도: {assessment.risk_level})'
        )

        db.session.commit()

        level = assessment.risk_level
        if level == 'CRITICAL':
            flash(f'🚨 [CRITICAL] 즉각 대응 필요! 위험 점수: {assessment.risk_score}점', 'danger')
        elif level == 'HIGH':
            flash(f'⚠️ [HIGH] 위험 인수인계 저장됨. 점수: {assessment.risk_score}점', 'warning')
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
        RISK_COLOR=RISK_COLOR,
    )


@handover_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@require_permission('handover', 'write')
def edit(id):
    handover = Handover.query.get_or_404(id)

    if (handover.from_user_id != current_user.id and
            current_user.role not in ('admin', 'charge_nurse')):
        flash('본인이 작성한 인수인계만 수정할 수 있습니다.', 'danger')
        return redirect(url_for('inbox.sent'))

    if handover.is_confirmed:
        flash('이미 확인된 인수인계는 수정할 수 없습니다.', 'warning')
        return redirect(url_for('handover.detail', id=id))

    patients = Patient.query.filter_by(status='입원중').all()
    users    = User.query.filter(User.id != current_user.id).all()

    if request.method == 'POST':
        old_value = handover.to_dict()

        handover.patient_id  = request.form.get('patient_id', type=int)
        handover.to_user_id  = request.form.get('to_user_id', type=int)
        handover.shift       = request.form.get('shift', '주간')
        handover.content     = request.form.get('content', '').strip()
        handover.vital_signs = request.form.get('vital_signs', '').strip()
        handover.medications = request.form.get('medications', '').strip()
        handover.procedures  = request.form.get('procedures',  '').strip()
        handover.updated_at  = datetime.utcnow()

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
