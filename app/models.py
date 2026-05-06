from datetime import datetime
from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id            = db.Column(db.Integer,     primary_key=True)
    username      = db.Column(db.String(80),  unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name          = db.Column(db.String(100), nullable=False)
    role          = db.Column(db.String(20),  default='nurse')   # nurse / doctor / admin
    ward          = db.Column(db.String(50))
    created_at    = db.Column(db.DateTime,    default=datetime.utcnow)

    handovers_given    = db.relationship('Handover', foreign_keys='Handover.from_user_id',
                                         backref='from_user', lazy=True)
    handovers_received = db.relationship('Handover', foreign_keys='Handover.to_user_id',
                                         backref='to_user',   lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Patient(db.Model):
    __tablename__ = 'patients'

    id             = db.Column(db.Integer,     primary_key=True)
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
    status         = db.Column(db.String(20),  default='입원중')   # 입원중 / 퇴원 / 전동
    allergies      = db.Column(db.Text)
    special_notes  = db.Column(db.Text)
    created_at     = db.Column(db.DateTime,    default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime,    default=datetime.utcnow,
                               onupdate=datetime.utcnow)

    handovers = db.relationship('Handover', backref='patient', lazy=True,
                                cascade='all, delete-orphan')


class Handover(db.Model):
    __tablename__ = 'handovers'

    id             = db.Column(db.Integer,  primary_key=True)
    patient_id     = db.Column(db.Integer,  db.ForeignKey('patients.id'), nullable=False)
    from_user_id   = db.Column(db.Integer,  db.ForeignKey('users.id'),    nullable=False)
    to_user_id     = db.Column(db.Integer,  db.ForeignKey('users.id'))
    shift          = db.Column(db.String(20))                 # 주간 / 야간 / 심야
    content        = db.Column(db.Text,     nullable=False)
    vital_signs    = db.Column(db.Text)
    medications    = db.Column(db.Text)
    procedures     = db.Column(db.Text)
    has_danger     = db.Column(db.Boolean,  default=False)
    danger_keywords = db.Column(db.Text)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, default=datetime.utcnow,
                               onupdate=datetime.utcnow)
