"""
app/models.py — 고도화 버전
기존 User / Patient / Handover 유지 + 3개 테이블 신규 추가:
  - AuditLog          : 모든 데이터 접근/변경 추적
  - RiskAssessment    : 인수인계별 위험도 분석 결과
  - HandoverAck       : 인수인계 확인(읽음) 처리
"""

import json
from datetime import datetime
from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ──────────────────────────────────────────────────────────────
# 기존 모델 (개선)
# ──────────────────────────────────────────────────────────────

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id              = db.Column(db.Integer,     primary_key=True)
    username        = db.Column(db.String(80),  unique=True, nullable=False)
    email           = db.Column(db.String(120), unique=True, nullable=False)
    password_hash   = db.Column(db.String(256), nullable=False)
    name            = db.Column(db.String(100), nullable=False)
    role            = db.Column(db.String(20),  default='nurse')
    # nurse / charge_nurse / doctor / admin
    ward            = db.Column(db.String(50))
    license_number  = db.Column(db.String(50))   # NEW: 면허번호
    is_active       = db.Column(db.Boolean,      default=True)  # NEW: 계정 활성 여부
    last_login_at   = db.Column(db.DateTime)     # NEW: 마지막 로그인
    created_at      = db.Column(db.DateTime,     default=datetime.utcnow)

    # Relationships
    handovers_given    = db.relationship('Handover', foreign_keys='Handover.from_user_id',
                                         backref='from_user', lazy=True)
    handovers_received = db.relationship('Handover', foreign_keys='Handover.to_user_id',
                                         backref='to_user', lazy=True)
    audit_logs         = db.relationship('AuditLog', backref='actor', lazy=True)
    acknowledgements   = db.relationship('HandoverAck', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_permission(self, resource: str, action: str) -> bool:
        """역할 기반 권한 확인 (하드코딩 테이블 방식 — 빠른 조회)"""
        ROLE_PERMISSIONS = {
            'admin': {'*': ['read', 'write', 'delete', 'admin']},
            'charge_nurse': {
                'handover': ['read', 'write', 'delete'],
                'patient':  ['read', 'write'],
                'audit_log': ['read'],
                'stats':    ['read'],
            },
            'nurse': {
                'handover': ['read', 'write'],
                'patient':  ['read', 'write'],
            },
            'doctor': {
                'handover': ['read'],
                'patient':  ['read', 'write'],
                'stats':    ['read'],
            },
        }
        role_perms = ROLE_PERMISSIONS.get(self.role, {})
        # admin은 모든 권한
        if '*' in role_perms:
            return True
        allowed_actions = role_perms.get(resource, [])
        return action in allowed_actions

    def to_dict(self):
        return {
            'id':       self.id,
            'username': self.username,
            'name':     self.name,
            'role':     self.role,
            'ward':     self.ward,
        }


class Patient(db.Model):
    __tablename__ = 'patients'

    id             = db.Column(db.Integer,  primary_key=True)
    patient_number = db.Column(db.String(20),  unique=True, nullable=False)
    name           = db.Column(db.String(100), nullable=False)
    age            = db.Column(db.Integer)
    gender         = db.Column(db.String(10))
    ward           = db.Column(db.String(50),  nullable=False)
    room           = db.Column(db.String(20))
    bed            = db.Column(db.String(10))
    diagnosis      = db.Column(db.Text)
    admission_date = db.Column(db.Date)
    discharge_date = db.Column(db.Date)
    status         = db.Column(db.String(20),  default='입원중')
    allergies      = db.Column(db.Text)
    special_notes  = db.Column(db.Text)
    created_at     = db.Column(db.DateTime,    default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime,    default=datetime.utcnow,
                               onupdate=datetime.utcnow)

    handovers = db.relationship('Handover', backref='patient', lazy=True,
                                cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id':             self.id,
            'patient_number': self.patient_number,
            'name':           self.name,
            'age':            self.age,
            'gender':         self.gender,
            'ward':           self.ward,
            'room':           self.room,
            'bed':            self.bed,
            'diagnosis':      self.diagnosis,
            'status':         self.status,
            'allergies':      self.allergies,
            'admission_date': self.admission_date.isoformat() if self.admission_date else None,
        }


class Handover(db.Model):
    __tablename__ = 'handovers'

    id              = db.Column(db.Integer,  primary_key=True)
    patient_id      = db.Column(db.Integer,  db.ForeignKey('patients.id'), nullable=False)
    from_user_id    = db.Column(db.Integer,  db.ForeignKey('users.id'),    nullable=False)
    to_user_id      = db.Column(db.Integer,  db.ForeignKey('users.id'))
    shift           = db.Column(db.String(20))
    content         = db.Column(db.Text,     nullable=False)
    vital_signs     = db.Column(db.Text)
    medications     = db.Column(db.Text)
    procedures      = db.Column(db.Text)
    has_danger      = db.Column(db.Boolean,  default=False)
    danger_keywords = db.Column(db.Text)
    priority        = db.Column(db.String(10), default='NORMAL')  # NEW: URGENT/HIGH/NORMAL
    is_confirmed    = db.Column(db.Boolean,  default=False)       # NEW: 인계자 확인 여부
    confirmed_at    = db.Column(db.DateTime)                      # NEW: 확인 시각
    confirmed_by    = db.Column(db.Integer,  db.ForeignKey('users.id'))  # NEW: 확인자
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow,
                               onupdate=datetime.utcnow)

    # Relationships
    risk_assessment  = db.relationship('RiskAssessment', backref='handover',
                                       uselist=False, cascade='all, delete-orphan')
    acknowledgements = db.relationship('HandoverAck', backref='handover',
                                       cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id':           self.id,
            'patient_id':   self.patient_id,
            'patient_name': self.patient.name if self.patient else None,
            'from_user':    self.from_user.name if self.from_user else None,
            'to_user':      self.to_user.name if self.to_user else None,
            'shift':        self.shift,
            'content':      self.content,
            'vital_signs':  self.vital_signs,
            'medications':  self.medications,
            'procedures':   self.procedures,
            'has_danger':   self.has_danger,
            'danger_keywords': self.danger_keywords,
            'priority':     self.priority,
            'is_confirmed': self.is_confirmed,
            'risk_score':   self.risk_assessment.risk_score if self.risk_assessment else None,
            'risk_level':   self.risk_assessment.risk_level if self.risk_assessment else None,
            'created_at':   self.created_at.isoformat() if self.created_at else None,
        }


