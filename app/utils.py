import re

from flask import current_app
from sqlalchemy import false


def detect_danger_keywords(text: str):
    """
    텍스트에서 위험 키워드를 찾아 (발견된_키워드_리스트, has_danger) 를 반환합니다.
    config.py 의 DANGER_KEYWORDS 목록을 참조합니다.
    """
    if not text:
        return [], False

    keywords = current_app.config.get('DANGER_KEYWORDS', [])
    found    = [kw for kw in keywords if kw in text]
    return found, len(found) > 0


def normalize_department(department: str) -> str:
    """
    병동/진료과명에서 선행 숫자를 제거해 상위 진료과 그룹을 반환합니다.
    예: 1내과, 2 내과, 3-내과 -> 내과 / 1외과 -> 외과
    """
    if not department:
        return ''

    normalized = str(department).strip()
    normalized = normalized.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
    normalized = re.sub(r'^\s*\d+\s*[-_/]?\s*', '', normalized)
    return normalized.strip()


def get_department_group(department: str) -> str:
    """normalize_department의 의미가 드러나는 별칭."""
    return normalize_department(department)


def get_accessible_patient_wards(user) -> list:
    """
    nurse가 접근 가능한 실제 ward 값 목록을 반환합니다.
    nurse 외 역할은 환자 스코프 제한이 없으므로 None을 반환합니다.
    """
    if getattr(user, 'role', None) != 'nurse':
        return None

    user_group = get_department_group(getattr(user, 'ward', None))
    if not user_group:
        return []

    from app import db
    from app.models import Patient

    wards = [row[0] for row in db.session.query(Patient.ward).distinct().all() if row[0]]
    return [ward for ward in wards if get_department_group(ward) == user_group]


def can_access_patient(user, patient) -> bool:
    """사용자가 해당 환자를 조회/선택할 수 있는지 확인합니다."""
    if getattr(user, 'role', None) != 'nurse':
        return True
    if not patient:
        return False
    user_group = get_department_group(getattr(user, 'ward', None))
    if not user_group:
        return False
    return user_group == get_department_group(patient.ward)


def apply_patient_scope(query, user):
    """환자 쿼리에 역할 기반 환자 접근 범위를 적용합니다."""
    allowed_wards = get_accessible_patient_wards(user)
    if allowed_wards is None:
        return query

    from app.models import Patient

    if not allowed_wards:
        return query.filter(false())
    return query.filter(Patient.ward.in_(allowed_wards))


def apply_handover_patient_scope(query, user):
    """인수인계 쿼리에 환자 접근 범위를 적용합니다."""
    allowed_wards = get_accessible_patient_wards(user)
    if allowed_wards is None:
        return query

    from app.models import Handover, Patient

    if not allowed_wards:
        return query.filter(false())
    return (query
            .join(Patient, Handover.patient_id == Patient.id)
            .filter(Patient.ward.in_(allowed_wards)))
