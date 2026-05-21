"""
app/__init__.py — 고도화 버전 Flask App Factory

변경사항:
  - API Blueprint (api_handover, api_stats) 등록
  - Audit Blueprint 등록
  - 전역 에러 핸들러 추가
  - 요청마다 감사 컨텍스트 설정
"""

from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config


db           = SQLAlchemy()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # ── 확장 초기화 ────────────────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view          = 'auth.login'
    login_manager.login_message       = '로그인이 필요합니다.'
    login_manager.login_message_category = 'warning'

    # ── Blueprint 등록 ─────────────────────────────────────────
    # 웹 뷰
    from app.routes.auth     import auth_bp
    from app.routes.main     import main_bp
    from app.routes.patients import patients_bp
    from app.routes.handover import handover_bp
    from app.routes.audit    import audit_bp
    

    # REST API
    from app.api.handover import api_handover_bp
    from app.api.stats    import api_stats_bp
    from app.routes.inbox       import inbox_bp
    from app.api.notifications  import api_notifications_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(patients_bp)
    app.register_blueprint(handover_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(api_handover_bp)
    app.register_blueprint(api_stats_bp)
    app.register_blueprint(inbox_bp)
    app.register_blueprint(api_notifications_bp)

    # ── 전역 에러 핸들러 ───────────────────────────────────────
    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({'error': 'FORBIDDEN', 'message': '권한이 없습니다.'}), 403

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'error': 'NOT_FOUND', 'message': '리소스를 찾을 수 없습니다.'}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({'error': 'SERVER_ERROR', 'message': '서버 오류가 발생했습니다.'}), 500

    # ── DB 테이블 자동 생성 ────────────────────────────────────
    with app.app_context():
        db.create_all()

    return app
