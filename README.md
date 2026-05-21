# 🏥 병동 인수인계 시스템 (Ward Handover Platform)

Flask + MySQL 기반 병동 인수인계 웹 플랫폼이다. 단순 CRUD를 넘어 실제 병동 인수인계 흐름에 필요한 수신 확인, 대상 변경, 위험도 분류, 감사 로그, 알림, 대시보드 기능을 구현했다. 추가로 FastAPI 기반 AI 서버를 분리하고, Colab에서 재학습한 KLUE-BERT 임상 텍스트 위험도 분류 모델을 연동해 인수인계 문장의 위험도를 자동 예측하도록 구성했다.

> 포트폴리오 목적의 로컬 실행 프로젝트이다. 실제 의료 현장 적용 전에는 개인정보보호, 보안, 의료기관 내부 규정, 임상 검증 절차가 필요하다.

---

## 1. 프로젝트 핵심 요약

```text
Flask 병동 인수인계 시스템
+ MySQL 데이터 저장
+ 역할 기반 접근 제어(RBAC)
+ 받은/보낸/위험 인수인계함
+ 확인 처리 및 확인 메모
+ 감사 로그
+ Polling 기반 알림 배지
+ 규칙 기반 위험도 분석
+ KLUE-BERT 기반 AI 위험도 분석
+ FastAPI /predict 서버 분리
+ 대시보드 및 상세 화면 위험도 표시
```

핵심 특징은 **규칙 기반 위험도 분석**과 **AI 기반 위험도 분석**을 함께 표시하는 구조다. 규칙 기반 분석은 명확한 키워드와 바이탈 기준으로 판단하고, AI 분석은 인수인계 문장 전체 맥락을 기반으로 LOW / MEDIUM / HIGH 위험도를 예측한다.

---

## 2. 전체 아키텍처

```text
사용자
  ↓
Flask Web App
  ↓
인수인계 작성 / 조회 / 확인 / 수정
  ↓
MySQL 저장
  ↓
[1] risk_service.py      → 규칙 기반 위험도 분석
[2] risk_ai_service.py   → FastAPI /predict 호출
                              ↓
                         KLUE-BERT risk_model
                              ↓
                         AI 위험도 반환
  ↓
handovers.risk_level / risk_score 저장
  ↓
대시보드·목록·상세 화면 표시
```

---

## 3. 프로젝트 구조

```text
nurse_handover/
├── run.py                          # Flask 실행 진입점
├── config.py                       # 환경변수 로드, DB URI, 위험 키워드 설정
├── .env.example                    # 환경변수 예시
├── .gitignore
├── requirements.txt
│
└── app/
    ├── __init__.py                 # Flask App Factory, Blueprint 등록
    ├── models.py                   # User, Patient, Handover, AuditLog, RiskAssessment, HandoverAck
    ├── utils.py                    # 공통 유틸
    │
    ├── routes/
    │   ├── auth.py                 # 회원가입, 로그인, 로그아웃
    │   ├── main.py                 # 메인, 대시보드
    │   ├── patients.py             # 환자 CRUD
    │   ├── handover.py             # 인수인계 CRUD, AI 위험도 저장
    │   ├── inbox.py                # 받은/보낸/위험 인수인계함
    │   └── audit.py                # 감사 로그 화면
    │
    ├── api/
    │   ├── handover.py             # 인수인계 REST API
    │   ├── stats.py                # 통계 API
    │   └── notifications.py        # 미확인 알림 API
    │
    ├── services/
    │   ├── audit_service.py        # 감사 로그 기록
    │   ├── risk_service.py         # 규칙 기반 위험도 분석
    │   ├── risk_ai_service.py      # FastAPI AI 위험도 API 호출
    │   ├── handover_workflow_service.py
    │   └── notification_service.py
    │
    ├── middleware/
    │   └── rbac.py                 # 역할 기반 접근 제어
    │
    └── templates/
        ├── base.html
        ├── auth/
        ├── main/dashboard.html
        ├── patients/
        ├── handover/
        │   ├── index.html
        │   ├── detail.html
        │   └── form.html
        ├── inbox/
        │   ├── index.html
        │   ├── sent.html
        │   ├── danger.html
        │   └── transfer.html
        └── audit/index.html
```

AI 서버는 별도 프로젝트로 분리한다.

```text
clinical_text_risk_api/
├── main.py                         # FastAPI /predict 엔드포인트
├── risk_model/                     # Colab에서 학습한 KLUE-BERT 모델
├── data/
│   └── handover_risk_dataset.csv   # 학습 데이터셋
└── requirements.txt
```

---

## 4. 주요 기능

