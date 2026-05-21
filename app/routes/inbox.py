"""
routes/inbox.py — 받은 인수인계함 + 보낸 인수인계함

URL:
  GET  /inbox/              → 받은 인수인계함 (미확인 우선)
  GET  /inbox/sent          → 보낸 인수인계함
  GET  /inbox/danger        → 위험 인수인계 (CRITICAL/HIGH)
  POST /inbox/<id>/acknowledge   → 확인 처리
  POST /inbox/<id>/cancel        → 취소
  GET  /inbox/<id>/transfer      → 대상 변경 폼
  POST /inbox/<id>/transfer      → 대상 변경 처리
"""

from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models import Handover, User, HandoverAck, RiskAssessment
from app.services.audit_service import AuditService
from app.utils import apply_handover_patient_scope, can_access_patient

inbox_bp = Blueprint('inbox', __name__, url_prefix='/inbox')

# 위험도 색상 맵 (템플릿에서 사용)
RISK_COLOR = {
    'CRITICAL': 'danger',
    'HIGH':     'warning',
    'MEDIUM':   'info',
    'LOW':      'success',
}


# ── 1. 받은 인수인계함 ─────────────────────────────────────────

@inbox_bp.route('/')
@login_required
def index():
    """
    받은 인수인계함.
    우선순위: ① 미확인 CRITICAL/HIGH → ② 미확인 일반 → ③ 확인 완료
    """
    tab = request.args.get('tab', 'pending')  # pending / acked

    # 미확인 목록 (CRITICAL/HIGH 먼저, 그 다음 최신순)
    pending_q = Handover.query.filter_by(to_user_id=current_user.id, is_confirmed=False)
    pending_q = (apply_handover_patient_scope(pending_q, current_user)
                 .outerjoin(RiskAssessment)
                 .order_by(
                     # CRITICAL=0, HIGH=1, MEDIUM=2, LOW=3 순서로 정렬
                     db.case(
                         (RiskAssessment.risk_level == 'CRITICAL', 0),
                         (RiskAssessment.risk_level == 'HIGH',     1),
                         (RiskAssessment.risk_level == 'MEDIUM',   2),
                         else_=3
                     ),
                     Handover.created_at.desc()
                 ))

    pending_list = pending_q.all()

    # 확인 완료 목록 (최신 30건)
    acked_q = Handover.query.filter_by(to_user_id=current_user.id, is_confirmed=True)
    acked_list = (apply_handover_patient_scope(acked_q, current_user)
                  .order_by(Handover.confirmed_at.desc())
                  .limit(30).all())

    # 통계
    unread_count   = len(pending_list)
    critical_count = sum(1 for h in pending_list
                         if h.risk_assessment and h.risk_assessment.risk_level == 'CRITICAL')
    high_count     = sum(1 for h in pending_list
                         if h.risk_assessment and h.risk_assessment.risk_level == 'HIGH')

    return render_template('inbox/index.html',
        tab=tab,
        pending_list=pending_list,
        acked_list=acked_list,
        unread_count=unread_count,
        critical_count=critical_count,
        high_count=high_count,
        RISK_COLOR=RISK_COLOR,
    )


# ── 2. 보낸 인수인계함 ─────────────────────────────────────────

@inbox_bp.route('/sent')
@login_required
def sent():
    """
    내가 작성한 인수인계 목록.
    - 상대방 확인 여부 표시
    - 미확인 건 강조
    - 수정/취소/대상변경 버튼
    """
    page   = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')  # confirmed / pending

    q = apply_handover_patient_scope(
        Handover.query.filter_by(from_user_id=current_user.id),
        current_user
    )

    if status == 'pending':
        q = q.filter_by(is_confirmed=False)
    elif status == 'confirmed':
        q = q.filter_by(is_confirmed=True)

    handovers = q.order_by(Handover.created_at.desc()).paginate(page=page, per_page=20)

    # 미확인 건수
    pending_count = apply_handover_patient_scope(
        Handover.query.filter_by(from_user_id=current_user.id, is_confirmed=False),
        current_user
    ).count()

    return render_template('inbox/sent.html',
        handovers=handovers,
        status=status,
        pending_count=pending_count,
        RISK_COLOR=RISK_COLOR,
    )


# ── 3. 위험 인수인계 모아보기 ─────────────────────────────────

@inbox_bp.route('/danger')
@login_required
def danger():
    """
    CRITICAL / HIGH 위험도 인수인계 전체.
    nurse는 같은 상위 진료과 기준으로 필터.
    """
    level  = request.args.get('level', '')   # CRITICAL / HIGH / MEDIUM
    page   = request.args.get('page', 1, type=int)

    q = (Handover.query
         .join(RiskAssessment)
         .filter(RiskAssessment.risk_level.in_(['CRITICAL', 'HIGH', 'MEDIUM']))
         .order_by(
             db.case(
                 (RiskAssessment.risk_level == 'CRITICAL', 0),
                 (RiskAssessment.risk_level == 'HIGH',     1),
                 else_=2
             ),
             Handover.created_at.desc()
         ))

    if level:
        q = q.filter(RiskAssessment.risk_level == level)

    # 일반 nurse는 같은 상위 진료과 환자 관련만
    q = apply_handover_patient_scope(q, current_user)

    handovers = q.paginate(page=page, per_page=20)

    return render_template('inbox/danger.html',
        handovers=handovers,
        level=level,
        RISK_COLOR=RISK_COLOR,
    )


