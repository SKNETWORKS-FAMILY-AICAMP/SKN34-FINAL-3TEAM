# 점검·검증 기록

통합 원본: develop-verification, docs-consistency-audit, issue-94-96-audit-fixes

## 1. develop 종합 검증 (c608f52)

리포트 #50~#55 병합 직후 develop `c608f52`의 테스트·코드↔문서·문서 간 정합성·코드 결함·테스트 공백 점검. 발견 항목(코드↔문서 C1~C15, 문서 간 D1~D14, 결함 B1~B17)과 처리는 1.3, 남은 항목은 1.5.

### 1.1 실행 결과

Windows 11 로컬 실행. CI(`_python.yml`·`_spring.yml`·`_web.yml`·`ci-db-schema.yml`)와 같은 명령을 사용했다.

| 대상 | 명령 | 결과 |
|---|---|---|
| ai-service | `uv sync --frozen` → `ruff check` → `ruff format --check` → `pytest` | 통과. 167건(161초) |
| scoring-service | 동일 | 통과. 5건. 경고 1건(`starlette.testclient`의 httpx 사용 폐기 예정) |
| report-service | 동일 + `playwright install chromium` | 통과. 239건(190초), 수정 후 240건. PostgreSQL·RabbitMQ·MinIO 컨테이너, Chromium 사용 |
| 루트 계약 테스트 | report `.venv` + `jsonschema==4.26.0`, `python -O -m unittest discover -s scripts/tests` | 통과. 58건 |
| DB 마이그레이션 | 임시 `postgres:17.11-alpine`에서 `scripts/check_db_migrations.py` | 통과. core 40/351, learning 19/158, report 7/50(테이블/컬럼), 위반 입력 60건, CHECK 값 67종, 인덱스 23개, 재실행·Alembic 왕복 |
| core-service | `gradle:8.14.6-jdk21` 컨테이너에서 `./gradlew test bootJar` | 통과. 205건(11분 23초), 수정 후 208건. PostgreSQL·Redis·RabbitMQ Testcontainers |
| learning-service | 동일 | 통과. 186건(4분 48초), 수정 후 187건 |
| 계약 산출물 | core 테스트 산출물로 `scripts/validate_report_contracts.py`·`validate_notification_contracts.py` | 통과. report 이벤트 4종·상세 응답, 알림 목록·설정 응답 |
| web | `npm ci` → `npm run lint` → `npm run build` → `npm test` | 통과. lint 0건, 빌드 성공(번들 583 kB, 500 kB 초과 경고), 단위 87건 |

- 로컬 PC에는 JDK 17만 있고 Gradle toolchain은 21을 요구한다. `settings.gradle.kts`에 toolchain 자동 설치 플러그인이 없어 로컬 `./gradlew`는 바로 실패하므로 `gradle:8.14.6-jdk21` 컨테이너에서 Docker 소켓을 연결해 실행했다.
- 인가 우회(B1·B2)는 core에 임시 `@SpringBootTest(RANDOM_PORT)` 테스트를 두고 실제 Tomcat에 원시 URI로 요청해 재현했다. 임시 테스트는 커밋하지 않고 삭제했다.
- 수동 검증 스크립트 `scripts/verify_*.py`(JDK 21·빌드 JAR·전용 컨테이너 필요)와 `check_policy_migrations.py`는 이번 범위에서 실행하지 않았다.

### 1.2 코드 결함

