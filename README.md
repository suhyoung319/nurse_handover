# 병동 인수인계 시스템 (Ward Handover Platform)

Flask + MySQL 기반 병동 인수인계 웹 플랫폼입니다. 단순 환자/인수인계 CRUD를 넘어 실제 병동 업무 흐름에 필요한 받은/보낸 인수인계함, 확인 처리, 대상 변경, 위험 인수인계 조회, 역할 기반 접근 제어, 감사 로그, 알림 배지, 규칙 기반 위험도 분석, FastAPI AI 위험도 분석을 함께 구성했습니다.

별도 프로젝트인 `clinical-text-risk-api`를 함께 실행하면 KLUE-BERT 기반 임상 텍스트 위험도 예측 결과가 `handovers.risk_level`, `handovers.risk_score`에 저장되고 화면에 표시됩니다.

> 포트폴리오 목적의 로컬 실행 프로젝트입니다. 실제 의료 현장 적용 전에는 개인정보보호, 보안, 의료기관 내부 규정, 임상 검증 절차가 필요합니다.

---

## 1. 핵심 요약

```text
Flask 병동 인수인계 시스템
+ MySQL 데이터 저장
+ Flask-Login 세션 인증
+ 역할 기반 접근 제어(RBAC)
+ 환자 접근 범위 제한
+ 받은/보낸/위험 인수인계함
+ 확인 처리 및 확인 메모
+ Polling 기반 미확인 알림 배지
+ 감사 로그
+ 규칙 기반 위험도 분석
+ FastAPI AI 위험도 분석
+ 대시보드 및 환자 목록 위험도 표시
```

핵심 특징은 **규칙 기반 위험도**와 **AI 기반 위험도**를 분리해 함께 보여주는 구조입니다. 규칙 기반 분석은 명확한 키워드, 바이탈, 반복 위험을 점수화하고, AI 분석은 별도 FastAPI 서버의 KLUE-BERT 모델이 문장 전체 맥락을 예측합니다.

---

## 2. 전체 아키텍처

```text
사용자
  ↓
Flask Web App
  ↓
인수인계 작성 / 조회 / 확인 / 수정 / 취소 / 대상 변경
  ↓
MySQL 저장
  ↓
[1] risk_service.py      -> 규칙 기반 위험도 분석
[2] risk_ai_service.py   -> FastAPI /predict 호출
                              ↓
                         clinical-text-risk-api
                              ↓
                         KLUE-BERT risk_model
                              ↓
                         AI 위험도 반환
  ↓
화면 표시
  - risk_assessments: 규칙 기반 위험도
  - handovers.risk_level / risk_score: AI 위험도
```

---

## 3. 프로젝트 구조

```text
nurse_handover/
├── run.py                          # Flask 실행 진입점
├── config.py                       # 환경변수 로드, DB URI, 위험 키워드 설정
├── requirements.txt
├── README.md
│
└── app/
    ├── __init__.py                 # Flask App Factory, Blueprint 등록
    ├── models.py                   # User, Patient, Handover, AuditLog, RiskAssessment, HandoverAck
    ├── utils.py                    # 환자 접근 범위, 진료과 정규화, 위험 키워드 유틸
    │
    ├── routes/
    │   ├── auth.py                 # 회원가입, 로그인, 로그아웃
    │   ├── main.py                 # 루트 리다이렉트, 대시보드
    │   ├── patients.py             # 환자 CRUD, 환자별 위험 요약
    │   ├── handover.py             # 인수인계 CRUD, 규칙/AI 위험도 저장
    │   ├── inbox.py                # 받은/보낸/위험 인수인계함
    │   └── audit.py                # 감사 로그 화면
    │
    ├── api/
    │   └── notifications.py        # 미확인 알림 Polling API
    │
    ├── services/
    │   ├── audit_service.py        # 감사 로그 기록
    │   ├── risk_service.py         # 규칙 기반 위험도 분석
    │   ├── risk_ai_service.py      # FastAPI AI 위험도 API 호출
    │   ├── handover_workflow_service.py
    │   └── notification_service.py
    │
    ├── middleware/
    │   └── rbac.py                 # 역할 기반 접근 제어 데코레이터
    │
    └── templates/
        ├── base.html
        ├── auth/
        ├── main/dashboard.html
        ├── patients/
        ├── handover/
        ├── inbox/
        └── audit/index.html
```

