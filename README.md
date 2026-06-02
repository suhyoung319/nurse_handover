# 병동 인수인계 시스템

Flask + MySQL 기반 병동 인수인계 웹 애플리케이션입니다. 환자 관리, 인수인계 작성, 받은/보낸 인수인계함, 확인 처리, 위험도 분석, 역할 기반 접근 제어, 감사 로그를 제공합니다.

이 프로젝트는 Windows 로컬 실행을 기준으로 구성되어 있습니다. 별도 프로젝트인 `clinical-text-risk-api`의 FastAPI 서버를 함께 실행하면 KLUE-BERT 기반 AI 위험도도 인수인계 화면에 저장/표시됩니다.

---

## 주요 기능

| 기능 | 설명 |
|---|---|
| 회원가입 / 로그인 | Flask-Login 세션 인증, Werkzeug 비밀번호 해싱 |
| 역할 기반 권한 | `nurse`, `charge_nurse`, `doctor`, `admin` 역할별 권한 분리 |
| 환자 관리 | 환자 등록, 조회, 수정, 삭제, 검색, 필터 |
| 환자 접근 범위 | 일반 간호사는 같은 상위 진료과/병동 그룹 환자만 조회 |
| 인수인계 작성 | 환자, 교대, 인계 대상, 내용, 활력징후, 투약, 처치 입력 |
| 받은 인수인계함 | 미확인 / 확인 완료 인수인계 분리 조회 |
| 보낸 인수인계함 | 상대방 확인 여부 확인, 취소, 대상 변경 |
| 인수인계 확인 | 확인 완료 처리 및 확인 메모 저장 |
| 위험 인수인계 | 위험도 높은 인수인계를 별도 조회 |
| 규칙 기반 위험도 분석 | 위험 키워드, 바이탈 이상, 반복 위험을 점수화 |
| AI 위험도 분석 | `clinical-text-risk-api`의 `/predict` 호출 결과를 저장 |
| 알림 배지 | 미확인 인수인계 수 조회 |
| 감사 로그 | 로그인, 조회, 생성, 수정, 삭제, 접근 거부 기록 |

---

## 프로젝트 구조

```text
nurse_handover/
├── run.py
├── config.py
├── requirements.txt
├── README.md
│
└── app/
    ├── __init__.py
    ├── models.py
    ├── utils.py
    │
    ├── routes/
    │   ├── auth.py
    │   ├── main.py
    │   ├── patients.py
    │   ├── handover.py
    │   ├── inbox.py
    │   └── audit.py
    │
    ├── services/
    │   ├── audit_service.py
    │   ├── risk_service.py
    │   ├── handover_workflow_service.py
    │   └── notification_service.py
    │
    ├── middleware/
    │   └── rbac.py
    │
    ├── api/
    │   └── notifications.py
    │
    └── templates/
        ├── base.html
        ├── auth/
        ├── main/
        ├── patients/
        ├── handover/
        ├── inbox/
        └── audit/
```

---

## 역할별 권한

| 역할 | 설명 | 주요 권한 |
|---|---|---|
| `nurse` | 일반 간호사 | 환자 조회/등록, 인수인계 작성/조회 |
| `charge_nurse` | 수간호사 | nurse 권한 + 삭제/감사 로그/통계성 화면 접근 |
| `doctor` | 의사 | 환자/인수인계 조회, 통계 조회 |
| `admin` | 관리자 | 전체 권한 |

수간호사 계정의 role 값은 반드시 `charge_nurse`여야 합니다.

---

## 감사 로그

감사 로그는 `/audit/`에서 확인합니다. 사이드바의 `관리 > 감사 로그` 메뉴는 `admin`, `charge_nurse`에게만 표시됩니다.

기록 대상:

| 행위 | 예시 |
|---|---|
| `LOGIN` / `LOGIN_FAILED` / `LOGOUT` | 인증 이벤트 |
| `READ` | 환자 상세, 인수인계 상세 조회 |
| `CREATE` | 환자 등록, 인수인계 작성 |
| `UPDATE` | 환자 정보 수정, 인수인계 수정, 확인 처리 |
| `DELETE` | 환자 삭제, 인수인계 삭제 |
| `ACCESS_DENIED` | 권한 없는 접근 시도 |

감사 로그 기록 실패가 실제 업무 처리를 막지 않도록 `AuditService`에서 예외를 잡습니다.

---

## 위험도 분석

위험도는 두 갈래로 관리합니다.

| 구분 | 저장 위치 | 설명 |
|---|---|---|
| 규칙 기반 위험도 | `risk_assessments` | 키워드, 바이탈, 반복 위험 기준 점수 |
| AI 위험도 | `handovers.risk_level`, `handovers.risk_score` | FastAPI AI 서버의 예측 라벨과 confidence |

