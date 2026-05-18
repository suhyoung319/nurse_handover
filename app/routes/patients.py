"""
routes/patients.py — 병동 UX 고도화 버전

핵심 변경:
1. 환자 목록에 위험도 우선순위 정렬 주입
   → 고위험+미확인 → 고위험 → 미확인 → 일반
2. 긴급 영역 카운트 (CRITICAL/HIGH + 미확인)
3. 환자별 최신 인수인계 + 위험 요약 데이터 주입
   → 목록에서 상세 진입 없이 핵심 정보 즉시 표시
"""

from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import desc
from app import db
from app.models import Patient, Handover, RiskAssessment
from app.services.audit_service import AuditService
from app.middleware.rbac import require_permission

patients_bp = Blueprint('patients', __name__, url_prefix='/patients')


# ── 위험도 레벨 정렬 가중치 ─────────────────────────────────────
RISK_ORDER = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3, None: 4}

RISK_CONFIG = {
    'CRITICAL': {
        'color':    'danger',
        'bg':       '#fff5f5',
        'border':   '#ef4444',
        'icon':     '🔴',
        'label':    '고위험',
        'badge_bg': 'bg-danger',
    },
    'HIGH': {
        'color':    'warning',
        'bg':       '#fffbeb',
        'border':   '#f59e0b',
        'icon':     '🟡',
        'label':    '주의',
        'badge_bg': 'bg-warning',
    },
    'MEDIUM': {
        'color':    'info',
        'bg':       '#f0f9ff',
        'border':   '#38bdf8',
        'icon':     '🔵',
        'label':    '관찰',
        'badge_bg': 'bg-info',
    },
    'LOW': {
        'color':    'secondary',
        'bg':       '#f8fafc',
        'border':   '#e2e8f0',
        'icon':     '⚪',
        'label':    '일반',
        'badge_bg': 'bg-secondary',
    },
}


def _get_patient_risk_summary(patient: Patient) -> dict:
    """
    환자의 최신 인수인계에서 핵심 정보 추출.
    목록 화면에서 상세 진입 없이 표시하기 위한 데이터.
    """
    # 최신 인수인계 (미확인 우선)
    latest_unconfirmed = None
    latest_any = None

    handovers = sorted(patient.handovers, key=lambda h: h.created_at, reverse=True)

    for h in handovers:
        if not h.is_confirmed and latest_unconfirmed is None:
            latest_unconfirmed = h
        if latest_any is None:
            latest_any = h

    latest = latest_unconfirmed or latest_any

    if not latest:
        return {
            'risk_level':    None,
            'risk_score':    0,
            'risk_config':   RISK_CONFIG['LOW'],
            'has_unconfirmed': False,
            'unconfirmed_count': 0,
            'danger_keywords': [],
            'latest_time':   None,
            'latest_shift':  None,
            'vital_flag':    False,
            'keyword_flag':  False,
            'sort_weight':   99,
        }

    ra = latest.risk_assessment
    risk_level  = ra.risk_level  if ra else 'LOW'
    risk_score  = ra.risk_score  if ra else 0
    vital_flag  = ra.vital_flag  if ra else False
    keyword_flag = ra.keyword_flag if ra else False

    unconfirmed_list = [h for h in handovers if not h.is_confirmed]
    unconfirmed_count = len(unconfirmed_list)
    has_unconfirmed = unconfirmed_count > 0

    # 위험 키워드 (최대 3개)
    danger_keywords = []
    if latest.danger_keywords:
        danger_keywords = [k.strip() for k in latest.danger_keywords.split(',')][:3]

    # 정렬 가중치: 고위험+미확인=0, 고위험=1, 미확인=2, 일반=3
    base_weight = RISK_ORDER.get(risk_level, 4)
    if has_unconfirmed and risk_level in ('CRITICAL', 'HIGH'):
        sort_weight = 0
    elif risk_level in ('CRITICAL', 'HIGH'):
        sort_weight = 1
    elif has_unconfirmed:
        sort_weight = 2
    else:
        sort_weight = base_weight + 3

    return {
        'risk_level':       risk_level,
        'risk_score':       risk_score,
        'risk_config':      RISK_CONFIG.get(risk_level, RISK_CONFIG['LOW']),
        'has_unconfirmed':  has_unconfirmed,
        'unconfirmed_count': unconfirmed_count,
        'danger_keywords':  danger_keywords,
        'latest_time':      latest.created_at,
        'latest_shift':     latest.shift,
        'vital_flag':       vital_flag,
        'keyword_flag':     keyword_flag,
        'sort_weight':      sort_weight,
    }