AI 서버는 별도 프로젝트로 분리되어 있습니다.

```text
clinical-text-risk-api/
├── app/main.py                     # FastAPI /predict 엔드포인트
├── models/risk_model/              # KLUE-BERT 기반 위험도 모델
├── data/handover_risk_dataset.csv
├── requirements.txt
└── README.md
```

---

## 4. 주요 기능

| 기능 | 설명 |
|---|---|
| 회원가입 / 로그인 | Flask-Login 기반 세션 인증, 비밀번호 해싱 |
| 역할 기반 접근 제어 | `nurse`, `charge_nurse`, `doctor`, `admin` 권한 분리 |
| 회원가입 역할 제한 | 가입 화면에는 간호사, 수간호사, 의사만 노출. 관리자 가입은 차단 |
| 환자 접근 범위 | 일반 간호사는 같은 상위 진료과/병동 그룹 환자만 조회 |
| 환자 관리 | 등록, 조회, 수정, 삭제, 검색, 병동/상태 필터 |
| 환자 목록 위험도 정렬 | 고위험+미확인 환자를 우선 노출 |
| 인수인계 작성 | 환자, 교대, 인계 대상, 내용, 바이탈, 투약, 처치 입력 |
| 받은 인수인계함 | 미확인/확인 완료 탭, 확인 메모 저장 |
| 보낸 인수인계함 | 상대방 확인 여부, 취소, 대상 변경 |
| 위험 인수인계함 | CRITICAL/HIGH/MEDIUM 위험도 별도 조회 |
| 알림 배지 | `/api/v1/notifications/unread-count`를 5초마다 Polling |
| 감사 로그 | 로그인, 조회, 생성, 수정, 삭제, 접근 거부 기록 |
| 규칙 기반 위험도 | 키워드, 바이탈, 반복 위험 기준 점수화 |
| AI 위험도 | `clinical-text-risk-api`의 `/predict` 결과 저장 |
| 대시보드 | 환자 수, 인수인계 수, 오늘 인수인계, 위험도/AI 통계 |

---

## 5. 역할별 권한

| 역할 | 설명 | 주요 권한 |
|---|---|---|
| `nurse` | 일반 간호사 | 환자 조회/등록, 인수인계 작성/조회 |
| `charge_nurse` | 수간호사 | nurse 권한 + 삭제 + 감사 로그 + 통계성 화면 접근 |
| `doctor` | 의사 | 환자/인수인계 조회, 통계 조회 |
| `admin` | 관리자 | 전체 권한 |

회원가입 화면에서는 `admin`을 선택할 수 없습니다. 관리자 계정은 DB에서 별도 생성하거나 기존 계정 role을 `admin`으로 변경해야 합니다.

수간호사 계정의 role 값은 반드시 `charge_nurse`여야 감사 로그와 관리 메뉴가 표시됩니다.

---

## 6. 인수인계 업무 흐름

```text
작성자
  ↓
인수인계 작성
  ↓
규칙 기반 위험도 분석 + AI 위험도 예측
  ↓
받는 사람의 받은 인수인계함에 표시
  ↓
받는 사람 확인 + 확인 메모
  ↓
보낸 인수인계함에서 확인 여부 추적
```

상태/확인 관련 필드:

| 필드 | 설명 |
|---|---|
| `handover_type` | ASSIGNMENT / NOTICE / ESCALATION |
| `status` | PENDING / ACKNOWLEDGED / CANCELLED / TRANSFERRED |
| `is_confirmed` | 수신자가 확인했는지 여부 |
| `confirmed_at` | 확인 시각 |
| `confirmed_by` | 확인자 ID |

---

## 7. 위험도 분석 구조

### 7.1 규칙 기반 위험도

`app/services/risk_service.py`에서 처리하고, 결과는 `risk_assessments` 테이블에 저장됩니다.

