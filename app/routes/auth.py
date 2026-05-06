from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User

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
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            flash(f'안녕하세요, {user.name}님!', 'success')
            return redirect(next_page or url_for('main.dashboard'))

        flash('아이디 또는 비밀번호가 올바르지 않습니다.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('로그아웃되었습니다.', 'info')
    return redirect(url_for('auth.login'))
