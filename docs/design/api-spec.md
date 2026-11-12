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
| 목록 | `page`(0부터), `size`(기본 20, 최대 100) → `{items, page, size, totalElements}`. 예외: 알림은 `totalElements` 대신 `hasNext`(2.7), 리포트·학생 기기 목록은 `{items}`만(5.5·3.11, 리포트는 core가 report 페이지를 끝까지 모아 전체 반환 #500), 자녀·동의 목록은 페이지 없이 전체를 `page: 0, size = items 수`로 반환(5.3) |
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
| `SERVICE_OPS` | 작업·큐 현황, 작업 재처리, 신고·문의·공지, 모델·프롬프트 버전, AI 사용량 (운영 현황 `/admin/overview`·감사 로그 조회는 권한 없이 ADMIN 역할만, 2.8.1) |
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
| `FORBIDDEN` | 403 | 역할·관리자 권한 부족, 지원 조회의 권한·학생 범위 거부 (5.7) |
| `CHILD_NOT_LINKED` | 403 | 연결되지 않은 자녀 요청 (FN-AGT-02, FN-RPT-12) |
| `REAUTH_REQUIRED` | 403 | 중요 정보 변경 전 재확인 필요 (FN-ACC-10). 문구는 로그인 수단과 무관하게 "해당 작업의 본인 재확인이 필요합니다." (#415) |
| `REAUTH_PASSWORD_INVALID` / `REAUTH_METHOD_MISMATCH` | 403 / 409 | 비밀번호 재확인에서 틀린 비밀번호(로그인 실패 횟수에 포함) / Google 계정이 비밀번호 재확인을 요청 (5.6, #415) |
| `STUDENT_DEVICE_INVALID` | 401 | 학생 기기 자격증명 없음·해제·만료, 해당 기기에 등록되지 않은 자녀 (FN-ACC-05) |
| `STUDENT_PIN_INVALID` | 401 | PIN 불일치, `remainingAttempts` 포함 (FN-ACC-05) |
| `STUDENT_PIN_LOCKED` | 423 | PIN 연속 5회 실패로 잠금, 학부모 PIN 재설정 필요 (FN-ACC-05) |
| `STUDENT_PIN_NOT_SET` | 409 | PIN 미설정 자녀의 PIN 로그인 → 학부모 동석 진입 안내 (FN-ACC-05) |
| `PARENT_SESSION_LOCKED` | 401 | 동석 학생 화면 사용 중 잠긴 학부모 세션의 refresh·access → 보호자 비밀번호로 복귀 안내. refresh 토큰은 소비하지 않음 (FN-ACC-05, 5.1) |
| `GUARDIAN_PASSWORD_INVALID` | 401 | 보호자 비밀번호 불일치, `remainingAttempts` 포함 (FN-ACC-05) |
| `GUARDIAN_PASSWORD_LOCKED` | 423 | 보호자 비밀번호 연속 5회 실패로 잠금 → Google 로그인, 비밀번호 재설정 시 해제 (FN-ACC-05) |
| `GUARDIAN_PASSWORD_NOT_SET` | 409 | 보호자 비밀번호 미설정 → Google 로그인 안내 (FN-ACC-05) |
| `PAIRING_CODE_INVALID` | 400 | 페어링 코드 없음·만료·이미 사용 (FN-ACC-14) |
| `NOT_FOUND` | 404 | 리소스 없음 |
| `DATA_UNAVAILABLE` | 410 / 503 | 삭제된 근거 → "이용 불가" 표시(410), report 원문 조회·파일 저장소 장애는 재시도 가능한 503 |
| `TRANSFER_PENDING` | 409 | 해당 자녀의 이관 대기 요청이 있어 다른 이관·연결 해제·삭제 불가, 발신자는 탈퇴 불가 (5.17) |
| `TRANSFER_ALREADY_RESOLVED` | 409 | 이미 종료된 이관 요청에 다른 상태 전이 시도 (5.17) |
| `TRANSFER_CHILD_UNAVAILABLE` | 409 | 삭제 요청 중이거나 비활성인 자녀의 이관 요청·수락 (5.17) |
| `TRANSFER_RECIPIENT_NOT_FOUND` | 404 | 가입 이메일에 맞는 활성 학부모가 없거나 후보를 하나로 특정할 수 없음 (5.17) |
| `TRANSFER_ACTIVITY_IN_PROGRESS` | 409 | 해당 자녀의 발신자 상담·관리자 재처리가 진행 중이어서 수락 불가 (5.17) |
| `TRANSFER_PAYMENT_BLOCKED` | 409 | 해당 자녀의 구독·진행 중 결제·미처리 환불로 이관 요청·수락 불가 (5.17) |
| `DELETION_IN_PROGRESS` | 409 | report 학생 삭제가 진행 중이므로 리포트 조회를 잠시 차단(core가 같은 코드로 전달), core 자녀 삭제 요청이 이미 진행 중 (5.6) |
| `VALIDATION_FAILED` | 400 / 422 | 형식 오류 (`errors[]`에 필드별 사유). 형식은 맞지만 업무 규칙에 어긋난 PIN(3.11)·꾸미기 선택값(3.12)은 422 |
| `ANSWER_INCOMPLETE` | 422 | 필요한 선택·입력 누락 (FN-LRN-04) |
| `ANSWER_INAPPROPRIATE` | 422 | 학생이 쓴 답변(최초·보완)에 욕설·비속어·성적·혐오·위협 표현이나 연락처(전화번호·이메일) → 저장·판정 요청 없이 차단. `detail`은 범주별 고정 안내 문구, 걸린 단어·원문은 응답에 넣지 않음 (#205) |
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
| `USAGE_LIMIT_REACHED` | 429 | 요금제 사용 한도 도달(무료: 분석 대화 없음, 무료 상품에서 추가 문제를 다시 켠 경우의 무료 `EXTRA` 하루 `limits.dailyMissions`개. 2026-11-10 개정 #483·core #485 뒤 무료 테마 문제는 하루 한도 없이 주 5개(learning 공개 규칙), 무료 추가 문제는 403 `PREMIUM_REQUIRED`. 프리미엄: 하루 피드백 50회·분석 대화 30회). 추억 검색·설명 하루 한도(`limits.dailyMemorySearches`·`dailyMemoryExplanations`, 2026-11-12 확정 20·10, 2.12, core #566)도 같은 코드이며 `detail`에 하루 횟수와 "내일 0시(KST)에 초기화"를 넣는다(새 칸 없음). 가능 범위·사유·초기화 시점 포함 (FN-ADM-19, P13, P27) |
| `AI_UNAVAILABLE` | 503 / 502 | AI 처리 실패, `retryable` 포함 (처리 실패 상태, 보류와 구분). ai·learning 피드백은 503, core 분석 대화의 ai 연결 실패·서킷 차단·스트림 중단은 502 (#167) |
| `SESSION_CHANGED` | 401 | 다른 탭에서 역할·세션이 바뀌어 access의 세션 version 불일치 (5.1) |
| `REFRESH_REUSED` | 401 | 이미 사용된 refresh 재사용 → 해당 세션 전체 폐기 (5.1) |
| `OAUTH_FAILED` / `OAUTH_UNAVAILABLE` | 401 / 503 | Google 인증 실패 / Google 로그인 미설정·연결 실패. 콜백 실패는 `/login?oauthError=<code>`로 이동 (5.1) |
| `ACCOUNT_EXISTS` | 409 | 같은 이메일의 기존 계정은 자동 연결하지 않음 (5.1) |
| `INVALID_CREDENTIALS` / `ADMIN_LOGIN_LOCKED` | 401 / 423 | 관리자·학부모 ID·비밀번호 로그인 실패(없는 ID·틀린 비밀번호·Google 계정·다른 역할·비활성 계정 구분 없음) / 관리자 연속 5회 실패 후 15분 잠금 (5.1, #369·#415) |
| `LOGIN_LOCKED` | 423 | 학부모 ID·비밀번호 로그인 또는 비밀번호 재확인 연속 5회 실패 후 15분 잠금(두 경로의 실패 횟수를 함께 셈) (5.1·5.6, #415) |
| `LOGIN_ID_TAKEN` | 409 | 학부모 ID·비밀번호 가입에서 이미 쓰는 아이디(대소문자 무관) (5.1, #415) |
| `SIGNUP_RATE_LIMITED` / `SIGNUP_UNAVAILABLE` | 429 / 503 | 같은 IP의 학부모 ID·비밀번호 가입 한도(기본 10분 5회) 초과 / 가입 한도 저장소(Redis) 장애 (5.1, #415) |
| `AUTH_UNAVAILABLE` | 503 | 인증 상태 확인 실패(DB 장애 등) |
| `CONSENT_REQUIRED` | 403 | 필수 계정 동의 또는 GUARDIAN 동의 전 접근 (5.3) |
| `CONSENT_DOCUMENT_CHANGED` / `CONSENT_DOCUMENTS_UNAVAILABLE` | 409 / 503 | 제출한 동의 문서 버전이 현재와 다름 / 게시된 동의 문서 확인 실패 (5.3) |
| `IDEMPOTENCY_IN_PROGRESS` / `IDEMPOTENCY_UNAVAILABLE` | 409 / 503 | 같은 키 처리 중(`Retry-After: 1`) / 멱등 기록 저장소 장애 (1.4) |
| `LEARNING_UNAVAILABLE` / `LEARNING_TIMEOUT` / `LEARNING_CIRCUIT_OPEN` | 503 / 504 / 503 | core→learning 호출 실패 / 시간 초과 / 서킷 차단 (1.4) |
| `LEARNING_CONTRACT_INVALID` | 502 | 대시보드 공급자의 JSON·학생 식별자·필수 조회 봉투 계약 위반. 기록 없음으로 대체하지 않음 (#40, 2.3) |
| `MODEL_VERSION_CONFLICT` / `MODEL_APPROVAL_REJECTED` / `MODEL_VERSION_STATE_INVALID` | 409 / 422 / 503 | 허용되지 않는 전이·복귀 이력 없음 / 승인 근거·범위 부족 / 기존 ACTIVE 상태 불완전 (5.2) |
| `LEARNING_INVALID_RESPONSE` | 502 | 피드백 SSE에서 learning 응답 형식 오류 (3.2) |
| `SUPPORT_CORRECTION_CONFLICT` / `SUPPORT_CORRECTION_REJECTED` | 409 / 422 | learning 정정 POST의 업무 충돌 / 요청 거부. 공급자 본문은 공개하지 않음 (5.7) |
| `SUPPORT_DEPENDENCY_UNAVAILABLE` / `SUPPORT_INVALID_RESPONSE` | 503 / 502 | 지원 GET의 검증된 403·404를 제외한 비-2xx / 잘못된 2xx 성공 응답 (5.7) |
| `REPORT_NOT_FOUND` / `REPORT_SCOPE_REJECTED` | 404 / 403 | 없는 리포트 / report-api가 학생 범위를 거부 (5.5) |
| `PAYMENT_ENTITLEMENT_CONFIRMING` / `PAYMENT_PRODUCT_UNAVAILABLE` / `PAYMENT_FREE_PRODUCT_UNAVAILABLE` | 503 | 상품 권한 확인 불가(결제 확정 중·상품 정보 누락·무료 상품 미설정). 리포트 생성은 작업·Outbox를 만들지 않음 (5.5, #48) |
| `REPORT_UNAVAILABLE` / `REPORT_CONTRACT_INVALID` | 503 / 502 | report-api 연결 실패·그 밖의 오류 응답 / 응답 JSON·식별·기간 계약 위반 (5.5) |
| `JOB_NOT_FOUND` / `JOB_ID_AMBIGUOUS` | 404 / 409 | 관리자 작업 조회·재처리 대상 없음 / UUID가 작업 종류 간 중복 (2.8) |
| `JOB_NOT_FAILED` / `JOB_RETRY_IN_PROGRESS` / `REPORT_ALREADY_RETRIED` / `REPORT_RETRY_STUDENT_UNAVAILABLE` | 409 | FAILED가 아닌 작업 재처리 / 알림 재처리 선점 실패 / 이미 새 작업으로 재처리된 리포트 / 삭제 요청·비활성 학생 (2.8) |
| `JOB_RETRY_UNAVAILABLE` / `JOB_RETRY_OUTCOME_UNKNOWN` | 503 | 재처리를 지원하지 않는 작업 종류 / 알림 재처리 후 결과 상태 미확정 (2.8) |
| `RATE_LIMITED` / `STUDENT_AUTH_UNAVAILABLE` | 429 / 503 | 기기 등록·페어링 발급 10분 한도 초과 / 기기·페어링 저장소(Redis) 장애 (3.11) |
| `REAUTH_PENDING` | 409 | Google 재인증 callback 전에 재인증 토큰 수령 시도 (5.6) |
| `STUDENT_RECORDS_PRIVATE` / `STUDENT_UNAVAILABLE` / `STUDENT_DELETED` | 403 / 409 / 409 | 학생이 학부모 공개를 끈 기록·비교 조회(#206) / 학생 삭제 진행·비활성(꾸미기·공개 설정·리포트 설정 내부 조회) / 삭제 차단된 학생의 리포트 생성(관리자 재처리) |
| `INVALID_TEMPLATE_SETTINGS` / `TEMPLATE_PROPOSAL_EXPIRED` | 400 / 409 | 리포트 표시 설정 값 오류 / 다른 대화·만료·덮어쓴 변경안 확정, 설정 revision 변경 (#209) |
| `ANALYSIS_IN_PROGRESS` / `EVIDENCE_UNAVAILABLE` / `AI_INVALID_RESPONSE` | 409 / 410 / 502 | 같은 대화에서 분석 생성 중 / 삭제된 분석 근거 / ai 응답 형식 오류 (2.4) |
| `ANALYSIS_FIRST_RESPONSE_TIMEOUT` / `ANALYSIS_TIMEOUT` / `ANALYSIS_FAILED` | 504 / 504 / 502 | 분석 대화 SSE `error` 이벤트 전용: ai 첫 이벤트 20초 안에 없음 / 전체 120초 초과 / 원인 코드가 없는 처리 실패(원래 오류 상태가 있으면 그 상태). `retryable: true`, 메시지는 FAILED로 저장 (3.3) |
| `REPORT_PREMIUM_REQUIRED` / `REPORT_JOB_IDENTITY_MISMATCH` | 403 / 409 | 무료 이용권에서 프리미엄 리포트 항목 요청 / report 복구 응답의 작업 식별자 불일치 (5.9) |
| `COMMUNITY_CONSENT_REQUIRED` / `COMMUNITY_LOCKED` / `COMMUNITY_OWN_POST` / `COMMUNITY_POST_NOT_FOUND` | 409 / 403 / 409 / 404 | 보호자 `COMMUNITY` 동의 없이 공개 켜기 / 미션 미마무리 학생의 커뮤니티 열람·반응(learning 판정 전달). 2026-11-10 개정 #483 뒤 큰 질문 정답 고르기 문제를 마무리했지만 그 주 엔딩 전인 학생은 `403 COMMUNITY_LOCKED_UNTIL_ENDING`("이번 주 테마 엔딩을 보면 친구들 생각을 볼 수 있어요.", learning #484 코드, core 공개 문구 #550) / 본인 공유물 반응·신고 / 숨김·파기·없는 공유물 반응·신고 (2.9, #388) |
| `COMMUNITY_NOT_SHAREABLE` | 409 | learning 내부 공유 요청 거절: 학습 완료 전·다시 푼 시도·답변 없음·지금 표현 필터(#205)에 걸림. core는 공유 안 함으로 보고 학생 응답에 내보내지 않음 (4.1, #386) |
| `COMMUNITY_UNAVAILABLE` / `COMMUNITY_INVALID_RESPONSE` | 503 / 502 | learning 커뮤니티 내부 호출이 공개 오류 코드 외의 실패로 응답 / 잘못된 2xx 성공 응답 (2.9) |
| `INSUFFICIENT_POINTS` / `LOOK_ITEM_NOT_ON_SALE` / `LOOK_LOCKED` | 409 | 해금 포인트 부족 / 판매 중단 아이템 해금 / 해금하지 않은 테마·캐릭터·아이템 선택 (2.10, 3.12, #389) |
| `LOOK_ITEM_NOT_FOUND` / `LOOK_ITEM_CODE_DUPLICATE` | 404 / 409 | 없는 꾸미기 항목 해금 / 관리자 아이템 코드 중복 (2.8, 2.10, #389) |
| `THEME_DAY_CLOSED` / `THEME_REVIEW_NOT_ALLOWED` / `PREMIUM_REQUIRED` | 409 / 409 / 403 | 오늘 요일이 아닌 테마 문제 신규 시도 / 토·일 외 또는 마무리하지 않은 테마 문제 다시 풀기·평일 되돌아보기 열람(두 코드는 learning #385, core는 그대로 전달) / 추가 문제(`EXTRA`)를 끈 상품(`features.extraMissions = false`)의 시도(core #387. V43부터 무료 상품은 `false`, 값이 없으면 무료 거부·구독 중 허용 #506) (2.11). 2026-11-10 개정(#483, learning #484·core #485) 뒤 뜻: `THEME_DAY_CLOSED`는 공개 전(`LOCKED`) 문제·일요일(허용 값 없는 무료) 신규 시도, `THEME_REVIEW_NOT_ALLOWED`는 토요일(프리미엄 일요일) 외 다시 풀기·열람 또는 마무리하지 않은 문제 다시 풀기, `PREMIUM_REQUIRED`는 무료 상품 `features.extraMissions = false`로 무료의 추가 문제 시도(일요일 전용 코드는 새로 만들지 않음, #484 확정). 그 주 이미 마무리한 문제의 새 `THEME_DAY` 시도도 `THEME_DAY_CLOSED`(#506·#484) |
| `THEME_STORY_NOT_ALLOWED` | 409 | 시작 이야기(INTRO)를 무료 일요일에, 종료 이야기(OUTRO)를 엔딩 상태가 아닐 때·무료 일요일에 열람 기록(learning #438·#484, core는 그대로 전달 #439) (2.11) |
| `THEME_PICK_NOT_ALLOWED` | 409 | 큰 질문 정답을 지금 고를 수 없음(큰 질문 없는 테마·금요일 문제 마무리 전·그 주 이미 고름·무료 일요일. learning #484 판정, core는 그대로 전달 #550) (2.11) |
| `CONVERSATION_REPORT_INVALID` / `WEEKLY_THEME_PUBLISH_INCOMPLETE` | 422 | 이 자녀의 완료된 일일 리포트가 아닌 리포트로 대화 생성 (2.4, #392) / 테마 게시 검사 실패 + `errors:[{code, message}]`(learning #385, core는 그대로 전달 #387) (2.8) |
| `SUPPORT_STATE_CONFLICT` / `CORRECTION_TARGET_UNSUPPORTED` | 409 / 422 | 신고·문의 처리 상태 전이 위반·완료 답변 변경 / 정정할 수 없는 신고 대상 (5.7) |
| `CORRECTION_REPORT_CONFLICT` / `JUDGMENT_STATE_CONFLICT` | 409 | learning: 같은 신고로 이미 정정함 / 판정 처리 상태 충돌 (5.7) |
| `MISSION_VERSION_CONFLICT` / `CONFLICT` | 409 | learning 미션 버전 충돌 / 현재 미션 상태에서 허용되지 않는 전이 (2.8 #47 미션 운영) |
| `ADMIN_MISSIONS_UNAVAILABLE` / `MISSION_AUDIT_UNAVAILABLE` / `LEARNING_STATS_UNAVAILABLE` / `LEARNING_REQUEST_FAILED` | 503 / 503 / 503 / learning 상태 | core 관리자 미션·감사·통계 조회의 learning 실패 / 허용 목록 밖 learning 오류 코드 대체 (2.8) |
| `QUEUE_MANAGEMENT_NOT_CONFIGURED` / `QUEUE_MANAGEMENT_UNAVAILABLE` / `QUEUE_MANAGEMENT_TIMEOUT` / `QUEUE_MANAGEMENT_INVALID_RESPONSE` / `QUEUE_MANAGEMENT_INCOMPLETE` | 503 / 503 / 504 / 503 / 503 | 관리자 큐 조회: RabbitMQ 관리 API 미설정 / 연결 실패 / 5초 초과 / 응답 형식 오류 / 정의된 큐 누락 (2.8) |
| `AI_PROMPT_VERSION_UNAVAILABLE` / `SCORING_UNAVAILABLE` | 503 | ai 활성 프롬프트 본문 없음 / scoring 모델 미준비 (내부 API, 4.2·4.3) |
| `MODEL_PREFLIGHT_UNAVAILABLE` / `MODEL_PREFLIGHT_INVALID_RESPONSE` | 503 / 502 | 모델 파일 사전 검사 중 scoring 연결 실패·제한 시간 초과 / scoring 응답 오류·형식 위반 (5.2.1) |
| `PAYMENT_ENTITLEMENT_UNAVAILABLE` / `PAYMENT_USAGE_UNAVAILABLE` / `REFUND_IN_PROGRESS` | 503 / 503 / 409 | 분석·피드백 이용권 확인 실패 / learning→core 사용 증빙 실패 / 환불 진행 중 프리미엄 사용. learning 피드백은 core `/internal/payment-usage/*` 409의 `code` 중 `REFUND_IN_PROGRESS`·`PAYMENT_USAGE_RETRY_REQUIRES_NEW_SOURCE`·`PAYMENT_USAGE_STATE_CHANGED`만 같은 코드 409로 전달하고, 그 밖의 코드·형식 오류 409는 환불로 안내하지 않고 `PAYMENT_USAGE_UNAVAILABLE` 503 (#276) |
| `PAYMENT_NOT_FOUND` / `BILLING_KEY_REQUIRED` / `INVALID_PAGE` / `INVALID_DATE_RANGE` / `PAYMENT_RECONCILIATION_RANGE_REQUIRED` | 404 / 409 / 409 / 409 / 409 | 결제 없음 / 빌링키 등록 전 자동 갱신 켜기 / 페이지 범위 오류 / 조회 기간 오류 / 대사 조회 기간 누락 (2.6) |
| `SUBSCRIPTION_NOT_ACTIVE` / `SUBSCRIPTION_STATE_CHANGED` / `PRODUCT_NOT_PURCHASABLE` / `PRODUCT_TERMS_INVALID` / `PRODUCT_FEATURE_DISABLED` | 409 | 활성 구독 아님 / 처리 중 구독 상태 변경 / 월 단위·자녀 1명 유료 상품이 아님 / 상품 한도 설정 형식 오류 / 현재 이용권에 없는 기능 (2.6) |
| `PAYMENT_KEY_MISMATCH` / `PAYMENT_ORDER_KIND_MISMATCH` / `PAYMENT_USAGE_STATE_CHANGED` / `PAYMENT_USAGE_RETRY_REQUIRES_NEW_SOURCE` | 409 | 이미 승인된 주문에 다른 paymentKey / 최초 결제가 아닌 주문 승인 / 사용 증빙 상태 변경 / 실패한 사용 증빙은 새 요청으로 재시도 (2.6·4.5) |
| `REFUND_NOT_READY` / `REFUND_STATE_CHANGED` / `REFUND_PREMIUM_USAGE_PRESENT` | 409 | 사용 이력 확인 전 또는 REQUESTED가 아닌 환불 승인 / 처리 중 환불 상태 변경 / 프리미엄 기능 사용 이력 있음 (P14) |
| `PAYMENT_PG_UNAVAILABLE` / `PAYMENT_PG_MISMATCH` / `PAYMENT_PG_KEY_UNAVAILABLE` / `PAYMENT_KEY_UNAVAILABLE` / `PAYMENT_CUSTOMER_UNAVAILABLE` | 503 | 토스 설정·연결 실패 / 토스 응답과 주문·금액·MID·상태 불일치 / 토스 키 미설정 / 빌링키 암호화 키 미설정 / 구독의 고객 키 없음 (2.6) |
| `PAYMENT_STORAGE_UNAVAILABLE` / `PAYMENT_WEBHOOK_UNAVAILABLE` / `PAYMENT_WEBHOOK_LOOKUP_UNAVAILABLE` / `PAYMENT_RECONCILIATION_UNAVAILABLE` / `PAYMENT_RENEWAL_DATA_UNAVAILABLE` / `REFUND_USAGE_UNAVAILABLE` | 503 | 결제 저장소 장애 / 웹훅 처리 실패 / 웹훅 결제 조회 실패 / 대사 조회 실패 / 갱신 데이터 확인 실패 / 환불 전 사용 이력 확인 실패 (2.6) |
| `THEME_FRAME_NOT_FOUND` | 404 | 보유하지 않은 기념 액자 회차의 앨범 상세·확인 처리·추억의 벽 걸기 (2.12 설계, P27) |
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
- core는 답변의 `Idempotency-Key`를 learning에 그대로 전달한다. learning은 `(attempt_id, idempotency_key)` UK와 답변·PENDING 판정의 동일 트랜잭션으로 최초 응답을 재구성하고, 키 중복 시 본문 불일치를 422로 거부해야 한다. core 저장 실패·만료·연결 장애 후 재요청도 이 계약으로 중복 반영을 막는다.
- 초안은 `ETag`/`If-Match`(초안 버전)로 처리. 불일치 시 409를 반환하고 조용히 덮어쓰지 않음
- 학생 `GET /attempts/{attemptId}`는 `Cache-Control: no-store`로 반환한다. 이 응답의 ETag는 초안 동시성용이며 피드백·마무리·돌아보기 변경을 나타내는 전체 표현 버전이 아니다. 웹의 상세 조회와 답변 제출·마무리·돌아보기 후 재조회는 `cache: 'no-store'`로 기존 HTTP 캐시도 사용하지 않는다. 초안 ETag/If-Match와 409 계약은 유지한다.
- 피드백 요청은 키 대신 answerId의 판정 처리 상태로 중복 방지 (실패 후 재시도가 같은 요청이므로 키 재사용 불가)
  - `DONE`: 저장된 결과 반환
  - `RUNNING`: 새로 실행하지 않고 `status` 이벤트 후 종료, 클라이언트가 잠시 후 재요청. 그사이 다른 요청의 처리가 실패(`FAILED`)한 경우도 처리 중으로 응답하고, 다시 요청하면 실행
  - `PENDING`·`FAILED`·리스 만료된 `RUNNING`(처리 Pod 종료로 고착): 조건부 상태 전이 후 실행 (리스 90초, P12)

### 1.5 상태 코드값 (FN 1.2 대응)
| 대상 | 값 |
|---|---|
| 미션 수행 | `NOT_STARTED` 시작 전 · `IN_PROGRESS` 진행 중 · `COMPLETED` 완료 |
| 미션 운영 | `DRAFT` 작성 중 · `REVIEW_REQUIRED` 검토 필요 · `PUBLISHED` 공개 · `UNPUBLISHED` 비공개 |
| 미션 생성 방식 (#353) | `MANUAL` 사람 작성 · `LLM_DRAFT` LLM 초안 채택 |
| 미션 초안 (#353) | `GENERATING` 생성 중 · `READY` 검사 통과 · `CHECK_FAILED` 검사 실패(상한) · `FAILED` 생성 실패(AI 호출) · `ADOPTED` 채택 · `DISCARDED` 버림 |
| 주간 테마 운영 (#385) | `DRAFT` 작성 중 · `REVIEW_REQUIRED` 검토 필요 · `PUBLISHED` 게시 · `UNPUBLISHED` 게시 중단 |
| 테마 요일 문제 (#385, #483 개정) | `LOCKED` 잠김 · `OPEN` 열림 · `CLOSED` 닫힘 (저장하지 않고 KST 날짜로 계산). 개정 뒤: 그 요일 00:00 공개 후 토요일까지 `OPEN`, 일요일 `CLOSED`(프리미엄 일요일은 `OPEN`) |
| 주간 테마 엔딩 (#483, learning #484) | `NOT_ENDED` 엔딩 전 · `ENDED` 엔딩 (큰 질문 정답 즉시, 오답이면 고른 뒤 토요일(프리미엄 일요일) 금요일 문제 다시 풀기 마무리 뒤, state-diagram 3.2.2) |
| 커뮤니티 공유물 (#386) | `VISIBLE` 공개 · `HIDDEN_SETTING` 설정 비공개 · `HIDDEN_REPORT` 신고 숨김 · `REMOVED` 운영 숨김 |
| 꾸미기 아이템 (#389) | `ON_SALE` 판매 중 · `STOPPED` 판매 중단 |
| 초안 저장 | `SAVED` (저장 중·저장 실패는 클라이언트 상태) |
| 판정 처리 | `PENDING` · `RUNNING` · `DONE` · `FAILED` |
| 판정 결과 | `CORRECT` 정답 · `PARTIAL` 부분 정답 · `RETHINK` 다시 생각 · `HELD` 판정 보류 (처리 실패는 처리 상태 `FAILED`) |
| 되묻기 유형 | `ONE_STEP_MORE` 한 걸음 더 · `TELL_MORE` 더 말해 보기 · `LOOK_AGAIN` 다시 살펴보기 |
| 돌아보기 난이도 | `EASY` 쉬웠어 · `NORMAL` 보통 · `HARD` 어려웠어 (ERD `reflection.difficulty`) |
| 자녀 이관 | `PENDING` 수락 대기 · `ACCEPTED` 수락 완료 · `REJECTED` 수신자 거절 · `CANCELLED` 발신자 취소 |
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
{ "kind": "ANSWER", "attemptId": "...", "missionTitle": "...", "answerId": "...", "answerVersion": 1,
  "submittedAt": "...", "quote": "아이 원문 일부", "available": true }   // 삭제 시 available=false
// kind: ANSWER(답변) | REFLECTION(돌아보기). 돌아보기는 시도당 하나라 attemptId로 식별하고
// answerId·answerVersion은 null, submittedAt은 돌아보기 작성 시각(reflection.createdAt)

// Versions: 결과에 연결된 버전 (NFR-DAT-02)
// model: M2 활성 판정은 M2 버전, M2 미활성 판정·되묻기는 LLM 모델 ID(예: gpt-6.1-terra), 규칙 판정은 null
{ "mission": "m-12@3", "rubric": "r-12@2", "model": "m2-klue-narrative@1.0", "prompt": "judge@2" }
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
| POST | `/auth/admin/login` | 공개 | 등록된 관리자 ID·비밀번호 로그인 `{loginId,password}` → refresh 응답과 같은 형식 + refresh 쿠키. 가입 없음, `admin_credential` 행으로만 등록 (#369, 5.1) | ACC-03, ADM-01 | 핵심 |
| POST | `/auth/parent/signup` | 공개 | 학부모 ID·비밀번호 가입 `{loginId,password,name}` → refresh 응답과 같은 형식(`nextAction: CONSENT_REQUIRED`, `startPath: /parent/onboarding`) + refresh 쿠키. 같은 IP 가입 한도 (#415, 5.1) | ACC-01 | 핵심 |
| POST | `/auth/parent/login` | 공개 | 학부모 ID·비밀번호 로그인 `{loginId,password}` → refresh 응답과 같은 형식 + refresh 쿠키. 5회 실패 15분 잠금 (#415, 5.1) | ACC-03 | 핵심 |
| POST | `/auth/refresh` | 쿠키 | access token 재발급 | ACC-04 | 제안 |
| POST | `/auth/logout` | 인증 | refresh token 폐기 | ACC-04 | 제안 |
| POST | `/auth/student/logout` | 학생 Bearer | 해당 학생 세션만 폐기, 보호자 refresh·기기 쿠키 유지 | ACC-04, ACC-05 | 핵심 |
| POST | `/auth/student-sessions` | 학부모 | 학생 진입(동석): `{childId}` 연결 자녀 확인 후 별도 학생 세션(`STUDENT` 토큰) 발급, 학부모 세션은 잠금(refresh 쿠키 유지). 시연 링크·URL 식별값 진입 없음 (P01, 5.1) | ACC-05 | 제안 |
| POST | `/auth/parent-unlock` | 쿠키 | 학생 화면 → 학부모 화면 복귀: `{password}` 보호자 비밀번호 확인 후 잠긴 학부모 세션 해제, 그 세션에서 들어간 학생 세션 폐기, refresh 응답과 같은 형식 + 회전 쿠키 (5.1) | ACC-05 | 제안 |
| GET | `/me/guardian-password` | 학부모 | 보호자 비밀번호 상태 `{set, locked, updatedAt}`. 값·해시는 반환하지 않음 | ACC-05 | 제안 |
| PUT | `/me/guardian-password` | 학부모 | 보호자 비밀번호 설정·변경 `{password}` (`X-Reauth-Token`, 숫자 4~6자리·반복/연속 불가, PIN과 같은 규칙). 실패 횟수·잠금 해제. 학부모가 아니면 입력과 관계없이 403(규칙 검사 422보다 먼저, #310) | ACC-05, ACC-10 | 제안 |
| POST | `/auth/student/devices` | 공개 | 페어링 코드로 기기 등록 `{pairingCode, label}` → 기기 자격증명 쿠키 발급, 등록 자녀 프로필 반환 (P01, 3.11) | ACC-14 | 제안 |
| GET | `/auth/student/profiles` | 기기 쿠키 | 이 기기에 등록된 자녀 프로필 `{childId, nickname, pinSet, pinLocked}` (P01, `/children` 확장과 같은 필드명) | ACC-05 | 제안 |
| POST | `/auth/student/login` | 기기 쿠키 | 학생 진입(단독): `{childId, pin}` → 학생 세션(`STUDENT` 토큰) 발급. refresh 미발급 (P01, 3.11) | ACC-05 | 제안 |
| GET | `/me` | 인증 | 본인 정보·역할·관리자 권한·로그인 수단(`authMethod`, 비밀번호 학부모는 `loginId`) | ACC-09 | 우선1 |
| PATCH | `/me` | 인증 | 본인 정보 수정 | ACC-09 | 우선1 |
| POST | `/me/reauth` | 인증 | Google 재인증 시작 `{purpose, childId?, scope?}` → `{challengeId, authorizationUrl, expiresAt}`, callback 후 `{challengeId}`로 단기 `reauthToken` 수령 (5.6) | ACC-10 | 우선1 |
| POST | `/me/reauth/password` | 학부모 | 비밀번호 계정의 재확인 `{purpose, childId?, scope?, password}` → `{reauthToken, expiresAt}` 바로 발급. Google 계정은 409 (#415, 5.6) | ACC-10 | 우선1 |
| GET | `/auth/google/reauth/callback` | 공개(재인증 상태 쿠키) | Google 재인증 callback → 완료 안내 HTML(원래 탭에 challengeId 알림 후 창 닫기) (5.6) | ACC-10 | 우선1 |
| GET | `/me/consents` | 학부모 | 동의 이력(주체·문서 버전·시점·철회 상태) | ACC-02 | 제안 |
| POST | `/me/consents` | 학부모 | 현재 문서의 동의 항목 저장 `{consents:[{documentId,version,agreed}], childId?}`. 계정은 TERMS·PRIVACY, 자녀는 GUARDIAN | ACC-02 | 제안 |
| POST | `/me/consents/{consentId}/withdrawal` | 학부모 | 동의 철회. 필수 동의면 해당 자녀(또는 계정) 이용 차단 후 삭제·탈퇴 안내, 선택 동의면 해당 기능만 중단 (P09) | ACC-02 | 제안 |
| GET | `/children` | 학부모 | 연결 자녀 목록(닉네임·학년·기록 유무, 5.3). PIN 상태 `pinSet`·`pinLocked`는 실제 저장 상태로 반환. 빈 목록이면 자녀 등록 안내 | ACC-07, ACC-14 | 제안 |
| POST | `/children` | 학부모 | 자녀 프로필 등록 `{nickname, grade(3~6), birthYear}` + 법정대리인 동의(전원 만 14세 미만 간주). 3명 초과 시 409 (P01, P02, P03) | ACC-06, ACC-02 | 제안 |
| PATCH | `/children/{childId}` | 학부모 | 닉네임·학년(3~9, 7~9는 중1~3) 수정 (학년은 이후 제공 문제에만 적용, 학년이 바뀌면 `grade_changed_at` 기록해 그 해 자동 진급 판단에 씀, P26 #432) | ACC-09 | 우선1 |
| PUT | `/children/{childId}/pin` | 학부모 | PIN 설정·변경 `{pin}`. 활성 학부모 세션·현재 연결 자녀 권한 검사, 추가 재인증 없음. 숫자 4~6자리·반복/연속 거부(422), 잠금·실패 횟수 초기화·감사 | ACC-14 | 구현 |
| POST | `/student-devices/pairings` | 학부모 | 1회용 페어링 코드 발급 `{childIds[]}` → `{pairingCode, expiresAt}` (10분, QR은 클라이언트가 코드로 생성) (P01) | ACC-14 | 제안 |
| GET | `/student-devices` | 학부모 | 등록 기기 목록 `{deviceId, label, children[], createdAt, lastUsedAt, expiresAt}` | ACC-14 | 제안 |
| DELETE | `/student-devices/{deviceId}` | 학부모 | 기기 등록 해제 → 이후 해당 기기 PIN 로그인 거부 | ACC-14 | 제안 |
| GET | `/children/{childId}/deletion-impact` | 학부모 | 연결 해제·프로필 삭제·기록 삭제별 범위·영향 안내 | ACC-11 | 우선2 |
| DELETE | `/children/{childId}/link` | 학부모 | 연결 해제 (`X-Reauth-Token`). 이관 대기 중이면 409 `TRANSFER_PENDING` | ACC-11, ACC-10 | 우선2 |
| POST | `/children/{childId}/deletion-requests` | 학부모 | 프로필·학습 기록 삭제 요청 `{scope: PROFILE\|RECORDS}` (`X-Reauth-Token`). 같은 요청에서 확정하고 `student.deleted` 발행, 별도 확인 API 없음. 사전 안내는 `deletion-impact` (P09). 이관 대기 중이면 409 `TRANSFER_PENDING` | ACC-11, ACC-13 | 우선2 |
| GET | `/children/{childId}/deletion-requests/{requestId}` | 학부모 | 삭제 요청 처리 상태 (5.6) | ACC-11 | 우선2 |
| GET | `/me/withdrawal/precheck` | 인증 | 탈퇴 전 진행 중 구독·미처리 환불·보관 거래(5년) 안내 (P09, P14) | ACC-12 | 우선2 |
| POST | `/me/withdrawal` | 인증 | 탈퇴 요청 (`X-Reauth-Token`). 진행 중 구독·미처리 환불은 409 `WITHDRAWAL_BLOCKED`, 보낸 이관이 대기 중이면 409 `TRANSFER_PENDING`. 요청 즉시 처리·이후 로그인 불가 (P09) | ACC-12 | 우선2 |
| GET | `/me/withdrawal` | 인증 | 탈퇴 처리 상태 | ACC-12 | 우선2 |
| POST | `/guardian-transfers/recipient` | 학부모 | 가입 이메일로 받는 학부모 조회 `{email}`. 404 `TRANSFER_RECIPIENT_NOT_FOUND`, 3명 한도 409 `CHILD_LIMIT_REACHED` (5.17) | ACC-15 | 우선2 |
| GET | `/guardian-transfers` | 학부모 | 본인이 보낸·받은 요청 `{items}`. 자녀 없음·동의 누락·기능 비활성 상태에서도 조회 가능 (5.17) | ACC-15 | 우선2 |
| POST | `/guardian-transfers` | 학부모 | `{childId,recipientId,includeConversations}` + CHILD_TRANSFER 재인증으로 요청, 409 이관·결제·인원 충돌 (5.17) | ACC-15 | 우선2 |
| POST | `/guardian-transfers/{id}/accept` | 수신 학부모 | `{consents}` + TRANSFER_ACCEPT 재인증으로 수락. 현재 GUARDIAN 동의·결제·인원·진행 상태 재검사 (5.17) | ACC-15 | 우선2 |
| POST | `/guardian-transfers/{id}/reject` | 수신 학부모 | 대기 요청 거절. 동의 누락·기능 비활성 상태에서도 가능. 다른 종료 상태이면 409 `TRANSFER_ALREADY_RESOLVED` (5.17) | ACC-15 | 우선2 |
| POST | `/guardian-transfers/{id}/cancel` | 발신 학부모 | 대기 요청 취소. 동의 누락·기능 비활성 상태에서도 가능. 다른 종료 상태이면 409 `TRANSFER_ALREADY_RESOLVED` (5.17) | ACC-15 | 우선2 |
| POST | `/guardian-transfers/cancel-outgoing` | 발신 학부모 | 본인의 보낸 대기 요청만 일괄 취소 `{cancelled}`. 동의 누락·기능 비활성 상태에서도 가능. 탈퇴·삭제는 실행하지 않음 (5.17) | ACC-15 | 우선2 |

- 삭제 후 처리 (FN-ACC-13)
  - 삭제가 끝난 기록은 학습·대화·리포트·대시보드 응답에서 제외
  - 근거로 참조된 경우에는 `available: false` 또는 `410 DATA_UNAVAILABLE` 반환
  - 다른 기록으로 대체하지 않음

### 2.2 미션 학습·판정·되묻기 (FN-LRN, FN-JDG)
| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/missions` | 학생 | 학년·입력 방식 범위의 공개 미션 목록(제목·교과·생각 유형·수행 상태), 진행 위치 | LRN-02, DSH-02 | 핵심 |
| GET | `/missions/{missionId}` | 학생 | 장면(애니메이션·정적 대체)·질문·안내·입력 방식 틀. 정답·예시 답 미포함 | LRN-03, LRN-05 | 핵심 |
| POST | `/missions/{missionId}/attempts` | 학생 | 학습 시도 시작. 신규 생성은 `201`, 진행 중 시도 반환(이어하기)은 `200`. core는 learning의 상태를 그대로 전달. body `{context}`(2.11, #387, 생략 시 `EXTRA`) | LRN-01, LRN-16 | 핵심 |
| GET | `/attempts/{attemptId}` | 학생 | 시도 상세: 상태, 최신 초안(`ETag`), 답변·판정·되묻기 타임라인, 가능한 다음 행동 | LRN-16, JDG-08, JDG-09 | 핵심 |
| PUT | `/attempts/{attemptId}/draft` | 학생 | 초안 자동 저장 (`If-Match`), 응답에 저장 시점·새 버전. `content: {answer, memo}` (P05). | LRN-15, LRN-16, LRN-17 | 우선1 |
| POST | `/attempts/{attemptId}/hints` | 학생 | 생각 열기 질문 열람 기록 → 질문 반환 (정답·제출용 답 미포함) | LRN-06 | 핵심 |
| POST | `/attempts/{attemptId}/answers` | 학생 | 답변 제출(최초·보완). 별도 버전 저장, 보완은 `followupId`에 연결. `Idempotency-Key` | LRN-04, LRN-05, LRN-08, LRN-09, LRN-10 | 핵심 |
| POST | `/answers/{answerId}/feedback` | 학생 | **SSE**. 판정 + 되묻기 생성. 이미 완료됐으면 저장된 결과 반환, `FAILED`면 재실행 | JDG-01~07, JDG-09, JDG-10 | 핵심 |
| POST | `/attempts/{attemptId}/finish` | 학생 | 마무리 → 정답(닫힌 문제)·예시 답(열린 문제)·근거 확인된 체크리스트 공개. 판정 `DONE` 1회 이상 아니면 409 (P04) | LRN-11, JDG-09 | 핵심 |
| POST | `/attempts/{attemptId}/self-assessment` | 학생 | 자기 체크 저장 → AI 확인 항목과 나란히 반환 (원본·판정 불변) | LRN-13 | 선택 |
| POST | `/attempts/{attemptId}/reflection` | 학생 | 돌아보기 `{difficulty(필수), text(선택)}` 저장 → 학습 완료 처리 (P04) | LRN-12, LRN-14 | 핵심 |
| GET | `/attempts/{attemptId}/comparison` | 학생 본인 | 같은 학생·미션의 직전 마무리 시도와 현재 시도 비교 `NO_PREVIOUS\|COMPARABLE\|CRITERIA_CHANGED` (#207, 5.15). 학생 세션 전용(학부모·관리자 403), 현재 시도 마무리 이후만 | LRN-09, LRN-11 | — |

- #38 미션 조회의 `grade`·`demo`는 검증된 STUDENT의 연결된 활성 학생을 core DB에서 읽어 결정한다. 공개 요청의 동일 이름 query는 사용하지 않는다. 목록은 `page`·`size`만 learning에 전달하고, 상세도 같은 학생 학년·시연 여부를 붙인다. 학년별 문항 노출·시연 전용 미션 판단은 learning 소유다.

- 음성 시범(FN-LRN-18): 미구현 (P03)
- 질문 읽어주기(FN-LRN-19): 브라우저 TTS(Web Speech API), API 없음 (P03)
- 메모(FN-LRN-07): 초안 `content.memo`로 저장, 학생 본인 조회에만 포함 (P05)
- 되묻기·마무리 (P04)
  - 되묻기는 시도당 최대 2회, 2회째 답변 후 `nextActions: ["FINISH"]`
  - 고르기 `CORRECT`면 되묻기 없이 `nextActions: ["FINISH"]`
  - 되묻기에 답하지 않고 `FINISH` 가능("이대로 돌아보기")
- 2026-11-10 개정(#483, core #485 구현): 무료 테마 문제(`THEME_DAY`·`THEME_REVIEW`)는 core 하루 한도 집계 없이 통과하고, 무료 주 5개는 learning 누적 공개 규칙으로 정한다(learning #484). 추가 문제(`EXTRA`)는 무료 403 `PREMIUM_REQUIRED`(V43이 무료 상품 `features.extraMissions = false`, 값이 없으면 무료 거부 #506). `mission_daily_usage`·`limits.dailyMissions`는 유지하되 무료 상품에서 `EXTRA`를 다시 켤 때의 무료 `EXTRA` 하루 한도로만 쓴다([core 보고서 18절](../report/core-gateway.md#18-무료-테마-주-5문제추가-문제-프리미엄-전용프리미엄-일요일당일-풀이주간-완주-포인트-485-2026-11-10))
- 무료 추가 문제 하루 한도(무료 상품에서 `EXTRA`를 다시 켠 경우만, P13): 한도 수는 무료 상품 `limits.dailyMissions`, 집계는 #210 결정대로 core `mission_daily_usage`([ERD 3.4](erd.md#34-결제구독-fn-pay--토스페이먼츠-테스트), KST 일자)이며 무료 `EXTRA` 신규 생성 `201`만 집계하고 이어하기 `200`·테마 문제(`THEME_DAY`·`THEME_REVIEW`)는 집계하지 않음. 한도 도달 시 신규 생성만 `429 USAGE_LIMIT_REACHED`(같은 미션의 진행 중 시도는 learning에 확인한 뒤 이어하기 허용). 상품 `limits.dailyMissions`가 없거나 음수면 무료 `EXTRA`만 503 `PAYMENT_PRODUCT_UNAVAILABLE`(임의 값으로 대체하지 않음). 2026-11-08 결정(무료 `THEME_DAY`·`EXTRA` 합산 하루 1개)은 위 개정으로 대체
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
- `students/me/preferences`는 3.12 (#234 core 구현)

| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/students/me/home` | 학생 | 학생 정보, 이어할 시도, 시작 가능한 미션 경로 | DSH-01, DSH-02 | 제안 |
| GET | `/students/me/attempts` | 학생 | 최근 학습 기록(미션·시점·완료 여부, `status` 필터) | DSH-03, LRN-16 | 제안 |
| GET | `/students/me/thinking-activities` | 학생 | 수행 미션의 생각 유형·본인 돌아보기 (레벨·등급·순위 없음) | DSH-04 | 제안 |
| GET·PUT | `/students/me/preferences` | 학생 | 생각 지도 테마·동행 캐릭터 설정 (3.12, #234) | - | 제안 |
| GET | `/children/{childId}/summary?from&to` | 학부모 | 학습 건수·상태 `Metric[]`, 집계 기준·기간 (P08) | DSH-06, DSH-07, DSH-10 | 제안 |
| GET | `/children/{childId}/thinking-types?from&to` | 학부모 | 다섯 유형별 미션·기록, 없는 유형은 `NO_RECORD`("미관찰") | DSH-08 | 제안 |
| GET | `/children/{childId}/attempts?from&to` | 학부모 | 기간 내 학습 목록 | DSH-07, DSH-09 | 제안 |
| GET | `/children/{childId}/attempts/{attemptId}` | 학부모 | 최초 답변·되묻기·추가 답변·도움 이용·돌아보기 원문 연결 | DSH-09 | 제안 |

- 모든 응답에 `state`(QueryState)와 `period` 포함
- 기록 없음과 조회 실패를 구분하고, 미확인 수치는 채우지 않음 (FN-DSH-05, FN-DSH-11)

### 2.4 분석 대화 (FN-AGT)
| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| POST | `/conversations` | 학부모 | 대화 생성 `{childId, from, to}` (기본 기간 최근 7일·오늘 포함, P06). 무료 플랜은 `USAGE_LIMIT_REACHED` (P13). `{childId, reportId}`이면 일일 리포트 고정 대화(아래, #392) | AGT-01 | 핵심 |
| GET | `/conversations?childId` | 학부모 | 본인 대화 목록 | AGT-11 | 핵심 |
| GET | `/conversations/{conversationId}` | 학부모 | 질문·답변·대상 자녀·기간·참조 기록. 답변별 `correctionNotice`(5.7, #244) | AGT-11 | 핵심 |
| POST | `/conversations/{conversationId}/messages` | 학부모 | **SSE**. 질문 → 범위 확인 → 기록 조회·계산 → 숫자·인용 대조 → 확정 답변. 범위 변경 시 `scope` 동봉 | AGT-02~06, AGT-08~10 | 핵심 |
| POST | `/conversations/{conversationId}/messages/{messageId}/retry` | 학부모 | **SSE**. 실패한 질문 재처리 | AGT-10 | 핵심 |
| GET | `/conversations/{conversationId}/messages/{messageId}/evidence` | 학부모 | 답변 근거(미션·답변 시점·원문, 전후 답변 연결) | AGT-07 | 핵심 |
| GET | `/agent/example-questions?childId` | 학부모 | 예시 질문(숫자·유형별 활동·아이가 쓴 생각·전후 변화·돌아보기), 가능 여부 표시. 현재 구현은 고정 5문항이며 기록 유무 하나로 모두의 가능 여부를 정함(수학 점검 질문 없음) | AGT-12 | 선택 |
| GET | `/conversations/{id}/report-template` | 학부모 | 현재 확정 리포트 표시 설정 `{settings, revision}` (#209) | — (기능 명세 #209 절) | — |
| POST | `/conversations/{id}/report-template/proposals` | 학부모 | 자연어 요청 `{question}` → 변경안 `{proposalId, settings, expiresAt}` 또는 `{clarification}`. 분석 사용량 차감 (#209) | — (기능 명세 #209 절) | — |
| POST | `/conversations/{id}/report-template/confirm` | 학부모 | 서버에 저장된 변경안 확정 `{proposalId}` → `{settings, revision}`. 만료·대체·다른 대화는 409 `TEMPLATE_PROPOSAL_EXPIRED` (#209) | — (기능 명세 #209 절) | — |

- 예시 질문(FN-AGT-12): core `conversation`이 learning `/internal/records/...`로 기록 유무 확인 후 가능 여부 표시
- 대화 이력은 이용 중 보관, 탈퇴·자녀 삭제 시 파기. 삭제된 근거는 `available: false` (P09)
- 일일 리포트 고정 대화(FN-RPT-16, P25, #392): `{childId, reportId}`이면 그 일일 리포트의 자녀·대상일·최신 판으로 고정(`from = to =` 대상일). `reportId`와 `from`·`to`를 함께 보내면 400. 응답·목록·대화 상세에 `reportId`·`reportRevision`(일반 대화는 null) 포함, core `conversation.report_id`·`report_revision`에 저장. 확인 순서: 자녀 연결·이용권(무료 `429 USAGE_LIMIT_REACHED`) → core `report_job`으로 일일·같은 자녀 확인 → report 최신 판 조회(`COMPLETED`만). 주간 리포트·다른 자녀·없는 리포트·미완료 리포트는 `422 CONVERSATION_REPORT_INVALID`. 메시지마다 core가 report `/internal/reports/{reportId}?revision`(4.4)으로 그 판을 읽어 ai 요청 `report`에 요약(지표 개수, 문제별 제목·맥락·판정·확인 요소. 원문·인용 없음)으로 넣는다(ai → report 직접 호출 없음, 열람 기록 없음). 고정 대화에 다른 기간 `scope`를 보내면 400, 질문 속 다른 날은 ai 범위 확인(`DIFFERENT_PERIOD`)이 새 대화로 안내. 리포트 조회 실패는 메시지 `FAILED`(`REPORT_UNAVAILABLE` 등, 차감 유지). 프리미엄은 분석 대화 하루 30회 공유
- 대조 실패·LLM 장애 시 LLM 답변을 보내지 않고 규칙 응답 모드 결과를 보냄 (3.3, FN-AGT-06·10, P16)

### 2.5 리포트 (FN-RPT)
| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/children/{childId}/reports?status&periodType` | 학부모 | 대상 기간·생성 상태별 목록. `status`는 `RUNNING`·`COMPLETED`·`FAILED`만 허용하며 `QUEUED`·알 수 없는 값은 400 `VALIDATION_FAILED`다(#518). `periodType`(`DAILY`·`WEEKLY`, 생략 시 전체) 필터, 항목에 항상 `periodType`(report가 생략하면 core가 `WEEKLY`로 채움, #390). 페이지 없이 전체 반환(core가 report 목록을 `size=100`으로 끝까지 조회해 합침, #500) | RPT-10, RPT-11, RPT-15 | 핵심 |
| GET | `/reports/{reportId}?revision` | 학부모 | 상세: 기간·포함 기준·`Metric[]`·생각 유형 요약·전후 변화·돌아보기·원문 인용·저녁 질문·버전, `periodType`(core가 작업 기준으로 채움, #390). #391 구현: 일일 `problems[]`, 주간 `themeSummary`(아래). 기본 최신판, `revision`으로 이전판 조회 (P06) | RPT-02~10, RPT-12 | 핵심 |
| GET | `/reports/{reportId}/evidence/{itemId}` | 학부모 | 리포트 항목의 원본 기록 `{items:[{attemptId,answerId,answerVersion,available,quote?,missionTitle?,submittedAt?}]}` (report `EvidencePage` 그대로, 삭제된 근거는 `available=false`·원문 없음) | RPT-03, RPT-12 | 핵심 |
| GET | `/reports/{reportId}/download?format=pdf\|md` | 학부모 | 권한 확인 후 `{url, expiresAt}`(단기 presigned URL) 반환, 웹이 해당 URL로 이동. Bearer 인증이라 302 대신 JSON (PDF·Markdown, P06) | RPT-13 | 핵심 |
| POST | `/reports/{reportId}/regenerate` | 학부모·관리자(`SERVICE_OPS`) | 같은 기간 재생성(일일은 그날, 주간은 그 주) → `report.generate`, 새 판(`revision + 1`) 추가·기존 판 보존. 학부모 리포트당 1회(초과 409, 기간 종류·대상 기간별), 관리자는 `SERVICE_OPS` 권한만 무제한(그 밖의 관리자 403). 응답에 `periodType` (P06, P24) | RPT-12, RPT-15 | 핵심 |

- 자동 생성(FN-RPT-01)은 core 스케줄러가 주가 끝난 일요일 자정(월요일 00:00 KST)에 직전 월~일(KST) 대상으로 수행하며 공개 API는 없음 (P06, 2026-11-09 결정)
- 생성 내용(FN-RPT-02~09)은 report-service가 계산하고, 그 결과를 상세 응답 스키마(3.4)로 제공
- 기록 없는 주·표본 부족 주는 `COMPLETED` + `state: NO_RECORD|INSUFFICIENT_SAMPLE`로 표시하며, 생성 실패(`FAILED`)와 구분 (FN-RPT-11). `NO_RECORD`는 LLM 미호출 (P06)
- 무료 플랜은 수치만 제공(`narrative: null`, 생각 유형 `summary` 없음) (P13)
- 일일 리포트(FN-RPT-14·15, P24): core 스케줄러가 대상일이 끝난 자정(다음 날 00:00 KST, ShedLock `core-daily-reports`)에 보호자가 연결된 자녀별 전날(KST) 대상으로 작업을 만든다(#390, 기록 없는 날 포함, 생성 시각은 2026-11-09 결정). report 생성·저장·조회·다운로드 구현(#391). 상세의 일일 항목은 `problems:[{missionId, title, context, judgment, followups[], finalAnswer, elements[], reflection, quotes[]}]`, `metrics`는 개수만, `eveningQuestion`·`narrative` 없음. 토·일은 되돌아보기 다시 풀기·추가 문제 시도도 포함
- 주간 테마 요약(FN-RPT-17, #391 구현): 주간 상세에 `themeSummary:{themeId, title, days[], completed, reviewRetries[], finished, ending}`. 테마 미참여 주는 `state: NO_RECORD` 요약. #486: `days[].completed`(당일 풀이)·`days[].completedInWeek`(그 주 안에 학습 완료)로 요일별 "그날 풀었어요·나중에 풀었어요·못 풀었어요", `completed`(개근)·`finished`(주간 완주)·`ending`(`NOT_ENDED`·`ENDED`)을 표시. 새 칸은 learning이 주지 않으면 `null`이며 이전처럼 표시
- 다운로드·근거·재생성 경로는 2.5 그대로이며 일일에도 같은 규칙(학부모 리포트당 1회, 관리자 무제한)
- 일일 리포트는 이용권과 관계없이 전체 제공(서술이 없어 `X-Report-Narrative-Enabled`와 무관). 주간 무료 규칙은 그대로
- 알림 유형: `DAILY_REPORT_COMPLETED`·`DAILY_REPORT_FAILED`(2.7 설정 1~9개, #390)
- 리포트 고정 대화의 질문은 그 대상일 밖으로 범위를 바꾸지 않는다. 다른 날 질문은 범위 확인에서 새 대화 안내

### 2.6 결제·구독 (FN-PAY) — 토스페이먼츠 테스트 환경만
| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/products` | 공개 | 상품 목록(무료·프리미엄 월 14,900원): 가격·청구 주기·기능·사용 한도·대상 자녀 수·기간. 값은 `product` 데이터 (P13) | PAY-01 | 우선2 |
| GET | `/children/{childId}/entitlement` | 연결 학부모 | 실제 상품·구독의 `childId, product, subscriptionId, status, autoRenew, periodEnd, graceUntil, refundPending, conversationEnabled, narrativeEnabled` 조회. `Cache-Control: no-store`. 기본 무료 상품 미설정은 `PAYMENT_FREE_PRODUCT_UNAVAILABLE` 503이며 임의 무료 값으로 대체하지 않음 | PAY-01 | 우선2 |
| POST | `/orders` | 학부모 | 결제 요청 생성 `{productId, childId}` → `orderId`·금액·위젯 파라미터. 중복 구독 409. `Idempotency-Key` | PAY-02, PAY-03 | 우선2 |
| POST | `/payments/confirm` | 학부모 | 위젯 성공 리다이렉트 값(`paymentKey, orderId, amount`)으로 서버 승인 → 금액 대조 → 구독·권한 반영. `Idempotency-Key` | PAY-03, PAY-04, PAY-05 | 우선2 |
| GET | `/payments/{orderId}` | 학부모 | 결제 상태 (`CONFIRMING`이면 PG 상태 조회 후 갱신) | PAY-04 | 우선2 |
| GET | `/payments` | 학부모 | 본인 거래 내역(결제·취소·환불) | PAY-07 | 우선2 |
| GET | `/subscriptions` | 학부모 | 구독 상태·대상 자녀·이용 기간·다음 결제 예정일 | PAY-07 | 우선2 |
| GET | `/subscriptions/{subscriptionId}/billing-key` | 학부모 | 자동결제 수단 등록 준비 `{subscriptionId, customerKey}` (PG 결제위젯 빌링 인증 요청에 사용) | PAY-08 | 우선2 |
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
| POST | `/error-reports` | 학생·학부모 | 오류 신고 `{targetType: FOLLOWUP\|JUDGMENT\|ANALYSIS\|REPORT\|COMMUNITY_POST(학생만, #388), targetId, category, comment}` (`category`: `WRONG_JUDGMENT` 판정이 틀려요 · `ODD_QUESTION` 질문이 이상해요 · `MISMATCH` 숫자·인용이 달라요 · `INAPPROPRIATE` 부적절한 표현 · `OTHER` 기타, P10) | SUP-01 | 우선1 |
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
- 설정: GET → `{items:[{type,enabled}]}`, PUT도 동일한 객체(1~9개 중복 없는 유형)로 지정 유형만 갱신하고 전체 유효 설정을 반환. 미저장 유형 기본 true, 채널은 IN_APP 고정. 유형은 REPORT_COMPLETED, REPORT_FAILED, ERROR_REPORT_RESOLVED, INQUIRY_ANSWERED, PAYMENT_CHANGED, SUBSCRIPTION_CHANGED, DAILY_REPORT_COMPLETED, DAILY_REPORT_FAILED, GRADE_PROMOTED. `GRADE_PROMOTED`는 3월 학년 자동 진급 안내(P26, #432): 제목 "{별명}의 학년이 {새 학년}으로 올라갔어요. 다르면 정보 관리에서 고쳐 주세요.", 링크 `/parent/settings`, 원천 ID는 학생·학년도로 정해 같은 진급을 두 번 알리지 않는다. 수신 거부는 이후 알림 생성을 막으며 기존 알림은 보존한다.
- 리포트 실패는 REPORT_FAILED로 독립 설정한다. 일일 리포트(P24)는 DAILY_REPORT_COMPLETED·DAILY_REPORT_FAILED로 주간과 따로 설정한다(#390). 완료·실패 모두 현재 연결·동의가 유효한 보호자에게 생성한다. 상세 링크 권한은 이동 시 다시 검사한다. 실패 링크는 리포트 목록으로 이동한다.
- SSE는 `event: notification`에 목록 항목과 같은 데이터를 전송한다. 15초 `: ping`, 최대 5분 후 재연결. 각 전송·heartbeat에서 세션/동의를 재검사하고 만료·폐기 시 연결을 닫는다. 학생으로 역할을 바꾸면 기존 보호자 구독도 폐기된 세션 검사로 닫힌다.
- 구독 준비 후 `event: ready`를 받으면 목록 API를 첫 페이지부터 재조회해 id로 병합한다. 연결 중에도 주기적으로 목록을 동기화한다. Last-Event-ID 재생은 제공하지 않는다. Redis Pub/Sub은 유실 가능하며 SSE를 영구 전달 보장으로 사용하지 않는다.
- DB 저장이 원본이다. 커밋 이후 Redis에 발행하며 발행 실패는 DB 전달 상태 FAILED/REDIS_PUBLISH_FAILED와 로그로 기록한다. COMPLETED는 Redis 발행 성공이며 브라우저 수신 확인이 아니다(구독자 0명도 발행 성공). 프로세스가 커밋 직후 종료되면 QUEUED로 남아도 목록에서 조회된다. 발행 실패 때문에 리포트 상태를 되돌리지 않는다.

- 알림 생성(FN-SUP-08)은 내부 사건(리포트 완료·실패, 신고·문의 처리, 구독·결제 변경)에서 발생
  - 사건 ID 기준으로 1회만 생성
  - 알림 본문에는 학생 원문·결제 민감 정보를 넣지 않고 상세 화면 링크만 담음 (FN-SUP-11)
- 신고 대상 `COMMUNITY_POST`(2.9, 학생만)는 #388에서 구현

### 2.8 관리자 (FN-ADM, FN-SUP 관리 측) — `/api/v1/admin`

#### 2.8.1 #47 구현 계약

##### #47 REPORT 실패 작업 재처리 (core, #152 연결)

- SERVICE_OPS 관리자만 실패한 report_job ID로 `POST /admin/jobs/{jobId}/retry`를 요청한다. reportId가 없어도 가능하며 원래 FAILED 작업·기존 report 판은 바꾸지 않는다. 학부모 regenerate 경로와 제한은 유지한다.
- REPORT 성공 접수는 **202** `{originalJobId,jobId,type:"REPORT",status:"QUEUED",acceptedAt}`와 `Location: /api/v1/admin/jobs/{새jobId}`다. 이는 실행 완료가 아니다. 알림의 기존 200 작업 상세 응답은 유지한다. CONVERSATION은 하단 [#47 CONVERSATION 관리자 재처리](#514-47-conversation-관리자-재처리)의 202 접수를 따른다.
- 원작업↔새 ADMIN_RETRY 작업 관계와 수행자·Idempotency-Key·접수 시각은 core report_job_retry에 영속 저장한다. 원작업당 새 작업 1개, 새 작업 ID·수행자+요청 키 각각 UNIQUE다. 같은 키의 응답 저장 유실/24시간 만료 뒤에도 최초 202를 복원한다. 다른 키로 이미 재처리한 원작업을 요청하면 409 REPORT_ALREADY_RETRIED다. 새 작업이 다시 FAILED면 그 새 jobId를 대상으로 다음 재처리를 요청한다.
- 기존 학생·주 잠금과 원작업 행 잠금을 사용하고 다른 QUEUED/RUNNING 주간 작업이 있으면 409 REPORT_GENERATION_IN_PROGRESS다. 학생 활성 상태·삭제 요청 이력을 학생 행 잠금 아래 확인하며 삭제/비활성은 409 REPORT_RETRY_STUDENT_UNAVAILABLE다. 현재 상품의 narrativeEnabled를 기존 ReportEntitlementService로 확정하며 설정/조회 장애는 기존 명시적 오류다.
- 새 report_job·관계·요청 감사 JOB_RETRY_REQUESTED·기존 OutboxWriter의 report.generate를 한 트랜잭션에 기록한다. 외부 HTTP/브로커 호출은 이 트랜잭션에서 하지 않는다. 기존 v1 이벤트 필드만 사용하며 원작업 연결은 core가 소유한다.
- 새 job의 started/completed/failed와 job_execution은 기존 ReportLifecycleService를 재사용한다. ReportJobOutcomeRecorded의 BEFORE_COMMIT 처리로 JOB_RETRY_COMPLETED/FAILED 감사를 동일 결과 트랜잭션에 저장한다. 이 내부 이벤트는 정상 결과·복구·삭제 종료에 모두 적용하며 reportId 없는 실패도 포함한다. 부모 알림용 ReportJobFinished의 기존 조건은 유지한다. 과거 job의 지연/중복 이벤트는 기존 종료 상태와 jobId 구분으로 새 작업을 덮어쓰지 않는다.
- 작업 DTO에 `retryOfJobId`(직전 원작업), `retryJobId`(직접 재처리 작업)를 nullable UUID로 추가한다. 이미 자식이 있는 FAILED REPORT는 retryable=false, retryUnavailableReason=REPORT_ALREADY_RETRIED다. 관계 없는 FAILED REPORT의 retryable=true는 접수 가능 상태를 뜻하며 POST에서 현재 권한·학생/상품·진행 작업을 다시 검사한다.

- overview·audit-logs의 정확한 GET 경로는 ADMIN 역할, jobs·queues·retry는 SERVICE_OPS, missions는 CONTENT다. 다른 관리자 경로의 기존 권한은 유지한다.
- overview/jobs/audit 기간은 KST 날짜 양 끝 포함(저장 조회는 시작 이상·다음날 미만), 둘 다 생략하면 최근 7일, 한쪽만 입력하거나 역순·366일 초과는 400. page=0, size=20(1~100), page 최대 1000. 정렬은 createdAt DESC, id DESC다.
- overview는 `{period,inclusionRule,learning:{attempts,completedAttempts,students,inclusionRule},jobCounts:[{type,status,count}],missionCounts:[{status,count}],missionInclusionRule}`다. learning은 P08, core 작업은 생성 시각이 기간 안인 작업의 현재 상태를 센다. 미션은 learning 관리자 목록의 전체 현재 상태별 건수로 기간·필터·페이지와 무관하다. learning 장애/계약 위반은 오류다.
- jobs는 `{items,page,size,totalElements}`, 상세는 `{jobId,type,status,retryCount,failureReason,createdAt,executions,retryable,retryUnavailableReason}`다. CONVERSATION ID는 conversation_message.id, REPORT는 report_job.id, NOTIFICATION은 notification.id다. updatedAt은 존재하지 않아 반환하지 않는다. executions는 실제 job_execution을 attemptNo 순으로 반환한다. error_detail·원문 실패 메시지·감사 detail은 공개하지 않고 알려진 오류 코드만 노출하며 그 외는 REDACTED_ERROR다. UUID가 종류 간 충돌하면 409 JOB_ID_AMBIGUOUS다.
- retry는 UUID Idempotency-Key 필수, 실패 상태만 허용한다. NOTIFICATION은 동일 ID를 RUNNING으로 원자 선점하고 새 job_execution을 남긴 뒤 트랜잭션 밖에서 기존 Redis publisher/DeliveryService를 호출한다. Redis 확인은 브라우저 수신 확인이 아니다. 실제 결과를 200 작업 상세로 반환하고 감사 기록을 남긴다. RUNNING 고착은 자동 재실행하지 않는다. REPORT는 위 REPORT 접수 계약에 따라 새 jobId로 재처리하며 원작업을 보존한다. CONVERSATION은 하단 계약대로 DB 대기 작업으로 202 접수한다. 리포트 regenerate를 대신 호출하지 않는다. 실패한 요청은 실행 이력으로 위장하지 않으며 거절 감사만 남긴다.
- audit-logs는 targetType/targetId 및 기간·페이지 필터. 항목은 `{id,actorUserId,action,targetType,targetId,result,createdAt}`이며 자유형 detail은 노출하지 않는다. 기존 감사 저장 경로를 교체하지 않는다.
- queues는 `{vhost,items:[{name,kind:WORK|RETRY|DLQ,messages,messagesReady,messagesUnacknowledged,consumers,state}]}`다. definitions.json의 `/` vhost와 고정 35개 큐(기본 큐 7개×기본·재시도 3·DLQ)만 읽는다(#208 감사 큐 `core.event.audit`, #370 `core.model.loading.reported` 포함). 누락·인증·HTTP·타임아웃·잘못된 응답은 명시적인 503/504이며 0으로 치환하지 않는다. `ADMIN_RABBIT_MANAGEMENT_URL`, `ADMIN_RABBIT_MANAGEMENT_USERNAME`, `ADMIN_RABBIT_MANAGEMENT_PASSWORD`를 환경에서 읽는다(기본 자격 증명 없음). 기존 AMQP 설정과 독립이며 production 의존성은 추가하지 않는다.
- missions는 표의 명시된 메서드/경로만 `/internal/admin/missions`로 프록시한다. 검증된 ADMIN 사용자 컨텍스트, 빈 학생 범위, 내부 토큰과 trace를 기존 LearningClient/InternalRestClientFactory로 전달한다. JSON object 본문과 목록 status/grade/thinkingType/page/size만 전달한다. 버전·기준표·검토·게시 정책/DTO는 learning 소유다. learning 공급자 계약은 4.1 `/internal/admin/missions…`(#145)와 learning OpenAPI다. 404는 application/problem+json JSON 객체의 status=404·code=NOT_FOUND가 일치할 때 404 NOT_FOUND와 고정 문구 "미션을 찾을 수 없습니다."로 반환한다(#163). 불명확한 404와 API 미지원 405/501은 기존 503 ADMIN_MISSIONS_UNAVAILABLE다. 나머지 Problem Details는 기존 code/status와 구조화된 missingFields만 허용하며 자유형 오류 문구는 전달하지 않는다. 성공 응답은 learning 관리자 콘텐츠 계약을 그대로 반환한다. 쓰기는 요청 감사 후 호출하고 응답 missionId·버전으로 결과 감사를 남긴다(하단 #47 미션 운영 후속 계약). 서비스 간 재시도는 없다.
- #355: 성취기준 표·미션 초안(아래 표 `/admin/achievement-standards`·`/admin/mission-drafts…`)도 같은 방식으로 learning `/internal/admin/achievement-standards`·`/internal/admin/mission-drafts…`(4.1)로 프록시하고 CONTENT 권한이다. learning 오류 코드(`VALIDATION_FAILED`·`NOT_FOUND`·`CONFLICT`)는 그대로 전달하고 404 고정 문구는 "미션 초안을 찾을 수 없습니다.", 미지원 405/501은 미션과 같은 `ADMIN_MISSIONS_UNAVAILABLE`이다. 초안 요청·채택·버리기는 요청·결과 감사를 남긴다(`audit_log.action` `MISSION_DRAFT_REQUEST`·`MISSION_DRAFT_ADOPT`·`MISSION_DRAFT_DISCARD` + `_REQUESTED`·`_SUCCEEDED`·`_REJECTED`·`_UNKNOWN`). 대상은 `target_type = MISSION_DRAFT`·초안 ID(요청의 요청 감사는 아직 ID가 없어 NULL)이고, 채택 결과만 응답 `missionId`(`target_type = MISSION`, detail `draftId`·버전, FN-ADM-13). 목록 필터는 표의 쿼리만 전달하고 `status`·`page`·`size`는 core가 먼저 검사한다.

| Method | Path | 권한 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/admin/overview?from&to` | 관리자 | 학습 시도·완료 건수, 대화·리포트·알림 처리 현황, 미션 공개 현황 (학생 원문 없음) | ADM-01, ADM-02, ADM-04 | 제안 |
| GET | `/admin/jobs?type=CONVERSATION\|REPORT\|NOTIFICATION&status` | SERVICE_OPS | 작업 상태별 목록, 요약 수치 → 상세 이동 | ADM-03, ADM-05, SUP-11 | 제안 |
| GET | `/admin/jobs/{jobId}` | SERVICE_OPS | 실패 원인·처리 이력 | ADM-07 | 제안 |
| POST | `/admin/jobs/{jobId}/retry` | SERVICE_OPS | 권한·중복 확인 후 재처리, 실제 결과로 갱신 (`SERVICE_OPS` 전원, `audit_log`, P07). `Idempotency-Key` | ADM-07, SUP-11 | 제안 |
| GET | `/admin/queues` | SERVICE_OPS | 큐 길이·DLQ 적재 현황 | ADM-03 | 제안 |
| GET | `/admin/audit-logs?targetType&from&to` | 관리자 | 운영 조치·콘텐츠 변경 이력(수행자·대상·시점·결과) | ADM-06, ADM-13 | 제안 |
| GET | `/admin/missions?status&grade&thinkingType` | CONTENT | 미션 목록·상태별 건수 | ADM-04, ADM-08 | 제안 |
| POST | `/admin/missions` | CONTENT | 미션 작성 (학년·생각 유형·입력 방식·장면·질문·교과·성취기준, 시연 전용 여부) | ADM-09 | 제안 |
| GET | `/admin/missions/{missionId}` | CONTENT | 미션 상세·버전 이력 | ADM-09, ADM-10 | 제안 |
| PATCH | `/admin/missions/{missionId}` | CONTENT | 미션 수정 (새 버전 생성, 기존 학습은 당시 버전 유지) | ADM-09, ADM-12 | 제안 |
| PUT | `/admin/missions/{missionId}/rubric` | CONTENT | 기준표(요소·배점·흔한 오답)·정답·예시 답·들어가면 좋은 생각·생각 열기 질문 → 새 기준 버전. 요소 code는 FN 1.5 표준 요소 모양(표준 코드·`e`+숫자·`ANSWER_KEY`·`FINAL_ANSWER`), 아니면 400 (#262) | ADM-10 | 제안 |
| GET | `/admin/missions/{missionId}/preview` | CONTENT | 학생 화면 미리보기 데이터 | ADM-09 | 제안 |
| POST | `/admin/missions/{missionId}/review-request` | CONTENT | 검토 요청 `DRAFT → REVIEW_REQUIRED` (현재 미션·기준표 버전 필요) (P07) | ADM-11 | 제안 |
| POST | `/admin/missions/{missionId}/review` | CONTENT | 검토 결과 기록, `CONTENT` 1인 가능(작성자 포함) (P07) | ADM-11 | 제안 |
| POST | `/admin/missions/{missionId}/publish` | CONTENT | 게시, 필수 누락 시 422. 재게시 시 새 버전이 신규 시도부터 적용, 진행 중 시도는 시작 당시 버전 유지 (P07) | ADM-11 | 제안 |
| POST | `/admin/missions/{missionId}/unpublish` | CONTENT | 신규 제공 중단 (진행 중 시도는 시작 당시 버전으로 계속, P07) | ADM-12 | 제안 |
| GET | `/admin/achievement-standards?subject&gradeBand&q&page&size` | CONTENT | 성취기준 표 조회 (미션 작성·초안 요청에서 고름, #355) | ADM-21 | 제안 |
| POST | `/admin/mission-drafts` | CONTENT | 미션 초안 생성 요청 → 202, 생성·자동 검사는 비동기 (#355) | ADM-20 | 제안 |
| GET | `/admin/mission-drafts?status&page&size`, `/admin/mission-drafts/{draftId}` | CONTENT | 초안 목록·상세 (상태·시도 횟수·검사 실패 사유·초안·버전) | ADM-20 | 제안 |
| POST | `/admin/mission-drafts/{draftId}/adopt` | CONTENT | 검사 통과 초안 채택 → `DRAFT` 미션 생성, 이후 위 미션 경로로 수정·검토·게시 | ADM-20, ADM-09 | 제안 |
| POST | `/admin/mission-drafts/{draftId}/discard` | CONTENT | 초안 버리기 | ADM-20 | 제안 |
| GET | `/admin/error-reports?status` | SERVICE_OPS | 신고 목록·상태별 | SUP-02 | 우선1 |
| GET | `/admin/error-reports/{reportId}` | SERVICE_OPS | 신고 상세 + 연결 시도의 답변·판정 원문 (열람마다 `audit_log`, P07) | SUP-02 | 우선1 |
| PATCH | `/admin/error-reports/{reportId}` | SERVICE_OPS | 상태·검토 결과·처리 이유 (접수만으로 판정 변경 없음) | SUP-02 | 우선1 |
| POST | `/admin/error-reports/{reportId}/corrections` | SERVICE_OPS | 정정: 기존 결과·사유·시점 보존, 영향받는 대화·집계·리포트 반영 여부 (원본 답변 불변) | SUP-03 | 우선1 |
| GET | `/admin/inquiries?status` | SERVICE_OPS | 문의 목록 | SUP-06 | 우선2 |
| GET | `/admin/inquiries/{inquiryId}` | SERVICE_OPS | 문의 상세 (5.7) | SUP-06 | 우선2 |
| POST | `/admin/inquiries/{inquiryId}/answer` | SERVICE_OPS | 문의 답변 | SUP-06 | 우선2 |
| GET | `/admin/notices?status=SCHEDULED\|ACTIVE\|ENDED&role=STUDENT\|PARENT\|ADMIN` | SERVICE_OPS | 예약·공개 중·종료 공지 전체 목록 (상태·대상 역할 필터, 페이지, #242) | SUP-07 | 우선2 |
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
| GET | `/admin/ai-usage?from&to&callType` | SERVICE_OPS | 되묻기·판정·분석·리포트·미션 초안(#355, `MISSION_DRAFT`)·리포트 설명(FN-RPT-09, #480 `REPORT_EXPLANATION`)·지식 임베딩(#467 `KNOWLEDGE_EMBEDDING`)·주간 테마 생성(#439, 텍스트 `THEME_DRAFT`·이미지 `THEME_IMAGE`·영상 `THEME_VIDEO` #436)·scoring 모델(`M2`·`M1`)별 호출량·실패·지연·토큰·비용 (요금제 한도 P13, 월 LLM 비용 예산 80% 경보 P10) | ADM-19 | 우선1 |
| GET·POST | `/admin/weekly-themes?grade&weekStart&status` | CONTENT | 테마 목록·작성 `{grade, weekStart, title, intro, days:[{day, missionId}]}`. `grade`는 `G3`·`G4`·`G5`·`G6`(학년별 테마, 에픽 #436) | ADM-22 | core 프록시 #387 |
| GET·PUT | `/admin/weekly-themes/{themeId}` | CONTENT | 상세·수정(게시 중 수정은 재검토) | ADM-22 | core 프록시 #387 |
| POST | `/admin/weekly-themes/{themeId}/review-request` · `/publish` · `/unpublish` | CONTENT | 미션과 같은 작성→검토→게시(본문 `{}`). 별도 검토 경로 없이 검토 요청한 현재본의 게시가 승인, 아니면 `409 CONFLICT`. 게시 검사: 월~금 다섯 요일, 게시 미션만(시연 전용 제외), 다섯 생각 유형 1개씩, 학년군 전체를 덮는 학년 범위(초3~4 논술 불가), 같은 학년군·주 게시 1개 | ADM-22 | core 프록시 #387 |
| POST | `/admin/theme-drafts` | CONTENT | 테마 초안 생성 요청(에픽 #436) `{grade, weekStart, topic?, missions?:[{thinkingType, standardCodes[], inputType}]}`(본문 값 검사는 learning #438) → `202 ThemeDraft`(`status: GENERATING`, 생성은 learning 주기 작업) | ADM-22 | core 프록시 #439 |
| GET | `/admin/theme-drafts?status&source&page&size` · `/admin/theme-drafts/{draftId}` | CONTENT | 목록(최근 요청 순)·상세. `status`는 `GENERATING`·`READY`·`CHECK_FAILED`·`FAILED`·`ADOPTED`·`DISCARDED`, `source`는 `AUTO`(주간 자동)·`ADMIN`(관리자 요청) | ADM-22 | core 프록시 #439 |
| POST | `/admin/theme-drafts/{draftId}/adopt` · `/discard` · `/regenerate` | CONTENT | 채택 `{}` → `201 AdminWeeklyTheme`(미션 5개 `DRAFT`·테마 `DRAFT`를 learning 한 트랜잭션으로, 자동 게시 없음), 버리기 `{}` → `ThemeDraft`, 다시 생성 `{}` → `202 ThemeDraft`. 상태상 불가 전이 `409 CONFLICT` | ADM-22 | core 프록시 #439 |
| GET·POST | `/admin/look-items?status&slot&page&size` | CONTENT | 아이템 목록(최신 등록순 `{items, page, size, totalElements}`)·등록 `{code, slot, name, pricePoints, assetKey?}` → 201 `{itemId, code, slot, name, pricePoints, assetKey, status, createdAt, updatedAt}`. `slot`은 `HAT`·`OUTFIT`·`ACCESSORY`·`BACKGROUND`, `code`는 대문자·숫자·밑줄 3~40자(변경 불가, 중복 409 `LOOK_ITEM_CODE_DUPLICATE`), 이름 1~40자, 포인트 1~10000, 형식 오류 422 | ADM-23 | 핵심(#389) |
| PATCH | `/admin/look-items/{itemId}` | CONTENT | 이름·필요 포인트·그림 수정, `status`(`ON_SALE`·`STOPPED`, 삭제 없음). 판매 중단해도 해금한 학생은 계속 착용, 가격 변경은 해금한 학생과 무관. 없는 아이템 404 | ADM-23 | 핵심(#389) |

- 테마는 core가 learning `/internal/admin/weekly-themes…`로 프록시(#355 미션 초안과 같은 방식, core #387·learning #385 구현), 테마 초안은 `/internal/admin/theme-drafts…`로 같은 방식(core #439·learning #438), 아이템은 core 소유. 변경은 `audit_log`(`WEEKLY_THEME_*`·`THEME_DRAFT_*`·`LOOK_ITEM_*`). 테마 초안 요청·버리기·다시 생성은 응답 초안(`target_type = THEME_DRAFT`), 채택은 만든 테마(`WEEKLY_THEME`, `detail.draftId`)가 결과 감사 대상 아이템은 같은 트랜잭션에서 `LOOK_ITEM_CREATED`·`LOOK_ITEM_UPDATED`·`LOOK_ITEM_STOPPED`·`LOOK_ITEM_RESUMED`(`target_type = LOOK_ITEM`, 수정은 `detail.before`에 이전 값)
- 커뮤니티 신고 검토는 기존 `/admin/error-reports`(SERVICE_OPS). 신고 연결 공유물 원문 열람은 감사 기록(P07)


### 2.9 커뮤니티 (FN-RET-01~04, P20)

core 경로는 #388에서 구현해 OpenAPI(`contracts/openapi/core-service.yaml`, 태그 Community)에 반영했다. 공유물·반응 저장과 열람 검사는 learning #386(구현, [ERD 4.3.1](erd.md#431-커뮤니티-공유물반응-p20-386), 내부 경로 4.1·`contracts/openapi/learning-service.yaml`), 공개 설정은 core `student.community_enabled`(ERD 3.1).

| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/students/me/community-settings` | 학생 | `{enabled, consentGranted, updatedAt}`. `consentGranted`는 현재 연결 보호자의 현재 문서 `COMMUNITY` 동의 | RET-01 | 구현(#388) |
| PUT | `/students/me/community-settings` | 학생 | `{enabled}`. 켜기는 보호자 선택 동의(`COMMUNITY`) 필요, 없으면 409 `COMMUNITY_CONSENT_REQUIRED`. 끄면 기존 공유물 즉시 비공개. 같은 값이어도 learning 공개 상태를 다시 맞춤 | RET-01 | 구현(#388) |
| GET | `/missions/{missionId}/community-posts?seed&page&size` | 학생 | 같은 미션 공유물 무작위 목록 `{items:[{postId, author:{nickname, look}, answer, myReactions[], createdAt}]}`. 반응 수·학생 ID 미포함. 같은 `seed`면 같은 순서. 이 미션을 마무리하지 않았으면 403 `COMMUNITY_LOCKED`, 정답 고르기 문제를 엔딩 전이면 403 `COMMUNITY_LOCKED_UNTIL_ENDING`(learning #484, core 공개 문구 #550). `look`은 `{theme, companion, equipped:{HAT, OUTFIT, ACCESSORY, BACKGROUND}}`(저장 전 `lake`·`mungchi`, 착용 없는 슬롯 null, #389) | RET-02 | 구현(#388·#389) |
| GET | `/students/me/community-posts` | 학생 | 내 공유물 `{items:[{postId, missionId, missionTitle, answer, status, reactions:{4종: 수}, createdAt}]}` | RET-02, RET-03 | 구현(#388) |
| PUT | `/community-posts/{postId}/reactions/{reaction}` | 학생 | 반응 남기기(멱등). `reaction`: `NEW_IDEA`·`CLEAR_REASON`·`DIFFERENT_VIEW`·`WANT_MORE`. 본인 글 409 `COMMUNITY_OWN_POST`, 열람 권한 없으면 403 `COMMUNITY_LOCKED`, 신고 숨김·없는 글 404 `COMMUNITY_POST_NOT_FOUND`, 4종 외 400. 성공 204 | RET-03 | 구현(#388) |
| DELETE | `/community-posts/{postId}/reactions/{reaction}` | 학생 | 반응 취소(멱등, 적립 포인트 회수 없음). 성공 204 | RET-03 | 구현(#388) |
| GET | `/children/{childId}/community-posts` | 학부모 | 연결·동의가 유효한 자녀의 공유물·상태·받은 반응 수(내 공유물과 같은 모양). 다른 학생 공유물 조회 경로 없음 | RET-02 | 구현(#388) |

- 공유물 생성 API는 없다. 커뮤니티 공개가 켜진 학생의 돌아보기 저장(`POST /attempts/{id}/reflection`, 학습 완료) 성공 후 core가 learning에 공유를 요청한다. 학생·미션당 1개로 그 미션을 처음 마무리한 시도의 마지막 답변만 공유하고(다시 풀기는 공유하지 않음) 메모·판정·되묻기는 넣지 않는다. `answer`는 learning `{inputType, text(입력 틀 칸 이름을 붙인 원문), content(입력 방식별 제출 내용)}`를 그대로 전달한다(#386)
- 작성자 표시: learning은 학생 ID를 돌려주고 core가 별명·꾸미기(`look`: 테마·캐릭터·착용 아이템 네 슬롯, #389)로 바꾼 뒤 학생 ID를 지워 응답한다. 반응 수는 learning이 주더라도 목록에서 뺀다
- core 재확인(#388): learning 공개 전환·검토 호출이 실패하거나 늦어도, core는 지금 공개할 수 없는 작성자(설정 끔·현재 보호자 동의 없음·비활성)와 접수·처리 중이거나 계속 숨김으로 처리된 신고가 걸린 공유물을 목록에서 빼고 반응을 404로 막는다. 내 공유물·자녀 공유물 상태도 core가 아는 비공개(`HIDDEN_SETTING`·`HIDDEN_REPORT`)로 덮어 보여 준다
- 신고: 기존 `POST /error-reports`에 `targetType: COMMUNITY_POST`, `targetId: postId` 추가(유형 5종 그대로). 접수 즉시 공유물 `HIDDEN_REPORT`, 관리자는 기존 `/admin/error-reports`에서 `RESOLVED` + `reviewResult: VISIBLE`(다시 공개)·`REMOVED`(계속 숨김, 생략 시 기본)로 처리. 같은 공유물의 신고가 여럿이면 계속 숨김이 하나라도 있으면 `REMOVED`, 처리 중이 있으면 `HIDDEN_REPORT`. 신고 행은 신고한 학생의 것(`student_id` = 신고 학생, 작성자 ID는 learning에만), 관리자 상세 `linkedPost`(원문, 열람마다 `SUPPORT_ORIGINAL_VIEW` 감사)
- 보호자 동의: 기존 `/me/consents`에 문서 종류 `COMMUNITY`(선택, 자녀 단위 `childId`) 추가. 자녀 동의 요청은 `GUARDIAN`·`COMMUNITY` 중 보낼 문서만 담을 수 있고, `COMMUNITY`만 보낼 때는 그 자녀의 현재 법정대리인 동의가 있어야 한다(없으면 400). 거부·철회 시 core가 설정을 끄고 공유물을 비공개로 바꾼다(P09 선택 동의). 이관 전 보호자의 옛 동의 철회는 지금 보호자의 설정을 바꾸지 않는다
- 공개 설정을 끄면 공유물 `HIDDEN_SETTING`, 다시 켜면 `HIDDEN_SETTING`만 `VISIBLE`로 복원(`HIDDEN_REPORT`·`REMOVED` 유지). #289 이관 수락 시 `HIDDEN_SETTING`, 새 보호자가 `COMMUNITY` 동의하고 설정이 켜져 있으면 다시 공개

### 2.10 포인트·꾸미기 (FN-RET-05·06, P21·P22)

2026-11-06 결정. #389로 조회·해금·착용·관리자 아이템을 구현했다(OpenAPI `RewardPoints`·`LookCatalog`·`LookUnlockResult`·`StudentLook.equipped`). 적립 사건 연결(학습 완료·공유·반응·되돌아보기·완주)도 #387·#388 뒤 구현했다(공개 응답 모양 변화 없음). 꾸미기 설정 확장은 3.12. 저장은 [ERD 3.5.1](erd.md#351-포인트꾸미기-p21p22-389).

| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/students/me/points?page&size` | 학생 | `{balance, items:[{eventType, amount, createdAt}], page, size, totalElements}` (최신순, size 1~100) | RET-05 | 핵심(#389) |
| GET | `/children/{childId}/points?page&size` | 학부모 | 연결 자녀 잔액·내역(같은 모양). 학생 공개 설정(#206)과 무관, 연결 아닌 자녀 403 | RET-05 | 핵심(#389) |
| GET | `/students/me/look-items` | 학생 | 테마·캐릭터·아이템 목록 `{items:[{itemKey, slot, name, pricePoints, unlocked, onSale, assetKey}]}`(테마·캐릭터 `assetKey` null). 판매 중단 아이템은 해금한 학생에게만 `onSale:false`로 보임 | RET-06 | 핵심(#389) |
| POST | `/students/me/look-items/{itemKey}/unlock` | 학생 | 포인트 해금 → 200 `{itemKey, unlocked:true, balance}`. `Idempotency-Key`(UUID) 필수(없으면 400), 같은 키 재전송은 처음 응답, 같은 키·다른 항목 422 `IDEMPOTENCY_KEY_REUSED`. 잔액 부족 409 `INSUFFICIENT_POINTS`, 판매 중단 409 `LOOK_ITEM_NOT_ON_SALE`, 없는 항목 404 `LOOK_ITEM_NOT_FOUND`, 이미 해금(무료 포함) 200(차감 없음). 잔액 행 잠금으로 다른 키 동시 요청도 1회만 차감 | RET-06 | 핵심(#389) |
| PUT | `/students/me/preferences` | 학생 | 3.12 확장: `{theme, companion, equipped?:{HAT, OUTFIT, ACCESSORY, BACKGROUND}}`(슬롯별 아이템 `itemKey` 또는 null, 생략하면 착용 유지). 잠긴 항목 409 `LOOK_LOCKED`, 모르는 슬롯·코드·다른 슬롯 아이템 422 | RET-06 | 핵심(#389) |

- `eventType`: `MISSION_COMPLETED`·`REVIEW_VIEWED`·`COMMUNITY_POSTED`·`REACTION_GIVEN`·`THEME_COMPLETED`(개근)·`THEME_ON_TIME`(당일 풀이)·`THEME_FINISHED`(주간 완주)(적립), `UNLOCK`(사용, 음수)
- 2026-11-10 개정(#483, core #485 구현·V43): 적립 사건에 당일 풀이(`THEME_ON_TIME`, 5, 사건 키 `weekStart:day` 예 `2026-11-09:MON`)·주간 완주(`THEME_FINISHED`, 10, 사건 키 `weekStart`)를 더했다. `THEME_COMPLETED`(30)는 이름·키 그대로 개근(월~금 각 당일 학습 완료)으로 표시한다. 근거는 learning 주간 테마 조회 응답의 `days[].completedOnDay`·`completed`(개근)·`finished`(2.11). 개근은 주간 테마 조회 보충과 되돌아보기 열람 응답 `completed`로, 당일 풀이·주간 완주는 주간 테마 조회 보충으로만 적립하며 사건 키로 1회(3.4·3.6 시퀀스, #506). learning #484가 `completedOnDay`·`finished`를 내보내고 같은 PR에서 web 학생 포인트 화면의 "준비 중" 표시를 뺐다(#506). 학생·학부모 포인트 내역 화면은 세 사건 이름(당일 풀이·개근·주간 완주)을 보여 준다(web #487)
- 적립은 별도 API가 없다. core `RewardService.earn(studentId, event, sourceKey)` 한 곳에서 처리하고(#389 구현, 자체 트랜잭션·예외 없이 결과 반환), core가 learning 응답을 프록시하는 경로에서 부른다(#389 구현): 돌아보기 저장 성공(학습 완료·미션당 최초 1회, 미션은 core가 learning 시도 상세로 확인), 공유 생성 성공(이미 있는 공유물 200 포함), 반응 남기기 성공(하루 상한, 취소는 적립 없음), 되돌아보기 열람(주 1회), 열람 응답 `completed`면 개근, 주간 테마 조회 응답의 개근·당일 풀이·주간 완주 칸(#485). 사건 키는 학습 완료 `missionId`, 공유 `postId`, 반응 `postId:reaction`, 되돌아보기·개근·주간 완주 그 주 월요일(KST), 당일 풀이 `weekStart:day`. 값·상한은 `reward_rule` 데이터(P21 초기값). 원장 사건 키 `source_key`로 멱등, 학습 응답 후 적립 저장이 실패하면 응답은 그대로 두고 같은 사건 재요청(돌아보기 재요청 `409 ATTEMPT_CLOSED` 포함, 같은 반응·열람 재요청)·`/students/me/weekly-theme` 조회(이번 주 학습 완료한 요일 문제) 때 보충. 적립 결과는 응답에 넣지 않고 `/students/me/points`로 조회
- `itemKey`: 테마·캐릭터는 `THEME:forest`·`COMPANION:tori` 형식(해금값은 코드 상수), 아이템은 관리자가 등록한 `look_item.code`. `THEME:lake`·`COMPANION:mungchi`는 항상 해금, 나머지 테마 100·캐릭터 150 포인트(코드 상수). 잠금 적용 전 저장된 `look_theme`·`look_companion`은 마이그레이션에서 해금 행으로 옮긴다
- 2026-11-12 결정(P22 개정·P27, 설계·구현 전): 생활공간 가구 스킨은 슬롯 `DESK`·`WALL`·`WARDROBE`의 `look_item`으로 등록하고 위 목록·해금 API와 `PUT /students/me/preferences`의 `equipped`(슬롯 키 추가)를 그대로 쓴다. 가구별 기본 스킨은 항상 해금(기준안). 새 경로 없음
- 다른 학생 잔액·순위 API는 없다(1.3)

### 2.11 주간 테마·되돌아보기 (FN-RET-07·08, P23)

core 경로는 #387 구현·OpenAPI 반영(태그 `WeeklyTheme`, 시도 `AttemptStartRequest`). 테마 데이터·요일·되돌아보기 검사는 learning #385 구현(4.1, [learning OpenAPI](../../contracts/openapi/learning-service.yaml), [ERD 4.2.1](erd.md#421-주간-테마-p23-385-v11v12)).

| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/students/me/weekly-theme` | 학생 | 이번 주(KST 월요일 기준) 학년 테마 `{themeId, weekStart, title, intro, reused, days:[{day, missionId, title, thinkingType, state, attemptStatus}], review:{open, missions:[{missionId, title, completed, missed}]}, completed}`. `day`는 `MON`~`FRI`, `state`는 `LOCKED`·`OPEN`·`CLOSED`, `attemptStatus`는 `NOT_STARTED`·`IN_PROGRESS`·`COMPLETED`(이번 주 그 요일 문제 최근 시도). `intro`는 월요일에만 채움. `review.missions[].completed`는 이번 주 그 문제를 마무리함(다시 풀기 가능), `missed`는 지난 요일인데 마무리하지 않음. `completed`는 월~금 다섯 문제를 각 요일 안에 학습 완료(개근, 2026-11-10 개정 전 이름 "완주"). 그 학년에 게시 테마가 없으면 `404`. #439(에픽 #436): `outro`(종료 이야기)·`introImageUrl`·`outroImageUrl`(없으면 null, 미션 `sceneUri`처럼 learning 값을 core가 그대로 전달)·`introSeen`·`outroSeen`(이번 주 이야기 열람 여부) 추가, 수동 테마는 비어 있을 수 있음. 2026-11-10 개정(#483) 추가 칸(learning #484): `days[].completedOnDay`(그 요일 문제를 그 요일 KST 안에 학습 완료, 당일 풀이), `finished`(5문제를 그 주 테마 시도로 토요일 23:59:59까지 학습 완료, 일요일 완료 제외, 주간 완주), `ending`(`NOT_ENDED`·`ENDED`), 기존 `completed`는 개근 뜻으로 유지, `days[].state`·`review.missions[].missed`는 아래 개정 뜻. 엔딩 전에는 `outro`·정답을 비움. `intro`는 그 주 첫 진입 때 보이도록 요일과 무관하게 채움. 요일 단서 `days[].clue`·`rulesOut`은 그 문제를 그 주에 학습 완료한 뒤에만(#484) | RET-07, RET-08 | core #387·#439 → #485 |
| POST | `/students/me/weekly-theme/review-views` | 학생 | 토·일 되돌아보기 열람 기록(멱등, 주 1회) → `{firstViewThisWeek, completed}`. 평일은 `409 THEME_REVIEW_NOT_ALLOWED`. 열람 기록 후 포인트·개근 적립(#389). 2026-11-10 개정(#483): 토요일(프리미엄은 일요일도)만, 무료 일요일도 `409 THEME_REVIEW_NOT_ALLOWED`(learning #484). 열람 응답으로는 개근(`completed`)만 적립하고 주간 완주(`finished`)는 주간 테마 조회 보충으로 적립한다(core #485, 열람 응답에 `finished`가 있어도 읽지 않음, #506) | RET-08 | core #387 → #485 |
| POST | `/students/me/weekly-theme/story-views` | 학생 | 시작·종료 이야기 열람 기록 body `{kind}`(`INTRO`·`OUTRO`, 다른 값·필드는 core가 `400 VALIDATION_FAILED`). INTRO는 월요일·OUTRO는 토요일만 허용, 주 1회 멱등(learning #438 판정, 다른 요일 오류 코드는 learning 소유를 그대로 전달). 학년·KST 날짜는 core가 정함. 2026-11-10 개정(#483, learning #484): INTRO는 그 주 첫 진입(월~토, 프리미엄 일요일), OUTRO는 `ending = ENDED`일 때만(요일 무관, 무료 일요일 제외) | RET-07, RET-08 | core #439 |
| POST | `/students/me/weekly-theme/answer-picks` | 학생 | 큰 질문 정답 고르기 body `{pick}`(고른 후보 하나, 빈 값·문자열 아님·다른 필드는 core가 `400 VALIDATION_FAILED`). 학년·KST 날짜·`sundayTheme`은 core가 정해 learning `answer-picks`로 넘김. 응답 `{correct, ending(NOT_ENDED\|ENDED), answer(엔딩일 때만)}`. 후보 안의 값인지·고를 수 있는 때(아니면 `409 THEME_PICK_NOT_ALLOWED`)·정답 판정·엔딩 상태는 learning #484, core는 응답·오류 그대로 전달. 포인트 적립 없음 | RET-07, RET-08 | core #550 |
| POST | `/missions/{missionId}/attempts` | 학생 | 2.2 확장: body `{context}`(`THEME_DAY`·`THEME_REVIEW`·`EXTRA`, 생략·`null` 시 `EXTRA`, 다른 필드·값은 400) | RET-07, RET-08 | core #387 |

- 2026-11-10 개정(#483, 구현 learning #484·core #485, 화면 web #487)
  - `THEME_DAY`: 그 미션이 이번 주 테마에서 공개된(`OPEN`) 요일 문제면 월~토 언제든 신규 시도(금요일에는 5개 모두 공개). 공개 전 문제·일요일은 409 `THEME_DAY_CLOSED`, 프리미엄 일요일(기준안 `features.sundayTheme = true`, core가 판단해 learning에 전달)은 토요일과 같이 허용. 무료도 하루 한도 집계 없음
  - `THEME_REVIEW`: 토요일(프리미엄은 일요일도)에 그 주 마무리한 테마 문제만. 아니면 409 `THEME_REVIEW_NOT_ALLOWED`. 토요일에는 안 푼 문제를 `THEME_DAY`로 새로 시작할 수 있다
  - 큰 질문 정답 고르기(금요일 문제를 마무리한 뒤 한 주 한 번, #437·#484): 정답이면 `ending = ENDED`, 오답이면 고른 뒤 토요일(프리미엄 일요일) 금요일 문제 `THEME_REVIEW` 마무리 뒤 `ENDED`(다시 고르지 않음, 정답 공개). 고른 값은 learning `theme_answer_pick`, 엔딩은 저장하지 않고 계산(사용자 결정 2026-11-12)
  - `review.missions[].missed`는 "공개됐지만 아직 마무리하지 않음"으로 읽는다(토요일에는 새로 풀 수 있음, 일요일엔 표시만). 칸 이름은 core·report 호환을 위해 유지
  - `EXTRA`: 무료 상품 `features.extraMissions = false`로 바꿔 프리미엄 전용(무료 403 `PREMIUM_REQUIRED`)
  - 커뮤니티: 정답 고르기 문제 공유물은 그 문제로 고른 주에 `ENDED`인 학생만 열람(2.9, 문제를 마무리했지만 엔딩 전이면 `403 COMMUNITY_LOCKED_UNTIL_ENDING`, #484·#550)
  - 진행 중 시도 이어하기는 요일과 무관(일요일 포함). core 한도 집계 없음(#485). 다시 풀기는 #207 비교 규칙 그대로
- 이미 마무리한 문제의 새 `THEME_DAY` 시도는 409 `THEME_DAY_CLOSED`(#506·#484, 전에는 무료 하루 1개 429가 부수적으로 막았음). 마무리한 문제 다시 풀기는 `THEME_REVIEW`
- `EXTRA`: 생각 유형별 미션 고르기(2.2 `/missions`). 프리미엄 전용(2026-11-10 개정 #483, core #485 V43): 무료 403 `PREMIUM_REQUIRED`, 프리미엄 신규 시도는 `EXTRA_MISSION` 사용 기록. 상품 `features.extraMissions`로 정하며 값이 없으면 무료 거부·구독 중 허용(#506). 무료 상품에서 `true`로 다시 켜면 무료 `EXTRA`만 하루 `limits.dailyMissions`개(2.2). 2026-11-08 결정(무료도 허용·하루 1개 합산)은 개정으로 대체. 전환 방법은 [core 보고서 13절](../report/core-gateway.md#13-주간-테마-프록시무료-하루-1개추가-문제-프리미엄-387)·18절
- 무료 `EXTRA`를 다시 켰을 때의 하루 한도는 #210 결정대로 core `mission_daily_usage` 집계(2.2). 테마 학년(`G3`~`G6`, 중학생은 `G6` P26 #432, 학년별 테마 에픽 #436)과 KST 날짜는 core가 정해 learning에 넘긴다(클라이언트 값 미사용). 응답은 `Cache-Control: no-store`
- 진행 중인 시도의 이어하기(`200`)는 요일 검사를 하지 않는다. 재사용 테마의 이미 푼 문제도 그 주 `OPEN` 요일에는 `THEME_DAY` 신규 시도 가능(그 주에 마무리한 시도만 기준, core 한도 집계 없음)
- 에픽 #436(learning #438) 주간 테마 응답 추가 칸: 큰 질문 `bigQuestion`·후보 `candidates`·요일 `days[].clue`·`rulesOut`, 시작·종료 장면 영상 `introVideoUrl`·`outroVideoUrl`과 움직임 `introMotion`·`outroMotion`, 엔딩 뒤 정답 `answer`·`answerClue`. 요일 장면 영상은 없다(ai 채택 테마의 미션 `themeScene.videoUrl`은 null). core는 응답을 그대로 전달하고 포인트 적립에 `weekStart`·`completed`·`finished`·`days[].missionId`·`attemptStatus`·`day`·`completedOnDay`만 읽는다. 정답·종료 이야기는 learning이 엔딩 전에 비운다

### 2.12 생활공간·추억 (FN-RET-09~13, P27)

**구현 전 계약(기준안)**. 2026-11-12 리텐션 확장 결정([결정 기록](../report/retention-expansion.md)). 경로·칸 이름은 구현 이슈에서 OpenAPI와 함께 확정한다. 저장은 [ERD 3.5.2·4.6](erd.md). 회차 키는 `themeId`·`weekStart`(KST 월요일), 학생은 세션으로 정한다.

| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/students/me/room/frame-slots` | 학생 | 추억의 벽 슬롯 `{slots:[{slotNo, themeId, weekStart, title, imageUrl}]}`(빈 슬롯 제외). 방 벽지·가구 스킨·캐릭터 착용은 기존 2.10·3.12 응답 사용 | RET-09 | 설계 |
| PUT | `/students/me/room/frame-slots` | 학생 | 전체 교체 `{slots:[{slotNo, themeId, weekStart}]}` → 저장된 목록. `slotNo` 1~6·중복 슬롯·같은 액자 중복 422 `VALIDATION_FAILED`, 미보유 회차 404 `THEME_FRAME_NOT_FOUND` | RET-09 | 설계 |
| GET | `/students/me/album?page&size` | 학생 | 보유 액자 회차(진행 중인 주·`EXTRA` 제외, 최근 회차순) `{items:[{themeId, weekStart, title, imageUrl, awardedAt, seen, displayed}], page, size, totalElements}` | RET-10, RET-11 | 설계 |
| GET | `/students/me/album/{themeId}/{weekStart}` | 학생 | 회차 상세 `{themeId, weekStart, title, awardedAt, missions:[{day, missionId, title, thinkingType, attemptId}], ending:{seen, outro, answer}}`. 엔딩을 보지 않았으면 `outro`·`answer` null(P23). 문제별 기록은 기존 시도 상세(2.3·`/attempts/{id}/comparison`)로 연다. 미보유 404 `THEME_FRAME_NOT_FOUND` | RET-11 | 설계 |
| POST | `/students/me/album/{themeId}/{weekStart}/seen` | 학생 | 새 액자 확인(멱등) → 204. 미보유 404 `THEME_FRAME_NOT_FOUND` | RET-10 | 설계 |
| POST | `/students/me/memories/search` | 학생 | body `{query}`(1~200자) → `{state, cards:[{themeId, weekStart, title, imageUrl, missions:[{missionId, title, attemptId, answerExcerpt}], score}]}`. `state`는 `RESULTS`·`NO_RESULTS`(관련도 기준 미달)·`NO_RECORDS`(보유 액자 없음), 카드 최대 3개(기준안). 하루 한도 429 `USAGE_LIMIT_REACHED`, 임베딩 장애 503 `AI_UNAVAILABLE`, 형식 오류 400 `VALIDATION_FAILED`(사용량 미기록) | RET-12 | core 구현 #566(learning #563 대기) |
| POST | `/students/me/memories/explanations` | 학생 | body `{query, attemptIds}`(검색 결과 카드의 시도, 1~3개) → 200 `{state, text, citations:[{no, themeId, weekStart, attemptId}]}`. `state`는 `GENERATED`·`INSUFFICIENT`(근거 부족, 생성 안 함)·`FAILED`(생성·검사 실패, `text` null). 본인 검색 문서가 아닌 `attemptId`는 422 `VALIDATION_FAILED`, 하루 한도 429 `USAGE_LIMIT_REACHED`. 빈 배열·4개 이상·중복·UUID 아님은 core 400 `VALIDATION_FAILED`(사용량 미기록) | RET-13 | core 구현 #566(learning #564 대기) |

- core는 검색·설명 요청마다 `memory_daily_usage`에 기록하고 KST 하루 건수가 상품 한도를 넘으면 롤백한 뒤 learning을 부르지 않고 429(ERD 3.4, #566). 무료·프리미엄 같은 값 20·10(2026-11-12 확정, P13). 키가 없는 기존 구독 스냅숏은 무료 상품 값을 쓴다
- learning 5xx·시간 초과·연결 실패·서킷 차단이면 기록을 되돌린다(장애가 한도를 깎지 않음). 4xx와 설명 `FAILED`·`INSUFFICIENT`(200)는 센다
- core → learning은 4.1.4 경로를 프록시하고 본문은 core가 모양을 확인해 다시 만든 뒤 넘기며 응답·오류를 그대로 전달(`Cache-Control: no-store`). 검색·설명 모두 별도 회로 `learning-memory`(검색 응답 30초·설명 45초, 아키텍처 1.3). ai 장애로 생긴 learning 5xx가 일반 `learning-json`을 열지 않게 하려고 검색도 이 회로를 쓴다(2026-11-12 결정)
- 검색 반영은 학습 완료 뒤 비동기라 방금 완료한 문제는 잠시 결과에 없을 수 있다(앨범에는 바로 보임). 질문·설명은 저장하지 않는다
- 학생 이외 역할 경로 없음(학부모 화면 미제공)

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
    "judgmentId":"j-7", "result":"PARTIAL", "trial":true,
    "elements":[
      {"elementId":"e1","label":"주장","code":"EVALUATE_CLAIM","goodThought":false,"satisfied":true,"quote":"나는 ...라고 생각해","sourceType":"AI_OBSERVATION"},
      {"elementId":"e2","label":"까닭","code":"EVALUATE_EVIDENCE","goodThought":false,"satisfied":false,"quote":null}
    ],
    "heldReason":null
  },
  "followup":{"followupId":"f-32","type":"TELL_MORE","question":"왜 그렇게 생각했는지 하나 더 말해 볼까?","source":"LLM"},
  "nextActions":["ANSWER_FOLLOWUP","FINISH"],
  "versions":{"mission":"m-12@3","rubric":"r-12@2","model":"gpt-6.1-terra","prompt":"judge@2"}
}

event: done
data: {}
```
- `judgment.judgmentId`: 이 판정의 ID. 신고(`targetType: JUDGMENT`)·정정 대상으로 씀, 판정 전(`judgment: null`)이면 판정 신고 없음 (#146)
- 보류인 경우: `judgment.result: "HELD"`, `heldReason`(`INSUFFICIENT_EVIDENCE`·`QUOTE_MISMATCH`·`TOO_SHORT`·`UNVERIFIED_SCOPE`, M2 교차 확인(`M2_CROSS_CHECK_ENABLED=true`)이면 `MODEL_DISAGREEMENT`, M1 점검(`M1_CHECK_ENABLED=true`, 모델 활성 시)이면 `LOW_CONFIDENCE` 추가. 둘 다 기본 꺼짐(#69, 4.2.2))
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
  "evidence":[{"kind":"ANSWER","attemptId":"t-7","missionTitle":"...","answerId":"a-102","answerVersion":2,"quote":"...","available":true}],
  "verification":{"numbersMatched":true,"quotesMatched":true},
  "recordCount":5
}

event: done
data: {}
```
- 범위가 불명확한 경우
  - `event: clarification`을 보내고 스트림 종료
  - 사용자 선택을 `scope`에 담아 다시 질문
- `delta`: ai가 LLM 답변 조각을 대조 전에 그대로 보냄. 확정 답변은 대조를 통과한 `result.answer`뿐이며 이어 붙인 delta와 앞뒤 공백만 다를 수 있음
- `evidence`: 답변 본문의 큰따옴표 인용을 원문과 대조해 ai가 연결. 같은 원문은 근거 하나. 돌아보기 근거(`kind: REFLECTION`)는 `attemptId`로 식별하며 core 재조회는 `/internal/records/students/{studentId}/attempts/{attemptId}`의 `reflection`
- 대조 실패·LLM 장애: 규칙 응답 모드 (P16)
  - `delta`로 보낸 임시 텍스트는 폐기 (첫 조각 뒤 LLM 실패도 재시도 없이 규칙 응답)
  - `event: result`에 계산된 `metrics`·`evidence`만 템플릿 문장으로 담고 `"source":"TEMPLATE"`, `"fallback":{"reason":"VERIFICATION_FAILED|AI_UNAVAILABLE"}` 표시
  - 기록 조회 자체가 실패하면 `event: error`

### 3.4 리포트 상세 — `GET /reports/{reportId}`
```jsonc
{
  "reportId": "r-44", "childId": "s-1", "status": "COMPLETED", "state": "OK",
  "period": { "from": "2026-11-02", "to": "2026-11-08" },
  "correctionNotice": false, // 이 판에 쓰인 판정 중 일부가 만들어진 뒤 정정됨 (5.7, #244)
  "revision": 1, "revisions": [{ "revision": 1, "generatedAt": "2026-11-09T00:00:00+09:00" }],
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
  "versions": { "prompt": "report@1", "model": null },
  "generatedAt": "2026-11-09T00:00:00+09:00"
}
```

- 리포트 상세의 `metrics`는 기록 지표 3개(답변 제출 시도 수·완료한 시도 수·도움 없이 시작한 비율) 뒤에 판정이 있는 기간에만 생각 요소 지표(FN-RPT-05)를 같은 `Metric` 모양으로 붙인다: 처음 답에서 확인된 생각 요소(전체·유형별), 되묻기 후 새로 확인된 생각 요소, 따져 보기 논술 논증 요소, 들어가면 좋은 생각, 표준 요소별 출현. 출처는 `AI_OBSERVATION`이고 시범 판정이 섞이면 `formula`에 표시한다(#344). 판정이 없거나 모두 처리 중·실패·보류면 기록 지표 3개만 있다.

- 리포트 상세의 `reflections[].difficulty`는 표시값 `쉬웠어요`·`보통`·`어려웠어요`이며 PDF·HTML·Markdown도 같은 표시값을 쓴다. learning 입력과 report 내부 저장의 `EASY`·`NORMAL`·`HARD` 코드는 출력 조립 시 변환한다. 미작성·기간 밖이면 `written:false`, `difficulty:null`, `text:null`이다. 선택 텍스트 없이 난이도만 작성한 기록은 `written:true`, `text:null`로 구분한다.

- 리포트 상세의 `changes[].followup`은 문자열 또는 null이다. 학습 기록 API 4.1.1에서 되묻기 없이 제출한 보완 답변도 비교하므로, 질문이 없는 경우 null을 그대로 반환하고 최초/최종 답변 및 계산 수치는 유지한다. 저장된 결과를 임의 질문이나 빈 기록으로 대체하지 않는다.

- 리포트 상세의 `explanations`(FN-RPT-09, #479): 주간 리포트만 `{state, items[]}`를 반환하고 일일 리포트·무료 플랜은 `null`이다(무료 전환 뒤 과거 리포트도 `narrative`처럼 null, P13). `state`는 `INCLUDED`(설명 1개 이상)·`NOT_INCLUDED`(대상 답변이 있으나 생성 실패·검사 실패·시간 초과·설명 모델 미활성, P16)·`NO_TARGET`(M2 점수가 있는 답변 없음 또는 원문 비공개, FN-RPT-07)이다. `items[]`는 대표 답변 최대 3개(생각 유형이 겹치지 않게, 같으면 최근 답변)의 `{attemptId, answerId, answerVersion, missionTitle, thinkingType, quote, text}`이며 "AI 관찰"로 표시한다. 점수·등급·숫자는 넣지 않는다. 저장은 report_db `report_item.item_type = EXPLANATION`(근거 `report_item_evidence`, 검사 통과분만)이고 설명이 빠져도 리포트 `status`·`state`는 바뀌지 않는다. 기존 `narrative.modelExplanation`은 계약 유지를 위해 항상 null이다. PDF·HTML·Markdown도 같은 항목·상태를 표시한다.

### 3.5 결제 승인 — `POST /payments/confirm`

learning 최소 연동(#48): `GET /internal/payment-usage/students/{studentId}?since=<date-time>`는 SYSTEM+정확한 학생 scope에서 `{studentId,since,used}`를 반환한다. DONE 피드백의 completed_at 또는 진행 중 피드백을 확인하며 원문을 반환하지 않는다. learning 공개 피드백 경로는 실행 전에 core `POST /internal/payment-usage/reservations {studentId,sourceId}`를 호출하고 DONE 저장 후 `POST /internal/payment-usage/completions {studentId,reservationId,used:true}`를 호출한다. 두 core 경로는 내부 토큰과 STUDENT+본인 scope가 필요하다. 예약 응답은 `{reservationId:uuid|null,premium:boolean}`이며 미완료 예약은 환불 증빙 불명확으로 남긴다. core 409는 Problem Details `code`로 구분해 learning이 같은 코드로 전달한다(1.3, #276). 새 외부 서비스나 dependency 없이 기존 내부 HTTP를 사용한다.

#48 세부 DTO·복구·내부 권한 계약은 core OpenAPI와 [결제 구현 보고서](../report/core-gateway.md#24-결제구독과-상품-권한-48184419)를 따른다. 무료 상품은 명시적 PAYMENT_FREE_PRODUCT_ID로 선택하고, 승인 응답·웹훅은 PG 주문/금액/MID/상태를 대조한다. 환불 승인과 조회 권한은 각각 PAYMENT_REFUND/PAYMENT_VIEW이며 `/admin/refund-requests` GET도 PAYMENT_VIEW다. 모든 결제 쓰기는 parent 계정 잠금에 참여하되 외부 PG/learning 호출은 트랜잭션 밖이다. 불명확한 승인·취소를 실패로 바꾸지 않고 조회 복구한다. 최초 결제 후 빌링키가 등록되기 전에는 autoRenew=false, nextBillingDate=null이다.

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

### 3.7 웹 목업 규칙

웹 MSW 목업 개발 규칙은 [웹 프론트 보고서](../report/frontend.md) 1장. 확정 계약은 5장·core OpenAPI가 기준이다.

- `GET /children`은 5.3·core OpenAPI 기준이며 실제 식별자는 `id`. 목업의 `childId`·`plan`은 계약이 아님(core는 `plan`을 만들지 않음)

### 3.8 학생 답변 입력 형식

- 입력 방식별 제출(learning 구현): `CHOICE`는 `choiceIds` 1개, `ORDERING`은 모든 `choiceIds`를 중복 없이 순서대로, `SOLUTION_STEPS`는 `{finalAnswer, steps[]}`(최종 답과 비어 있지 않은 단계 1개 이상, 단위는 `answerUnit`으로 칸 뒤에 고정·비교 안 함, #79), `CLASSIFICATION`은 `{assignments:[{choiceId, categoryId}]}`(모든 choice를 한 그룹에 정확히 배정, 미정·중복은 422). 공통으로 `dictatedByGuardian`, 보완 시 `followupId`. 메모는 제출하지 않음
- 미션 상세 필드는 `{id,title,subject,grade,gradeMax,thinkingType,inputType,question,hint,sceneUri,staticSceneUri,choices,inputTemplate,categories,answerUnit}`(`scene` 미제공)
- 마무리 후에만 `reveal`·`revealKind`·`checklist`(3.2 Element). 체크는 `satisfied`와 원문 인용이 모두 있는 요소만 표시

### 3.9 학부모 화면 응답

대화·근거·학습 요약·생각 유형 응답 모양은 1.6 공통 스키마, 3.3, 4.1과 core OpenAPI. 삭제된 근거는 `available:false`(410도 이용 불가 표시)이며 quote를 재사용하지 않는다.

### 3.10 관리자 화면 응답

운영 현황·작업·큐·감사 응답은 2.8.1과 core OpenAPI, 미션 관리 계약은 4.1 관리자 미션 행. 학생 이름·답변 원문·메모는 운영 DTO에 넣지 않으며 관리자 API는 `/me.permissions`로 검사한다(운영 현황·감사 로그 조회만 ADMIN 역할, 2.8.1).

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
  - 추가 재인증 없음(활성 보호자 세션·현재 자녀 권한만, 2026-11-10). 숫자 4~6자리, 동일 숫자 반복(`1111`)·연속(`1234`, `4321`) 거부 `422 VALIDATION_FAILED`
  - 해시 저장, 실패 횟수 0·잠금 해제. 잠긴 PIN의 해제 수단은 재설정뿐
- 기기 해제 `DELETE /student-devices/{deviceId}`: `revoked_at` 기록, 기존 학생 access token은 만료까지 유효
- 학부모 화면의 실제 PIN 상태: `GET /children` 각 항목에 `pinSet`(설정 여부)·`pinLocked`(5회 실패 잠금 여부)를 반환한다. PIN 원문·해시·실패 횟수는 반환하지 않음
- 기기 등록·해제·PIN 설정은 `audit_log` 기록 (FN-ACC-10). PIN 잠금 시 학부모 알림은 미정
- 응답 형식: 프로필 `{items:[{childId,nickname,pinSet,pinLocked}]}`, 기기 목록 `{items:[{deviceId,label,children:[{childId,nickname}],createdAt,lastUsedAt,expiresAt}]}`(해제 기기 제외). PIN 설정·변경은 204(잠금 해제 포함), 별도 해제 API 없음
- PIN 변경은 활성 보호자 세션·현재 자녀 권한으로 처리하며 추가 재인증 grant를 요구하지 않는다(2026-11-10 사용자 요청). 해시 변경·잠금 해제·감사는 같은 트랜잭션이다.
- 한도: 등록은 IP별, 페어링 발급은 보호자별 10분간 20회(설정 가능). 초과 429 `RATE_LIMITED`, Redis 장애 503 `STUDENT_AUTH_UNAVAILABLE`. IP는 직전 연결이 사설 대역(신뢰 프록시)일 때만 X-Forwarded-For를 오른쪽부터 해석한 첫 비신뢰 주소로 판정 (운영 조건 [아키텍처](architecture.md) 4.3)
- 코드 소비는 Redis 원자적 GET+DEL. 이후 DB 등록이 실패해도 코드는 복원하지 않음(새 코드 발급)
- 기기·학생 검사는 계정 행 잠금과 함께 재검사. PIN 실패는 커밋 후 오류 응답
- 등록·프로필·로그인 응답은 `Cache-Control: no-store`. PIN 로그인은 refresh 쿠키를 발급하거나 보호자 세션을 바꾸지 않음

### 3.12 학생 화면 꾸미기 설정 (core 구현, #234)

학생이 고른 생각 지도 테마와 동행 캐릭터를 기기와 관계없이 유지하기 위한 학생 본인 설정이다. 학습 기록·판정·리포트에 쓰지 않으며 학부모 화면에 노출하지 않는다. 대응 FN 항목이 없는 화면 개선이며, 요구사항 ID를 새로 만들지 않고 기능 명세에는 추가하지 않았다(필요하면 기획에서 FN을 정한 뒤 연결).

| Method | Path | 역할 | 설명 |
|---|---|---|---|
| GET | `/students/me/preferences` | 학생 | 현재 설정. 저장한 적 없으면 기본값과 `updatedAt:null` |
| PUT | `/students/me/preferences` | 학생 | 설정 전체 교체 `{theme, companion, equipped?}`(#389, 아래) |

```jsonc
// GET 200 / PUT 200
{ "theme": "lake", "companion": "mungchi", "updatedAt": "2026-10-27T05:00:00Z" }
```
- `theme`: `lake`(호수)·`forest`(숲)·`factory`(공장)·`space`(소행성)·`sea`(바닷속). 기본 `lake`
- `companion`: `mungchi`(뭉치)·`tori`(토리)·`mongdol`(몽돌)·`kongi`(콩이)·`monggeul`(몽글). 기본 `mungchi`
- 목록에 없는 값·누락·null은 `422 VALIDATION_FAILED`(이전 설정 유지). 학생 토큰 전용, 학부모·관리자 토큰은 `403 FORBIDDEN`. 응답 `Cache-Control: no-store`
- P22(#389): `lake`·`mungchi` 외 테마·캐릭터는 포인트로 해금한 것만 저장(잠긴 값 `409 LOOK_LOCKED`, 이전 설정 유지), 잠금 적용 전 저장된 값은 V35가 해금된 것으로 이관했다. 숫자 레벨·순위와 무관한 참여 보상이라 기능 명세 1.3 원칙과 충돌하지 않음
- 저장: core `student.look_theme`·`look_companion`·`look_updated_at`(V23, 세 열 함께 NULL 또는 함께 값). 값 목록은 코드 상수와 DB CHECK로 고정한다. 학생 삭제 확정 시 기본값(NULL)으로 되돌린다. OpenAPI `StudentLook`
- P22(#389): PUT `{theme, companion, equipped?:{HAT, OUTFIT, ACCESSORY, BACKGROUND}}`(슬롯별 아이템 `itemKey` 또는 null, 해금한 아이템만, 생략·null이면 착용 유지). GET·PUT 응답은 항상 네 슬롯의 `equipped`를 담는다. 판매 중단 아이템도 해금했으면 착용 가능. 학생 삭제 확정 때 해금·착용·포인트도 지운다. 해금은 2.10

### 3.13 지원·알림·계정 화면 연결

- 도움말·공지·신고·문의·관리자 공지는 2.7·2.8·5.7과 core OpenAPI(`SupportReport`·`SupportInquiry`·`SupportNoticePage`). 같은 신고 내용 재전송은 같은 `Idempotency-Key`
- 알림은 2.7(학생 요청 없음, 학부모·관리자 로그인 중 `/notifications/stream` 1개), 계정·삭제·탈퇴는 5.6. 탈퇴 사전 확인 `GET /me/withdrawal/precheck`는 `{canWithdraw,activeSubscriptions,unresolvedRefunds,retainedTransactionsYears,pendingPayments}`(`pendingPayments`는 승인 확인 중·권한 복구 필요 결제 수, #48)
- API 모드 실패를 시연 응답으로 대체하지 않으며 점검표 `/review`·가상 계정 진입은 DEV+MSW에서만

## 4. 내부 API (`/internal`)
- 인증: `X-Internal-Token` + 사용자 컨텍스트 헤더 `X-User-Id`, `X-User-Role`, `X-Student-Scope`(허용 학생 ID, 콤마 구분), `traceparent`
  - ai는 받은 컨텍스트 헤더를 learning 호출에 그대로 전달
  - 사용자 요청 없는 호출(report-worker): `X-User-Role: SYSTEM`, `X-Student-Scope` = 이벤트 `subject` 학생
- 외부에 노출하지 않음. NetworkPolicy로 호출 관계만 허용
- 범위 밖 학생 요청은 403

### 4.0 core 학생 별명 조회 (#119, 호출: report-worker)

`GET /internal/students/{studentId}/profile` → `200 {studentId, nickname, parentSharingEnabled, grade}`. core OpenAPI의 이 operation은 `servers: /`로 공개 API prefix와 구분한다. 응답은 `Cache-Control: no-store`이며 이 네 필드만 제공한다(`parentSharingEnabled`는 학생 공유 설정, #206).

실제 `InternalAuthFilter`가 내부 토큰을 검사한 뒤 guardianship Controller → Application Service → 기존 `ChildManagementRepository.profile`을 호출한다. Service는 `SYSTEM` 역할과 대상 학생의 `X-Student-Scope` 포함 여부를 DB 조회 전에 확인한다. 학부모 Bearer만으로 호출할 수 없다.

2026-10-29 사용자 확정: 잘못된 UUID는 `400 VALIDATION_FAILED`, 토큰 누락·불일치는 `401 UNAUTHENTICATED`, 역할 누락·SYSTEM 외 역할·scope 누락/불일치는 `403 FORBIDDEN`, 미존재·ACTIVE 외 상태(DELETION_REQUESTED·DELETED 포함)는 `404 NOT_FOUND`. DB 등 예상하지 못한 조회 실패는 기존 `500 INTERNAL_ERROR` Problem Details로 반환한다. 현재 student CHECK의 상태는 ACTIVE·DELETION_REQUESTED·DELETED이며 별도 INACTIVE 상태를 추가하지 않는다. 기존 SQL·스키마·공개 API는 유지한다.

report 연결은 별도 담당 범위다. 조회한 nickname을 생성 명령의 내부 `display_name`으로 보관해 제목에 사용하고, NarrativeGenerator에서 AI 요청 전에 가린다. `report.generate.v1`에 별명을 추가하지 않는다. 403·404를 가짜 별명·기록 없음으로 처리하지 않고 생성 실패로 취급한다. 통신 장애는 기존 작업 실패/재시도 경계를 따르며 서비스 간 HTTP 재시도를 추가하지 않는다. 실제 worker 연결·최종 AI payload 검증은 [#119 보고서](../report/core-gateway.md#8-리포트용-학생-별명-내부-조회-119)의 후속 조건을 따른다.

### 4.1 learning-service (호출: core, ai, report)

구현된 경로의 요청·응답 계약: [contracts/openapi/learning-service.yaml](../../contracts/openapi/learning-service.yaml) (`scripts/tests/test_record_exists_openapi.py`가 컨트롤러 경로와 대조)

| Method | Path | 호출자 | 설명 |
|---|---|---|---|
| GET | `/internal/missions?grade&demo&page&size`, `/internal/missions/{id}?grade&demo` | core | 학생용 미션 조회 (2.2 프록시). core가 학생 학년 `grade`(3~6, 필수. 저장 학년 7~9인 중학생은 중학교 과정 확장 전까지 6으로 맞춤, P26 #432)와 시연 학생 여부 `demo`(`student.is_demo`, 기본 `false`)를 붙임. `demo_only` 미션은 `demo=true`일 때만 노출. 미션에 분류 그룹 `categories`·수학 답 단위 `answerUnit` 포함(3.8, #79) |
| POST | `/internal/missions/{id}/attempts?grade&demo&sundayTheme` | core | 시도 시작·이어하기 (2.2와 1:1). 조회와 동일하게 core가 인증된 학생의 `grade`(필수, 3~6)와 `demo`(`student.is_demo`, 기본값 `false`)를 전달함. 공개 요청의 `grade`·`demo` 값은 사용하지 않음. 진행 중인 시도가 있으면 미션의 공개 여부나 제공 범위와 관계없이 해당 시도를 반환(`200`)하고, 신규 시도는 `201`을 반환함. core는 응답 상태를 그대로 전달하며, 신규 시도의 제공 범위 검사와 기존 시도의 시작 당시 버전 유지는 learning이 담당함. #387: core가 body `{context}`를 그대로 넘기고(요일·되돌아보기 검사는 learning #385), 무료 상품에서 `EXTRA`를 다시 켠 경우의 무료 `EXTRA` `201`만 core `mission_daily_usage`에 집계(2.2, core #485). #485: `sundayTheme`(`true`·`false`, core가 항상 붙임)은 KST 일요일이고 상품이 일요일 테마를 허용할 때만 `true`([core 보고서 18절](../report/core-gateway.md#18-무료-테마-주-5문제추가-문제-프리미엄-전용프리미엄-일요일당일-풀이주간-완주-포인트-485-2026-11-10)), learning은 `true`일 때만 일요일을 토요일과 같이 연다(#484) |
| POST · GET · PUT | `/internal/attempts/...` | core | 시도·초안·도움·답변·마무리·돌아보기·자기 평가 (2.2 경로와 1:1). 생각 열기 응답 형식은 `{question, seq, total}`이며, 질문이 없는 미션은 `404`를 반환함. 시도 상세 `answers[]`는 `{answerId, version, submittedAt, inputType, text(입력 틀 칸 이름을 붙인 원문), followupId, content, feedback}`, `feedback`은 아래 피드백 결과와 같은 모양(판정 전이면 `{status, judgment:null, followup:null, nextActions:[], versions:null}`), 시도 `nextActions`는 마지막 답변의 `nextActions`. 시도 상세의 `reveal`·`revealKind`·`checklist`는 마무리 뒤에만, `reflection{difficulty, text}`는 돌아보기 뒤에만(그 전에는 `null`). 마무리 `finish` → `200 {attemptId, finishedAt, reveal(시도 기준표 버전의 예시 답, 닫힌 문제는 정답과 해설), revealKind(고르기·순서·분류·풀이 단계 `ANSWER`, 서술·논술 `EXAMPLE`), checklist(기준표 요소 전체 3.2 `Element[]`, 이 시도의 처리 완료 판정 중 원문 구절과 함께 충족된 요소만 체크·가장 최근 구절)}`, 판정 `DONE` 1회 미만이면 `409 REVEAL_CONDITION_UNMET`, 다시 요청하면 기록하지 않고 같은 결과. 돌아보기 `reflection` `{difficulty(EASY·NORMAL·HARD, 필수), text(선택, 빈 글은 null)}` → `200 {attemptId, status:"COMPLETED", reflection}`(완료 시점은 시도 상세·기록 조회), 난이도 없음·값 밖 `400`, 마무리 전 `409 REVEAL_CONDITION_UNMET`, 완료 뒤 `409 ATTEMPT_CLOSED`. 자기 평가 `self-assessment` `{checks:[{elementId, checked}]}` → `200 [{elementId, label, selfChecked(체크 안 한 요소는 null), aiChecked, quote}]`(기준표 요소 전체), 마무리 전 `409 REVEAL_CONDITION_UNMET`, 완료 뒤 `409 ATTEMPT_CLOSED`, 비었거나 같은 요소 두 번·기준표 밖 요소 `400`, 다시 보내면 `checked`만 바꿈 |
| POST | `/internal/attempts/{id}/answers` | core | 답변 제출 (3.1·3.8 형식). `Idempotency-Key`(UUID) 필수, 없거나 형식 오류면 `400`. 같은 키·같은 본문은 처음 답변을 `201`로 다시, 다른 본문은 `422 IDEMPOTENCY_KEY_REUSED`. 미션 입력 방식과 다르면 `400`, 누락은 `422 ANSWER_INCOMPLETE`, 서술·풀이·논술 글에 욕설·비속어·성적·혐오·위협 표현이나 연락처(전화번호·이메일)가 있으면 `422 ANSWER_INAPPROPRIATE`(누락 검사 다음·되묻기 연결 검사 전, 저장·판정 없이 차단. `detail`은 범주별 고정 문구로 표현은 "고운 말로 바꿔서 다시 적어 주세요.", 연락처는 "전화번호나 이메일 같은 개인정보는 빼고 다시 적어 주세요."이고 걸린 단어·원문은 넣지 않음. 혐오 표현과 `새끼`처럼 뜻이 둘인 말은 미션 본문에 나온 말이면 허용, #205), 마무리·완료한 시도는 `409 ATTEMPT_CLOSED`. 보완 답변은 가장 최근 미답 되묻기의 `followupId` 필수(아니면 `422 ANSWER_INCOMPLETE`). 저장하면 같은 트랜잭션에서 초안 `content.answer`를 비우고 `memo`는 유지, 초안 `version` +1 |
| POST | `/internal/answers/{answerId}/feedback` | core | 판정 오케스트레이션: 규칙 판정 또는 ai 호출 → 저장 → 결과 반환 (동기). `200` 결과는 3.2 `result`와 같은 `{status, judgment{judgmentId, result, trial, elements[{elementId(rubric_element.id), label, satisfied, quote, sourceType}], heldReason}, followup{followupId, type, question, source}, nextActions, versions{mission, rubric, model, prompt}}`, `versions.mission`·`rubric`은 `미션 code@버전`, 규칙 판정이면 `model`·`prompt` 없음. 다른 요청이 처리 중이면(그사이 다른 요청이 실패한 경우도 포함, 다시 요청하면 실행) `200 {status:"RUNNING", judgment:null, followup:null, nextActions:[], versions:null}`. ai·LLM 실패·타임아웃·서킷 차단은 판정 `FAILED` 후 `503 AI_UNAVAILABLE` + `retryable`(ai가 false로 준 오류·ai 4xx·계약 밖 응답은 false), 그 밖의 예상 못 한 오류는 판정 `FAILED` 후 `500`. 허용 안 되는 판정 전이는 `409 JUDGMENT_STATE_CONFLICT`(learning 내부 방어 코드: 처리 중이 아닌 판정을 끝내거나 실패로 기록하려 함, state-diagram 1.3. 획득한 리스로만 저장해 정상 흐름에서는 없어 1.3 공통 오류 표에는 넣지 않음). `nextActions`는 지금 할 수 있는 행동: 이 판정의 되묻기에 아직 답하지 않았으면 `[ANSWER_FOLLOWUP, FINISH]`, 되묻기가 없으면 `[FINISH]`, 마무리·완료한 시도는 `[]` |
| POST | `/internal/judgments/{judgmentId}/corrections` | core | 신고 정정 반영(SUP-03, #80). `X-User-Role: ADMIN`, `X-Student-Scope`에 판정 학생 정확히 1명, `X-User-Id`(UUID, 정정한 관리자 = `corrected_by`) 필수. 요청 `{reportId(UUID), reason(1자 이상), corrected(CORRECT·PARTIAL·RETHINK·HELD)}` + `Idempotency-Key`(UUID, core가 저장한 정정 ID). 기존 판정·요소·답변은 그대로 두고 `judgment_correction` 행 추가. `200 {correctionId, previousResult(정정 직전에 보이던 결과, 앞선 정정이 있으면 그 결과), corrected, createdAt, impact{conversation, aggregation, report}}`(값은 `APPLIED`·`NOT_APPLIED`·`UNKNOWN`, 5.7.1. `AFFECTED`·`NOT_AFFECTED`는 core가 채우며 learning은 보내지 않음). 같은 키·같은 요청(판정·본문)은 처음 응답 전체를 다시 `200`, 다른 요청이면 `422 IDEMPOTENCY_KEY_REUSED`. 같은 `reportId` 정정이 다른 키로 이미 있으면 `409 CORRECTION_REPORT_CONFLICT`, 판정이 `DONE` 전이면 `409 JUDGMENT_STATE_CONFLICT`, 판정 없음 `404`, 역할·학생 범위 위반 `403`, 헤더·본문 형식 오류 `400`(409·422 코드는 learning 내부용, 공개 오류는 core #46이 바꿔 정함). 이후 피드백 결과·시도 상세·기록(#27)의 `judgment.result`는 최신 정정 결과(정정이 있으면 `heldReason: null`), 판정 요소·되묻기·`nextActions`는 원판정 그대로. `impact.aggregation`은 learning 수치 집계가 판정 결과를 쓰지 않아 `NOT_APPLIED`(변경 대상 없음), `conversation`·`report`는 learning이 확인할 수 없어 `UNKNOWN` (core #46 계약 `support-learning-required.yaml`) |
| GET | `/internal/support/targets/{targetType}/{targetId}` | core | 신고·문의 대상 확인(#46 접수·정정 전 확인, #146). `targetType` JUDGMENT·FOLLOWUP·ATTEMPT. `X-User-Role` STUDENT·PARENT·ADMIN(ADMIN은 `X-Student-Scope`에 학생 정확히 1명), `X-User-Id`(UUID) 필수. `200 {studentId, attemptId, judgmentId?, previousResult?}`: JUDGMENT는 `judgmentId`·`previousResult`(지금 보이는 결과, 최신 정정 반영, 판정 `DONE` 전이면 없음), FOLLOWUP은 되묻기를 만든 판정의 `judgmentId`, ATTEMPT는 둘 다 없음(없는 칸은 생략). 원문 없음. 대상 없음 `404`, 대상 학생이 범위 밖·역할 위반 `403`, `X-User-Id` 누락·형식 오류 `400` |
| GET | `/internal/support/attempts/{attemptId}` | core | 관리자 신고·문의 원문(#46, SERVICE_OPS 검사는 core, #146). `X-User-Role: ADMIN`, `X-Student-Scope`에 학생 정확히 1명, `X-User-Id`(UUID) 필수. `200 {studentId, attemptId, answers:[{answerId, version, text, feedback}]}`(답변 버전 순, `text`는 시도 상세와 같은 원문, `feedback`은 피드백 결과와 같은 모양). 초안·메모·학생 이름·돌아보기는 넣지 않음. 학생 전용 `/internal/attempts/{id}`와 별도. 시도 없음 `404`, 역할·범위 위반 `403`, `X-User-Id` 오류 `400` |
| GET | `/internal/records/students/{studentId}/exists` | core | 전체 보존 기록의 존재 여부 `{studentId,hasRecords}`. #37 선행 최소 API, P08 제출·실패·삭제 제외 기준 적용 |
| GET | `/internal/records/students/{studentId}/summary?from&to` | core, ai | 건수·상태 `Metric[]` → `{studentId, state, period, inclusionRule, metrics}`(1.6). 지표: 학습한 활동(집계 대상 시도 수), 완료한 활동(완료 / 집계 대상), 도움 없이 시작한 활동(최초 답변 전 생각 열기 열람 없는 시도 / 집계 대상, P08), 되묻기 후 생각을 더한 활동(보완 답변 제출 시도 / 되묻기 받은 시도, 1.6) |
| GET | `/internal/records/students/{studentId}/thinking-types?from&to` | core, ai, report | 유형별 미션·기록 → `{studentId, state, period, items:[{type, state, missions:[{attemptId, title}]}]}`, 다섯 유형 모두, 기록 없는 유형은 `NO_RECORD`(FN-DSH-08 미관찰) |
| GET | `/internal/records/students/{studentId}/attempts?from&to&status&page&size` | core, ai, report | 시도 목록·상세(답변 버전·되묻기·도움·돌아보기 원문) → 1.1 봉투 + `{studentId, state, period, inclusionRule}`, 최근 답변 순, `status`(`IN_PROGRESS`·`COMPLETED`, 생략하면 전체)는 지금 그 상태인 시도만. `items`는 4.1 시도 상세에서 초안(`draft`, 메모 포함)을 뺀 모양 + `completedAt`·`hintUsages:[{openedAt}]`·`reflection{difficulty, text, createdAt}`. `finishedAt`은 마무리(정답·예시 답 공개) 시각, `completedAt`은 돌아보기를 내 `COMPLETED`가 된 시각(각각 그 전에는 `null`), 돌아보기가 있으면 `createdAt`은 항상 값(= `completedAt`). `answers`·`hintUsages`는 1번·처음부터 조회 종료일까지(시작일 이전 포함, 지난 기간을 조회해도 그 뒤가 섞이지 않음, FN-RPT-02), `reflection`은 기간 안에 쓴 것만(아니면 `null`) |
| GET | `/internal/records/students/{studentId}/attempts/{attemptId}?from&to` | core | 학부모 2.3 시도 상세용. 목록 `items`와 같은 모양 + `state: OK`·`period`. 기간은 화면이 유지할 정보라 검증·기본값만 적용하고 이력(답변·되묻기·도움·돌아보기)은 자르지 않음. 다른 학생의 시도·집계 대상이 아닌 시도는 `404` |
| GET | `/internal/records/students/{studentId}/home?from&to&grade&demo` | core | 학생 2.3 홈용(FN-DSH-01·02) → `{studentId, state, period, resume, missions}`. 학생 본인 요청만(`STUDENT`, 범위에 본인 1명, 4.1 미션 목록과 같은 기준). `resume`은 진행 중 시도 중 가장 최근에 손댄 것(시작·답변 제출·초안 저장 중 가장 늦은 시각) 하나, 기간과 무관하고 초안만 있는 시도·마무리 뒤 돌아보기 전 시도도 포함(FN-LRN-16), 목록 `items`와 같은 모양(초안·메모 없음, 본인 초안은 core가 학생 시도 상세로 붙임), 없으면 `null`. `missions`는 4.1 미션 목록 항목 전체(`grade` 3~6 필수, `demo` 기본 `false`, 같은 노출 범위). `state`는 기간 안 집계 대상 시도 수 |
| GET | `/internal/records/students/{studentId}/thinking-activities?from&to` | core, ai | 학생 2.3 생각 활동용(FN-DSH-04), ai 분석 대화의 돌아보기·전후 변화 근거 미션 제목 → `{studentId, state, period, items:[{attemptId, thinkingType, missionTitle, reflection{difficulty, text}}]}`. 집계 대상 시도를 최근 답변 순으로, `reflection`은 기간 안에 쓴 것만(아니면 `null`, 목록과 같음). 수치·등급·순위 없음 |
| GET | `/internal/records/students/{studentId}/changes?from&to&page&size` | ai, report | 되묻기 전후 답변 쌍 → 1.1 봉투 + `{studentId, state, period}`, `items:[{attemptId, followup(마지막 답변이 답한 되묻기), first{answerId, text}, revised{answerId, text}, counts{chars, sentences, reasonConnectives}}]}`(3.4). 조회 종료일까지 보완 답변이 있는 시도만, 최초 vs 종료일 이전 마지막 답변(P08, FN-RPT-02). `text`는 원문, 수는 학생이 쓴 칸 내용으로 셈 |
| GET | `/internal/records/evidence?answerIds=` | core, report | 원문 근거 조회 → `{items: Evidence[]}`(1.6). 요청한 순서대로, 없는 답변·삭제 학생은 `available:false`(원문 없음), 범위 밖 학생의 답변이면 `403` |
| GET | `/internal/stats?from&to` | core | 운영 현황용 집계 (학생 원문 없음) → `{period, inclusionRule, attempts, completedAttempts, students}`(FN-ADM-02). 역할 `ADMIN`·`SYSTEM`, 학생 범위 없음 |
| GET · POST · PATCH · PUT | `/internal/admin/missions…` | core | 관리자 미션(2.8, #145). core가 `ADMIN` + `X-User-Id`(작성자·검토자 ID) + 빈 학생 범위로 넘김(CONTENT 검사는 core). 경로는 2.8 표와 1:1. 목록 `GET ?status&grade&thinkingType&page&size` → `{items: AdminMission[], page, size, totalElements, counts:[{status, count}]}`(`counts`는 페이지·status·grade·thinkingType 어느 필터와도 무관한 전체 상태별 건수), 상세 `GET /{id}` → `AdminMission`. 작성 `POST`(201)·수정 `PATCH /{id}` 본문 `{title, subject, gradeMin, gradeMax, thinkingType, inputType, question, guide?, sceneUri?, staticSceneUri?, achievementStandards[], choices?, categories?, answerUnit?, inputTemplate?, demoOnly}`, 기준표 `PUT /{id}/rubric` `{elements:[{code, label, description?, points, commonErrors[], goodThought, judgeVerified}], answerKey?, exampleAnswer?, forbiddenTerms[], keywords[], essayType?, hints[]}`(`keywords`·`essayType`은 M2 입력, 4.2.2. `essayType`은 논술 미션만)(`answerKey`는 입력 방식 모양 객체 `{choiceIds}`·`{assignments}`·`{finalAnswer}`), 검토 요청 `POST /{id}/review-request` `{missionVersion, rubricVersion}`, 검토 `POST /{id}/review` `{missionVersion, rubricVersion, result: APPROVED|CHANGES_REQUESTED, comment}`, 게시·중단 `POST /{id}/publish`·`/unpublish` `{}` → 모두 `AdminMission`. 미리보기 `GET /{id}/preview` → `{mission(4.1 학생 미션 상세 모양, 정답·예시 없음), missionVersion, rubricVersion}`. `AdminMission` = `{missionId, code, status, demoOnly, currentVersion, currentRubricVersion, publishedVersion, publishedRubricVersion, versions[], rubrics[], reviews:[{missionVersion, rubricVersion, result, comment, reviewerId, createdAt}]}`(생성·변경 응답의 `missionId`·버전 번호로 core가 감사 기록). 수정·기준표는 새 불변 버전(`current*`), 학생에게는 `published*` 버전(P07). 오류: 형식 `400 VALIDATION_FAILED`, 없는 미션 `404 NOT_FOUND`, 요청 버전이 현재와 다름 `409 MISSION_VERSION_CONFLICT`, 상태상 불가 전이 `409 CONFLICT`, 게시 필수 누락 `422 MISSION_PUBLISH_INCOMPLETE` + `missingFields`(영문 코드, class-diagram 4.1. 요소 code가 미션 유형·입력 방식에 맞지 않으면 `rubric.elements.code`, #262). 업로드 없음(URI 입력). #353(FN 1.5, ERD 4.1.1): 미션 본문 `achievementLevels?`(`{성취기준 코드: 단계 A~E}`, 저장 때는 모양만 400), 기준표 요소 `standardCode?`, `AdminMission.source`(`MANUAL`·`LLM_DRAFT`) 추가. 게시 누락 코드는 `achievementStandards`(성취기준 표에 없는 코드, 미션 학년 범위가 그 성취기준 학년군 밖인 경우 포함)·`achievementLevels`(미션 성취기준 밖 키 또는 그 성취기준 단계 수를 넘는 단계)·`rubric.elements.standardCode`(미션 성취기준 밖, 정답 요소에 값이 있음). 기존 `achievementStandards[]`는 문자열 배열 그대로 |
| GET · POST | `/internal/admin/achievement-standards`, `/internal/admin/mission-drafts…` | core | 성취기준 표·미션 초안(2.8, #353, FN-ADM-20·21). 인증·권한 전달은 위 관리자 미션과 같음. 성취기준 `GET ?subject&gradeBand&q&page&size` → 1.1 봉투 `items:[{code, subject, gradeBand, area, statement, levelScale, levels(이용 조건 확인 전 null), curriculumVersion, source, note}]`(`q`는 코드·문장 부분 일치). 초안 요청 `POST` `{standardCodes[](1개 이상), achievementLevels?, thinkingType, gradeMin, gradeMax, inputType}` → `202 MissionDraft`(`status: GENERATING`, 생성은 learning 주기 작업, class-diagram 4.1.1). 목록 `GET ?status&page&size`(최근 요청 순)·상세 `GET /{draftId}` → `MissionDraft`. 채택 `POST /{draftId}/adopt` `{}` → `201 AdminMission`(초안으로 미션·첫 버전·기준표를 위 작성·기준표 경로와 같은 규칙으로 한 트랜잭션에 만들고 `source: LLM_DRAFT`, 요소 배점은 기준안 1). 버리기 `POST /{draftId}/discard` `{}` → `MissionDraft`. `MissionDraft` = `{draftId, status, attempts, maxAttempts, input{standardCodes, achievementLevels, thinkingType, gradeMin, gradeMax, inputType}, checkResults:[{attempt, failures:[{check, reason}]}](`check`는 ai `REQUIRED`·`QUESTION_LENGTH`·`LEAK`, learning `STANDARD_CODE`·`ELEMENT_CODE`·`SHAPE`, AI 호출 실패는 `AI_CALL` + `reason` 실패 코드), draft(4.2 `draft`, 없으면 null), failureCode, versions{prompt, model}, missionId, requestedBy, createdAt, updatedAt}`. 오류: 형식·없는 성취기준 코드·미션 학년이 성취기준 학년군 밖·학년·입력 방식 조합(논술 5~6)·성취수준 단계(고르지 않은 성취기준이거나 단계 수 밖) `400 VALIDATION_FAILED`, 없는 초안 `404 NOT_FOUND`, 채택은 `READY`만·버리기는 `READY`·`CHECK_FAILED`·`FAILED`만(아니면 `409 CONFLICT`) |
| GET | `/internal/payment-usage/students/{studentId}?since` | core | SYSTEM + 해당 학생 scope. 결제 후 피드백 사용(DONE·RUNNING) 여부, 원문 미포함 (#48 환불 사용 확인) |
| GET | `/internal/students/{studentId}/weekly-theme?grade&date&sundayTheme` | core | 학생 본인 `STUDENT`(#385, core 호출 #387): 이번 주 테마·요일 상태·되돌아보기 목록(2.11 모양). 그 학년의 그 주 게시본, 없으면 그 주 이전 최근 게시본(`reused`). 게시 테마가 없으면 `404`. #438: `grade`는 `G3`·`G4`·`G5`·`G6`(중학생 `G6`은 core가 정함). 전환 기간에는 `grade`가 없으면 `gradeBand`(`G3_4` → `G3`, `G5_6` → `G5`)로 읽고 core 반영 뒤 지움. 응답에 더하는 칸(기준안, 수동 테마는 null일 수 있음): `bigQuestion`·`candidates[]`, `days[]`에 `clue`·`rulesOut[]`(그 문제를 그 주에 학습 완료한 뒤에만, 아니면 null, #484), `introImageUrl`·`introVideoUrl`·`introMotion`·`introSeen`·`outroSeen`, 엔딩 상태일 때만 `outro`·`outroImageUrl`·`outroVideoUrl`·`outroMotion`·`answer`·`answerClue`(결정적 단서)(그 밖에는 null. 엔딩 조건은 state-diagram 3.2.2, learning #484). URL은 learning이 만든 단기 presigned URL. 기존 칸 이름(`days[].attemptStatus`·`missionId` 등)은 그대로. `intro`(글)는 #385의 '월요일만'에서 매일 채움으로 바꿈(시작 이야기를 그 주 첫 진입에 보여 주려고). 2026-11-10 개정(#483): 일요일 허용 값 `sundayTheme`(위 시도 시작과 같은 뜻, 열람 기록 2종에도 붙임)을 core #485가 넘기고, 응답에 2.11 추가 칸(learning #484). core는 이 응답의 `days[].completedOnDay`·`completed`(개근)·`finished`로 포인트를 보충한다 |
| POST | `/internal/students/{studentId}/weekly-theme/review-views` | core | 학생 본인 `STUDENT`(#385, core 호출 #387): `?grade&date&sundayTheme`(본문 없음, #438 전환 기간 `gradeBand`도 받음, `sundayTheme`은 core #485), 열람 기록(학생·주당 1행 멱등), `{firstViewThisWeek, completed}` 반환(포인트·개근 판정 근거). 평일 `409 THEME_REVIEW_NOT_ALLOWED` |
| POST | `/internal/students/{studentId}/weekly-theme/story-views` | core | 학생 본인 `STUDENT`(learning #438, core 호출 #439): `?grade&date&sundayTheme`(전환 기간 `gradeBand`도 받음, `sundayTheme`은 core #485) + body `{kind: INTRO\|OUTRO}`. INTRO는 월~토·프리미엄 일요일(그 주 첫 진입에 1번, 2026-11-10 사용자 결정으로 '월요일만'에서 바꿈)·OUTRO는 엔딩 상태이고 무료 일요일이 아닐 때(#484), 학생·주·kind당 1행 멱등(`theme_story_view`) → `200 {kind, firstViewThisWeek}`. 그 밖 `409 THEME_STORY_NOT_ALLOWED`, 게시 테마 없음 `404`, 다른 `kind`·필드 `400` |
| POST | `/internal/students/{studentId}/weekly-theme/answer-picks` | core | 학생 본인 `STUDENT`(learning #484, core 호출 #550): `?grade&date&sundayTheme`(전환 기간 `gradeBand`도 받음) + body `{pick}`. 큰 질문 정답 고르기: 그 주 금요일 문제(`THEME_DAY`)를 마무리한 뒤 후보 중 하나, 학생·주당 1행(`theme_answer_pick`) → `200 {correct, ending, answer}`(`answer`는 `ENDED`일 때만). 맞히면 `ENDED`, 틀리면 `NOT_ENDED`이고 토요일(프리미엄 일요일) 금요일 문제 `THEME_REVIEW` 마무리 뒤 `ENDED`. `pick` 없음·빈 값·후보 밖 `400 VALIDATION_FAILED`, 큰 질문 없는 테마·금요일 문제 마무리 전·이미 고름·무료 일요일 `409 THEME_PICK_NOT_ALLOWED`, 게시 테마 없음 `404` |
| GET | `/internal/students/{studentId}/weekly-theme/summary?weekStart` | report | #385(소비는 report #391): 역할 `PARENT`·`STUDENT`·`SYSTEM` + 대상 학생 scope. `{studentId, weekStart, state(OK·NO_RECORD), themeId, title, days:[{day, missionId, title, completed}], completed, reviewRetries:[{missionId, title, attemptId, comparison}]}`. 2026-11-10 개정(#483): `days[].completedInWeek`(그 주 테마 시도 안에 학습 완료, 일요일 포함)·`finished`(주간 완주)·`ending`(`NOT_ENDED`·`ENDED`) 추가(learning #484 구현, report #486은 선택 칸으로 소비해 새 칸이 없는 이전 응답도 받음. `finished`는 그 주 테마 시도로 토요일 23:59:59 KST까지 다섯 문제 학습 완료). 요약의 `days[].completed`는 이름·뜻(그 요일 KST 안에 학습 완료 = 주간 테마 조회의 `completedOnDay`) 그대로 두고 요약에는 `completedOnDay`를 따로 두지 않는다(#486 결정, #507). 비교는 #207 규칙을 재사용해 `{state, elements}`만 제공하며 마무리 전 `null`, 답변 원문은 제외. 그 주 테마 시도가 없으면 `NO_RECORD`, 월요일이 아니면 `400` |
| POST | `/internal/community/posts` | core | 구현(learning #386, core 호출은 #388): `X-User-Role: SYSTEM`, scope = 그 학생. `{studentId, attemptId}` → 그 미션을 처음 학습 완료한 시도의 마지막 답변 공유(지금 표현 필터 통과, 학생·미션당 1개 멱등). `201 {postId, created:true, status}` 새 공유, `200 {postId, created:false, status}` 이미 있음(다시 푼 시도로 요청해도 같음). 새 공유물은 core가 마지막으로 알린 공개 여부가 끔이면 `HIDDEN_SETTING`. 그 밖: 없는·남의 시도 `404`, 공유 대상 아님 `409 COMMUNITY_NOT_SHAREABLE` → core는 공유 안 함으로 본다. `postId`는 포인트 사건 키(#389) |
| GET | `/internal/community/missions/{missionId}/posts?viewerStudentId&seed&page&size` | core | 구현(#386): `STUDENT`, scope = viewer(`viewerStudentId`와 같아야 함). 열람 검사(viewer가 그 미션을 학습 완료했는지, 아니면 `403 COMMUNITY_LOCKED`. 정답 고르기 문제는 그 문제로 고른 주의 엔딩도, 아니면 `403 COMMUNITY_LOCKED_UNTIL_ENDING` #484)·`VISIBLE` 무작위 목록(열람자 본인 공유물 제외, 반응 수 없음, 같은 `seed`면 같은 순서) `{items:[{postId, studentId, answer:{inputType, text, content}, myReactions[], createdAt}], page, size}`. `seed` 1~100자, `size` 1~100 |
| GET | `/internal/community/students/{studentId}/posts` | core | 구현(#386): `STUDENT`(본인)·`PARENT`(자녀), scope = 그 학생. 모든 상태, 최근 공유 순 `{studentId, items:[{postId, missionId, missionTitle, answer, status, reactions:{NEW_IDEA…: 수(4종 모두)}, createdAt}]}` |
| PUT·DELETE | `/internal/community/posts/{postId}/reactions/{reaction}?studentId` | core | 구현(#386): `STUDENT`, scope = 반응한 학생(`studentId`와 같아야 함). 반응 생성·취소(멱등), PUT `200 {postId, reaction, reactionId, created}`·DELETE `200 {postId, reaction, reactionId, deleted}`. `reactionId`는 학생·공유물·반응으로 정해 취소 뒤 다시 남겨도 같음(포인트 사건 키, #389). PUT은 `VISIBLE` 공유물만, 취소는 숨긴 공유물에서도 가능. 오류 `403 COMMUNITY_LOCKED`·`404 COMMUNITY_POST_NOT_FOUND`·`409 COMMUNITY_OWN_POST`는 core가 그대로 전달, 4종 밖 `400` |
| PUT | `/internal/students/{studentId}/community-visibility` | core | 구현(#386): `SYSTEM`, scope = 그 학생. `{visible, reason}`(`SETTING`·`CONSENT`·`TRANSFER`) → 공유물 `VISIBLE`↔`HIDDEN_SETTING`(`HIDDEN_REPORT`·`REMOVED`는 그대로), 같은 값 반복 멱등, `200 {studentId, visible, changed(바꾼 수)}`. learning은 마지막 값을 `community_visibility`에 두고 신고 숨김을 풀 때·새 공유 때 설정 비공개를 지킨다. core는 커밋 뒤 호출하고 실패는 기록 후 다음 설정 저장 때 다시 보낸다 |
| PUT | `/internal/community/posts/{postId}/moderation` | core | 구현(#386): `SYSTEM`, scope 없음. `{status, errorReportId}`(`HIDDEN_REPORT`·`VISIBLE`·`REMOVED`) 멱등 → `200 {postId, status(반영 뒤)}`. `VISIBLE`은 `HIDDEN_REPORT`에서만 되돌리고 작성자 공개가 끔이면 `HIDDEN_SETTING`으로, `REMOVED`는 끝 상태. 없는 공유물 `404 COMMUNITY_POST_NOT_FOUND` |
| GET | `/internal/community/posts/{postId}` | core | 구현(#386, #388 요청): `SYSTEM`, scope 없음. 신고 대상 확인·관리자 원문 열람 `{postId, studentId, missionId, status, answer, createdAt}`(상태 무관), 파기·없음 `404 COMMUNITY_POST_NOT_FOUND` |
| GET · POST | `/internal/admin/theme-drafts…` | core | learning #438(core #439 프록시, 에픽 #436): 인증·권한 전달은 관리자 미션과 같음. 요청 `POST` `{grade, weekStart, topic?, missions?:[{thinkingType, standardCodes[](1개 이상), inputType}]}` → `202 ThemeDraft`(`grade` `G3`~`G6`, `weekStart` 이번 주 이후 월요일, `topic` 100자 이하이고 비우면 learning이 주제 씨앗 `뭉치 역할: … / 장소: … / 찾는 대상: …`을 골라 넣음(주간 자동도 같음, 기준안 목록 24개·같은 학년 최근 목록 개수만큼의 주와 같은 주 다른 초안 씨앗은 피함·계절, #437 실측 쏠림 대응 2026-11-11), `missions`는 유형마다 최대 1개이고 비운 유형은 자동 규칙으로 채움, 성취기준 실재·그 학년을 포함하는 학년군·입력 방식(초3·초4 논술 불가) 아니면 `400`, 비운 유형을 채울 성취기준이 표에 없으면 `409 CONFLICT`). 목록 `GET ?status&source&page&size`(최근 요청 순)·상세 `GET /{draftId}` → `ThemeDraft`. 채택 `POST /{draftId}/adopt` `{}` → `201 AdminWeeklyTheme`(아래, 응답 `themeId`. 미션 5개 `DRAFT`·`source: LLM_THEME`와 테마 `DRAFT`를 한 트랜잭션, 요소 배점 1). 버리기 `POST /{draftId}/discard` `{}` → `ThemeDraft`. 다시 생성 `POST /{draftId}/regenerate` `{}` → `202 ThemeDraft`(같은 입력의 **새 초안**, `source: ADMIN`, 원래 초안은 그대로). 상태상 불가 전이 `409 CONFLICT`, 없는 초안 `404`. `ThemeDraft` = `{draftId, status, source, grade, weekStart, attempts, maxAttempts, input{topic, missions[{thinkingType, inputType, standardCodes}]}, checkResults:[{attempt, failures:[{stage, reasons[]}]}](`stage`는 ai `THEME`·`MISSION`·`REVIEW`·`IMAGE`, learning 검사 `LEARNING`, AI 호출 실패 `AI_CALL` + 실패 코드), draft(ai 응답 `theme`·`missions`·`dialogues`·`warnings`, 없으면 null), scenes:[{scene(INTRO·OUTRO·MON~FRI), imageUrl, videoUrl, motion}](미리보기 presigned URL. `videoUrl`은 `INTRO`·`OUTRO`만 값이 있고 요일은 null(ai 요일 영상 없음, #437 사용자 결정 2026-11-11). `motion`은 ai 움직임 형식 v1(살펴보기 `spots` 포함)을 칸 검사 없이 그대로, ai가 빠뜨린 장면은 null), failureCode, versions{prompt, model}, themeId, requestedBy, createdAt, updatedAt}` |
| GET·POST·PUT | `/internal/admin/weekly-themes…` | core | #385(core #387 프록시): `ADMIN` + `X-User-Id`. 목록 `GET ?grade&weekStart&status&page&size` → `{items, page, size, totalElements}`, 작성 `POST`(201)·수정 `PUT /{id}`(새 버전) 본문 `{grade, weekStart, title, intro, days:[{day, missionId}]}`, 검토 요청·게시·중단 `POST /{id}/review-request`·`/publish`·`/unpublish` `{}` → 모두 `AdminWeeklyTheme` = `{themeId, grade, weekStart, status, version, publishedVersion, reviewRequested, title, intro, days, publishedAt, createdAt, updatedAt}`. 오류: 형식·월요일 아닌 주·없는 미션 `400`, 상태상 불가 전이·게시 중 학년·주 변경 `409 CONFLICT`, 게시 검사 `422 WEEKLY_THEME_PUBLISH_INCOMPLETE` + `errors:[{code, message}]`. #438 학년별 테마: `gradeBand` → `grade`(`G3`~`G6`, 목록·본문·응답 모두, 관리자 경로는 전환 호환 없음). 본문·응답에 선택 칸 추가(기준안, 생략하면 null): `outro`, `introImageUri`·`outroImageUri`·`introVideoUri`·`outroVideoUri`(S3 키), `introMotion`·`outroMotion`, `bigQuestion`·`candidates[]`·`answer`·`answerClue`, `days[]`에 `clue`·`rulesOut[]`·`dialogue[{speaker, text}]`·`hintSpots[{seq, x, y}]`·`videoUri`(요일 문제 전 영상 키. ai는 요일 영상을 만들지 않아 테마 초안 채택 테마에서는 null이고 관리자가 직접 넣을 때만 쓰는 칸, #437 2026-11-11). 응답에는 미리보기용 presigned URL `introImageUrl`·`outroImageUrl`·`introVideoUrl`·`outroVideoUrl`·`days[].videoUrl`·`days[].sceneImageUrl`(그날 미션 현재본 장면)도 담음. 저장 때 정답 논리(정답·`candidates`·`rulesOut`이 함께 있거나 함께 없음, 정답은 후보 안이고 어떤 날에도 빠지지 않음, 틀린 후보는 적어도 한 날 빠짐, `rulesOut`은 후보 안)와 `hintSpots`(`x`·`y` 0~100, `seq`가 그날 미션 현재 기준표의 생각 열기 순번, 중복 없음) 위반은 `400`. 게시 검사 코드 `GRADE_BAND_MISMATCH`를 `GRADE_MISMATCH`(미션 학년 범위가 테마 학년을 포함하지 않음)로 바꿈(웹·core는 `errors[].message`만 쓰고 코드를 읽지 않음) |
| GET·POST·DELETE | `/internal/admin/knowledge/datasets…` | 운영 스크립트 | #466 교육과정 지식 판 적재·상태·활성화·제거. `SYSTEM`, core 프록시 없음. 4.1.3 |
| GET · POST | `/internal/knowledge…` | ai, learning 내부 | 교육과정 지식 근거·검색(#463, 계약 #464 C5, 구현 #469). `SYSTEM` 역할, 학생 범위·학생 정보 없음. 다섯 경로와 응답은 4.1.2 |

- 기록 조회 공통 (#27): 학생 경로는 역할 `PARENT`·`STUDENT`·`SYSTEM`(`home`은 학생 본인 `STUDENT`만)이고 `X-Student-Scope`에 대상 학생이 없으면 `403`. `from`·`to`는 KST 날짜(양 끝 포함), 둘 다 주거나 둘 다 생략(생략하면 오늘 포함 최근 7일, P06), 한쪽만 주거나 `from > to`면 `400`. 응답 `period`는 실제 조회 기간. 집계 대상은 P08(기간 안에 답변 제출이 있는 시도, 미완료 포함·판정 상태 무관. 조회 종료일까지의 답변이 모두 처리 실패인 시도와 삭제 기록은 제외). 시도별 사실(완료·되묻기 받음·보완 답변·최근 답변)은 조회 종료일까지 일어난 것만. `state`는 집계 대상(비율은 분모) 0건 `NO_RECORD`, 1~4건 `INSUFFICIENT_SAMPLE`(비율 `value: null`), 5건 이상 `OK`. 메모·초안은 반환하지 않음(P05). 최상위 학생 식별자는 호출 역할과 무관하게 `studentId`(학부모 공개 응답의 `childId`는 core가 바꿈, core #40·report #51과 합의). 조회 장애는 `state`가 아니라 HTTP 오류(Problem Details)로 반환. 까닭을 잇는 말은 `왜냐하면`·`때문`·`그래서`·`따라서`(report와 확정)

- #387: learning 시도 시작 내부 API(4.1 `/internal/missions/{id}/attempts`)에 body `{context}` 전달(`themeId`는 넘기지 않음: 그 주 테마는 learning이 `grade`·KST 날짜로 정한다), 요일·되돌아보기 검사는 learning(#385), 무료 한도 집계는 core
- #438(에픽 #436, 기준안): 시도 시작·이어하기 응답(`POST /internal/missions/{id}/attempts`)에 `themeScene`을 더한다. `context`가 `THEME_DAY`·`THEME_REVIEW`면 `{dialogue:[{speaker, text}], hintSpots:[{seq, x, y}], videoUrl}`(그 시도 `theme_id` 테마 게시본의 그 미션 요일 값, 칸이 비면 null·빈 배열), `EXTRA`는 `null`. 학생 미션 응답(목록·상세·시도의 `mission`)에 `sceneMotion`(장면 그림 움직임, 없으면 null)을 더하고, `sceneUri`·`staticSceneUri`가 ai 키(`theme-drafts/…`, 테마 초안 채택 미션)면 단기 presigned URL로 바꿔 내보낸다(그 밖의 값은 저장 값 그대로). 관리자 미션 응답은 저장된 키 그대로(웹이 그 값을 다시 저장하므로), 관리자 미션 수정 본문에는 `sceneMotion`이 없어 `sceneUri`가 같으면 이전 버전 움직임을 이어받고 바뀌면 비운다. 문제 전 영상은 미션이 아니라 테마 요일 칸이라(같은 미션이 학년별 테마 여럿에 들어갈 수 있고, 미션 조회는 어느 테마에서 열었는지 모름) `themeScene.videoUrl`로만 준다(ai 테마 초안 채택 테마는 요일 영상이 없어 null, 관리자가 넣은 영상만 나감). `sceneMotion`은 ai 움직임 형식 v1(ai OpenAPI `ThemeMotion`, 요일 장면 살펴보기 `spots` 포함)을 learning이 칸 검사 없이 저장한 그대로다. 생각 열기(`POST /internal/attempts/{id}/hints`)는 그대로

#### 4.1.1 report 수치 집계 입력

P06·P08 계산에 쓰는 learning 공급 입력. 계산 규칙과 검증은 [리포트 보고서](../report/report.md).

- 세 조회 모두 `studentId`·`period:{from,to}`·`state`를 반환한다. 학부모 공개 응답의 `childId`와 혼용하지 않는다. 학생·기간이 요청과 다르면 생성에 사용할 수 없다. 날짜 범위는 KST 양 끝 포함이며 조회 장애는 HTTP 오류다.
- `attempts`·`changes`는 1.1의 페이지 봉투를 사용한다. `page`는 0부터 시작하고 `totalElements`는 같은 학생·기간·포함 기준의 전체 항목 수다. report는 `size=100`으로 모든 페이지를 읽으며 실패/누락 페이지를 빈 기록으로 바꾸지 않는다. `thinking-types`는 `{studentId,state,period,items}` 형태를 사용한다.
- `attempts.items[]`의 필수 입력:
  - `attemptId`, `studentId`, `mission:{title,thinkingType}`, `status:IN_PROGRESS|COMPLETED`, `answers[]`, `hintUsages:[{openedAt}]`. 학생 메모·초안은 포함하지 않는다. #27은 attempts에 삭제 표식 항목을 넣지 않는다. 삭제 뒤 정상 조회는 `NO_RECORD`, `items:[]`, `totalElements:0`이다. 이것은 evidence의 삭제된 답변 표시나 #55 삭제 완료 처리를 대신하지 않는다.
  - `answers[]`: `{answerId,version,submittedAt,inputType,text,followupId,content,feedback}`. `feedback`은 학생 시도 상세와 같은 `{status:PENDING|RUNNING|DONE|FAILED,judgment,followup,nextActions,versions}`이고, `judgment`는 처리 전·실패면 null, 아니면 `{judgmentId,result,trial,elements[{elementId,label,code,goodThought,satisfied,quote,sourceType}],heldReason}`. 생각 요소 지표(FN-RPT-05)는 `code`(FN 1.5 표준 요소)로 미션을 넘어 같은 요소를 세고 `goodThought = false`인 필수 요소만 충족률·보완률 분모로 쓴다. report는 시범 판정(`trial`)을 포함해 계산하고 계산식에 표시하며, `HELD` 판정과 정답 요소(`ANSWER_KEY`·`FINAL_ANSWER`)는 쓰지 않는다 (FN-RPT-05, #262·#344). `text`는 표시·근거용 평문 전체이고 null이 아닌 문자열이다(내용이 없으면 `""`). 풀이·논술의 칸 이름과 고르기의 선택지 이름이 포함될 수 있다. 수치 재계산에는 `content`의 학생 작성 칸만 사용해야 하며 표시용 `text`를 그대로 세면 안 된다. 시도당 1번부터 조회 종료일 끝까지의 답변 버전을 제공한다. 최초 답변·도움 이용을 비교할 수 있도록 조회 시작일 이전의 답변도 포함한다. report는 종료일 이후 답변을 사용하지 않는다.
  - `feedback.judgment.corrected`: 최신 정정이 있으면 true. 정정은 결과만 바꾸고 `elements`는 원판정 그대로이므로 report는 요소 지표(FN-RPT-05)와 일일 리포트 요소 표시에서 제외한다 (#244).
  - `feedback.judgment.modelScores`(#478): attempts에 `includeModelScores=true`로 요청할 때만 키가 있고, learning `judgment.model_scores` 저장값 그대로(4.2.2 `modelScores`와 같은 `{m2, m1, skipped}`), M2를 부르지 않았으면 null이다. 이 쿼리는 `X-User-Role: SYSTEM`(report 주기 작업)만 허용하고 그 밖 역할은 `403 FORBIDDEN`이다. 같은 경로를 core가 학부모·학생 대시보드로 그대로 넘기고 ai 분석 대화 도구도 읽으므로, 쿼리가 없으면 키를 넣지 않는다(학생 시도 상세 응답도 키 없음). report는 리포트 설명(FN-RPT-09) 대상 선정·설명 요청 입력에만 쓰며 점수를 수치·화면에 표시하지 않는다
  - `hintUsages[]`는 조회 시작일 이전 기록을 포함하여 최초 답변 이전 열람 여부를 판정할 수 있는 전체 열람 시각을 제공한다. 열람이 없으면 빈 배열이며 단순 `helped` 값으로 대체하지 않는다. `submittedAt`·`openedAt`·`completedAt`·`createdAt`은 시간대 오프셋이 있는 ISO 8601 시각이다.
  - 완료 시도는 `completedAt`을 제공한다. learning **입력**의 `reflection`은 해당 기간에 작성한 `{difficulty:EASY|NORMAL|HARD,text:string|null,createdAt}` 또는 `null`이다. 미작성·기간 밖이면 `null`을 사용하고 report는 필드 생략도 허용한다. 선택 텍스트가 null이어도 난이도·작성 시각이 있는 돌아보기는 작성한 기록이다. `{written:false}`만 있는 객체는 입력 형식이 아니다.
  - report **출력/저장 항목**의 `reflections[]`는 미작성·기간 밖이면 `{attemptId,written:false,difficulty:null,text:null}`이다. 입력에 기간 밖 돌아보기가 포함되어도 report가 작성 시각으로 제외한다. 작성한 항목은 `written:true`이며 내부 계산·저장에는 난이도 코드를 유지한다. 입력과 3.4 출력 형식을 혼용하지 않는다.
- `thinking-types.items[]`: `{type,missions:[{attemptId,title}],state}`. 다섯 유형을 모두 제공하며 없는 유형은 `NO_RECORD`, 있는 유형은 `OK`다. 유형 요약 문장은 제공하지 않는다. 집계 대상 시도의 유형·미션을 대조한다.
- `changes.items[]`: `{attemptId,followup:string|null,first:{answerId,text},revised:{answerId,text},counts:{chars,sentences,reasonConnectives}}`. 포함된 시도의 종료일 기준 최초·마지막 답변과 ID·평문이 일치해야 한다. 시도당 한 쌍이며 답변이 하나뿐이면 변화 항목을 만들지 않는다. 수치는 report가 `answers[].content`로 다시 계산한다. 서술은 text, 풀이는 steps 순서 후 finalAnswer, 논술은 essay.claim·reasons 순서·rebuttal 중 비어 있지 않은 칸을 줄바꿈으로 연결한다. 칸 이름·선택지 이름·메모·추가 필드는 제외하며 고르기·순서·분류의 학생 작성 글은 빈 문자열로 계산한다. 필수 내용 누락·잘못된 형식은 오류로 처리하며 표시용 text로 대신 계산하지 않는다. null `followup`은 계산 결과·DB에 그대로 보존한다. 후속 #53·#54의 조회 JSON도 null을 유지하고 PDF·HTML·Markdown은 질문 문구를 생략해야 한다. `None`이나 임의의 질문을 표시하지 않는다.
- `evidence`는 `{items:[...]}`다. 정상 항목은 `answerId,attemptId,answerVersion,quote,missionTitle,submittedAt,available:true`이며 `quote`는 attempts의 `text`와 같은 전체 평문이다. 없는 답변·삭제 학생은 `available:false`로 원문을 제공하지 않는다. 요청 ID를 중복 제거한 순서대로 정상/삭제 항목을 함께 반환하며 누락하지 않는다. report는 ID를 중복 없이 보내고 시도·버전·원문을 대조한다.
- 동일 시도가 여러 주에 걸치면 각 주에 제출된 답변 존재 여부로 포함한다. 변화는 포함된 시도의 최초 답변과 해당 주 종료일 이전 마지막 답변을 비교한다. 조회 이후에 추가된 답변으로 과거 주의 마지막 답변을 바꾸지 않는다.

#### 4.1.2 교육과정 지식 내부 API (#463, 계약 #464 C5, 구현 #469)

**C5 코드 조회(#469)**. 2026-11-12 #466·#470 합의와 PR #547에 따라 성취기준·생각 유형 코드 조회만 제공한다. 벡터 검색 API 3개와 전용 요청·응답·오류·사유는 제외한다. 저장 구조는 [ERD 4.5](erd.md#45-교육과정-지식-rag-463-계약-464-구현-466), 요청·응답은 learning OpenAPI, ai 모델은 `app/knowledge/contracts.py`, 시험 대역은 `app/knowledge/fake.py`를 따른다. 변경 시 이 절·양쪽 OpenAPI·ai 계약·대역·계약 시험을 함께 갱신한다.

| Method | Path | 호출자 | 요청 → 응답 |
|---|---|---|---|
| GET | `/internal/knowledge/standards?codes&grade&thinkingType` | learning 미션 초안 작업(같은 서비스 안), ai 테마 미션 생성 | 코드(쉼표, 1~10개) → `KnowledgeBundle {datasetVersion, items:[{standard{code, subject, grades, semesters, noticeGradeBand, area, statement, explanation, ref}, domain(고려 사항을 가진 영역, 없으면 null), covers:[내용 요소], fits:[{thinkingType, reason}], gradeMatch}], missingCodes, subjectGuides:[교과 지침], thinkingType(그 유형 출제 지침 또는 null), reason}`. 유사도 검색 없음. `grade`를 주면 `gradeMatch`(그 학년에 배우는 성취기준인지), 안 주면 null |
| GET | `/internal/knowledge/thinking-types/{type}` | ai | → `{datasetVersion, guide:{type, name, basis[{framework, attribution}], elements[{code, label, description}], questionMust[], questionMustNot[], ref}, reason}`. 팀이 우리 말로 쓴 지침과 출처 표기만(블룸·VALUE 원문 없음) |

- 인증: HTTP는 내부 토큰·`SYSTEM` 역할 필수. 학생 정보·학생 범위 헤더를 받지 않는다.
- 직접 호출: learning 미션 초안은 `KnowledgeService.standards(codes, grade, thinkingType)`를 직접 호출한다. 컨트롤러와 같은 `KnowledgeBundle`을 반환하며 입력 검사·읽기 트랜잭션·질의 예산을 공유한다. `thinkingType(type)`도 같은 서비스에서 제공한다. ai 테마는 HTTP로 호출한다(#470).
- 조회 판: `knowledge_dataset.status = ACTIVE` 한 판의 `version`으로 조각·관계를 조회한다. `LOADING`·`RETIRED`는 제외하며 요청 전체가 같은 읽기 스냅샷을 사용해 판 교체 중 근거가 섞이지 않는다.
- 대체 사유(`reason`): `NO_ACTIVE_DATASET`(활성 판 없음)·`CODE_NOT_FOUND`(요청 코드가 하나도 없거나 유효한 유형의 지침이 없음). 정상적인 근거 없음은 HTTP 200, 일부 코드만 없으면 `missingCodes`에 기록하고 `reason`은 null이다.
- 오류: 형식·상한 밖·알 수 없는 생각 유형은 `400 VALIDATION_FAILED`, 조회 실패·질의 시간 예산 초과는 `500 INTERNAL_ERROR`. 오류를 근거 없음으로 숨기지 않는다. 임베딩 비교·409 오류는 없다.
- 내용: 성취기준 묶음의 `domain`은 성취기준이 속한 영역(국어·수학·도덕은 내용 체계와 고려 사항이 같은 영역, 사회·과학은 단원 = 고려 사항·탐구 활동)이다. 고려 사항은 영역 단위라 같은 영역끼리 같은 글이다. 교과 지침은 요청 교과마다 한 번(`subjectGuides`) 반환한다. 각 근거에 `{kind, id, datasetVersion}`을 붙인다.
- 관계: 사람이 확인한 같은 판의 `fits`·`covers`만 반환한다. 확인된 관계가 없으면 빈 배열이며 성취기준·해설·영역·교과·유형 지침 조회는 계속된다. 관계를 추정해 채우지 않는다.
- 학년: 선택 `grade`는 초3~6이며 각 성취기준의 `gradeMatch`를 채운다. 불일치여도 해당 코드를 숨기지 않는다. 학년 미지정은 null, `thinkingType` 미지정은 유형 지침 null이다.
- 상한: 코드 1~10개. learning 질의 예산은 기본 2초(각 SQL에 남은 시간 적용)이며 작업 이름·결과·지연만 기록한다. 연결 풀 대기 강제 취소와 응답 전송까지의 절대 2초 보장은 아니며 실측·한계는 [learning 보고서 33장](../report/learning.md#33-지식-코드-조회-내부-api-469-2026-11-12)에 기록한다. ai→learning 대기 시간은 #470에서 정한다.
- 배포: #466 V17까지 적용된 DB를 사용한다. #469는 테이블·마이그레이션을 중복 생성하지 않는다. 미션 생성 프롬프트·C7 연결은 #470 범위이며 C6 임베딩 API는 별도 기능으로 유지한다.

#### 4.1.3 교육과정 지식 판 관리 (#466)

판 적재·상태 조회·활성화·제거(계약 #464 C9, 저장 구조 [ERD 4.5](erd.md#45-교육과정-지식-rag-463-계약-464-구현-466)). learning OpenAPI `/admin/knowledge/datasets…`.

- 부르는 쪽: 운영 스크립트 `scripts/knowledge/manage_datasets.py`가 learning에 직접(kind는 `kubectl -n app port-forward svc/learning-service 18081:8081`) 내부 토큰 + `X-User-Role: SYSTEM`. core 프록시·관리자 화면·감사 기록 없음(동섭 결정 2026-11-11, 이슈 기준안). 다른 역할은 `403`
- 적재는 동기(동섭 결정 2026-11-11). 실제 추출본(#465 `curriculum-v1`, 1,341건)이 kind에서 5초. 스크립트는 10분까지 기다린다. 실패하면 판은 `LOADING`으로 남는다(C9)
- 임베딩 없음: 미션·테마 생성에 벡터 검색을 쓰지 않는 팀 결정(에픽 #463, 2026-11-11)에 따라 적재는 ai 임베딩(4.2.4)을 부르지 않고 활성화도 임베딩을 요구하지 않는다. 지식 표는 성취기준·생각 유형 코드 조회(4.1.2 `standards`·`thinking-types`, #469)용이다. learning V17이 임베딩 칸을 지웠다

| 메서드 | 경로 | 내용 |
|---|---|---|
| GET | `/internal/admin/knowledge/datasets` | `{items:[KnowledgeDatasetView]}` 최근 판부터. `KnowledgeDatasetView = {version, status, source, chunkCount, relationCount, chunks:{종류: 수}, relations:{SEMESTER·FITS·PREREQUISITE·COVERS: 수}, createdAt, activatedAt}` |
| POST | `/internal/admin/knowledge/datasets` | 본문 `{source, records:[C1], reviews:[C4 행]}`(reviews 선택) → `201 KnowledgeLoadResult {dataset, documents, previousVersion, carriedRelations, recheck:[C4 행]}`. 새 판 `kn-YYYYMMDD-NN`(KST) `LOADING`, `source.previousVersion`에 적재 때 활성 판 |
| GET | `/internal/admin/knowledge/datasets/{version}` | `KnowledgeDatasetView`, 없으면 `404 KNOWLEDGE_DATASET_NOT_FOUND` |
| POST | `/internal/admin/knowledge/datasets/{version}/activate` | 본문 `{}` 또는 없음 → 한 트랜잭션에서 이전 `ACTIVE` → `RETIRED`, 이 판 → `ACTIVE` |
| DELETE | `/internal/admin/knowledge/datasets/{version}` | `RETIRED`만 `204`(관계 → 조각 → 판) |

- 적재 순서(C9 ①~⑦): 입력 검사(레코드 형식, 같은 판 안 조각 ID 겹침, 학기가 그 학년 것, 성취기준 문장 = `achievement_standard`, 확인 행 `reviewer = SAMPLE` 거부, 관계 끝: 성취기준·생각 유형·내용 요소 조각, 선수 코드는 `achievement_standard`) → 실패하면 판을 만들기 전에 `400 VALIDATION_FAILED` → ① 판 행 → ②④⑤⑥⑦ 한 트랜잭션: 조각, 학기 관계, 이전 활성 판 관계 옮기기 + 새 확인 행(늦은 `reviewedAt` 우선, 늦은 `REJECT`는 옮긴 관계를 뺌), 확인된 covers로 내용 요소·영역 학년·학기, `chunk_count`·`relation_count`(학기·fits·prerequisite·covers 행 합)
- `recheck`: 옮기지 못한 관계(끝이 새 판에 없음)와 옮겼지만 끝 본문이 바뀐 관계를 C4 행 모양(`decision` 빈 칸, `evidence`에 사유, `datasetVersion` = 이전 판)으로. 스크립트 `--recheck-out`이 CSV로 저장해 #468 확인 파일에 다시 넣는다
- 활성화 `409 KNOWLEDGE_DATASET_STATE_CONFLICT`: `LOADING`이 아님, 적재 뒤 활성 판이 바뀜(`source.previousVersion` ≠ 현재 활성 판, 다시 적재). 제거 `409`: `ACTIVE`·`LOADING`
- 같은 입력을 다시 적재하면 같은 조각·관계 수(멱등)

#### 4.1.4 기념 액자·추억 내부 API (P27, 설계·구현 전)

**구현 전 계약(기준안)**. 2.12의 core 프록시 대상. 호출자는 core, `X-Student-Scope`에 `studentId`가 없으면 403(1.3). 저장은 [ERD 4.6](erd.md).

| 메서드 | 경로 | 내용 |
|---|---|---|
| GET | `/internal/students/{studentId}/album?page&size` | 2.12 앨범 목록과 같은 모양(`displayed`는 core가 슬롯으로 채움) |
| GET | `/internal/students/{studentId}/album/{themeId}/{weekStart}` | 2.12 회차 상세, 미보유 404 `THEME_FRAME_NOT_FOUND` |
| POST | `/internal/students/{studentId}/album/{themeId}/{weekStart}/seen` | `seen_at` 기록(멱등) → 204 |
| POST | `/internal/students/{studentId}/frames/ownership` | `{frames:[{themeId, weekStart}]}` → `{owned:[{themeId, weekStart}]}`(core 액자 슬롯 저장 전 확인) |
| POST | `/internal/students/{studentId}/memories/search` | `{query}` → 2.12 검색 응답. 질문 임베딩은 ai 4.2.4, 실패 503 `AI_UNAVAILABLE` |
| POST | `/internal/students/{studentId}/memories/explanations` | `{query, attemptIds}` → 2.12 설명 응답. 생성은 ai 4.2.6 |

- 검색 범위: `memory_search_doc.status = READY` + 본인 + 보유 `theme_frame` 회차 + `theme_week_start < 이번 주(KST)`. 코사인 거리 정렬 뒤 회차 단위로 묶어 상위 3개, 관련도 기준값(기준안, 평가셋으로 조정) 미달은 `NO_RESULTS`
- 설명: `attemptIds`가 위 범위의 문서인지 다시 확인(아니면 422 `VALIDATION_FAILED`) → 근거 부족 규칙(최고 관련도 기준 미달·답변 너무 짧음)이면 ai를 부르지 않고 `INSUFFICIENT` → ai 응답의 `citations`가 보낸 번호 안이고 따옴표 인용이 근거 원문의 부분 문자열일 때만 `GENERATED`, 아니면 ai 실패와 같이 `FAILED`(200)
- 학습 완료(돌아보기 저장) 트랜잭션의 액자·검색 문서 등록과 임베딩 주기 작업은 내부 API가 아니다([시퀀스 3.8·3.10](sequence-diagram.md), [상태 3.7](state-diagram.md))

### 4.2 ai-service (호출: learning, core, report)

구현된 경로의 요청·응답 계약: [contracts/openapi/ai-service.yaml](../../contracts/openapi/ai-service.yaml) (`scripts/tests/test_ai_openapi.py`가 라우터 경로와 대조)

| Method | Path | 호출자 | 요청 → 응답 |
|---|---|---|---|
| POST | `/internal/judgments` | learning | `{answerText, inputType, grade, rubric{elements[]}, versions, question?, keywords?, essayType?, answerKey?, solution?}` → `{result, elements[{elementId, quote, verified, satisfied}], heldReason, trial, versions, modelScores}` (scoring 교차 확인 4.2.2) |
| POST | `/internal/followups` | learning | `{timeline[], judgment, rubric, mission, grade}` → `{type, question, source, leakCheck{passed}, versions}` (정답·금지어 검사 실패 시 1회 재생성 `LLM_RETRY`, 재실패 시 `question` 없이 `leakCheck.passed = false` → learning이 질문 은행 `BANK` 선택, P16) |
| POST | `/internal/analysis/stream` | core | **SSE**. `{conversationId, question, scope{studentId, from, to}, history[], report?}` → 3.3과 같은 이벤트. `report`는 일일 리포트 고정 대화(2.4, #392)의 요약 `{reportId, revision, date, metrics[{label, count}], problems[{title, context, judgment, elements[{label, satisfied}]}]}`, 있으면 `from = to = date` |
| POST | `/internal/report-narratives` | report | `{metrics[], thinkingTypes[], changes[], reflections[], quotes[], tone?}`(tone 생략 시 DEFAULT, #209) → `{narrative, eveningQuestion, citedQuotes[], versions}` (4.2.1) |
| POST | `/internal/report-explanations` | report | `{grade, inputType, text, scores}` → `{active:true, explanation:{text, quote}, versions}` 또는 `{active:false}` (4.2.3, #477) |
| GET | `/internal/versions` | core | 현재 호출에 사용하는 프롬프트 버전 `{prompts:{judgment,followup,analysis,reportNarrative,reportTemplate,missionDraft,reportExplanation,themeDraft}}` (#280 `reportTemplate`, #354 `missionDraft`, #477 `reportExplanation`, #437 `themeDraft` 추가. core에 이 응답을 읽는 코드는 없음) |
| POST | `/internal/analysis/report-template` | core | `{question, current}` → `{settings}` 또는 `{clarification}` 중 하나 (#209, 2.4). 미보유 활성 본문은 503 `AI_PROMPT_VERSION_UNAVAILABLE`(#280). core 호출은 별도 서킷 `ai-report-template`(아키텍처 1.3) |
| POST | `/internal/mission-drafts` | learning | 미션 초안 1회 생성·검사 (#354, FN-ADM-20). `{standards:[{code, statement, level?:{grade, text}}], thinkingType, elementCodes:[{code, label, description}], gradeMin, gradeMax, inputType, previousFailures:[{check, reason}]}` → `{draft:{title, question, guide, sceneNote, choices?, categories?, answerKey?, exampleAnswer?, forbiddenTerms[], hints[], elements:[{code, label, description, goodThought, standardCode}]}, checks:{passed, failures:[{check, reason}]}, versions:{prompt, model}}`. `level`은 성취수준 문장이 있을 때만, `elementCodes`는 learning이 FN 1.5 표에서 그 유형 코드와 입력 방식에 맞는 정답 코드를 채움(코드 목록은 learning 소유). ai 검사 `check`: `REQUIRED`(필수 항목·입력 방식별 선택지·정답 키·예시 답), `QUESTION_LENGTH`(`TOO_LONG`, `gradeMin` 학년의 상한, 설정 `MISSION_DRAFT_QUESTION_MAX_CHARS` 기본 전 학년 200자, P19 확정 전 기준안), `LEAK`(질문·안내·생각 열기 질문 속 정답 키·금지어 노출과, 안내·생각 열기 질문 속 예시 답 노출(질문에 이미 있는 글은 빼고 비교, 질문은 예시 답과 비교하지 않음), `reason`은 되묻기 노출 검사 코드 `ANSWER_KEY`·`FORBIDDEN_TERM`·`EXAMPLE_ANSWER` 그대로. 정답 키 글은 고르기면 정답 선택지 이름, 풀이면 최종 답이고 숫자뿐인 답은 숫자 경계로 비교, 순서·분류는 비교하지 않음). 검사 실패도 `200`(`checks.passed=false`), 형식에 맞는 초안을 못 만들면 `502 AI_BAD_RESPONSE`, 그 밖 LLM 실패는 `503 AI_UNAVAILABLE`(둘 다 `retryable`). 호출 1번에 생성 1회이고 재생성 반복은 learning이 함. 시간은 P12 예외(#353): LLM 60초 1회(재시도 없음)·마감 63초, learning→ai 대기 70초. 주기 작업이라 기다리는 사람이 없고, 기본 모델 `gpt-6-luna`가 실제 성취기준으로 15~31.7초 걸림(ai.md 9.2). LLM 입력에 학생 정보 없음. 사용량 `callType = MISSION_DRAFT`(core #355가 받음. 그 전에 발행된 메시지는 core 소비자가 거부해 DLQ에 남아 있음). 근거 칸 `knowledge`·응답 `sources`는 4.2.5(#464 C7, 구현 전) |
| POST | `/internal/theme-drafts` | learning | 주간 테마 초안 1회 생성 (#437, 에픽 #436, FN-ADM-22). `{gradeMin, gradeMax, weekStart, topic?, missions:[{thinkingType, inputType, standards:[{code, statement, level?:{grade, text}}], elementCodes:[{code, label, description}]}], previousFailures:[{stage, reasons[]}]}` → `{theme:{title, world, characters, styleNote, outfit, intro, outro, bigQuestion, candidates[], answer, days:[{day, thinkingType, place, sceneNote, clue, rulesOut[]}]}, missions:[{day, thinkingType, draft}], dialogues:[{day, lines:[{speaker, text}]}], images:{장면: key}, videos:{INTRO|OUTRO: key}, motions:{장면: motion}, warnings:[{stage, item, reason}], failure:{stage, reasons[]} 또는 null, versions:{prompt, model}}`. `missions`는 유형 5개에 1개씩이고 성취기준·요소 code·입력 방식은 learning이 채움(코드 목록은 learning 소유). 학년별 테마(`G3`~`G6`, #438)라 `gradeMin = gradeMax`. 응답 `draft`는 위 `/internal/mission-drafts`의 `draft`와 같은 모양이고 같은 검사(`REQUIRED`·`QUESTION_LENGTH`·`LEAK`)를 거침. 단서 `days[].clue`는 학생이 그날 미션을 학습 완료한 뒤 보여 줄 글(learning #484 구현)이라 미션·대화에는 그날 단서 결론을 쓰지 않음: `dialogues[].lines`의 끝 두 줄은 단서가 아니라 그날 증거 발견 줄과 뭉치의 수사 연결 문장(미션 질문에는 다시 쓰지 않음, 앞 요일 요약 줄 없음), 금요일 `draft.guide`에 단서 목록을 넣지 않음(최종 후보 고르기는 화면, 사용자 결정 2026-11-11, 응답 모양은 그대로). 장면은 `INTRO`·`OUTRO`·`MON`~`FRI` 7개. 요일 배치는 ai가 기준안(월 `ANALYZE`·화 `EVALUATE`·수 `CREATE`·목 `SOLVE`·금 `REFLECT`, 에픽 확인 필요)대로 정해 `day`로 돌려주고 learning이 다시 검사. 큰 질문·정답: 후보 기준안 모든 학년 4개(사용자 결정 2026-11-10, 3개면 월~수에 1개만 뺄 수 있어 단서가 밋밋해짐), 정답은 후보 중 하나이고 요일별 단서 5개마다 빠지는 후보 `rulesOut`. `rulesOut`은 빈 배열일 수 있음(그때 남은 후보를 하나도 빼지 않는 힌트 단서. 남은 후보를 빼는 내용이면 빈 배열이 아니라 그 후보를 적음). `rulesOut`이 비지 않은 단서는 그때 남은 후보를 적어도 하나 새로 뺌(이미 빠진 후보만 다시 빼는 단서는 빈 배열), 그래서 `rulesOut`이 비지 않은 마지막 요일이 마지막 틀린 후보가 빠지는 날(learning 결정적 단서 계산, #438). 정답은 어떤 단서로도 빠지지 않고, 틀린 후보는 각각 적어도 한 단서에서 빠지며, 마지막 틀린 후보는 목요일 이후 단서에서 빠짐(기준안, 금요일 전에 답이 드러나지 않게). ai 코드 검사. 정답은 종료 이야기에만 쓰고 문제·대화·생각 열기 질문·예시 답에 나오면 유출. 그래프 안에서 실패한 부분만 다시 만들고(상한), 끝내 실패하면 `200`에 `failure.stage`(`THEME`·`MISSION`·`REVIEW`·`IMAGE`)와 사유를 담음(learning `CHECK_FAILED`). 실패해도 그때까지 만든 테마·미션·대화를 함께 돌려줌(줄거리 단계에서 끝내 실패하면 `theme`은 `null`), learning은 받은 결과를 `output`에 그대로 저장해 관리자 상세에서 보여 줌(미션 초안이 검사 실패에도 초안을 돌려주는 것과 같은 방식, 사용자 결정 2026-11-10). 대화·영상·움직임은 끝내 실패해도 그 항목만 빼고 성공으로 돌려주고 `warnings`에 남김(영상은 컷 하나가 끝내 검토를 통과하지 못하면 그 컷만 첫 그림을 천천히 확대하는 움직이는 그림 컷으로 대신하고 장면 영상은 남김, 2026-11-11). 검토 LLM(생성과 다른 모델, 기준안 생성 `gpt-6-luna`·검토 `gpt-6.1-terra`. 검토 제공자·모델은 설정이라 팀 키가 생기면 다른 제공자로 바꿀 수 있음)의 애매한 항목도 `warnings`. 형식 밖 LLM 응답은 `502 AI_BAD_RESPONSE`, 그 밖 실패·마감 초과는 `503 AI_UNAVAILABLE`(둘 다 `retryable`, learning `FAILED`). 다시 부를 때 learning이 이전 시도들의 `failure`를 그대로 `previousFailures`에 넣음. `previousFailures[].stage`는 `THEME`·`MISSION`·`REVIEW`·`IMAGE`만(그 밖 `422`). learning 검사 실패는 요일·유형 배치·정답 논리면 `THEME`, 미션 게시 규칙이면 `MISSION`으로 바꿔 넣고 AI 호출 실패는 넣지 않음. `MISSION` 사유는 `"<요일> <검사 코드> <자세히>"`(요일 `MON`~`FRI`)로 시작(사용자 결정 2026-11-10, #438과 맞춤). `IMAGE` 사유는 ai가 돌려준 그대로이며 그림 이름(`MON`~`FRI`·`INTRO1`~`INTRO4`·`OUTRO1`~`OUTRO4`)으로 시작하면 그 그림에만, 아니면 모든 그림에 넣음(2026-11-11). 이미지·영상은 ai가 S3에 올리고 키만 돌려줌(경로 `theme-drafts/{ai가 만든 실행 ID}/{장면}.png`·`.mp4`, 버킷·쓰기 권한은 인프라 확인). 그림은 장면 7장(`MON`~`FRI`는 그날 미션 그림, `INTRO`·`OUTRO`는 영상 4번째 컷 첫 그림, 2D 만화풍, 앱 솜뭉치 모양 기본 뭉치를 고정 참조). 영상은 시작·종료(`INTRO`·`OUTRO`)만이고 장면마다 컷 4개(4·6·8·6초, 컷 첫 그림만 고정, 컷마다 장소·각도 다름)를 0.5초 녹아드는 전환으로 이은 22.5초(요일 문제 전 영상 없음, 사용자 결정 2026-11-11). 그림 설정(버킷·키)이 없으면 그림·영상·움직임을 건너뛰고 `warnings`에 `IMAGE`(`item` `ALL`) 하나, 영상 설정이 꺼져 있으면 `VIDEO`(`item` `ALL`) 하나. 움직임은 장면마다 JSON 형식 v1 `{version, transition:{kind, seconds}, camera:{from:{x, y, zoom}, to, seconds} 또는 null, speakers:{이름: {x, y, zoom}}, effects:[{shape, color, count, size, direction, speed, opacity}], captions:[{start, end, text}], spots:[{x, y, label, line, evidence}]}`(좌표는 그림 너비·높이 %, `spots`는 요일 장면 살펴보기로 문제 전에 누르는 그림 속 물건 2~3개(증거 물건 1개, 이름 10자·한마디 30자 기준안, 단서 결론·후보·정답 이름 금지, 시작·종료는 빈 배열, 2026-11-11 추가 선택 칸이라 version 1 유지), `captions`는 시작·종료 영상 위에 웹이 띄우는 컷 문구로 컷 경계는 겹치는 구간 한가운데, 영상 속 글자 없음). learning은 받은 그대로 저장·전달. 시간: ai 마감 15분, learning→ai 대기 16분(기준안, 에픽 9분·10분에서 변경, 실측 후 조정). 주기 작업이라 기다리는 사람이 없음. LLM 입력에 학생 정보 없음. 사용량 `callType` `THEME_DRAFT`(글 생성·검토)·`THEME_IMAGE`·`THEME_VIDEO`. `THEME_VIDEO`는 사용량 이벤트 스키마와 core enum·DB 제약에 먼저 들어간 뒤에만 보냄(그 전에 보내면 core 소비자가 거부해 DLQ에 남음, `MISSION_DRAFT` 선례. core 마이그레이션은 core 담당이 준비) |
| POST | `/internal/embeddings` | learning(추억 검색, P27 설계), 스크립트(관계 후보), ai 내부(검색 질의) | 교육과정 지식 본문·질의, 추억 검색 문서·질문 임베딩(#463, 계약 #464 C6, 구현 #467). `{texts[]}` → `{model, dimensions, vectors[]}`, 4.2.4 |
| POST | `/internal/memory-explanations` | learning | 추억 설명 1회 생성(P27, 설계·구현 전). `{query, evidence:[{no, themeTitle, missionQuestion, answerExcerpt, weekLabel}]}` → `{text, citations:[no], versions}`, 4.2.6 |

- #68 프롬프트 레지스트리의 `PROMPT name`은 위 응답의 여덟 키와 같다. 승인 scope는 차례대로 `ai/judgment`·`ai/followup`·`ai/analysis`·`ai/report-narrative`·`ai/report-template`·`ai/mission-draft`(#354 `missionDraft`)·`ai/report-explanation`(#477 `reportExplanation`)·`ai/theme-draft`(#437 `themeDraft`)이며 요청 범위 밖 이벤트는 적용하지 않는다. core에 해당 활성 항목이 없으면 ai 이미지에 포함된 기존 본문·버전을 사용한다. 활성화된 버전의 실제 본문이 이미지에 없으면 해당 기능의 새 요청과 `/internal/versions`는 `503 AI_PROMPT_VERSION_UNAVAILABLE`로 실패하고 `/health/ready`의 `versions`는 DOWN이다. 기존 본문을 새 버전명으로 보고하지 않는다. 진행 중인 요청은 시작 때 선택한 본문·버전으로 완료한다. 추억 설명(4.2.6) 구현 때 키 `memoryExplanation`·scope `ai/memory-explanation`을 더한다(P27, 설계).

#### 4.2.2 판정 모델 교차 확인 (#69, 2026-11-03)

- 선택 입력: `question`(mission_version.question, M2 `prompt`·M1 `problem`), `keywords`(rubric_version.keywords, 서술 핵심어 묶음 배열, 생략 시 빈 배열), `essayType`(rubric_version.essay_type, 설명글·글짓기·주장·찬성반대·대안제시), `answerKey`(M1 정답 문자열), `solution`(`{steps[], finalAnswer}`, M1 학생 풀이). learning은 현재 앞의 세 항목만 보낸다. M1은 지금 운영하는 모델이 아니어서(M1 미지원) `answerKey`·`solution` 전달은 M1 활성화 때 scoring 응답 확정과 함께 한다(#501). 그래서 지금은 `M1_CHECK_ENABLED=true`로 켜도 M1을 부르지 않고 `modelScores.skipped`에도 남기지 않는다.
- M2 호출: `M2_CROSS_CHECK_ENABLED=true`이고 LLM 판정 결과가 보류가 아니며 `inputType`이 NARRATIVE·ESSAY이며 `question`이 있을 때 `POST /internal/m2/scores`(4.3.1)를 부른다. 서술은 `keywords`가 비어 있으면, 논술은 `essayType`이 없으면 호출하지 않는다. 학년·승인 범위 판단은 scoring이 하며 `{active:false}`면 LLM 판정을 그대로 쓴다. M2 text는 `answerText`다.
- 불일치 기준(임시, 설정값): M2 `scores` 평균을 서술 9항목·논술 3영역으로 구한다. LLM 결과가 `CORRECT`인데 평균이 낮은 경계 이하(서술 `M2_NARRATIVE_LOW=2.0`, 논술 `M2_ESSAY_LOW=1.0`)이거나, `RETHINK`인데 높은 경계 이상(서술 `M2_NARRATIVE_HIGH=4.0`, 논술 `M2_ESSAY_HIGH=2.0`)이면 불일치다. `PARTIAL`은 불일치로 보지 않는다. 경계는 M2 담당 확인 전 임시값이다.
- `M2_CROSS_CHECK_ENABLED`는 기본 `false`다. 꺼져 있으면 scoring M2를 부르지 않고 LLM 판정만 쓴다(`modelScores`는 `null`, LLM은 판정 마감 전체 사용). 켜져 있고 불일치면 `HELD(MODEL_DISAGREEMENT)`이며 `elements`는 빈 목록이다. #69의 "꺼져 있어도 점수·불일치를 기록" 동작은 #305에서 없앴다.
- M1 점검: `M1_CHECK_ENABLED`(기본 `false`)이고 SOLUTION_STEPS이며 `question`·`answerKey`·`solution`이 모두 있을 때만 `POST /internal/m1/checks`(4.3.2)를 부른다. 현재 scoring은 항상 `{active:false}`다. ai가 기대하는 활성 응답은 `{active:true, confidence(0~1), model:{name,version,revision}}`이며 M1 활성화 때 scoring과 확정한다. `confidence < 0.8`(`M1_MIN_CONFIDENCE`)이면 `HELD(LOW_CONFIDENCE)`, 실수 위치는 표시하지 않는다(P15).
- `modelScores`: `null` 또는 `{m2, m1, skipped}`. `m2`는 `{inputType, scores, rawScores, model{name,version,revision}, mean, disagreement}`, `m1`은 `{confidence, model}`이며 호출하지 않았거나 비활성이면 `null`이다. `skipped`는 아래 장애로 교차 확인을 생략했을 때만 값이 있고 정상이면 `null`이다. scoring을 부르지 않았거나 모두 비활성이면 `modelScores` 자체가 `null`이다. learning은 그대로 `judgment.model_scores`에 저장하고 학생 화면에 보이지 않는다(AI 관찰).
- `versions.model`: M2(또는 M1)가 활성 응답을 주면 `"{name}@{version}"`, 아니면 LLM 모델 ID다. LLM 모델 ID는 사용량 이벤트에만 남는다.
- 장애(#305): scoring 실패는 `503`으로 바꾸지 않고 교차 확인을 생략한 채 LLM 판정 결과를 200으로 돌려준다. `modelScores`는 `{m2:null, m1:null, skipped}`이고 `versions.model`은 LLM 모델 ID다. `skipped`는 5xx·시간 초과·연결 실패·남은 시간 부족이면 `SCORING_UNAVAILABLE`, 400 등 4xx(M2 입력 토큰 한도 초과 포함)·계약 밖 응답이면 `SCORING_REJECTED`다. `{active:false}`(비활성)와는 구분해 기록한다. ai는 경고 로그를 남긴다. 판정 응답이 200이므로 learning `ai` 서킷(판정·되묻기 공용)에 scoring 장애가 실패로 집계되지 않는다(아키텍처 1.3). 서비스 간 재시도는 없다. 한계: learning 관리자 기준표는 keywords 100개·각 200자를 허용하지만 scoring M2 토큰 한도를 넘으면 그 미션의 판정은 매번 `SCORING_REJECTED`로 교차 확인이 생략된다(입력 제한 조정은 이번 범위 밖).
- 시간 예산(P12): 판정 전체 마감은 `JUDGE_DEADLINE=33`초다. M2·M1을 부를 입력이 있으면 LLM 근거 추출은 마감에서 scoring 몫 `SCORING_RESERVE=3`초를 뺀 30초 안에서만 요청·재시도한다(LLM 1회 15초 + 대기 1초 + 재시도는 남은 14초로 줄어듦). 입력이 없으면 LLM이 33초 전체를 쓴다. scoring 호출 한도는 `SCORING_TIMEOUT=10`초와 남은 시간 중 작은 값이라 LLM이 최악 경로를 가도 3초 이상 남는다. 남은 시간이 1초 미만이면 scoring을 부르지 않고 `skipped: SCORING_UNAVAILABLE`로 LLM 판정만 쓴다. 최악 33초로 learning→ai 35초보다 2초 짧다.

#### 4.2.1 report 서술 요청·응답

- 요청 항목은 report 계산 결과(3.4 `metrics`·`thinkingTypes`·`changes`·`reflections`·`quotes`)를 그대로 보낸다. `quotes[]`는 인용 후보 `{attemptId, answerId, answerVersion, text}`이며 `answerVersion`은 해당 답변 근거의 버전이다(3.4 상세 `quotes`에는 없음). 대조 전 값인 `verified`는 ai가 무시한다. 다섯 배열은 필수(빈 배열 허용)다.
- ai는 인용을 후보 번호와 원문 구절로 고르고, 구절이 그 후보 `text`의 부분 문자열이 아니면 `citedQuotes`에서 제외한다. `attemptId`·`answerId`·`answerVersion`은 후보 입력값을 쓴다. LLM 실패·키 미설정·빈 서술이나 빈 저녁 질문은 503 `AI_UNAVAILABLE`(+`retryable`)이다.
- 응답은 `{narrative:{text,source:"LLM",modelExplanation:null},eveningQuestion,citedQuotes:[{attemptId,answerId,answerVersion,quote}],versions:{prompt,model}}`로 정의한다. 원문 인용은 citedQuotes에 명시하며 답변 버전과 연결한다. ai는 숫자를 새로 계산하거나 수치 레벨·등급·사고력 향상을 단정하지 않는다.
- report는 learning evidence의 같은 answer ID·version·원문과 인용을 대조하고, 서술·저녁 질문의 숫자가 계산 결과에 포함되는지 검사한다. 지원하지 않는 한글 수사 표현은 검증 통과로 간주하지 않는다. 검증 메타데이터는 `numbersMatched`, `quotesMatched`, `contentAllowed`다.
- 대조 실패만 코드 기반 템플릿 요약으로 전환한다. AI 시간 초과·5xx·응답 스키마 오류·learning 원문 조회 실패는 `FAILED`로 처리한다. 학생 이름·닉네임 필드는 요청에 넣지 않으며, 알려진 닉네임이 본문에 포함된 경우 전송 전에 가린다.
- LLM 요청에는 학생 이름·식별정보를 넣지 않음. 학생·시도·답변 ID도 넣지 않으므로 가명 토큰이 필요 없음(원문은 요청 안 번호로만 지칭) (NFR-SEC-03)

#### 4.2.3 report 설명 요청·응답 (FN-RPT-09, #477)

- `POST /internal/report-explanations`, 호출자 report. 대표 답변 1개당 1회 호출한다(학생·주당 최대 3회)
- 요청 `{grade(3~6), inputType:"NARRATIVE"|"ESSAY", text, scores}`. `text`는 학생 작성 칸 평문(공백만이면 400), `scores`는 learning `modelScores.m2.scores` 그대로다. 서술은 9개 키(`hol` 1~4, 나머지 1~5), 논술은 `org`·`cont`·`exp`(0~3) 3개 키가 정확히 있어야 하며 아니면 `400 VALIDATION_FAILED`. 학생·시도·답변 ID와 이름·닉네임은 넣지 않는다(NFR-SEC-03)
- 활성 확인: core 모델 레지스트리의 `MODEL` `report-explanation`이 scope `explanation/grade-{grade}/{narrative|essay}`에 활성이어야 한다(활성 목록·`model.version.activated`로 받음, #480). 아니면 sLLM을 부르지 않고 `200 {active:false}`
- 설명 항목: 가장 높은 항목 1개(잘한 점) + 가장 낮은 항목 1개(함께 이야기해 볼 점). 동점은 항목 표 순서(서술 과제 수행→명료성→구체성→적절성→연결성→통일성→어휘→어법, 논술 구성→내용→표현)로 앞선 항목, 모든 항목이 같은 점수면 1개(범위 중간 이상이면 잘한 점, 아니면 함께 이야기해 볼 점). 서술 총점 `hol`은 고르지 않는다
- 생성: 항목마다 설명 전용 OpenAI 호환 클라이언트(`EXPLANATION_BASE_URL`, 다른 호출의 LLM 제공자는 그대로)로 평문 1회, 재시도 없음. 입력 형식은 #475 학습 쌍과 같다([AI 보고서](../report/ai.md)). 사용량 `callType = REPORT_EXPLANATION`(#480), 프롬프트 이름 `reportExplanation`
- 규칙 후처리·검사: 숫자나 금지어(레벨·등급·점수·사고력 등, 분석 대화 검증과 같은 목록)가 있는 문장은 버리고 항목당 앞 2문장까지 남긴다. 남는 문장이 없는 항목이 하나라도 있으면 `422 AI_EXPLANATION_REJECTED`(`retryable:false`)
- 응답 `{active:true, explanation:{text, quote}, versions:{model, prompt}}`. `text`는 `잘한 점: …`·`함께 이야기해 볼 점: …` 줄(1~2줄), `quote`는 설명과 낱말(앞 두 글자 기준)이 2개 이상 겹치는 학생 글 문장 중 가장 많이 겹치는 문장(원문 부분 문자열), 없으면 null이다. `versions.model`은 레지스트리 `이름@버전`
- 오류: 설명 sLLM 주소 미설정·호출 실패·마감 초과는 `503 AI_UNAVAILABLE`(+`retryable`). 시간 초과·5xx·422는 리포트 생성 실패로 바꾸지 않는다. report는 해당 설명만 빼고 `explanations.state = NOT_INCLUDED`로 저장한다(P16)
- 시간 기준안(#475 CPU 실측 전 임시값, P12 예외: 주 1회 배치라 기다리는 사람이 없음): 항목 1회 `EXPLANATION_LLM_TIMEOUT=60`초, 요청 전체 마감 `EXPLANATION_DEADLINE=125`초. report→ai 대기는 아래 #479 시간 기준안(호출당 130초·단계 400초)을 따른다

- #479 연동 기준(PR #489·#491): report는 SYSTEM 범위로 기록 목록에 `includeModelScores=true`를 붙이고 `modelScores.m2.scores`를 설명 요청의 `scores`로 전달한다. core의 기존 SYSTEM 전용 학생 프로필에 `grade`(저장 학년 3~9)를 추가한다. 학년 누락·지원 범위 밖이면 설명만 제외하며 임의 학년을 만들지 않는다.
- #479의 인용은 PR #491과 같이 nullable이다. `quote=null`이면 인용 영역을 생략하고, 값이 있으면 해당 답변·버전의 실제 원문 부분 문자열인지 다시 검사한다. 설명 문장에 숫자·점수·등급·금지 표현이 있으면 그 설명만 제외한다. 상세 `explanations.items[].quote`도 null을 허용한다.
- #479 시간 기준안: 설명 호출당 130초(AI 마감 125초보다 길게), 답변 선정·근거 확인을 포함한 설명 단계 전체 400초. 각각 `REPORT_EXPLANATION_TIMEOUT_SECONDS`, `REPORT_EXPLANATION_BUDGET_SECONDS`로 조절한다. 최대 세 답변을 순차 호출하고 재시도하지 않는다. 실제 CPU 실측 전 임시값이며 만료 시 이미 검증한 설명만 유지한다. sLLM 가동 창(일 23:50~월 02:00, #476) 밖의 호출은 실패로 끝나 그 리포트의 설명만 빠진다(`NOT_INCLUDED`, P16). 생각 유형마다 최신 답변부터 시도하며 ai 호출 전 제외(정정·빈 답변·학년·입력 유형·점수 형식·원문 대조 실패)는 같은 유형의 다음 답변으로 넘어가고, ai를 한 번 부른 유형은 결과와 관계없이 다시 부르지 않는다(#508).
- #479 저장: 설명 상태는 기존 `weekly_report.verification` JSONB의 `explanationState`에 보관하고 설명 본문은 `EXPLANATION` 항목·근거 테이블에 저장한다. 이전 리포트에 상태가 없으면 `explanations=null`, 일일·무료 응답/파일도 null이다. 기존 요약 검증 결과와 설명 검증 결과는 독립적이다.

#### 4.2.4 지식 임베딩 (#463, 계약 #464 C6, 구현 #467)

**#467에서 구현**. ai OpenAPI `/embeddings`, 모델 `contracts.py` `EmbeddingRequest`·`EmbeddingResponse`, 라우터 `app/embedding/`, 제공자 `app/llm/embeddings.py`.

- `POST /internal/embeddings` `{texts:[string]}` → `200 {model, dimensions, vectors:[[number]]}`. `vectors`는 `texts`와 같은 순서·같은 개수. 내부 토큰만 확인한다(4.2 다른 경로와 같음)
- 입력은 교육과정 지식 본문(C2 조각 본문)과 검색 질의 문장만. 학생 정보·학생 답은 받지 않는다(FN-ADM-20 원칙)
  - 2026-11-12 P27(설계·구현 전): learning 추억 검색이 검색 문서(테마·미션 + 학생 최종 답변)와 학생 질문도 보낸다. 판정과 같은 기준으로 학생 이름·학생·시도·답변 ID를 넣지 않고 알려진 닉네임은 가린다(NFR-SEC-03). 사용량을 구분하려고 요청에 `purpose`(`KNOWLEDGE`·`MEMORY`, 생략 시 `KNOWLEDGE`, 기준안)를 더하고 `MEMORY`는 `callType = MEMORY_EMBEDDING`으로 기록한다(core 허용 목록 확장 뒤에만 보냄)
- 상한(기준안, #467): 한 요청 `texts` 1~64개, 본문당 1~8,000자. 넘거나 빈 글·공백만이거나 `texts` 밖 칸이 있으면 `400 VALIDATION_FAILED`. 64개를 넘는 적재는 부르는 쪽이 나눠 보낸다
- 모델·차원(기준안, 에픽 #463): OpenAI `text-embedding-3-small`, 1536차원. 설정값(`EMBEDDING_MODEL`·`EMBEDDING_DIMENSIONS`, OpenAI 요청에 `dimensions`로 보냄)이며 응답에 함께 돌려줘 learning이 판(`knowledge_dataset.embedding_model`·`embedding_dimensions`, C2)과 다른 벡터를 넣지 않게 한다
- 오류: 제공자 응답의 벡터 개수·차원이 맞지 않음 `502 AI_BAD_RESPONSE`, 제공자 미설정·호출 실패·시간 초과 `503 AI_UNAVAILABLE`(둘 다 `retryable`, 기존 `AI_*` 실패 코드와 같은 방식)
- 제공자(#467 결정): `EMBEDDING_PROVIDER=openai`(기본)|`fake`. openai는 `OPENAI_API_KEY`를 쓰고 `OPENAI_BASE_URL`(sLLM 대화용)은 쓰지 않아 항상 OpenAI 기본 주소로 보낸다. 키가 없으면 임베딩만 `503`(`retryable=false`). 제공자 요청 1회 타임아웃·재시도·대기는 LLM 공통 값(P12 15초·1회·1초)을 그대로 쓰고, 재시도 대상은 시간 초과·연결·429·5xx·개수/차원 불일치다. 한 요청의 `texts`는 OpenAI에 한 번에 보낸다
- 사용량: 기존 `llm.usage.recorded`로 제공자 요청 1회마다(재시도 포함) 1건, `callType`은 `KNOWLEDGE_EMBEDDING`(4.6, core V44). 입력 토큰만 있고 출력 토큰은 `0`, `promptVersion`은 null. `fake`는 외부 호출이 없어 기록하지 않는다
- 가짜 구현(개발용, `app/knowledge/fake.py` `FakeEmbedder`): 모델 이름 `fake-bigram-v1`. 벡터 = NFC·소문자·공백 제거 → 글자 2개씩(한 글자면 그 글자) → 조각마다 SHA-256 앞 4바이트(big endian) % 차원 위치에 5번째 바이트가 짝수면 +1·홀수면 −1 → 길이 1로 맞춤(모두 0이면 0번 위치 1.0). 같은 글은 언제나 같은 벡터라 learning 시험 대역(#466)이 같은 규칙으로 만들 수 있다

#### 4.2.5 미션 초안 근거 칸 (#463, 계약 #464 C7, 구현 #470)

**구현 전 계약(기준안, 팀 확인 전)**. 미션 초안 요청·응답(4.2 `/internal/mission-drafts`)에 칸을 더한다. ai OpenAPI `MissionDraftRequest.knowledge`·`MissionDraftResponse.sources`(`x-implementation-status: planned-issue-470`).

- 요청 `knowledge`(선택, null 허용): learning 미션 초안 작업이 요청 성취기준 코드·생각 유형·`gradeMin`으로 4.1.2 `GET /internal/knowledge/standards?codes&grade&thinkingType`를 조회해 **응답 본문 그대로** 넣는다. 조회 실패·`reason` 있음이면 칸을 비우고 진행한다(기존 동작 보존)
- 응답 `sources:[{kind, id, datasetVersion}]`: ai가 프롬프트에 넣은 근거 조각 표시(`contracts.sources_of`: 성취기준·영역·내용 요소·교과 지침·유형 지침 순서, 중복 제거). 근거 없이 생성했으면 빈 배열
- learning은 `sources`를 초안과 함께 저장하고 관리자 초안 상세(P19)에 보여 준다. 저장 칸·관리자 화면·core 프록시 모양은 #470에서 팀 확인 후 정한다
- 테마 초안(#437) 미션 생성도 같은 근거 묶음·`sources` 모양을 쓴다(그래프 쪽 반영은 #470)
- 프롬프트 문구가 바뀌면 프롬프트 버전을 올린다(`mission-draft@2` 등, #470)

#### 4.2.6 추억 설명 (P27, 설계·구현 전)

**구현 전 계약(기준안)**. 2026-11-12 리텐션 확장 결정([결정 기록](../report/retention-expansion.md)). 호출자 learning(4.1.4 설명).

- `POST /internal/memory-explanations` `{query, evidence:[{no(1~3), themeTitle, missionQuestion, answerExcerpt, weekLabel}]}` → `200 {text, citations:[no], versions:{prompt, model}}`
- 입력: 학생 질문과 근거 1~3개. 근거는 요청 안 번호로만 지칭하고 학생 이름·학생·시도·답변 ID를 넣지 않는다. 알려진 닉네임은 learning이 보내기 전에 가린다(NFR-SEC-03, 4.2.1과 같은 방식)
- 생성: ai 기본 LLM 설정으로 1회(P12 15초·재시도 1회). 2~3문장, 문장마다 근거 번호, 근거에 없는 활동·감정·의도·능력 변화 추정 금지, 원문 인용은 따옴표로 근거 문장 그대로
- 검사: `citations`가 비었거나 보낸 번호 밖이면 `422 AI_EXPLANATION_REJECTED`(`retryable:false`). 인용 원문 대조는 learning이 다시 한다
- 오류: LLM 실패·시간 초과 `503 AI_UNAVAILABLE`(+`retryable`), 형식 밖 응답 `502 AI_BAD_RESPONSE`. learning은 422·5xx를 모두 설명 `FAILED`로 돌려 검색 결과는 유지한다
- 사용량 `callType = MEMORY_EXPLANATION`(core 허용 목록 확장 뒤에만 보냄), 프롬프트 이름 `memoryExplanation`. 요청·응답 원문은 저장·로그하지 않는다(NFR-SEC-05)


### 4.3 scoring-service (호출: ai)

#### 4.3.1 #228 M2 확정 계약 (2026-11-02 담당자 답변 반영)

- `POST /internal/m2/scores`: `{prompt:string, text:string, grade:integer(3~6), inputType:"NARRATIVE"|"ESSAY", keywords:string[], essayType?:string}`. keywords 생략은 빈 배열. ESSAY에는 essayType(설명글·글짓기·주장·찬성반대·대안제시)이 필수다. prompt는 기존 요청 호환을 위해 유지하지만 새 모델 입력에는 넣지 않는다. prompt 10,000자, text 50,000자, keywords 100개·각 200자이며 공백만 있는 문자열은 거부한다.
- 서술 `m2-klue-narrative` 3.0은 초5·6, 논술 `m2-klue-essay` 3.1은 초4·5·6을 지원한다. 지원 학년 밖·미활성·승인 scope 밖·핵심어 없는 서술은 200 `{active:false}`. 논술은 핵심어를 사용하지 않는다.
- 승인 scope는 `judgment/grade-{grade}/{narrative|essay}` 정확 일치. 로컬 검증 승인은 운영 품질 승인으로 간주하지 않는다.
- 성공 응답은 `{active:true,inputType,scores,rawScores,model:{name,version,revision}}`. 서술의 두 점수 객체는 기존 9개 키(hol·task_1·content_1~3·organization_1~2·expression_1~2), 정수 hol 1~4·나머지 1~5를 유지한다. 논술 3.1은 두 객체 모두 `{org,cont,exp}`(구성·내용·표현)이며 scores는 0~3 정수다. rawScores는 유한 소수 원점수를 반올림하거나 범위로 자르지 않고 그대로 전달한다. 논술 학습 목표 범위는 0~3이나 회귀 예측의 범위 초과도 보존한다. 14출력 중 앞 3개만 반환하고 뒤 11개는 노출하지 않는다.
- 점수 변환은 score_cuts.json의 경계에 `bisect_right` 적용: 서술은 +1, 논술은 +0. 경계와 같으면 위 점수다. 논술 경계는 담당자가 제공한 임시 기준으로, 업데이트 시 파일 교체와 재검증이 필요하다. 화면에 정수/소수 중 무엇을 표시할지는 소비 측 결정이다.
- 새 서술 입력은 `[학년] 초N [핵심어] ` + `", ".join(keywords)`, 논술은 `[학년] 초N [글 종류] {essayType}`. 두 번째 문장은 text다. train_info의 no_prompt·max_length와 체크포인트 구조를 검증하며 truncation=only_second, token_type_ids 제외를 유지한다. 기존 2.0 rollback 호환 시에는 기존 지시문 입력·9항목 응답을 유지하고 논술 4학년은 비활성이다.
- 모델 파일은 버전 폴더 바로 아래 config.json·model.safetensors·tokenizer.json·tokenizer_config.json·train_info.json·score_cuts.json 6개다. 로더는 서술 9출력, essay545 논술 14출력과 메타데이터·경계 형식을 검사한다. 잘못된 파일은 반올림이나 임의값으로 대체하지 않는다. 새 모델 호환 코드 배포 전에 core 활성화하지 않는다.
- learning→AI의 핵심어·essayType 전달 및 구조화 논술 답변을 text로 합치는 규칙은 #69 소비 측 연동 범위다. scoring은 전달받은 text를 그대로 사용한다.
- 내부 토큰 오류 401, 요청/첫 문장 토큰 길이 오류 400, 모델 설정·추론·처리 용량 장애 503 SCORING_UNAVAILABLE. 장애를 active:false로 바꾸지 않는다. 사용량은 추론 성공/실패 후 best-effort 발행하며 원문·학생 ID·핵심어를 넣지 않는다. 비활성 시 추론·사용량 발행 없음.

구현 계약은 [scoring OpenAPI](../../contracts/openapi/scoring-service.yaml), 변경·검증 기록은 [#228](../report/ai.md#41-서술-30논술-31-서비스-호환-228)을 따른다.

##### 서술 content_3 선택 보정 (2026-11-03, 규칙 v1.0.0)

- `M2_CONTENT3_RULE_ENABLED`는 기본 `false`다. 미설정·false이면 위 #228의 모든 원점수·정수 점수와 모델 입력을 그대로 유지한다. true라도 활성 모델이 정확히 `m2-klue-narrative@3.0`이고 NARRATIVE 초5·6 승인 scope일 때만 적용한다. 기존 비활성·검증 오류·장애 처리는 유지한다.
- 적용 시에만 `mixed = clip(0.9724 + 0.197 * 모델 content_3 원점수 + 2.8891 * 핵심어 포함 비율, 1, 5)`로 계산한다. `rawScores.content_3 = round(mixed, 4)`, `scores.content_3 = floor(mixed + 0.5)`다. 정수는 소수 4자리로 반올림하기 전 mixed로 계산하며 score_cuts.json의 content_3 경계를 사용하지 않는다. 나머지 서술 8개 항목·논술·다른 모델 버전은 기존 계약을 유지한다.
- 기준은 담당자 제공 `content3_rule_1103.json`·`content3_rule_1103.py` v1.0.0이다. 요청은 배열 원소 하나당 핵심어 묶음 하나로 보내며 `"한글(훈민정음, 정음)"`을 괄호 안에서 쪼개지 않는다. 참고 구현과 같이 배열을 쉼표·공백으로 연결하고 괄호 밖 쉼표로 묶음을 구분한다. 따라서 `['환경, 보호']`도 두 묶음으로 계산하지만 권장 입력은 `['환경', '보호']`다. 괄호 안 쉼표·슬래시는 대체어를 구분한다.
- 묶음마다 본래 핵심어 또는 대체어 하나라도 text에 있으면 1, 없으면 0이며 전체 묶음의 평균을 사용한다. 비교할 때만 공백 문자를 제거하고 부분 문자열로 검사한다. 모델 tokenizer에 전달하는 text·keywords 원문은 바꾸지 않는다. 여러 대체어가 함께 등장해도 한 묶음은 한 번만 센다.
- 이 설정은 모델 활성화·품질 승인을 대신하지 않는다. 11/22 허용 기준 확정 전 기본 꺼짐을 유지한다. 변경 후 scoring 프로세스를 재시작해야 하며 false로 되돌리면 이후 요청은 기존 계산을 따른다. 응답 model은 실제 사용한 모델 버전을 유지하고, 적용 여부·규칙 버전은 시작 로그 및 배포 설정 이력으로 추적한다.

#### 4.3.2 #88 M1 미학습 상태의 구현 계약

- `problem`은 mission_version.question, `answerKey`는 answer_key.finalAnswer 문자열이다. `solution`은 정답 풀이가 아닌 학생의 `{steps: 문자열 배열, finalAnswer: 문자열}`이다. 단계 순서와 빈 단계의 위치를 보존하며, 최소 한 단계는 공백 아닌 내용이 있어야 한다. 세 최상위 항목과 두 solution 항목은 필수이며 알 수 없는 필드·잘못된 타입·공백만 있는 문제/정답/최종 답은 400이다.
- 내부 토큰 누락·불일치는 401. 유효한 요청은 현재 항상 HTTP 200 `{active:false}`를 반환한다. M1 학습·평가·로더·승인 범위 계약이 없으므로 core에 모델 메타데이터를 등록하는 것만으로 활성화되지 않는다. M2 모델을 대신 사용하거나 문자열 비교로 정답 판정을 흉내 내지 않는다.
- 추론하지 않으므로 M1 사용량 이벤트도 발행하지 않는다. 문항·학생 풀이를 로그에 기록하지 않는다. 기존 내부 인증·오류 처리를 재사용한다.
- #88의 미학습 예외에 따라 이번 완료 범위는 비활성 계약이다. 향후 활성 추론은 기존 ModelRegistry·UsagePublisher를 재사용하고 threadpool에서 실행한다. 확신도 0.8 미만은 scoring이 실수 위치를 제외하고 ai가 보류를 결정한다. 활성 응답 필드·단계 번호 기준과 승인 scope는 활성화 시 확정한다.

| Method | Path | 설명 |
|---|---|---|
| POST | `/internal/m2/scores` | 위 #228 계약. 서술 9항목·논술 3영역의 정수/소수 점수와 실제 모델 버전 반환 |
| POST | `/internal/m1/checks` | `{problem, answerKey, solution:{steps,finalAnswer}}` → 현재 미학습이므로 `{active:false}`. 활성 추론·확신도 처리는 후속 범위(P15) |
| GET | `/internal/versions` | 로딩 완료한 활성 모델 `{items:[{name,version,revision}]}`. name 순 정렬, 없으면 `{items:[]}`. 내부 토큰 필수 |

#### 4.3.3 #85 scoring 모델 조회·로딩 기준 (2026-10-28)

- core의 활성 snapshot에서 `kind=MODEL`, 이름이 `m2-` 또는 `m1-`로 시작하는 항목만 처리한다. `artifactUri`의 S3 디렉터리를 내려받아 로컬 파일로만 로딩하며 외부 모델 저장소로 대체하지 않는다.
- `/internal/versions`는 core가 요구한 버전이 아니라 **실제로 로딩 완료한 버전**을 반환한다. 초기 조회·로딩 전에는 빈 목록이며 준비 여부는 `/health/ready`의 `models` 항목으로 구분한다. S3 경로·평가 자료·비밀 값은 반환하지 않는다.
- 사용자 결정: core 조회 성공 + 활성 모델 없음은 `models=UP`. 해당 모델은 비활성이며 #87·#88에서 `{active:false}`로 응답한다. core 조회 실패 또는 첫 가중치 로딩 실패는 `models=DOWN` 상태에서 백그라운드 재시도하고 프로세스를 종료하지 않는다. 다른 readiness 항목도 모두 UP이어야 HTTP 200이다.
- 교체는 새 가중치 로딩 완료 후 수행한다. 교체 실패 시 기존 로딩 버전을 유지한다. 같은 kind·name의 낮은 revision은 무시하고, 실패한 최신 revision은 재시도할 수 있다. 새 승인 범위가 좁아졌다면 기존 모델 유지 중에도 이전·새 범위의 교집합에서만 사용한다.
- scope는 #43 계약의 문자열 정확 일치로 검사한다. 학년·입력 유형의 M2 scope는 위 #87 계약의 정확 일치 키를 사용한다. core 승인 범위를 임의로 확장하지 않는다.
- #85는 기동 snapshot·로더·레지스트리 기반, Pod별 큐 바인딩 후 snapshot 조회·보존 이벤트 조정·재연결은 #86이다.

### 4.4 report-service (호출: core)
- 호출 대상은 `report-api` Deployment (KEDA로 0까지 줄어드는 `report-worker`와 분리, [아키텍처 4.4](architecture.md#44-확장))

| Method | Path | 설명 |
|---|---|---|
| GET | `/internal/reports?studentId&status&periodType` | 리포트 목록. periodType 생략은 두 종류, DAILY/WEEKLY 필터 지원 (#391). core는 필터를 전달하고 응답 종류가 다르면 502로 거부한다(#390) |
| GET | `/internal/reports/{reportId}?revision` | 상세 (3.4 스키마), 기본 최신판·양의 revision으로 이전판 조회 |
| GET | `/internal/reports/{reportId}/evidence/{itemId}` | 항목 근거 |
| GET | `/internal/reports/{reportId}/files/{format}` | 단기 presigned URL 발급 → `{url, expiresAt}` |
| GET | `/internal/reports/correction-impact?studentId&attemptId` | 판정 정정 영향 조회(#244, FN-SUP-03). 그 시도로 만든 완료 판 `{items:[{reportId, periodType, periodFrom, revision}]}`. 주간은 `THINKING_TYPE`의 `missions[].attemptId`, 일일은 `PROBLEM`의 `attemptId`로 찾음(보호자 공유가 꺼지면 근거 연결을 저장하지 않으므로 근거 테이블로는 찾지 않음) |
| POST | `/internal/report-jobs/{jobId}/reconcile` | core 작업 복구: `{studentId, periodFrom, periodTo, periodType?}` 대조 후 현재 상태 반환, 불일치 409 `REPORT_JOB_IDENTITY_MISMATCH` (5.9) |

- core는 현재 이용 권한으로 `X-Report-Narrative-Enabled:true|false`를 설정해야 함(공개 요청의 같은 헤더는 전달하지 않음). report는 누락 시 false로 처리해 응답·다운로드에서 AI 서술·생각 유형 summary·저녁 질문을 가림
- P24: 일일 리포트는 같은 경로를 쓰고 최신 판 선택·재생성 판 단위가 학생·`periodType`·대상 기간이 된다(#391 구현). `report.generate` 페이로드에 `periodType`(`DAILY`·`WEEKLY`, 생략 시 `WEEKLY`)을 추가했고 core는 일일에만 넣는다. 새 메시지 없음([이벤트 계약](../../contracts/events/report-messages.md), #390). 일일 상세·다운로드는 `X-Report-Narrative-Enabled: false`로 요청하며 상품 권한을 조회하지 않는다
- 목록은 학생/기간 종류/시작일별 최신 revision을 고른 뒤 status를 적용하며 1.1 페이지 봉투를 사용한다. 상세의 기본값은 같은 학생·기간 종류·시작일 최신판, `revision` 지정 시 해당 판이다. evidence/files 경로는 전달한 실제 reportId 판에 속한 항목·파일을 조회한다.
- 파일 키는 `reports/{studentId}/{reportId}/r{revision}/{full|free}/{pdf|md|html}`다. DB `report_file`에는 full 키 3개를 저장하며 무료용 파생 파일도 생성한다. 다운로드 수명은 설정값이며 운영 기본안은 300초다. 버전·형식·학생이 맞지 않는 키를 서명하지 않는다.

### 4.5 core-service (호출: ai, scoring, learning, report)
| Method | Path | 설명 |
|---|---|---|
| GET | `/internal/model-versions/active` | 기동 시 활성 모델·프롬프트 버전 조회 |
| POST | `/internal/deletion-requests/{deletionRequestId}/completions` | learning·report가 `student.deleted` 처리 후 완료 보고 `{service}`. 두 서비스 모두 보고 시 `COMPLETED` (멱등, P09) |
| POST | `/internal/payment-usage/reservations` | learning 피드백 실행 전 프리미엄 사용 예약 `{studentId,sourceId}` → `{reservationId,premium}` (STUDENT+본인 scope, #48) |
| POST | `/internal/payment-usage/completions` | learning 피드백 DONE 저장 후 사용 확정 `{studentId,reservationId,used}` (#48) |
| GET | `/internal/students/{studentId}/profile` | report-worker: 학생 별명·`parentSharingEnabled` (4.0, #206) |
| GET | `/internal/students/{studentId}/report-template` | report-worker: 현재 연결 학부모의 리포트 표시 설정 `{settings, revision}`. 학생 삭제 진행·비활성 409 `STUDENT_UNAVAILABLE` (#209) |

- 비동기 메시지(`report.generate` 등)는 [아키텍처 1.4](architecture.md#14-메시지-목록) 참고
- report 삭제: PROFILE·RECORDS 모두 리포트 내용·파일을 물리 삭제하고 `report_deletion_guard`에 식별 UUID·범위·기준 시각·상태만 남김. core가 RECORDS 후에도 학습을 자동 재개하지 않으므로 두 scope 모두 이후 생성을 차단(재개는 별도 계약 필요)
- 삭제 학생의 미종료 job은 core 삭제 확정 트랜잭션에서 `FAILED(STUDENT_DELETED)`로 종료하고, 이후 도착한 상태 이벤트·복구 결과도 학생이 `ACTIVE`가 아니면 같은 사유로 종료한다(#132, `ReportLifecycleService`). report 삭제 장벽이 core job 상태를 대신 정리하지 않음

### 4.6 #43 AI 사용량 조회 계약

- `GET /api/v1/admin/ai-usage`: 기존 #36 Bearer·`SERVICE_OPS` 검사를 사용한다. 필수 `from`, `to`는 0001~9999 연도의 ISO 날짜이며 KST 기준 양 끝 날짜를 포함한다. 조회 기간은 양 끝 포함 최대 366일이다. `from > to`, 366일 초과 또는 허용 연도 밖의 날짜는 DB 조회 전에 400 `VALIDATION_FAILED`로 거부한다. 선택 `callType`은 사용량 이벤트의 12개 호출 종류 중 하나다(#355에서 `MISSION_DRAFT`, #439에서 주간 테마 생성 텍스트 `THEME_DRAFT`·이미지 `THEME_IMAGE`, #480에서 `REPORT_EXPLANATION`, #467에서 지식 임베딩 `KNOWLEDGE_EMBEDDING`, 에픽 #436에서 영상 `THEME_VIDEO` 추가). 이미지·영상 호출은 토큰이 없어 `costUsd`가 null이고 `unpricedCalls`로 센다(장당 단가 반영은 ai #437 비용 측정 뒤).
- 응답은 `{period:{from,to},items:[{callType,calls,failures,latencyMs,inputTokens,outputTokens,costUsd,unpricedCalls}]}`다. 기간에 실제 호출이 있는 종류만 반환한다. `latencyMs`는 성공·실패를 포함한 호출당 평균 지연(ms)이다. 토큰은 합계이며 하나라도 미기록이면 해당 합계는 null이다.
- `costUsd`는 저장된 소비 시점 비용의 합계다. 단가 미등록 등 null 비용이 하나라도 있으면 합계도 null이며 `unpricedCalls`로 미산정 호출 수를 공개한다. 빈 결과는 `items:[]`이고 null을 0으로 치환하지 않는다. 수집·멱등 처리·과거 단가 계산은 변경하지 않는다.
- 요금제 한도, 월 예산 알림, 결제·구독 구현은 #43 조회 범위에 포함하지 않는다.
- #467: 지식 임베딩(4.2.4) 사용량 `callType = KNOWLEDGE_EMBEDDING`을 V44에서 추가했다. 입력 토큰만 있어 출력 토큰은 0이고, 단가(`app.llm-pricing`)가 다른 모델처럼 비어 있어 `costUsd`는 null(`unpricedCalls`로 셈)이다.

## 5. 구현 계약

### 5.1 #36 Google OAuth·토큰 구현 계약 (개정 P01 정렬)

인증 경로의 정식 공개 계약은 [core-service OpenAPI](../../contracts/openapi/core-service.yaml). 이 절은 부모·관리자 Google 인증, 관리자·학부모 ID·비밀번호 로그인과 동석 학생 진입, 학생 기기·PIN은 3.11.

- 기기 진입 3개 경로(`POST /auth/student/devices`, `GET /auth/student/profiles`, `POST /auth/student/login`)만 Bearer 검사에서 제외. POST는 다른 쿠키 API와 같이 정확한 web Origin·`X-Requested-With` 검사 유지. 다른 메서드·유사 경로와 `/auth/student-sessions`는 제외하지 않음

- 학부모·관리자: Google core 콜백 → refresh 쿠키 → web `/oauth/complete` → refresh → `/me`. access는 HS256, 기본 15분·메모리 보관. refresh는 256비트 난수·SHA-256 해시 저장, 최초 로그인부터 최대 7일이며 회전으로 연장하지 않는다. 재사용 시 해당 세션 폐기.
- 관리자 ID·비밀번호(#369, 2026-11-09): `POST /auth/admin/login {loginId,password}`는 `user_account.login_id`가 같고 `role=ADMIN`·`status=ACTIVE`이며 `admin_credential` 행이 있는 계정만 받는다. 가입 API는 없고 운영자가 `scripts/admin_account_sql.py`로 행을 만들거나 비밀번호 재설정·비활성화한다. 비밀번호는 PBKDF2-SHA256(60만 회, 보호자 비밀번호와 같은 해시)으로만 저장한다. 없는 ID·틀린 비밀번호·비관리자·비활성 계정은 같은 401 `INVALID_CREDENTIALS`(없는 ID도 해시 검사를 한 번 해 응답 시간 차이를 줄임), 연속 5회째 실패부터 15분간 423 `ADMIN_LOGIN_LOCKED`이며 실패 횟수는 오류 응답 전에 커밋한다. 성공하면 실패 횟수를 지우고 `audit_log`에 `ADMIN_PASSWORD_LOGIN`을 남긴 뒤 Google 로그인과 같은 ADMIN 세션·refresh 쿠키를 발급한다(이전 refresh 쿠키의 세션은 폐기). 정확한 web Origin·`X-Requested-With` 검사를 받는다. web은 `/admin/login`에서만 이 폼을 보여 주고 사용자 화면에는 관리자 로그인 링크·문구를 두지 않는다. 기존 Google 관리자 로그인은 유지한다.
- 학부모 ID·비밀번호(#415, 2026-11-09): 학부모는 Google 또는 ID·비밀번호 중 한 가지로 가입·로그인한다. 두 방법은 자동 연결하지 않으며(같은 사람이라도 별개 계정, `ACCOUNT_EXISTS` 원칙 유지) 한 계정은 한 가지 로그인 수단만 쓴다. `POST /auth/parent/signup {loginId,password,name}`은 아이디(영문·숫자 4~30자, 앞뒤 공백 제거 후 소문자로 저장·비교, `@` 불가라 Google 계정의 이메일 login_id와 겹치지 않음)·비밀번호(8~128자)·이름(1~80자)을 검사해 400 `VALIDATION_FAILED`, 이미 쓰는 아이디는 409 `LOGIN_ID_TAKEN`이다. 같은 IP는 Redis 고정 창으로 기본 10분 5회(`AUTH_SIGNUP_LIMIT_PER_IP`·`AUTH_SIGNUP_LIMIT_WINDOW`)까지이며 넘으면 429 `SIGNUP_RATE_LIMITED`, Redis 장애는 503 `SIGNUP_UNAVAILABLE`이다. 중복 아이디 거절은 횟수에 넣지 않는다. 성공하면 `user_account`(PARENT·ACTIVE, `login_id`=아이디, `oauth_provider`·`oauth_subject`·레거시 `password_hash` NULL, `AUTH_NEW_ACCOUNT_DEMO=true`면 `is_demo`)와 `parent_credential`(PBKDF2 해시)을 만들고 `audit_log`에 `PARENT_PASSWORD_SIGNUP`을 남긴 뒤 Google 신규 가입과 같은 세션·refresh 쿠키를 발급한다(이전 refresh 쿠키의 세션은 폐기, `nextAction: CONSENT_REQUIRED`, `startPath: /parent/onboarding`). `POST /auth/parent/login {loginId,password}`는 관리자 로그인과 같은 규칙이다. 없는 ID·틀린 비밀번호·Google 계정·관리자·비활성 계정은 같은 401 `INVALID_CREDENTIALS`(없는 ID도 더미 해시 검사), 연속 5회째 실패부터 15분간 423 `LOGIN_LOCKED`이고 잠금 뒤 횟수는 0으로 되돌린다. 실패 횟수는 오류 응답 전에 커밋하며 비밀번호 재확인(5.6) 실패와 함께 센다. 성공 감사는 `PARENT_PASSWORD_LOGIN`. 두 경로 모두 정확한 web Origin·`X-Requested-With` 검사를 받는다. 비밀번호 찾기·로그인 상태의 비밀번호 변경 API는 없다.
- 학생(동석·단독 공통): access 전용, refresh 미발급. 동석 `/auth/student-sessions`는 별도 학생 auth_session(`parent_session_id` = 학부모 세션)을 만들고, 학부모 세션은 `locked_at`을 기록하고 version을 올려 잠근다. 학부모 refresh 쿠키는 지우지 않는다. 잠긴 세션의 `/auth/refresh`는 refresh 토큰을 소비하지 않고 401 `PARENT_SESSION_LOCKED`이며 기존 부모 access는 `SESSION_CHANGED`로 거부한다. 단독 PIN 로그인은 별도 학생 auth_session을 생성하며 기존 부모 세션을 변경하지 않는다.
- 학부모 복귀(보호자 비밀번호, 2026-11-03): `POST /auth/parent-unlock {password}`는 refresh 쿠키의 잠긴 학부모 세션과 계정의 보호자 비밀번호를 확인한다. 성공하면 잠금을 풀고 version을 올리며, 그 세션에서 들어간 학생 세션을 폐기하고, refresh를 회전해 refresh 응답과 같은 본문·쿠키를 준다. 실패는 비밀번호 실패 횟수를 커밋한 뒤 401 `GUARDIAN_PASSWORD_INVALID`(`remainingAttempts`), 5회째와 이후는 423 `GUARDIAN_PASSWORD_LOCKED`, 미설정은 409 `GUARDIAN_PASSWORD_NOT_SET`이다. 이때는 Google 로그인으로 돌아오며, 새 로그인은 이전(잠긴) 세션과 그 학생 세션을 폐기한다. 잠기지 않은 세션은 refresh와 같이 처리한다.
- 보호자 비밀번호는 `guardian_password`(계정당 1행)에 PBKDF2 해시·실패 횟수·잠금 시각만 저장한다. 설정·변경은 `PUT /me/guardian-password`에서 `GUARDIAN_PASSWORD` 재인증 grant(5.6)를 같은 트랜잭션에서 1회 소비하며, 성공 시 실패 횟수·잠금을 초기화한다. 탈퇴 요청 시 삭제한다.
- JWT에는 `sub`(계정 UUID), `sid`, `ver`, `role`, `studentId`(학생만), `iss`, `aud`, `iat`, `exp`, `jti`를 넣는다. 매 요청에서 세션·현재 계정·자녀 연결·동의를 확인한다. 기기 해제 시 기존 학생 access를 즉시 폐기하는 별도 정책은 추가하지 않는다.
- 학부모 access 기본 15분, 학생은 `AUTH_STUDENT_ACCESS_TTL`로 별도 관리하며 초기 기본값은 15분이다. 학생 만료·새로고침 시 자동 refresh하지 않고 학생 진입 화면으로 이동한다. 기기·PIN API로 단독 재진입하며 미등록 기기는 등록을 안내한다. 토큰을 영구 저장해 새로고침을 우회하지 않는다.
- 부모 refresh 응답 `{accessToken,expiresIn,role,child:null,nextAction,startPath}` + 회전 쿠키. 동석 응답 `{accessToken,expiresIn,role:STUDENT,child,nextAction:READY,startPath:/student/home}`, Set-Cookie 없음(잠긴 학부모 refresh 유지). child는 `{id,nickname,grade,birthYear}`(기존 #7 소비자 계약)이다. 단독 PIN 로그인 응답(3.11)은 `child.childId`를 쓰므로 프론트 경계에서 정규화한다.
- `GET /me`는 부모/관리자에게 `{userId,name,email,loginId,authMethod,role,permissions,child:null,nextAction,startPath}`, 학생에게 `{role,child,nextAction,startPath}`만 반환한다. `authMethod`는 Google subject가 있으면 `GOOGLE`, 없으면 `PASSWORD`(#415)다. `loginId`는 비밀번호 학부모만 아이디를 주고 그 외는 null이며, 비밀번호 학부모의 `email`은 null이다. 학생에게 부모 개인정보·권한을 반환하지 않는다. 학생은 `/me/consents` 등 부모 계정 관리 API를 사용할 수 없다.
- 로그아웃은 현재 쿠키의 부모 세션 또는 Bearer로 전달된 학생 세션을 종료하고 refresh 쿠키를 삭제한다. 다른 기기는 유지한다. 쿠키 API는 정확한 web Origin과 `X-Requested-With: XMLHttpRequest`를 요구한다.
- web/API 동일 origin. refresh 쿠키 `sagomungchi_refresh`: HttpOnly·Secure·SameSite=Strict·Path=/api/v1/auth. OAuth 상태 쿠키 `sagomungchi_oauth`: HttpOnly·Secure·SameSite=Lax·Path=/api/v1/auth/google, 10분. 로컬 HTTP만 Secure=false.
- Google state·nonce·PKCE S256 및 ID 토큰 JWKS 서명·iss·aud·exp·nonce 검증. 서비스 토큰을 URL에 넣지 않는다. callback 성공은 `/oauth/complete`, 실패는 `/login?oauthError=<고정 코드>`.
- 부모/관리자 refresh는 Web Locks로 탭 간 직렬화한다. 학생 전환·로그아웃 알림을 받은 다른 탭은 토큰·캐시를 지우며 학생 refresh로 다시 로그인하지 않는다. 학생→부모 복귀는 Google 로그인부터 시작한다.
- PIN/동석 학생의 종료는 `POST /auth/student/logout`을 사용한다. `Origin`·`X-Requested-With`와 유효한 학생 Bearer를 검증하고 그 세션만 폐기한다(204, Cache-Control: no-store, Set-Cookie 없음). 누락·만료·위조 Bearer는 401, 다른 역할·출처는 403이며 동반된 보호자 refresh로 대체 인증하거나 보호자 세션을 폐기하지 않는다. 기존 `/auth/logout`의 보호자·관리자 로그아웃 계약은 유지한다.
- 학생에서 보호자 로그인 화면으로 전환할 때는 해당 탭의 access·화면 캐시만 정리하며 전역 LOGOUT을 방송하지 않는다. 탭별 비밀정보 없는 `sessionStorage` 전환 표식으로 새로고침 후에도 보호자 쿠키 자동 복원을 차단하고, Google OAuth 완료 후에만 보호자 역할을 복원한다. PIN 진입 및 학생 만료 경로는 유지한다.
- 계정 복구·비밀번호 찾기·비밀번호 변경 API는 제공하지 않는다(기기·PIN 저장은 core V13, Google·비밀번호 재인증은 5.6). 학부모 ID·비밀번호 계정도 비밀번호 찾기가 없으며 화면에서 문의하기·새 아이디 가입을 안내한다(#415). 관리자 비밀번호 재설정도 API 없이 `scripts/admin_account_sql.py`로만 한다(#369).

### 5.2 #43 모델 레지스트리 확정 계약

자동 품질 합격선 없이 SERVICE_OPS의 명시적 사람 승인을 사용한다. 새 승인 상태 enum은 만들지 않는다. 등록 상태는 기존 REGISTERED·ACTIVE·INACTIVE다.

- GET `/api/v1/admin/model-versions?kind&page=0&size=20`: `{items,page,size,totalElements}`. size 1~100, page 0 이상. kind 생략 시 전체 종류. 항목은 `{id,kind,name,version,refId,artifactUri,evalResult,status,approvedBy,activatedAt,createdAt}`다.
- POST 같은 경로: `{kind,name,version,refId?,artifactUri?,evaluation,registration?}` → 201 항목. `(kind,name,version)` 중복은 409. RUBRIC은 learning 원본 UUID인 refId 필수, 다른 종류는 refId를 받지 않는다. 원본 내용·수정·존재 확인을 core에서 소유하지 않는다.
- `evaluation`은 `{datasetId,datasetVersion,baselineVersion,comparisonReport,trainingEvaluationSeparation,quoteAccuracy,calculationAccuracy,humanReview,evaluatedScopes,limitations?}`다. 문자열 필드는 모두 비어 있지 않은 평가 근거·검토 기록 또는 그 참조이며 `baselineVersion`은 비교한 기존 버전 식별값이다. 최초 등록도 비교 기준을 명시한다. `evaluatedScopes`는 평가한 범위 키의 중복 없는 비어 있지 않은 배열이다. 평가·활성화·복귀 범위 배열의 null 항목은 422로 거부한다.
- #367: `evaluation.limitations?: string[]`는 임시 기준·평가 한계·미검증 사항이다. 생략한 기존 기록은 빈 목록으로 읽는다. `MODEL` 등록은 `artifactUri`가 필수이며 빈 값은 422 `MODEL_APPROVAL_REJECTED`다.
- 웹 등록 파일은 최상위 설명 키와 `requests[]`를 가진 JSON이다. `requests[]`는 기존 등록 본문만 허용하며 승인·활성화·사유·재분석·승인자 필드는 거부한다. 브라우저에서 파싱해 모델별 미리보기와 개별 POST를 제공한다. 별도 파일 업로드 API는 없다. `<버킷>` 일괄 치환 전에는 등록을 차단한다.
- manifest는 `models[]`의 `name/version/scope/files[{file,bytes,sha256}]`를 대조한다. 최상위 `주의`와 일치 모델의 `주의`를 limitations 후보로 쓰되 명시한 `evaluation.limitations`(빈 목록 포함)가 우선한다. JSON·manifest·해시 목록의 확인은 실제 산출물 해시 대조나 로딩·품질 승인을 의미하지 않는다.
- #366: 감사 목록의 `MODEL_VERSION`에는 선택 `detail` 객체(name·version·scopes·reason·reanalysisPlanned·previousVersionId)를 반환한다. 다른 대상 및 허용 목록 밖 detail 필드는 공개하지 않는다. 웹에서 펼쳐 본다.
- 범위 키는 소비자가 동일하게 사용하는 소문자 논리 식별자(예: `judgment/grade-3/narrative`, 최대 200자, `[a-z0-9][a-z0-9._:/-]*`)다. core는 문자열의 정확한 집합 포함 관계만 확인하며 와일드카드·계층 확장을 하지 않는다. 원본 평가 문항·학생 원문은 저장하지 않는다. 검토 기록의 사실성·품질 수치의 적합성은 사람이 판단하며 서버는 자료 자체를 실행·검증했다고 주장하지 않는다.
- POST `/{versionId}/activate`: `{approved:true,scopes,reason,reanalysisPlanned}`. REGISTERED만 최초 승인·활성화할 수 있다. 필수 평가 근거 누락·미승인·평가 외 범위는 422, 이미 활성화 이력이 있는 대상은 409다. 승인자는 요청 값이 아닌 #36 인증 계정 ID다. 기존 ACTIVE는 INACTIVE가 되고 승인·평가 이력은 보존한다.
- POST `/{versionId}/rollback`: `{scopes,reason,reanalysisPlanned}`. 같은 kind·name의 현재 ACTIVE가 있고, 대상이 과거 승인·활성화된 INACTIVE이며 요청 범위가 당시 승인 범위의 부분 집합일 때만 성공한다. 잘못된 상태는 409, 승인 외 범위는 422다. 원 승인자·승인 범위는 보존하고 복귀 수행자는 감사 이력에 별도 기록한다.
- `reanalysisPlanned`는 재분석 여부 기록일 뿐 작업을 실행하지 않는다. 기존 관찰·질문·분석·리포트 결과는 수정하지 않는다. 등록·성공 교체는 audit_log에 추가하며 교체의 상태·감사·Outbox는 한 트랜잭션이다.
- `evalResult`는 `{evidence:evaluation,approval:null|{scopes,reason,approvedBy,approvedAt},activeScopes:[],revision:0}`로 저장한다. 활성화·복귀 때 activeScopes와 revision을 갱신한다. 동일 kind·name을 advisory transaction lock으로 직렬화하고 해당 그룹에 저장된 최대 revision + 1을 사용한다. 평가 근거와 최초 승인은 덮어쓰지 않는다.
- 내부 GET `/internal/model-versions/active`는 기존 `X-Internal-Token` 필수이며 `{items:[{id,kind,name,version,refId,artifactUri,scopes,revision,activatedAt}]}`를 반환한다. 평가·관리자 정보는 전파하지 않는다. 공개 API base(`/api/v1`)를 붙이지 않는다.
- 이벤트는 `contracts/events/model.version.activated.v1.schema.json` data와 기존 봉투를 사용한다. `revision`은 kind·name별 단조 증가 값이다. 소비자는 큐 바인딩 후 내부 API로 초기화하고, 초기화 중 이벤트를 보존·조정하며 더 높은 revision만 적용한다. 승인 scope를 실제 요청 시에도 제한해야 한다.
- ai는 `PROMPT` 중 #68의 여덟 이름(#280 `reportTemplate`, #354 `missionDraft`, #477 `reportExplanation`, #437 `themeDraft` 포함)과 해당 기능 scope만 반영한다. 이벤트는 전체 snapshot이 아니며 다른 기능의 활성 버전을 제거하지 않는다. 새 scope에서 빠진 기능에는 이전 활성 본문을 계속 쓰지 않고 내장 버전으로 돌아간다. 재연결 후 새 큐 바인딩·snapshot 조회·이벤트 조정을 완료하기 전에는 `versions=DOWN`이다. malformed 이벤트는 안전한 로그 후 ACK하여 재시도하지 않는다. probe 자체는 core 조회를 수행하지 않는다.

- #43 기존 SQL NULL 평가 행은 목록에서 evalResult:null로 보존하고 활성화/복귀 시 422로 거부한다. 승인 근거·적용 범위가 불완전한 기존 ACTIVE 행이 있으면 내부 snapshot은 MODEL_VERSION_STATE_INVALID(503)로 명시적으로 실패하며 임의 기본 버전을 반환하지 않는다. 신규 등록은 계속 완전한 평가 기록을 요구한다.

#### #367 등록 확장 (백엔드 구현)

- `MODEL` 등록은 비어 있지 않은 `artifactUri`가 필수(422 `MODEL_APPROVAL_REJECTED`). 다른 종류의 기존 규칙은 유지한다.
- `evaluation.limitations`는 선택 문자열 배열, 생략/기존 행은 `[]`. 최대 100개, 각 1~4,000자이며 공백뿐인 문자열·null 항목은 거부한다. 반환 위치는 `evalResult.evidence.limitations`다.
- `registration`은 선택 출처 정보다. 생략하면 `{source:MANUAL}`. JSON 가져오기는 `{source:JSON_IMPORT,jsonSha256,manifestSha256?,modifiedFields:[],artifactFiles:[{file,bytes,sha256}]}`를 보낸다. 해시는 소문자 64자리 SHA-256. 가져온 원본 파일 바이트 기준이며 JSON 재직렬화나 폼 수정 후 해시가 아니다. 파일 목록은 선택한 모델 항목만 보낸다.
- JSON_IMPORT는 jsonSha256 필수. artifactFiles가 있으면 manifestSha256 필수. MANUAL은 해시·수정 목록·파일 목록을 받지 않는다. modifiedFields는 OpenAPI에 나열한 등록 필드 경로만 허용하며 배열 전체 변경도 필드 경로 하나로 기록한다. 파일 상대 경로는 중복·상위 경로·절대 경로를 거부한다.
- source·해시·수정 필드·파일 목록은 기존 MODEL_REGISTER 감사 detail에 기록한다. 출처/해시는 클라이언트 신고이며 서버에서 원본 파일·S3·품질을 검증한 결과가 아니다. actor·등록 ID·시각·상태는 서버가 정한다.
- 브라우저가 기존 registration 파일의 requests[]를 파싱해 개별 POST한다. manifest는 선택이며 원래 두 파일 형식은 유지한다. 파일 업로드·일괄 등록 API는 없다. 주의사항 우선순위는 명시된 evaluation.limitations → 최상위 주의와 해당 모델 manifest 주의 후보이며 운영자가 확인한다.
- 등록 요청의 승인 여부·활성화 범위·사유·재분석 계획·승인자 및 알 수 없는 필드는 400 VALIDATION_FAILED. 유효한 타입의 업무 검증 실패는 기존 422 MODEL_APPROVAL_REJECTED, 중복은 409 MODEL_VERSION_CONFLICT. 공통 Problem Details 형식은 유지한다.
- 프론트 전달용 예시와 역할 분담: [#367 API 전달 내용](../report/ai.md#11-모델-등록-api-367). 화면·웹 타입은 프론트 담당 범위다.

#### 5.2.1 모델 파일 사전 검사 (#368)

- 관리자 `POST /api/v1/admin/models/preflight`: SERVICE_OPS 권한. core가 내부 토큰을 붙여 scoring `POST /internal/models/preflight`로 동기 중계한다. core HTTP 제한 20초, 자동 재시도 없음.
- 요청: `name`, `version`, `artifactUri`, manifest의 `files[{file,bytes,sha256}]`. config.json·tokenizer.json·tokenizer_config.json·train_info.json·score_cuts.json·model.safetensors를 각각 한 번씩 받는다. 승인 관련 필드·알 수 없는 필드는 거부한다.
- 응답: `{status: PASS|FAIL, code, files:[{file,status,code}]}`. 검사 대상 파일이 없거나 불일치해도 검사 결과는 HTTP 200/FAIL이다. 잘못된 요청 400, 권한 401/403, scoring 응답 오류 502, 연결/시간 제한 503은 기존 RFC 9457 형식이다.
- scoring은 설정된 S3 버킷의 models/ 경로만 검사한다. 각 파일 HEAD로 존재·크기를 확인한다. 세 메타데이터 JSON만 ETag 조건(If-Match)으로 고정하여 최대 1MiB 본문을 읽고 SHA-256을 직접 대조한다. 나머지 파일은 S3가 제공하는 전체 SHA-256을 비교하며 ETag·사용자 메타데이터·COMPOSITE 체크섬을 파일 해시로 사용하지 않는다. 없는 체크섬은 CHECKSUM_UNAVAILABLE이다.
- `validate_metadata`를 재사용해 학습 입력·점수 경계와 config의 회귀 출력 수를 확인한다. 모델·토크나이저 로딩, 점수 추론, 파일 쓰기는 하지 않는다. scoring은 15초 작업 예산과 개별 S3 연결/읽기 1초·재시도 없음으로 제한한다.
- 결과는 `MODEL_PREFLIGHT` 감사 action의 SUCCESS/FAILURE에 남긴다. 등록 전 검사여서 target_id는 null이며 이름·버전·경로·manifest 파일·결과를 detail에 저장한다. evaluation/evidence와 기존 모델 레코드는 변경하지 않는다.
- 화면 결과는 해당 입력 스냅샷에만 유효하다. 입력 변경 시 재검사를 안내한다. 검사 통과는 파일·형식 확인일 뿐 품질 승인·활성화·추론 성공이 아니며 자동 등록/활성화하지 않는다.

### 5.3 #37 동의·자녀 구현 계약

- 문서 조회·저장·철회·자녀 등록의 정식 스키마는 core OpenAPI를 따른다. GET /consent-documents는 3종 현재 문서를 목록 봉투로 반환한다. 현재=KST 시행일 이하에서 effective_from·created_at·id 내림차순 첫 문서. 게시 문서가 없거나 불완전하면 503 CONSENT_DOCUMENTS_UNAVAILABLE이며 가짜 본문을 생성하지 않는다. 1.0 문서 3종(공식 원문 기반, 시연용·법률 검토 없음)은 core V25 마이그레이션이 게시한다(#235, 출처는 auth-account 보고서). 개정은 기존 행을 고치지 않고 새 version 행을 추가한다.
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

- 자동 생성은 직전 KST 월~일, 주가 끝난 일요일 자정(월요일 00:00)이다(2026-11-09 결정). 부모 REGENERATE 한도는 자녀·주 계열 전체 1회(새 판을 기준으로 재요청해도 409 REPORT_REGENERATION_LIMIT). SERVICE_OPS 관리자는 같은 POST 경로에서 ADMIN_RETRY 작업을 무제한 생성한다. 생성 중 작업이 있으면 409 REPORT_GENERATION_IN_PROGRESS이다.
- 재생성 202는 `{jobId, childId, period:{from,to}, status:"QUEUED"}`다. 이전 reportId는 보존되고 report가 revision을 배정한다. 상품·구독 권한은 payment의 ProductEntitlementService에서 확인한다. 상품 설정 불완전·권한 조회 실패는 명시적인 오류로 처리하고 job/Outbox를 생성하지 않는다.
- reportId 조회의 자녀 연결·현재 필수/법정대리인 동의를 확인한 뒤 단일 학생 scope로 report-api를 호출한다. 없는 core reportId는 404 REPORT_NOT_FOUND다. 목록은 `{items:[3.4의 식별·기간·status·state·revision·generatedAt 필드]}`다. core는 report 목록을 `page=0`부터 `size=100`으로 짧은 페이지가 나올 때까지 조회해 합치며 각 페이지에 같은 계약 검사를 적용한다. 50페이지를 넘으면 502 REPORT_CONTRACT_INVALID다(#500). 목록 `status` 필터는 `RUNNING`·`COMPLETED`·`FAILED`만 허용한다. `QUEUED`는 아직 리포트가 없는 작업 상태로 목록 필터에 제공하지 않으며 요청하면 400 `VALIDATION_FAILED`다(#518). 상세는 3.4, 근거는 report-api JSON을 그대로 전달하고 다운로드는 pdf/md의 `{url,expiresAt}`다. report 장애는 503 REPORT_UNAVAILABLE, JSON 계약 위반은 502 REPORT_CONTRACT_INVALID다. 성공 상세의 실제 반환 reportId로 열람 기록을 남긴다.
- v1 이벤트 스키마·봉투·생산자·소비자는 [report-messages.md](../../contracts/events/report-messages.md). 결정 근거는 [리포트 보고서](../report/report.md).

#### 5.5.1 #152 관리자 실패 리포트 재처리 (report 공급 계약)

- #47 담당자와 합의: core가 관리자 권한·Idempotency-Key·현재 이용 권한/학생 상태를 확인하고, 원래 실패 작업과 **새 jobId**의 연결·감사 기록을 관리한다. report에는 기존 `report.generate.v1`의 `trigger=ADMIN_RETRY`와 현재 권한의 `narrativeEnabled`를 보낸다. 같은 재처리 요청 재전달은 같은 jobId·같은 업무 본문을 사용한다. 새로 명시적으로 재처리할 때만 새 jobId를 발급한다.
- report는 기존 GenerationService·JobLocks·ReportRepository·OutboxRelay를 재사용한다. 새 jobId이면 같은 학생/주의 다음 revision을 생성하고 이전 판을 보존한다. 같은 jobId의 COMPLETED·FAILED 재전달은 ACK 후 종료하며 상태를 되돌리거나 생성기를 다시 호출하지 않는다(#50 유지). 동시 전달은 작업 잠금으로 중복 실행을 막고 기존 소비자의 지연 재시도 정책을 따른다.
- started/completed/failed는 **받은 새 jobId**, 학생 ID 및 그 실행에 배정한 같은 reportId를 반환한다. 원래 실패 jobId·revision·관리자 ID는 report 이벤트에 추가하지 않는다. core는 jobId로 실행을 구분해 지연된 원작업 이벤트가 새 작업에 반영되지 않게 한다. report에는 core 결과 이벤트를 다시 적용하는 API가 없다.
- 시작 행과 started Outbox, 종료 상태/항목/파일과 terminal Outbox는 각각 같은 DB 트랜잭션이다. Outbox 발행은 at-least-once이므로 core는 봉투 id와 조건부 상태 전이로 중복·순서 역전을 방어한다. 새 이벤트 ID를 붙여 같은 jobId를 다시 보내도 업무 실행은 늘어나지 않는다.
- report는 기존 삭제 장벽과 core ACTIVE 프로필 조회를 유지한다. 삭제 장벽으로 거부된 작업은 기존 정책대로 생성·성공 이벤트를 만들지 않는다. 삭제와 경쟁한 core 작업의 취소·정리는 core 책임이며 #152에서 삭제 정책이나 거짓 실패/완료 이벤트를 임의 추가하지 않는다.
- 새 HTTP API·이벤트 버전·DB 컬럼은 필요 없다. 요청 접수·원작업 연결·감사는 core(2.8 #47 REPORT 실패 작업 재처리).
- 요청·결과 예시: [report-admin-retry](../../contracts/examples/report-admin-retry/). 기존 [공유 메시지 계약](../../contracts/events/report-messages.md)과 같은 스키마를 사용한다.

### 5.6 #45 계정 관리·Google·비밀번호 재확인·삭제·탈퇴 계약

- 기존 Google 로그인과 별도 재인증 흐름을 사용한다. `POST /me/reauth`에 `{purpose: PIN_CHANGE|CHILD_UNLINK|CHILD_DELETE|WITHDRAWAL|GUARDIAN_PASSWORD|CHILD_TRANSFER|TRANSFER_ACCEPT, childId?, scope?}`를 보내면 `{challengeId,authorizationUrl,expiresAt}`를 반환하고 HttpOnly/Secure/SameSite=Lax 재인증 상태 쿠키를 설정한다. CHILD_DELETE는 PROFILE/RECORDS scope를 반드시 지정한다. WITHDRAWAL·GUARDIAN_PASSWORD·TRANSFER_ACCEPT는 자녀/scope를 허용하지 않는다. CHILD_TRANSFER를 포함한 다른 자녀 작업은 childId 필수이며 CHILD_DELETE 외에는 scope를 허용하지 않는다.
- Google redirect URI는 web origin + `/api/v1/auth/google/reauth/callback`이다. 기존 GoogleOAuthClient의 code·PKCE·서명·iss·aud·exp·nonce 검증을 재사용한다. callback은 현재 계정의 Google sub와 일치할 때만 challenge를 VERIFIED로 바꾸며 로그인/refresh를 발급하지 않는다. 계정 선택은 비밀번호/MFA 재입력을 보장하지 않는다. 클라이언트는 원래 로그인 세션을 유지한 상태에서 `POST /me/reauth`에 `{challengeId}`를 보내 `{reauthToken,expiresAt}`를 한 번 수령한다. 아직 callback 전이면 409 REAUTH_PENDING이다. callback 응답은 작은 안내 HTML이다(#425). 성공하면 같은 출처 `BroadcastChannel('sagomungchi-reauth')`로 `{type:"REAUTH_VERIFIED",challengeId}`만 알리고 `window.close()`를 호출하며, 닫히지 않으면 "확인이 끝났습니다. 이 창을 닫고 원래 화면으로 돌아가 주세요."를 보인다. 원래 탭은 자기 challengeId 알림을 받으면 위 수령 요청을 자동으로 보내고, 수동 "완료 확인"은 대체 수단으로 남긴다. 팝업은 `opener=null`이라 postMessage 대신 BroadcastChannel을 쓴다. 응답 헤더는 `Content-Security-Policy`(script-src·style-src nonce, default-src 'none'), `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`다. 실패(403 REAUTH_REQUIRED 조건)도 스크립트 없는 안내 HTML로 응답한다.
- 비밀번호 재확인(#415): ID·비밀번호 학부모는 Google 대신 `POST /me/reauth/password {purpose, childId?, scope?, password}`로 로그인 비밀번호를 다시 입력해 `{reauthToken,expiresAt}`를 바로 받는다. 목적·자녀·범위 규칙과 소유권 검사는 `/me/reauth`와 같다. 비밀번호가 맞으면 검증·발급을 마친 `reauth_challenge`와 `reauth_grant`를 한 트랜잭션에 만들어, 재인증 사용처(탈퇴·보호자 비밀번호·자녀 해제·자녀 삭제·자녀 이관·이관 수락)의 consume 검사는 바뀌지 않는다. 틀리면 403 `REAUTH_PASSWORD_INVALID`이고 로그인과 실패 횟수를 함께 세어 5회째부터 15분간 423 `LOGIN_LOCKED`이다(횟수는 오류 응답 전에 커밋). Google 계정(또는 `parent_credential` 행이 없는 계정)은 409 `REAUTH_METHOD_MISMATCH`. 성공 감사는 `PASSWORD_REAUTHENTICATED`. 필수 동의 누락 상태에서도 `/me/reauth`와 같은 동의 복구 목록으로 허용한다. 웹은 `/me`의 `authMethod`가 `PASSWORD`면 Google 새 탭 대신 비밀번호 입력을 보인다.
- challenge 10분, reauthToken 5분(설정값, 세션 만료 이내). 토큰은 256비트 난수, DB에는 SHA-256 해시만 저장한다. 프론트는 메모리에만 보관한다. 사용자·세션 ID/version·purpose·childId·삭제 scope에 결합하며 변경 트랜잭션에서 정확히 1회 소비한다. 일반 access/로그인 상태는 재인증 증명이 아니다. 잘못된 계정·만료·위조·다른 범위·중복 사용은 403 REAUTH_REQUIRED다.
- 2026-11-10 사용자 동선 변경: 학생 PIN 저장은 활성 학부모 세션과 현재 자녀 권한만 요구한다. PIN 해시 변경·잠금 해제·감사는 같은 트랜잭션이며 추가 Google/로그인 비밀번호 재인증을 요구하지 않는다. 보호자 비밀번호·자녀 삭제·탈퇴 등 다른 재인증 작업은 유지한다.
- PATCH /me `{name}` → `{userId,name}`; PATCH /children/{id} `{nickname?,grade?}` → 현재 자녀. 공백·범위 밖 입력 거부. 기존 기록/학년을 변경하지 않는다. 학생 역할 금지, 계정·자녀의 현재 동의를 검사한다.
- deletion-impact → `{childId,actions:[{scope,effect}],retainedTransactionsYears:5,deviceCleanupPending:false}`. 연결 해제는 UNLINKED 이력을 남기고 학생 세션을 폐기한다. 삭제 확정은 `X-Reauth-Token`, `{scope}` 필수, 202 `{deletionRequestId,childId,scope,status,completedServices}`. 동시에 진행 중인 다른 삭제는 409 DELETION_IN_PROGRESS다. 재확인이 유효한 요청을 즉시 CONFIRMED로 저장한다.
- PROFILE은 연결 해제·학생 이용 차단 후 두 서비스 완료 시 프로필 필드를 지우고 DELETED 표식을 남긴다(FK/거래 보존용 ID 유지). RECORDS는 프로필을 유지하되 CONFIRMED부터 이용을 차단한다. 완료 후에도 자동 학습 재개는 하지 않는다. learning의 삭제 표식 이후 새 기록 허용 계약은 후속 통합 사항이다. 두 scope 모두 core 분석 대화·근거와 learning/report 기록을 삭제한다. 삭제 확정 때 `student_device_child`를 제거하고 PIN 해시·잠금을 지운다(ERD 3.1).
- GET /children/{id}/deletion-requests/{requestId}: 본인 소유 삭제 상태 조회. 삭제 후에도 본인이 요청한 상태는 조회 가능하다. 다른 보호자는 403이다.
- 내부 완료 API는 기존 내부 토큰 + SYSTEM 컨텍스트/대상 학생 scope를 요구하며 `{service:learning|report}`만 허용한다. `(request_id,service)` UNIQUE 기록으로 중복/동시 보고를 멱등 처리한다. CONFIRMED인 요청만 완료할 수 있으며 두 서비스가 모두 있어야 COMPLETED다. 한 서비스 완료는 실제 전체 삭제 완료가 아니다.
- 필수 동의 철회 뒤에도 재인증·삭제 영향·연결 해제·삭제/탈퇴 요청 및 상태 조회, 본인의 이관 목록 조회·거절·취소는 가능하다. 재동의를 파기의 선행 조건으로 요구하지 않는다. 이 경로는 계정 활성·보호자 소유권·재확인을 계속 검사한다. 정보 수정에는 기존 동의를 요구한다.
- 탈퇴 precheck는 core payment 소유 서비스로 현재 subscription/refund_request를 실제 조회한다. ACTIVE(기간 내/자동갱신), RENEWAL_FAILED, 취소됐어도 기간 내 구독 및 REQUESTED/APPROVED/FAILED 환불은 409 WITHDRAWAL_BLOCKED다. DB 오류는 성공으로 대체하지 않는다. #48은 결제/환불 쓰기 시 같은 parent 계정 행 잠금 규약에 참여해야 한다.
- POST /me/withdrawal은 WITHDRAWAL 재인증, 계정 행 잠금 후 재확인한다. 즉시 WITHDRAWAL_REQUESTED·전체 세션/refresh 폐기·자녀 PROFILE 삭제 요청/Outbox를 같은 트랜잭션에 저장한다. 자녀가 모두 삭제되면 WITHDRAWN 및 withdrawal COMPLETED다. 자녀가 없으면 즉시 완료한다. 요청 즉시 로그인/취소 불가다.
- 응답 `{withdrawalRequestId,status,statusToken}`의 statusToken은 별도 256비트 조회 전용 영수증이다(DB에는 해시). 세션 폐기 후 `GET /me/withdrawal`에 `X-Withdrawal-Status-Token`으로 해당 요청의 `{withdrawalRequestId,status}`만 조회한다. 로그인/사용자 정보 접근 권한을 주지 않는다. 헤더/응답은 no-store다. 인증 상태에서도 자신의 최신 요청을 조회할 수 있다.
- 연결 해제 뒤에도 같은 보호자의 등록 이력으로 PROFILE·RECORDS 삭제를 요청할 수 있다. 호환용 PIN_CHANGE·CHILD_UNLINK 재인증 발급은 현재 LINKED 소유권이 필요하다.
- 진행 중인 RECORDS 삭제와 탈퇴가 겹치면 RECORDS 완료 뒤 새 PROFILE 요청·이벤트를 기록한다. 이벤트 scope를 바꾸거나 완료 보고를 다른 요청에 쓰지 않는다.
- 탈퇴 완료 시 연락 이메일·표시 이름은 계정 tombstone으로 정리하고 Google sub는 재로그인 차단 표식으로 유지한다. 상품·거래·구독·환불 행은 변경하지 않는다.
- learning은 `student.deleted`를 받아 학습 기록을 삭제한 뒤 `{service:"learning"}`으로 완료를 보고한다(#128, SYSTEM 컨텍스트 + 대상 학생 범위). 같은 이벤트를 다시 받으면 삭제 없이 보고만 다시 보낸다.

### 5.7 #46 support 구현 계약

- `/help`·`/notices`는 Bearer 인증·현재 동의가 필요하다. help의 role 생략 시 현재 역할, 다른 역할 요청은 403. 기존 Google·기기·PIN·탈퇴 상태 토큰 예외는 유지한다.
- 신고·문의 소유자는 `(userId, requesterRole, requesterStudentId)`다. 학생은 세션 studentId만, 보호자는 자신의 PARENT 건만 조회한다. 자녀 대상은 현재 연결·동의를 재검사한다. 기존 소유 역할이 없는 행은 사용자 목록에 추정 노출하지 않는다.
- `POST /error-reports`: 기존 필드 + 선택 `studentId`(서버 확인), UUID Idempotency-Key 필수. learning 대상은 아래 공급자 조회에서 학생·시도를 검증한 뒤 저장한다. ANALYSIS targetId는 core conversation_message ID, REPORT는 완료 report ID이며 보호자만 가능하다. 접수는 판정을 변경하지 않는다.
- `POST /inquiries`: `{category:ACCOUNT|USAGE|PAYMENT,title,body,studentId?,attemptId?}`. 학생은 세션 학생으로 고정한다. 세 문의 분류는 학생·보호자 모두 접수할 수 있으며, 문의 분류가 결제 데이터 조회 권한을 부여하지 않는다. attemptId는 공급자가 해당 학생 시도로 확인할 때만 연결한다. 문의 목록·상세는 `{inquiryId,category,title,body,status,answer?,answeredAt?,createdAt}`.
- 관리자 신고 PATCH `{status,reviewReason,reviewResult?}`: RECEIVED→IN_REVIEW→RESOLVED. RESOLVED는 결과·사유 필수(reviewResult 생략 시 reviewReason 사용). 완료 후 재요청은 동일 값만 허용한다. 문의 답변 `{answer}`는 RECEIVED/IN_REVIEW→RESOLVED, 같은 답변 재시도는 동일 결과, 변경은 409.
- 정정 POST는 UUID Idempotency-Key + `{reason,corrected:CORRECT|PARTIAL|RETHINK|HELD}`. 이번 공급자 계약은 JUDGMENT만 지원하며 다른 targetType은 422. 검토 중 신고에 정정 의도·이전 결과·고정 요청 ID를 먼저 커밋 → 트랜잭션 밖 learning HTTP → 성공 결과와 영향·신고 완료·알림을 같은 트랜잭션으로 저장한다. 실패/응답 유실은 완료하지 않으며 동일 ID로 재시도한다. 신고당 정정 1건, 다른 본문 재사용 409. 원본 학생 답변·판정은 덮어쓰지 않는다.
- 관리자 상세 원문은 저장된 attemptId·studentId에서만 조회한다. 임의 attemptId query를 받지 않는다. 목록·쓰기 응답에는 원문 없음. 원문은 draft·memo 제외 답변·판정만, 응답 전에 audit_log 저장(실패 시 원문 응답 실패). 문의 원문은 추가 `GET /admin/inquiries/{inquiryId}`를 동일하게 처리한다.
- 공지 POST/PATCH `{kind:NOTICE|MAINTENANCE,title,body,targetRoles:[STUDENT|PARENT|ADMIN],visibleFrom,visibleTo?}`. 역할·기간 검증, 종료 후 수정 금지. DELETE는 endedAt 기록이며 물리 삭제하지 않는다. 사용자 GET은 현재 역할과 `visibleFrom <= now < visibleTo`, endedAt 없음만 조회한다. 목록은 공통 page/size 봉투.
- #242 관리자 전체 목록 `GET /admin/notices?status&role&page=0&size=20`: SERVICE_OPS 전용(그 외 관리자·학부모·학생 403, 미인증 401). 응답은 사용자 GET과 같은 공지 항목의 `{items,page,size,totalElements}`이며 새 필드를 추가하지 않는다. 상태는 저장 컬럼이 아니라 조회 시각(DB `CURRENT_TIMESTAMP`)으로 계산한다: `SCHEDULED` = endedAt 없음·`now < visibleFrom`, `ACTIVE` = endedAt 없음·`visibleFrom <= now`·(visibleTo 없음 또는 `now < visibleTo`), `ENDED` = endedAt 있음 또는 `visibleTo <= now`. status 생략 시 세 상태 전체, role은 targetRoles에 해당 역할 포함. 정렬은 visibleFrom DESC, id DESC. 정의 밖 status·role, page<0, size 1~100 밖은 400 VALIDATION_FAILED. 조회만 하며 감사 기록을 남기지 않는다.
- 보호자 신고 완료·문의 답변만 기존 알림 service로 연결한다. 학생 건은 본인 결과 조회, 보호자 알림으로 우회하지 않는다. sourceEventId는 신고/문의 UUID이며 완료 여부만 알린다. 링크는 `/parent/support?reportId=...` 또는 `?inquiryId=...`, 소비자에서 본인 상세 API를 호출한다.

#### 5.7.1 learning 공급자 계약

learning 구현 명세는 4.1 표와 learning OpenAPI다(정정 #80, 대상·원문 조회 #146). 학생 전용 `/internal/attempts/{id}`를 관리자로 위장 호출하지 않는다. 별도 `contracts/openapi/support-learning-required.yaml`은 core가 받는 범위를 적은 소비 계약이며, 요청·응답 구조는 learning OpenAPI와 같게 두고 `scripts/tests/test_support_openapi.py`가 대조한다(정정 `impact`는 core가 받는 enum이 learning이 보내는 값을 포함하는지만 확인, #423).

- GET `/internal/support/targets/{targetType}/{targetId}`: JUDGMENT/FOLLOWUP/ATTEMPT → `{studentId,attemptId,judgmentId?,previousResult?}`. 내부 토큰 + 사용자 scope 검사, 관리자 SERVICE_OPS 컨텍스트는 core 검증 후 전달. 범위 밖 403, 대상 없음 404. core는 아래 #163 GET 오류 매핑을 적용하며, 미구현/장애는 `SUPPORT_DEPENDENCY_UNAVAILABLE` (503).
- GET `/internal/support/attempts/{attemptId}`: `{studentId,attemptId,answers:[{answerId,version,text,feedback}]}`. core가 저장된 연결 ID로만 호출, 공급자도 전달한 단일 학생 scope·ADMIN 역할·core 내부 토큰 검사(SERVICE_OPS는 core에서 검증). draft/memo/이름 제외.
- POST `/internal/judgments/{judgmentId}/corrections`는 **#80**의 공급자 구현 범위다. `{reportId,reason,corrected}`와 core에 영속 저장한 correction UUID를 `Idempotency-Key`로 전달하는 현재 흐름을 유지한다. 원판정·원본 답변을 보존하고 정정 이력을 추가한다. 조회에는 최신 정정을 적용하되 기존 되묻기와 `nextActions`는 유지한다.
- 정정 인증은 내부 토큰·`ADMIN`·대상 학생 **정확히 1명**의 `X-Student-Scope`·UUID `X-User-Id`가 필수다. SERVICE_OPS 검사는 core가 소유한다. 잘못된 내부 토큰은 401, 역할/학생 범위 위반은 403, 필수 사용자 ID 누락/형식 오류는 400이다.
- 정정 대상의 처리 상태가 `DONE` 이전이면 409. 동일 `reportId`에 다른 `Idempotency-Key`를 사용하면 409. 같은 키·같은 본문은 `correctionId`·이전 결과·정정 결과·시각·impact를 포함한 **최초 응답 전체**를 재현하고, 같은 키·다른 본문은 422다. 응답 유실·core 저장 실패 후에도 같은 영속 키로 재개한다.
- 정정 응답은 `{correctionId,previousResult,corrected,createdAt,impact:{conversation,aggregation,report}}`다. `impact.aggregation`은 **학습 수치 집계**에 대한 정정 반영 여부이며 개별 기록 상세의 판정 표시와 구분한다.
- impact의 `APPLIED`는 해당 영역에 정정 반영을 확인함, `NOT_APPLIED`는 해당 영역에 정정 반영을 수행하지 않았음을 확인함, `UNKNOWN`은 반영 여부를 확인하지 못함이다. 집계가 판정 결과를 사용하지 않아 변경 대상이 없는 경우도 `aggregation: NOT_APPLIED`이며 오류나 후속 처리 필요를 뜻하지 않는다. learning은 `conversation`·`report`에 UNKNOWN을 반환할 수 있다.
- **모든 impact가 UNKNOWN이어도 판정 정정 성공과 신고 RESOLVED 전이가 가능**하다. core는 공급자가 확인한 정정 성공을 기준으로 완료 처리하고 impact의 `aggregation`은 그대로 보존하며 `conversation`·`report`는 아래 #244대로 채운다. 관리자 화면은 이를 대화·집계·리포트까지 모두 반영됐다는 의미로 표시하지 않는다.
- #244 영향 판정: 위 값은 learning 응답 계약이고 "정정을 반영했는지"를 뜻한다. 새 값 `AFFECTED`·`NOT_AFFECTED`는 "정정 대상 판정이 쓰였는지"를 뜻하며 core가 저장·공개할 때만 쓴다. 새 정정의 `conversation`·`report`에는 `APPLIED`·`NOT_APPLIED`가 오지 않는다. core는 정정 성공 후 DB 트랜잭션 밖에서 대화·리포트 영향을 조회해, 저장·공개하는 impact의 `conversation`·`report`를 `AFFECTED`(이 판정을 쓴 리포트·대화 답변이 있음)·`NOT_AFFECTED`(없음)·`UNKNOWN`(조회 실패)로 채운다. `aggregation`은 learning 값 그대로다. 영향이 있으면 `reportIds`·`messageIds`·`conversationIds`도 저장한다. 조회 실패는 정정 성공과 RESOLVED 전이를 막지 않고 다시 조회하지 않는다.
- #244 찾는 범위: 리포트는 `GET /internal/reports/correction-impact`, 대화는 정정한 판정의 답변 ID(`GET /support/attempts/{attemptId}`의 `feedback.judgment.judgmentId`로 확인)를 `message_evidence`의 `answer_id`(`ANSWER`)로 찾는다. 일일 리포트 고정 대화는 질문마다 고정된 판을 다시 읽으므로 영향받은 판(자녀·대상일·판)에 고정된 대화 전체가 대상이다. 리포트는 보호자 공유가 꺼지면 근거 연결이 없어 시도 단위로 찾으므로, 같은 시도의 다른 답변을 정정해도 `AFFECTED`가 될 수 있다.
- #244 표시: 리포트 상세와 대화 답변 응답의 `correctionNotice`(boolean)가 true면 화면에 정정 안내를 표시한다. 리포트·답변 내용은 바꾸지 않고 재생성하지 않는다. 재생성한 새 판은 리포트 ID가 달라 표시되지 않는다. `impact`는 관리자 응답에만 제공하고 신고자(학생·학부모) 응답에서는 `null`이다.
- `/support/targets/...`(신고 대상 확인·최초 정정 전 조회)와 `/support/attempts/...`(관리자 원문 조회)는 #146에서 구현했다.

#### 5.7.2 #163 지원 GET 공개 오류 매핑 (2026-10-30 사용자 승인)

대상 GET과 원문 GET에만 적용한다. 정상 오류는 Content-Type `application/problem+json`(매개변수 허용)의 JSON 객체이며 HTTP 상태와 정수 `status`, 문자열 `code`가 아래 쌍과 정확히 일치해야 한다. 공급자의 title/detail/instance/traceId·추가 필드와 임의 code는 공개하지 않고 core가 고정 문구의 Problem Details를 만든다.

| learning GET 응답 | core 공개 응답 | 고정 문구 |
|---|---|---|
| 정상 403 FORBIDDEN | 403 FORBIDDEN | 지원 대상에 접근할 권한이 없습니다. |
| 정상 404 NOT_FOUND | 404 NOT_FOUND | 지원 대상 기록을 찾을 수 없습니다. |
| 잘못된 Content-Type·JSON·status·code의 403/404, 400·401·405·409·422·5xx 등 나머지 비-2xx | 기존 503 SUPPORT_DEPENDENCY_UNAVAILABLE | 학습 지원 API 처리를 확인하지 못했습니다. |
| 잘못된 2xx 응답 | 기존 502 SUPPORT_INVALID_RESPONSE | 기존 성공 응답 검증 유지 |

공개 영향은 신고 접수 POST, 시도 연결 문의 POST, 관리자 신고·문의 상세 GET, 최초 정정 POST의 대상 사전 GET이다. 사전 GET 실패 시 정정 의도를 만들거나 learning 정정 POST를 호출하지 않는다. 실제 learning 정정 POST의 403/404는 이 정책에 포함하지 않고 기존 503을 유지한다. 정정 POST의 409/422·멱등성·실패 상태 저장은 아래 계약을 유지한다. 전송 오류·시간 초과·서킷 차단은 기존 LEARNING_UNAVAILABLE(503)·LEARNING_TIMEOUT(504)·LEARNING_CIRCUIT_OPEN(503)이다.

기존 FORBIDDEN·NOT_FOUND를 재사용하며 신규 오류 코드는 없다. learning의 FORBIDDEN은 학생 범위·역할·scope 형식 거부를 구별하지 않으므로 학생 범위 오류로 단정하지 않는다. 프레임워크의 경로 없음도 NOT_FOUND여서 정상 Problem Details만으로 리소스 부재와 완전히 구분할 수 없다. 인증된 요청자가 403/404로 권한 거부와 대상 부재를 구별할 수 있는 공개 정보 차이는 승인된 정책이며 학생 식별자·원문은 오류에 추가하지 않는다. 학생 scope 설정·복원, 트랜잭션 밖 호출, 성공 응답 allowlist·감사 저장은 그대로다.

#### 5.7.3 #46 관리자 정정 공개 오류 계약

공급자 비-2xx는 기본적으로 `503 SUPPORT_DEPENDENCY_UNAVAILABLE`이며, 정정 POST에 한해 다음처럼 구분한다. 공급자 오류 본문·내부 상세·임의 code는 공개 응답에 전달하지 않는다.

| learning 응답/실패 | 관리자 `POST /admin/error-reports/{id}/corrections` 응답 | 상태 처리 |
|---|---|---|
| 409 (DONE 이전·reportId/키 충돌) | **409 SUPPORT_CORRECTION_CONFLICT** | 정정 FAILED, 신고 IN_REVIEW 유지, 완료 알림 없음 |
| 422 (같은 키·다른 본문) | **422 SUPPORT_CORRECTION_REJECTED** | 정정 FAILED, 신고 IN_REVIEW 유지, 완료 알림 없음 |
| 실제 정정 POST의 그 외 비-2xx (403·404 포함), 조회 API의 409·422 등 위 GET 예외 외 오류 | **503 SUPPORT_DEPENDENCY_UNAVAILABLE** | 완료로 표시하지 않음 |
| 2xx의 잘못된 JSON·필수 필드·impact 코드(learning 응답의 `APPLIED`·`NOT_APPLIED`·`UNKNOWN`만 허용. `AFFECTED`·`NOT_AFFECTED`는 core가 계산하므로 검사 대상 아님) | **502 SUPPORT_INVALID_RESPONSE** | 완료로 표시하지 않음 |
| 전송/시간 초과/서킷 차단 | 기존 LEARNING_UNAVAILABLE(503) / LEARNING_TIMEOUT(504) / LEARNING_CIRCUIT_OPEN(503) | 완료로 표시하지 않음 |

core 자체의 권한·상태·본문 충돌 오류는 기존 계약을 유지한다. 이 표는 공급자 HTTP 응답 변환 계약이다.

#46 신고 POST의 최초 접수 응답은 RECEIVED·검토 결과 없음·정정 이력 없음으로 고정한다. 공통 멱등 응답 저장 실패 후 재구성해도 이미 진행된 관리자 처리 결과를 최초 접수 응답에 섞지 않는다. 생성 시각은 PostgreSQL과 같은 UTC 마이크로초 정밀도를 사용한다. 최신 learning #27의 기록 상세는 ADMIN을 허용하지 않으므로 이를 보호자/SYSTEM으로 위장 호출하지 않는다.

### 5.8 리포트 현재 이용권 연결 (#129)

- 생성은 기존 `ReportJobService → ReportEntitlementService → ProductEntitlementService`를 사용한다. 상품·구독 판정값을 job과 같은 트랜잭션의 `report.generate.narrativeEnabled`에 기록한다. 무료 상품 누락·잘못된 상품 설정·결제 확정 중 오류를 무료 권한으로 대체하지 않는다. 데모 계정 우회 정책은 없다.
- 상세·다운로드는 연결 자녀와 동의를 검사한 후 현재 이용권을 조회한다. `ReportQueryService → ReportClient`가 검증된 boolean으로 `X-Report-Narrative-Enabled`를 직접 설정한다. 공개 입력 헤더를 복사하지 않는다. 목록·근거 조회에는 추가 이용권 판정을 요구하지 않는다.
- 상세는 HTTP 호출 전에 선택한 범위를 유지한다. HTTP 뒤 기존 parent 잠금 안에서 권한·연결을 다시 확인하고 열람을 기록한다. 요청 당시 또는 최종 판정이 무료이면 `narrative`·`eveningQuestion`을 null로, `thinkingTypes[].summary`를 제거한다. 호출 중 유료로 바뀌어도 이미 받은 무료 응답을 전체 응답으로 간주하거나 프리미엄 사용으로 기록하지 않는다.
- 다운로드는 상세 메타데이터와 파일 요청에 같은 판정값을 사용한다. 메타데이터가 식별한 불변 reportId를 파일 경로에 사용한다. 무료는 free, 유료는 full을 요청하며 본문에서 서술 유무를 추측해 파일 권한을 결정하지 않는다. full 요청은 최종 parent 잠금 안에서도 유료여야 URL을 반환한다(상실 시 403 REPORT_PREMIUM_REQUIRED). free 요청 중 유료 전환이 생겨도 free URL만 반환하며 프리미엄 사용을 기록하지 않는다.
- `ReportViewService`는 요청 시 선택한 범위와 반환 직전 권한을 함께 사용해 프리미엄 사용을 기록한다. parent 잠금·환불 직렬화는 유지하고 외부 HTTP는 트랜잭션 밖이다. 최종 확인 이후 이미 발급된 서명 URL은 기존 TTL 동안 유효하며 이 변경은 발급된 URL의 즉시 회수 기능을 추가하지 않는다.
- 공개 API 경로·응답 필드·이벤트 스키마·DB는 유지한다. 실제 report 공급자의 무료 투영·free/full 파일 계약을 재사용한다.

### 5.9 리포트 작업 복구 (#132)

`POST /internal/report-jobs/{jobId}/reconcile` (core → report). 내부 토큰 + SYSTEM + 정확히 한 학생 scope가 필요하다. 요청 `{studentId,periodFrom,periodTo,periodType?}`는 core 작업의 학생·기간·기간 종류다. periodType 생략은 WEEKLY(월~일), DAILY는 periodFrom=periodTo 하루만 허용한다(#391). report는 기존 행/차단 기록과 이 값들을 대조하며 불일치는 409 `REPORT_JOB_IDENTITY_MISMATCH`로 거부한다.

200 응답은 `{jobId,studentId,periodFrom,periodTo,status,reportId,failureReason}`이다. status는 BUSY·COMPLETED·FAILED. BUSY는 reportId/failureReason null, COMPLETED는 실제 reportId 필수·사유 null, FAILED는 실제 ID가 있을 때만 reportId 및 원문 없는 대문자 사유 코드다. 원문·서술·파일 URL은 반환하지 않는다. `Cache-Control: no-store`. DB/통신 실패는 오류이며 종료로 간주하지 않는다.

기존 학생 shared/job exclusive session advisory lock 획득 실패는 BUSY다. 잠금 획득 후 저장된 종료 결과를 반환하거나 소유자 없는 RUNNING을 `REPORT_EXECUTION_ABANDONED`로 종료한다. 행이 없으면 `report_job_guard`에 `REPORT_NOT_CREATED`를 원자 저장한다. 삭제 표식 PENDING은 BUSY, COMPLETED는 `STUDENT_DELETED` 실패다. 동일 호출/응답 유실 재호출은 같은 저장 결과를 사용한다. 삭제 완료 후에는 삭제 결과가 우선한다. v1 이벤트의 reportId 필수 계약은 유지한다.

core는 생성 후 4시간 이상 QUEUED/RUNNING을 기본 1분마다 점검한다(`app.report.recovery.stale-after` 기본 `PT4H`, `app.report.recovery.interval`). 4시간은 운영 후보 선정 정책이며 실행 시간 측정값/강제 중단 제한이 아니다. 월 00:00에는 주간·일일 작업이 함께 생성되고 report-worker 1대·prefetch 1로 차례로 처리되므로, 기준은 `주간 설명 대상 수 × (설명 단계 400초 + 기본 생성 시간) + 일일 처리 시간`보다 길어야 한다. 데모 30명 기준 30×(400+약 30)초 ≈ 215분 + 일일 수 분 < 240분이다(#508). 실행 중 작업은 report 리스가 잡혀 BUSY로 남으므로 이 기준은 큐에서 기다리는 작업에만 의미가 있다. 학생 수가 늘거나 #475 실측으로 설명 시간이 바뀌면 다시 계산한다. HTTP는 DB 트랜잭션·행 잠금 밖에서 수행하고 새 트랜잭션에서 학생·작업·종료 상태를 재검사한다. 자동 재생성·재생성 횟수 정책은 변경하지 않는다.

### 5.10 #41 분석 대화 구현 계약

대화·SSE·범위 확인·payment 소비 port·차감 정책은 [#41 계약](../report/core-gateway.md#5-분석-대화-계약-41167)을 따른다. 일일 한도는 Redis 카운터가 아니라 결제 사용 이력(`payment_premium_usage`)의 KST 일자 집계로 판정한다([#225](../report/core-gateway.md#분석-대화-사용량-db-이관-구현-225)). 내부 history는 `{role:USER|ASSISTANT,text}`이며 core messageId를 요청에 추가한다. 같은 대화의 자녀는 고정하며 자녀 변경은 새 대화로 확인한다. 기간 명시는 사용자 확인이고 동일 기간 완료 이력만 AI에 전달한다.

#41 보완(P08): 시작일 이전 답변은 현재 기간의 집계 대상 시도에 포함되는 경우에만 비교 근거로 허용하며 종료일 이후 답변은 거부한다. AI가 contentAllowed를 보내면 false인 결과는 확정하지 않는다.

### 5.11 #167 하위 호출 차단

분석 AI OPEN은 기존 SSE error의 502 AI_UNAVAILABLE 및 FAILED 저장으로 처리한다. 접수 시 한도·사용 이력 차감은 유지한다. report 조회/복구 OPEN은 기존 503 REPORT_UNAVAILABLE이며 신규 오류 코드나 Retry-After는 추가하지 않는다. 기존 403/404/409/503 DATA_UNAVAILABLE 매핑은 보존한다. 토스 조회 OPEN은 기존 미확정 결과(결제 상태 유지), 거래 대조 OPEN은 기존 PAYMENT_RECONCILIATION_UNAVAILABLE로 처리하며 성공/거절로 치환하지 않는다. 승인·청구·취소·빌링키 발급은 차단 대상이 아니다.

### 5.12 #47 미션 운영 후속 계약

- overview의 `missionCounts`는 learning 관리자 목록의 전체 DRAFT/REVIEW_REQUIRED/PUBLISHED/UNPUBLISHED 건수를 허용 목록으로 투영한다. 기간·목록 필터·페이지와 무관한 현재 상태이며 학생·미션 본문은 포함하지 않는다. 누락·중복·음수 등 잘못된 집계는 503으로 처리한다.
- 실제 미션 404는 안전한 NOT_FOUND 오류로 전달한다. 405/501은 제공 기능 불가로 유지한다.
- CONTENT 쓰기는 인증된 관리자 UUID로 요청 감사를 먼저 커밋한 뒤 learning을 한 번 호출한다. 성공 응답의 missionId/currentVersion/currentRubricVersion을 검증해 결과 감사를 별도 커밋한다. 외부 HTTP와 core DB는 단일 트랜잭션이 아니다.
- 감사 action은 MISSION_{CREATE,UPDATE,RUBRIC,REVIEW_REQUEST,REVIEW,PUBLISH,UNPUBLISH}_{REQUESTED,SUCCEEDED,REJECTED,UNKNOWN}. REQUESTED의 SUCCESS는 요청 기록 성공만 뜻한다. 계약에 맞는 4xx 문제 응답은 REJECTED, 5xx·통신 단절·해석할 수 없는 응답은 UNKNOWN이다. 요청 원문·공급자 오류 원문은 저장하지 않는다.
- 쓰기 응답의 X-Admin-Operation-Id는 요청 감사 ID다. 연결 실패 오류는 detail에 같은 확인 번호를 제공한다. 결과 감사 저장 실패는 503 MISSION_AUDIT_UNAVAILABLE이며 요청 기록이 남는다. 성공으로 응답하거나 자동으로 쓰기를 재호출하지 않는다. REQUESTED만 남은 작업은 결과 미확정으로 운영자가 learning에서 확인한다.
- 공개 감사 목록은 기존대로 detail을 제외한다.
### 5.13 #67·#41 분석 최종 응답 계약 보완

`verification`은 source와 관계없이 최종 answer를 실제 검사한 numbersMatched/quotesMatched/contentAllowed다. 최종 검사를 통과한 응답만 result로 확정한다. 대조 실패 초안은 fallback.draftVerification에 보존하며 값을 true로 덮어쓰지 않는다. 정상 LLM은 fallback/notice=null, 규칙 응답은 fallback.reason=VERIFICATION_FAILED 또는 AI_UNAVAILABLE와 notice=null, 기록 부족·지원 외 안내는 fallback=null과 notice.reason=NO_RECORD|NO_CHANGES|NO_REFLECTIONS|UNSUPPORTED|MATH_CHECK다. LLM 장애의 draftVerification은 null이다. 최종 템플릿/안내 검사 실패는 FINAL_RESPONSE_VERIFICATION_FAILED error이며 result/done으로 대체하지 않는다. learning 조회 실패도 기존 error다. LLM 장애 후 기본 조회가 비어 있더라도 AI_UNAVAILABLE를 보존한다. 임시 delta는 최종 result.answer로 교체하고 error/clarification 시 폐기한다. 숫자 검사는 계산 결과와 허용 기간 숫자, 인용 검사는 원문 공백 정규화 범위를 사용한다. 계산에 없는 고정 임계 숫자는 안내에 넣지 않는다.

#67 돌아보기 근거: kind=ANSWER는 answerId/answerVersion 필수, kind=REFLECTION은 둘 다 null이며 attemptId로 식별한다. core는 기존 learning 시도 상세 API의 reflection.text/createdAt, 현재 학생 권한 및 요청 기간의 시도 포함 여부를 검증한다. 근거 원문은 별도 복제하지 않고 참조만 저장한다. 기존 ANSWER 근거는 그대로 유지한다. conversation_message의 fallback/notice는 JSONB로 저장해 다시 조회해도 초안 실패 정보·정상 안내를 보존한다. 최종 템플릿 검증 실패도 오류이며 임시 delta는 폐기한다.

### 5.14 #47 CONVERSATION 관리자 재처리

SERVICE_OPS는 실패 message ID에 UUID Idempotency-Key로 재처리를 접수한다. 202는 `{jobId,type:CONVERSATION,retryRequestId,generation,status:QUEUED,acceptedAt}`이며 Location은 기존 작업 상세다. 같은 관리자·키는 완료 후에도 같은 접수 응답을 반환하고 다른 메시지에 재사용하면 422다. 새 키의 동시 요청은 한 세대만 접수한다. 관리자 화면에 질문·답변 원문을 반환하지 않는다.

접수는 현재 학부모 계정·연결·동의·상품 권한을 검사하고 메시지를 새 RUNNING 세대로 선점하며 새 요청 표의 QUEUED·요청 감사를 같은 DB 트랜잭션으로 저장한다. 작업 조회는 대기 요청을 QUEUED로 투영한다. DB 대기 작업을 core 내부 작업자가 실행하며 실제 실행 시 권한·상품·사용량을 재검사한다. 한도 부족 등 실행 전 거절은 비동기 FAILED이며 임의 성공으로 바꾸지 않는다. 실제 실행부터 job_execution을 기록한다.

사용량 차감은 실행 선점 트랜잭션 안의 결제 사용 이력 행이라 DB 저장과 함께 커밋·롤백된다(#225). 관리자 실행은 영속 요청 ID를 사용 이력 source ID로 써서 한 번만 차감하며, 이미 기록된 요청 ID는 추가 차감·한도 재판정을 하지 않는다. 130초 대기·실행 만료(대화 RUNNING 고착 판정과 같은 값)를 적용하며 중단 작업은 실패 처리하고 자동 AI 재실행하지 않는다. 부모 SSE는 기존 소비 정책을 보존한다.

학부모 SSE와 관리자 실행은 같은 AI 이벤트 순서·최종 검증·근거 확인·저장 경로를 사용한다. 관리자는 학생 원문을 수신하지 않는다. 내부 실행 컨텍스트는 권한을 재검사한 대화 소유 학부모이며 요청 관리자는 별도 감사에 보존한다. 성공·실패·stale 세대 종료 감사는 상태/실행 이력과 같은 트랜잭션이며, 늦은 세대 결과는 현재 실행을 덮어쓰지 못한다. #162의 fallback·notice·ANSWER/REFLECTION 계약은 최종 통합에서 그대로 유지한다.

학생 삭제 시 요청 표는 message FK CASCADE로 정리하며 삭제 전 실패 이력·감사를 같은 트랜잭션에 기록한다. 삭제된 작업 조회·새 접수는 404다. 기존 멱등 캐시의 과거 202가 재전달될 수 있으나 재실행하지 않는다.

관리자 재처리 화면은 202 QUEUED를 접수로 안내하고 REPORT는 응답의 새 jobId, CONVERSATION은 기존 jobId의 상세를 조회한다. 사용자가 상태를 새로 조회할 수 있고 실제 COMPLETED 응답에만 완료 문구를 표시한다. NOTIFICATION의 200 완료/실패 구분은 유지한다.

#163·#47 통합: 검증된 미션 404는 GET/쓰기 모두 고정 문구의 404 NOT_FOUND를 반환한다. 쓰기는 요청 감사와 REJECTED 결과 감사 및 X-Admin-Operation-Id를 보존한다. 불명확한 404·405·501은 503이며 쓰기 결과 감사는 UNKNOWN이다.

### 5.15 2026-11-01 확정 변경: #206·#207

- `GET /api/v1/students/me/sharing-preferences`와 `PUT /api/v1/students/me/sharing-preferences`는 학생 세션의 단일 학생만 대상으로 합니다. PUT 본문은 `{parentSharingEnabled: boolean}`, 응답은 `{studentId, parentSharingEnabled}`이며 누락/null은 400입니다. 기본값은 false입니다. 학부모는 `GET /api/v1/children/{childId}/sharing-preferences`로 연결된 자녀의 상태만 조회할 수 있습니다.
- 비공개 상태에서 학부모의 답변 목록·상세·분석 대화·근거·기존 다운로드 URL 재발급은 `403 STUDENT_RECORDS_PRIVATE`입니다. 요약·유형 집계와 리포트의 수치는 유지합니다. 리포트 상세의 답변·돌아보기·인용·파생 문구는 제거하며, 기존 원문 포함 파일은 비공개 중 재발급하지 않습니다. 이미 전달된 파일은 회수할 수 없습니다.
- 내부 학생 프로필에 `parentSharingEnabled`를 추가합니다. report는 생성 시 현재 값을 조회하고 false 또는 누락이면 원문·근거 링크·원문 기반 AI 문구를 생성/파일 렌더링 전에 제거합니다. 기존 리포트의 조회도 core에서 현재 설정을 다시 확인합니다.

- #207 조회 경로: core `GET /api/v1/attempts/{attemptId}/comparison` → learning `GET /internal/attempts/{attemptId}/comparison`. 응답 상태는 `NO_PREVIOUS | COMPARABLE | CRITERIA_CHANGED`, 각 스냅샷에 고정 문항·제출 답변·마지막 판정·기준표를 포함합니다.
- #207 사용자 확정: 같은 학생·미션의 **직전 마무리 시도**를 비교 기준으로 삼는다. 기준은 현재 시도 시작 이전에 마무리한 시도 중 finishedAt 내림차순(동률은 startedAt·ID 순) 첫 건이다. 이전 답변·판정·피드백을 덮어쓰지 않는다. 현재 시도의 마무리 이후에만 비교를 공개한다. 기준표 버전이 다르면 요소 충족 변화는 직접 비교하지 않고 기준 변경을 안내한다. 이전 시도가 없으면 명시적으로 비교 기록 없음이다.

### 5.16 #209 학부모 리포트 템플릿 설정 (로컬 구현 계약)

2026-11-02 사용자 전달 승인: 원문 공개는 #206 학생 전역 설정만 사용(학생 본인 변경,
기본 비공개), 메모 제외. 섹션 숨김은 승인하지 않음. 기존 권한·숫자·인용 대조 유지.
설정은 학부모별이며 자녀 전반의 다음 생성에 사용. 기존 리포트 판은 변경하지 않는다.

- `sectionOrder`: `thinkingTypes, changes, reflections, quotes, narrative, eveningQuestion`의
  중복 없는 전체 순열. 학생·기간·상태·집계 기준과 수치 표는 고정한다.
- `highlightMetrics`: 기존 지표 코드 `ATTEMPTS`, `COMPLETED`, `UNASSISTED` 중 중복 없는 목록.
  계산식·값은 바꾸지 않는다. 순서대로 답변 제출 시도 수·완료한 시도 수·도움 없이 시작한 비율.
- `tone`: `DEFAULT`(기본), `EASY`(쉬운 설명), `CONCISE`(간결).
- 공개 여부·메모·섹션 삭제·임의 계산식 필드는 받지 않는다.

`POST /api/v1/conversations/{id}/report-template/proposals` `{question}`:
기존 대화 소유권·연결·동의·분석 권한 및 사용 한도 확인 후 AI가 변경안을 해석한다.
접수된 제안 요청은 기존 분석 대화와 같이 한도를 차감하고 결제 사용 증빙을 기록한다.
AI 실패·확인 질문도 접수된 시도로 취급하며, 설정 조회와 제안 확정은 추가 차감하지 않는다.
모호하거나 지원 밖이면 clarification만 반환하고 저장 설정을 변경하지 않는다.
명확하면 `{proposalId, settings, expiresAt}` 반환. 초안은 10분 유효하며 새 제안이 기존 것을 대체한다.
`POST /api/v1/conversations/{id}/report-template/confirm` `{proposalId}`:
현재 권한 재확인 후 서버에 저장된 초안만 확정. 다른 대화·만료·덮어쓴 초안은 409.
클라이언트가 설정을 바꿔 보내는 방식이 아니다.
`GET /api/v1/conversations/{id}/report-template`: 현재 확정 설정과 revision.

`POST /internal/analysis/report-template` `{question,current}` →
`{settings,clarification}` (둘 중 하나만 존재). PARENT 내부 컨텍스트, ANALYSIS 사용량.
`GET /internal/students/{studentId}/report-template`: SYSTEM + 대상 학생 scope,
현재 연결 학부모의 `{settings,revision}`. 권한·조회 장애를 기본 설정으로 대체하지 않는다.
report-worker는 생성 시작 시 한 번 조회하여 command에 고정한다. 메시지 v1은 변경하지 않는다.
생성 결과 `versions.template`에 `{settings,revision}`을 보존하여 과거 판을 재해석하지 않는다.
서술 요청에 `tone`을 추가하며 생략 시 DEFAULT. 무료·NO_RECORD AI 생략, 대조 실패 처리 유지.

원문 비공개 생성·기존 파일 접근은 #206 계약(5.15)을 따른다.

화면 동작은 [기능명세서](functional-spec.md) 2.6.1.

### 5.17 #289 학부모 탈퇴 전 자녀 이관

이 절은 #275의 잘못된 다중 보호자 전제를 정정한 #289의 정식 이관 흐름이다(#309·PR #325). 기능 플래그는 노출을 제어한다. 서버
`app.guardian-transfer.enabled=true`와 웹 `VITE_GUARDIAN_TRANSFER_ENABLED=true`에서만
신규 대상 조회·요청·수락 진입점을 제공한다. 본인의 기존 요청 조회·거절·취소는 설정과 필수 동의 상태에 관계없이 제공한다(#307). 두 설정의 기본값은 false이며, V26 마이그레이션은 기존 V24 보호자 비밀번호와 V25 동의 문서를 보존한다. 기능 플래그는 DB 롤백 수단이 아니다.

- `POST /guardian-transfers/recipient` `{email}`: 가입 Google 이메일의 활성 학부모를 정확히 조회.
  본인/비학부모/미가입/중복 이메일 후보는 거부하며 자녀 3명 제한을 확인한다.
- `GET /guardian-transfers`: 본인이 보낸/받은 요청만 반환. 자녀가 없거나 필수 동의가 누락·철회되어도, 서버 플래그가 꺼져 있어도 조회 가능. 학습 기록·리포트 조회 권한은 부여하지 않는다.
- `POST /guardian-transfers` `{childId,recipientId,includeConversations}`와
  `X-Reauth-Token`(CHILD_TRANSFER, 해당 자녀): 자녀별 PENDING 요청 생성.
- `POST /guardian-transfers/{id}/accept` `{consents}`와 `X-Reauth-Token`(TRANSFER_ACCEPT):
  수신자가 현재 GUARDIAN 문서에 동의하면 연결·동의·선택 대화 소유권을 같은 트랜잭션에서 변경.
- `POST /guardian-transfers/{id}/reject`, `/cancel`: 수신자 거절/발신자 취소. 종료 상태는 되돌리지 않는다.
- `POST /guardian-transfers/cancel-outgoing`: 탈퇴 재진입 확인 시 본인의 대기 요청만 취소.
  이 호출 자체는 탈퇴·삭제를 수행하지 않는다.
- 기본 이관은 동일 학생 ID의 프로필·학습·리포트 유지. 상담 대화 포함은 기본 false이며
  발신자와 해당 자녀의 대화만 이관한다. 결제·구독·리포트 표시 설정은 학부모 간 이전하지 않는다.
- 발신자의 기존 탈퇴 사전 검사 및 자녀의 활성 구독 정리가 요청/수락 시 모두 필요하다.
  삭제 요청이 있는 자녀, 실행 중 상담/관리자 재처리는 이관하지 않는다.
- PENDING 동안 자녀 삭제·연결 해제·발신자 탈퇴를 거부한다. 수락 전 기록 접근은 허용하지 않는다.
- 이전 연결은 이관 완료 표식을 남겨 일반 연결 해제와 구분한다. 이전 학부모는 삭제 권한을 잃고,
  탈퇴해도 이관된 자녀/대화는 유지한다. 미이관 대화는 이전 학부모 탈퇴 시 별도 정리한다.
- 기존 학생 세션·기기 연결은 종료하며 새 학부모가 기기를 등록한다. 새 보호자의 기존 리포트 설정을 사용한다.
- 수락·취소·동시 자녀 등록은 계정 ID 정렬 잠금 → 학생 → 요청 순서로 직렬화하고 DB에서 활성 보호자 1명을 강제한다.
- 새 이관 경로는 기존 개인정보·보호자 동의·재인증을 우회하지 않는다. 기존 삭제/탈퇴 경로는 그대로 유지한다.
- 조회·수신자 거절·발신자 단건/일괄 취소는 동의 회복 경로다(#307). 활성 학부모 계정·유효 세션·요청 소유권은 계속 검사한다. 플래그 off여도 PENDING 삭제/탈퇴 차단은 유지하며, 명시적 취소/거절로 대기를 해소한 후 기존 재인증·최종 확인을 거쳐 삭제/탈퇴한다. 자동 취소·자동 탈퇴·대기 검사 우회는 하지 않는다.
- 같은 대상·수신자·대화 선택의 대기 요청 재전송과 같은 종료 상태 재전송은 멱등 처리한다. 다른 종료 상태로 바꾸면 `409 TRANSFER_ALREADY_RESOLVED`다.


#### #391 report 일일 생성·주간 테마 소비 계약

- report 내부 목록 `GET /internal/reports`는 선택 `periodType=DAILY|WEEKLY`를 받는다. 미지정은 두 종류 모두이며 `(studentId,periodType,periodFrom)`별 최신 판이다. 상세·목록에 periodType을 반환하고 상세 problems는 일일, themeSummary는 주간에 사용한다. 구체적인 중첩 필드는 report OpenAPI를 따른다. core 공개 프록시는 #390에서 연결한다.
- 일일 항목은 PROBLEM으로 저장한다. `mission.id`, `feedback.followup.question`, 판정·요소와 제출 답변을 기존 learning 응답에서 읽는다. `context`는 learning 기록 응답 값을 그대로 쓰며 임의로 추정하지 않는다. 원문 비공개면 finalAnswer=null, followups/quotes=[], reflection.text=null, evidence 없음. 일일은 비율·서술·저녁 질문을 생성하지 않는다.
- learning `GET /internal/records/students/{studentId}/daily-attempts?from&to&page&size`는 같은 KST 날짜의 **완료 시각**으로 조회한다. 기존 P08의 제출일 조회와 분리하며 응답은 RecordPage와 같다. 전날 제출·오늘 완료도 포함한다. 학생 scope·삭제 검사와 페이지 제한은 기존 기록 조회와 같다.
- learning 주간 테마 summary API는 #385에서 구현했다(내부 API 표 `GET /internal/students/{studentId}/weekly-theme/summary`). report 소비 계약은 `{studentId,weekStart,state,themeId,title,days:[{day(MON~FRI),missionId,title?,completed,completedInWeek?}],completed,reviewRetries:[{missionId,title?,comparison?{state,elements:[{label,previousSatisfied,currentSatisfied}]}}],finished?,ending?}`이다(`?` 칸은 #486 선택 칸). 날짜·학생 범위를 검증하며 NO_RECORD는 themeId/title=null, 배열=[], completed=false다. HTTP 오류·형식 오류를 NO_RECORD로 숨기지 않는다.
- 복구 요청 `POST /internal/report-jobs/{jobId}/reconcile`도 periodType을 받는다. 미지정 WEEKLY, DAILY는 하루만 허용한다. 응답은 기존 7개 필드를 유지하며 periodType을 추가하지 않는다.

- #391 learning 기록 목록·상세·일일 완료 목록은 `context: THEME_DAY|THEME_REVIEW|EXTRA`를 실제 시도에서 반환한다. 주간 요약은 기존 #207 비교 규칙의 상태·요소만 포함하며 답변 원문·인용은 반환하지 않는다.

### scoring Pod별 모델 로딩 확인 (#370)

`GET /api/v1/admin/model-loading` (SERVICE_OPS): `pods[]`의 Pod·프로세스·보고 시각·stale·모델 상태와 `summaries[]`의 활성 name/version/revision별 observedPods·loadedPods·failedPods를 반환한다. 분모는 최근 120초 안에 보고한 Pod이며 Kubernetes 전체 replica 수가 아니다. 0개는 미확인이다. 품질 승인·추론 확인과 분리한다. 이벤트 `model.loading.reported.v1`로 30초마다 전체 상태를 재보고하며 상태 보관·배포 순서는 [#370 설계](../report/ai.md#13-pod별-모델-로딩-보고-370)를 따른다.