| 기준 | 예시 | 설명 |
|---|---|---|
| CRITICAL 키워드 | DNR, 심정지, CPR, 쇼크 | 즉시 확인이 필요한 문맥 |
| HIGH 키워드 | 낙상, 경련, 패혈증, 출혈 | 고위험 가능성이 높은 문맥 |
| MEDIUM 키워드 | 호흡곤란, 고열, 저혈압 | 관찰과 보고가 필요한 문맥 |
| 바이탈 이상 | BP, HR, BT, SpO2 | 수치 기반 위험 판단 |
| 복합 위험 | 여러 위험 카테고리 동시 감지 | 가중 점수 부여 |
| 반복 위험 | 같은 환자에게 24시간 내 유사 위험 반복 | 가중 점수 부여 |
| 부정 문맥 | “낙상 없음”, “호전”, “정상” | 불필요한 과탐지 완화 |

점수 기준:

| 점수 | 레벨 |
|---|---|
| 80~100 | CRITICAL |
| 60~79 | HIGH |
| 40~59 | MEDIUM |
| 0~39 | LOW |

### 7.2 AI 기반 위험도

`app/services/risk_ai_service.py`가 FastAPI 서버의 `/predict`를 호출합니다. 기본 URL은 다음과 같습니다.

```text
http://127.0.0.1:8000/predict
```

환경변수로 변경할 수 있습니다.

```env
RISK_API_URL=http://127.0.0.1:8001/predict
```

AI 서버 응답:

```json
{
  "risk_level": "HIGH",
  "confidence": 0.9876
}
```

Flask 앱 저장 위치:

| 값 | 저장 위치 |
|---|---|
| AI 위험도 라벨 | `handovers.risk_level` |
| AI confidence | `handovers.risk_score` |
| 규칙 기반 상세 결과 | `risk_assessments` |

화면에서는 예를 들어 다음처럼 표시됩니다.

```text
규칙 CRITICAL / 85점
AI HIGH / 0.99
```

---

## 8. 감사 로그

감사 로그는 `/audit/`에서 확인합니다. 사이드바의 `관리 > 감사 로그` 메뉴는 `admin`, `charge_nurse`에게만 표시됩니다.

기록 대상:

| 행위 | 예시 |
|---|---|
| `LOGIN` / `LOGIN_FAILED` / `LOGOUT` | 인증 이벤트 |
| `READ` | 환자 상세, 인수인계 상세 조회 |
| `CREATE` | 환자 등록, 인수인계 작성 |
| `UPDATE` | 환자 정보 수정, 인수인계 수정, 확인 처리 |
| `DELETE` | 환자 삭제, 인수인계 삭제 |
| `ACKNOWLEDGE` | 인수인계 확인 |
| `TRANSFER` | 인수인계 대상 변경 |
| `ACCESS_DENIED` | 권한 없는 접근 시도 |

감사 로그 기록 실패가 실제 업무 처리를 막지 않도록 `AuditService`에서 예외를 처리합니다.

---

## 9. REST API

현재 등록된 Flask API는 인수인계, 통계, 알림 기능을 제공합니다.

| 메서드 | URL | 설명 |
|---|---|---|
| GET | `/api/v1/handovers/` | 인수인계 목록 JSON 조회 |
| POST | `/api/v1/handovers/` | 인수인계 JSON 생성 |
| GET | `/api/v1/handovers/<id>` | 인수인계 상세 JSON 조회 |
| PUT | `/api/v1/handovers/<id>` | 인수인계 수정 |
| DELETE | `/api/v1/handovers/<id>` | 인수인계 삭제 |
| POST | `/api/v1/handovers/<id>/acknowledge` | 인수인계 확인 처리 |
| GET | `/api/v1/handovers/<id>/risk` | 규칙 기반 위험도 상세 조회 |
| GET | `/api/v1/stats/dashboard` | 대시보드 통계 JSON 조회 |
| GET | `/api/v1/stats/top-risk-patients` | 최근 고위험 환자 Top 10 |
| GET | `/api/v1/notifications/unread-count` | 미확인 인수인계 수, 고위험 수, 최신 미확인 정보 |

프론트엔드에서는 `base.html`에서 5초마다 호출해 사이드바/상단 배지를 갱신합니다.

---

## 10. DB 테이블 개요

