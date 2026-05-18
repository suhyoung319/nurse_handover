# 🏥 병동 인수인계 시스템 (Ward Handover Platform)

Flask + MySQL 기반 간호사 인수인계 웹 플랫폼입니다.  
단순 CRUD를 넘어 **실제 병동 업무 흐름**을 반영한 백엔드 시스템을 목표로 설계했습니다.

---

## 📁 프로젝트 구조

```
nurse_handover/
├── run.py                          # Flask 실행 진입점
├── config.py                       # .env 로드 + DB URI 조립 + 위험 키워드 설정
├── .env                            # 실제 DB 접속정보 (Git 제외)
├── .env.example                    # 환경변수 템플릿
├── .gitignore
├── requirements.txt
│
└── app/
    ├── __init__.py                 # Flask App Factory + Blueprint 등록 + 에러핸들러
    ├── models.py                   # DB 모델 (User, Patient, Handover,
    │                               #   AuditLog, RiskAssessment, HandoverAck)
    ├── utils.py                    # 레거시 키워드 유틸 (현재 risk_service로 대체됨)
    │
    ├── routes/                     # 웹뷰 라우트 (HTML 반환)
    │   ├── auth.py                 # 회원가입 / 로그인 / 로그아웃
    │   ├── main.py                 # 대시보드 (/ → inbox로 리다이렉트)
    │   ├── patients.py             # 환자 CRUD + 위험도 우선순위 정렬
    │   ├── handover.py             # 인수인계 CRUD + 키워드 AJAX API
    │   ├── inbox.py                # 받은/보낸/위험 인수인계함
    │   └── audit.py                # 감사 로그 뷰 (admin/charge_nurse 전용)
    │
    ├── api/                        # REST API (JSON 반환, /api/v1/)
    │   ├── handover.py             # GET/POST/PUT/DELETE /api/v1/handovers
    │   ├── stats.py                # GET /api/v1/stats/dashboard, top-risk-patients
    │   └── notifications.py        # GET /api/v1/notifications/unread-count (Polling)
    │
    ├── services/                   # 비즈니스 로직 레이어
    │   ├── audit_service.py        # 감사 로그 기록 엔진
    │   ├── risk_service.py         # 위험도 자동 분석 (가중치 기반 0~100점)
    │   ├── handover_workflow_service.py  # 인수인계 워크플로우 (상태 전이)
    │   └── notification_service.py # 미확인 인수인계 알림 요약
    │
    ├── middleware/
    │   └── rbac.py                 # @require_role, @require_permission 데코레이터
    │
    └── templates/                  # Jinja2 템플릿 (Bootstrap 5)
        ├── base.html               # 공통 레이아웃 (사이드바 + 알림 배지 + Polling JS)
        ├── auth/
        │   ├── login.html
        │   └── register.html
        ├── main/
        │   └── dashboard.html
        ├── patients/
        │   ├── index.html          # 위험도 우선순위 카드 목록
        │   ├── detail.html         # 인수인계 이력 3단계 (진행중/24h/전체)
        │   └── form.html
        ├── handover/
        │   ├── index.html
        │   ├── detail.html
        │   └── form.html
        ├── inbox/
        │   ├── index.html          # 받은 인수인계함 (미확인 우선)
        │   ├── sent.html           # 보낸 인수인계함
        │   ├── danger.html         # CRITICAL/HIGH 위험 인수인계 모아보기
        │   └── transfer.html       # 인수인계 대상 변경
        └── audit/
            └── index.html          # 감사 로그 목록
```

---

## 🚀 실행 방법 (Windows 로컬)

### 사전 준비

**1. Python 설치**

