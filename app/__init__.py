from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # 확장 초기화
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view         = 'auth.login'
    login_manager.login_message      = '로그인이 필요합니다.'
    login_manager.login_message_category = 'warning'

    # Blueprint 등록
    from app.routes.auth     import auth_bp
    from app.routes.main     import main_bp
    from app.routes.patients import patients_bp
    from app.routes.handover import handover_bp
    from app.routes.inbox    import inbox_bp
    from app.routes.audit    import audit_bp
    from app.api.handover    import api_handover_bp
    from app.api.stats       import api_stats_bp
    from app.api.notifications import api_notifications_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(patients_bp)
    app.register_blueprint(handover_bp)
    app.register_blueprint(inbox_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(api_handover_bp)
    app.register_blueprint(api_stats_bp)
    app.register_blueprint(api_notifications_bp)

    # 테이블 자동 생성 (MySQL DB가 이미 존재해야 함)
    with app.app_context():
        db.create_all()

    return app