| 기능 | 설명 |
|---|---|
| 회원가입 / 로그인 | Flask-Login 기반 세션 인증 |
| 역할 기반 접근 제어 | nurse, charge_nurse, doctor, admin 역할별 권한 분리 |
| 환자 관리 | 환자 등록, 조회, 수정, 삭제 |
| 인수인계 작성 | 환자, 근무조, 바이탈, 투약, 처치, 인수 대상 입력 |
| 받은 인수인계함 | 미확인 / 확인 완료 탭 분리 |
| 보낸 인수인계함 | 수신자 확인 여부 추적, 대상 변경, 취소 |
| 인수인계 확인 | 확인 완료 처리 및 확인 메모 저장 |
| 위험 인수인계함 | 고위험 인수인계 별도 조회 |
| 규칙 기반 위험도 | 키워드, 바이탈, 반복 위험 기준 점수화 |
| AI 기반 위험도 | KLUE-BERT 모델로 LOW / MEDIUM / HIGH 예측 |
| 위험도 저장 | `handovers.risk_level`, `handovers.risk_score` 저장 |
| 대시보드 | 환자 수, 인수인계 수, 미확인 수, 위험도 통계 표시 |
| 알림 배지 | 미확인 인수인계 수 Polling 갱신 |
| 감사 로그 | 로그인, 조회, 생성, 수정, 삭제 등 주요 행위 기록 |
| REST API | 인수인계, 통계, 알림 관련 JSON API 제공 |

---

## 5. 위험도 분석 구조

### 5.1 규칙 기반 위험도 분석

`risk_service.py`에서 처리한다.

| 기준 | 예시 | 설명 |
|---|---|---|
| CRITICAL 키워드 | DNR, 심정지, 쇼크, 의식저하 | 즉시 확인이 필요한 위험 문맥 |
| HIGH 키워드 | 낙상, 경련, SpO2 저하 | 고위험 가능성이 높은 문맥 |
| MEDIUM 키워드 | 어지러움, 호흡곤란, 발열 | 관찰과 보고가 필요한 문맥 |
| 바이탈 이상 | BP 저하, HR 증가, SpO2 감소 | 수치 기반 위험 판단 |
| 복합 위험 | 여러 위험 요소 동시 발생 | 가중 점수 부여 |
| 부정 문맥 | “낙상 없음”, “호흡곤란 없음” | 불필요한 과탐지 완화 |

규칙 기반 결과는 화면에서 다음처럼 표시된다.

```text
규칙 CRITICAL
규칙 HIGH
규칙 MEDIUM
규칙 LOW
```

### 5.2 AI 기반 위험도 분석

`risk_ai_service.py`가 FastAPI 서버의 `/predict`를 호출한다. FastAPI 서버는 Colab에서 학습한 KLUE-BERT 모델을 사용해 인수인계 문장의 위험도를 예측한다.

```text
인수인계 문장
  ↓
Flask risk_ai_service.py
  ↓
FastAPI /predict
  ↓
KLUE-BERT Sequence Classification
  ↓
LOW / MEDIUM / HIGH + confidence 반환
  ↓
handovers.risk_level / risk_score 저장
```

화면 표시 예시는 다음과 같다.

```text
규칙 CRITICAL    AI HIGH / 0.99
```

이 구조는 룰 기반 판단의 설명 가능성과 AI 기반 문맥 판단을 함께 보여주기 위한 설계다.

---

## 6. AI 모델 학습 과정

### 6.1 데이터셋

학습 데이터는 병동 인수인계 스타일의 합성 문장으로 구성한다.

| 컬럼 | 설명 |
|---|---|
| `text` | 인수인계 문장 |
| `label` | LOW, MEDIUM, HIGH |

예시:

```csv
text,label
"환자 활력징후 안정적이며 통증 호소 없음. 식사 가능하고 보행 가능함.",LOW
"환자 어지러움 호소하며 낙상 위험 있어 침상 안정 유지 중. BP 95/60으로 관찰 필요함.",MEDIUM
"환자 BP 70/40, SpO2 86%, 의식 저하 있으며 쇼크 의심되어 즉시 보고 필요함.",HIGH
```

### 6.2 Colab 학습 흐름

```text
Google Drive 연결
→ handover_risk_dataset.csv 로드
→ LOW / MEDIUM / HIGH 숫자 라벨 변환
→ train/test split
→ KLUE-BERT tokenizer 적용
→ AutoModelForSequenceClassification 로드
→ Trainer 학습
→ validation accuracy / f1 확인
→ risk_model 저장
→ risk_model.zip 다운로드
→ FastAPI risk_model 폴더 교체
```

