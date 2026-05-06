# 🏥 병동 인수인계 시스템 — Windows 로컬 실행 가이드

Flask + MySQL (PyMySQL) 기반 병동 인수인계 웹 플랫폼입니다.  
Docker 없이 **Windows 로컬 환경**에서 바로 실행합니다.

---

## 📁 프로젝트 구조

```
nurse_handover/
├── run.bat                    ← Windows 실행 파일 (더블클릭)
├── run.py                     ← Flask 진입점
├── config.py                  ← DB URI 조립 + 앱 설정
├── .env                       ← 실제 DB 접속정보 (직접 생성, Git 제외)
├── requirements.txt           ← Python 패키지 목록
│
└── app/
    ├── __init__.py            ← Flask App Factory, SQLAlchemy/LoginManager 초기화
    ├── models.py              ← DB 모델 (User, Patient, Handover)
    ├── utils.py               ← 위험 키워드 감지 함수
    ├── routes/
    │   ├── auth.py            ← 회원가입 / 로그인 / 로그아웃
    │   ├── main.py            ← 대시보드
    │   ├── patients.py        ← 환자 CRUD
    │   └── handover.py        ← 인수인계 CRUD + 키워드 AJAX API
    └── templates/             ← Jinja2 HTML 템플릿 (Bootstrap 5)
        ├── base.html
        ├── auth/
        ├── main/
        ├── patients/
        └── handover/
```

---

## ✅ 사전 준비

### 1. Python 설치
- https://www.python.org/downloads/ 에서 **Python 3.11 이상** 설치
- 설치 화면 첫 번째 옵션 **"Add Python to PATH"** 반드시 체크 ✔

설치 확인:
```cmd
python --version
```

### 2. MySQL 설치 및 DB 생성 (MySQL Workbench 사용)

MySQL Workbench를 열고 아래 SQL을 실행해 DB를 만듭니다:

```sql
CREATE DATABASE nurse_handover
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

> 테이블은 Flask 최초 실행 시 **자동으로 생성**됩니다 (`db.create_all()`).  
> Workbench에서 DB만 만들어두면 됩니다.

---

## ⚙️ 환경 설정 (.env 파일)

### 1. `.env` 파일 수정

메모장으로 `.env` 를 열어 본인 MySQL 정보를 입력합니다:

```env
SECRET_KEY=my-secret-key-12345

DB_USER=root
DB_PASSWORD=본인MySQL비밀번호
DB_HOST=localhost
DB_PORT=3306
DB_NAME=nurse_handover

FLASK_ENV=development
```

`.env` 파일은 **절대 Git에 올리지 마세요** (비밀번호 포함).  
`.gitignore` 에 `.env` 가 이미 등록되어 있습니다.

---

## ▶️ 실행 방법

### 방법 A — 더블클릭 (권장)

탐색기에서 **`run.bat`** 을 더블클릭합니다.

- 최초 실행 시 가상환경(venv) 자동 생성
- 패키지 자동 설치 (Flask, PyMySQL 등)
- 브라우저 자동 오픈 → http://localhost:5000

### 방법 B — 명령 프롬프트 (수동)

```cmd
:: 프로젝트 폴더로 이동
cd C:\path\to\nurse_handover

:: 가상환경 생성 (최초 1회)
python -m venv venv

:: 가상환경 활성화
venv\Scripts\activate

:: 패키지 설치 (최초 1회)
pip install -r requirements.txt

:: 서버 실행
python run.py
```

브라우저에서 http://localhost:5000 접속

---

## 🔌 DB 연결 구조

`.env` → `config.py` → `app/__init__.py` 순서로 읽힙니다.

```
.env 파일
  DB_USER=root
  DB_PASSWORD=1234
  DB_HOST=localhost
  DB_PORT=3306
  DB_NAME=nurse_handover
        ↓
config.py 에서 조립
  mysql+pymysql://root:1234@localhost:3306/nurse_handover?charset=utf8mb4
        ↓
SQLAlchemy 가 MySQL 에 연결
        ↓
db.create_all() 로 테이블 자동 생성
```

---

## 🏗️ 주요 기능

| 기능 | 설명 |
|------|------|
| 회원가입 / 로그인 | Flask-Login 세션 인증, Werkzeug 비밀번호 해싱 |
| 환자 CRUD | 등록·수정·삭제·검색·필터·페이지네이션 |
| 인수인계 CRUD | 교대(주간/야간/심야)별 작성, 활력징후·투약·처치 입력 |
| 위험 키워드 감지 | 입력 중 AJAX 실시간 감지 + 저장 시 DB 기록 |
| 대시보드 | 입원 환자 수, 오늘 인수인계, 위험 감지 현황 |

---

## 🚨 자주 겪는 문제

| 증상 | 원인 | 해결 |
|------|------|------|
| `python` 명령어를 찾을 수 없음 | PATH 미설정 | Python 재설치, "Add to PATH" 체크 |
| `Access denied for user 'root'` | .env 비밀번호 오류 | .env 의 DB_PASSWORD 확인 |
| `Unknown database 'nurse_handover'` | DB 미생성 | Workbench에서 CREATE DATABASE 실행 |
| `ModuleNotFoundError: flask` | venv 미활성화 | `venv\Scripts\activate` 후 재실행 |
| 포트 5000 이미 사용 중 | 다른 프로그램 충돌 | run.py 의 port=5000 → 5001 변경 |

---

## 🔧 기술 스택

| 구분 | 기술 |
|------|------|
| Backend | Flask 3.x |
| ORM | Flask-SQLAlchemy 3.x |
| DB 드라이버 | PyMySQL 1.1 |
| 인증 | Flask-Login |
| 환경변수 | python-dotenv |
| Frontend | Bootstrap 5.3 + Jinja2 |
| DB | MySQL 8.x (MySQL Workbench로 직접 생성) |
