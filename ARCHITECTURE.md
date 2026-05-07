# 🏥 병동 인수인계 플랫폼 — 고도화 설계 가이드
## (시니어 백엔드 관점 / 의료 IT 아키텍트 관점)

---

## 1. 현재 프로젝트의 부족한 점 분석

### ❌ 구조적 문제
| 문제 | 현재 상태 | 리스크 |
|------|-----------|--------|
| **비즈니스 로직이 route에 혼재** | `patients.py`가 DB조회+검증+렌더링을 한 파일에서 수행 | 테스트 불가, 유지보수 어려움 |
| **RBAC 없음** | role 컬럼만 있고 권한 제어 코드 없음 | 간호사가 관리자 기능 접근 가능 |
| **감사 로그 없음** | 누가 언제 뭘 수정했는지 추적 불가 | 의료사고 시 책임 추적 불가 |
| **API 없음** | HTML만 반환, REST 구조 없음 | 모바일 앱, 외부 시스템 연동 불가 |
| **에러 핸들링 없음** | DB오류시 500 그대로 노출 | 환자 정보 유출 위험 |

### ❌ 의료 시스템 관점 문제
| 문제 | 설명 |
|------|------|
| **위험도 분석이 단순 키워드 매칭** | "위험" 단어가 있으면 무조건 위험 — 오탐률 높음 |
| **인수인계 확인(Acknowledge) 없음** | 인계자가 읽었는지 확인 불가 |
| **환자 이력 추적 미흡** | 특정 환자의 상태 변화 추이 파악 불가 |
| **통계/분석 없음** | 병동별 위험 발생 패턴 파악 불가 |

---

## 2. 우선순위별 추가 기능

```
Priority 1 (즉시) : Audit Log + RBAC
  → 의료 시스템의 가장 기본 요건
  → 없으면 실제 병원 도입 불가

Priority 2 (단기) : 위험도 자동 분석 고도화
  → 단순 키워드→ 가중치 기반 점수 시스템
  → 복합 조건 판단 (바이탈 + 키워드 + 빈도)

Priority 3 (중기) : REST API + Swagger
  → 모바일 앱 연동 준비
  → 포트폴리오 어필용

Priority 4 (장기) : 통계 대시보드
  → 병원 관리자용 리포팅
```

---

## 3. 데이터베이스 구조 제안

### 새로 추가할 테이블

```sql
-- 감사 로그 (모든 데이터 변경 추적)
CREATE TABLE audit_logs (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    user_id     INT,                          -- 행위자
    action      VARCHAR(20) NOT NULL,         -- CREATE/UPDATE/DELETE/VIEW
    resource    VARCHAR(50) NOT NULL,         -- 'handover', 'patient', 'user'
    resource_id INT,                          -- 대상 레코드 ID
    old_value   JSON,                         -- 변경 전 값
    new_value   JSON,                         -- 변경 후 값
    ip_address  VARCHAR(45),                  -- 접속 IP
    user_agent  VARCHAR(500),                 -- 브라우저 정보
    created_at  DATETIME DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 위험도 분석 결과 (인수인계별 상세 분석)
CREATE TABLE risk_assessments (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    handover_id     INT UNIQUE NOT NULL,
    risk_score      INT DEFAULT 0,             -- 0~100점
    risk_level      VARCHAR(20),               -- CRITICAL/HIGH/MEDIUM/LOW
    triggered_rules JSON,                      -- 어떤 규칙이 발동됐는지
    vital_flag      BOOLEAN DEFAULT FALSE,     -- 바이탈 이상
    keyword_flag    BOOLEAN DEFAULT FALSE,     -- 키워드 감지
    frequency_flag  BOOLEAN DEFAULT FALSE,     -- 동일 환자 반복 위험
    created_at      DATETIME DEFAULT NOW(),
    FOREIGN KEY (handover_id) REFERENCES handovers(id)
);

-- 인수인계 확인 (읽음 처리)
CREATE TABLE handover_acknowledgements (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    handover_id INT NOT NULL,
    user_id     INT NOT NULL,
    ack_at      DATETIME DEFAULT NOW(),
    note        TEXT,                          -- 확인 메모
    UNIQUE KEY unique_ack (handover_id, user_id),
    FOREIGN KEY (handover_id) REFERENCES handovers(id),
    FOREIGN KEY (user_id)     REFERENCES users(id)
);

-- RBAC: 역할별 권한 정의
CREATE TABLE permissions (
    id       INT PRIMARY KEY AUTO_INCREMENT,
    role     VARCHAR(20) NOT NULL,             -- nurse/doctor/admin/charge_nurse
    resource VARCHAR(50) NOT NULL,             -- 'handover', 'patient', 'audit_log'
    action   VARCHAR(20) NOT NULL,             -- 'read', 'write', 'delete', 'admin'
    UNIQUE KEY unique_perm (role, resource, action)
);
```

### 기존 테이블 개선