`app/services/risk_service.py`에서 규칙 기반 위험도 분석을 수행합니다.

분석 기준:

| 기준 | 설명 |
|---|---|
| 위험 키워드 | 심정지, CPR, DNR, 낙상, 경련, 쇼크 등 |
| 바이탈 이상 | BP, HR, BT, SpO2 텍스트 수치 분석 |
| 복합 위험 | 여러 위험 카테고리 동시 감지 시 가산 |
| 반복 위험 | 같은 환자에게 24시간 내 유사 위험 반복 시 가산 |
| 부정 문맥 | “낙상 없음”, “정상”, “호전” 등은 일부 감점 |

규칙 기반 분석 결과는 `risk_assessments` 테이블에 저장되고, 인수인계의 `has_danger`, `danger_keywords`, `priority`에도 반영됩니다.

AI 위험도는 `app/services/risk_ai_service.py`가 `RISK_API_URL`의 `/predict` 서버를 호출해 저장합니다. 기본 주소는 다음과 같습니다.

```text
http://127.0.0.1:8000/predict
```

환경변수로 변경할 수 있습니다.

```env
RISK_API_URL=http://127.0.0.1:8001/predict
```

AI 서버 응답 형식:

```json
{
  "risk_level": "HIGH",
  "confidence": 0.9876
}
```

---

## DB 테이블

| 테이블 | 설명 |
|---|---|
| `users` | 계정, 역할, 병동, 활성 상태 |
| `patients` | 환자 정보 |
| `handovers` | 인수인계 본문, 상태, 확인 여부, 위험도 요약 |
| `handover_acknowledgements` | 인수인계 확인 이력과 메모 |
| `risk_assessments` | 규칙 기반 위험도 분석 상세 결과 |
| `audit_logs` | 데이터 접근 및 변경 감사 기록 |

주의: `db.create_all()`은 새 테이블은 만들 수 있지만, 기존 테이블에 새 컬럼을 자동 추가하지 않습니다. 이미 DB를 만들어 사용 중이었다면 모델 확장 후 마이그레이션 또는 수동 `ALTER TABLE`이 필요할 수 있습니다.

---

## 실행 방법

### 1. Python 설치

Python 3.11 이상을 설치하고 PATH에 등록합니다.

```cmd
python --version
```

### 2. MySQL DB 생성

MySQL Workbench 또는 CLI에서 DB를 생성합니다.

```sql
CREATE DATABASE nurse_handover
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

### 3. 환경변수 설정

프로젝트 루트에 `.env` 파일을 생성합니다.

```env
SECRET_KEY=my-secret-key-12345

DB_USER=root
DB_PASSWORD=본인MySQL비밀번호
DB_HOST=localhost
DB_PORT=3306
DB_NAME=nurse_handover

FLASK_ENV=development
```

### 4. 패키지 설치 및 서버 실행

```cmd
cd C:\path\to\nurse_handover

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt

python run.py
```

브라우저에서 접속합니다.

```text
http://localhost:5000
```

### 5. AI 서버 실행

`nurse_handover`와 같은 바탕화면 경로에 있는 `clinical-text-risk-api` 프로젝트를 별도 터미널에서 실행합니다.

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

---

## 기술 스택

| 구분 | 기술 |
|---|---|
| Backend | Flask 3.x |
| ORM | Flask-SQLAlchemy |
| DB | MySQL |
| DB Driver | PyMySQL |
| Auth | Flask-Login |
| Frontend | Bootstrap 5, Bootstrap Icons, Jinja2 |
| Env | python-dotenv |

---

## 자주 겪는 문제

| 증상 | 원인 | 해결 |
|---|---|---|
| `python` 명령어를 찾을 수 없음 | PATH 미설정 | Python 재설치 시 Add to PATH 체크 |
| `ModuleNotFoundError: flask` | 패키지 미설치 또는 venv 미활성화 | `venv\Scripts\activate` 후 `pip install -r requirements.txt` |
| `Access denied for user 'root'` | DB 비밀번호 오류 | `.env`의 `DB_PASSWORD` 확인 |
| `Unknown database 'nurse_handover'` | DB 미생성 | MySQL에서 DB 생성 |
| `Unknown column ...` | 기존 DB에 새 컬럼 없음 | 마이그레이션 또는 수동 `ALTER TABLE` 필요 |
| 감사 로그 메뉴가 안 보임 | role 값 불일치 | `admin` 또는 `charge_nurse`인지 확인 |
| 포트 5000 사용 중 | 기존 서버 실행 중 | 기존 프로세스 종료 또는 `run.py` 포트 변경 |

---

## 현재 병합 기준

현재 코드는 `main`의 받은함/워크플로우/실행 편의 파일을 유지하면서, `suhyoung319` 브랜치의 감사 로그, RBAC, 위험도 분석, 확장 모델을 선별 반영한 상태입니다.
