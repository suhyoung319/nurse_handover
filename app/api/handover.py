"""
api/handover.py — REST API Blueprint (v1)

## 설계 원칙

1. URL 구조: /api/v1/handovers
   - 버전(v1)을 URL에 포함 → 나중에 하위 호환성 유지하며 v2 추가 가능

2. 응답 형식 통일
   - 성공: {"data": {...}, "message": "..."}
   - 실패: {"error": "ERROR_CODE", "message": "설명"}
   - 목록: {"data": [...], "total": N, "page": P, "per_page": PP}

3. HTTP 상태코드 엄수
   - 200: 조회 성공
   - 201: 생성 성공
   - 400: 잘못된 요청 (클라이언트 오류)
   - 401: 미인증
   - 403: 권한 없음
   - 404: 리소스 없음
   - 500: 서버 오류

4. 인수인계 API는 웹뷰의 HandoverService를 그대로 재사용
   → Service Layer 패턴의 핵심 이점
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Handover, Patient
from app.services.audit_service import AuditService
from app.services.risk_service import RiskService
from app.middleware.rbac import require_permission

api_handover_bp = Blueprint('api_handover', __name__, url_prefix='/api/v1/handovers')


def success_response(data, message='OK', status=200):
    """표준 성공 응답"""
    return jsonify({'data': data, 'message': message}), status


def error_response(error_code, message, status=400):
    """표준 에러 응답"""
    return jsonify({'error': error_code, 'message': message}), status


# ── GET /api/v1/handovers ─────────────────────────────────────

@api_handover_bp.route('/', methods=['GET'])
@login_required
def list_handovers():
    """
    인수인계 목록 조회
    
    Query params:
        page: 페이지 번호 (기본: 1)
        per_page: 페이지 크기 (기본: 20, 최대: 100)
        shift: 교대 필터 (주간/야간/심야)
        danger_only: true이면 위험 인수인계만
        patient_id: 특정 환자 필터
    
    Response:
        {
            "data": [...],
            "total": 100,
            "page": 1,
            "per_page": 20,
            "pages": 5
        }
    """
    page      = request.args.get('page', 1, type=int)
    per_page  = min(request.args.get('per_page', 20, type=int), 100)
    shift     = request.args.get('shift')
    danger_only = request.args.get('danger_only', 'false').lower() == 'true'
    patient_id = request.args.get('patient_id', type=int)

    q = Handover.query

    if shift:
        q = q.filter_by(shift=shift)
    if danger_only:
        q = q.filter_by(has_danger=True)
    if patient_id:
        q = q.filter_by(patient_id=patient_id)

    # 병동 필터 (admin이 아니면 자기 병동만)
    if current_user.role not in ('admin', 'charge_nurse') and current_user.ward:
        q = (q.join(Patient)
               .filter(Patient.ward == current_user.ward))

    paginated = q.order_by(Handover.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'data':     [h.to_dict() for h in paginated.items],
        'total':    paginated.total,
        'page':     page,
        'per_page': per_page,
        'pages':    paginated.pages,
    }), 200


# ── GET /api/v1/handovers/<id> ────────────────────────────────

@api_handover_bp.route('/<int:id>', methods=['GET'])
@login_required
def get_handover(id):
    """
    인수인계 상세 조회.
    민감 정보이므로 조회 시 Audit Log 기록.
    """
    handover = Handover.query.get_or_404(id)

    # 감사 로그: 상세 조회
    AuditService.log_view(
        resource='handover',
        resource_id=id,
        description=f'인수인계 상세 조회 (환자: {handover.patient.name})'
    )

    data = handover.to_dict()
    # 위험도 분석 결과도 포함
    if handover.risk_assessment:
        data['risk'] = {
            'score':          handover.risk_assessment.risk_score,
            'level':          handover.risk_assessment.risk_level,
            'triggered_rules': handover.risk_assessment.get_triggered_rules(),
            'vital_flag':     handover.risk_assessment.vital_flag,
            'keyword_flag':   handover.risk_assessment.keyword_flag,
        }

    return success_response(data)


# ── POST /api/v1/handovers ────────────────────────────────────

@api_handover_bp.route('/', methods=['POST'])
@login_required
@require_permission('handover', 'write')
def create_handover():
    """
    인수인계 생성.
    
    Request body (JSON):
        {
            "patient_id": 1,
            "to_user_id": 2,
            "shift": "주간",
            "content": "...",
            "vital_signs": "BP: 120/80  HR: 72",
            "medications": "...",
            "procedures": "..."
        }
    """
    data = request.get_json()
    if not data:
        return error_response('INVALID_JSON', 'JSON 형식이 올바르지 않습니다.')

    # 필수 필드 검증
    required = ['patient_id', 'content']
    missing  = [f for f in required if not data.get(f)]
    if missing:
        return error_response('MISSING_FIELDS',
                              f'필수 항목 누락: {", ".join(missing)}')

    patient = Patient.query.get(data['patient_id'])
    if not patient:
        return error_response('PATIENT_NOT_FOUND', '존재하지 않는 환자입니다.', 404)

    handover = Handover(
        patient_id   = data['patient_id'],
        from_user_id = current_user.id,
        to_user_id   = data.get('to_user_id'),
        shift        = data.get('shift', '주간'),
        content      = data['content'],
        vital_signs  = data.get('vital_signs', ''),
        medications  = data.get('medications', ''),
        procedures   = data.get('procedures', ''),
    )
    db.session.add(handover)
    db.session.flush()  # ID 생성을 위해 flush (commit 전)

    # 위험도 분석 자동 실행
    RiskService.analyze_and_save(handover)

    # 감사 로그
    AuditService.log_create(
        resource='handover',
        resource_id=handover.id,
        new_value=handover.to_dict(),
        description=f'인수인계 작성 (환자: {patient.name})'
    )

    db.session.commit()
    return success_response(handover.to_dict(),
                            message='인수인계가 저장되었습니다.', status=201)


# ── PUT /api/v1/handovers/<id> ────────────────────────────────

@api_handover_bp.route('/<int:id>', methods=['PUT'])
@login_required
@require_permission('handover', 'write')
def update_handover(id):
    """인수인계 수정. 작성자 본인 또는 관리자만 가능."""
    handover = Handover.query.get_or_404(id)

    # 작성자 본인 또는 admin만 수정 가능
    if (handover.from_user_id != current_user.id and
            current_user.role not in ('admin', 'charge_nurse')):
        AuditService.log_access_denied('handover', id)
        return error_response('PERMISSION_DENIED', '본인이 작성한 인수인계만 수정 가능합니다.', 403)

    data = request.get_json()
    if not data:
        return error_response('INVALID_JSON', 'JSON 형식이 올바르지 않습니다.')

    # 변경 전 값 저장 (감사 로그용)
    old_value = handover.to_dict()

    # 업데이트 가능한 필드만 처리
    updatable = ['content', 'vital_signs', 'medications', 'procedures',
                 'shift', 'to_user_id']
    for field in updatable:
        if field in data:
            setattr(handover, field, data[field])

    # 위험도 재분석
    RiskService.analyze_and_save(handover)

    # 감사 로그
    AuditService.log_update(
        resource='handover',
        resource_id=id,
        old_value=old_value,
        new_value=handover.to_dict(),
        description='인수인계 수정'
    )

    db.session.commit()
    return success_response(handover.to_dict(), message='수정되었습니다.')


# ── DELETE /api/v1/handovers/<id> ────────────────────────────

@api_handover_bp.route('/<int:id>', methods=['DELETE'])
@login_required
@require_permission('handover', 'delete')
def delete_handover(id):
    """인수인계 삭제. 삭제 전 내용을 감사 로그에 기록."""
    handover = Handover.query.get_or_404(id)

    if (handover.from_user_id != current_user.id and
            current_user.role != 'admin'):
        return error_response('PERMISSION_DENIED', '권한이 없습니다.', 403)

    # 삭제 전 내용 보존 (감사 로그)
    AuditService.log_delete(
        resource='handover',
        resource_id=id,
        old_value=handover.to_dict(),
        description=f'인수인계 삭제 (환자: {handover.patient.name})'
    )

    db.session.delete(handover)
    db.session.commit()
    return success_response(None, message='삭제되었습니다.')


# ── POST /api/v1/handovers/<id>/acknowledge ──────────────────

@api_handover_bp.route('/<int:id>/acknowledge', methods=['POST'])
@login_required
def acknowledge_handover(id):
    """
    인수인계 확인(읽음) 처리.
    인계 받은 사람이 "확인했음"을 누르는 기능.
    """
    from app.models import HandoverAck
    handover = Handover.query.get_or_404(id)

    # 이미 확인했는지 체크
    existing = HandoverAck.query.filter_by(
        handover_id=id, user_id=current_user.id
    ).first()

    if existing:
        return error_response('ALREADY_ACKNOWLEDGED',
                              '이미 확인한 인수인계입니다.')

    note = request.get_json(silent=True) or {}

    ack = HandoverAck(
        handover_id=id,
        user_id=current_user.id,
        note=note.get('note', ''),
    )
    db.session.add(ack)

    # to_user가 확인한 경우 confirmed 처리
    if handover.to_user_id == current_user.id:
        from datetime import datetime
        handover.is_confirmed = True
        handover.confirmed_at = datetime.utcnow()
        handover.confirmed_by = current_user.id

    AuditService.log(
        action='ACKNOWLEDGE',
        resource='handover',
        resource_id=id,
        description=f'인수인계 확인 처리'
    )

    db.session.commit()
    return success_response({'acknowledged': True}, message='인수인계를 확인했습니다.', status=201)


# ── GET /api/v1/handovers/<id>/risk ──────────────────────────

@api_handover_bp.route('/<int:id>/risk', methods=['GET'])
@login_required
def get_risk_detail(id):
    """
    인수인계 위험도 상세 분석 결과 조회.
    "왜 위험으로 판단됐는가" 를 확인할 수 있음.
    """
    handover = Handover.query.get_or_404(id)

    # 분석 결과 없으면 실시간 분석
    if not handover.risk_assessment:
        assessment = RiskService.analyze_and_save(handover)
    else:
        assessment = handover.risk_assessment

    return success_response({
        'handover_id':    id,
        'risk_score':     assessment.risk_score,
        'risk_level':     assessment.risk_level,
        'triggered_rules': assessment.get_triggered_rules(),
        'vital_flag':     assessment.vital_flag,
        'keyword_flag':   assessment.keyword_flag,
        'frequency_flag': assessment.frequency_flag,
    })