@patients_bp.route('/')
@login_required
def index():
    search = request.args.get('search', '').strip()
    status = request.args.get('status', '입원중')  # 기본값: 입원중
    ward   = request.args.get('ward',   '')
    page   = request.args.get('page', 1, type=int)

    q = Patient.query

    # nurse: 자기 병동만
    if current_user.role == 'nurse' and current_user.ward:
        q = q.filter_by(ward=current_user.ward)

    if search:
        q = q.filter(
            Patient.name.contains(search) |
            Patient.patient_number.contains(search) |
            Patient.diagnosis.contains(search)
        )
    if status:
        q = q.filter_by(status=status)
    if ward and current_user.role != 'nurse':
        q = q.filter_by(ward=ward)

    # 전체 조회 후 Python에서 위험도 정렬
    # (DB 조인 복잡도 vs 정렬 정확성 트레이드오프 → 페이지당 15건이므로 Python 정렬 선택)
    all_patients = q.all()

    # 환자별 위험 요약 계산
    patient_summaries = {}
    for p in all_patients:
        patient_summaries[p.id] = _get_patient_risk_summary(p)

    # 우선순위 정렬
    # 1) 고위험+미확인 → 2) 고위험 → 3) 미확인 → 4) 일반
    sorted_patients = sorted(
        all_patients,
        key=lambda p: (
            patient_summaries[p.id]['sort_weight'],
            # 같은 레벨이면 최신 인수인계 시간 우선
            -(patient_summaries[p.id]['latest_time'].timestamp()
              if patient_summaries[p.id]['latest_time'] else 0)
        )
    )

    # 수동 페이지네이션
    per_page = 15
    total    = len(sorted_patients)
    start    = (page - 1) * per_page
    end      = start + per_page
    page_items = sorted_patients[start:end]
    total_pages = (total + per_page - 1) // per_page

    # 긴급 영역 카운트 (즉시 확인 필요)
    urgent_count = sum(
        1 for p in all_patients
        if patient_summaries[p.id]['sort_weight'] == 0
    )

    wards = [r[0] for r in db.session.query(Patient.ward).distinct().all()]

    return render_template('patients/index.html',
        page_items=page_items,
        patient_summaries=patient_summaries,
        total=total,
        page=page,
        total_pages=total_pages,
        per_page=per_page,
        search=search,
        status=status,
        ward=ward,
        wards=wards,
        urgent_count=urgent_count,
        can_delete=(current_user.role in ('admin', 'charge_nurse')),
        RISK_CONFIG=RISK_CONFIG,
    )


@patients_bp.route('/create', methods=['GET', 'POST'])
@login_required
@require_permission('patient', 'write')
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
        db.session.flush()

        AuditService.log_create('patient', patient.id,
            new_value={'name': name, 'ward': patient.ward},
            description=f'환자 등록: {name}')

        db.session.commit()
        flash(f'환자 {name}이(가) 등록되었습니다.', 'success')
        return redirect(url_for('patients.detail', id=patient.id))

    return render_template('patients/form.html', patient=None)


@patients_bp.route('/<int:id>')
@login_required
def detail(id):
    patient = Patient.query.get_or_404(id)

    AuditService.log_view('patient', id,
        description=f'환자 상세 조회: {patient.name}')

    all_handovers = sorted(patient.handovers,
                           key=lambda h: h.created_at, reverse=True)
    now = datetime.utcnow()

    active_handovers = [h for h in all_handovers if not h.is_confirmed]
    cutoff_24h       = now - timedelta(hours=24)
    recent_24h       = [h for h in all_handovers
                        if h.created_at >= cutoff_24h and h.is_confirmed]
    history          = [h for h in all_handovers
                        if h.created_at < cutoff_24h or h.is_confirmed]

    summary = _get_patient_risk_summary(patient)

    return render_template('patients/detail.html',
        patient=patient,
        active_handovers=active_handovers,
        recent_24h=recent_24h,
        history=history,
        summary=summary,
        RISK_CONFIG=RISK_CONFIG,
        can_delete=(current_user.role in ('admin', 'charge_nurse')))


@patients_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@require_permission('patient', 'write')
def edit(id):
    patient = Patient.query.get_or_404(id)

    if request.method == 'POST':
        old_value = patient.to_dict()

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

        AuditService.log_update('patient', id,
            old_value=old_value,
            new_value=patient.to_dict(),
            description=f'환자 정보 수정: {patient.name}')

        db.session.commit()
        flash('환자 정보가 수정되었습니다.', 'success')
        return redirect(url_for('patients.detail', id=patient.id))

    return render_template('patients/form.html', patient=patient)


@patients_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    if current_user.role not in ('admin', 'charge_nurse'):
        flash('환자 삭제 권한이 없습니다. 수간호사 또는 관리자에게 문의하세요.', 'danger')
        return redirect(url_for('patients.detail', id=id))

    patient = Patient.query.get_or_404(id)
    name    = patient.name

    AuditService.log_delete('patient', id,
        old_value=patient.to_dict(),
        description=f'환자 삭제: {name}')

    db.session.delete(patient)
    db.session.commit()
    flash(f'환자 {name}이(가) 삭제되었습니다.', 'warning')
    return redirect(url_for('patients.index'))
