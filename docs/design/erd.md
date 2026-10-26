# ERD

- 근거: [기능명세서](functional-spec.md), [API 명세서](api-spec.md), [유스케이스](usecase.md), [아키텍처 설계](architecture.md), [프로젝트 기획서](<../outputs/프로젝트 기획서_사고뭉치_최종.pdf>) 4.5
- 범위: DB를 소유한 서비스 3개(core_db · learning_db · report_db). ai·scoring은 상태 없음 (아키텍처 1.1)
- AI Hub 원본·가공본은 `ml/` 학습용으로 서비스 DB에 넣지 않음 (NFR-DAT-03)
- `[P..]`는 미확정 정책. 확정 전에는 컬럼 자리만 두거나 테이블을 만들지 않음

---

## 1. 공통 규칙

| 항목 | 규칙 |
|---|---|
| DBMS | PostgreSQL. 마이그레이션은 core·learning Flyway, report Alembic (아키텍처 5장) |
| 이름 | 테이블·컬럼 snake_case, 테이블명 단수형 |
| PK | `id uuid` (API 식별자와 동일). 예외: 복합 PK 테이블, `shedlock` |
| 시각·날짜 | 시각 `timestamptz`, 기간 `date`(KST, 양 끝 포함) |
| 상태값 | [API 명세 1.5](api-spec.md#15-상태-코드값-fn-12-대응) 코드값 그대로 `varchar` + CHECK |
| 서비스 간 참조 | 다른 DB의 ID는 FK 없는 논리 참조 (2장). 같은 DB 안에서만 FK |
| 덮어쓰기 금지 | 답변·판정·기준표·미션·리포트는 수정 대신 새 버전 행 추가 (NFR-DAT-01, 02) |
| 버전 연결 | 판정·되묻기·분석·리포트 행에 당시 미션·기준표·모델·프롬프트 버전 저장 (NFR-DAT-02) |
| 개인정보 | 학생은 가명 닉네임만 저장, 실명 컬럼 없음. 결제수단 민감 정보 미저장 (NFR-SEC-06) |
| JSONB | 구조가 응답 스키마와 같고 조회 조건에 쓰지 않는 값만 (Metric[], verification, versions 등) |

- 테이블 없이 Redis에 두는 값: `reauthToken`(단기), 계정 복구 확인 코드, SSE 알림 중계 (아키텍처 1.6)
- 서버에 저장하지 않는 값: 생각 메모 `[P05]`, 음성 원음 (FN-LRN-07, 18)
- 테이블 미생성: 학생 별도 계정·학생 세션 방식 `[P01]` → `student.user_account_id` 자리만 둠

---

## 2. 서비스 간 ID

| ID | 소유 (원본 테이블) | 참조하는 곳 |
|---|---|---|
| `student_id` | core `student.id` | learning `attempt`·`deleted_student`, report `weekly_report` |
| `mission_id` | learning `mission.id` | (core는 프록시만, 저장 없음) |
| `attempt_id`, `answer_id` | learning `attempt`·`answer` | core `message_evidence`, report `report_item_evidence` |
| `judgment_id`, `followup_id` | learning `judgment`·`followup` | core `error_report.target_id` |
| `job_id` | core `report_job.id` | report `weekly_report.job_id` |
| `report_id` | report `weekly_report.id` | core `report_job.report_id`, `report_view.report_id`, `error_report.target_id` |
| `rubric_version_id` | learning `rubric_version.id` | core `model_version.ref_id` (`kind = RUBRIC`) |
| `error_report_id` | core `error_report.id` | learning `judgment_correction` |
| 사용자 ID | core `user_account.id` | learning `mission.created_by`·`mission_review.reviewer_id`·`judgment_correction.corrected_by` |

- 삭제 전파: core가 삭제 확정 시 `student.deleted` 발행 → learning·report가 해당 학생 기록 삭제 (아키텍처 1.4, `[P09]`)
- 삭제된 기록을 참조하면 learning 근거 조회가 `available: false` 반환 (FN-ACC-13)

---

## 3. core_db

### 3.1 계정·동의·자녀 연결 (FN-ACC)

```mermaid
erDiagram
  user_account ||--o{ admin_permission : has
  user_account ||--o{ refresh_token : issues
  user_account |o--o| student : "학생 계정 [P01]"
  user_account ||--o{ consent : agrees
  consent_document ||--o{ consent : "문서 버전"
  student |o--o{ consent : "법정대리인 동의 대상"
  user_account ||--o{ guardianship : parent
  student ||--o{ guardianship : child
  user_account ||--o{ deletion_request : requests
  student ||--o{ deletion_request : target
  user_account ||--o{ withdrawal_request : requests

  user_account {
    uuid id PK
    varchar role "STUDENT|PARENT|ADMIN"
    varchar login_id UK "로그인 ID(이메일)"
    varchar password_hash
    varchar display_name
    varchar status "ACTIVE|WITHDRAWAL_REQUESTED|WITHDRAWN"
    boolean is_demo "시연 계정"
    timestamptz created_at
    timestamptz updated_at
    timestamptz withdrawn_at
  }
  admin_permission {
    uuid user_id PK,FK
    varchar permission PK "CONTENT|PAYMENT_VIEW|PAYMENT_REFUND|SERVICE_OPS"
    uuid granted_by FK
    timestamptz granted_at
  }
  refresh_token {
    uuid id PK
    uuid user_id FK
    varchar token_hash UK
    timestamptz expires_at
    timestamptz revoked_at
    timestamptz created_at
  }
  student {
    uuid id PK "전 서비스 공통 학생 ID"
    uuid user_account_id FK,UK "nullable [P01]"
    varchar nickname "가명"
    int grade "이후 제공 문제에만 적용"
    boolean is_demo "시연 가상 학생"
    varchar status "ACTIVE|DELETION_REQUESTED|DELETED"
    timestamptz created_at
    timestamptz updated_at
    timestamptz deleted_at
  }
  consent_document {
    uuid id PK
    varchar kind "TERMS|PRIVACY|GUARDIAN"
    varchar version
    varchar title
    text content
    boolean required "필수 동의 여부"
    date effective_from
    timestamptz created_at
  }
  consent {
    uuid id PK
    uuid document_id FK
    uuid subject_user_id FK "동의 주체(학부모)"
    uuid student_id FK "nullable, 자녀 동의일 때"
    boolean agreed
    varchar status "AGREED|WITHDRAWN"
    timestamptz agreed_at
    timestamptz withdrawn_at
  }
  guardianship {
    uuid id PK
    uuid parent_user_id FK
    uuid student_id FK
    varchar method "REGISTER|LINK"
    varchar status "LINKED|UNLINKED"
    timestamptz linked_at
    timestamptz unlinked_at
  }
  deletion_request {
    uuid id PK
    uuid requested_by FK
    uuid student_id FK
    varchar scope "PROFILE|RECORDS"
    varchar status "REQUESTED|CONFIRMED|COMPLETED"
    timestamptz requested_at
    timestamptz confirmed_at
    timestamptz completed_at
  }
  withdrawal_request {
    uuid id PK
    uuid user_id FK
    varchar status "REQUESTED|COMPLETED"
    timestamptz requested_at
    timestamptz completed_at
  }
```

- `consent_document` UK `(kind, version)`. 동의는 철회해도 행 유지 → `status`·`withdrawn_at` 갱신 (FN-ACC-02)
- `guardianship` 부분 UK `(parent_user_id, student_id) WHERE status = 'LINKED'`. 권한 확인은 이 테이블의 `LINKED` 행 기준 (아키텍처 1.1)
- 연결 해제는 행 삭제 대신 `UNLINKED` 전환 → 해제 이후 조회 차단, 이력 보존 (FN-DSH-06)
- `deletion_request`가 `CONFIRMED`가 되면 같은 트랜잭션에서 `outbox_event(student.deleted)` 저장
- 로그인 수단·자녀 연결 변경 결과·시점은 `audit_log`에 기록 (FN-ACC-10)
- `user_account.is_demo`·`student.is_demo` 행은 운영 현황·사용량·결제 집계에서 제외 (NFR-OPS-01)

### 3.2 분석 대화·리포트 작업 (FN-AGT, FN-RPT)

```mermaid
erDiagram
  user_account ||--o{ conversation : parent
  student ||--o{ conversation : target
  conversation ||--o{ conversation_message : contains
  conversation_message ||--o{ message_evidence : cites
  student ||--o{ report_job : target
  user_account |o--o{ report_job : "재생성 요청자"
  user_account ||--o{ report_view : views
  user_account |o--o{ job_execution : "재처리 요청자"

  conversation {
    uuid id PK
    uuid parent_user_id FK
    uuid student_id FK
    date period_from "확인된 기간"
    date period_to
    timestamptz created_at
    timestamptz updated_at
  }
  conversation_message {
    uuid id PK
    uuid conversation_id FK
    int seq
    text question
    text answer "대조 통과한 확정 답변만"
    uuid scope_student_id
    date scope_from
    date scope_to
    boolean scope_changed
    varchar status "QUEUED|RUNNING|COMPLETED|FAILED"
    varchar source "LLM|LLM_RETRY|TEMPLATE"
    jsonb clarification "범위 확인 질문·선택지"
    jsonb metrics "Metric[]"
    jsonb verification "numbersMatched, quotesMatched"
    int record_count
    varchar prompt_version
    varchar model_version
    varchar failure_code
    int retry_count
    varchar trace_id
    timestamptz created_at
    timestamptz completed_at
  }
  message_evidence {
    uuid id PK
    uuid message_id FK
    uuid attempt_id "learning 논리 참조"
    uuid answer_id "learning 논리 참조"
    int answer_version
  }
  report_job {
    uuid id PK "= report.generate job_id"
    uuid student_id FK
    date period_from
    date period_to
    varchar trigger "SCHEDULE|REGENERATE|ADMIN_RETRY"
    uuid requested_by FK "nullable"
    varchar status "QUEUED|RUNNING|COMPLETED|FAILED"
    uuid report_id "report 논리 참조"
    varchar failure_reason
    int retry_count
    varchar trace_id
    timestamptz created_at
    timestamptz started_at
    timestamptz completed_at
  }
  job_execution {
    uuid id PK
    varchar job_type "CONVERSATION|REPORT|NOTIFICATION"
    uuid job_id "message·report_job·notification id"
    int attempt_no
    varchar status "RUNNING|COMPLETED|FAILED"
    varchar error_code
    text error_detail "원문·민감 정보 미포함"
    uuid triggered_by FK "nullable, 관리자 재처리"
    timestamptz started_at
    timestamptz finished_at
  }
  report_view {
    uuid id PK
    uuid report_id "report 논리 참조"
    uuid user_id FK
    timestamptz viewed_at
  }
  shedlock {
    varchar name PK
    timestamptz lock_until
    timestamptz locked_at
    varchar locked_by
  }
```

- `conversation_message` UK `(conversation_id, seq)`. 실패 메시지는 `FAILED`로 남기고 재시도 시 같은 행 상태 전이 (FN-AGT-10)
- `message_evidence`는 ID만 저장, 원문은 근거 조회 시 learning에서 읽음 → 삭제된 기록이 core에 남지 않음 (FN-ACC-13)
- 관리자 작업 목록(`/admin/jobs`)은 `conversation_message`·`report_job`·`notification`의 상태 컬럼을 조회 (FN-ADM-03)
- `report_job` 상태 전이: `report.started` 수신 시 `QUEUED→RUNNING`, `report.completed|failed` 수신 시 종료 상태 + `report_id` 저장 (아키텍처 1.6 조건부 전이)
- `report_job` 부분 UK `(student_id, period_from) WHERE trigger = 'SCHEDULE'` → 정기 생성 중복 방지. 재생성·재처리는 새 행 (FN-RPT-01, 12)
- `job_execution`: 작업 실행 1회당 1행, UK `(job_type, job_id, attempt_no)`. 관리자 실패 원인·처리 이력 조회 근거 (FN-ADM-07)
- `report_view`: 학부모 리포트 상세 조회 시 기록, 주간 리포트 열람률 지표 근거 (기획서 3.9)
- `clarification`이 있는 메시지는 범위 확인 후 종료된 질문, 사용자 선택은 다음 메시지의 `scope_*`에 저장 (FN-AGT-03)
- `shedlock`은 ShedLock 기본 스키마 (주간 리포트·정기 청구 스케줄)

### 3.3 알림·신고·문의·공지 (FN-SUP)

```mermaid
erDiagram
  user_account ||--o{ notification : receives
  student |o--o{ notification : "자녀별 사건"
  user_account ||--o{ notification_setting : sets
  user_account ||--o{ error_report : reports
  error_report ||--o{ correction : "정정"
  user_account ||--o{ inquiry : asks
  user_account ||--o{ notice : "등록(관리자)"

  notification {
    uuid id PK
    uuid user_id FK
    uuid child_id FK "nullable"
    varchar type "REPORT_COMPLETED|ERROR_REPORT_RESOLVED|INQUIRY_ANSWERED|PAYMENT_CHANGED|SUBSCRIPTION_CHANGED"
    uuid source_event_id "사건 ID"
    varchar title "원문·결제 민감 정보 미포함"
    varchar link "상세 화면 경로"
    varchar status "QUEUED|RUNNING|COMPLETED|FAILED"
    int retry_count
    varchar failure_reason
    timestamptz read_at
    timestamptz created_at
  }
  notification_setting {
    uuid user_id PK,FK
    varchar type PK
    varchar channel PK "IN_APP|EMAIL|PUSH [P10]"
    boolean enabled
    timestamptz updated_at
  }
  error_report {
    uuid id PK
    uuid reporter_user_id FK
    uuid student_id FK "nullable"
    varchar target_type "FOLLOWUP|JUDGMENT|ANALYSIS|REPORT"
    uuid target_id "learning·core·report 논리 참조"
    varchar category "[P10]"
    text comment
    varchar status "RECEIVED|IN_REVIEW|RESOLVED"
    text review_result
    text resolution_reason
    uuid reviewed_by FK
    timestamptz created_at
    timestamptz resolved_at
  }
  correction {
    uuid id PK
    uuid error_report_id FK
    varchar target_type
    uuid target_id
    text reason
    jsonb impact "대화·집계·리포트 반영 여부"
    uuid corrected_by FK
    timestamptz created_at
  }
  inquiry {
    uuid id PK
    uuid user_id FK
    varchar category "ACCOUNT|USAGE|PAYMENT"
    varchar title
    text body
    varchar status "RECEIVED|IN_REVIEW|RESOLVED"
    text answer
    uuid answered_by FK
    timestamptz answered_at
    timestamptz created_at
  }
  notice {
    uuid id PK
    varchar kind "NOTICE|MAINTENANCE"
    varchar title
    text body
    jsonb target_roles
    timestamptz visible_from
    timestamptz visible_to
    uuid created_by FK
    timestamptz created_at
    timestamptz ended_at
  }
```

- `notification` UK `(user_id, type, source_event_id)` → 같은 사건 재처리 시 중복 생성 방지 (FN-SUP-08)
- 판정 정정 원본은 learning `judgment_correction`, core `correction`은 신고 단위 정정 사유·영향 범위 기록 (FN-SUP-03)
- 도움말(`/help`)은 정적 콘텐츠로 테이블 없음

### 3.4 결제·구독 (FN-PAY) — 토스페이먼츠 테스트

```mermaid
erDiagram
  product ||--o{ payment_order : ordered
  product ||--o{ subscription : plan
  user_account ||--o{ payment_order : buyer
  student ||--o{ payment_order : "대상 자녀"
  user_account ||--o{ subscription : owner
  student ||--o{ subscription : "대상 자녀"
  subscription |o--o{ payment_order : "청구 대상"
  payment_order ||--o| payment : "승인"
  payment ||--o{ refund_request : refunds

  product {
    uuid id PK
    varchar code UK "BASIC|PLUS"
    varchar name
    int price "원, [P13]"
    varchar billing_cycle "MONTHLY|YEARLY"
    int child_limit
    jsonb features
    boolean active
    timestamptz created_at
  }
  payment_order {
    uuid id PK
    varchar order_no UK "PG orderId"
    uuid parent_user_id FK
    uuid student_id FK
    uuid product_id FK
    uuid subscription_id FK "최초 결제는 구독 생성 후 연결"
    varchar kind "INITIAL|RENEWAL"
    date billing_period_start "갱신 청구 대상 기간"
    int amount
    varchar trace_id
    timestamptz created_at
  }
  payment {
    uuid id PK
    uuid order_id FK,UK
    varchar payment_key UK "PG paymentKey"
    int amount "승인 금액"
    varchar status "APPROVED|CONFIRMING|FAILED|CANCELED|REFUND_REVIEW|REFUNDED"
    varchar method "결제수단 종류만"
    varchar entitlement_status "APPLIED|RECOVERY_REQUIRED"
    varchar failure_code
    timestamptz approved_at
    timestamptz canceled_at
    timestamptz updated_at
  }
  subscription {
    uuid id PK
    uuid parent_user_id FK
    uuid student_id FK
    uuid product_id FK
    varchar status "ACTIVE|RENEWAL_FAILED|CANCELED"
    date period_start
    date period_end
    date next_billing_date
    boolean auto_renew
    varchar customer_key "PG customerKey"
    varchar billing_key_enc "암호화 저장"
    int renewal_retry_count "[P13]"
    date grace_until "이용 제한 예정일 [P13]"
    timestamptz auto_renew_canceled_at "자동 갱신 해지 요청"
    timestamptz canceled_at "해지 효력 [P14]"
    timestamptz created_at
    timestamptz updated_at
  }
  refund_request {
    uuid id PK
    uuid payment_id FK
    uuid requested_by FK
    int amount
    text reason
    varchar status "REQUESTED|APPROVED|REJECTED|COMPLETED|FAILED"
    uuid decided_by FK
    text reject_reason
    varchar pg_status
    timestamptz decided_at
    timestamptz created_at
  }
  pg_webhook_event {
    uuid id PK
    varchar transmission_id UK "PG 통지 ID"
    varchar event_type
    varchar order_no
    varchar result "APPLIED|IGNORED|FAILED"
    timestamptz received_at
    timestamptz processed_at
  }
```

- `subscription` 부분 UK `(student_id) WHERE status IN ('ACTIVE','RENEWAL_FAILED')` → 같은 자녀 중복 구독 409 (FN-PAY-02)
- 승인 처리 순서: `payment_order.amount`·대상 자녀 대조 → PG 승인 → `payment` 저장 → 구독 생성·반영 → `payment_order.subscription_id` 연결. 반영 실패 시 `entitlement_status = RECOVERY_REQUIRED` (FN-PAY-03, 05)
- `payment_order` 부분 UK `(subscription_id, billing_period_start) WHERE kind = 'RENEWAL'` → 정기 청구 중복 실행 시 이중 청구 방지 (FN-PAY-06, NFR-REL-01)
- 자동 갱신 해지는 `auto_renew = false` + `auto_renew_canceled_at` 기록, 남은 기간 이후 `status = CANCELED` + `canceled_at` (FN-PAY-09)
- 갱신 실패 시 `RENEWAL_FAILED` + `renewal_retry_count`·`grace_until` 갱신, 재시도 횟수·유예 기간 값은 `[P13]` (FN-PAY-08)
- 웹훅은 `transmission_id`로 1회만 반영, 본문 대신 PG 조회 결과로 상태 갱신 (FN-PAY-04)
- 환불 중복·초과 방지: 승인된 `refund_request.amount` 합계 ≤ `payment.amount` 검사 (FN-ADM-16)
- 카드번호 등 결제수단 원본 미저장, 빌링키는 암호화 (NFR-SEC-06)

### 3.5 운영·공통

```mermaid
erDiagram
  user_account ||--o{ audit_log : acts
  user_account |o--o{ model_version : approves

  model_version {
    uuid id PK
    varchar kind "RUBRIC|MODEL|PROMPT|GENERATION"
    varchar name "judge, m2-klue 등"
    varchar version
    uuid ref_id "RUBRIC이면 learning rubric_version"
    varchar artifact_uri "S3 가중치 경로"
    jsonb eval_result "승인 근거 평가"
    varchar status "REGISTERED|ACTIVE|INACTIVE"
    uuid approved_by FK
    timestamptz activated_at
    timestamptz created_at
  }
  audit_log {
    uuid id PK
    uuid actor_user_id FK
    varchar action "MISSION_PUBLISH, JOB_RETRY, MODEL_ACTIVATE 등"
    varchar target_type
    uuid target_id
    varchar result "SUCCESS|FAILURE"
    jsonb detail "주요 변경 내용, 재분석 여부"
    timestamptz created_at
  }
  llm_usage {
    uuid id PK
    uuid event_id UK "llm.usage.recorded id"
    varchar service "ai|scoring"
    varchar call_type "JUDGMENT|FOLLOWUP|ANALYSIS|REPORT_NARRATIVE|M2|M1|SPEECH"
    varchar model
    varchar prompt_version
    int input_tokens
    int output_tokens
    int latency_ms
    numeric cost_usd "소비 시점 단가 기준"
    boolean success
    varchar error_code
    timestamptz occurred_at
  }
  outbox_event {
    uuid id PK "CloudEvents id"
    varchar event_type
    varchar routing_key
    varchar subject "학생 ID 등"
    jsonb payload
    timestamptz created_at
    timestamptz published_at
  }
  processed_event {
    uuid event_id PK
    varchar event_type
    timestamptz processed_at
  }
  idempotency_record {
    uuid idempotency_key PK
    uuid user_id PK
    varchar endpoint
    varchar request_hash
    int response_status
    jsonb response_body
    timestamptz created_at
    timestamptz expires_at "[P12]"
  }
```

- `model_version` UK `(kind, name, version)`, 부분 UK `(kind, name) WHERE status = 'ACTIVE'`. 롤백은 이전 버전 재활성화 + `audit_log` 기록 (FN-ADM-18)
- 기준표 원본은 learning `rubric_version`, core는 `kind = RUBRIC` 행의 `ref_id`로 연결해 승인·활성 상태만 관리
- `llm_usage`에 학생 ID·답변 원문 컬럼 없음 (NFR-PRF-02). 수집 데이터 보고서의 예정 필드 `llm_usage_log(call_type, model, input_tokens, output_tokens, ts)` 대응
- `cost_usd`는 core 설정의 모델별 토큰 단가(기획서 3.9)로 소비 시 계산, 단가 변경 후에도 과거 값 유지 (FN-ADM-19)
- `outbox_event`: 상태 변경과 같은 트랜잭션에 저장, 릴레이가 publisher confirm 후 `published_at` 기록 (아키텍처 1.6)
- `idempotency_record`: 공개 API의 `Idempotency-Key` 대상(답변 제출·주문·승인·환불·재처리·신고) 공통. 같은 키·다른 본문은 `request_hash` 불일치로 422 (API 1.4)

---

## 4. learning_db

### 4.1 미션·기준표 (FN-ADM-08~13, FN-LRN-02~03)

```mermaid
erDiagram
  mission ||--o{ mission_version : versions
  mission ||--o{ rubric_version : versions
  rubric_version ||--o{ rubric_element : elements
  rubric_version ||--o{ hint_question : hints
  mission ||--o{ mission_review : reviews

  mission {
    uuid id PK
    varchar code UK
    varchar status "DRAFT|REVIEW_REQUIRED|PUBLISHED|UNPUBLISHED"
    uuid current_version_id FK
    uuid current_rubric_version_id FK
    boolean demo_only "시연 전용"
    int sort_order "목록 순서·이전·다음"
    uuid created_by "core 사용자"
    timestamptz created_at
    timestamptz updated_at
    timestamptz published_at
  }
  mission_version {
    uuid id PK
    uuid mission_id FK
    int version
    varchar title
    varchar subject "교과"
    int grade_min
    int grade_max
    varchar thinking_type "ANALYZE|EVALUATE|CREATE|SOLVE|REFLECT"
    jsonb basic_skills "비교·분류·순서·규칙·원인과 결과·추론"
    varchar input_type "CHOICE|ORDERING|CLASSIFICATION|NARRATIVE|SOLUTION_STEPS|ESSAY"
    text question
    text guide
    varchar scene_uri "S3 애니메이션"
    varchar static_scene_uri "움직임 줄이기"
    jsonb choices
    jsonb input_template "풀이 단계·논술 틀"
    jsonb achievement_standards "성취기준 코드"
    uuid created_by
    timestamptz created_at
  }
  rubric_version {
    uuid id PK
    uuid mission_id FK
    int version
    jsonb answer_key "정답·동치 표현"
    text example_answer
    jsonb forbidden_terms "되묻기 유출 검사 금지어"
    uuid created_by
    timestamptz created_at
  }
  rubric_element {
    uuid id PK
    uuid rubric_version_id FK
    varchar code "e1"
    varchar label
    text description
    int points
    jsonb common_errors
    boolean good_thought "들어가면 좋은 생각"
    boolean judge_verified "AI 판정 검증 통과"
    int sort_order
  }
  hint_question {
    uuid id PK
    uuid rubric_version_id FK
    int seq
    text content "정답·제출용 답 금지"
  }
  mission_review {
    uuid id PK
    uuid mission_id FK
    uuid mission_version_id FK
    uuid rubric_version_id FK
    uuid reviewer_id "core 사용자"
    varchar result "APPROVED|CHANGES_REQUESTED"
    text comment
    timestamptz created_at
  }
```

- `mission_version`·`rubric_version` UK `(mission_id, version)`. 수정은 새 버전 추가 후 `mission.current_*` 갱신, 이전 버전 불변 (FN-ADM-10, 12)
- 공개(`PUBLISHED`) 전 필수 항목 검사: 현재 미션·기준표 버전 존재, 기준표 요소 1개 이상(서술·논술) 또는 `answer_key`(고르기·수학) (FN-ADM-11)
- `mission.sort_order`: 학년군 안의 목록 순서, 이전·다음 이동과 진행 위치 계산 (FN-LRN-02)
- `rubric_element.judge_verified = false` 요소는 AI 판정 시 충족 표시 금지 → `HELD (UNVERIFIED_SCOPE)`. 평가 통과 후 관리자가 갱신 (FN-JDG-04, 05, NFR-AIQ-01)
- `forbidden_terms`: 정답 키와 함께 ai `followups` 유출 검사 입력 (FN-JDG-06)
- AI Hub 문항·답안·피드백 원문은 어떤 컬럼에도 저장하지 않음 (FN-ADM-09)

### 4.2 학습 시도·답변·판정 (FN-LRN, FN-JDG)

```mermaid
erDiagram
  mission ||--o{ attempt : "시도"
  mission_version ||--o{ attempt : "당시 버전"
  rubric_version ||--o{ attempt : "당시 기준"
  attempt ||--o| attempt_draft : draft
  attempt ||--o{ hint_usage : opens
  hint_question ||--o{ hint_usage : opened
  attempt ||--o{ answer : submits
  answer |o--o{ answer : "previous_answer"
  followup |o--o{ answer : "보완 답변"
  answer ||--|| judgment : judged
  judgment ||--o{ judgment_element : elements
  rubric_element ||--o{ judgment_element : "기준 요소"
  judgment ||--o| followup : generates
  attempt ||--o{ followup : timeline
  judgment ||--o{ judgment_correction : corrected
  attempt ||--o| reflection : reflects
  attempt ||--o{ self_assessment : "자기 체크"
  rubric_element ||--o{ self_assessment : checked

  attempt {
    uuid id PK
    uuid student_id "core 논리 참조"
    uuid mission_id FK
    uuid mission_version_id FK
    uuid rubric_version_id FK
    int grade "시작 당시 학년"
    varchar status "IN_PROGRESS|COMPLETED"
    timestamptz started_at
    timestamptz finished_at "마무리·정답 공개"
    timestamptz completed_at "돌아보기 저장"
    timestamptz updated_at
  }
  attempt_draft {
    uuid attempt_id PK,FK
    int version "ETag"
    jsonb content
    timestamptz saved_at
  }
  hint_usage {
    uuid id PK
    uuid attempt_id FK
    uuid hint_question_id FK
    timestamptz opened_at
  }
  answer {
    uuid id PK
    uuid attempt_id FK
    int version "1 = 최초 답변"
    uuid followup_id FK "보완 답변이 답한 되묻기"
    uuid previous_answer_id FK
    varchar input_type
    jsonb content "text, essay, choiceIds"
    text plain_text "인용 대조용 원문"
    boolean dictated_by_guardian
    boolean speech_transcribed "음성 시범, 판정 제외"
    uuid idempotency_key
    timestamptz submitted_at
  }
  judgment {
    uuid id PK
    uuid answer_id FK,UK
    varchar process_status "PENDING|RUNNING|DONE|FAILED"
    timestamptz lease_until "RUNNING 리스 [P12]"
    varchar result "CORRECT|PARTIAL|RETHINK|HELD"
    varchar held_reason "INSUFFICIENT_EVIDENCE|QUOTE_MISMATCH|TOO_SHORT|UNVERIFIED_SCOPE|MODEL_DISAGREEMENT|LOW_CONFIDENCE"
    varchar method "RULE|LLM"
    boolean trial "AI 채점(시범)"
    jsonb model_scores "M2·M1 결과(AI 관찰)"
    uuid rubric_version_id FK
    varchar model_version
    varchar prompt_version
    varchar failure_code
    int retry_count
    varchar trace_id
    timestamptz created_at
    timestamptz completed_at
  }
  judgment_element {
    uuid id PK
    uuid judgment_id FK
    uuid rubric_element_id FK
    text quote "LLM 추출 구절"
    boolean verified "코드 원문 대조"
    boolean satisfied
    varchar source_type "RECORD|RULE|ANSWER_KEY|AI_OBSERVATION"
  }
  followup {
    uuid id PK
    uuid attempt_id FK
    uuid judgment_id FK,UK
    varchar type "ONE_STEP_MORE|TELL_MORE|LOOK_AGAIN"
    text question
    varchar source "LLM|LLM_RETRY|BANK|TEMPLATE"
    boolean leak_check_passed
    varchar prompt_version
    varchar model_version
    timestamptz created_at
  }
  judgment_correction {
    uuid id PK
    uuid judgment_id FK
    uuid error_report_id "core 논리 참조"
    text reason
    jsonb previous "정정 전 결과"
    jsonb corrected "정정 후 결과"
    uuid corrected_by "core 사용자"
    uuid idempotency_key UK
    timestamptz created_at
  }
  reflection {
    uuid id PK
    uuid attempt_id FK,UK
    varchar difficulty "EASY|NORMAL|HARD"
    text changed_text "달라진 점"
    timestamptz created_at
  }
  self_assessment {
    uuid id PK
    uuid attempt_id FK
    uuid rubric_element_id FK
    boolean checked
    timestamptz created_at
  }
```

- `attempt` 부분 UK `(student_id, mission_id) WHERE status = 'IN_PROGRESS'` → 시작 요청 시 진행 중 시도 반환 (FN-LRN-16)
- `attempt`는 시작 시점의 미션·기준표 버전을 고정 → 기준 변경 후에도 과거 결과 재현 (NFR-DAT-02)
- `attempt_draft`는 시도당 1행, `UPDATE ... WHERE version = :ifMatch` 실패 시 409 (FN-LRN-17)
- `answer` UK `(attempt_id, version)`, `(attempt_id, idempotency_key)`. 수정·삭제 없이 추가만 (FN-LRN-08~10)
- `speech_transcribed = true` 답변은 판정하지 않음 (FN-LRN-18, 범위 `[P03]`)
- `judgment`는 답변 제출 시 `PENDING`으로 함께 생성. 피드백 요청 시 `PENDING|FAILED|리스 만료 RUNNING → RUNNING` 조건부 전이 (API 1.4)
- 판정 보류는 `result = HELD`, 처리 실패는 `process_status = FAILED` → 서로 다른 컬럼 (NFR-REL-04)
- `judgment_element` UK `(judgment_id, rubric_element_id)`. `verified = false`면 `satisfied = true` 금지 (CHECK, FN-JDG-03)
- 정정은 `judgment`를 직접 바꾸지 않고 `judgment_correction` 추가, 최신 정정을 조회 시 반영 (FN-SUP-03)
- `self_assessment` UK `(attempt_id, rubric_element_id)`. AI 판정·원본 답변과 별도 저장 (FN-LRN-13)
- 도움 이용 비율 집계 근거 = `hint_usage.opened_at` vs 최초 `answer.submitted_at` (집계 규칙 `[P08]`)

### 4.3 삭제·공통

```mermaid
erDiagram
  deleted_student {
    uuid student_id PK
    varchar scope "PROFILE|RECORDS"
    uuid event_id "student.deleted id"
    timestamptz deleted_at
  }
  processed_event {
    uuid event_id PK
    varchar event_type
    timestamptz processed_at
  }
```

- `student.deleted` 소비: 해당 학생 `attempt` 이하 기록 삭제 + `deleted_student` 저장 → 근거 조회 시 `available: false` (삭제 방식 `[P09]`)
- learning은 이벤트를 발행하지 않으므로 `outbox_event` 없음 (아키텍처 1.6)
- 멱등은 `answer`·`judgment_correction`의 `idempotency_key` UK로 처리, 별도 `idempotency_record` 없음

---

## 5. report_db

```mermaid
erDiagram
  weekly_report ||--o{ report_item : items
  report_item ||--o{ report_item_evidence : cites
  weekly_report ||--o{ report_file : files

  weekly_report {
    uuid id PK
    uuid job_id UK "core report_job"
    uuid student_id "core 논리 참조"
    date period_from
    date period_to
    int revision "재생성 회차"
    varchar status "RUNNING|COMPLETED|FAILED"
    varchar state "OK|NO_RECORD|INSUFFICIENT_SAMPLE"
    text inclusion_rule "포함 기준 [P06][P08]"
    text evening_question
    jsonb narrative "text, source, modelExplanation"
    jsonb verification "numbersMatched, quotesMatched"
    jsonb versions "prompt, model"
    varchar failure_reason
    timestamptz created_at
    timestamptz generated_at
  }
  report_item {
    uuid id PK "evidence itemId"
    uuid report_id FK
    varchar item_type "METRIC|THINKING_TYPE|CHANGE|REFLECTION|QUOTE"
    int seq
    jsonb payload "Metric, 유형 요약, 전후 변화 등"
    varchar state "OK|NO_RECORD|INSUFFICIENT_SAMPLE"
    boolean verified "숫자·인용 대조"
  }
  report_item_evidence {
    uuid id PK
    uuid item_id FK
    uuid attempt_id "learning 논리 참조"
    uuid answer_id "learning 논리 참조"
    int answer_version
  }
  report_file {
    uuid id PK
    uuid report_id FK
    varchar format "PDF|MD|HTML"
    varchar s3_key
    bigint size_bytes
    timestamptz created_at
  }
  outbox_event {
    uuid id PK
    varchar event_type
    varchar routing_key
    varchar subject
    jsonb payload
    timestamptz created_at
    timestamptz published_at
  }
  processed_event {
    uuid event_id PK
    varchar event_type
    timestamptz processed_at
  }
```

- `weekly_report.job_id` UK → 같은 `report.generate` 재전달 시 1회만 생성. 상태 전이 `RUNNING → COMPLETED|FAILED`와 `outbox_event(report.*)`를 같은 트랜잭션에 저장
- 재생성은 기존 행을 덮지 않고 `revision` 증가 행 추가, UK `(student_id, period_from, revision)` (보존 방식 `[P06]` `[P09]`)
- 기록 없는 주·표본 부족 주는 `status = COMPLETED` + `state`로 구분, 생성 실패(`FAILED`)와 분리 (FN-RPT-11)
- `report_item` UK `(report_id, item_type, seq)`. 상세 응답(API 3.4)은 `item_type`별로 묶어 조립
- `report_file` UK `(report_id, format)`. 다운로드는 `s3_key`로 presigned URL 발급 (FN-RPT-13)

---

## 6. 인덱스

| DB | 테이블 | 인덱스 | 용도 |
|---|---|---|---|
| core | `guardianship` | `(parent_user_id) WHERE status='LINKED'` | 요청마다 자녀 연결 확인 |
| core | `conversation` | `(parent_user_id, student_id, created_at)` | 대화 목록 |
| core | `report_job` | `(student_id, period_from)`, `(status, created_at)` | 리포트 목록, 관리자 작업 현황 |
| core | `job_execution` | `(job_type, job_id)` | 작업별 처리 이력 |
| core | `report_view` | `(report_id)`, `(user_id, viewed_at)` | 열람률 집계 |
| core | `notification` | `(user_id, read_at, created_at)` | 읽지 않은 알림 |
| core | `payment` | `(status, updated_at)` | `CONFIRMING` 재조회, 결제 운영 조회 |
| core | `subscription` | `(next_billing_date) WHERE auto_renew` | 정기 청구 대상 |
| core | `llm_usage` | `(occurred_at, call_type)` | 사용량·비용 집계 |
| core | `outbox_event` | `(created_at) WHERE published_at IS NULL` | 릴레이 대상 |
| learning | `mission` | `(status, sort_order)`, `mission_version (thinking_type, grade_min, grade_max)` | 학년·유형별 공개 미션 목록 |
| learning | `attempt` | `(student_id, started_at)` | 기간별 기록 조회 (대시보드·에이전트·리포트) |
| learning | `answer` | `(attempt_id, submitted_at)` | 시도 타임라인 |
| learning | `judgment` | `(process_status, lease_until)` | 고착 `RUNNING` 탐지 |
| report | `weekly_report` | `(student_id, status, period_from)` | 자녀별 리포트 목록 |

---

## 7. 확인 필요 가정
- `[P01]` 학생 별도 계정: 확정 전 `student.user_account_id` NULL, 학생 진입은 학부모 계정 하위 세션으로 가정. 만 14세 확인 방식 확정 시 `student.birth_year` 추가
- `[P02]` 기존 학생 연결 절차: 연결 코드 방식 확정 시 연결 코드 테이블 추가
- `[P05]` 메모 보관: 확정 시 `attempt_draft.content`에 포함 또는 별도 테이블
- `[P16]` 중립 질문 은행: 사용 합의 시 learning에 질문 은행 테이블 추가 (`followup.source = BANK`)
- PG 거래 대조(FN-ADM-15): 조회 시 PG API와 계산, 결과 테이블 없음
- `[P09]` 삭제 방식: 물리 삭제 + `deleted_student` 표식으로 가정. 보관 기간 확정 시 대화·리포트 삭제 범위 반영
- `[P12]` `idempotency_record.expires_at`·`judgment.lease_until` 값
- `[P13]` 상품·가격: `product` 시드 데이터로만 관리, 스키마 변경 없음
