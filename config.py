import os
from dotenv import load_dotenv

# 프로젝트 루트의 .env 파일을 자동으로 읽어 환경변수로 등록
load_dotenv()

class Config:
    # ── 보안 ───────────────────────────────────────
    SECRET_KEY = os.environ.get('SECRET_KEY', 'fallback-secret-key')

    # ── MySQL 연결 (MySQL Workbench 로 직접 만든 DB 사용) ──
    DB_USER     = os.environ.get('DB_USER',     'root')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
    DB_HOST     = os.environ.get('DB_HOST',     'localhost')
    DB_PORT     = os.environ.get('DB_PORT',     '3306')
    DB_NAME     = os.environ.get('DB_NAME',     'nurse_handover')

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── Flask 모드 ─────────────────────────────────
    FLASK_ENV = os.environ.get('FLASK_ENV', 'development')
    DEBUG     = FLASK_ENV == 'development'

    # ── 위험 키워드 목록 (자유롭게 추가/수정) ───────
    DANGER_KEYWORDS = [
        '낙상', '자살', '자해', '무의식', '심정지', '호흡곤란', '경련', '발작',
        '쇼크', '알레르기', '과민반응', '출혈', '혼수', '혼미', '섬망',
        '패혈증', '응급', '즉시', '위험', '악화', '급격', '사망',
        'DNR', 'CPR', '인공호흡기', '투석', '수혈',
    ]
