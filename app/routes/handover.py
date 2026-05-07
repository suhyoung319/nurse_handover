"""
routes/handover.py — 고도화 버전

변경사항 (기존 대비):
  1. 저장 시 RiskService.analyze_and_save() 자동 호출
  2. 상세 조회 시 AuditService.log_view() 기록
  3. 수정/삭제 시 AuditService.log_update/delete() 기록
  4. 인수인계 확인(acknowledge) 기능 추가
"""

from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Handover, Patient, User, HandoverAck
from app.services.audit_service import AuditService
from app.services.risk_service import RiskService
from app.middleware.rbac import require_permission

handover_bp = Blueprint('handover', __name__, url_prefix='/handovers')


@handover_bp.route('/')
@login_required
def index():
    page        = request.args.get('page', 1, type=int)
    shift       = request.args.get('shift', '')
    danger_only = request.args.get('danger_only', '')
    risk_level  = request.args.get('risk_level', '')

    q = Handover.query
    if shift:
        q = q.filter_by(shift=shift)
    if danger_only:
        q = q.filter_by(has_danger=True)
    if risk_level:
        from app.models import RiskAssessment
        q = q.join(RiskAssessment).filter(RiskAssessment.risk_level == risk_level)

    handovers = q.order_by(Handover.created_at.desc()).paginate(page=page, per_page=15)
    return render_template('handover/index.html',
                           handovers=handovers, shift=shift,
                           danger_only=danger_only, risk_level=risk_level)


@handover_bp.route('/create', methods=['GET', 'POST'])
@handover_bp.route('/create/<int:patient_id>', methods=['GET', 'POST'])
@login_required
@require_permission('handover', 'write')
def create(patient_id=None):
    patients = Patient.query.filter_by(status='입원중').order_by(Patient.name).all()
    users    = User.query.filter(User.id != current_user.id).all()

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
        db.session.flush()  # ID 확보

        # ① 위험도 자동 분석 (기존 단순 키워드→고도화 엔진으로 대체)
        assessment = RiskService.analyze_and_save(handover)

        # ② 감사 로그 기록
        patient = Patient.query.get(pid)
        AuditService.log_create(
            resource='handover',
            resource_id=handover.id,
            new_value={'patient': patient.name, 'shift': handover.shift,
                       'risk_level': assessment.risk_level},
            description=f'인수인계 작성 (환자: {patient.name}, 위험도: {assessment.risk_level})'
        )

        db.session.commit()

        # 위험도에 따라 다른 메시지 표시
        level = assessment.risk_level
        if level == 'CRITICAL':
            flash(f'🚨 [CRITICAL] 즉각 대응이 필요합니다! 위험 점수: {assessment.risk_score}점', 'danger')
        elif level == 'HIGH':
            flash(f'⚠️ [HIGH] 위험 인수인계가 저장되었습니다. 점수: {assessment.risk_score}점', 'warning')
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

    # 민감 정보 조회 감사 로그
    AuditService.log_view(
        resource='handover',
        resource_id=id,
        description=f'인수인계 상세 조회 (환자: {handover.patient.name})'
    )

    # 분석 결과가 없으면 실시간 생성
    if not handover.risk_assessment:
        RiskService.analyze_and_save(handover)

    # 현재 사용자의 확인 여부
    already_acked = HandoverAck.query.filter_by(
        handover_id=id, user_id=current_user.id
    ).first() is not None

    return render_template('handover/detail.html',
                           handover=handover,
                           already_acked=already_acked)


@handover_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@require_permission('handover', 'write')
def edit(id):
    handover = Handover.query.get_or_404(id)

    # 작성자 본인 또는 수간호사/admin만 수정 가능
    if (handover.from_user_id != current_user.id and
            current_user.role not in ('admin', 'charge_nurse')):
        flash('본인이 작성한 인수인계만 수정할 수 있습니다.', 'danger')
        return redirect(url_for('handover.index'))

    patients = Patient.query.filter_by(status='입원중').all()
    users    = User.query.filter(User.id != current_user.id).all()

    if request.method == 'POST':
        old_value = handover.to_dict()  # 변경 전 스냅샷

        handover.patient_id  = request.form.get('patient_id', type=int)
        handover.to_user_id  = request.form.get('to_user_id', type=int)
        handover.shift       = request.form.get('shift', '주간')
        handover.content     = request.form.get('content', '').strip()
        handover.vital_signs = request.form.get('vital_signs', '').strip()
        handover.medications = request.form.get('medications', '').strip()
        handover.procedures  = request.form.get('procedures',  '').strip()
        handover.updated_at  = datetime.utcnow()

        # 위험도 재분석
        assessment = RiskService.analyze_and_save(handover)

        # 감사 로그
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

    # 삭제 전 감사 로그
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


@handover_bp.route('/<int:id>/acknowledge', methods=['POST'])
@login_required
def acknowledge(id):
    """인수인계 확인 처리 (웹뷰용)"""
    handover = Handover.query.get_or_404(id)

    existing = HandoverAck.query.filter_by(
        handover_id=id, user_id=current_user.id
    ).first()

    if not existing:
        ack = HandoverAck(
            handover_id=id,
            user_id=current_user.id,
            note=request.form.get('note', ''),
        )
        db.session.add(ack)

        if handover.to_user_id == current_user.id:
            handover.is_confirmed = True
            handover.confirmed_at = datetime.utcnow()
            handover.confirmed_by = current_user.id

        AuditService.log('ACKNOWLEDGE', 'handover', id,
                         description='인수인계 확인')
        db.session.commit()
        flash('인수인계를 확인했습니다.', 'success')
    else:
        flash('이미 확인한 인수인계입니다.', 'info')

    return redirect(url_for('handover.detail', id=id))


@handover_bp.route('/check-keywords', methods=['POST'])
@login_required
def check_keywords():
    """AJAX 실시간 키워드 감지 (기존 유지)"""
    text = request.json.get('text', '')

    # 임시 Handover 객체로 분석 (DB 저장 없이)
    temp = Handover(
        content=text,
        vital_signs=request.json.get('vital_signs', ''),
        medications=request.json.get('medications', ''),
        procedures=request.json.get('procedures', ''),
        patient_id=1,  # 임시값
        from_user_id=current_user.id,
    )
    result = RiskService.analyze(temp)

    return jsonify({
        'has_danger':  result['score'] >= 40,
        'keywords':    result['found_keywords'],
        'risk_score':  result['score'],
        'risk_level':  result['level'],
        'vital_flag':  result['vital_flag'],
        'rules':       result['rules'][:5],  # 상위 5개만
    })