```sql
-- users 테이블에 추가
ALTER TABLE users ADD COLUMN license_number VARCHAR(50);  -- 면허번호
ALTER TABLE users ADD COLUMN is_active      BOOLEAN DEFAULT TRUE;
ALTER TABLE users ADD COLUMN last_login_at  DATETIME;

-- handovers 테이블에 추가
ALTER TABLE handovers ADD COLUMN priority     VARCHAR(10) DEFAULT 'NORMAL';  -- URGENT/HIGH/NORMAL
ALTER TABLE handovers ADD COLUMN is_confirmed BOOLEAN DEFAULT FALSE;
ALTER TABLE handovers ADD COLUMN confirmed_at DATETIME;
ALTER TABLE handovers ADD COLUMN confirmed_by INT;  -- FK to users
```

---

## 4. Flask Blueprint 구조 개선안

### 현재 구조 (문제)
```
app/
  routes/
    auth.py      # 라우트 + 비즈니스 로직 혼재
    patients.py  # 라우트 + DB쿼리 혼재
    handover.py  # 라우트 + 분석 로직 혼재
```

### 개선된 구조 (Service Layer 패턴)
```
app/
  ├── routes/          # HTTP 요청/응답만 처리
  │   ├── auth.py
  │   ├── patients.py
  │   ├── handover.py
  │   └── admin.py      # NEW: 관리자 전용
  │
  ├── api/             # NEW: REST API (JSON 반환)
  │   ├── __init__.py
  │   ├── handover.py  # /api/v1/handovers
  │   ├── patients.py  # /api/v1/patients
  │   └── stats.py     # /api/v1/stats
  │
  ├── services/        # NEW: 비즈니스 로직 분리
  │   ├── audit_service.py      # 감사 로그 기록
  │   ├── risk_service.py       # 위험도 분석 엔진
  │   └── stats_service.py      # 통계 계산
  │
  ├── middleware/      # NEW: 공통 미들웨어
  │   ├── rbac.py              # 권한 데코레이터
  │   └── audit_middleware.py  # 자동 감사 로그
  │
  └── models.py        # 기존 + AuditLog, RiskAssessment 추가
```

### 왜 이렇게 설계하는가?

**Service Layer를 쓰는 이유:**
- Route는 "어떤 데이터를 받아서 어떤 응답을 줄까"만 결정
- Service는 "실제로 어떻게 처리할까"를 결정
- 같은 Service를 HTML Route와 REST API 모두에서 재사용 가능
- 테스트 작성이 쉬워짐 (HTTP 없이 Service만 단위 테스트)

---

## 5. 포트폴리오 설명 방법

### GitHub README에 쓸 문장
```
"단순 CRUD를 넘어, 실제 의료 현장의 규정 준수 요건(Compliance)을
고려한 백엔드 시스템을 설계했습니다.

핵심 설계 결정:
1. Audit Log — 모든 데이터 접근/변경을 DB에 기록하여 
   의료 사고 발생 시 추적 가능한 구조 구현
   
2. RBAC — 직종(간호사/의사/수간호사/관리자)별 접근 권한을
   데코레이터 기반으로 선언적으로 관리
   
3. 위험도 분석 엔진 — 단순 키워드 매칭이 아닌 
   가중치 기반 점수 시스템으로 오탐률 감소
   
4. Service Layer — 비즈니스 로직을 Route에서 분리하여
   동일 로직을 웹뷰/REST API에서 재사용"
```

---

## 6. 면접관이 좋아할 포인트

### 기술적 어필 포인트

**"왜 AuditLog를 별도 테이블로?"**
→ "SQLAlchemy event listener를 사용해 모델 레이어에서
   자동으로 로그를 기록합니다. 개발자가 각 라우트마다
   로그 코드를 작성할 필요가 없어 누락 위험이 없습니다."

**"위험도 점수는 어떻게 산정?"**
→ "키워드 자체 위험도(가중치) × 발생 빈도 × 바이탈 이상 여부를
   조합한 0~100점 스코어링 시스템입니다.
   동일 환자에게 24시간 내 같은 위험 키워드가 3회 이상
   등장하면 가중치를 추가로 부여합니다."

**"RBAC를 어떻게 구현?"**
→ "Flask 데코레이터 패턴으로 @require_role('admin') 처럼
   선언적으로 사용합니다. 권한 정보는 DB에 저장해
   코드 배포 없이 관리자가 권한을 변경할 수 있습니다."

---

## 7. 의료 서비스 특성을 살린 차별화 아이디어

1. **교대 시간 알림** — 주간(07:00)→야간(15:00) 교대 시
   미확인 인수인계가 있으면 자동 알림

2. **동일 환자 반복 위험 패턴 감지** — 3일 연속 같은 위험
   키워드가 등장하면 담당의에게 에스컬레이션

3. **인수인계 완결성 검사** — 활력징후, 투약, 처치 중
   하나라도 미입력 시 경고 (선택이지만 권장)

4. **익명 통계** — 병동별 위험 발생률을 집계해
   원무팀이 인력 배치에 활용 가능한 리포트 제공