# ──────────────────────────────────────────────────────────────
# 신규 모델 1: AuditLog (감사 로그)
# ──────────────────────────────────────────────────────────────

class AuditLog(db.Model):
    """
    모든 데이터 접근/변경을 기록하는 감사 로그.
    
    설계 원칙:
    - 절대 삭제하지 않는다 (불변 레코드)
    - 변경 전/후 값을 JSON으로 저장
    - IP와 User-Agent를 함께 기록 (비정상 접근 탐지용)
    - old_value/new_value는 JSON 직렬화하여 TEXT로 저장
      (MySQL JSON 타입 대신 TEXT를 쓰는 이유: 구버전 MySQL 호환)
    """
    __tablename__ = 'audit_logs'

    id          = db.Column(db.Integer,      primary_key=True)
    user_id     = db.Column(db.Integer,      db.ForeignKey('users.id'), nullable=True)
    action      = db.Column(db.String(20),   nullable=False)
    # CREATE / READ / UPDATE / DELETE / LOGIN / LOGOUT / ACCESS_DENIED
    resource    = db.Column(db.String(50),   nullable=False)
    # 'handover' / 'patient' / 'user' / 'auth'
    resource_id = db.Column(db.Integer,      nullable=True)
    old_value   = db.Column(db.Text,         nullable=True)  # JSON string
    new_value   = db.Column(db.Text,         nullable=True)  # JSON string
    ip_address  = db.Column(db.String(45),   nullable=True)
    user_agent  = db.Column(db.String(500),  nullable=True)
    description = db.Column(db.String(500),  nullable=True)  # 사람이 읽기 좋은 설명
    created_at  = db.Column(db.DateTime,     default=datetime.utcnow,
                            index=True)  # 인덱스: 날짜별 조회 성능

    def get_old_value(self):
        """JSON 문자열을 dict로 반환"""
        if self.old_value:
            try:
                return json.loads(self.old_value)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    def get_new_value(self):
        if self.new_value:
            try:
                return json.loads(self.new_value)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    def to_dict(self):
        return {
            'id':          self.id,
            'user':        self.actor.name if self.actor else '시스템',
            'action':      self.action,
            'resource':    self.resource,
            'resource_id': self.resource_id,
            'description': self.description,
            'ip_address':  self.ip_address,
            'created_at':  self.created_at.isoformat() if self.created_at else None,
        }


