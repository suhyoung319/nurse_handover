"""
routes/auth.py — 고도화 버전
로그인 성공/실패, 로그아웃을 감사 로그에 기록합니다.
"""

from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User
from app.services.audit_service import AuditService

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email    = request.form.get('email',    '').strip()
        name     = request.form.get('name',     '').strip()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')
        role     = request.form.get('role', 'nurse')
        ward     = request.form.get('ward', '').strip()

        if not all([username, email, name, password]):
            flash('모든 필수 항목을 입력해주세요.', 'danger')
            return render_template('auth/register.html')

        if password != confirm:
            flash('비밀번호가 일치하지 않습니다.', 'danger')
            return render_template('auth/register.html')

        if User.query.filter_by(username=username).first():
            flash('이미 사용 중인 아이디입니다.', 'danger')
            return render_template('auth/register.html')

        if User.query.filter_by(email=email).first():
            flash('이미 사용 중인 이메일입니다.', 'danger')
            return render_template('auth/register.html')

        user = User(username=username, email=email, name=name, role=role, ward=ward)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        # 회원가입 감사 로그
        AuditService.log_create(
            resource='user',
            resource_id=user.id,
            new_value={'username': username, 'role': role, 'ward': ward},
            description=f'신규 계정 생성: {name} ({role})'
        )

        flash('회원가입이 완료되었습니다. 로그인해주세요.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            if not user.is_active:
                flash('비활성화된 계정입니다. 관리자에게 문의하세요.', 'danger')
                AuditService.log_login(user.id, success=False)
                return render_template('auth/login.html')

            login_user(user, remember=remember)

            # 마지막 로그인 시각 업데이트
            user.last_login_at = datetime.utcnow()
            db.session.commit()

            # 로그인 성공 감사 로그
            AuditService.log_login(user.id, success=True)

            next_page = request.args.get('next')
            flash(f'안녕하세요, {user.name}님! ({user.role})', 'success')
            return redirect(next_page or url_for('main.dashboard'))

        else:
            # 로그인 실패 감사 로그 (user_id는 None일 수 있음)
            AuditService.log_login(
                user_id=user.id if user else None,
                success=False
            )
            flash('아이디 또는 비밀번호가 올바르지 않습니다.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    AuditService.log_logout()
    logout_user()
    flash('로그아웃되었습니다.', 'info')
    return redirect(url_for('auth.login'))