라벨 매핑:

```python
label_map = {
    "LOW": 0,
    "MEDIUM": 1,
    "HIGH": 2
}

df["label"] = df["label"].map(label_map)
```

---

## 7. 실행 방법

### 7.1 MySQL DB 생성

```sql
CREATE DATABASE nurse_handover
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

### 7.2 환경변수 설정

`.env.example`을 복사해 `.env`로 저장한다.

```env
SECRET_KEY=your-secret-key-here

DB_USER=root
DB_PASSWORD=본인MySQL비밀번호
DB_HOST=localhost
DB_PORT=3306
DB_NAME=nurse_handover

FLASK_ENV=development
```

### 7.3 Flask 서버 실행

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

접속 주소:

```text
http://localhost:5000
```

### 7.4 FastAPI AI 서버 실행

```powershell
cd clinical_text_risk_api
venv\Scripts\Activate.ps1
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Swagger 테스트:

```text
http://127.0.0.1:8000/docs
```

예측 API:

```text
POST http://127.0.0.1:8000/predict
```

요청 예시:

```json
{
  "text": "환자 BP 70/40, SpO2 86%, 의식 저하 있으며 쇼크 의심되어 즉시 보고 필요함."
}
```

응답 예시:

```json
{
  "risk_level": "HIGH",
  "risk_score": 0.99
}
```

---

## 8. DB 테이블 개요

| 테이블 | 설명 |
|---|---|
| `users` | 의료진 계정, 역할, 병동, 활성 상태 |
| `patients` | 환자 정보, 병동, 진단, 알레르기, 특이사항 |
| `handovers` | 인수인계 본문, 바이탈, 투약, 처치, 상태, AI 위험도 |
| `risk_assessments` | 규칙 기반 위험도 분석 결과 |
| `handover_acknowledgements` | 인수인계 확인자, 확인 시각, 확인 메모 |
| `audit_logs` | 데이터 접근 및 변경 감사 기록 |

AI 연동을 위해 `handovers` 테이블에 다음 컬럼을 사용한다.

```sql
ALTER TABLE handovers
ADD COLUMN risk_level VARCHAR(20) DEFAULT 'UNKNOWN',
ADD COLUMN risk_score FLOAT DEFAULT 0;
```

SQLAlchemy 모델 필드:

```python
risk_level = db.Column(db.String(20), default="UNKNOWN")
risk_score = db.Column(db.Float, default=0.0)
```

---

## 9. 역할별 권한

| 역할 | 설명 | 주요 권한 |
|---|---|---|
| `nurse` | 일반 간호사 | 인수인계 작성·조회, 본인 병동 환자 조회 |
| `charge_nurse` | 수간호사 | nurse 권한 + 삭제 + 감사 로그 + 통계 |
| `doctor` | 의사 | 환자·인수인계 조회, 통계 조회 |
| `admin` | 관리자 | 전체 권한 |

회원가입 시 기본 역할은 `nurse`다.

---

## 10. REST API 엔드포인트

### Flask API

| 메서드 | URL | 설명 |
|---|---|---|
| GET | `/api/v1/handovers/` | 인수인계 목록 조회 |
| POST | `/api/v1/handovers/` | 인수인계 생성 |
| GET | `/api/v1/handovers/<id>` | 인수인계 상세 조회 |
| PUT | `/api/v1/handovers/<id>` | 인수인계 수정 |
| DELETE | `/api/v1/handovers/<id>` | 인수인계 삭제 |
| GET | `/api/v1/handovers/<id>/risk` | 규칙 기반 위험도 상세 조회 |
| POST | `/api/v1/handovers/<id>/acknowledge` | 인수인계 확인 처리 |
| GET | `/api/v1/stats/dashboard` | 대시보드 통계 |
| GET | `/api/v1/stats/top-risk-patients` | 고위험 환자 Top 10 |
| GET | `/api/v1/notifications/unread-count` | 미확인 인수인계 요약 |

### AI API

| 메서드 | URL | 설명 |
|---|---|---|
| POST | `/predict` | 임상 텍스트 위험도 예측 |
| GET | `/docs` | Swagger 테스트 화면 |

---

## 11. 기술 스택

| 구분 | 기술 |
|---|---|
| Backend | Flask 3.x |
| ORM | Flask-SQLAlchemy |
| Database | MySQL |
| DB Driver | PyMySQL |
| Auth | Flask-Login |
| Frontend | Bootstrap 5, Bootstrap Icons, Jinja2 |
| REST API | Flask Blueprint |
| AI API | FastAPI, Uvicorn |
| NLP Model | KLUE-BERT Sequence Classification |
| ML Framework | PyTorch, Transformers |
| Training | Google Colab |
| Environment | python-dotenv |