| 테이블 | 설명 |
|---|---|
| `users` | 의료진 계정, 역할, 병동, 활성 상태, 마지막 로그인 |
| `patients` | 환자 정보, 병동, 진단, 알레르기, 특이사항 |
| `handovers` | 인수인계 본문, 바이탈, 투약, 처치, 상태, 확인 여부, AI 위험도 |
| `handover_acknowledgements` | 인수인계 확인자, 확인 시각, 확인 메모 |
| `risk_assessments` | 규칙 기반 위험도 분석 결과 |
| `audit_logs` | 데이터 접근 및 변경 감사 기록 |

기존 DB를 계속 사용하는 경우 `db.create_all()`만으로 새 컬럼이 자동 추가되지 않습니다. 기존 테이블에 컬럼이 없는 경우 마이그레이션 또는 수동 `ALTER TABLE`이 필요합니다.

대표 확장 컬럼:

```sql
ALTER TABLE users
ADD COLUMN license_number VARCHAR(50),
ADD COLUMN is_active BOOLEAN DEFAULT TRUE,
ADD COLUMN last_login_at DATETIME;

ALTER TABLE handovers
ADD COLUMN priority VARCHAR(10) DEFAULT 'NORMAL',
ADD COLUMN handover_type VARCHAR(20) DEFAULT 'NOTICE',
ADD COLUMN status VARCHAR(20) DEFAULT 'PENDING',
ADD COLUMN cancelled_at DATETIME,
ADD COLUMN cancelled_by INT,
ADD COLUMN transferred_at DATETIME,
ADD COLUMN transferred_to INT,
ADD COLUMN is_confirmed BOOLEAN DEFAULT FALSE,
ADD COLUMN confirmed_at DATETIME,
ADD COLUMN confirmed_by INT,
ADD COLUMN risk_level VARCHAR(20) DEFAULT 'UNKNOWN',
ADD COLUMN risk_score FLOAT DEFAULT 0;
```

---

## 11. 실행 방법

### 11.1 MySQL DB 생성

```sql
CREATE DATABASE nurse_handover
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

### 11.2 환경변수 설정

프로젝트 루트에 `.env` 파일을 생성합니다.

```env
SECRET_KEY=my-secret-key-12345

DB_USER=root
DB_PASSWORD=본인MySQL비밀번호
DB_HOST=localhost
DB_PORT=3306
DB_NAME=nurse_handover

FLASK_ENV=development
RISK_API_URL=http://127.0.0.1:8000/predict
```

### 11.3 Flask 서버 실행

```cmd
cd C:\Users\user\Desktop\nurse_handover

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt

python run.py
```

접속 주소:

```text
http://localhost:5000
```

### 11.4 AI 서버 실행

별도 터미널에서 실행합니다.

```cmd
cd C:\Users\user\Desktop\clinical-text-risk-api

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Swagger 문서:

```text
http://127.0.0.1:8000/docs
```

테스트 요청:

```json
{
  "text": "환자 BP 70/40, SpO2 86%, 의식 저하 있으며 쇼크 의심되어 즉시 보고 필요함."
}
```

응답 예시:

```json
{
  "risk_level": "HIGH",
  "confidence": 0.9876
}
```

---

## 12. 현재 등록 라우트

```text
/
/dashboard
/auth/register
/auth/login
/auth/logout
/patients/
/patients/create
/patients/<id>
/patients/<id>/edit
/patients/<id>/delete
/handovers/
/handovers/create
/handovers/create/<patient_id>
/handovers/<id>
/handovers/<id>/edit
/handovers/<id>/delete
/handovers/check-keywords
/inbox/
/inbox/sent
/inbox/danger
/inbox/<id>/acknowledge
/inbox/<id>/cancel
/inbox/<id>/transfer
/audit/
/api/v1/handovers/
/api/v1/handovers/<id>
/api/v1/handovers/<id>/acknowledge
/api/v1/handovers/<id>/risk
/api/v1/stats/dashboard
/api/v1/stats/top-risk-patients
/api/v1/notifications/unread-count
```

---

## 13. 기술 스택

