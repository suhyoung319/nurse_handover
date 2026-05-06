from datetime import datetime
from flask import (Blueprint, render_template, redirect,
                   url_for, flash, request, jsonify)
from flask_login import login_required, current_user
from app import db
from app.models import Handover, Patient, User
from app.utils import detect_danger_keywords

handover_bp = Blueprint('handover', __name__, url_prefix='/handovers')


@handover_bp.route('/')
@login_required
def index():
    page       = request.args.get('page', 1, type=int)
    shift      = request.args.get('shift', '')
    danger_only = request.args.get('danger_only', '')

    q = Handover.query
    if shift:
        q = q.filter_by(shift=shift)
    if danger_only:
        q = q.filter_by(has_danger=True)

    handovers = q.order_by(Handover.created_at.desc()).paginate(page=page, per_page=15)
    return render_template('handover/index.html',
                           handovers=handovers, shift=shift, danger_only=danger_only)


@handover_bp.route('/create', methods=['GET', 'POST'])
@handover_bp.route('/create/<int:patient_id>', methods=['GET', 'POST'])
@login_required
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

        full_text = ' '.join([
            content,
            request.form.get('vital_signs', ''),
            request.form.get('medications', ''),
            request.form.get('procedures',  ''),
        ])
        found, has_danger = detect_danger_keywords(full_text)

        h = Handover(
            patient_id      = pid,
            from_user_id    = current_user.id,
            to_user_id      = request.form.get('to_user_id', type=int),
            shift           = request.form.get('shift', '주간'),
            content         = content,
            vital_signs     = request.form.get('vital_signs', '').strip(),
            medications     = request.form.get('medications', '').strip(),
            procedures      = request.form.get('procedures',  '').strip(),
            has_danger      = has_danger,
            danger_keywords = ', '.join(found) if found else None,
        )
        db.session.add(h)
        db.session.commit()

        if has_danger:
            flash(f'⚠️ 위험 키워드 감지: {", ".join(found)} — 인수인계가 저장되었습니다.', 'warning')
        else:
            flash('인수인계가 저장되었습니다.', 'success')
        return redirect(url_for('handover.detail', id=h.id))

    return render_template('handover/form.html',
                           handover=None, patients=patients,
                           users=users, selected_patient_id=patient_id)


@handover_bp.route('/<int:id>')
@login_required
def detail(id):
    handover = Handover.query.get_or_404(id)
    return render_template('handover/detail.html', handover=handover)


@handover_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    handover = Handover.query.get_or_404(id)
    patients = Patient.query.filter_by(status='입원중').all()
    users    = User.query.filter(User.id != current_user.id).all()

    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        handover.patient_id  = request.form.get('patient_id', type=int)
        handover.to_user_id  = request.form.get('to_user_id', type=int)
        handover.shift       = request.form.get('shift', '주간')
        handover.content     = content
        handover.vital_signs = request.form.get('vital_signs', '').strip()
        handover.medications = request.form.get('medications', '').strip()
        handover.procedures  = request.form.get('procedures',  '').strip()
        handover.updated_at  = datetime.utcnow()

        full_text = ' '.join([handover.content, handover.vital_signs,
                               handover.medications, handover.procedures])
        found, has_danger = detect_danger_keywords(full_text)
        handover.has_danger      = has_danger
        handover.danger_keywords = ', '.join(found) if found else None

        db.session.commit()
        flash('인수인계가 수정되었습니다.', 'success')
        return redirect(url_for('handover.detail', id=handover.id))

    return render_template('handover/form.html',
                           handover=handover, patients=patients,
                           users=users, selected_patient_id=None)


@handover_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    handover = Handover.query.get_or_404(id)
    db.session.delete(handover)
    db.session.commit()
    flash('인수인계가 삭제되었습니다.', 'warning')
    return redirect(url_for('handover.index'))


@handover_bp.route('/check-keywords', methods=['POST'])
@login_required
def check_keywords():
    """AJAX — 입력 중 실시간 위험 키워드 감지"""
    text  = request.json.get('text', '')
    found, has_danger = detect_danger_keywords(text)
    return jsonify({'has_danger': has_danger, 'keywords': found})
