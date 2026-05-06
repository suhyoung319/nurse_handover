from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from app import db
from app.models import Patient

patients_bp = Blueprint('patients', __name__, url_prefix='/patients')


@patients_bp.route('/')
@login_required
def index():
    search = request.args.get('search', '').strip()
    status = request.args.get('status', '')
    ward   = request.args.get('ward',   '')
    page   = request.args.get('page', 1, type=int)

    q = Patient.query
    if search:
        q = q.filter(
            Patient.name.contains(search) |
            Patient.patient_number.contains(search) |
            Patient.diagnosis.contains(search)
        )
    if status:
        q = q.filter_by(status=status)
    if ward:
        q = q.filter_by(ward=ward)

    patients = q.order_by(Patient.created_at.desc()).paginate(page=page, per_page=15)
    wards    = [r[0] for r in db.session.query(Patient.ward).distinct().all()]

    return render_template('patients/index.html',
        patients=patients, search=search,
        status=status, ward=ward, wards=wards)


@patients_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    if request.method == 'POST':
        patient_number = request.form.get('patient_number', '').strip()
        name           = request.form.get('name', '').strip()

        if not patient_number or not name:
            flash('환자번호와 이름은 필수입니다.', 'danger')
            return render_template('patients/form.html', patient=None)

        if Patient.query.filter_by(patient_number=patient_number).first():
            flash('이미 존재하는 환자번호입니다.', 'danger')
            return render_template('patients/form.html', patient=None)

        adm = request.form.get('admission_date')
        dis = request.form.get('discharge_date')

        patient = Patient(
            patient_number = patient_number,
            name           = name,
            age            = request.form.get('age', type=int),
            gender         = request.form.get('gender', ''),
            ward           = request.form.get('ward', '').strip(),
            room           = request.form.get('room', '').strip(),
            bed            = request.form.get('bed',  '').strip(),
            diagnosis      = request.form.get('diagnosis',    '').strip(),
            status         = request.form.get('status', '입원중'),
            allergies      = request.form.get('allergies',    '').strip(),
            special_notes  = request.form.get('special_notes','').strip(),
            admission_date = datetime.strptime(adm, '%Y-%m-%d').date() if adm else None,
            discharge_date = datetime.strptime(dis, '%Y-%m-%d').date() if dis else None,
        )
        db.session.add(patient)
        db.session.commit()
        flash(f'환자 {name}이(가) 등록되었습니다.', 'success')
        return redirect(url_for('patients.detail', id=patient.id))

    return render_template('patients/form.html', patient=None)


@patients_bp.route('/<int:id>')
@login_required
def detail(id):
    patient   = Patient.query.get_or_404(id)
    handovers = sorted(patient.handovers, key=lambda h: h.created_at, reverse=True)
    return render_template('patients/detail.html', patient=patient, handovers=handovers)


@patients_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    patient = Patient.query.get_or_404(id)

    if request.method == 'POST':
        patient.name          = request.form.get('name', patient.name).strip()
        patient.age           = request.form.get('age', type=int)
        patient.gender        = request.form.get('gender', patient.gender)
        patient.ward          = request.form.get('ward',  patient.ward).strip()
        patient.room          = request.form.get('room',  patient.room or '').strip()
        patient.bed           = request.form.get('bed',   patient.bed  or '').strip()
        patient.diagnosis     = request.form.get('diagnosis',    '').strip()
        patient.status        = request.form.get('status', patient.status)
        patient.allergies     = request.form.get('allergies',    '').strip()
        patient.special_notes = request.form.get('special_notes','').strip()
        patient.updated_at    = datetime.utcnow()

        adm = request.form.get('admission_date')
        dis = request.form.get('discharge_date')
        if adm:
            patient.admission_date = datetime.strptime(adm, '%Y-%m-%d').date()
        if dis:
            patient.discharge_date = datetime.strptime(dis, '%Y-%m-%d').date()

        db.session.commit()
        flash('환자 정보가 수정되었습니다.', 'success')
        return redirect(url_for('patients.detail', id=patient.id))

    return render_template('patients/form.html', patient=patient)


@patients_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    patient = Patient.query.get_or_404(id)
    name    = patient.name
    db.session.delete(patient)
    db.session.commit()
    flash(f'환자 {name}이(가) 삭제되었습니다.', 'warning')
    return redirect(url_for('patients.index'))
