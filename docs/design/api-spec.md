# API 명세서

- 근거: [기능명세서](functional-spec.md), [유스케이스](usecase.md), [프로젝트 기획서](<../outputs/프로젝트_기획서_사고뭉치.pdf>), [아키텍처 설계](architecture.md)
- 범위: 공개 API(core-service, 웹이 호출) 전체 + 서비스 간 내부 API
- 우선순위: 유스케이스 우선순위(핵심·제안·우선1·우선2·선택)
- `(P04)` 형태는 확정 정책 번호, 내용은 [기능명세서 1.4](functional-spec.md#14-확정-정책)
- 구현 시 이 문서 → `contracts/openapi/<service>.yaml` 순으로 반영

---

## 1. 공통 규칙

### 1.1 기본
| 항목 | 규칙 |
|---|---|
| Base URL | 공개 `/api/v1` (core만 외부 노출), 내부 `/internal` |
| 형식 | JSON(UTF-8), 필드 camelCase, 시각 ISO-8601 오프셋 포함(`2026-11-02T19:00:00+09:00`), 날짜 `YYYY-MM-DD`(KST) |
| 식별자 | 문자열 ID(UUID). 학부모 경로의 `{childId}`는 학생 ID |
| 기간 조회 | `from`, `to`(날짜, 양 끝 포함). 응답에 실제 조회 기간 `period` 반환 (FN-DSH-10) |
| 목록 | `page`(0부터), `size`(기본 20, 최대 100) → `{items, page, size, totalElements}`. 예외: 알림은 `totalElements` 대신 `hasNext`(3.10), 리포트·학생 기기 목록은 `{items}`만(5.5·3.11), 자녀·동의 목록은 페이지 없이 전체를 `page: 0, size = items 수`로 반환(5.3) |
| 스트리밍 | `text/event-stream`, 각 이벤트 `event: <이름>` + `data: <JSON>` (1.6) |

### 1.2 인증·권한
- 인증: `Authorization: Bearer <accessToken>`. access token은 메모리 보관, refresh token은 httpOnly·Secure·SameSite=Strict 쿠키
- 학생 기기 자격증명: 학부모가 등록한 기기에만 httpOnly·Secure·SameSite=Strict 쿠키(`student_device`, path `/api/v1/auth/student`)로 발급. PIN 로그인에만 사용하며 그 자체로 API 접근 권한 없음 (P01, 3.11)
- 역할: `STUDENT`, `PARENT`, `ADMIN`. 관리자 권한은 승인 계정에만 부여, 가입 시 선택 불가 (FBN-02)
- 관리자 세부 권한

| 권한 | 범위 |
|---|---|
| `CONTENT` | 미션·기준표 작성·검토·공개·중단 (학생 원문 열람 불가) |
| `PAYMENT_VIEW` | 결제·구독 조회, PG 대조 |
| `PAYMENT_REFUND` | 환불 승인 |
| `SERVICE_OPS` | 운영 현황, 작업 재처리, 신고·문의·공지, 모델·프롬프트 버전, AI 사용량 |
| 학생 원문 열람 | `SERVICE_OPS`가 오류 신고·문의에 연결된 시도의 답변·판정만, 열람마다 `audit_log` (P07) |

- 리소스 권한 (FN 1.1, NFR-SEC-02)
  - 학생: 본인 기록만
  - 학부모: 연결된 자녀만. 아닌 경우 `403 CHILD_NOT_LINKED`
  - 화면 API·다운로드·에이전트 도구·내부 조회 모두 동일 검사

### 1.3 오류 응답 (RFC 9457)
```json
{
  "type": "https://sagomungchi.dev/errors/attempt-draft-conflict",
  "title": "초안 충돌",
  "status": 409,
  "code": "ATTEMPT_DRAFT_CONFLICT",
  "detail": "다른 화면에서 더 최신 초안이 저장됨",
  "instance": "/api/v1/attempts/7b1.../draft",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

| code | status | 상황 |
|---|---|---|
| `UNAUTHENTICATED` / `TOKEN_EXPIRED` | 401 | 미인증 / 만료 → 재인증 안내 (FN-ACC-04) |
| `FORBIDDEN` | 403 | 역할·관리자 권한 부족 |
| `CHILD_NOT_LINKED` | 403 | 연결되지 않은 자녀 요청 (FN-AGT-02, FN-RPT-12) |
| `REAUTH_REQUIRED` | 403 | 중요 정보 변경 전 재확인 필요 (FN-ACC-10) |
| `STUDENT_DEVICE_INVALID` | 401 | 학생 기기 자격증명 없음·해제·만료, 해당 기기에 등록되지 않은 자녀 (FN-ACC-05) |
| `STUDENT_PIN_INVALID` | 401 | PIN 불일치, `remainingAttempts` 포함 (FN-ACC-05) |
| `STUDENT_PIN_LOCKED` | 423 | PIN 연속 5회 실패로 잠금, 학부모 PIN 재설정 필요 (FN-ACC-05) |
| `STUDENT_PIN_NOT_SET` | 409 | PIN 미설정 자녀의 PIN 로그인 → 학부모 동석 진입 안내 (FN-ACC-05) |
| `PAIRING_CODE_INVALID` | 400 | 페어링 코드 없음·만료·이미 사용 (FN-ACC-14) |
| `NOT_FOUND` | 404 | 리소스 없음 |
| `DATA_UNAVAILABLE` | 410 / 503 | 삭제된 근거 → "이용 불가" 표시(410), report 원문 조회·파일 저장소 장애는 재시도 가능한 503 |
| `DELETION_IN_PROGRESS` | 409 | report 학생 삭제가 진행 중이므로 리포트 조회를 잠시 차단(core가 같은 코드로 전달), core 자녀 삭제 요청이 이미 진행 중 (5.6) |
| `VALIDATION_FAILED` | 400 | 형식 오류 (`errors[]`에 필드별 사유) |
| `ANSWER_INCOMPLETE` | 422 | 필요한 선택·입력 누락 (FN-LRN-04) |
| `IDEMPOTENCY_KEY_REUSED` | 422 | 같은 키에 다른 요청 본문 |
| `ATTEMPT_DRAFT_CONFLICT` | 409 | 초안 버전 충돌, 응답에 최신 초안 포함 (FN-LRN-17) |
| `ATTEMPT_CLOSED` | 409 | 완료된 학습 시도에 쓰기, 마무리(`finished_at`) 이후 답변 제출 (P04) |
| `REVEAL_CONDITION_UNMET` | 409 | 마무리 조건(판정 `DONE` 1회 이상) 미충족 → 정답·예시 답 비공개 (FN-LRN-11, P04) |
| `MISSION_NOT_AVAILABLE` | 409 | 비공개·범위 밖 미션 |
| `MISSION_PUBLISH_INCOMPLETE` | 422 | 필수 정보 누락으로 공개 불가, `missingFields[]` (FN-ADM-11) |
| `SUBSCRIPTION_DUPLICATE` | 409 | 같은 자녀 중복 구독 (FN-PAY-02) |
| `PAYMENT_AMOUNT_MISMATCH` | 422 | 요청 금액과 승인 정보 불일치 (FN-PAY-03) |
| `REFUND_NOT_ALLOWED` | 409 | 중복·초과 환불, 환불 조건(결제 7일 이내·프리미엄 기능 미사용) 불충족 (FN-ADM-16, P14) |
| `CHILD_LIMIT_REACHED` | 409 | 학부모당 자녀 3명 초과 등록 (FN-ACC-06, P02) |
| `REPORT_REGENERATION_LIMIT` / `REPORT_GENERATION_IN_PROGRESS` | 409 / 409 | 학부모의 같은 자녀·주 리포트 재생성 1회 초과 (FN-RPT-12, P06) / 같은 주 생성 작업 진행 중 (5.5) |
| `WITHDRAWAL_BLOCKED` | 409 | 진행 중 구독·미처리 환불이 있어 탈퇴 불가, 정리 대상 포함 (FN-ACC-12, P09) |
| `USAGE_LIMIT_REACHED` | 429 | 요금제 사용 한도 도달(무료: 하루 미션 3개·분석 대화 없음, 프리미엄: 하루 피드백 50회·분석 대화 30회), 가능 범위·사유·초기화 시점 포함 (FN-ADM-19, P13) |
| `AI_UNAVAILABLE` | 503 | AI 처리 실패, `retryable` 포함 (처리 실패 상태, 보류와 구분) |
| `SESSION_CHANGED` | 401 | 다른 탭에서 역할·세션이 바뀌어 access의 세션 version 불일치 (5.1) |
| `REFRESH_REUSED` | 401 | 이미 사용된 refresh 재사용 → 해당 세션 전체 폐기 (5.1) |
| `OAUTH_FAILED` / `OAUTH_UNAVAILABLE` | 401 / 503 | Google 인증 실패 / Google 로그인 미설정·연결 실패. 콜백은 `/auth/complete?error=<code>`로 전달 (5.1) |
| `ACCOUNT_EXISTS` | 409 | 같은 이메일의 기존 계정은 자동 연결하지 않음 (5.1) |
| `AUTH_UNAVAILABLE` | 503 | 인증 상태 확인 실패(DB 장애 등) |
| `CONSENT_REQUIRED` | 403 | 필수 계정 동의 또는 GUARDIAN 동의 전 접근 (5.3) |
| `CONSENT_DOCUMENT_CHANGED` / `CONSENT_DOCUMENTS_UNAVAILABLE` | 409 / 503 | 제출한 동의 문서 버전이 현재와 다름 / 게시된 동의 문서 확인 실패 (5.3) |
| `IDEMPOTENCY_IN_PROGRESS` / `IDEMPOTENCY_UNAVAILABLE` | 409 / 503 | 같은 키 처리 중(`Retry-After: 1`) / 멱등 기록 저장소 장애 (1.4) |
| `LEARNING_UNAVAILABLE` / `LEARNING_TIMEOUT` / `LEARNING_CIRCUIT_OPEN` | 503 / 504 / 503 | core→learning 호출 실패 / 시간 초과 / 서킷 차단 (1.4) |
| `LEARNING_CONTRACT_INVALID` | 502 | 대시보드 공급자의 JSON·학생 식별자·필수 조회 봉투 계약 위반. 기록 없음으로 대체하지 않음 (#40, 2.3) |
| `MODEL_VERSION_CONFLICT` / `MODEL_APPROVAL_REJECTED` / `MODEL_VERSION_STATE_INVALID` | 409 / 422 / 503 | 허용되지 않는 전이·복귀 이력 없음 / 승인 근거·범위 부족 / 기존 ACTIVE 상태 불완전 (5.2) |
| `LEARNING_INVALID_RESPONSE` | 502 | 피드백 SSE에서 learning 응답 형식 오류 (3.2) |
| `SUPPORT_CORRECTION_CONFLICT` / `SUPPORT_CORRECTION_REJECTED` | 409 / 422 | learning 정정 POST의 업무 충돌 / 요청 거부. 공급자 본문은 공개하지 않음 (5.7) |
| `SUPPORT_DEPENDENCY_UNAVAILABLE` / `SUPPORT_INVALID_RESPONSE` | 503 / 502 | 지원 공급자의 기타 비-2xx / 잘못된 2xx 성공 응답 (5.7) |
| `REPORT_NOT_FOUND` / `REPORT_SCOPE_REJECTED` | 404 / 403 | 없는 리포트 / report-api가 학생 범위를 거부 (5.5) |
| `REPORT_ENTITLEMENT_UNAVAILABLE` | 503 | 리포트 상품 권한 확인 불가. 작업·Outbox를 만들지 않음 (5.5) |
| `REPORT_UNAVAILABLE` / `REPORT_CONTRACT_INVALID` | 503 / 502 | report-api 연결 실패·그 밖의 오류 응답 / 응답 JSON·식별·기간 계약 위반 (5.5) |
| `RATE_LIMITED` / `STUDENT_AUTH_UNAVAILABLE` | 429 / 503 | 기기 등록·페어링 발급 10분 한도 초과 / 기기·페어링 저장소(Redis) 장애 (3.11) |
| `REAUTH_PENDING` | 409 | Google 재인증 callback 전에 재인증 토큰 수령 시도 (5.6) |
| `METHOD_NOT_ALLOWED` / `UNSUPPORTED_MEDIA_TYPE` / `REQUEST_FAILED` | 405 / 415 / 그 밖의 4xx·5xx | 허용되지 않는 메서드 / 지원하지 않는 Content-Type / 위 표에 없는 프레임워크 기본 오류 |
| `INTERNAL_ERROR` | 500 | 예상하지 못한 서버 오류 (SSE `error` 이벤트는 `retryable: true`) |

- 피드백 SSE `error` 이벤트: core가 만든 오류는 `type: "about:blank"`·`title`·`status`·`code`·`retryable`만 포함하고 `instance`·`traceId`는 없음. learning이 보낸 Problem Details는 그대로 전달하고 빠진 `type`·`title`·`status`·`code`·`retryable`만 보충 (3.2)

### 1.4 멱등성·동시성
- `Idempotency-Key`(UUID) 필수 대상
  - 답변 제출
  - 결제 주문·승인
  - 환불 요청
  - 작업 재처리
  - 신고 제출
- 같은 키 재요청 처리: 최초 결과를 그대로 반환하고 1회만 반영 (NFR-REL-01)
- 키 보관 기간 24시간 (P12)
- #38 core 답변 프록시: 키는 검증된 계정 UUID에 묶고, HTTP 메서드·실제 endpoint·검증된 학생 범위·원문 본문 SHA-256을 대조한다. 같은 키로 다른 endpoint·학생·본문을 보내면 `422 IDEMPOTENCY_KEY_REUSED`다. JSON 공백·필드 순서가 바뀌어도 다른 원문으로 취급한다.
- 처리 중 같은 키는 `409 IDEMPOTENCY_IN_PROGRESS`와 `Retry-After: 1`을 반환한다. PostgreSQL 세션 advisory lock으로 프로세스 간 실행을 직렬화하며 외부 HTTP 중 DB 트랜잭션은 열지 않는다. 응답 확정 전 NULL 행은 잠금이 해제된 다음 같은 요청으로 재개한다. 프로세스 종료·연결 종료 시 잠금은 해제된다.
- 최초 2xx~4xx 상태·응답 원문·Content-Type·ETag·Retry-After·Location을 저장해 재사용한다. 5xx·전송 실패·core 응답 저장 실패는 성공으로 확정하지 않고 같은 키 재요청을 허용한다. core가 생성한 장애는 `503 LEARNING_UNAVAILABLE` / `503 IDEMPOTENCY_UNAVAILABLE`, 시간 초과는 `504 LEARNING_TIMEOUT`, 서킷 차단은 `503 LEARNING_CIRCUIT_OPEN`이다. learning에서 받은 오류 상태·Problem Details는 그대로 전달한다.
- core는 답변의 `Idempotency-Key`를 learning에 그대로 전달한다. learning은 `(attempt_id, idempotency_key)` UK와 답변·PENDING 판정의 동일 트랜잭션으로 최초 응답을 재구성하고, 키 중복 시 본문 불일치를 422로 거부해야 한다. core 저장 실패·만료·연결 장애 후 재요청도 이 계약으로 중복 반영을 막는다. learning의 실제 구현·통합 검증은 #24에서 충족해야 한다.
- 초안은 `ETag`/`If-Match`(초안 버전)로 처리. 불일치 시 409를 반환하고 조용히 덮어쓰지 않음
- 피드백 요청은 키 대신 answerId의 판정 처리 상태로 중복 방지 (실패 후 재시도가 같은 요청이므로 키 재사용 불가)
  - `DONE`: 저장된 결과 반환
  - `RUNNING`: 새로 실행하지 않고 `status` 이벤트 후 종료, 클라이언트가 잠시 후 재요청. 그사이 다른 요청의 처리가 실패(`FAILED`)한 경우도 처리 중으로 응답하고, 다시 요청하면 실행
  - `PENDING`·`FAILED`·리스 만료된 `RUNNING`(처리 Pod 종료로 고착): 조건부 상태 전이 후 실행 (리스 90초, P12)

### 1.5 상태 코드값 (FN 1.2 대응)
| 대상 | 값 |
|---|---|
| 미션 수행 | `NOT_STARTED` 시작 전 · `IN_PROGRESS` 진행 중 · `COMPLETED` 완료 |
| 미션 운영 | `DRAFT` 작성 중 · `REVIEW_REQUIRED` 검토 필요 · `PUBLISHED` 공개 · `UNPUBLISHED` 비공개 |
| 초안 저장 | `SAVED` (저장 중·저장 실패는 클라이언트 상태) |
| 판정 처리 | `PENDING` · `RUNNING` · `DONE` · `FAILED` |
| 판정 결과 | `CORRECT` 정답 · `PARTIAL` 부분 정답 · `RETHINK` 다시 생각 · `HELD` 판정 보류 (처리 실패는 처리 상태 `FAILED`) |
| 되묻기 유형 | `ONE_STEP_MORE` 한 걸음 더 · `TELL_MORE` 더 말해 보기 · `LOOK_AGAIN` 다시 살펴보기 |
| 돌아보기 난이도 | `EASY` 쉬웠어 · `NORMAL` 보통 · `HARD` 어려웠어 (ERD `reflection.difficulty`) |
| 작업 (대화·리포트·알림) | `QUEUED` 대기 · `RUNNING` 처리 중 · `COMPLETED` 완료 · `FAILED` 실패 |
| 조회 결과 | `OK` · `NO_RECORD` 기록 없음(집계 대상 시도 0건) · `INSUFFICIENT_SAMPLE` 표본 부족(1~4건, 비율 대신 개수만, P08) · `PROCESSING` 처리 중 · `FAILED` 조회 실패 |
| 신고 | `RECEIVED` 접수 · `IN_REVIEW` 검토 중 · `RESOLVED` 처리 완료 |
| 결제 거래 | `APPROVED` 승인 · `CONFIRMING` 확인 중 · `FAILED` 실패 · `CANCELED` 취소 · `REFUND_REVIEW` 환불 검토 중 · `REFUNDED` 환불 |
| 구독 | `ACTIVE` 이용 중 · `RENEWAL_FAILED` 갱신 실패(이용 제한 예정) · `CANCELED` 해지 |
| 생각 유형 | `ANALYZE` 분석하기 · `EVALUATE` 따져 보기 · `CREATE` 새로 만들기 · `SOLVE` 문제 해결하기 · `REFLECT` 돌아보기 |
| 입력 방식 | `CHOICE` 선택지 · `ORDERING` 순서 · `CLASSIFICATION` 분류 · `NARRATIVE` 서술 · `SOLUTION_STEPS` 풀이 단계 · `ESSAY` 논술 |
| 출처 유형 | `RECORD` 기록 · `RULE` 규칙 · `ANSWER_KEY` 정답 키 · `AI_OBSERVATION` AI 관찰 |
| 생성 출처 | `LLM` · `LLM_RETRY` · `BANK` 질문 은행(되묻기) · `TEMPLATE` 규칙 응답(분석 대화)·템플릿 요약(리포트) (P16) |

### 1.6 공통 스키마
```jsonc
// Metric: 모든 건수·비율 (FN 1.3 수치 근거, FN-RPT-03)
{
  "label": "되묻기 후 생각을 더한 비율",
  "value": 0.6,                 // 분모 5 미만이면 null, count만 표시 (P08)
  "count": 3,
  "numerator": 3,
  "denominator": 5,
  "formula": "보완 답변 제출 시도 수 / 되묻기 받은 시도 수",
  "period": { "from": "2026-11-02", "to": "2026-11-08" },
  "sourceType": "RECORD",
  "state": "OK"                 // QueryState
}

// Evidence: 원문 근거 (FN-AGT-07)
{ "attemptId": "...", "missionTitle": "...", "answerId": "...", "answerVersion": 1,
  "submittedAt": "...", "quote": "아이 원문 일부", "available": true }   // 삭제 시 available=false

// Versions: 결과에 연결된 버전 (NFR-DAT-02)
// model: M2 활성 판정은 M2 버전, M2 미활성 판정·되묻기는 LLM 모델 ID(예: gpt-6.1-terra), 규칙 판정은 null
{ "mission": "m-12@3", "rubric": "r-12@2", "model": "m2-klue-narrative@1.0", "prompt": "judge@4" }
```

- SSE 이벤트

| event | data | 용도 |
|---|---|---|
| `status` | `{state, message}` | 처리 중 단계 안내 |
| `clarification` | `{question, options[]}` | 대상·기간 확인 요청 (FN-AGT-03) |
| `delta` | `{text}` | 답변 스트리밍 조각 (대조 전 임시 표시) |
| `result` | 엔드포인트별 최종 결과 | 대조 완료된 확정 결과 |
| `error` | Problem Details + `retryable` | 처리 실패 |
| `done` | `{}` | 스트림 종료 |

- heartbeat: 15초마다 주석 줄 `: ping` 전송 (CloudFront·ALB 유휴 타임아웃 방지, 클라이언트는 무시)
- 알림 스트림은 연결 직후 `event: ready`를 보내며, 재연결한 클라이언트는 `GET /notifications` 첫 페이지부터 재조회해 id로 병합 (2.7)

---

## 2. 공개 API 목록

### 2.1 계정·동의·자녀 (FN-ACC)
| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/consent-documents` | 공개 | 현재 이용 안내·동의 문서(버전) 조회 | ACC-02 | 제안 |
| GET | `/auth/google/authorize` | 공개 | Google 로그인·가입 시작 (Authorization Code + PKCE) | ACC-01, ACC-03 | 제안 |
| GET | `/auth/google/callback` | 공개 | Google 코드 교환·ID 토큰 검증 → refresh 쿠키 → web 복귀 | ACC-03 | 제안 |
| POST | `/auth/refresh` | 쿠키 | access token 재발급 | ACC-04 | 제안 |
| POST | `/auth/logout` | 인증 | refresh token 폐기 | ACC-04 | 제안 |
| POST | `/auth/student-sessions` | 학부모 | 학생 진입(동석): `{childId}` 연결 자녀 확인 후 학생 세션(`STUDENT` 토큰) 발급. 시연 링크·URL 식별값 진입 없음 (P01) | ACC-05 | 제안 |
| POST | `/auth/student/devices` | 공개 | 페어링 코드로 기기 등록 `{pairingCode, label}` → 기기 자격증명 쿠키 발급, 등록 자녀 프로필 반환 (P01, 3.11) | ACC-14 | 제안 |
| GET | `/auth/student/profiles` | 기기 쿠키 | 이 기기에 등록된 자녀 프로필 `{childId, nickname, pinSet, pinLocked}` (P01, `/children` 확장과 같은 필드명) | ACC-05 | 제안 |
| POST | `/auth/student/login` | 기기 쿠키 | 학생 진입(단독): `{childId, pin}` → 학생 세션(`STUDENT` 토큰) 발급. refresh 미발급 (P01, 3.11) | ACC-05 | 제안 |
| GET | `/me` | 인증 | 본인 정보·역할·관리자 권한 | ACC-09 | 우선1 |
| PATCH | `/me` | 인증 | 본인 정보 수정 | ACC-09 | 우선1 |
| POST | `/me/reauth` | 인증 | Google 재인증 시작 `{purpose, childId?, scope?}` → `{challengeId, authorizationUrl, expiresAt}`, callback 후 `{challengeId}`로 단기 `reauthToken` 수령 (5.6) | ACC-10 | 우선1 |
| GET | `/auth/google/reauth/callback` | 공개(재인증 상태 쿠키) | Google 재인증 callback → `{challengeId, status: VERIFIED}` (5.6) | ACC-10 | 우선1 |
| GET | `/me/consents` | 학부모 | 동의 이력(주체·문서 버전·시점·철회 상태) | ACC-02 | 제안 |
| POST | `/me/consents` | 학부모 | 현재 문서의 동의 항목 저장 `{consents:[{documentId,version,agreed}], childId?}`. 계정은 TERMS·PRIVACY, 자녀는 GUARDIAN | ACC-02 | 제안 |
| POST | `/me/consents/{consentId}/withdrawal` | 학부모 | 동의 철회. 필수 동의면 해당 자녀(또는 계정) 이용 차단 후 삭제·탈퇴 안내, 선택 동의면 해당 기능만 중단 (P09) | ACC-02 | 제안 |
| GET | `/children` | 학부모 | 연결 자녀 목록(닉네임·학년·기록 유무, 5.3). PIN 상태 `pinSet`·`pinLocked`는 실제 저장 상태로 반환. 빈 목록이면 자녀 등록 안내 | ACC-07, ACC-14 | 제안 |
| POST | `/children` | 학부모 | 자녀 프로필 등록 `{nickname, grade(3~6), birthYear}` + 법정대리인 동의(전원 만 14세 미만 간주). 3명 초과 시 409 (P01, P02, P03) | ACC-06, ACC-02 | 제안 |
| PATCH | `/children/{childId}` | 학부모 | 닉네임·학년(3~6) 수정 (학년은 이후 제공 문제에만 적용) | ACC-09 | 우선1 |
| PUT | `/children/{childId}/pin` | 학부모 | PIN 설정·변경 `{pin}` (`X-Reauth-Token`). 실패 횟수·잠금 해제 (P01) | ACC-14, ACC-10 | 제안 |
| POST | `/student-devices/pairings` | 학부모 | 1회용 페어링 코드 발급 `{childIds[]}` → `{pairingCode, expiresAt}` (10분, QR은 클라이언트가 코드로 생성) (P01) | ACC-14 | 제안 |
| GET | `/student-devices` | 학부모 | 등록 기기 목록 `{deviceId, label, children[], createdAt, lastUsedAt, expiresAt}` | ACC-14 | 제안 |
| DELETE | `/student-devices/{deviceId}` | 학부모 | 기기 등록 해제 → 이후 해당 기기 PIN 로그인 거부 | ACC-14 | 제안 |
| GET | `/children/{childId}/deletion-impact` | 학부모 | 연결 해제·프로필 삭제·기록 삭제별 범위·영향 안내 | ACC-11 | 우선2 |
| DELETE | `/children/{childId}/link` | 학부모 | 연결 해제 (`X-Reauth-Token`) | ACC-11, ACC-10 | 우선2 |
| POST | `/children/{childId}/deletion-requests` | 학부모 | 프로필·학습 기록 삭제 요청 `{scope: PROFILE\|RECORDS}` (`X-Reauth-Token`). 같은 요청에서 확정하고 `student.deleted` 발행, 별도 확인 API 없음. 사전 안내는 `deletion-impact` (P09) | ACC-11, ACC-13 | 우선2 |
| GET | `/children/{childId}/deletion-requests/{requestId}` | 학부모 | 삭제 요청 처리 상태 (5.6) | ACC-11 | 우선2 |
| GET | `/me/withdrawal/precheck` | 인증 | 탈퇴 전 진행 중 구독·미처리 환불·보관 거래(5년) 안내 (P09, P14) | ACC-12 | 우선2 |
| POST | `/me/withdrawal` | 인증 | 탈퇴 요청 (`X-Reauth-Token`). 진행 중 구독·미처리 환불이 있으면 409, 요청 즉시 처리·이후 로그인 불가 (P09) | ACC-12 | 우선2 |
| GET | `/me/withdrawal` | 인증 | 탈퇴 처리 상태 | ACC-12 | 우선2 |

- 삭제 후 처리 (FN-ACC-13)
  - 삭제가 끝난 기록은 학습·대화·리포트·대시보드 응답에서 제외
  - 근거로 참조된 경우에는 `available: false` 또는 `410 DATA_UNAVAILABLE` 반환
  - 다른 기록으로 대체하지 않음

### 2.2 미션 학습·판정·되묻기 (FN-LRN, FN-JDG)
| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/missions` | 학생 | 학년·입력 방식 범위의 공개 미션 목록(제목·교과·생각 유형·수행 상태), 진행 위치 | LRN-02, DSH-02 | 핵심 |
| GET | `/missions/{missionId}` | 학생 | 장면(애니메이션·정적 대체)·질문·안내·입력 방식 틀. 정답·예시 답 미포함 | LRN-03, LRN-05 | 핵심 |
| POST | `/missions/{missionId}/attempts` | 학생 | 학습 시도 시작. 신규 생성은 `201`, 진행 중 시도 반환(이어하기)은 `200`. core는 learning의 상태를 그대로 전달 | LRN-01, LRN-16 | 핵심 |
| GET | `/attempts/{attemptId}` | 학생 | 시도 상세: 상태, 최신 초안(`ETag`), 답변·판정·되묻기 타임라인, 가능한 다음 행동 | LRN-16, JDG-08, JDG-09 | 핵심 |
| PUT | `/attempts/{attemptId}/draft` | 학생 | 초안 자동 저장 (`If-Match`), 응답에 저장 시점·새 버전. `content: {answer, memo}` (P05) | LRN-15, LRN-16, LRN-17 | 우선1 |
| POST | `/attempts/{attemptId}/hints` | 학생 | 생각 열기 질문 열람 기록 → 질문 반환 (정답·제출용 답 미포함) | LRN-06 | 핵심 |
| POST | `/attempts/{attemptId}/answers` | 학생 | 답변 제출(최초·보완). 별도 버전 저장, 보완은 `followupId`에 연결. `Idempotency-Key` | LRN-04, LRN-05, LRN-08, LRN-09, LRN-10 | 핵심 |
| POST | `/answers/{answerId}/feedback` | 학생 | **SSE**. 판정 + 되묻기 생성. 이미 완료됐으면 저장된 결과 반환, `FAILED`면 재실행 | JDG-01~07, JDG-09, JDG-10 | 핵심 |
| POST | `/attempts/{attemptId}/finish` | 학생 | 마무리 → 정답(닫힌 문제)·예시 답(열린 문제)·근거 확인된 체크리스트 공개. 판정 `DONE` 1회 이상 아니면 409 (P04) | LRN-11, JDG-09 | 핵심 |
| POST | `/attempts/{attemptId}/self-assessment` | 학생 | 자기 체크 저장 → AI 확인 항목과 나란히 반환 (원본·판정 불변) | LRN-13 | 선택 |
| POST | `/attempts/{attemptId}/reflection` | 학생 | 돌아보기 `{difficulty(필수), text(선택)}` 저장 → 학습 완료 처리 (P04) | LRN-12, LRN-14 | 핵심 |

- #38 미션 조회의 `grade`·`demo`는 검증된 STUDENT의 연결된 활성 학생을 core DB에서 읽어 결정한다. 공개 요청의 동일 이름 query는 사용하지 않는다. 목록은 `page`·`size`만 learning에 전달하고, 상세도 같은 학생 학년·시연 여부를 붙인다. 학년별 문항 노출·시연 전용 미션 판단은 learning 소유다.

- 음성 시범(FN-LRN-18): 미구현 (P03)
- 질문 읽어주기(FN-LRN-19): 브라우저 TTS(Web Speech API), API 없음 (P03)
- 메모(FN-LRN-07): 초안 `content.memo`로 저장, 학생 본인 조회에만 포함 (P05)
- 되묻기·마무리 (P04)
  - 되묻기는 시도당 최대 2회, 2회째 답변 후 `nextActions: ["FINISH"]`
  - 고르기 `CORRECT`면 되묻기 없이 `nextActions: ["FINISH"]`
  - 되묻기에 답하지 않고 `FINISH` 가능("이대로 돌아보기")
- 무료 플랜 하루 신규 미션 시도 3개(P13). 일일 한도는 core Redis 카운터 책임(미구현)이며 신규 생성 `201`만 집계하고 이어하기 `200`은 집계하지 않음. 한도 도달 시 신규 생성만 `429 USAGE_LIMIT_REACHED`
- 목록 접기·펼치기(FN-LRN-20): 프론트 전용, API 없음
- 판정 규칙 (FN-JDG-01~05)
  - 고르기·수학 최종 답: 규칙 판정
  - 서술·논술: LLM 근거 추출 → 코드 원문 대조
  - 풀이 단계: 풀이는 LLM 근거 추출, 최종 답은 수학 동치 규칙으로 판정해 합침 (state-diagram 3.3). 최종 답 결과는 기준표 `FINAL_ANSWER` 요소로 기록. 단위는 비교하지 않고 미션 `answerUnit`으로 답 칸 뒤에 고정 표시 (FN-JDG-02)
  - 근거 없는 요소는 `satisfied: false`
  - 검증 전 결과는 `trial: true`("AI 채점(시범)")
  - 숫자 레벨은 응답에 포함하지 않음
- 판정 보류(`HELD`)와 처리 실패(`FAILED`)는 서로 다른 필드로 구분 (NFR-REL-04)

### 2.3 대시보드 (FN-DSH)

정식 공개 DTO는 core OpenAPI의 Dashboard 스키마, 내부 공급자 DTO는 learning OpenAPI의 Record 스키마(4.1).

- 기간: 아래 GET은 `from`·`to`를 함께 받음. 둘 다 생략하면 KST 오늘 포함 최근 7일, 한쪽만·역전·유효하지 않은 날짜(연도 0001~9999 밖 포함)는 400 `VALIDATION_FAILED`. 양 끝 포함, learning 조회 경계는 `[from 00:00 KST, to 다음날 00:00 KST)`. 응답 `period`는 learning 조회 결과 그대로
- 목록: `page` 0 이상, `size` 1~100(기본 20), `status`는 생략 또는 `IN_PROGRESS`·`COMPLETED`. 상세의 기간은 화면 범위 메타데이터이며 답변 이력을 자르지 않음
- 식별자: 내부 records 응답은 역할과 무관하게 `studentId`, core가 학부모 요약·유형·목록의 최상위 식별자만 `childId`로 바꿈. 내부 studentId는 검증된 STUDENT scope 또는 현재 연결·활성·동의를 확인한 자녀
- 학생 home: core 학생 프로필 + learning `records/.../home`. resume는 draft·memo 없이 식별만 하고, core가 학생 전용 `/internal/attempts/{attemptId}`로 본인 초안을 붙임. 두 번째 조회 실패도 홈 조회 실패(부분 성공·빈 이어하기로 대체하지 않음). 집계·미션 선정은 learning 소유
- 계약 오류: Metric 필수 값·타입, 다섯 생각 유형 누락·중복은 502 `LEARNING_CONTRACT_INVALID`(수치 보충 없음). 공급자 조회 실패는 오류이며 `NO_RECORD`가 아님
- 표시 필드: `completedAt`·`hintUsages`·`reflection.createdAt` 보존. `finishedAt`은 마무리 공개 시각, `completedAt`은 돌아보기 완료 시각(그 전에는 null), reflection이 있으면 `createdAt` 필수. 학부모 상세는 Attempt에 `state`·`period`를 더하고 draft·memo 제외. `thinking-activities`는 `{studentId,state,period,items:[{attemptId,thinkingType,missionTitle,reflection}]}`. reflection의 `EASY/NORMAL/HARD`·nullable text는 프론트 표시 경계에서 한국어 선택값으로 변환
- `students/me/preferences`는 3.12 목업

| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/students/me/home` | 학생 | 학생 정보, 이어할 시도, 시작 가능한 미션 경로 | DSH-01, DSH-02 | 제안 |
| GET | `/students/me/attempts` | 학생 | 최근 학습 기록(미션·시점·완료 여부, `status` 필터) | DSH-03, LRN-16 | 제안 |
| GET | `/students/me/thinking-activities` | 학생 | 수행 미션의 생각 유형·본인 돌아보기 (레벨·등급·순위 없음) | DSH-04 | 제안 |
| GET·PUT | `/students/me/preferences` | 학생 | 생각 지도 테마·동행 캐릭터 설정 (3.12) | - | 제안 |
| GET | `/children/{childId}/summary?from&to` | 학부모 | 학습 건수·상태 `Metric[]`, 집계 기준·기간 (P08) | DSH-06, DSH-07, DSH-10 | 제안 |
| GET | `/children/{childId}/thinking-types?from&to` | 학부모 | 다섯 유형별 미션·기록, 없는 유형은 `NO_RECORD`("미관찰") | DSH-08 | 제안 |
| GET | `/children/{childId}/attempts?from&to` | 학부모 | 기간 내 학습 목록 | DSH-07, DSH-09 | 제안 |
| GET | `/children/{childId}/attempts/{attemptId}` | 학부모 | 최초 답변·되묻기·추가 답변·도움 이용·돌아보기 원문 연결 | DSH-09 | 제안 |

- 모든 응답에 `state`(QueryState)와 `period` 포함
- 기록 없음과 조회 실패를 구분하고, 미확인 수치는 채우지 않음 (FN-DSH-05, FN-DSH-11)

### 2.4 분석 대화 (FN-AGT)
| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| POST | `/conversations` | 학부모 | 대화 생성 `{childId, from, to}` (기본 기간 최근 7일·오늘 포함, P06). 무료 플랜은 `USAGE_LIMIT_REACHED` (P13) | AGT-01 | 핵심 |
| GET | `/conversations?childId` | 학부모 | 본인 대화 목록 | AGT-11 | 핵심 |
| GET | `/conversations/{conversationId}` | 학부모 | 질문·답변·대상 자녀·기간·참조 기록 | AGT-11 | 핵심 |
| POST | `/conversations/{conversationId}/messages` | 학부모 | **SSE**. 질문 → 범위 확인 → 기록 조회·계산 → 숫자·인용 대조 → 확정 답변. 범위 변경 시 `scope` 동봉 | AGT-02~06, AGT-08~10 | 핵심 |
| POST | `/conversations/{conversationId}/messages/{messageId}/retry` | 학부모 | **SSE**. 실패한 질문 재처리 | AGT-10 | 핵심 |
| GET | `/conversations/{conversationId}/messages/{messageId}/evidence` | 학부모 | 답변 근거(미션·답변 시점·원문, 전후 답변 연결) | AGT-07 | 핵심 |
| GET | `/agent/example-questions?childId` | 학부모 | 예시 질문(숫자·유형별 활동·아이가 쓴 생각·전후 변화·돌아보기·수학 점검), 가능 여부 표시 | AGT-12 | 선택 |

- 예시 질문(FN-AGT-12): core `conversation`이 learning `/internal/records/...`로 기록 유무 확인 후 가능 여부 표시
- 대화 이력은 이용 중 보관, 탈퇴·자녀 삭제 시 파기. 삭제된 근거는 `available: false` (P09)
- 대조 실패·LLM 장애 시 LLM 답변을 보내지 않고 규칙 응답 모드 결과를 보냄 (3.3, FN-AGT-06·10, P16)

### 2.5 주간 리포트 (FN-RPT)
| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/children/{childId}/reports?status` | 학부모 | 대상 주·생성 상태별 목록 | RPT-10, RPT-11 | 핵심 |
| GET | `/reports/{reportId}?revision` | 학부모 | 상세: 기간·포함 기준·`Metric[]`·생각 유형 요약·전후 변화·돌아보기·원문 인용·저녁 질문·버전. 기본 최신판, `revision`으로 이전판 조회 (P06) | RPT-02~10, RPT-12 | 핵심 |
| GET | `/reports/{reportId}/evidence/{itemId}` | 학부모 | 리포트 항목의 원본 기록 | RPT-03, RPT-12 | 핵심 |
| GET | `/reports/{reportId}/download?format=pdf\|md` | 학부모 | 권한 확인 후 `{url, expiresAt}`(단기 presigned URL) 반환, 웹이 해당 URL로 이동. Bearer 인증이라 302 대신 JSON (PDF·Markdown, P06) | RPT-13 | 핵심 |
| POST | `/reports/{reportId}/regenerate` | 학부모·관리자 | 같은 주 재생성 → `report.generate`, 새 판(`revision + 1`) 추가·기존 판 보존. 학부모 리포트당 1회(초과 409), 관리자 무제한 (P06) | RPT-12 | 핵심 |

- 자동 생성(FN-RPT-01)은 core 스케줄러가 매주 월요일 07:00 KST에 직전 월~일(KST) 대상으로 수행하며 공개 API는 없음 (P06)
- 생성 내용(FN-RPT-02~09)은 report-service가 계산하고, 그 결과를 상세 응답 스키마(3.4)로 제공
- 기록 없는 주·표본 부족 주는 `COMPLETED` + `state: NO_RECORD|INSUFFICIENT_SAMPLE`로 표시하며, 생성 실패(`FAILED`)와 구분 (FN-RPT-11). `NO_RECORD`는 LLM 미호출 (P06)
- 무료 플랜은 수치만 제공(`narrative: null`, 생각 유형 `summary` 없음) (P13)

### 2.6 결제·구독 (FN-PAY) — 토스페이먼츠 테스트 환경만
| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/products` | 공개 | 상품 목록(무료·프리미엄 월 14,900원): 가격·청구 주기·기능·사용 한도·대상 자녀 수·기간. 값은 `product` 데이터 (P13) | PAY-01 | 우선2 |
| POST | `/orders` | 학부모 | 결제 요청 생성 `{productId, childId}` → `orderId`·금액·위젯 파라미터. 중복 구독 409. `Idempotency-Key` | PAY-02, PAY-03 | 우선2 |
| POST | `/payments/confirm` | 학부모 | 위젯 성공 리다이렉트 값(`paymentKey, orderId, amount`)으로 서버 승인 → 금액 대조 → 구독·권한 반영. `Idempotency-Key` | PAY-03, PAY-04, PAY-05 | 우선2 |
| GET | `/payments/{orderId}` | 학부모 | 결제 상태 (`CONFIRMING`이면 PG 상태 조회 후 갱신) | PAY-04 | 우선2 |
| GET | `/payments` | 학부모 | 본인 거래 내역(결제·취소·환불) | PAY-07 | 우선2 |
| GET | `/subscriptions` | 학부모 | 구독 상태·대상 자녀·이용 기간·다음 결제 예정일 | PAY-07 | 우선2 |
| POST | `/subscriptions/{subscriptionId}/billing-key` | 학부모 | 자동결제 수단 등록·변경 (PG `authKey` → 빌링키 발급, 카드 정보 미저장) | PAY-08 | 우선2 |
| DELETE | `/subscriptions/{subscriptionId}/auto-renewal` | 학부모 | 자동 갱신 해지, 해지 시점·남은 기간 반환. `period_end`까지 이용 유지 (P14) | PAY-09 | 우선2 |
| PUT | `/subscriptions/{subscriptionId}/auto-renewal` | 학부모 | 해지 철회(자동 갱신 재설정), `period_end` 전 `ACTIVE` 구독만 (P14) | PAY-09 | 우선2 |
| POST | `/payments/{paymentId}/refund-requests` | 학부모 | 취소·환불 요청, `Idempotency-Key`. 결제 7일 이내 + 프리미엄 기능 미사용 시 전액만(부분 환불 없음), 아니면 409 (P14) | PAY-10 | 우선2 |
| POST | `/webhooks/tosspayments` | PG | 상태 변경 통지. 본문을 신뢰하지 않고 PG 조회 API로 재확인 후 1회 반영 | PAY-04, PAY-06 | 우선2 |

- 정기 청구(FN-PAY-06)는 core 스케줄러가 수행하며 공개 API는 없음
  - 매일 09:00 KST, 최초 결제일 기준 매월 같은 날(없으면 말일) 도래 구독을 빌링키로 자동결제 (P13)
  - 결과를 거래별로 기록
  - 실패 시 `RENEWAL_FAILED`, 유예 3일 동안 이용 유지·매일 1회 최대 3회 재청구, 모두 실패 시 `CANCELED` (P13)
- 화면 복귀만으로 결제 완료를 판단하지 않음. 결과가 불명확하면 `CONFIRMING`으로 두고 재결제를 안내하지 않음

### 2.7 신고·지원·알림 (FN-SUP)
| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| POST | `/error-reports` | 학생·학부모 | 오류 신고 `{targetType: FOLLOWUP\|JUDGMENT\|ANALYSIS\|REPORT, targetId, category, comment}` (`category`: `WRONG_JUDGMENT` 판정이 틀려요 · `ODD_QUESTION` 질문이 이상해요 · `MISMATCH` 숫자·인용이 달라요 · `INAPPROPRIATE` 부적절한 표현 · `OTHER` 기타, P10) | SUP-01 | 우선1 |
| GET | `/error-reports` | 학생·학부모 | 본인 신고 목록·상태 | SUP-04 | 우선1 |
| GET | `/error-reports/{reportId}` | 학생·학부모 | 상태·허용된 처리 결과 | SUP-04 | 우선1 |
| GET | `/help?role` | 인증 | 역할별 도움말·최초 이용 안내 | SUP-05 | 우선2 |
| POST | `/inquiries` | 학생·학부모 | 계정·이용·결제 문의 | SUP-06 | 우선2 |
| GET | `/inquiries`, `/inquiries/{inquiryId}` | 학생·학부모 | 본인 문의 상태·답변 | SUP-06 | 우선2 |
| GET | `/notices` | 인증 | 대상 역할·공개 기간 내 공지·점검 안내 | SUP-07 | 우선2 |
| GET | `/notifications?unreadOnly` | 인증 | 본인 알림 목록 (자녀별 사건은 `childId` 포함) | SUP-09 | 우선2 |
| PATCH | `/notifications/{notificationId}/read` | 인증 | 읽음 처리 | SUP-09 | 우선2 |
| POST | `/notifications/read-all` | 인증 | 전체 읽음 | SUP-09 | 우선2 |
| GET | `/notifications/stream` | 인증 | **SSE**. 새 알림 (`event: notification`) | SUP-08 | 우선2 |
| GET | `/notification-settings` | 인증 | 알림 유형별 수신 설정 (앱 내 알림만, P10) | SUP-10 | 우선2 |
| PUT | `/notification-settings` | 인증 | 수신 설정 변경 (유형별 on/off, 이메일·푸시 없음, P10) | SUP-10 | 우선2 |

- #44 권한: 학생 세션의 account.id는 보호자 ID를 공유하므로 학생은 모든 알림/설정 API에서 403이다. PARENT·ADMIN은 인증된 본인 계정만 사용하며 userId 입력을 받지 않는다. 학생 전용 알림함은 현재 제공하지 않는다.
- 목록: `GET /notifications?unreadOnly=false&page=0&size=20` → `{items:[{id,childId,type,title,link,readAt,createdAt}],page,size,hasNext}`. size 1~100, 최신 createdAt·id 내림차순. 읽음 PATCH와 전체 읽음 POST는 204, 반복해도 최초 readAt 유지, 타인/없는 ID는 404.
- 설정: GET → `{items:[{type,enabled}]}`, PUT도 동일한 객체(1~6개 중복 없는 유형)로 지정 유형만 갱신하고 전체 유효 설정을 반환. 미저장 유형 기본 true, 채널은 IN_APP 고정. 유형은 REPORT_COMPLETED, REPORT_FAILED, ERROR_REPORT_RESOLVED, INQUIRY_ANSWERED, PAYMENT_CHANGED, SUBSCRIPTION_CHANGED. 수신 거부는 이후 알림 생성을 막으며 기존 알림은 보존한다.
- 리포트 실패는 REPORT_FAILED로 독립 설정한다. 완료·실패 모두 현재 연결·동의가 유효한 보호자에게 생성한다. 상세 링크 권한은 이동 시 다시 검사한다. 실패 링크는 리포트 목록으로 이동한다.
- SSE는 `event: notification`에 목록 항목과 같은 데이터를 전송한다. 15초 `: ping`, 최대 5분 후 재연결. 각 전송·heartbeat에서 세션/동의를 재검사하고 만료·폐기 시 연결을 닫는다. 학생으로 역할을 바꾸면 기존 보호자 구독도 폐기된 세션 검사로 닫힌다.
- 구독 준비 후 `event: ready`를 받으면 목록 API를 첫 페이지부터 재조회해 id로 병합한다. 연결 중에도 주기적으로 목록을 동기화한다. Last-Event-ID 재생은 제공하지 않는다. Redis Pub/Sub은 유실 가능하며 SSE를 영구 전달 보장으로 사용하지 않는다.
- DB 저장이 원본이다. 커밋 이후 Redis에 발행하며 발행 실패는 DB 전달 상태 FAILED/REDIS_PUBLISH_FAILED와 로그로 기록한다. COMPLETED는 Redis 발행 성공이며 브라우저 수신 확인이 아니다(구독자 0명도 발행 성공). 프로세스가 커밋 직후 종료되면 QUEUED로 남아도 목록에서 조회된다. 발행 실패 때문에 리포트 상태를 되돌리지 않는다.

- 알림 생성(FN-SUP-08)은 내부 사건(리포트 완료·실패, 신고·문의 처리, 구독·결제 변경)에서 발생
  - 사건 ID 기준으로 1회만 생성
  - 알림 본문에는 학생 원문·결제 민감 정보를 넣지 않고 상세 화면 링크만 담음 (FN-SUP-11)

### 2.8 관리자 (FN-ADM, FN-SUP 관리 측) — `/api/v1/admin`

#### #47 구현 계약

- overview·audit-logs의 정확한 GET 경로는 ADMIN 역할, jobs·queues·retry는 SERVICE_OPS, missions는 CONTENT다. 다른 관리자 경로의 기존 권한은 유지한다.
- overview/jobs/audit 기간은 KST 날짜 양 끝 포함(저장 조회는 시작 이상·다음날 미만), 둘 다 생략하면 최근 7일, 한쪽만 입력하거나 역순·366일 초과는 400. page=0, size=20(1~100), page 최대 1000. 정렬은 createdAt DESC, id DESC다.
- overview는 `{period,inclusionRule,learning:{attempts,completedAttempts,students,inclusionRule},jobCounts:[{type,status,count}]}`다. learning은 P08, core 작업은 생성 시각이 기간 안인 작업의 현재 상태를 센다. 미션 상태 집계 공급자는 없어 숫자를 만들지 않는다. learning 장애/계약 위반은 오류다.
- jobs는 `{items,page,size,totalElements}`, 상세는 `{jobId,type,status,retryCount,failureReason,createdAt,executions,retryable,retryUnavailableReason}`다. CONVERSATION ID는 conversation_message.id, REPORT는 report_job.id, NOTIFICATION은 notification.id다. updatedAt은 존재하지 않아 반환하지 않는다. executions는 실제 job_execution을 attemptNo 순으로 반환한다. error_detail·원문 실패 메시지·감사 detail은 공개하지 않고 알려진 오류 코드만 노출하며 그 외는 REDACTED_ERROR다. UUID가 종류 간 충돌하면 409 JOB_ID_AMBIGUOUS다.
- retry는 UUID Idempotency-Key 필수, 실패 상태만 허용한다. NOTIFICATION은 동일 ID를 RUNNING으로 원자 선점하고 새 job_execution을 남긴 뒤 트랜잭션 밖에서 기존 Redis publisher/DeliveryService를 호출한다. Redis 확인은 브라우저 수신 확인이 아니다. 실제 결과를 200 작업 상세로 반환하고 감사 기록을 남긴다. RUNNING 고착은 자동 재실행하지 않는다. REPORT는 기존 소비자가 실패 jobId를 재실행하지 않고 core lifecycle도 종료 상태이므로 503 JOB_RETRY_UNAVAILABLE, CONVERSATION도 관리자 재처리 공급자 부재로 같은 오류다. 리포트 regenerate를 대신 호출하지 않는다. 실패한 요청은 실행 이력으로 위장하지 않으며 거절 감사만 남긴다.
- audit-logs는 targetType/targetId 및 기간·페이지 필터. 항목은 `{id,actorUserId,action,targetType,targetId,result,createdAt}`이며 자유형 detail은 노출하지 않는다. 기존 감사 저장 경로를 교체하지 않는다.
- queues는 `{vhost,items:[{name,kind:WORK|RETRY|DLQ,messages,messagesReady,messagesUnacknowledged,consumers,state}]}`다. definitions.json의 `/` vhost와 고정 25개 큐만 읽는다. 누락·인증·HTTP·타임아웃·잘못된 응답은 명시적인 503/504이며 0으로 치환하지 않는다. `ADMIN_RABBIT_MANAGEMENT_URL`, `ADMIN_RABBIT_MANAGEMENT_USERNAME`, `ADMIN_RABBIT_MANAGEMENT_PASSWORD`를 환경에서 읽는다(기본 자격 증명 없음). 기존 AMQP 설정과 독립이며 production 의존성은 추가하지 않는다.
- missions는 표의 명시된 메서드/경로만 `/internal/admin/missions`로 프록시한다. 검증된 ADMIN 사용자 컨텍스트, 빈 학생 범위, 내부 토큰과 trace를 기존 LearningClient/InternalRestClientFactory로 전달한다. JSON object 본문과 목록 status/grade/thinkingType/page/size만 전달한다. 버전·기준표·검토·게시 정책/DTO는 learning 소유다. 현재 실제 공급자/OpenAPI가 없으므로 본문/응답은 JSON object 중계 계약이고 테스트 HTTP 대역으로 선개발한다. 404/405/501은 503 ADMIN_MISSIONS_UNAVAILABLE, 나머지 Problem Details는 code/status와 구조화된 missingFields만 허용하며 자유형 오류 문구는 전달하지 않는다. 성공 응답은 learning 관리자 콘텐츠 계약을 그대로 반환한다. 서비스 간 재시도는 없다.

| Method | Path | 권한 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/admin/overview?from&to` | 관리자 | 학습 시도·완료 건수, 대화·리포트 처리 현황, 미션 공개 현황 (학생 원문 없음) | ADM-01, ADM-02, ADM-04 | 제안 |
| GET | `/admin/jobs?type=CONVERSATION\|REPORT\|NOTIFICATION&status` | SERVICE_OPS | 작업 상태별 목록, 요약 수치 → 상세 이동 | ADM-03, ADM-05, SUP-11 | 제안 |
| GET | `/admin/jobs/{jobId}` | SERVICE_OPS | 실패 원인·처리 이력 | ADM-07 | 제안 |
| POST | `/admin/jobs/{jobId}/retry` | SERVICE_OPS | 권한·중복 확인 후 재처리, 실제 결과로 갱신 (`SERVICE_OPS` 전원, `audit_log`, P07). `Idempotency-Key` | ADM-07, SUP-11 | 제안 |
| GET | `/admin/queues` | SERVICE_OPS | 큐 길이·DLQ 적재 현황 | ADM-03 | 제안 |
| GET | `/admin/audit-logs?targetType&from&to` | 관리자 | 운영 조치·콘텐츠 변경 이력(수행자·대상·시점·결과) | ADM-06, ADM-13 | 제안 |
| GET | `/admin/missions?status&grade&thinkingType` | CONTENT | 미션 목록·상태별 건수 | ADM-04, ADM-08 | 제안 |
| POST | `/admin/missions` | CONTENT | 미션 작성 (학년·생각 유형·입력 방식·장면·질문·교과·성취기준, 시연 전용 여부) | ADM-09 | 제안 |
| GET | `/admin/missions/{missionId}` | CONTENT | 미션 상세·버전 이력 | ADM-09, ADM-10 | 제안 |
| PATCH | `/admin/missions/{missionId}` | CONTENT | 미션 수정 (새 버전 생성, 기존 학습은 당시 버전 유지) | ADM-09, ADM-12 | 제안 |
| PUT | `/admin/missions/{missionId}/rubric` | CONTENT | 기준표(요소·배점·흔한 오답)·정답·예시 답·들어가면 좋은 생각·생각 열기 질문 → 새 기준 버전 | ADM-10 | 제안 |
| GET | `/admin/missions/{missionId}/preview` | CONTENT | 학생 화면 미리보기 데이터 | ADM-09 | 제안 |
| POST | `/admin/missions/{missionId}/review-request` | CONTENT | 검토 요청 `DRAFT → REVIEW_REQUIRED` (현재 미션·기준표 버전 필요) (P07) | ADM-11 | 제안 |
| POST | `/admin/missions/{missionId}/review` | CONTENT | 검토 결과 기록, `CONTENT` 1인 가능(작성자 포함) (P07) | ADM-11 | 제안 |
| POST | `/admin/missions/{missionId}/publish` | CONTENT | 게시, 필수 누락 시 422. 재게시 시 새 버전이 신규 시도부터 적용, 진행 중 시도는 시작 당시 버전 유지 (P07) | ADM-11 | 제안 |
| POST | `/admin/missions/{missionId}/unpublish` | CONTENT | 신규 제공 중단 (진행 중 시도는 시작 당시 버전으로 계속, P07) | ADM-12 | 제안 |
| GET | `/admin/error-reports?status` | SERVICE_OPS | 신고 목록·상태별 | SUP-02 | 우선1 |
| GET | `/admin/error-reports/{reportId}` | SERVICE_OPS | 신고 상세 + 연결 시도의 답변·판정 원문 (열람마다 `audit_log`, P07) | SUP-02 | 우선1 |
| PATCH | `/admin/error-reports/{reportId}` | SERVICE_OPS | 상태·검토 결과·처리 이유 (접수만으로 판정 변경 없음) | SUP-02 | 우선1 |
| POST | `/admin/error-reports/{reportId}/corrections` | SERVICE_OPS | 정정: 기존 결과·사유·시점 보존, 영향받는 대화·집계·리포트 반영 여부 (원본 답변 불변) | SUP-03 | 우선1 |
| GET | `/admin/inquiries?status` | SERVICE_OPS | 문의 목록 | SUP-06 | 우선2 |
| POST | `/admin/inquiries/{inquiryId}/answer` | SERVICE_OPS | 문의 답변 | SUP-06 | 우선2 |
| POST / PATCH / DELETE | `/admin/notices`, `/admin/notices/{noticeId}` | SERVICE_OPS | 공지 등록·수정·종료 (공개 기간·대상 역할) | SUP-07 | 우선2 |
| GET | `/admin/payments?status&from&to` | PAYMENT_VIEW | 결제·구독 상태, 대상 자녀 권한 반영 여부 | ADM-14 | 우선2 |
| GET | `/admin/payments/reconciliation?from&to` | PAYMENT_VIEW | 내부 기록 vs PG 상태 대조, 누락·중복·불일치 분리 | ADM-15 | 우선2 |
| GET | `/admin/refund-requests?status` | PAYMENT_VIEW | 환불 요청 목록 | ADM-16 | 우선2 |
| POST | `/admin/refund-requests/{requestId}/approve` | PAYMENT_REFUND | 대상·금액·사유 확인 후 PG 취소, 결과·수행자 기록. `Idempotency-Key` | ADM-16 | 우선2 |
| POST | `/admin/refund-requests/{requestId}/reject` | PAYMENT_REFUND | 반려 사유 기록 | ADM-16 | 우선2 |
| GET | `/admin/model-versions?kind=RUBRIC\|MODEL\|PROMPT\|GENERATION` | SERVICE_OPS | 버전 목록·활성 상태·평가 결과 | ADM-17 | 우선1 |
| POST | `/admin/model-versions` | SERVICE_OPS | 버전 등록 (평가 기록 첨부) | ADM-17 | 우선1 |
| POST | `/admin/model-versions/{versionId}/activate` | SERVICE_OPS | 승인 조건(NFR-AIQ-05) 확인 후 활성화 → `model.version.activated` | ADM-18 | 우선1 |
| POST | `/admin/model-versions/{versionId}/rollback` | SERVICE_OPS | 이전 승인 버전 복귀, 재분석 여부 기록 | ADM-18 | 우선1 |
| GET | `/admin/ai-usage?from&to&callType` | SERVICE_OPS | 되묻기·판정·분석·리포트별 호출량·실패·지연·토큰·비용 (요금제 한도 P13, 월 LLM 비용 예산 80% 경보 P10) | ADM-19 | 우선1 |

---

## 3. 주요 요청·응답

### 3.1 답변 제출 — `POST /attempts/{attemptId}/answers`
```http
Idempotency-Key: 5c0e...  
```
```jsonc
// 요청: 서술(최초 답변)
{ "inputType": "NARRATIVE", "text": "나는 ...라고 생각해. 왜냐하면 ...", "dictatedByGuardian": false }
// 요청: 보완 답변 (되묻기에 대한 답)
{ "inputType": "ESSAY", "followupId": "f-31",
  "essay": { "claim": "...", "reasons": ["...", "..."], "rebuttal": "..." } }
// 요청: 고르기
{ "inputType": "ORDERING", "choiceIds": ["c3", "c1", "c2"] }
```
```jsonc
// 201 Created
{ "answerId": "a-102", "attemptId": "t-7", "version": 2, "followupId": "f-31",
  "submittedAt": "2026-11-03T19:12:04+09:00",
  "feedback": { "status": "PENDING" } }
```

### 3.2 피드백 — `POST /answers/{answerId}/feedback` (SSE)
```
event: status
data: {"state":"RUNNING","message":"생각을 살펴보는 중"}

event: result
data: {
  "status":"DONE",
  "judgment":{
    "result":"PARTIAL", "trial":true,
    "elements":[
      {"elementId":"e1","label":"주장","satisfied":true,"quote":"나는 ...라고 생각해","sourceType":"AI_OBSERVATION"},
      {"elementId":"e2","label":"까닭","satisfied":false,"quote":null}
    ],
    "heldReason":null
  },
  "followup":{"followupId":"f-32","type":"TELL_MORE","question":"왜 그렇게 생각했는지 하나 더 말해 볼까?","source":"LLM"},
  "nextActions":["ANSWER_FOLLOWUP","FINISH"],
  "versions":{"mission":"m-12@3","rubric":"r-12@2","model":"gpt-6.1-terra","prompt":"judge@4"}
}

event: done
data: {}
```
- 보류인 경우: `judgment.result: "HELD"`, `heldReason`(`INSUFFICIENT_EVIDENCE`·`QUOTE_MISMATCH`·`TOO_SHORT`·`UNVERIFIED_SCOPE`, M2·M1 교차 확인 활성 시 `MODEL_DISAGREEMENT`·`LOW_CONFIDENCE` 추가(#69, 현재 ai는 앞 4종만 반환))
- 실패한 경우
  - `event: error` 데이터: `{"code":"AI_UNAVAILABLE","retryable":true}`
  - 답변은 저장된 상태로 유지
  - 같은 엔드포인트를 다시 호출해 재시도 (상태별 처리는 1.4)
- 클라이언트 연결이 끊겨도 처리는 끝까지 진행·저장, 재요청 시 저장 결과 반환
- core 중계 계약(#39): 인증·학생 범위 검사는 스트림 시작 전에 수행한다. `status(RUNNING)` 후 learning 동기 응답을 기다리고, `DONE`은 응답 전체를 `result`로 전달한다(`HELD` 포함). learning이 이미 `RUNNING`을 반환하면 `status`만 전달하고 종료한다. 정상·실패·이미 처리 중인 경우 모두 마지막에 `done: {}`를 한 번 전송하고 연결을 닫는다. 전송 불가능한 연결에는 종료 이벤트 전달을 보장할 수 없다.
- 내부 응답: `200 application/json`의 `status`는 `DONE` 또는 `RUNNING`이다. `DONE` 결과는 위 3.2 형태이며 `RUNNING`은 4.1과 동일한 `{status:"RUNNING", judgment:null, followup:null, nextActions:[], versions:null}`이다. 내부 message 필드는 없으며 공개 status의 message는 core가 작성한다. 업무·처리 실패는 비-2xx Problem Details(+`retryable`)로 반환한다. core는 확장 필드를 보존하며, 잘못된 JSON·알 수 없는 성공 상태는 `502 LEARNING_INVALID_RESPONSE`로 전달한다. 판정 상태 전이·저장은 learning만 수행한다.
- 스트림 시작 뒤 learning HTTP 오류·연결 실패·80초 시간 초과는 `error`(Problem Details + `retryable`) → `done`이다. 내부 Problem Details는 원래 code·확장 필드를 유지하고, `retryable`이 없으면 5xx·429만 true로 보충한다. core 연결 장애는 `503 LEARNING_UNAVAILABLE`, 시간 초과는 `504 LEARNING_TIMEOUT`, 서킷 차단은 `503 LEARNING_CIRCUIT_OPEN`이다. 성공 fallback·core 피드백 캐시는 없다.
- 피드백 전용 `learning-feedback` 서킷은 전송 오류·시간 초과·계약된 Problem Details가 아닌 5xx를 실패로 센다. 5xx여도 Content-Type이 `application/problem+json`이고 JSON 객체에 비어 있지 않은 문자열 `code`가 있으면 learning이 반환한 업무/처리 오류로 보고 서킷 실패에는 포함하지 않는다. `AI_UNAVAILABLE`·`INTERNAL_ERROR`는 계속 error 이벤트이며 성공으로 바꾸지 않는다. AI 서킷·FAILED 재실행은 learning 소유이고, core가 AI 업무 실패를 다시 30초 차단하지 않는다. 일반 JSON의 `learning-json` 집계는 기존대로 유지한다.
- 스트림 시작 전 인증 DB/세션 조회 장애는 실제 PublicAuthFilter가 HTTP `503 AUTH_UNAVAILABLE` Problem Details로 반환한다. learning 서킷·연결 오류는 스트림 시작 뒤 error 이벤트에만 담는다.
- SSE 연결 타임아웃은 90초로 내부 80초보다 길다. 15초 주석 heartbeat는 연결 종료 시 해제하지만 이미 시작한 learning 호출은 취소하지 않는다. 검증된 컨텍스트를 복사해 virtual thread에 명시적으로 설정하고 finally에서 제거한다. executor는 앱 생명주기에 맞춰 종료하며 heartbeat 전송 대기가 다른 연결의 heartbeat를 막지 않게 한다.

### 3.3 분석 대화 — `POST /conversations/{conversationId}/messages` (SSE)
```jsonc
// 요청 (scope 생략 시 대화의 확인된 자녀·기간 유지)
{ "question": "질문을 받고 뭐가 달라졌어?", "scope": { "from": "2026-10-27", "to": "2026-11-08" } }
```
```
event: status
data: {"state":"RUNNING","message":"기록을 조회하는 중"}

event: delta
data: {"text":"되묻기를 받은 5번 중 3번 ..."}

event: result
data: {
  "messageId":"msg-9",
  "answer":"되묻기를 받은 5번 중 3번 생각을 더 썼어요. ...",
  "scope":{"childId":"s-1","from":"2026-10-27","to":"2026-11-08","changed":true},
  "metrics":[{ "label":"되묻기 후 생각을 더한 비율","count":3,"numerator":3,"denominator":5,"value":0.6,
               "formula":"보완 답변 제출 시도 수 / 되묻기 받은 시도 수","period":{"from":"2026-10-27","to":"2026-11-08"},
               "sourceType":"RECORD","state":"OK" }],
  "evidence":[{"attemptId":"t-7","missionTitle":"...","answerId":"a-102","answerVersion":2,"quote":"...","available":true}],
  "verification":{"numbersMatched":true,"quotesMatched":true},
  "recordCount":5
}

event: done
data: {}
```
- 범위가 불명확한 경우
  - `event: clarification`을 보내고 스트림 종료
  - 사용자 선택을 `scope`에 담아 다시 질문
- 대조 실패·LLM 장애: 규칙 응답 모드 (P16)
  - `delta`로 보낸 임시 텍스트는 폐기
  - `event: result`에 계산된 `metrics`·`evidence`만 템플릿 문장으로 담고 `"source":"TEMPLATE"`, `"fallback":{"reason":"VERIFICATION_FAILED|AI_UNAVAILABLE"}` 표시
  - 기록 조회 자체가 실패하면 `event: error`

### 3.4 리포트 상세 — `GET /reports/{reportId}`
```jsonc
{
  "reportId": "r-44", "childId": "s-1", "status": "COMPLETED", "state": "OK",
  "period": { "from": "2026-11-02", "to": "2026-11-08" },
  "revision": 1, "revisions": [{ "revision": 1, "generatedAt": "2026-11-09T07:00:00+09:00" }],
  "inclusionRule": "기간 내 답변 제출이 있는 시도(미완료 포함), 처리 실패만 있는 시도·삭제 기록 제외",
  "metrics": [ /* Metric[] */ ],
  "thinkingTypes": [
    { "type": "ANALYZE", "state": "OK", "missions": [{ "attemptId": "t-7", "title": "..." }], "summary": "..." },
    { "type": "CREATE", "state": "NO_RECORD", "summary": "확인된 기록 없음" }
  ],
  "changes": [{ "attemptId": "t-7", "followup": "...", "first": { "answerId": "a-101", "text": "..." },
                "revised": { "answerId": "a-102", "text": "..." },
                "counts": { "chars": [42, 88], "sentences": [2, 4], "reasonConnectives": [0, 2] } }],
  "reflections": [{ "attemptId": "t-7", "difficulty": "보통", "text": "...", "written": true }],
  "quotes": [{ "attemptId": "t-7", "answerId": "a-102", "text": "...", "verified": true }],
  "eveningQuestion": "...",
  "narrative": { "text": "...", "source": "LLM", "modelExplanation": null },   // 대조 실패 시 source=TEMPLATE (P16), 무료 플랜은 null (P13)
  "verification": { "numbersMatched": true, "quotesMatched": true },
  "versions": { "prompt": "report@2", "model": null },
  "generatedAt": "2026-11-09T07:00:00+09:00"
}
```

- 리포트 상세의 `reflections[].difficulty`는 표시값 `쉬웠어요`·`보통`·`어려웠어요`이며 PDF·HTML·Markdown도 같은 표시값을 쓴다. learning 입력과 report 내부 저장의 `EASY`·`NORMAL`·`HARD` 코드는 출력 조립 시 변환한다. 미작성·기간 밖이면 `written:false`, `difficulty:null`, `text:null`이다. 선택 텍스트 없이 난이도만 작성한 기록은 `written:true`, `text:null`로 구분한다.

- 리포트 상세의 `changes[].followup`은 문자열 또는 null이다. 학습 기록 API 4.1.1에서 되묻기 없이 제출한 보완 답변도 비교하므로, 질문이 없는 경우 null을 그대로 반환하고 최초/최종 답변 및 계산 수치는 유지한다. 저장된 결과를 임의 질문이나 빈 기록으로 대체하지 않는다.

### 3.5 결제 승인 — `POST /payments/confirm`

learning 최소 연동(#48): `GET /internal/payment-usage/students/{studentId}?since=<date-time>`는 SYSTEM+정확한 학생 scope에서 `{studentId,since,used}`를 반환한다. DONE 피드백의 completed_at 또는 진행 중 피드백을 확인하며 원문을 반환하지 않는다. learning 공개 피드백 경로는 실행 전에 core `POST /internal/payment-usage/reservations {studentId,sourceId}`를 호출하고 DONE 저장 후 `POST /internal/payment-usage/completions {studentId,reservationId,used:true}`를 호출한다. 두 core 경로는 내부 토큰과 STUDENT+본인 scope가 필요하다. 예약 응답은 `{reservationId:uuid|null,premium:boolean}`이며 미완료 예약은 환불 증빙 불명확으로 남긴다. 새 외부 서비스나 dependency 없이 기존 내부 HTTP를 사용한다.

#48 세부 DTO·복구·내부 권한 계약은 core OpenAPI와 [결제 구현 보고서](../report/issue-48-payments.md)를 따른다. 무료 상품은 명시적 PAYMENT_FREE_PRODUCT_ID로 선택하고, 승인 응답·웹훅은 PG 주문/금액/MID/상태를 대조한다. 환불 승인과 조회 권한은 각각 PAYMENT_REFUND/PAYMENT_VIEW이며 `/admin/refund-requests` GET도 PAYMENT_VIEW다. 모든 결제 쓰기는 parent 계정 잠금에 참여하되 외부 PG/learning 호출은 트랜잭션 밖이다. 불명확한 승인·취소를 실패로 바꾸지 않고 조회 복구한다. 최초 결제 후 빌링키가 등록되기 전에는 autoRenew=false, nextBillingDate=null이다.

대조 조회는 from/to(KST 날짜)를 모두 요구한다. 로컬 주문 상태 조회와 두 테스트 상점의 PG 거래 조회 페이지를 대조해 MISSING_LOCAL·MISSING_PG·DUPLICATE·MISMATCH·UNKNOWN·MATCH·NO_PG_ATTEMPT를 구분한다. PG 거래 목록이 불명확하면 빈 목록으로 대체하지 않고 503이다. 토스 거래 조회는 공식 최소 60초 timeout을 사용하며 결과는 page/size로 반환한다. paymentKey·transactionKey·customerKey는 응답에 포함하지 않는다.

결제 조회의 `refundRequests`는 본인 거래의 환불 상태 이력이며 취소 멱등키는 노출하지 않는다. GET 단건 조회는 승인된 환불의 불명확 PG 결과도 조회 복구한다. 빌링키 등록·변경은 ACTIVE와 유예 중 RENEWAL_FAILED에서 허용하며 유예/재청구 횟수를 초기화하지 않는다. 늦은 빌링 발급 결과는 subscription.revision 변경 시 거부한다. 같은 HTTP 멱등키로 받은 4xx 결과는 24시간 동일하게 반환하며 새 동의/등록 의도에는 새 키를 사용한다.

2026-10-28 #48 사용자 확정·2026-10-29 #129 연결: 과거 리포트도 현재 상품 권한을 적용한다. 무료 전환 후 상세의 narrative/eveningQuestion은 null이며 수치는 유지한다. 다운로드는 상세 메타데이터가 식별한 동일 불변 revision reportId의 파일만 요청한다. 현재 서술 권한이 없으면 report가 생성한 같은 판의 free 파일을 요청한다. full 파일 URL을 요청한 뒤 반환 직전 권한이 없어졌으면 403 REPORT_PREMIUM_REQUIRED로 URL을 반환하지 않는다. 수치 전용 파일은 무료에서도 제공한다. PG/HTTP 호출 이후 파일 URL 반환 직전에 parent 잠금 안에서 현재 권한·프리미엄 사용 기록을 함께 확정하여 환불과 직렬화한다.

#45 복구 경계: 필수 동의 철회 후에도 본인 결제·구독 GET, 본인 환불 요청 POST, 자동 갱신 해지 DELETE만 허용한다. 거래 소유권·활성 계정·환불 증빙 검사는 유지한다. 신규 주문·승인·빌링 등록·해지 철회는 현재 동의와 자녀 연결을 요구한다. 자녀 연결 해제 후에도 본인 구독의 청구 중단은 가능하다. 이미 갱신 승인이 진행 중이면 그 결과를 복구하되 autoRenew=false는 보존하며, 미청구 만료 구독은 즉시 종료한다.

```jsonc
// 요청 (결제위젯 successUrl 쿼리 값)
{ "paymentKey": "tgen_2026...", "orderId": "ord-88", "amount": 14900 }
// 200
{ "orderId": "ord-88", "status": "APPROVED",
  "subscription": { "subscriptionId": "sub-3", "childId": "s-1", "status": "ACTIVE",
                    "periodEnd": "2026-12-03", "nextBillingDate": null } }
// 202: PG 응답 지연·불명확
{ "orderId": "ord-88", "status": "CONFIRMING" }
```
- 처리 순서: 주문 금액·대상 자녀 대조 → PG 승인 API 호출 → 구독 반영
- 권한 반영이 실패한 경우
  - 결제는 `APPROVED`로 두고 복구 대상으로 기록 (FN-PAY-05)
  - 추가 청구 없이 재시도

### 3.6 초안 충돌 — `PUT /attempts/{attemptId}/draft`
```http
If-Match: "7"
```
```jsonc
// 409
{ "code": "ATTEMPT_DRAFT_CONFLICT", "status": 409,
  "latest": { "version": 8, "content": { "answer": { "text": "..." }, "memo": "..." }, "savedAt": "2026-11-03T19:10:00+09:00" } }
```

---

### 3.7 웹 목업 공통 규칙

3.8~3.10은 공개 API가 아직 없는 화면을 MSW로 개발하기 위한 웹 목업 계약. 확정 계약(5장·core OpenAPI)이 있는 항목은 그쪽이 우선이며 여기에는 다시 적지 않음.

- 개발 전용 MSW fixture(이메일 로그인 등)는 운영 계약이 아님. 로그인·토큰·`/me`·`/children`·동의·리포트·모델 레지스트리·AI 사용량은 5장과 OpenAPI 기준
- `GET /children`은 5.3·core OpenAPI 기준이며 실제 식별자는 `id`. 목업의 `childId`·`plan`은 계약이 아님(core는 `plan`을 만들지 않음)
- 시나리오 선택은 개발 브라우저 내부 이벤트로 전달하며 `/api/v1`에 가짜 경로를 추가하지 않음
- 새로고침 시험은 sessionStorage의 가상 fixture 상태만 복원. 실제 아동 정보·토큰·비밀번호는 저장하지 않음
- 브라우저 목업 시험은 서버 집계·연동 검증을 대신하지 않음

### 3.8 학생 화면 (답변 제출 형식·목업)

- 입력 방식별 제출(learning 구현): `CHOICE`는 `choiceIds` 1개, `ORDERING`은 모든 `choiceIds`를 중복 없이 순서대로, `SOLUTION_STEPS`는 `{finalAnswer, steps[]}`(최종 답과 비어 있지 않은 단계 1개 이상, 단위는 `answerUnit`으로 칸 뒤에 고정·비교 안 함, #79), `CLASSIFICATION`은 `{assignments:[{choiceId, categoryId}]}`(모든 choice를 한 그룹에 정확히 배정, 미정·중복은 422). 공통으로 `dictatedByGuardian`, 보완 시 `followupId`. 메모는 제출하지 않음
- 미션 상세 필드는 `{id,title,subject,grade,gradeMax,thinkingType,inputType,question,hint,sceneUri,staticSceneUri,choices,inputTemplate,categories,answerUnit}`(`scene` 미제공)
- 목업 전용: 미션 목록 항목의 `status·attemptId?·position·total`, `GET /students/me/home` `{student,state,period,resume,missions}`. 마무리 전에는 정답·예시·reveal·checklist를 주지 않음
- 마무리 후에만 `reveal`·`revealKind`·`checklist`(3.2 Element). 체크는 `satisfied`와 원문 인용이 모두 있는 요소만 표시
- 개발 시나리오 PARTIAL·RETHINK·CORRECT는 고정 UI 시험 상태이며 모델 판정이 아님

### 3.9 학부모 화면 (목업)

- 대화 목록·상세: `{conversationId,childId,period,title,createdAt,messages?}`, 메시지 `{messageId,question,status,scope,answer?,metrics?,evidence?,source?,fallback?,verification?,failureCode?,retryable?}`. clarification 선택지는 `{label,scope:{childId,from,to}}[]`, status에 `messageId?` 동봉. 다른 자녀 scope는 명시 전환하며 이전 자녀 결과는 표시하지 않음
- evidence 조회 `{items:Evidence[]}`. 삭제 항목은 `available:false`(410도 이용 불가 표시), quote 재사용 금지. delta는 저장하지 않음
- 학습 요약·생각 유형 목업 봉투: summary `{childId,state,period,inclusionRule,metrics[]}`, thinking-types `{childId,state,period,items:[{type,state,missions:[{attemptId,title}],summary?}]}`

### 3.10 관리자 화면 (목업)

ERD 3.2·3.5·4.1을 camelCase로 매핑. 학생 이름·답변 원문·메모는 운영 DTO에 넣지 않음. 모든 목 핸들러가 `/me.permissions`(`CONTENT|PAYMENT_VIEW|PAYMENT_REFUND|SERVICE_OPS`, 미제공은 권한 없음)로 검사.

- overview `{period,state,inclusionRule,attempts,completed,jobCounts:[{type,status,count}],missionCounts:[{status,count}]}`
- jobs: 1.1 봉투, 항목 `{jobId,type,status,retryCount,failureReason,createdAt,updatedAt,executions:[{executionId,attemptNo,status,errorCode,errorDetail,triggeredBy,startedAt,finishedAt}]}`, 선택 `from&to` 필터(백엔드 확인 대상). retry는 같은 키의 최초 응답 반환. queues `{items:[{name,length,dlq}]}`, audit `{id,actorUserId,action,targetType,targetId,result,detail,createdAt}`
- mission `{missionId,status,demoOnly,currentVersion,currentRubricVersion,publishedVersion,versions[],rubrics[],reviews[]}`. PATCH·rubric PUT은 새 불변 버전, review-request `{missionVersion,rubricVersion}`, review는 `result:APPROVED|CHANGES_REQUESTED,comment`, publish 실패는 422 `missingFields[]`, preview `{mission,missionVersion,rubricVersion}`(답안 미포함). 업로드는 미구현(URI 입력)
- error-report `{reportId,status,targetType,targetId,category,comment,reviewReason?,corrections:[{reason,corrected,createdAt,impact}],linkedAttempt?}`. SERVICE_OPS만 연결 시도 원문 열람, 매번 감사 기록. 정정은 기존 판정을 덮지 않음

### 3.11 학생 기기 등록·PIN 로그인 (P01 개정)

학부모 부재 시 자녀 단독 학습을 위한 경로다. 근거·대안 비교는 [보고서](../report/auth-account.md)를 따른다. 기존 `POST /auth/student-sessions`(학부모 동석)는 유지한다.

- 페어링 `POST /student-devices/pairings`
  - 학부모 토큰, `childIds[]`는 모두 `guardianship LINKED`이어야 함 (아니면 `403 CHILD_NOT_LINKED`)
  - 응답 `{pairingCode, expiresAt}`. 코드는 8자리 영숫자, 10분 유효·1회 사용, Redis 저장(원문 대신 해시 키)
  - 기본 등록 방식은 학부모 기기에서 코드·QR 발급 → 자녀 기기에서 입력·스캔. 로그인이 Google OAuth(#36)이므로 학부모가 자녀 기기에서 직접 로그인하면 브라우저에 Google 세션이 남을 수 있어 비권장
  - 부득이 자녀 기기에서 학부모가 로그인한 경우 클라이언트가 발급 직후 등록 API를 호출하고 학부모 세션을 로그아웃하며, Google 계정 로그아웃을 안내한다
- 등록 `POST /auth/student/devices`
  - 요청 `{pairingCode, label}` → 응답 `201 {deviceId, children:[{childId,nickname}]}` + `Set-Cookie: student_device=<랜덤 256bit>`
  - 서버는 토큰 해시만 저장, 등록일부터 고정 만료 90일(설정값, 사용 시 연장 없음). 코드 오류·만료·재사용은 `400 PAIRING_CODE_INVALID`, IP 단위 시도 제한
- PIN 로그인 `POST /auth/student/login`
```jsonc
// 요청 (Cookie: student_device=...)
{ "childId": "c1...", "pin": "4831" }
// 200
{ "accessToken": "...", "expiresIn": 900, "role": "STUDENT", "child": { "childId": "c1...", "nickname": "별빛", "grade": 3, "birthYear": 2017 } }
// 401
{ "code": "STUDENT_PIN_INVALID", "status": 401, "remainingAttempts": 2 }
```
  - 검사 순서: 기기 쿠키 유효(해시 일치·미해제·미만료) → 자녀가 기기에 등록됨 → 기기 소유 학부모와 `LINKED`·`student ACTIVE`·필수 동의 유지 → PIN 설정 → 잠금 아님 → PIN 일치
  - 기기·자녀 불일치는 `401 STUDENT_DEVICE_INVALID`, 연결·동의 문제는 `403 CHILD_NOT_LINKED`
  - 불일치 시 `pin_failed_count` 증가, 5회째 `pin_locked_at` 기록 후 `423 STUDENT_PIN_LOCKED`. 성공 시 실패 횟수 0, 기기 `last_used_at` 갱신
  - refresh token 미발급. access 만료 시 PIN 재입력(초안은 자동 저장으로 보존). 학생 토큰 권한은 동석 경로와 동일
- PIN 설정 `PUT /children/{childId}/pin`
  - `X-Reauth-Token` 필수. 숫자 4~6자리, 동일 숫자 반복(`1111`)·연속(`1234`, `4321`) 거부 `422 VALIDATION_FAILED`
  - 해시 저장, 실패 횟수 0·잠금 해제. 잠긴 PIN의 해제 수단은 재설정뿐
- 기기 해제 `DELETE /student-devices/{deviceId}`: `revoked_at` 기록, 기존 학생 access token은 만료까지 유효
- 학부모 화면의 실제 PIN 상태: `GET /children` 각 항목에 `pinSet`(설정 여부)·`pinLocked`(5회 실패 잠금 여부)를 반환한다. PIN 원문·해시·실패 횟수는 반환하지 않음
- 기기 등록·해제·PIN 설정은 `audit_log` 기록 (FN-ACC-10). PIN 잠금 시 학부모 알림은 미정
- 응답 형식: 프로필 `{items:[{childId,nickname,pinSet,pinLocked}]}`, 기기 목록 `{items:[{deviceId,label,children:[{childId,nickname}],createdAt,lastUsedAt,expiresAt}]}`(해제 기기 제외). PIN 설정·변경은 204(잠금 해제 포함), 별도 해제 API 없음
- PIN 변경은 현재 세션·버전·`PIN_CHANGE`·자녀에 결합된 5분 재인증 grant를 같은 트랜잭션에서 1회 소비
- 한도: 등록은 IP별, 페어링 발급은 보호자별 10분간 20회(설정 가능). 초과 429 `RATE_LIMITED`, Redis 장애 503 `STUDENT_AUTH_UNAVAILABLE`. 신뢰 프록시 설정 전에는 X-Forwarded-For 미사용
- 코드 소비는 Redis 원자적 GET+DEL. 이후 DB 등록이 실패해도 코드는 복원하지 않음(새 코드 발급)
- 기기·학생 검사는 계정 행 잠금과 함께 재검사. PIN 실패는 커밋 후 오류 응답
- 등록·프로필·로그인 응답은 `Cache-Control: no-store`. PIN 로그인은 refresh 쿠키를 발급하거나 보호자 세션을 바꾸지 않음

### 3.12 학생 화면 꾸미기 설정 (목업 계약 초안, 백엔드 확인 대기)

학생이 고른 생각 지도 테마와 동행 캐릭터를 기기와 관계없이 유지하기 위한 학생 본인 설정이다. 학습 기록·판정·리포트에 쓰지 않으며 학부모 화면에 노출하지 않는다. 대응 FN 항목이 없는 화면 개선 제안이므로 기능 명세 반영 여부도 함께 확인한다.

| Method | Path | 역할 | 설명 |
|---|---|---|---|
| GET | `/students/me/preferences` | 학생 | 현재 설정. 저장한 적 없으면 기본값과 `updatedAt:null` |
| PUT | `/students/me/preferences` | 학생 | 설정 전체 교체 `{theme, companion}` |

```jsonc
// GET 200 / PUT 200
{ "theme": "lake", "companion": "mungchi", "updatedAt": "2026-10-27T05:00:00Z" }
```
- `theme`: `lake`(호수)·`forest`(숲)·`factory`(공장)·`space`(소행성)·`sea`(바닷속). 기본 `lake`
- `companion`: `mungchi`(뭉치)·`tori`(토리)·`mongdol`(몽돌)·`kongi`(콩이)·`monggeul`(몽글). 기본 `mungchi`
- 목록에 없는 값은 `422 VALIDATION_FAILED`. 학생 토큰 전용, 학부모·관리자 토큰은 `403 FORBIDDEN`
- 숫자 레벨·보상·잠금 해제 조건 없이 언제든 바꿀 수 있다 (기능 명세 1.3의 숫자 레벨·등급·순위 비표시 원칙과 충돌하지 않음)
- 저장 위치(core 학생 테이블 컬럼 또는 별도 설정 테이블)와 값 목록 관리 방식은 백엔드 확정 대상

### 3.13 요구사항 화면 보완용 지원 DTO (프론트 목업, 백엔드 확인 대기)

2026-10-29 첨부 요구사항 정의서 대조에 따라 아래 지원 화면을 연결했다. 경로·역할은 2.7·2.8을 따르며 이 절의 DTO는 프론트 목업 계약이다. 실제 서버 Controller 구현이나 저장·전달 완료를 뜻하지 않는다. API 모드 실패를 시연 응답으로 대체하지 않는다.

- `GET /help?role`: `{items:[{id,title,content}]}`. 현재 인증 역할만 요청한다.
- `GET /notices`: `{items:[{id,title,content,roles[],startsAt,endsAt:null|string}]}`. 현재 역할·공개 기간을 만족하는 공지만 반환한다.
- `POST/GET /error-reports`, `POST/GET /inquiries`: 요청은 2.7을 따른다. 화면의 공통 목록 항목은 `{id,targetType?,targetId?,category,comment,status,answer?,createdAt}`, 상태는 RECEIVED/IN_REVIEW/RESOLVED. 기존 관리자 오류 신고의 reportId는 별도 계약으로 유지한다. 목업에서 사용자 신고를 관리자 검토 목록과 연결하며 답변 원문은 수정하지 않는다.
- `GET /admin/inquiries`: SERVICE_OPS, `{items:[공통 목록 항목]}`. `PATCH /admin/inquiries/{id}`: `{answer,status:RESOLVED}` → 갱신 항목. 일반 문의와 판정 오류 검토를 구분한다.
- `POST /admin/notices`: SERVICE_OPS, `{title,content,roles[],startsAt,endsAt}` → 공지 항목(201). 공개 역할·기간을 검증한다.
- 알림은 2.7의 실제 #44 계약을 그대로 사용한다. 학생에게 요청하지 않으며 읽음·수신 설정은 서버 확인 후 갱신한다. SSE 구독은 이번 화면 보완에 포함하지 않고 목록·새로고침으로 확인한다.
- 계정·삭제·탈퇴는 5.6 실제 #45 계약을 따른다. 사전 확인 경로는 `GET /me/withdrawal/precheck`이며 `{canWithdraw,activeSubscriptions,unresolvedRefunds,retainedTransactionsYears}`를 반환한다. 삭제 목업은 CONFIRMED와 서비스별 완료 상태를 구분하고 자동으로 완료를 만들지 않는다. 탈퇴 조회 영수증은 URL·영구 저장소 대신 현재 화면 메모리에만 보관한다.
- 점검표 `/review`와 가상 계정 진입은 DEV+MSW에서만 제공하고 운영 번들에서 제외한다. 역할 URL만으로 권한을 부여하지 않고 기존 시연 로그인·학생 동석 API를 호출한다.

## 4. 내부 API (`/internal`)
- 인증: `X-Internal-Token` + 사용자 컨텍스트 헤더 `X-User-Id`, `X-User-Role`, `X-Student-Scope`(허용 학생 ID, 콤마 구분), `traceparent`
  - ai는 받은 컨텍스트 헤더를 learning 호출에 그대로 전달
  - 사용자 요청 없는 호출(report-worker): `X-User-Role: SYSTEM`, `X-Student-Scope` = 이벤트 `subject` 학생
- 외부에 노출하지 않음. NetworkPolicy로 호출 관계만 허용
- 범위 밖 학생 요청은 403

### 4.0 core 학생 별명 조회 (#119, 호출: report-worker)

`GET /internal/students/{studentId}/profile` → `200 {studentId, nickname}`. core OpenAPI의 이 operation은 `servers: /`로 공개 API prefix와 구분한다. 응답은 `Cache-Control: no-store`이며 두 필드만 제공한다.

실제 `InternalAuthFilter`가 내부 토큰을 검사한 뒤 guardianship Controller → Application Service → 기존 `ChildManagementRepository.profile`을 호출한다. Service는 `SYSTEM` 역할과 대상 학생의 `X-Student-Scope` 포함 여부를 DB 조회 전에 확인한다. 학부모 Bearer만으로 호출할 수 없다.

2026-10-29 사용자 확정: 잘못된 UUID는 `400 VALIDATION_FAILED`, 토큰 누락·불일치는 `401 UNAUTHENTICATED`, 역할 누락·SYSTEM 외 역할·scope 누락/불일치는 `403 FORBIDDEN`, 미존재·ACTIVE 외 상태(DELETION_REQUESTED·DELETED 포함)는 `404 NOT_FOUND`. DB 등 예상하지 못한 조회 실패는 기존 `500 INTERNAL_ERROR` Problem Details로 반환한다. 현재 student CHECK의 상태는 ACTIVE·DELETION_REQUESTED·DELETED이며 별도 INACTIVE 상태를 추가하지 않는다. 기존 SQL·스키마·공개 API는 유지한다.

report 연결은 별도 담당 범위다. 조회한 nickname을 생성 명령의 내부 `display_name`으로 보관해 제목에 사용하고, NarrativeGenerator에서 AI 요청 전에 가린다. `report.generate.v1`에 별명을 추가하지 않는다. 403·404를 가짜 별명·기록 없음으로 처리하지 않고 생성 실패로 취급한다. 통신 장애는 기존 작업 실패/재시도 경계를 따르며 서비스 간 HTTP 재시도를 추가하지 않는다. 실제 worker 연결·최종 AI payload 검증은 [#119 보고서](../report/issue-119-student-profile.md)의 후속 조건을 따른다.

### 4.1 learning-service (호출: core, ai, report)

구현된 경로의 요청·응답 계약: [contracts/openapi/learning-service.yaml](../../contracts/openapi/learning-service.yaml) (`scripts/tests/test_record_exists_openapi.py`가 컨트롤러 경로와 대조)

| Method | Path | 호출자 | 설명 |
|---|---|---|---|
| GET | `/internal/missions?grade&demo&page&size`, `/internal/missions/{id}?grade&demo` | core | 학생용 미션 조회 (2.2 프록시). core가 학생 학년 `grade`(3~6, 필수)와 시연 학생 여부 `demo`(`student.is_demo`, 기본 `false`)를 붙임. `demo_only` 미션은 `demo=true`일 때만 노출. 미션에 분류 그룹 `categories`·수학 답 단위 `answerUnit` 포함(3.8, #79) |
| POST | `/internal/missions/{id}/attempts?grade&demo` | core | 시도 시작·이어하기 (2.2와 1:1). 조회와 동일하게 core가 인증된 학생의 `grade`(필수, 3~6)와 `demo`(`student.is_demo`, 기본값 `false`)를 전달함. 공개 요청의 `grade`·`demo` 값은 사용하지 않음. 진행 중인 시도가 있으면 미션의 공개 여부나 제공 범위와 관계없이 해당 시도를 반환(`200`)하고, 신규 시도는 `201`을 반환함. core는 응답 상태를 그대로 전달하며, 신규 시도의 제공 범위 검사와 기존 시도의 시작 당시 버전 유지는 learning이 담당함. 일일 한도는 core의 Redis 책임이며, `201` 응답만 집계하는 후속 연계는 2.2 참고 |
| POST · GET · PUT | `/internal/attempts/...` | core | 시도·초안·도움·답변·마무리·돌아보기·자기 평가 (2.2 경로와 1:1). 생각 열기 응답 형식은 `{question, seq, total}`이며, 질문이 없는 미션은 `404`를 반환함. 시도 상세 `answers[]`는 `{answerId, version, submittedAt, inputType, text(입력 틀 칸 이름을 붙인 원문), followupId, content, feedback}`, `feedback`은 아래 피드백 결과와 같은 모양(판정 전이면 `{status, judgment:null, followup:null, nextActions:[], versions:null}`), 시도 `nextActions`는 마지막 답변의 `nextActions`. 시도 상세의 `reveal`·`revealKind`·`checklist`는 마무리 뒤에만, `reflection{difficulty, text}`는 돌아보기 뒤에만(그 전에는 `null`). 마무리 `finish` → `200 {attemptId, finishedAt, reveal(시도 기준표 버전의 예시 답, 닫힌 문제는 정답과 해설), revealKind(고르기·순서·분류·풀이 단계 `ANSWER`, 서술·논술 `EXAMPLE`), checklist(기준표 요소 전체 3.2 `Element[]`, 이 시도의 처리 완료 판정 중 원문 구절과 함께 충족된 요소만 체크·가장 최근 구절)}`, 판정 `DONE` 1회 미만이면 `409 REVEAL_CONDITION_UNMET`, 다시 요청하면 기록하지 않고 같은 결과. 돌아보기 `reflection` `{difficulty(EASY·NORMAL·HARD, 필수), text(선택, 빈 글은 null)}` → `200 {attemptId, status:"COMPLETED", reflection}`(완료 시점은 시도 상세·기록 조회), 난이도 없음·값 밖 `400`, 마무리 전 `409 REVEAL_CONDITION_UNMET`, 완료 뒤 `409 ATTEMPT_CLOSED`. 자기 평가 `self-assessment` `{checks:[{elementId, checked}]}` → `200 [{elementId, label, selfChecked(체크 안 한 요소는 null), aiChecked, quote}]`(기준표 요소 전체), 마무리 전 `409 REVEAL_CONDITION_UNMET`, 완료 뒤 `409 ATTEMPT_CLOSED`, 비었거나 같은 요소 두 번·기준표 밖 요소 `400`, 다시 보내면 `checked`만 바꿈 |
| POST | `/internal/attempts/{id}/answers` | core | 답변 제출 (3.1·3.8 형식). `Idempotency-Key`(UUID) 필수, 없거나 형식 오류면 `400`. 같은 키·같은 본문은 처음 답변을 `201`로 다시, 다른 본문은 `422 IDEMPOTENCY_KEY_REUSED`. 미션 입력 방식과 다르면 `400`, 누락은 `422 ANSWER_INCOMPLETE`, 마무리·완료한 시도는 `409 ATTEMPT_CLOSED`. 보완 답변은 가장 최근 미답 되묻기의 `followupId` 필수(아니면 `422 ANSWER_INCOMPLETE`). 저장하면 같은 트랜잭션에서 초안 `content.answer`를 비우고 `memo`는 유지, 초안 `version` +1 |
| POST | `/internal/answers/{answerId}/feedback` | core | 판정 오케스트레이션: 규칙 판정 또는 ai 호출 → 저장 → 결과 반환 (동기). `200` 결과는 3.2 `result`와 같은 `{status, judgment{result, trial, elements[{elementId(rubric_element.id), label, satisfied, quote, sourceType}], heldReason}, followup{followupId, type, question, source}, nextActions, versions{mission, rubric, model, prompt}}`, `versions.mission`·`rubric`은 `미션 code@버전`, 규칙 판정이면 `model`·`prompt` 없음. 다른 요청이 처리 중이면(그사이 다른 요청이 실패한 경우도 포함, 다시 요청하면 실행) `200 {status:"RUNNING", judgment:null, followup:null, nextActions:[], versions:null}`. ai·LLM 실패·타임아웃·서킷 차단은 판정 `FAILED` 후 `503 AI_UNAVAILABLE` + `retryable`(ai가 false로 준 오류·ai 4xx·계약 밖 응답은 false), 그 밖의 예상 못 한 오류는 판정 `FAILED` 후 `500`. 허용 안 되는 판정 전이는 `409 JUDGMENT_STATE_CONFLICT`(learning 내부 방어 코드: 처리 중이 아닌 판정을 끝내거나 실패로 기록하려 함, state-diagram 1.3. 획득한 리스로만 저장해 정상 흐름에서는 없어 1.3 공통 오류 표에는 넣지 않음). `nextActions`는 지금 할 수 있는 행동: 이 판정의 되묻기에 아직 답하지 않았으면 `[ANSWER_FOLLOWUP, FINISH]`, 되묻기가 없으면 `[FINISH]`, 마무리·완료한 시도는 `[]` |
| POST | `/internal/judgments/{judgmentId}/corrections` | core | 신고 정정 반영(SUP-03, #80). `X-User-Role: ADMIN`, `X-Student-Scope`에 판정 학생 정확히 1명, `X-User-Id`(UUID, 정정한 관리자 = `corrected_by`) 필수. 요청 `{reportId(UUID), reason(1자 이상), corrected(CORRECT·PARTIAL·RETHINK·HELD)}` + `Idempotency-Key`(UUID, core가 저장한 정정 ID). 기존 판정·요소·답변은 그대로 두고 `judgment_correction` 행 추가. `200 {correctionId, previousResult(정정 직전에 보이던 결과, 앞선 정정이 있으면 그 결과), corrected, createdAt, impact{conversation, aggregation, report}}`. 같은 키·같은 요청(판정·본문)은 처음 응답 전체를 다시 `200`, 다른 요청이면 `422 IDEMPOTENCY_KEY_REUSED`. 같은 `reportId` 정정이 다른 키로 이미 있으면 `409 CORRECTION_REPORT_CONFLICT`, 판정이 `DONE` 전이면 `409 JUDGMENT_STATE_CONFLICT`, 판정 없음 `404`, 역할·학생 범위 위반 `403`, 헤더·본문 형식 오류 `400`(409·422 코드는 learning 내부용, 공개 오류는 core #46이 바꿔 정함). 이후 피드백 결과·시도 상세·기록(#27)의 `judgment.result`는 최신 정정 결과(정정이 있으면 `heldReason: null`), 판정 요소·되묻기·`nextActions`는 원판정 그대로. `impact.aggregation`은 learning 수치 집계가 판정 결과를 쓰지 않아 `NOT_APPLIED`(변경 대상 없음), `conversation`·`report`는 learning이 확인할 수 없어 `UNKNOWN` (core #46 계약 `support-learning-required.yaml`) |
| GET | `/internal/records/students/{studentId}/exists` | core | 전체 보존 기록의 존재 여부 `{studentId,hasRecords}`. #37 선행 최소 API, P08 제출·실패·삭제 제외 기준 적용 |
| GET | `/internal/records/students/{studentId}/summary?from&to` | core, ai | 건수·상태 `Metric[]` → `{studentId, state, period, inclusionRule, metrics}`(3.9). 지표: 학습한 활동(집계 대상 시도 수), 완료한 활동(완료 / 집계 대상), 도움 없이 시작한 활동(최초 답변 전 생각 열기 열람 없는 시도 / 집계 대상, P08), 되묻기 후 생각을 더한 활동(보완 답변 제출 시도 / 되묻기 받은 시도, 1.6) |
| GET | `/internal/records/students/{studentId}/thinking-types?from&to` | core, ai, report | 유형별 미션·기록 → `{studentId, state, period, items:[{type, state, missions:[{attemptId, title}]}]}`, 다섯 유형 모두, 기록 없는 유형은 `NO_RECORD`(FN-DSH-08 미관찰) |
| GET | `/internal/records/students/{studentId}/attempts?from&to&status&page&size` | core, ai, report | 시도 목록·상세(답변 버전·되묻기·도움·돌아보기 원문) → 1.1 봉투 + `{studentId, state, period, inclusionRule}`, 최근 답변 순, `status`(`IN_PROGRESS`·`COMPLETED`, 생략하면 전체)는 지금 그 상태인 시도만. `items`는 4.1 시도 상세에서 초안(`draft`, 메모 포함)을 뺀 모양 + `completedAt`·`hintUsages:[{openedAt}]`·`reflection{difficulty, text, createdAt}`. `finishedAt`은 마무리(정답·예시 답 공개) 시각, `completedAt`은 돌아보기를 내 `COMPLETED`가 된 시각(각각 그 전에는 `null`), 돌아보기가 있으면 `createdAt`은 항상 값(= `completedAt`). `answers`·`hintUsages`는 1번·처음부터 조회 종료일까지(시작일 이전 포함, 지난 기간을 조회해도 그 뒤가 섞이지 않음, FN-RPT-02), `reflection`은 기간 안에 쓴 것만(아니면 `null`) |
| GET | `/internal/records/students/{studentId}/attempts/{attemptId}?from&to` | core | 학부모 2.3 시도 상세용. 목록 `items`와 같은 모양 + `state: OK`·`period`. 기간은 화면이 유지할 정보라 검증·기본값만 적용하고 이력(답변·되묻기·도움·돌아보기)은 자르지 않음. 다른 학생의 시도·집계 대상이 아닌 시도는 `404` |
| GET | `/internal/records/students/{studentId}/home?from&to&grade&demo` | core | 학생 2.3 홈용(FN-DSH-01·02) → `{studentId, state, period, resume, missions}`. 학생 본인 요청만(`STUDENT`, 범위에 본인 1명, 4.1 미션 목록과 같은 기준). `resume`은 진행 중 시도 중 가장 최근에 손댄 것(시작·답변 제출·초안 저장 중 가장 늦은 시각) 하나, 기간과 무관하고 초안만 있는 시도·마무리 뒤 돌아보기 전 시도도 포함(FN-LRN-16), 목록 `items`와 같은 모양(초안·메모 없음, 본인 초안은 core가 학생 시도 상세로 붙임), 없으면 `null`. `missions`는 4.1 미션 목록 항목 전체(`grade` 3~6 필수, `demo` 기본 `false`, 같은 노출 범위). `state`는 기간 안 집계 대상 시도 수 |
| GET | `/internal/records/students/{studentId}/thinking-activities?from&to` | core, ai | 학생 2.3 생각 활동용(FN-DSH-04), ai 분석 대화의 돌아보기·전후 변화 근거 미션 제목 → `{studentId, state, period, items:[{attemptId, thinkingType, missionTitle, reflection{difficulty, text}}]}`. 집계 대상 시도를 최근 답변 순으로, `reflection`은 기간 안에 쓴 것만(아니면 `null`, 목록과 같음). 수치·등급·순위 없음 |
| GET | `/internal/records/students/{studentId}/changes?from&to&page&size` | ai, report | 되묻기 전후 답변 쌍 → 1.1 봉투 + `{studentId, state, period}`, `items:[{attemptId, followup(마지막 답변이 답한 되묻기), first{answerId, text}, revised{answerId, text}, counts{chars, sentences, reasonConnectives}}]}`(3.4). 조회 종료일까지 보완 답변이 있는 시도만, 최초 vs 종료일 이전 마지막 답변(P08, FN-RPT-02). `text`는 원문, 수는 학생이 쓴 칸 내용으로 셈 |
| GET | `/internal/records/evidence?answerIds=` | core, ai, report | 원문 근거 조회 → `{items: Evidence[]}`(1.6·3.9). 요청한 순서대로, 없는 답변·삭제 학생은 `available:false`(원문 없음), 범위 밖 학생의 답변이면 `403` |
| GET | `/internal/stats?from&to` | core | 운영 현황용 집계 (학생 원문 없음) → `{period, inclusionRule, attempts, completedAttempts, students}`(FN-ADM-02). 역할 `ADMIN`·`SYSTEM`, 학생 범위 없음 |
| * | `/internal/admin/missions/...` | core | 2.8 미션 관리 프록시 |

- 기록 조회 공통 (#27): 학생 경로는 역할 `PARENT`·`STUDENT`·`SYSTEM`(`home`은 학생 본인 `STUDENT`만)이고 `X-Student-Scope`에 대상 학생이 없으면 `403`. `from`·`to`는 KST 날짜(양 끝 포함), 둘 다 주거나 둘 다 생략(생략하면 오늘 포함 최근 7일, P06), 한쪽만 주거나 `from > to`면 `400`. 응답 `period`는 실제 조회 기간. 집계 대상은 P08(기간 안에 답변 제출이 있는 시도, 미완료 포함·판정 상태 무관. 조회 종료일까지의 답변이 모두 처리 실패인 시도와 삭제 기록은 제외). 시도별 사실(완료·되묻기 받음·보완 답변·최근 답변)은 조회 종료일까지 일어난 것만. `state`는 집계 대상(비율은 분모) 0건 `NO_RECORD`, 1~4건 `INSUFFICIENT_SAMPLE`(비율 `value: null`), 5건 이상 `OK`. 메모·초안은 반환하지 않음(P05). 최상위 학생 식별자는 호출 역할과 무관하게 `studentId`(학부모 공개 응답의 `childId`는 core가 바꿈, core #40·report #51과 합의). 조회 장애는 `state`가 아니라 HTTP 오류(Problem Details)로 반환. 까닭을 잇는 말은 `왜냐하면`·`때문`·`그래서`·`따라서`(report와 확정)

#### 4.1.1 report 수치 집계 입력

P06·P08 계산에 쓰는 learning 공급 입력. 계산 규칙과 검증은 [리포트 보고서](../report/report.md).

- 세 조회 모두 `studentId`·`period:{from,to}`·`state`를 반환한다. 학부모 공개 응답의 `childId`와 혼용하지 않는다. 학생·기간이 요청과 다르면 생성에 사용할 수 없다. 날짜 범위는 KST 양 끝 포함이며 조회 장애는 HTTP 오류다.
- `attempts`·`changes`는 1.1의 페이지 봉투를 사용한다. `page`는 0부터 시작하고 `totalElements`는 같은 학생·기간·포함 기준의 전체 항목 수다. report는 `size=100`으로 모든 페이지를 읽으며 실패/누락 페이지를 빈 기록으로 바꾸지 않는다. `thinking-types`는 `{studentId,state,period,items}` 형태를 사용한다.
- `attempts.items[]`의 필수 입력:
  - `attemptId`, `studentId`, `mission:{title,thinkingType}`, `status:IN_PROGRESS|COMPLETED`, `answers[]`, `hintUsages:[{openedAt}]`. 학생 메모·초안은 포함하지 않는다. #27은 attempts에 삭제 표식 항목을 넣지 않는다. 삭제 뒤 정상 조회는 `NO_RECORD`, `items:[]`, `totalElements:0`이다. 이것은 evidence의 삭제된 답변 표시나 #55 삭제 완료 처리를 대신하지 않는다.
  - `answers[]`: `{answerId,version,submittedAt,inputType,text,followupId,content,feedback:{status:PENDING|RUNNING|DONE|FAILED}}`. `text`는 표시·근거용 평문 전체이고 null이 아닌 문자열이다(내용이 없으면 `""`). 풀이·논술의 칸 이름과 고르기의 선택지 이름이 포함될 수 있다. 수치 재계산에는 `content`의 학생 작성 칸만 사용해야 하며 표시용 `text`를 그대로 세면 안 된다. 시도당 1번부터 조회 종료일 끝까지의 답변 버전을 제공한다. 최초 답변·도움 이용을 비교할 수 있도록 조회 시작일 이전의 답변도 포함한다. report는 종료일 이후 답변을 사용하지 않는다.
  - `hintUsages[]`는 조회 시작일 이전 기록을 포함하여 최초 답변 이전 열람 여부를 판정할 수 있는 전체 열람 시각을 제공한다. 열람이 없으면 빈 배열이며 단순 `helped` 값으로 대체하지 않는다. `submittedAt`·`openedAt`·`completedAt`·`createdAt`은 시간대 오프셋이 있는 ISO 8601 시각이다.
  - 완료 시도는 `completedAt`을 제공한다. learning **입력**의 `reflection`은 해당 기간에 작성한 `{difficulty:EASY|NORMAL|HARD,text:string|null,createdAt}` 또는 `null`이다. 미작성·기간 밖이면 `null`을 사용하고 report는 필드 생략도 허용한다. 선택 텍스트가 null이어도 난이도·작성 시각이 있는 돌아보기는 작성한 기록이다. `{written:false}`만 있는 객체는 입력 형식이 아니다.
  - report **출력/저장 항목**의 `reflections[]`는 미작성·기간 밖이면 `{attemptId,written:false,difficulty:null,text:null}`이다. 입력에 기간 밖 돌아보기가 포함되어도 report가 작성 시각으로 제외한다. 작성한 항목은 `written:true`이며 내부 계산·저장에는 난이도 코드를 유지한다. 입력과 3.4 출력 형식을 혼용하지 않는다.
- `thinking-types.items[]`: `{type,missions:[{attemptId,title}],state}`. 다섯 유형을 모두 제공하며 없는 유형은 `NO_RECORD`, 있는 유형은 `OK`다. 유형 요약 문장은 제공하지 않는다. 집계 대상 시도의 유형·미션을 대조한다.
- `changes.items[]`: `{attemptId,followup:string|null,first:{answerId,text},revised:{answerId,text},counts:{chars,sentences,reasonConnectives}}`. 포함된 시도의 종료일 기준 최초·마지막 답변과 ID·평문이 일치해야 한다. 시도당 한 쌍이며 답변이 하나뿐이면 변화 항목을 만들지 않는다. 수치는 report가 `answers[].content`로 다시 계산한다. 서술은 text, 풀이는 steps 순서 후 finalAnswer, 논술은 essay.claim·reasons 순서·rebuttal 중 비어 있지 않은 칸을 줄바꿈으로 연결한다. 칸 이름·선택지 이름·메모·추가 필드는 제외하며 고르기·순서·분류의 학생 작성 글은 빈 문자열로 계산한다. 필수 내용 누락·잘못된 형식은 오류로 처리하며 표시용 text로 대신 계산하지 않는다. null `followup`은 계산 결과·DB에 그대로 보존한다. 후속 #53·#54의 조회 JSON도 null을 유지하고 PDF·HTML·Markdown은 질문 문구를 생략해야 한다. `None`이나 임의의 질문을 표시하지 않는다.
- `evidence`는 `{items:[...]}`다. 정상 항목은 `answerId,attemptId,answerVersion,quote,missionTitle,submittedAt,available:true`이며 `quote`는 attempts의 `text`와 같은 전체 평문이다. 없는 답변·삭제 학생은 `available:false`로 원문을 제공하지 않는다. 요청 ID를 중복 제거한 순서대로 정상/삭제 항목을 함께 반환하며 누락하지 않는다. report는 ID를 중복 없이 보내고 시도·버전·원문을 대조한다.
- 동일 시도가 여러 주에 걸치면 각 주에 제출된 답변 존재 여부로 포함한다. 변화는 포함된 시도의 최초 답변과 해당 주 종료일 이전 마지막 답변을 비교한다. 조회 이후에 추가된 답변으로 과거 주의 마지막 답변을 바꾸지 않는다.

### 4.2 ai-service (호출: learning, core, report)

구현된 경로의 요청·응답 계약: [contracts/openapi/ai-service.yaml](../../contracts/openapi/ai-service.yaml) (`scripts/tests/test_ai_openapi.py`가 라우터 경로와 대조)

| Method | Path | 호출자 | 요청 → 응답 |
|---|---|---|---|
| POST | `/internal/judgments` | learning | `{answerText, inputType, grade, rubric{elements[]}, versions}` → `{result, elements[{elementId, quote, verified, satisfied}], heldReason, trial, versions}` (M2 활성 시 scoring 교차 확인) |
| POST | `/internal/followups` | learning | `{timeline[], judgment, rubric, mission, grade}` → `{type, question, source, leakCheck{passed}, versions}` (정답·금지어 검사 실패 시 1회 재생성 `LLM_RETRY`, 재실패 시 `question` 없이 `leakCheck.passed = false` → learning이 질문 은행 `BANK` 선택, P16) |
| POST | `/internal/analysis/stream` | core | **SSE**. `{conversationId, question, scope{studentId, from, to}, history[]}` → 3.3과 같은 이벤트 |
| POST | `/internal/report-narratives` | report | `{metrics[], thinkingTypes[], changes[], reflections[], quotes[]}` → `{narrative, eveningQuestion, citedQuotes[], versions}` (4.2.1) |
| GET | `/internal/versions` | core | 활성 프롬프트 버전 |

#### 4.2.1 report 서술 요청·응답

- 요청 항목은 report 계산 결과(3.4 `metrics`·`thinkingTypes`·`changes`·`reflections`·`quotes`)를 그대로 보낸다. `quotes[]`는 인용 후보 `{attemptId, answerId, answerVersion, text}`이며 `answerVersion`은 해당 답변 근거의 버전이다(3.4 상세 `quotes`에는 없음). 대조 전 값인 `verified`는 ai가 무시한다. 다섯 배열은 필수(빈 배열 허용)다.
- ai는 인용을 후보 번호와 원문 구절로 고르고, 구절이 그 후보 `text`의 부분 문자열이 아니면 `citedQuotes`에서 제외한다. `attemptId`·`answerId`·`answerVersion`은 후보 입력값을 쓴다. LLM 실패·키 미설정·빈 서술이나 빈 저녁 질문은 503 `AI_UNAVAILABLE`(+`retryable`)이다.
- 응답은 `{narrative:{text,source:"LLM",modelExplanation:null},eveningQuestion,citedQuotes:[{attemptId,answerId,answerVersion,quote}],versions:{prompt,model}}`로 정의한다. 원문 인용은 citedQuotes에 명시하며 답변 버전과 연결한다. ai는 숫자를 새로 계산하거나 수치 레벨·등급·사고력 향상을 단정하지 않는다.
- report는 learning evidence의 같은 answer ID·version·원문과 인용을 대조하고, 서술·저녁 질문의 숫자가 계산 결과에 포함되는지 검사한다. 지원하지 않는 한글 수사 표현은 검증 통과로 간주하지 않는다. 검증 메타데이터는 `numbersMatched`, `quotesMatched`, `contentAllowed`다.
- 대조 실패만 코드 기반 템플릿 요약으로 전환한다. AI 시간 초과·5xx·응답 스키마 오류·learning 원문 조회 실패는 `FAILED`로 처리한다. 학생 이름·닉네임 필드는 요청에 넣지 않으며, 알려진 닉네임이 본문에 포함된 경우 전송 전에 가린다.
- LLM 요청에는 학생 이름·식별정보를 넣지 않음. 학생 ID는 가명 토큰으로 치환 (NFR-SEC-03)

### 4.3 scoring-service (호출: ai)

#### #87 M2 확정 계약 (2026-10-29 담당자 답변 반영)

- `POST /internal/m2/scores`: `{prompt:string, text:string, grade:integer(3~6), inputType:"NARRATIVE"|"ESSAY", keywords:string[]}`. keywords 생략은 빈 배열. 문자열은 공백만 허용하지 않는다. 요청 보호 한도는 prompt 10,000자, text 50,000자, keywords 100개·각 200자이다.
- learning은 관리자가 입력한 `rubric_version.keywords`(문자열 배열, 서술형 전용)와 `mission_version.question`을 AI의 `keywords`·`question`으로 전달하고, AI는 question을 scoring의 prompt로 매핑한다. 이 저장 컬럼·관리자 입력·learning DTO·AI 연결은 **후속 서비스 변경 필요**이며 #87 scoring 구현이 제공했다고 해석하지 않는다.
- 모델 이름은 `NARRATIVE → m2-klue-narrative`, `ESSAY → m2-klue-essay`. 초3·4, 미활성 모델, 승인 scope 밖, 핵심어 없는 서술형은 **200 `{active:false}`**. 논술형은 핵심어를 사용하지 않는다.
- 승인 scope는 기존 core 논리 키 형식에 맞춘 `judgment/grade-{grade}/{narrative|essay}`의 **정확한 일치**로 검사한다. 학생 권한 헤더와 모델 승인 scope는 다른 개념이다. 문항별 승인 제한이 필요한 경우 현재 요청에는 문항 ID가 없으므로 별도 계약 확장 전에는 그 모델을 넓은 학년 scope로 승인하지 않는다.
- 성공 응답: `{active:true, inputType, scores:{hol,task_1,content_1,content_2,content_3,organization_1,organization_2,expression_1,expression_2}, rawScores:{동일한 9개 키}, model:{name,version,revision}}`. scores.hol은 1~4 정수, 나머지는 1~5 정수. rawScores는 변환 전 유한 소수값이며 범위 자르지 않는다. 원점수 저장은 소비 측 `judgment.model_scores` 연결이 필요하다(scoring은 무상태).
- 받은 회귀 2.0은 train_info의 max_length·with_keyword와 score_cuts.json을 사용한다. 학습 입력은 `[학년] 초N [지시문] ...` + 서술형일 때 ` [핵심어] `와 쉼표로 결합한 핵심어, 두 번째 문장은 학생 글이다. `truncation=only_second`, token_type_ids 제외. 컷 경계와 같으면 위 점수로 변환한다. 서술형 content_3도 **모델 점수**를 쓰며 예전 핵심어 개수 규칙으로 대체하지 않는다(수빈님 답변). 메타데이터·컷이 잘못되면 반올림으로 대체하지 않고 실패한다.
- 401 내부 토큰 오류, 400 요청/첫 문장 토큰 길이 오류, 503 `SCORING_UNAVAILABLE` 모델 설정·추론 장애 또는 처리 용량 초과. AI는 장애·시간 초과를 판정 처리 실패로 다루며 active:false로 바꾸거나 재시도하지 않는다(태윤님 답변). learning→AI 35초는 전체 예산으로, M2 단독 지연 측정과 구분한다.
- 사용량은 실제 추론 시도 후 성공/실패 모두 best-effort 발행한다. 토큰 수 null, model=`name@version`, 학생 원문·ID·핵심어 없음. 비활성 응답은 추론하지 않아 사용량 이벤트를 만들지 않는다.

구현된 내부 API 계약은 [contracts/openapi/scoring-service.yaml](../../contracts/openapi/scoring-service.yaml)에 기록한다. #85 버전 조회, #87 M2 점수, #88 M1 비활성 계약을 구현했다. M1은 미학습 상태로 활성 추론을 제공하지 않는다. 계약 테스트가 실제 FastAPI 경로·응답 스키마와 대조한다.

#### #88 M1 미학습 상태의 구현 계약

- `problem`은 mission_version.question, `answerKey`는 answer_key.finalAnswer 문자열이다. `solution`은 정답 풀이가 아닌 학생의 `{steps: 문자열 배열, finalAnswer: 문자열}`이다. 단계 순서와 빈 단계의 위치를 보존하며, 최소 한 단계는 공백 아닌 내용이 있어야 한다. 세 최상위 항목과 두 solution 항목은 필수이며 알 수 없는 필드·잘못된 타입·공백만 있는 문제/정답/최종 답은 400이다.
- 내부 토큰 누락·불일치는 401. 유효한 요청은 현재 항상 HTTP 200 `{active:false}`를 반환한다. M1 학습·평가·로더·승인 범위 계약이 없으므로 core에 모델 메타데이터를 등록하는 것만으로 활성화되지 않는다. M2 모델을 대신 사용하거나 문자열 비교로 정답 판정을 흉내 내지 않는다.
- 추론하지 않으므로 M1 사용량 이벤트도 발행하지 않는다. 문항·학생 풀이를 로그에 기록하지 않는다. 기존 내부 인증·오류 처리를 재사용한다.
- #88의 미학습 예외에 따라 이번 완료 범위는 비활성 계약이다. 향후 활성 추론은 기존 ModelRegistry·UsagePublisher를 재사용하고 threadpool에서 실행한다. 확신도 0.8 미만은 scoring이 실수 위치를 제외하고 ai가 보류를 결정한다. 활성 응답 필드·단계 번호 기준, 실제 모델/승인 scope 및 0.8 경계 검증은 활성화 후속 작업이며 이번에 검증 완료로 표시하지 않는다.


| Method | Path | 설명 |
|---|---|---|
| POST | `/internal/m2/scores` | `{prompt, text, grade, inputType, keywords}` → 총점 1~4점·8개 항목 1~5점·버전 (활성 범위 밖이면 `{active:false}`). `inputType`(`NARRATIVE`·`ESSAY`)으로 모델 선택(`m2-klue-narrative`·`m2-klue-essay`). `grade`(3~6)는 scoring이 `초{grade}`로 바꿔 모델 입력에 사용, 학습 데이터 학년(초5·6) 밖은 활성 범위 밖 |
| POST | `/internal/m1/checks` | `{problem, answerKey, solution:{steps,finalAnswer}}` → 현재 미학습이므로 `{active:false}`. 활성 추론·확신도 처리는 후속 범위(P15) |
| GET | `/internal/versions` | 로딩 완료한 활성 모델 `{items:[{name,version,revision}]}`. name 순 정렬, 없으면 `{items:[]}`. 내부 토큰 필수 |

#### #85 scoring 모델 조회·로딩 기준 (2026-10-28)

- core의 활성 snapshot에서 `kind=MODEL`, 이름이 `m2-` 또는 `m1-`로 시작하는 항목만 처리한다. `artifactUri`의 S3 디렉터리를 내려받아 로컬 파일로만 로딩하며 외부 모델 저장소로 대체하지 않는다.
- `/internal/versions`는 core가 요구한 버전이 아니라 **실제로 로딩 완료한 버전**을 반환한다. 초기 조회·로딩 전에는 빈 목록이며 준비 여부는 `/health/ready`의 `models` 항목으로 구분한다. S3 경로·평가 자료·비밀 값은 반환하지 않는다.
- 사용자 결정: core 조회 성공 + 활성 모델 없음은 `models=UP`. 해당 모델은 비활성이며 #87·#88에서 `{active:false}`로 응답한다. core 조회 실패 또는 첫 가중치 로딩 실패는 `models=DOWN` 상태에서 백그라운드 재시도하고 프로세스를 종료하지 않는다. 다른 readiness 항목도 모두 UP이어야 HTTP 200이다.
- 교체는 새 가중치 로딩 완료 후 수행한다. 교체 실패 시 기존 로딩 버전을 유지한다. 같은 kind·name의 낮은 revision은 무시하고, 실패한 최신 revision은 재시도할 수 있다. 새 승인 범위가 좁아졌다면 기존 모델 유지 중에도 이전·새 범위의 교집합에서만 사용한다.
- scope는 #43 계약의 문자열 정확 일치로 검사한다. 학년·입력 유형의 M2 scope는 위 #87 계약의 정확 일치 키를 사용한다. core 승인 범위를 임의로 확장하지 않는다.
- #85는 기동 snapshot·로더·레지스트리 기반이다. Pod별 큐 바인딩 후 snapshot 조회·보존 이벤트 조정·재연결은 #86에서 연결한다. #85만으로 실시간 모델 버전 동기화를 완료했다고 간주하지 않는다.

### 4.4 report-service (호출: core)
- 호출 대상은 `report-api` Deployment (KEDA로 0까지 줄어드는 `report-worker`와 분리, [아키텍처 4.4](architecture.md#44-확장))

| Method | Path | 설명 |
|---|---|---|
| GET | `/internal/reports?studentId&status` | 리포트 목록 |
| GET | `/internal/reports/{reportId}?revision` | 상세 (3.4 스키마), 기본 최신판·양의 revision으로 이전판 조회 |
| GET | `/internal/reports/{reportId}/evidence/{itemId}` | 항목 근거 |
| GET | `/internal/reports/{reportId}/files/{format}` | 단기 presigned URL 발급 → `{url, expiresAt}` |

- core는 현재 이용 권한으로 `X-Report-Narrative-Enabled:true|false`를 설정해야 함(공개 요청의 같은 헤더는 전달하지 않음). report는 누락 시 false로 처리해 응답·다운로드에서 AI 서술·생각 유형 summary·저녁 질문을 가림
- 목록은 학생/대상 주별 최신 revision을 고른 뒤 status를 적용하며 1.1 페이지 봉투를 사용한다. 상세의 기본값은 같은 학생·대상 주 최신판, `revision` 지정 시 해당 판이다. evidence/files 경로는 전달한 실제 reportId 판에 속한 항목·파일을 조회한다.
- 파일 키는 `reports/{studentId}/{reportId}/r{revision}/{full|free}/{pdf|md|html}`다. DB `report_file`에는 full 키 3개를 저장하며 무료용 파생 파일도 생성한다. 다운로드 수명은 설정값이며 운영 기본안은 300초다. 버전·형식·학생이 맞지 않는 키를 서명하지 않는다.

### 4.5 core-service (호출: ai, scoring, learning, report)
| Method | Path | 설명 |
|---|---|---|
| GET | `/internal/model-versions/active` | 기동 시 활성 모델·프롬프트 버전 조회 |
| POST | `/internal/deletion-requests/{deletionRequestId}/completions` | learning·report가 `student.deleted` 처리 후 완료 보고 `{service}`. 두 서비스 모두 보고 시 `COMPLETED` (멱등, P09) |

- 비동기 메시지(`report.generate` 등)는 [아키텍처 1.4](architecture.md#14-메시지-목록) 참고
- report 삭제: PROFILE·RECORDS 모두 리포트 내용·파일을 물리 삭제하고 `report_deletion_guard`에 식별 UUID·범위·기준 시각·상태만 남김. core가 RECORDS 후에도 학습을 자동 재개하지 않으므로 두 scope 모두 이후 생성을 차단(재개는 별도 계약 필요)
- 삭제 학생의 queued job 정리와 늦은 상태 이벤트 무시는 core 미구현(검증 보고서 B9). report 삭제 장벽이 core job 상태를 대신 정리하지 않음

### 4.6 #43 AI 사용량 조회 계약

- `GET /api/v1/admin/ai-usage`: 기존 #36 Bearer·`SERVICE_OPS` 검사를 사용한다. 필수 `from`, `to`는 0001~9999 연도의 ISO 날짜이며 KST 기준 양 끝 날짜를 포함한다. 조회 기간은 양 끝 포함 최대 366일이다. `from > to`, 366일 초과 또는 허용 연도 밖의 날짜는 DB 조회 전에 400 `VALIDATION_FAILED`로 거부한다. 선택 `callType`은 기존 사용량 이벤트의 6개 호출 종류 중 하나다.
- 응답은 `{period:{from,to},items:[{callType,calls,failures,latencyMs,inputTokens,outputTokens,costUsd,unpricedCalls}]}`다. 기간에 실제 호출이 있는 종류만 반환한다. `latencyMs`는 성공·실패를 포함한 호출당 평균 지연(ms)이다. 토큰은 합계이며 하나라도 미기록이면 해당 합계는 null이다.
- `costUsd`는 저장된 소비 시점 비용의 합계다. 단가 미등록 등 null 비용이 하나라도 있으면 합계도 null이며 `unpricedCalls`로 미산정 호출 수를 공개한다. 빈 결과는 `items:[]`이고 null을 0으로 치환하지 않는다. 수집·멱등 처리·과거 단가 계산은 변경하지 않는다.
- 요금제 한도, 월 예산 알림, 결제·구독 구현은 #43 조회 범위에 포함하지 않는다.


## 5. 구현 계약

### 5.1 #36 Google OAuth·토큰 구현 계약 (개정 P01 정렬)

인증 경로의 정식 공개 계약은 [core-service OpenAPI](../../contracts/openapi/core-service.yaml). 이 절은 부모·관리자 Google 인증과 동석 학생 진입, 학생 기기·PIN은 3.11.

- 기기 진입 3개 경로(`POST /auth/student/devices`, `GET /auth/student/profiles`, `POST /auth/student/login`)만 Bearer 검사에서 제외. POST는 다른 쿠키 API와 같이 정확한 web Origin·`X-Requested-With` 검사 유지. 다른 메서드·유사 경로와 `/auth/student-sessions`는 제외하지 않음

- 학부모·관리자: Google core 콜백 → refresh 쿠키 → web `/oauth/complete` → refresh → `/me`. access는 HS256, 기본 15분·메모리 보관. refresh는 256비트 난수·SHA-256 해시 저장, 최초 로그인부터 최대 7일이며 회전으로 연장하지 않는다. 재사용 시 해당 세션 폐기.
- 학생(동석·단독 공통): access 전용, refresh 미발급. 동석 `/auth/student-sessions`는 부모 refresh를 소비하고 세션 버전·역할·학생 범위를 변경하며 부모 refresh 쿠키를 만료시킨다. 학생 상태에서 `/auth/refresh`는 401이다. 기존 부모 access도 거부한다. 단독 PIN 로그인은 별도 학생 auth_session을 생성하며 기존 부모 세션을 변경하지 않는다.
- JWT에는 `sub`(계정 UUID), `sid`, `ver`, `role`, `studentId`(학생만), `iss`, `aud`, `iat`, `exp`, `jti`를 넣는다. 매 요청에서 세션·현재 계정·자녀 연결·동의를 확인한다. 기기 해제 시 기존 학생 access를 즉시 폐기하는 별도 정책은 추가하지 않는다.
- 학부모 access 기본 15분, 학생은 `AUTH_STUDENT_ACCESS_TTL`로 별도 관리하며 초기 기본값은 15분이다. 학생 만료·새로고침 시 자동 refresh하지 않고 학생 진입 화면으로 이동한다. 기기·PIN API로 단독 재진입하며 미등록 기기는 등록을 안내한다. 토큰을 영구 저장해 새로고침을 우회하지 않는다.
- 부모 refresh 응답 `{accessToken,expiresIn,role,child:null,nextAction,startPath}` + 회전 쿠키. 동석 응답 `{accessToken,expiresIn,role:STUDENT,child,nextAction:READY,startPath:/student/home}` + refresh 쿠키 삭제. child는 `{id,nickname,grade,birthYear}`(기존 #7 소비자 계약)이다. 단독 PIN 로그인 응답(3.11)은 `child.childId`를 쓰므로 프론트 경계에서 정규화한다.
- `GET /me`는 부모/관리자에게 `{userId,name,email,role,permissions,child:null,nextAction,startPath}`, 학생에게 `{role,child,nextAction,startPath}`만 반환한다. 학생에게 부모 개인정보·권한을 반환하지 않는다. 학생은 `/me/consents` 등 부모 계정 관리 API를 사용할 수 없다.
- 로그아웃은 현재 쿠키의 부모 세션 또는 Bearer로 전달된 학생 세션을 종료하고 refresh 쿠키를 삭제한다. 다른 기기는 유지한다. 쿠키 API는 정확한 web Origin과 `X-Requested-With: XMLHttpRequest`를 요구한다.
- web/API 동일 origin. refresh 쿠키 `sagomungchi_refresh`: HttpOnly·Secure·SameSite=Strict·Path=/api/v1/auth. OAuth 상태 쿠키 `sagomungchi_oauth`: HttpOnly·Secure·SameSite=Lax·Path=/api/v1/auth/google, 10분. 로컬 HTTP만 Secure=false.
- Google state·nonce·PKCE S256 및 ID 토큰 JWKS 서명·iss·aud·exp·nonce 검증. 서비스 토큰을 URL에 넣지 않는다. callback 성공은 `/oauth/complete`, 실패는 `/login?oauthError=<고정 코드>`.
- 부모/관리자 refresh는 Web Locks로 탭 간 직렬화한다. 학생 전환·로그아웃 알림을 받은 다른 탭은 토큰·캐시를 지우며 학생 refresh로 다시 로그인하지 않는다. 학생→부모 복귀는 Google 로그인부터 시작한다.
- 계정 복구·비밀번호 변경 API는 Google 단일 로그인 범위에서 제외(기기·PIN 저장은 core V13, Google 재인증은 5.6).


### 5.2 #43 모델 레지스트리 확정 계약

자동 품질 합격선 없이 SERVICE_OPS의 명시적 사람 승인을 사용한다. 새 승인 상태 enum은 만들지 않는다. 등록 상태는 기존 REGISTERED·ACTIVE·INACTIVE다.

- GET `/api/v1/admin/model-versions?kind&page=0&size=20`: `{items,page,size,totalElements}`. size 1~100, page 0 이상. kind 생략 시 전체 종류. 항목은 `{id,kind,name,version,refId,artifactUri,evalResult,status,approvedBy,activatedAt,createdAt}`다.
- POST 같은 경로: `{kind,name,version,refId?,artifactUri?,evaluation}` → 201 항목. `(kind,name,version)` 중복은 409. RUBRIC은 learning 원본 UUID인 refId 필수, 다른 종류는 refId를 받지 않는다. 원본 내용·수정·존재 확인을 core에서 소유하지 않는다.
- `evaluation`은 `{datasetId,datasetVersion,baselineVersion,comparisonReport,trainingEvaluationSeparation,quoteAccuracy,calculationAccuracy,humanReview,evaluatedScopes}`다. 문자열 필드는 모두 비어 있지 않은 평가 근거·검토 기록 또는 그 참조이며 `baselineVersion`은 비교한 기존 버전 식별값이다. 최초 등록도 비교 기준을 명시한다. `evaluatedScopes`는 평가한 범위 키의 중복 없는 비어 있지 않은 배열이다. 평가·활성화·복귀 범위 배열의 null 항목은 422로 거부한다.
- 범위 키는 소비자가 동일하게 사용하는 소문자 논리 식별자(예: `judgment/grade-3/narrative`, 최대 200자, `[a-z0-9][a-z0-9._:/-]*`)다. core는 문자열의 정확한 집합 포함 관계만 확인하며 와일드카드·계층 확장을 하지 않는다. 원본 평가 문항·학생 원문은 저장하지 않는다. 검토 기록의 사실성·품질 수치의 적합성은 사람이 판단하며 서버는 자료 자체를 실행·검증했다고 주장하지 않는다.
- POST `/{versionId}/activate`: `{approved:true,scopes,reason,reanalysisPlanned}`. REGISTERED만 최초 승인·활성화할 수 있다. 필수 평가 근거 누락·미승인·평가 외 범위는 422, 이미 활성화 이력이 있는 대상은 409다. 승인자는 요청 값이 아닌 #36 인증 계정 ID다. 기존 ACTIVE는 INACTIVE가 되고 승인·평가 이력은 보존한다.
- POST `/{versionId}/rollback`: `{scopes,reason,reanalysisPlanned}`. 같은 kind·name의 현재 ACTIVE가 있고, 대상이 과거 승인·활성화된 INACTIVE이며 요청 범위가 당시 승인 범위의 부분 집합일 때만 성공한다. 잘못된 상태는 409, 승인 외 범위는 422다. 원 승인자·승인 범위는 보존하고 복귀 수행자는 감사 이력에 별도 기록한다.
- `reanalysisPlanned`는 재분석 여부 기록일 뿐 작업을 실행하지 않는다. 기존 관찰·질문·분석·리포트 결과는 수정하지 않는다. 등록·성공 교체는 audit_log에 추가하며 교체의 상태·감사·Outbox는 한 트랜잭션이다.
- `evalResult`는 `{evidence:evaluation,approval:null|{scopes,reason,approvedBy,approvedAt},activeScopes:[],revision:0}`로 저장한다. 활성화·복귀 때 activeScopes와 revision을 갱신한다. 동일 kind·name을 advisory transaction lock으로 직렬화하고 해당 그룹에 저장된 최대 revision + 1을 사용한다. 평가 근거와 최초 승인은 덮어쓰지 않는다.
- 내부 GET `/internal/model-versions/active`는 기존 `X-Internal-Token` 필수이며 `{items:[{id,kind,name,version,refId,artifactUri,scopes,revision,activatedAt}]}`를 반환한다. 평가·관리자 정보는 전파하지 않는다. 공개 API base(`/api/v1`)를 붙이지 않는다.
- 이벤트는 `contracts/events/model.version.activated.v1.schema.json` data와 기존 봉투를 사용한다. `revision`은 kind·name별 단조 증가 값이다. 소비자는 큐 바인딩 후 내부 API로 초기화하고, 초기화 중 이벤트를 보존·조정하며 더 높은 revision만 적용한다. 승인 scope를 실제 요청 시에도 제한해야 한다.
- ai·scoring의 Pod별 소비·readiness·실제 교체 구현은 별도 서비스 작업이며 core 계약 테스트의 큐 대역으로 완료 처리하지 않는다.

- #43 기존 SQL NULL 평가 행은 목록에서 evalResult:null로 보존하고 활성화/복귀 시 422로 거부한다. 승인 근거·적용 범위가 불완전한 기존 ACTIVE 행이 있으면 내부 snapshot은 MODEL_VERSION_STATE_INVALID(503)로 명시적으로 실패하며 임의 기본 버전을 반환하지 않는다. 신규 등록은 계속 완전한 평가 기록을 요구한다.


### 5.3 #37 동의·자녀 구현 계약

- 문서 조회·저장·철회·자녀 등록의 정식 스키마는 core OpenAPI를 따른다. GET /consent-documents는 3종 현재 문서를 목록 봉투로 반환한다. 현재=KST 시행일 이하에서 effective_from·created_at·id 내림차순 첫 문서. 게시 문서가 없거나 불완전하면 503 CONSENT_DOCUMENTS_UNAVAILABLE이며 가짜 본문을 생성하지 않는다.
- POST /me/consents: `{consents:[{documentId,version,agreed}],childId?}`. childId 없음=TERMS·PRIVACY, 있음=소유한 자녀 GUARDIAN 재동의. 필요한 범위의 모든 현재 항목을 정확히 1개씩 보낸다. 필수 거부/누락은 400 VALIDATION_FAILED, 오래된 문서/범위 불일치는 409 CONSENT_DOCUMENT_CHANGED. 200은 해당 범위 동의 목록 봉투다. 재전송은 현재 선택과 같으면 행을 중복 생성하지 않는다.
- GET /me/consents: 주체·문서 메타데이터·studentId·agreed·status·agreedAt·withdrawnAt의 전체 이력(최대 항목 제한 없이 1개 목록 봉투). POST /me/consents/{consentId}/withdrawal: 본인 이력만 철회, 반복 요청은 같은 행 반환. 타인/없는 ID는 403 FORBIDDEN. 필수 철회 후에는 계정/해당 자녀의 현재 동의 검사로 접근을 차단한다. 삭제·탈퇴는 #45에서 별도 요청하며 자동 삭제하지 않는다.
- 권한 판정은 같은 문서·주체·자녀의 최신 이력만 사용한다. 필수 계정 동의 전에는 본인 조회·로그아웃·동의 관리만 허용한다. 현재 계정 동의가 있어야 POST /children을 사용한다. /me nextAction은 CONSENT_REQUIRED → CHILD_REGISTRATION_REQUIRED → READY다. 연결은 있으나 GUARDIAN 철회인 자녀는 목록에 guardianConsentRequired=true로 남기고 재동의를 안내한다.
- POST /children: `{nickname,grade,birthYear,consents}` → 201 `{id,nickname,grade,birthYear}`. 학년 3~6, 별명 1~40자(앞뒤 공백 제거), 출생연도 1900~현재 KST 연도. 필수 GUARDIAN 동의와 학생·연결을 원자 저장한다. 보호자 행 잠금 후 LINKED 연결 수를 검사해 동시 요청도 최대 3명, 초과 409 CHILD_LIMIT_REACHED다.
- GET /children: 목록 봉투 items=`{id,nickname,grade,birthYear,guardianConsentRequired,hasRecords:boolean|null,recordState:AVAILABLE|UNAVAILABLE|CONSENT_REQUIRED,pinSet:boolean,pinLocked:boolean}`. 기존 프론트 id 계약을 유지한다. 실제 learning `/internal/records/students/{studentId}/exists`의 hasRecords로 기록 유무를 전달한다. 공급자 미구현·실패는 UNAVAILABLE/null로 명시하며 기록 없음으로 바꾸지 않는다. 동의 없는 자녀는 CONSENT_REQUIRED/null이며 기록 조회·동석 진입을 막는다. pinSet·pinLocked는 #58에서 실제 PIN 저장 상태를 반환한다. plan은 이 API에서 임의 생성하지 않는다.
- 기능 간 접근은 service를 거친다. requireLinked의 반환 계약을 유지하고 현재 GUARDIAN 동의를 확인한다. 보호자 내부 scope는 이용 가능한 자녀만 포함한다. 필터가 자녀별 경로의 scope를 확인하며 학생은 매 인증에서 현재 계정·GUARDIAN 동의를 다시 확인한다.


### 5.4 #37 선행 learning 기록 존재 확인

- 정식 내부 계약은 [learning-service OpenAPI](../../contracts/openapi/learning-service.yaml)를 따른다. `GET /internal/records/students/{studentId}/exists` → 200 `{studentId,hasRecords:boolean}`. 기간·페이지·건수·답변 원문·메모는 반환하지 않는다. 목록·상세·통계는 #27에서 4.1 "기록 조회"로 추가했다(같은 실패·삭제 제외 기준).
- core의 공개 GET /children → GuardianshipService → core learning의 LearningRecordService → LearningRecordClient → 기존 LearningClient(공유 서킷) → learning RecordExistsController → RecordExistsService → RecordExistsRepository/Mapper → learning DB 순서다. core는 learning DB를 직접 읽지 않는다.
- 기간 필터가 없는 전체 보존 기록을 조회한다. P08에 따라 답변 제출이 있는 완료/미완료 시도가 대상이며, 초안만 있는 시도는 제외한다. 해당 시도의 답변이 모두 FAILED 판정이면 제외한다. PENDING/RUNNING/DONE(보류 포함) 및 아직 판정 행이 없는 제출 답변은 실패 확정 상태가 아니므로 포함한다. 답변 저장과 후속 처리는 구분한다.
- `deleted_student` 표식이 있는 학생은 조회 대상에서 제외해 false다. 삭제·재등록·재학습의 수명주기를 새로 구현하지 않는다. #27과 삭제 기능에서 이 정책을 바꾸면 소비자·회귀 테스트를 함께 변경한다.
- 기존 InternalAuthFilter의 내부 토큰 검증 뒤 PARENT/STUDENT/SYSTEM 역할과 X-Student-Scope를 검사한다. 잘못된 내부 토큰은 401, 미허용 역할·범위 밖 학생은 403이다. 학부모는 core에서 현재 연결·동의를 검사해 생성한 scope만 전달한다.
- DB/HTTP 장애는 정상 false로 변환하지 않는다. learning은 오류 응답, core는 기존 공개 계약에 따라 hasRecords=null, recordState=UNAVAILABLE로 표시한다. 정상 false/true는 recordState=AVAILABLE이다. 응답 studentId·boolean 형식이 다르면 UNAVAILABLE이다.
- 자녀별 원격 조회는 기존 최대 자녀 수 3을 상한으로 병렬 수행해 read timeout이 순차로 누적되는 것을 피한다. LearningHttpProperties의 기존 read timeout(기본 30초), learning-json 서킷의 최근 20회·최소 20회·실패율 50%·30초 차단 정책을 공유하며 재시도는 추가하지 않는다. 서킷 OPEN은 즉시 null/UNAVAILABLE이고 CLOSED의 개별 요청은 기존 timeout을 유지한다. 전체 HTTP 요청의 엄격한 30초 deadline을 새로 정의하거나 보장하지 않는다.
- core LearningRecordService는 검증된 PARENT 컨텍스트와 대상 학생 scope만 허용하는 기록 전용 service다. 기존 학생 전용 LearningProxyService의 역할·쓰기 권한은 완화하지 않는다.


### 5.5 #42 주간 리포트 구현 계약

- 자동 생성은 직전 KST 월~일, 매주 월요일 07:00이다. 부모 REGENERATE 한도는 자녀·주 계열 전체 1회(새 판을 기준으로 재요청해도 409 REPORT_REGENERATION_LIMIT). SERVICE_OPS 관리자는 같은 POST 경로에서 ADMIN_RETRY 작업을 무제한 생성한다. 생성 중 작업이 있으면 409 REPORT_GENERATION_IN_PROGRESS이다.
- 재생성 202는 `{jobId, childId, period:{from,to}, status:"QUEUED"}`다. 이전 reportId는 보존되고 report가 revision을 배정한다. 상품·구독 권한은 payment의 ProductEntitlementService에서 확인한다. 상품 설정 불완전·권한 조회 실패는 명시적인 오류로 처리하고 job/Outbox를 생성하지 않는다.
- reportId 조회의 자녀 연결·현재 필수/법정대리인 동의를 확인한 뒤 단일 학생 scope로 report-api를 호출한다. 없는 core reportId는 404 REPORT_NOT_FOUND다. 목록은 `{items:[3.4의 식별·기간·status·state·revision·generatedAt 필드]}`다. 상세는 3.4, 근거는 report-api JSON을 그대로 전달하고 다운로드는 pdf/md의 `{url,expiresAt}`다. report 장애는 503 REPORT_UNAVAILABLE, JSON 계약 위반은 502 REPORT_CONTRACT_INVALID다. 성공 상세의 실제 반환 reportId로 열람 기록을 남긴다.
- v1 이벤트 스키마·봉투·생산자·소비자는 [report-messages.md](../../contracts/events/report-messages.md). 결정 근거는 [리포트 보고서](../report/report.md).

#### 5.5.1 #152 관리자 실패 리포트 재처리 (report 공급 계약)

- #47 담당자와 합의: core가 관리자 권한·Idempotency-Key·현재 이용 권한/학생 상태를 확인하고, 원래 실패 작업과 **새 jobId**의 연결·감사 기록을 관리한다. report에는 기존 `report.generate.v1`의 `trigger=ADMIN_RETRY`와 현재 권한의 `narrativeEnabled`를 보낸다. 같은 재처리 요청 재전달은 같은 jobId·같은 업무 본문을 사용한다. 새로 명시적으로 재처리할 때만 새 jobId를 발급한다.
- report는 기존 GenerationService·JobLocks·ReportRepository·OutboxRelay를 재사용한다. 새 jobId이면 같은 학생/주의 다음 revision을 생성하고 이전 판을 보존한다. 같은 jobId의 COMPLETED·FAILED 재전달은 ACK 후 종료하며 상태를 되돌리거나 생성기를 다시 호출하지 않는다(#50 유지). 동시 전달은 작업 잠금으로 중복 실행을 막고 기존 소비자의 지연 재시도 정책을 따른다.
- started/completed/failed는 **받은 새 jobId**, 학생 ID 및 그 실행에 배정한 같은 reportId를 반환한다. 원래 실패 jobId·revision·관리자 ID는 report 이벤트에 추가하지 않는다. core는 jobId로 실행을 구분해 지연된 원작업 이벤트가 새 작업에 반영되지 않게 한다. report에는 core 결과 이벤트를 다시 적용하는 API가 없다.
- 시작 행과 started Outbox, 종료 상태/항목/파일과 terminal Outbox는 각각 같은 DB 트랜잭션이다. Outbox 발행은 at-least-once이므로 core는 봉투 id와 조건부 상태 전이로 중복·순서 역전을 방어한다. 새 이벤트 ID를 붙여 같은 jobId를 다시 보내도 업무 실행은 늘어나지 않는다.
- report는 기존 삭제 장벽과 core ACTIVE 프로필 조회를 유지한다. 삭제 장벽으로 거부된 작업은 기존 정책대로 생성·성공 이벤트를 만들지 않는다. 삭제와 경쟁한 core 작업의 취소·정리는 core 책임이며 #152에서 삭제 정책이나 거짓 실패/완료 이벤트를 임의 추가하지 않는다.
- 새 HTTP API·이벤트 버전·DB 컬럼은 필요 없다. `/admin/jobs/{id}/retry`의 실제 요청 접수·원작업 연결·감사 처리는 #47 후속이며, 이 공급 계약만으로 현재 core의 `JOB_RETRY_UNAVAILABLE` 차단을 해제하지 않는다.
- 요청·결과 예시: [report-admin-retry](../../contracts/examples/report-admin-retry/). 기존 [공유 메시지 계약](../../contracts/events/report-messages.md)과 같은 스키마를 사용한다.

### 5.6 #45 계정 관리·Google 재확인·삭제·탈퇴 계약

- 기존 Google 로그인과 별도 재인증 흐름을 사용한다. `POST /me/reauth`에 `{purpose: PIN_CHANGE|CHILD_UNLINK|CHILD_DELETE|WITHDRAWAL, childId?, scope?}`를 보내면 `{challengeId,authorizationUrl,expiresAt}`를 반환하고 HttpOnly/Secure/SameSite=Lax 재인증 상태 쿠키를 설정한다. CHILD_DELETE는 PROFILE/RECORDS scope를 반드시 지정한다. WITHDRAWAL은 자녀/scope를 허용하지 않는다. 다른 자녀 작업은 childId 필수다.
- Google redirect URI는 web origin + `/api/v1/auth/google/reauth/callback`이다. 기존 GoogleOAuthClient의 code·PKCE·서명·iss·aud·exp·nonce 검증을 재사용한다. callback은 현재 계정의 Google sub와 일치할 때만 challenge를 VERIFIED로 바꾸며 로그인/refresh를 발급하지 않는다. 계정 선택은 비밀번호/MFA 재입력을 보장하지 않는다. 클라이언트는 원래 로그인 세션을 유지한 상태에서 `POST /me/reauth`에 `{challengeId}`를 보내 `{reauthToken,expiresAt}`를 한 번 수령한다. 아직 callback 전이면 409 REAUTH_PENDING이다. callback 응답은 완료 안내 JSON이다.
- challenge 10분, reauthToken 5분(설정값, 세션 만료 이내). 토큰은 256비트 난수, DB에는 SHA-256 해시만 저장한다. 프론트는 메모리에만 보관한다. 사용자·세션 ID/version·purpose·childId·삭제 scope에 결합하며 변경 트랜잭션에서 정확히 1회 소비한다. 일반 access/로그인 상태는 재인증 증명이 아니다. 잘못된 계정·만료·위조·다른 범위·중복 사용은 403 REAUTH_REQUIRED다.
- #58은 `ReauthenticationService.consume(identity, token, ReauthPurpose.PIN_CHANGE, childId)`를 PIN 변경의 같은 트랜잭션 안에서 호출한다(MANDATORY). 기존 인증/현재 자녀 권한 검사를 별도로 수행한다.
- PATCH /me `{name}` → `{userId,name}`; PATCH /children/{id} `{nickname?,grade?}` → 현재 자녀. 공백·범위 밖 입력 거부. 기존 기록/학년을 변경하지 않는다. 학생 역할 금지, 계정·자녀의 현재 동의를 검사한다.
- deletion-impact → `{childId,actions:[{scope,effect}],retainedTransactionsYears:5,deviceCleanupPending:false}`. 연결 해제는 UNLINKED 이력을 남기고 학생 세션을 폐기한다. 삭제 확정은 `X-Reauth-Token`, `{scope}` 필수, 202 `{deletionRequestId,childId,scope,status,completedServices}`. 동시에 진행 중인 다른 삭제는 409 DELETION_IN_PROGRESS다. 재확인이 유효한 요청을 즉시 CONFIRMED로 저장한다.
- PROFILE은 연결 해제·학생 이용 차단 후 두 서비스 완료 시 프로필 필드를 지우고 DELETED 표식을 남긴다(FK/거래 보존용 ID 유지). RECORDS는 프로필을 유지하되 CONFIRMED부터 이용을 차단한다. 완료 후에도 자동 학습 재개는 하지 않는다. learning의 삭제 표식 이후 새 기록 허용 계약은 후속 통합 사항이다. 두 scope 모두 core 분석 대화·근거와 learning/report 기록을 삭제한다. 삭제 확정 때 `student_device_child`를 제거하고 PIN 해시·잠금을 지운다(ERD 10장).
- GET /children/{id}/deletion-requests/{requestId}: 본인 소유 삭제 상태 조회. 삭제 후에도 본인이 요청한 상태는 조회 가능하다. 다른 보호자는 403이다.
- 내부 완료 API는 기존 내부 토큰 + SYSTEM 컨텍스트/대상 학생 scope를 요구하며 `{service:learning|report}`만 허용한다. `(request_id,service)` UNIQUE 기록으로 중복/동시 보고를 멱등 처리한다. CONFIRMED인 요청만 완료할 수 있으며 두 서비스가 모두 있어야 COMPLETED다. 한 서비스 완료는 실제 전체 삭제 완료가 아니다.
- 필수 동의 철회 뒤에도 재인증·삭제 영향·연결 해제·삭제/탈퇴 요청 및 상태 조회는 가능하다. 재동의를 파기의 선행 조건으로 요구하지 않는다. 이 경로는 계정 활성·보호자 소유권·재확인을 계속 검사한다. 정보 수정에는 기존 동의를 요구한다.
- 탈퇴 precheck는 core payment 소유 서비스로 현재 subscription/refund_request를 실제 조회한다. ACTIVE(기간 내/자동갱신), RENEWAL_FAILED, 취소됐어도 기간 내 구독 및 REQUESTED/APPROVED/FAILED 환불은 409 WITHDRAWAL_BLOCKED다. DB 오류는 성공으로 대체하지 않는다. #48은 결제/환불 쓰기 시 같은 parent 계정 행 잠금 규약에 참여해야 한다.
- POST /me/withdrawal은 WITHDRAWAL 재인증, 계정 행 잠금 후 재확인한다. 즉시 WITHDRAWAL_REQUESTED·전체 세션/refresh 폐기·자녀 PROFILE 삭제 요청/Outbox를 같은 트랜잭션에 저장한다. 자녀가 모두 삭제되면 WITHDRAWN 및 withdrawal COMPLETED다. 자녀가 없으면 즉시 완료한다. 요청 즉시 로그인/취소 불가다.
- 응답 `{withdrawalRequestId,status,statusToken}`의 statusToken은 별도 256비트 조회 전용 영수증이다(DB에는 해시). 세션 폐기 후 `GET /me/withdrawal`에 `X-Withdrawal-Status-Token`으로 해당 요청의 `{withdrawalRequestId,status}`만 조회한다. 로그인/사용자 정보 접근 권한을 주지 않는다. 헤더/응답은 no-store다. 인증 상태에서도 자신의 최신 요청을 조회할 수 있다.
- 연결 해제 뒤에도 같은 보호자의 등록 이력으로 PROFILE·RECORDS 삭제를 요청할 수 있다. PIN_CHANGE·CHILD_UNLINK 재인증은 현재 LINKED 소유권이 필요하다.
- 진행 중인 RECORDS 삭제와 탈퇴가 겹치면 RECORDS 완료 뒤 새 PROFILE 요청·이벤트를 기록한다. 이벤트 scope를 바꾸거나 완료 보고를 다른 요청에 쓰지 않는다.
- 탈퇴 완료 시 연락 이메일·표시 이름은 계정 tombstone으로 정리하고 Google sub는 재로그인 차단 표식으로 유지한다. 상품·거래·구독·환불 행은 변경하지 않는다.
- learning은 `student.deleted`를 받아 학습 기록을 삭제한 뒤 `{service:"learning"}`으로 완료를 보고한다(#128, SYSTEM 컨텍스트 + 대상 학생 범위). 같은 이벤트를 다시 받으면 삭제 없이 보고만 다시 보낸다([검증 보고서 B3](../report/audit.md) 해소).

### 5.7 #46 support 구현 계약

- `/help`·`/notices`는 Bearer 인증·현재 동의가 필요하다. help의 role 생략 시 현재 역할, 다른 역할 요청은 403. 기존 Google·기기·PIN·탈퇴 상태 토큰 예외는 유지한다.
- 신고·문의 소유자는 `(userId, requesterRole, requesterStudentId)`다. 학생은 세션 studentId만, 보호자는 자신의 PARENT 건만 조회한다. 자녀 대상은 현재 연결·동의를 재검사한다. 기존 소유 역할이 없는 행은 사용자 목록에 추정 노출하지 않는다.
- `POST /error-reports`: 기존 필드 + 선택 `studentId`(서버 확인), UUID Idempotency-Key 필수. learning 대상은 아래 공급자 조회에서 학생·시도를 검증한 뒤 저장한다. ANALYSIS targetId는 core conversation_message ID, REPORT는 완료 report ID이며 보호자만 가능하다. 접수는 판정을 변경하지 않는다.
- `POST /inquiries`: `{category:ACCOUNT|USAGE|PAYMENT,title,body,studentId?,attemptId?}`. 학생은 세션 학생으로 고정한다. 세 문의 분류는 학생·보호자 모두 접수할 수 있으며, 문의 분류가 결제 데이터 조회 권한을 부여하지 않는다. attemptId는 공급자가 해당 학생 시도로 확인할 때만 연결한다. 문의 목록·상세는 `{inquiryId,category,title,body,status,answer?,answeredAt?,createdAt}`.
- 관리자 신고 PATCH `{status,reviewReason,reviewResult?}`: RECEIVED→IN_REVIEW→RESOLVED. RESOLVED는 결과·사유 필수(reviewResult 생략 시 reviewReason 사용). 완료 후 재요청은 동일 값만 허용한다. 문의 답변 `{answer}`는 RECEIVED/IN_REVIEW→RESOLVED, 같은 답변 재시도는 동일 결과, 변경은 409.
- 정정 POST는 UUID Idempotency-Key + `{reason,corrected:CORRECT|PARTIAL|RETHINK|HELD}`. 이번 공급자 계약은 JUDGMENT만 지원하며 다른 targetType은 422. 검토 중 신고에 정정 의도·이전 결과·고정 요청 ID를 먼저 커밋 → 트랜잭션 밖 learning HTTP → 성공 결과와 영향·신고 완료·알림을 같은 트랜잭션으로 저장한다. 실패/응답 유실은 완료하지 않으며 동일 ID로 재시도한다. 신고당 정정 1건, 다른 본문 재사용 409. 원본 학생 답변·판정은 덮어쓰지 않는다.
- 관리자 상세 원문은 저장된 attemptId·studentId에서만 조회한다. 임의 attemptId query를 받지 않는다. 목록·쓰기 응답에는 원문 없음. 원문은 draft·memo 제외 답변·판정만, 응답 전에 audit_log 저장(실패 시 원문 응답 실패). 문의 원문은 추가 `GET /admin/inquiries/{inquiryId}`를 동일하게 처리한다.
- 공지 POST/PATCH `{kind:NOTICE|MAINTENANCE,title,body,targetRoles:[STUDENT|PARENT|ADMIN],visibleFrom,visibleTo?}`. 역할·기간 검증, 종료 후 수정 금지. DELETE는 endedAt 기록이며 물리 삭제하지 않는다. 사용자 GET은 현재 역할과 `visibleFrom <= now < visibleTo`, endedAt 없음만 조회한다. 목록은 공통 page/size 봉투.
- 보호자 신고 완료·문의 답변만 기존 알림 service로 연결한다. 학생 건은 본인 결과 조회, 보호자 알림으로 우회하지 않는다. sourceEventId는 신고/문의 UUID이며 완료 여부만 알린다. 링크는 `/parent/support?reportId=...` 또는 `?inquiryId=...`, 소비자에서 본인 상세 API를 호출한다.

### learning 공급자 필요 계약 (아직 구현되지 않음)

현재 learning controller/OpenAPI에는 target 해석·SERVICE_OPS 원문·정정 구현이 없다. 학생 전용 `/internal/attempts/{id}`를 관리자로 위장 호출하지 않는다. 별도 `contracts/openapi/support-learning-required.yaml`은 협의용 계약이며 현재 learning 구현 명세와 구분한다.

- GET `/internal/support/targets/{targetType}/{targetId}`: JUDGMENT/FOLLOWUP/ATTEMPT → `{studentId,attemptId,judgmentId?,previousResult?}`. 내부 토큰 + 사용자 scope 검사, 관리자 SERVICE_OPS 컨텍스트는 core 검증 후 전달. 범위 밖 403, 대상 없음 404, 미구현/장애는 core `SUPPORT_DEPENDENCY_UNAVAILABLE` (503).
- GET `/internal/support/attempts/{attemptId}`: `{studentId,attemptId,answers:[{answerId,version,text,feedback}]}`. core가 저장된 연결 ID로만 호출, 공급자도 전달한 단일 학생 scope·ADMIN 역할·core 내부 토큰 검사(SERVICE_OPS는 core에서 검증). draft/memo/이름 제외.
- POST `/internal/judgments/{judgmentId}/corrections`는 **#80**의 공급자 구현 범위다. `{reportId,reason,corrected}`와 core에 영속 저장한 correction UUID를 `Idempotency-Key`로 전달하는 현재 흐름을 유지한다. 원판정·원본 답변을 보존하고 정정 이력을 추가한다. 조회에는 최신 정정을 적용하되 기존 되묻기와 `nextActions`는 유지한다.
- 정정 인증은 내부 토큰·`ADMIN`·대상 학생 **정확히 1명**의 `X-Student-Scope`·UUID `X-User-Id`가 필수다. SERVICE_OPS 검사는 core가 소유한다. 잘못된 내부 토큰은 401, 역할/학생 범위 위반은 403, 필수 사용자 ID 누락/형식 오류는 400이다.
- 정정 대상의 처리 상태가 `DONE` 이전이면 409. 동일 `reportId`에 다른 `Idempotency-Key`를 사용하면 409. 같은 키·같은 본문은 `correctionId`·이전 결과·정정 결과·시각·impact를 포함한 **최초 응답 전체**를 재현하고, 같은 키·다른 본문은 422다. 응답 유실·core 저장 실패 후에도 같은 영속 키로 재개한다.
- 정정 응답은 `{correctionId,previousResult,corrected,createdAt,impact:{conversation,aggregation,report}}`다. `impact.aggregation`은 **학습 수치 집계**에 대한 정정 반영 여부이며 개별 기록 상세의 판정 표시와 구분한다.
- impact의 `APPLIED`는 해당 영역에 정정 반영을 확인함, `NOT_APPLIED`는 해당 영역에 정정 반영을 수행하지 않았음을 확인함, `UNKNOWN`은 반영 여부를 확인하지 못함이다. 집계가 판정 결과를 사용하지 않아 변경 대상이 없는 경우도 `aggregation: NOT_APPLIED`이며 오류나 후속 처리 필요를 뜻하지 않는다. learning은 `conversation`·`report`에 UNKNOWN을 반환할 수 있다.
- **모든 impact가 UNKNOWN이어도 판정 정정 성공과 신고 RESOLVED 전이가 가능**하다. core는 공급자가 확인한 정정 성공을 기준으로 완료 처리하고 impact는 그대로 보존한다. 관리자 화면은 이를 대화·집계·리포트까지 모두 반영됐다는 의미로 표시하지 않는다.
- `/support/targets/...`(신고 대상 확인·최초 정정 전 조회)와 `/support/attempts/...`(관리자 원문 조회)는 **#80 범위 밖의 별도 공급자 이슈**다. #80만으로 실제 정정 E2E가 완료되지는 않는다.

#### #46 관리자 정정 공개 오류 계약

기존 구현은 공급자의 모든 비-2xx를 `503 SUPPORT_DEPENDENCY_UNAVAILABLE`로 변환했다. 정정 POST에 한해 다음처럼 구분한다. 공급자 오류 본문·내부 상세·임의 code는 공개 응답에 전달하지 않는다.

| learning 응답/실패 | 관리자 `POST /admin/error-reports/{id}/corrections` 응답 | 상태 처리 |
|---|---|---|
| 409 (DONE 이전·reportId/키 충돌) | **409 SUPPORT_CORRECTION_CONFLICT** | 정정 FAILED, 신고 IN_REVIEW 유지, 완료 알림 없음 |
| 422 (같은 키·다른 본문) | **422 SUPPORT_CORRECTION_REJECTED** | 정정 FAILED, 신고 IN_REVIEW 유지, 완료 알림 없음 |
| 그 외 비-2xx (조회 API의 409·422도 포함) | **503 SUPPORT_DEPENDENCY_UNAVAILABLE** | 완료로 표시하지 않음 |
| 2xx의 잘못된 JSON·필수 필드·impact 코드 | **502 SUPPORT_INVALID_RESPONSE** | 완료로 표시하지 않음 |
| 전송/시간 초과/서킷 차단 | 기존 LEARNING_UNAVAILABLE(503) / LEARNING_TIMEOUT(504) / LEARNING_CIRCUIT_OPEN(503) | 완료로 표시하지 않음 |

core 자체의 권한·상태·본문 충돌 오류는 기존 계약을 유지한다. 이 표는 공급자 HTTP 응답 변환에 대한 계약이며 learning 공급자 구현 완료를 의미하지 않는다.

#46 신고 POST의 최초 접수 응답은 RECEIVED·검토 결과 없음·정정 이력 없음으로 고정한다. 공통 멱등 응답 저장 실패 후 재구성해도 이미 진행된 관리자 처리 결과를 최초 접수 응답에 섞지 않는다. 생성 시각은 PostgreSQL과 같은 UTC 마이크로초 정밀도를 사용한다. 최신 learning #27의 기록 상세는 ADMIN을 허용하지 않으므로 이를 보호자/SYSTEM으로 위장 호출하지 않는다.

### 이슈 #41 분석 대화 구현 계약

대화·SSE·범위 확인·payment 소비 port·Redis 차감 정책은 [#41 계약](../report/issue-41-analysis-conversations.md)을 따른다. 내부 history는 `{role:USER|ASSISTANT,text}`이며 core messageId를 요청에 추가한다. 같은 대화의 자녀는 고정하며 자녀 변경은 새 대화로 확인한다. 기간 명시는 사용자 확인이고 동일 기간 완료 이력만 AI에 전달한다.

#41 보완(P08): 시작일 이전 답변은 현재 기간의 집계 대상 시도에 포함되는 경우에만 비교 근거로 허용하며 종료일 이후 답변은 거부한다. AI가 contentAllowed를 보내면 false인 결과는 확정하지 않는다.

### 5.8 리포트 현재 이용권 연결 (#129)

- 생성은 기존 `ReportJobService → ReportEntitlementService → ProductEntitlementService`를 사용한다. 상품·구독 판정값을 job과 같은 트랜잭션의 `report.generate.narrativeEnabled`에 기록한다. 무료 상품 누락·잘못된 상품 설정·결제 확정 중 오류를 무료 권한으로 대체하지 않는다. 데모 계정 우회 정책은 없다.
- 상세·다운로드는 연결 자녀와 동의를 검사한 후 현재 이용권을 조회한다. `ReportQueryService → ReportClient`가 검증된 boolean으로 `X-Report-Narrative-Enabled`를 직접 설정한다. 공개 입력 헤더를 복사하지 않는다. 목록·근거 조회에는 추가 이용권 판정을 요구하지 않는다.
- 상세는 HTTP 호출 전에 선택한 범위를 유지한다. HTTP 뒤 기존 parent 잠금 안에서 권한·연결을 다시 확인하고 열람을 기록한다. 요청 당시 또는 최종 판정이 무료이면 `narrative`·`eveningQuestion`을 null로, `thinkingTypes[].summary`를 제거한다. 호출 중 유료로 바뀌어도 이미 받은 무료 응답을 전체 응답으로 간주하거나 프리미엄 사용으로 기록하지 않는다.
- 다운로드는 상세 메타데이터와 파일 요청에 같은 판정값을 사용한다. 메타데이터가 식별한 불변 reportId를 파일 경로에 사용한다. 무료는 free, 유료는 full을 요청하며 본문에서 서술 유무를 추측해 파일 권한을 결정하지 않는다. full 요청은 최종 parent 잠금 안에서도 유료여야 URL을 반환한다(상실 시 403 REPORT_PREMIUM_REQUIRED). free 요청 중 유료 전환이 생겨도 free URL만 반환하며 프리미엄 사용을 기록하지 않는다.
- `ReportViewService`는 요청 시 선택한 범위와 반환 직전 권한을 함께 사용해 프리미엄 사용을 기록한다. parent 잠금·환불 직렬화는 유지하고 외부 HTTP는 트랜잭션 밖이다. 최종 확인 이후 이미 발급된 서명 URL은 기존 TTL 동안 유효하며 이 변경은 발급된 URL의 즉시 회수 기능을 추가하지 않는다.
- 공개 API 경로·응답 필드·이벤트 스키마·DB는 유지한다. 실제 report 공급자의 무료 투영·free/full 파일 계약을 재사용한다.