| 구분 | 기술 |
|---|---|
| Backend | Flask 3.x |
| ORM | Flask-SQLAlchemy |
| Database | MySQL |
| DB Driver | PyMySQL |
| Auth | Flask-Login |
| Frontend | Bootstrap 5, Bootstrap Icons, Jinja2 |
| Env | python-dotenv |
| HTTP Client | requests |
| AI API | FastAPI, Uvicorn |
| AI/NLP | PyTorch, Transformers, KLUE-BERT |

---

## 14. 자주 발생한 문제와 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| `python` 명령어를 찾을 수 없음 | PATH 미설정 | Python 재설치 시 Add to PATH 체크 |
| `ModuleNotFoundError: flask` | venv 미활성화 또는 패키지 미설치 | `venv\Scripts\activate` 후 `pip install -r requirements.txt` |
| `ModuleNotFoundError: requests` | Flask 앱 의존성 누락 | `pip install -r requirements.txt` |
| `Access denied for user 'root'` | DB 비밀번호 오류 | `.env`의 `DB_PASSWORD` 확인 |
| `Unknown database 'nurse_handover'` | DB 미생성 | MySQL에서 DB 생성 |
| `Unknown column ...` | 기존 DB에 새 컬럼 없음 | 마이그레이션 또는 수동 `ALTER TABLE` |
| 감사 로그 메뉴가 안 보임 | role 값 불일치 | `admin` 또는 `charge_nurse`인지 확인 |
| 받은함/알림이 안 보임 | Blueprint 또는 JS 연결 문제 | `/inbox/`, `/api/v1/notifications/unread-count` 확인 |
| REST API가 404 | API Blueprint 미등록 | `/api/v1/handovers/`, `/api/v1/stats/dashboard` 라우트 확인 |
| AI 위험도가 `UNKNOWN` | AI 서버 미실행 또는 URL 불일치 | `clinical-text-risk-api` 실행, `RISK_API_URL` 확인 |
| `/predict` Method Not Allowed | 브라우저 GET 요청 | `/docs`에서 POST로 테스트 |
| 포트 5000/8000 사용 중 | 기존 서버 실행 중 | 기존 프로세스 종료 또는 포트 변경 |

---

## 15. 테스트 문장

### LOW

```text
환자 활력징후 안정적이며 통증 호소 없음. 식사 가능하고 보행 가능함.
```

### MEDIUM

```text
환자 어지러움 호소하며 낙상 위험 있어 침상 안정 유지 중. BP 95/60으로 관찰 필요함.
```

### HIGH

```text
환자 BP 70/40, SpO2 86%, 의식 저하 있으며 쇼크 의심되어 즉시 보고 필요함.
```

---

## 16. 포트폴리오 설명 문장

간호 인수인계 데이터를 기반으로 환자 상태와 주요 위험 문맥을 관리하는 병동 인수인계 플랫폼을 구현했습니다. Flask와 MySQL을 활용해 환자 관리, 인수인계 작성, 수신 확인, 알림, 감사 로그, 대시보드 기능을 구성했고, FastAPI로 분리한 AI 서버에서 KLUE-BERT 기반 임상 텍스트 위험도 분류 모델을 호출하도록 설계했습니다. 규칙 기반 위험도와 AI 위험도를 함께 표시해 설명 가능성과 문맥 기반 예측 기능을 동시에 반영했습니다.

---

## 17. 향후 개선 방향

| 개선 항목 | 설명 |
|---|---|
| DB 마이그레이션 | Flask-Migrate 도입 |
| 테스트 코드 | 서비스/라우트 단위 테스트 추가 |
| WebSocket / SSE | Polling 알림을 실시간 구조로 전환 |
| AI 모델 평가 | Confusion Matrix, F1, threshold 조정 |
| Docker 구성 | Flask, FastAPI, MySQL 실행 환경 통합 |
| 운영 보안 | 감사 로그 보존 정책, 접근 통제, 비식별화 강화 |

---

## 18. 현재 병합 기준

현재 `main` 작업트리는 `main`에 있던 받은함/알림/워크플로우/run.py 흐름을 유지하면서, `suhyoung319` 브랜치의 감사 로그, RBAC, 규칙 기반 위험도, 확장 모델, 환자 위험도 UX, AI 위험도 연동을 반영한 상태입니다.