| # | 상태 # | 심각도 | 결함 | 확인 | 근거 |
|---|---|---|---|---|---|
| B1 | 해결 | 높음 | 역할·관리자 권한을 디코딩하지 않은 `requestURI` 접두사로 판정. Spring MVC는 `;매개변수`를 제거하고 `%xx`를 디코딩한 경로로 핸들러를 매칭하므로 학부모 토큰이 관리자 API에 도달. 학생·학부모 역할 검사(`/missions`·`/children` 등)도 같은 구조. 관리자 컨트롤러·서비스에 권한 재검사 없음 | **재현됨**(실제 Tomcat, 임시 테스트): 학부모 토큰으로 `/api/v1/admin/ai-usage` 403, `/api/v1/admin;x/ai-usage`·`/api/v1/%61dmin/ai-usage`·`/api/v1/admin;x/model-versions` 200. 쓰기 API(activate·rollback·등록)도 같은 판정 경로 | `_common/security/PublicAuthFilter.kt:18-65`, `ModelVersionController.kt`, `AiUsageController.kt` |
| B2 | 해결 | 높음 | 내부 토큰 검사도 같은 접두사 판정이라 `/internal;x/…`가 검사를 건너뜀. core `/internal/model-versions/active`는 컨텍스트 없이 응답, 나머지는 `UserContextHolder.current()`에서 500 예상 | **재현됨**: 토큰 없이 `/internal/model-versions/active` 401, `/internal;x/model-versions/active` 200 | core·learning `InternalAuthFilter.kt:24-25` |
| B3 | 이슈 | 높음 | learning에 `student.deleted` 소비자 없음. core는 learning·report 완료 보고가 모두 와야 삭제를 COMPLETED로 바꾸므로 자녀 삭제·탈퇴가 끝나지 않음. learning `EventEnvelope`·`MessagingConfig` 미사용 | 코드 검색(learning `src/main`에 소비자 0건) | `ChildManagementService.kt:91-96`, `definitions.json` `learning.student.deleted`, `report-required-inputs.md:55` |
| B4 | 일부 해결 | 높음 | `ReportEntitlementService.narrativeEnabled`가 항상 503. 자동 생성·재생성 모두 실패. 스케줄러는 자녀별 예외를 격리하지 않아 첫 실패에서 그 주 실행 전체 중단. 테스트는 이 서비스를 mock으로 대체 | 코드 확인 | `ReportEntitlementService.kt:11`, `ReportJobService.kt:43`, `ReportScheduleService.kt:14-21`, `ReportHttpTest.kt:53` |
| B5 | 이슈 | 높음(문서화됨) | report-worker 생성기가 항상 `UnconfiguredGenerator`라 모든 요청이 `GENERATOR_NOT_CONFIGURED`로 FAILED. 실제 생성기를 연결해도 codec이 `display_name`을 채우지 않아 렌더링 실패, ai 서술 API 미구현(C9) | 코드 확인, `report-service-handoff.md:22` | `report-service/app/worker.py:92`, `generation/codec.py:56-63`, `rendering/generator.py:28` |
| B6 | 해결 | 중간 | core 리포트 목록의 `status=QUEUED`(OpenAPI 허용)를 report에 그대로 전달. report `ReportStatus`에 QUEUED가 없어 400 → core가 503 `REPORT_UNAVAILABLE`로 응답 | 코드 대조 | `ReportQueryService.kt:23`, `core-service.yaml:1841`, `report-service/app/query/router.py:56`, `generation/models.py:10-13` |
| B7 | 해결 | 중간 | `ReportClient`가 403·404 외 모든 응답을 503 `REPORT_UNAVAILABLE`로 변환. report의 409 `DELETION_IN_PROGRESS`·503 `DATA_UNAVAILABLE`·400이 구분되지 않음(api-spec 1.3 공개 코드 소실) | 코드 확인 | `ReportClient.kt:30-34` |
| B8 | 이슈 | 중간 | report Outbox가 가장 오래된 미발행 행부터 선택. 영구 실패하는 이벤트 하나가 1초마다 재시도되며 뒤 이벤트 발행을 막음 | 코드 확인(미재현) | `report-service/app/outbox/repository.py:66-95`, `worker.py:45-53` |
| B9 | 이슈 | 중간 | 종료 이벤트 없이 core 작업이 QUEUED/RUNNING에 남는 경로: 삭제 표식 COMPLETED 시 생성 요청 조용히 ACK, codec `InvalidEvent`·`JobConflict` 후 DLQ, `GenerationBusy` 3회 후 DLQ, 학생 삭제 시 해당 학생의 미발행 Outbox 행 삭제 | 코드 확인(core 정리 방식 확인 필요) | `generation/service.py:84-86`, `deletion/state.py:148` |
| B10 | 이슈 | 중간 | 기기 등록 rate limit 키가 `request.remoteAddr`인데 `server.forward-headers-strategy` 미설정. 프록시 뒤에서 모든 사용자가 한 버킷(10분당 20회)을 공유 | 설정 확인 | `StudentDeviceController.kt:36`, core `application.yml` |
| B11 | 이슈 | 중간 | 웹 실서버 모드가 `/children` 응답의 `plan`을 읽지만 OpenAPI·코드에 없음. 저녁 질문이 항상 숨겨지고 숫자·인용 대조 검사를 건너뜀 | 코드 대조 | `frontend/web/src/data/classroom/apiGateway.ts:206,351,375` |
| B12 | 이슈 | 중간(미해결 #93·#97) | 웹 관리자 모델 레지스트리 요청 모양(`evalResult`, `{reason, reanalyze}`)이 OpenAPI와 다름. `/auth/login`·`/auth/signup` 호출, `/me/reauth`에 `{password}` 전송 잔존 | 코드 대조 | `src/data/admin/api.ts:64-75`, `src/data/parent/api.ts:42,49`, `src/data/apiClient.ts:113` |
| B13 | 일부 해결 | 낮음 | 웹 재생성 409 코드를 `REGENERATE_NOT_ALLOWED`로 처리, 리포트 목록을 page 봉투로 가정, `PATCH /children`에 `X-Reauth-Token` 전송·필드 필수 처리 | 코드 대조 | `apiGateway.ts:391`, `parent/api.ts:51,138` |
| B14 | 해결 | 낮음 | `saveDraft`가 잠금 없이 소유·열림 확인 후 버전 조건부 UPDATE. finish·reflection과 겹치면 닫힌 시도에 초안 저장 가능 | 코드 확인(미재현) | learning `AttemptService.kt:147-152` |
| B15 | 해결 | 낮음 | report-api readiness가 쓰지 않는 RabbitMQ에 의존, learning readiness도 미사용 RabbitMQ 포함, core readiness에 Redis 없음 | 설정 확인 | `report-service/app/bootstrap.py:30,43`, core·learning `application.yml` |
| B16 | 해결 | 낮음 | 이미 처리한 삭제 이벤트 재전달 시 다른 요청이 PENDING이면 `RecordContractError` → 3회 후 DLQ | 코드 확인 | `report-service/app/deletion/state.py:88-98` |
| B17 | 이슈 | 낮음 | 미사용 설정 주입(ai `scoring_url`·`core_url`, scoring `core_url`, report `ai_url`), 요청마다 boto3·httpx 클라이언트 생성 | 코드 확인 | `ai-service/app/config.py:16-17`, `report-service/app/query/router.py:23-45` |

### 1.3 처리 결과

PR `feature/develop-verification`에서 단계별 1커밋으로 처리.

| 단계 | 항목 | 처리 |
|---|---|---|
| 1 | B1·B2 | 필터 판정 경로를 Spring 매칭 경로(`;` 매개변수 제거·퍼센트 디코딩)로 정규화. core `PublicAuthFilter`·core/learning `InternalAuthFilter`가 `_common/security/MatchedPath.kt`의 `matchedPath` 사용. 회귀 테스트: `ModelVersionHttpTest`(학부모 토큰 `;x`·`%61dmin` 경로 403), core·learning `InternalAuthFilterTest`(`/internal;x`·`/%69nternal` 401). 수정 전 코드에서 두 테스트 실패 확인. 실제 Tomcat 재현은 403·403·403·401로 변경 |
| 2 | B4(일부) | `ReportScheduleService.generate`가 자녀별 실패를 경고 로그(오류 코드만)로 남기고 다음 자녀를 계속 처리, 실행 끝에 실패 수를 `IllegalStateException`으로 전파. 이용권 공급자 연결은 이슈 대상. 테스트: `ReportRepositoryTest` 한 자녀 실패 시 다른 자녀 작업 생성 |
| 2 | B6 | core 리포트 목록 `status=QUEUED`는 report 호출 없이 400 `VALIDATION_FAILED`. OpenAPI 필터 enum에서 `QUEUED` 제거 |
| 2 | B7 | `ReportClient`가 report 409 `DELETION_IN_PROGRESS`·503 `DATA_UNAVAILABLE`을 같은 상태·코드로 전달, 그 밖은 기존처럼 503 `REPORT_UNAVAILABLE`. OpenAPI 조회 4개 경로에 409, 근거·다운로드 503에 `DATA_UNAVAILABLE` 추가. 테스트: `ReportHttpTest` |
| 2 | B14 | learning `AttemptService.saveDraft`가 `lockOwned`(시도 행 `FOR UPDATE`)로 확인해 마무리·돌아보기와 같은 순서로 직렬화 |
| 2 | B15 | learning readiness에서 미사용 `rabbit` 제거, report-api 수명 주기에서 AMQP 연결·readiness 제거(발행·소비는 worker). core readiness에 Redis는 추가하지 않음(Redis 장애가 로그인 등 전체 API 중단으로 번지지 않도록) |
| 2 | B16 | 이미 처리한 삭제 이벤트가 다른 요청 PENDING 중 재전달되면 계약 오류 대신 완료 보고만 재전송. 테스트: `test_processed_event_redelivered_during_newer_pending_request_resends_completion`(수정 전 실패 확인) |
| 3 | C1 | report 라우터에 problem+json 오류 응답(400·401·403·404·409·503) 선언, `install_problem_openapi`가 FastAPI 기본 422와 검증 오류 스키마를 제거하고 `Problem` 추가. `report-service.yaml` 재생성 |
| 3 | C2·C3 | `ai-service.yaml` versions에 `analysis`, `Mission`에 `title` 속성 추가 |
| 3 | C4 | api-spec 1.3·sequence 6장을 `REPORT_REGENERATION_LIMIT`로 수정. 웹도 서버 코드 사용(이미 생성 중: `REPORT_GENERATION_IN_PROGRESS`, 목업·데모 한도 초과: `REPORT_REGENERATION_LIMIT`) |
| 3 | C5 | 알림 오류 코드를 공통 코드로 통일(`INVALID_REQUEST`→`VALIDATION_FAILED`, `NOTIFICATION_NOT_FOUND`→`NOT_FOUND`). api-spec 1.3에 report 계열·기기·재인증·프레임워크 기본 코드 행 추가, `DELETION_IN_PROGRESS` 설명에 core 전달·삭제 중복 포함 |
| 3 | C6·C8·C12 | ERD 9장 현재 수치(66/559), 10장에 V10·V11 결번과 V12 주석 경위(마이그레이션 미수정), `verification`에 `contentAllowed` |
| 3 | C7 | core `V14__remove_speech_call_type.sql`로 CHECK에서 `SPEECH` 제거, ERD 동시 수정 |
| 3 | C9 | api-spec 4.2 `/internal/report-narratives`·4.3 scoring 전 경로 미구현 표기 |
| 3 | C10 | `NotificationController` 경로 변수를 `{notificationId}`로 변경(URL 동일) |
| 3 | C11 | api-spec 1.1 목록 봉투 예외(알림 `hasNext`, 리포트·기기 `{items}`, 자녀·동의 전체 반환) |
| 3 | C13·C14·C15 | `report-messages.md` 연동 상태, README 포트 변수 목록, compose core에 `AUTH_REAUTH_TTL` 전달 |
| 4 | D1~D14 | 설계 문서 간 불일치를 코드 기준으로 정리(#58 미구현 잔존 문장, 알림 상태·채널·재연결, SSE 연결 시간, report 저장 메서드, 재인증 흐름·표 누락 행, PIN 예시, 실제 클래스 이름). 깨진 앵커·색인 누락·낡은 보고서 서술은 보고서 55개를 10개로 통합하며 해소 |

### 1.4 API 변경

| 대상 | 변경 | 단계 |
|---|---|---|
| core `GET /children/{childId}/reports` | `status=QUEUED` → 400 `VALIDATION_FAILED`(필터 enum: RUNNING·COMPLETED·FAILED) | 2 |
| core 리포트 조회 4개 경로 | report 삭제 중 409 `DELETION_IN_PROGRESS` 신규, 근거·다운로드 503 `DATA_UNAVAILABLE` 신규(그 밖은 503 `REPORT_UNAVAILABLE` 유지) | 2 |
| core 알림 API | 400 코드 `INVALID_REQUEST`→`VALIDATION_FAILED`, 404 코드 `NOTIFICATION_NOT_FOUND`→`NOT_FOUND`(상태 동일) | 3 |
| report 내부 API OpenAPI | 422 제거, 실제 problem+json 오류 응답 선언(동작 변경 없음) | 3 |
| report-api `/health/ready` | `checks`에서 `rabbitmq` 제거 | 2 |
| core·learning 인증 필터 | `;`·퍼센트 인코딩 경로도 일반 경로와 같은 권한 판정 | 1 |

### 1.5 이슈로 넘긴 결함

상세 조사 후 바로 고치기보다 결정이 먼저 필요한 항목이다.

| # | 이유 |
|---|---|
| B3 | learning `student.deleted` 소비·완료 보고 기능 구현 |
| B4 | 상품 권한(이용권) 공급자 계약 미정 |
| B5 | report 실제 생성기·ai 서술 API(api-spec 4.2) 기능 구현 |
| B8 | 실패 이벤트를 건너뛰면 같은 리포트의 started→completed 순서 보장이 깨짐. 순서 정책 결정 필요 |
| B9 | v1 `report.failed`가 `reportId` 필수라 리포트 행 생성 전 실패를 알릴 계약이 없음. 계약 변경 또는 core 정리 작업 필요 |
| B10 | api-spec 3.11이 "신뢰 프록시 설정 전에는 X-Forwarded-For를 쓰지 않는다"로 정한 임시 결정. ALB·CloudFront 신뢰 프록시 설정과 함께 처리 |
| B11·B12 | 웹 실서버 계약(#93·#97 담당) |
| B13 | 재생성 코드 이름만 3단계에서 변경, 리포트 목록 봉투·`PATCH /children` 헤더는 웹 담당 |
| B17 | 예정 기능(#69 등)용 설정 자리와 요청별 클라이언트 생성 성능 개선 |

### 1.6 테스트 공백

#### 단위 테스트 없음

| 서비스 | 대상 | 우선순위 |
|---|---|---|
| core | `PublicAuthFilter`·`InternalAuthFilter`의 경로 정규화(`;`·`%xx`) 시나리오 | 높음(B1·B2) |
| core | 실제 `ReportEntitlementService`, `ReportScheduleService`의 자녀별 실패 격리 | 높음(B4) |
| scoring | `messaging/connection.py`(재연결), `messaging/envelope.py`, `clients/base.py`(헤더 전달), `config.py`. 현재 테스트 5건은 health·인증·오류 응답만 확인 | 중간 |
| ai | `analysis_agent/graph.py`·`nodes/{events,respond,retrieve,understand}.py`·`templates.py`·`state.py`(라우터 테스트로만 간접 확인), `judgment/prompts.py` | 중간 |
| report | `concurrency.py`, `generation/presentation.py`·`verifier.py`, `query/schemas.py`(렌더링·서술·조회 테스트로 간접 확인) | 낮음 |
| learning | `_common/messaging/EventEnvelope`·`MessagingConfig`(사용처 없음, B3 구현 시 함께), `GlobalExceptionHandler` 405·415 분기 | 낮음 |
| web | `src/data/classroom/useClassroom.ts`, `src/data/{parent,admin,studentDevice,studentLook}/queries.ts`, `src/data/queryClient.ts`, `src/data/studentLook/api.ts`, 관리자 `registerModel`·`modelAction`, `src/mocks/handlers/admin.ts` | 중간 |
| ml/m2 | `scripts/*.py` 5개 전체. pytest 의존성·CI 없음 | 낮음 |

#### 통합 테스트 없음

| 서비스 | 대상 | 우선순위 |
|---|---|---|
| core | 실제 Tomcat 경로로 학부모·학생 토큰의 관리자·역할 경로 접근 차단 | 높음(B1) |
| core↔learning·report | `student.deleted` 발행 → learning·report 완료 보고 → core 삭제 COMPLETED 전 구간 | 높음(B3) |
| core↔report | 리포트 목록 `status` 필터 전 값, report 409·503 전달 | 중간(B6·B7) |
| core | HTTP 미검증 경로: `GET /me/withdrawal/precheck`, `GET /children/{id}/deletion-impact`, `DELETE /children/{id}/link`, `POST /student-devices/pairings`, `GET`·`DELETE /student-devices…`, `PUT /children/{id}/pin`, `GET /auth/google/authorize`(서비스 수준 테스트만 있음) | 중간 |
| report | `worker.run()` 운영 조립(테스트는 `serve`만 사용), Outbox 영구 실패 시 후속 이벤트 발행 | 중간(B8) |
| scoring | RabbitMQ 연결·재연결 | 낮음 |
| web | `src/presentation` `.tsx` 34개 화면. Playwright 스크립트 11개는 수동 실행만 가능하고 `npm test`에 미포함, `e2e/`는 비어 있음 | 중간 |

### 1.7 CI 공백

- `_web.yml`이 lint·build만 실행하고 `npm test`(87건)를 실행하지 않음. `tsconfig.app.json` include가 `src`뿐이라 `tests/`는 타입 검사도 되지 않음
- 루트 계약 테스트(`scripts/tests`, 58건)는 `ci-db-schema.yml`에서 PR일 때만 실행. 경로 필터에 `contracts/openapi/**`·`backend/ai-service/app/**`·core·learning 컨트롤러가 없어 계약 변경 PR에서 미실행
- `ci-report-service.yml` 경로 필터에 `contracts/openapi/report-service.yaml` 없음
- `validate_report_contracts.py`·`validate_notification_contracts.py`는 core 테스트 산출물을 쓰는 수동 스크립트로 CI 미실행
- core·learning Testcontainers 테스트는 Docker가 없으면 건너뛰지 않고 실패. report pytest도 동일

## 2. 설계 문서 정합성 점검 (40a2501)

설계 문서를 코드와 대조해 고친 점검(PR #92). 설계 수정 내역은 커밋 이력 참고. 결정이 필요했던 항목과 선택은 아래와 같음.

점검 직후 결정이 필요했던 11건. 항목마다 문제·원인·선택지를 정리했고, 사용자가 모두 권장안을 선택해 반영했다.

| # | 문제 | 원인 | 결정 | 반영 |
|---|---|---|---|---|
| D1 계정 복구 | FN-ACC-08·10, UC-04, ERD Redis "계정 복구 확인 코드"가 남음. api-spec 5.1은 제외 | #36에서 Google 단일 로그인 확정 시 요구사항 문서 미갱신 | Google 기준 정리 | `functional-spec.md` FN-ACC-08(Google 계정 복구 위임·재로그인 안내)·FN-ACC-10(로그인 수단 변경 삭제, 재확인은 Google 재인증), `usecase.md` UC-04 "정보 수정·접근 복구 안내", `erd.md` Redis 항목 삭제 |
| D2 삭제 재확인 | state·sequence는 2단계(`REQUESTED → CONFIRMED`에 `X-Reauth-Token`), api-spec은 헤더·확인 API 없음 | 상태 설계와 API 표를 따로 작성 | 1단계 + 헤더 (연결 해제·탈퇴와 같은 방식) | api-spec 2.1, state 2.2, sequence 10.1, class 3.1(`confirmDeletion` 제거) |
| D3 PIN 잠금 필드명 | `/auth/student/profiles`는 `locked`, `/children`은 `pinLocked` | #59 목업에서 따로 정의 | `pinLocked` 통일 | api-spec 2.1, sequence 2.4. 프론트 `studentDevice.ts`의 `locked`는 #58·#59에서 변경 |
| D4 SSE 연결 시간 | `SseEmitters` 90초 고정이 범용으로 기술됨, 분석 대화는 120초(P12) | #39가 피드백 전용 값으로 구현 | 용도별 설정 명시 | architecture 1.3, class 2.1. 코드 확장은 #41 |
| D5 Problem `traceId` | core yaml 선택·nullable, learning yaml 필수. 코드는 항상 포함 | #36·#37이 각자 스키마 정의 | 필수로 통일 | core yaml `Problem.required`에 `traceId` 추가 |
| D6 내부 API OpenAPI | 구현된 learning 내부 API 8개·ai 3개가 yaml에 없음, 테스트가 learning yaml을 경로 1개로 고정 | #37이 최소 범위만 계약화, 이후 이슈는 api-spec만 갱신 | 지금 yaml 추가 | `learning-service.yaml` 9개 경로(DTO 기준 스키마), `ai-service.yaml` 신규 3개 경로(FastAPI 생성 스키마). 테스트: learning 컨트롤러·ai 라우터 경로 집합 대조, ai `heldReason` 대조. api-spec 4.1·4.2에 링크 |
| D7 이벤트 스키마 | `report.*`·`student.deleted` 스키마, asyncapi·`ci-contracts.yml` 없음 | 해당 기능 미착수 | 기능 이슈에서 선행 | #45·#42·#50 체크리스트에 이미 스키마 항목 있음. 새 정보만 코멘트: [#45](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/45#issuecomment-6459420129)(D1·D2 결정, `student.deleted` 선행), [#42](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/42#issuecomment-6459420524)·[#50](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/50#issuecomment-6459420848)(같은 스키마 중복 추가 방지, `narrativeEnabled`). #55는 #45 스키마 사용이라 생략 |
| D8 목표 구조 | stub·eks·aws·argocd·app chart·adr·환경별 yml·E2E·Redis·ShedLock·이미지 푸시가 저장소에 없음 | 최종 목표 구조로 작성 | "(예정)" 표시 | architecture 2.6·4.5·5·6장 |
| D9 core yaml 경미 | 공개 `GET /consent-documents`에 불필요한 오류 응답, `Admin`·`ModelRegistry` 태그 미선언 | 응답 블록 복사 | D5·D6과 함께 수정 | 400·401·403·409 제거(503 유지), 최상위 `tags` 추가 |
| D10 `heldReason` | ai 4종, api-spec 6종 | M1·M2 교차 확인(#69) 미구현 | 명세에 조건 표기 | api-spec 3.2. ai 추가는 #69 |
| D11 보고서 기록 | `learning-answer.md`의 판정 전 피드백 모양이 코드와 다름 | 당시 기록 | 조치 없음 | 과거 기록 유지 |

### 2.1 코드 결함 이슈 상태

| 이슈 | 내용 | 상태 |
|---|---|---|
| #93 | 웹 관리자 모델 레지스트리 요청 모양이 OpenAPI와 다름 | 미해결(1.2 B12) |
| #94 | 토큰 미기록 비용을 0으로 계산 | 해결: 입력·출력 토큰 중 하나라도 null이면 `cost_usd` null(부분 계산값은 완전한 비용과 구분되지 않아서). API 계약 변경 없음 |
| #95 | `SPEECH` 호출 종류 잔존 | 해결: 이벤트 스키마·ai·core enum·OpenAPI에서 제거(`callType=SPEECH`는 400), DB CHECK는 core V14(#99) |
| #96 | P12 "확정 전 임시값" 주석 | 해결: 서비스 공통 내부 호출 기본값 30초는 P12 목록 밖이라 값 유지, 주석만 정리 |
| #97 | 웹 `/auth/login`·`/auth/signup`·`/me/reauth {password}` 잔존 호출 | 미해결(1.2 B12) |

### #56 후속 반영 (2026-10-29)

B5의 기본 worker 미연결·표시 별명 누락은 #56에서 `CoreClient.lookup`과 `NamedGenerator`를 기본 생성 파이프라인에 연결해 수정했다. 실제 AI 서술 API(C9)는 별도 후속이며 #56 검증은 이슈가 허용한 AI 대역을 사용한다. [검증 범위와 결과](report-worker-integration.md)를 참고한다.