---

## 12. 핵심 설계 결정

### 12.1 Flask와 FastAPI 분리

Flask는 병동 인수인계 웹 기능을 담당하고, FastAPI는 AI 추론 서버로 분리했다. 이를 통해 웹 서비스와 AI 모델 추론 책임을 분리하고, 모델 교체와 재학습 결과 반영을 쉽게 만들었다.

### 12.2 규칙 기반 + AI 기반 이중 위험도 평가

의료 텍스트는 단순 AI 예측만으로 판단하기 어렵다. 따라서 키워드와 바이탈 기반 규칙 분석을 함께 사용해 설명 가능성을 확보했다.

### 12.3 받은/보낸 인수인계함 분리

실무 흐름에 맞춰 받은 인수인계, 보낸 인수인계, 위험 인수인계 화면을 분리했다. 받은 인수인계함은 미확인 항목을 우선 보여주고, 보낸 인수인계함은 상대방 확인 여부를 추적할 수 있게 했다.

### 12.4 감사 로그

환자 및 인수인계 데이터 접근과 변경 행위를 감사 로그로 기록한다. 감사 로그 실패가 핵심 업무 흐름을 막지 않도록 예외 처리를 적용했다.

### 12.5 Polling 기반 알림

5초마다 미확인 인수인계 수를 조회해 알림 배지를 갱신한다. 추후 WebSocket 또는 SSE로 확장 가능하다.

---

## 13. 테스트 문장

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

## 14. 자주 발생한 문제와 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| `Could not import module "main"` | uvicorn 실행 위치 오류 | `main.py` 위치에서 실행 |
| `/predict` 접속 시 Method Not Allowed | 브라우저 GET 요청 | `/docs`에서 POST로 테스트 |
| `risk_score`가 0으로 저장됨 | API 응답 key 불일치 | `risk_score` 또는 `confidence` 매핑 확인 |
| `Unknown column 'risk_level'` | DB 컬럼 미추가 | `ALTER TABLE handovers ...` 실행 |
| `AttributeError: Handover has no attribute risk_level` | 모델 필드 미추가 | `models.py` 필드 추가 |
| `Access denied for user 'root'` | DB 비밀번호 오류 | `.env`의 `DB_PASSWORD` 확인 |
| `Unknown database 'nurse_handover'` | DB 미생성 | MySQL에서 DB 생성 |
| 알림 배지가 안 뜸 | Polling API 오류 | `/api/v1/notifications/unread-count` 확인 |
| 포트 5000/8000 사용 중 | 기존 서버 실행 중 | 기존 프로세스 종료 또는 포트 변경 |

---

## 15. 포트폴리오 설명 문장

간호 인수인계 데이터를 기반으로 환자 상태와 주요 위험 문맥을 관리하는 병동 인수인계 플랫폼을 구현했다. Flask와 MySQL을 활용해 환자 관리, 인수인계 작성, 수신 확인, 감사 로그, 대시보드 기능을 구성했고, FastAPI로 분리한 AI 서버에서 KLUE-BERT 기반 임상 텍스트 위험도 분류 모델을 호출하도록 설계했다. 규칙 기반 위험도와 AI 위험도를 함께 표시해 설명 가능성과 문맥 기반 예측 기능을 동시에 반영했다.

---

## 16. 향후 개선 방향

| 개선 항목 | 설명 |
|---|---|
| 데이터셋 확장 | 실제 병동 표현을 반영한 LOW / MEDIUM / HIGH 데이터 추가 |
| Confusion Matrix 분석 | HIGH 위험군을 LOW로 오분류하는지 확인 |
| Threshold 조정 | HIGH 민감도를 높이는 기준값 조정 |
| WebSocket / SSE | 실시간 알림 구조로 확장 |
| 테스트 코드 추가 | 주요 서비스 로직 단위 테스트 작성 |
| Docker 구성 | Flask, FastAPI, MySQL 실행 환경 통합 |

---

## 17. 프로젝트 의의

이 프로젝트는 간호 인수인계 업무를 단순 게시판 형태로 구현한 것이 아니라, 실제 병동 업무 흐름에 맞춰 수신 확인, 위험도 분류, 알림, 감사 로그, AI 예측을 결합한 백엔드 중심 프로젝트다. 특히 Flask 웹 서비스와 FastAPI AI 서버를 분리하고, Colab에서 재학습한 KLUE-BERT 모델을 실제 웹 화면과 DB 저장 흐름에 연결했다는 점에서 포트폴리오용 차별성이 있다.
