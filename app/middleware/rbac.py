"""
middleware/rbac.py — Role-Based Access Control (RBAC)

## 설계 철학

Flask에서 RBAC를 구현하는 3가지 방법:

1. 라우트 안에서 직접 확인 (나쁜 방법)
   def delete_patient(id):
       if current_user.role != 'admin':
           abort(403)  # 중복 코드, 실수 위험

2. 데코레이터 방식 (우리가 선택)
   @require_role('admin')
   @require_permission('patient', 'delete')
   def delete_patient(id): ...
   → 선언적, 재사용 가능, 테스트 쉬움

3. Policy 객체 방식 (대규모 시스템용)
   → Casbin 같은 라이브러리 사용
   → 현재 프로젝트 규모에는 과함

## 역할 계층 (상위가 하위 권한 포함)
admin > charge_nurse > doctor = nurse
"""

from functools import wraps
from flask import abort, flash, redirect, url_for, request, jsonify
from flask_login import current_user
from app.services.audit_service import AuditService


def require_role(*roles):
    """
    특정 역할만 접근 허용하는 데코레이터.
    
    사용 예시:
        @require_role('admin', 'charge_nurse')
        def manage_users(): ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))

            if current_user.role not in roles:
                # 감사 로그에 ACCESS_DENIED 기록
                AuditService.log_access_denied(
                    resource=f.__name__,
                    resource_id=kwargs.get('id')
                )
                # API 요청이면 JSON, 웹이면 리다이렉트
                if _is_api_request():
                    return jsonify({
                        'error': 'ACCESS_DENIED',
                        'message': f'접근 권한이 없습니다. 필요 역할: {", ".join(roles)}'
                    }), 403
                flash(f'접근 권한이 없습니다. (필요 역할: {", ".join(roles)})', 'danger')
                return redirect(url_for('main.dashboard'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_permission(resource: str, action: str):
    """
    리소스-액션 기반 권한 확인 데코레이터.
    User.has_permission()을 사용해 역할별 권한 테이블 참조.
    
    사용 예시:
        @require_permission('audit_log', 'read')
        def view_audit_logs(): ...
        
        @require_permission('patient', 'delete')
        def delete_patient(id): ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))

            if not current_user.has_permission(resource, action):
                AuditService.log_access_denied(resource=resource,
                                               resource_id=kwargs.get('id'))
                if _is_api_request():
                    return jsonify({
                        'error': 'PERMISSION_DENIED',
                        'message': f'{resource}에 대한 {action} 권한이 없습니다.'
                    }), 403
                flash(f'{resource}에 대한 권한이 없습니다.', 'danger')
                return redirect(url_for('main.dashboard'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_same_ward_or_admin(get_ward_func):
    """
    같은 병동이거나 admin인 경우만 접근 허용.
    병동 정보를 동적으로 가져오는 함수를 인자로 받음.
    
    사용 예시:
        @require_same_ward_or_admin(lambda: Patient.query.get(id).ward)
        def view_patient(id): ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))

            if current_user.role == 'admin':
                return f(*args, **kwargs)

            try:
                target_ward = get_ward_func()
                if current_user.ward and current_user.ward != target_ward:
                    flash('다른 병동의 데이터에 접근할 수 없습니다.', 'warning')
                    return redirect(url_for('main.dashboard'))
            except Exception:
                pass  # 병동 확인 실패 시 통과 (보수적 허용)

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def _is_api_request() -> bool:
    """API 요청 여부 확인 (URL 또는 Accept 헤더 기반)"""
    return (request.path.startswith('/api/') or
            'application/json' in request.headers.get('Accept', ''))