# ──────────────────────────────────────────────────────────────
# 신규 모델 2: RiskAssessment (위험도 분석 결과)
# ──────────────────────────────────────────────────────────────

class RiskAssessment(db.Model):
    """
    인수인계별 위험도 분석 결과를 저장.
    
    설계 원칙:
    - Handover와 1:1 관계 (하나의 인수인계 = 하나의 분석 결과)
    - 분석 로직은 services/risk_service.py에서 처리
    - triggered_rules에 어떤 규칙이 발동됐는지 JSON으로 저장
      → 나중에 "왜 위험으로 판단했나" 설명 가능
    """
    __tablename__ = 'risk_assessments'

    id             = db.Column(db.Integer,  primary_key=True)
    handover_id    = db.Column(db.Integer,  db.ForeignKey('handovers.id'),
                               nullable=False, unique=True)
    risk_score     = db.Column(db.Integer,  default=0)     # 0~100
    risk_level     = db.Column(db.String(20), default='LOW')
    # CRITICAL(80~) / HIGH(60~79) / MEDIUM(40~59) / LOW(0~39)
    triggered_rules = db.Column(db.Text,    nullable=True)  # JSON: 발동된 규칙 목록
    vital_flag      = db.Column(db.Boolean, default=False)  # 바이탈 이상 여부
    keyword_flag    = db.Column(db.Boolean, default=False)  # 위험 키워드 감지
    frequency_flag  = db.Column(db.Boolean, default=False)  # 동일 환자 반복 위험
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    def get_triggered_rules(self):
        if self.triggered_rules:
            try:
                return json.loads(self.triggered_rules)
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    @property
    def level_color(self):
        """템플릿에서 배지 색상 결정용"""
        return {
            'CRITICAL': 'danger',
            'HIGH':     'warning',
            'MEDIUM':   'info',
            'LOW':      'success',
        }.get(self.risk_level, 'secondary')


# ──────────────────────────────────────────────────────────────
# 신규 모델 3: HandoverAck (인수인계 확인)
# ──────────────────────────────────────────────────────────────

class HandoverAck(db.Model):
    """
    인수인계를 누가 언제 확인(읽음)했는지 기록.
    
    설계 원칙:
    - 같은 사람이 같은 인수인계를 중복 확인 불가 (UNIQUE 제약)
    - 확인 메모 기능: 인계자가 간단한 코멘트 남길 수 있음
    """
    __tablename__ = 'handover_acknowledgements'
    __table_args__ = (
        db.UniqueConstraint('handover_id', 'user_id', name='unique_ack'),
    )

    id          = db.Column(db.Integer,  primary_key=True)
    handover_id = db.Column(db.Integer,  db.ForeignKey('handovers.id'), nullable=False)
    user_id     = db.Column(db.Integer,  db.ForeignKey('users.id'),     nullable=False)
    ack_at      = db.Column(db.DateTime, default=datetime.utcnow)
    note        = db.Column(db.Text,     nullable=True)  # 확인 메모