[https://www.python.org/downloads/](https://www.python.org/downloads/) 에서 Python 3.11 이상 설치  
설치 시 **"Add Python to PATH"** 반드시 체크

**2. MySQL DB 생성** (MySQL Workbench)

```sql
CREATE DATABASE nurse_handover
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

테이블은 Flask 최초 실행 시 `db.create_all()`로 자동 생성됩니다.

---

### 환경변수 설정 (`.env`)

`.env.example`을 복사해 `.env`로 저장 후 수정합니다.

```env
SECRET_KEY=your-secret-key-here

DB_USER=root
DB_PASSWORD=본인MySQL비밀번호
DB_HOST=localhost
DB_PORT=3306
DB_NAME=nurse_handover

FLASK_ENV=development
```

> `.env`는 절대 Git에 올리지 마세요. `.gitignore`에 등록되어 있습니다.

---

### 실행

```powershell
# 가상환경 생성 (최초 1회)
python -m venv venv

# 가상환경 활성화
venv\Scripts\Activate.ps1

# 패키지 설치 (최초 1회)
pip install -r requirements.txt

# 서버 실행
python run.py
```

브라우저에서 [http://localhost:5000](http://localhost:5000) 접속

---

## ⚙️ DB 연결 흐름

```
.env
  DB_USER / DB_PASSWORD / DB_HOST / DB_PORT / DB_NAME
      ↓
config.py
  mysql+pymysql://user:pw@host:port/dbname?charset=utf8mb4
      ↓
app/__init__.py
  SQLAlchemy 초기화 → db.create_all() → 테이블 자동 생성
```

---

## 🏗️ 주요 기능

| 기능 | 설명 |
|------|------|
| **회원가입 / 로그인** | Flask-Login 세션 인증, 가입 시 role=nurse 고정 |
| **RBAC 권한 관리** | nurse / charge_nurse / doctor / admin 역할별 접근 제어 |
| **환자 CRUD** | 등록·수정·삭제(admin/charge_nurse만)·검색·필터 |
| **환자 목록 우선순위 정렬** | 고위험+미확인 → 고위험 → 미확인 → 일반 순 자동 정렬 |
| **인수인계 CRUD** | 교대(주간/야간/심야)별, 활력징후·투약·처치 분리 입력 |
| **위험도 자동 분석** | 키워드 가중치 + 바이탈 수치 파싱 + 반복 패턴으로 0~100점 산정 |
| **받은 인수인계함** | 미확인(CRITICAL 우선) → 확인완료 탭 분리 |
| **보낸 인수인계함** | 상대방 확인 여부 추적, 대상 변경/취소 가능 |
| **위험 인수인계 모아보기** | CRITICAL/HIGH/MEDIUM 필터 전용 페이지 |
| **인수인계 확인(Ack)** | 확인 버튼 + 메모 입력, 중복 확인 방지 |
| **감사 로그** | 모든 생성·조회·수정·삭제·로그인을 IP와 함께 기록 |
| **알림 배지 (Polling)** | 5초마다 미확인 수 확인, CRITICAL 시 탭 타이틀 깜빡임 |
| **REST API** | `/api/v1/handovers`, `/api/v1/stats`, `/api/v1/notifications` |
| **대시보드** | 입원 환자 수, 오늘 인수인계, 위험 현황, 미확인 건수 |

---

## 🔐 역할별 권한

| 역할 | 설명 | 주요 권한 |
|------|------|----------|
| `nurse` | 일반 간호사 | 인수인계 작성·수정, 자기 병동 환자 조회 |
| `charge_nurse` | 수간호사 | nurse 권한 + 인수인계 삭제 + 감사 로그 + 통계 + 환자 삭제 |
| `doctor` | 의사 | 인수인계·환자 조회, 통계 |
| `admin` | 관리자 | 모든 권한 |

> 회원가입 시 role은 `nurse`로 고정됩니다. 역할 변경은 관리자가 DB에서 직접 수정합니다.

---

## 🧠 핵심 설계 결정

### 1. Service Layer 패턴

Route는 HTTP 요청/응답만 처리하고, 비즈니스 로직은 `services/`로 분리합니다.  
덕분에 웹뷰와 REST API가 같은 서비스 코드를 재사용합니다.

```
routes/handover.py  ──┐
                       ├──→ services/risk_service.py
api/handover.py     ──┘       services/audit_service.py
```

### 2. 위험도 분석 엔진 (`risk_service.py`)

단순 키워드 포함 여부가 아닌 **가중치 기반 점수 시스템**입니다.

| 규칙 | 점수 |
|------|------|
| CRITICAL 키워드 (심정지, DNR, 사망 등) | +40점 |
| HIGH 키워드 (낙상, 쇼크, 경련 등) | +25점 |
| MEDIUM 키워드 (호흡곤란, 섬망 등) | +10점 |
| 바이탈 수치 이상 (BP>180, SpO2<95% 등) | +20점 |
| 복합 카테고리 동시 발동 | +10점 |
| 24시간 내 반복 위험 | +15점 |
| 네거티브 컨텍스트 ("낙상 없음") | -50% |

점수 → 레벨: `CRITICAL(80+)` / `HIGH(60~79)` / `MEDIUM(40~59)` / `LOW(0~39)`

### 3. Audit Log (`audit_service.py`)

모든 데이터 접근·변경을 IP, User-Agent와 함께 `audit_logs` 테이블에 기록합니다.  
감사 로그 기록 실패가 실제 업무를 막지 않도록 내부에서 예외를 흡수합니다.

```python
# 사용 예시
AuditService.log_create('handover', handover.id, description='인수인계 작성')
AuditService.log_update('patient',  patient.id,  old_value=old, new_value=new)
AuditService.log_login(user.id, success=True)
```

### 4. RBAC (`middleware/rbac.py`)

데코레이터 한 줄로 선언적 권한 제어가 가능합니다.

```python
@require_role('admin', 'charge_nurse')
def delete_patient(id): ...

@require_permission('audit_log', 'read')
def view_audit_logs(): ...
```

### 5. 인수인계 상태 워크플로우

```
작성
  ↓
PENDING ──→ ACKNOWLEDGED  (인계받은 사람이 확인)
  ↓
CANCELLED               (작성자 / 수간호사 / admin이 취소)
  ↓
TRANSFERRED             (대상 변경 → 새 PENDING 자동 생성)
```

### 6. 알림 Polling

5초마다 `/api/v1/notifications/unread-count`를 호출해 navbar 배지를 업데이트합니다.  
`notification_service.py` 한 파일만 수정하면 WebSocket(Flask-SocketIO)으로 전환 가능합니다.

---

## 🌐 REST API 엔드포인트

| 메서드 | URL | 설명 |
|--------|-----|------|
| GET | `/api/v1/handovers/` | 인수인계 목록 (page, shift, danger_only 파라미터) |
| POST | `/api/v1/handovers/` | 인수인계 생성 |
| GET | `/api/v1/handovers/<id>` | 인수인계 상세 |
| PUT | `/api/v1/handovers/<id>` | 인수인계 수정 |
| DELETE | `/api/v1/handovers/<id>` | 인수인계 삭제 |
| GET | `/api/v1/handovers/<id>/risk` | 위험도 상세 (triggered_rules 포함) |
| POST | `/api/v1/handovers/<id>/acknowledge` | 확인 처리 |
| GET | `/api/v1/stats/dashboard` | 병동 통계 |
| GET | `/api/v1/stats/top-risk-patients` | 고위험 환자 Top 10 |
| GET | `/api/v1/notifications/unread-count` | 미확인 인수인계 요약 |

---

## 🗃️ DB 테이블 구조

| 테이블 | 설명 |
|--------|------|
| `users` | 의료진 계정 (role, ward, is_active, last_login_at) |
| `patients` | 환자 정보 (병동, 진단, 알레르기, 특이사항) |
| `handovers` | 인수인계 내용 (교대, 바이탈, 투약, 처치, 상태, 우선순위) |
| `risk_assessments` | 인수인계별 위험도 분석 결과 (score, level, triggered_rules) |
| `handover_acknowledgements` | 인수인계 확인 기록 (확인자, 확인 시각, 메모) |
| `audit_logs` | 모든 데이터 접근/변경 감사 기록 (action, IP, user_agent) |

---

## 🔧 기술 스택

| 구분 | 기술 |
|------|------|
| Backend | Flask 3.0.3 |
| ORM | Flask-SQLAlchemy 3.1.1 |
| DB 드라이버 | PyMySQL 1.1.1 |
| 인증 | Flask-Login 0.6.3 |
| 환경변수 | python-dotenv 1.0.1 |
| 보안 | Werkzeug (password hashing), cryptography |
| Frontend | Bootstrap 5.3 + Bootstrap Icons + Jinja2 |
| DB | MySQL 8.x |

---

## 🐛 자주 겪는 문제

| 증상 | 원인 | 해결 |
|------|------|------|
| `python` 명령어를 찾을 수 없음 | PATH 미설정 | Python 재설치, "Add to PATH" 체크 |
| `Access denied for user 'root'` | .env 비밀번호 오류 | `.env`의 `DB_PASSWORD` 확인 |
| `Unknown database 'nurse_handover'` | DB 미생성 | Workbench에서 `CREATE DATABASE` 실행 |
| `Unknown column 'users.license_number'` | 마이그레이션 미실행 | Workbench에서 `ALTER TABLE` 실행 |
| `ModuleNotFoundError: No module named 'app'` | venv 미활성화 | `venv\Scripts\Activate.ps1` 후 재실행 |
| `/audit/` 접근 시 대시보드로 튕김 | 권한 부족 | `charge_nurse` 또는 `admin` 계정으로 로그인 |
| 알림 배지가 안 뜸 | Polling API 오류 | `audit_logs` 테이블 존재 여부 확인 |
| 포트 5000 이미 사용 중 | 프로그램 충돌 | `run.py`에서 `port=5001`로 변경 |