# ── 4. 확인 처리 ──────────────────────────────────────────────

@inbox_bp.route('/<int:id>/acknowledge', methods=['POST'])
@login_required
def acknowledge(id):
    """인수인계 확인 (PENDING → 확인 완료) + 메모 저장"""
    handover = Handover.query.get_or_404(id)
    if not can_access_patient(current_user, handover.patient):
        flash('다른 진료과 환자의 인수인계에 접근할 수 없습니다.', 'warning')
        return redirect(url_for('inbox.index'))

    if handover.to_user_id != current_user.id and current_user.role not in ('admin', 'charge_nurse'):
        flash('본인에게 온 인수인계만 확인할 수 있습니다.', 'danger')
        return redirect(url_for('inbox.index'))

    existing = HandoverAck.query.filter_by(
        handover_id=id, user_id=current_user.id
    ).first()

    if existing:
        flash('이미 확인한 인수인계입니다.', 'info')
        return redirect(url_for('inbox.index'))

    note = request.form.get('note', '').strip()

    ack = HandoverAck(
        handover_id=id,
        user_id=current_user.id,
        note=note,
        ack_at=datetime.utcnow(),
    )
    db.session.add(ack)
    
    handover.is_confirmed = True
    handover.confirmed_at = datetime.utcnow()
    handover.confirmed_by = current_user.id
    handover.status       = 'ACKNOWLEDGED'  # 알림 배지 카운트 동기화

    AuditService.log(
        action='ACKNOWLEDGE',
        resource='handover',
        resource_id=id,
        description=f'{current_user.name}이(가) 인수인계 확인. 메모: {note or "없음"} (환자: {handover.patient.name})'
    )

    db.session.commit()

    msg = '✅ 인수인계를 확인했습니다.'
    if note:
        msg += f' 메모: "{note}"'
    flash(msg, 'success')
    return redirect(request.referrer or url_for('inbox.index'))


# ── 5. 취소 처리 ──────────────────────────────────────────────

@inbox_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
def cancel(id):
    """인수인계 취소 (작성자 or admin/charge_nurse)"""
    handover = Handover.query.get_or_404(id)
    if not can_access_patient(current_user, handover.patient):
        flash('다른 진료과 환자의 인수인계에 접근할 수 없습니다.', 'warning')
        return redirect(url_for('inbox.sent'))

    if (handover.from_user_id != current_user.id and
            current_user.role not in ('admin', 'charge_nurse')):
        flash('취소 권한이 없습니다.', 'danger')
        return redirect(url_for('inbox.sent'))

    if handover.is_confirmed:
        flash('이미 확인된 인수인계는 취소할 수 없습니다.', 'warning')
        return redirect(url_for('inbox.sent'))

    reason = request.form.get('reason', '').strip()

    AuditService.log_update(
        resource='handover',
        resource_id=id,
        old_value={'is_confirmed': False},
        new_value={'status': 'CANCELLED', 'reason': reason},
        description=f'인수인계 취소 (환자: {handover.patient.name}) 사유: {reason or "없음"}'
    )

    # 소프트 삭제 대신 to_user 제거 (인계 대상 없앰)
    handover.to_user_id = None
    db.session.commit()

    flash('인수인계가 취소되었습니다.', 'warning')
    return redirect(url_for('inbox.sent'))


# ── 6. 대상 변경 ──────────────────────────────────────────────

@inbox_bp.route('/<int:id>/transfer', methods=['GET', 'POST'])
@login_required
def transfer(id):
    """인수인계 대상 변경"""
    handover = Handover.query.get_or_404(id)
    if not can_access_patient(current_user, handover.patient):
        flash('다른 진료과 환자의 인수인계에 접근할 수 없습니다.', 'warning')
        return redirect(url_for('inbox.sent'))

    if (handover.from_user_id != current_user.id and
            current_user.role not in ('admin', 'charge_nurse')):
        flash('대상 변경 권한이 없습니다.', 'danger')
        return redirect(url_for('inbox.sent'))

    if handover.is_confirmed:
        flash('이미 확인된 인수인계는 대상을 변경할 수 없습니다.', 'warning')
        return redirect(url_for('inbox.sent'))

    if request.method == 'POST':
        new_user_id = request.form.get('new_to_user_id', type=int)
        note        = request.form.get('note', '').strip()

        if not new_user_id:
            flash('변경할 대상을 선택해주세요.', 'danger')
        else:
            old_name = handover.to_user.name if handover.to_user else '미지정'
            new_user = User.query.get(new_user_id)

            AuditService.log(
                action='TRANSFER',
                resource='handover',
                resource_id=id,
                new_value={'from': old_name, 'to': new_user.name if new_user else '?'},
                description=f'인수인계 대상 변경: {old_name} → {new_user.name if new_user else "?"} (환자: {handover.patient.name})'
            )

            handover.to_user_id = new_user_id
            handover.is_confirmed = False
            handover.confirmed_at = None
            handover.confirmed_by = None
            db.session.commit()

            flash(f'인수인계 대상이 {new_user.name}으로 변경되었습니다.', 'success')
            return redirect(url_for('inbox.sent'))

    users = User.query.filter(
        User.id != current_user.id,
        User.is_active == True,
    ).order_by(User.name).all()

    return render_template('inbox/transfer.html',
        handover=handover, users=users)
