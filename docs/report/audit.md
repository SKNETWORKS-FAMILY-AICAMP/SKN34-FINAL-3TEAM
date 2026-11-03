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
| B11 | 해결(#134) | 중간 | 웹 실서버 모드가 `/children` 응답의 `plan`을 읽지만 OpenAPI·코드에 없음. 저녁 질문이 항상 숨겨지고 숫자·인용 대조 검사를 건너뜀. → 이용권 계약(#129) 전까지 `plan`은 미확인으로 두고, 서술·저녁 질문은 서버 응답 유무로 표시, 서술이 있으면 항상 대조 검사. `FREE`가 명시된 경우만 화면에서 제한 | 코드 대조 | `frontend/web/src/data/classroom/apiGateway.ts:206,351,375` |
| B12 | 이슈 | 중간(미해결 #93·#97) | 웹 관리자 모델 레지스트리 요청 모양(`evalResult`, `{reason, reanalyze}`)이 OpenAPI와 다름. `/auth/login`·`/auth/signup` 호출, `/me/reauth`에 `{password}` 전송 잔존 | 코드 대조 | `src/data/admin/api.ts:64-75`, `src/data/parent/api.ts:42,49`, `src/data/apiClient.ts:113` |
| B13 | 해결(#134) | 낮음 | 웹 재생성 409 코드를 `REGENERATE_NOT_ALLOWED`로 처리, 리포트 목록을 page 봉투로 가정, `PATCH /children`에 `X-Reauth-Token` 전송·필드 필수 처리. → 409 코드는 3단계에서 변경, 리포트 목록은 `{items}`(웹·MSW), `PATCH /children`은 헤더 없이 바뀐 필드만 전송(웹·MSW 모두 선택 필드) | 코드 대조 | `apiGateway.ts:391`, `parent/api.ts:51,138` |
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
| B5 | report 실제 생성기 조립 기능 구현 (ai 서술 API `/internal/report-narratives`는 #64에서 구현) |
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

## 3. develop 종합 검증 (640e0a2)

1장 이후 PR 16개(#114·#124·#126·#127·#144·#148~#160) 병합 직후 develop `640e0a2`의 코드 통합·코드↔문서·문서 간 정합성·단위/통합 테스트 점검. 번호는 1장에 이어 결함 B18~, 코드↔문서 C16~, 문서 간 D15~.

### 3.1 실행 결과

Windows 11 로컬 실행. CI와 같은 명령, core·learning은 1장과 같이 `gradle:8.14.6-jdk21` 컨테이너(저장소 전체 마운트, Docker 소켓 연결).

| 대상 | 명령 | 결과 |
|---|---|---|
| ai-service | `uv sync --frozen` → `ruff check` → `ruff format --check` → `pytest` | 통과. 215건(177초) |
| scoring-service | 동일 | 통과. 125건(53초) |
| report-service | 동일 + `playwright install chromium` | 통과. 278건(277초), 경고 1건(`starlette.testclient`의 httpx 사용 폐기 예정) |
| core-service | `./gradlew test bootJar` | 통과. 329건(13분 57초) |
| learning-service | 동일 | 통과. 246건(8분 5초) |
| web | `npm ci` → `npm run lint` → `npm run build` → `npm test` | 통과. lint 0건, 빌드 성공(번들 611 kB, 500 kB 초과 경고), 단위 111건 |
| web 운영 산출물 | `node tests/production-mocks.mjs` | 통과. MSW·핸들러·가상 학생 fixture·개발 worker 제외 |
| 루트 계약 테스트 | report `.venv` + `jsonschema==4.26.0`, `python -O -m unittest discover -s scripts/tests` | 통과. 83건 |
| DB 마이그레이션 | 임시 `postgres:17.11-alpine`에서 `scripts/check_db_migrations.py` | 통과. core 42/390, learning 19/160, report 8/56(테이블/컬럼), 위반 입력 63건, CHECK 값 74종, 인덱스 23개, 재실행·Alembic 왕복 |
| 정책 마이그레이션 | 같은 방식으로 `scripts/check_policy_migrations.py` | 수정 전 실패(B20), 수정 후 통과(98초) |
| 계약 산출물 | core 테스트 산출물로 `validate_{report,notification,support,payment}_contracts.py` | 통과 |
| report↔learning 실제 연동 | `scripts/verify_report_learning.py` | 통과. 8건(79초) |
| report compose 통합 | `scripts/verify_report_compose.py`, `--admin-retry` | 통과. 기본 9건(294초: 유료·무료·기록 없음·삭제/없는 학생·숫자 불일치 TEMPLATE·AI 503·MinIO 실패·이벤트 스키마), `--admin-retry` 9건(122초: 새 jobId 재처리·중복 전달·현재 무료 권한·늦은 원래 결과 무시·워커 2개 Outbox 1회) |

정적 대조(스크립트로 전수 확인):

| 대상 | 결과 |
|---|---|
| core·learning 컨트롤러 경로 ↔ OpenAPI | core 127/127, learning 35/35 일치. ai·report·scoring은 기존 OpenAPI 일치 테스트가 통과 |
| api-spec 엔드포인트 표 ↔ OpenAPI | 모두 일치. 예외는 `students/me/preferences`(3.12 목업, 제안) |
| 웹 API 호출 경로 ↔ core OpenAPI | 시연 전용(`/auth/login`·`/auth/signup`·`/auth/student/demo-device`, MSW에서만)과 `students/me/preferences` 외 일치 |
| core 소비 계약 `support-learning-required.yaml` ↔ learning OpenAPI | 3개 경로·응답 코드 일치 |
| 이벤트·큐 | `definitions.json` 바인딩 ↔ 발행자·소비자 일치 |
| 환경 변수 | compose·`.env.example`·`application.yml`·Python `Settings` 일치(필수 값 누락 없음) |
| 상태 값 | state-diagram 상태 ↔ ERD CHECK 일치 |
| 문서 링크 | 상대 링크·앵커 깨짐 0건(md 43개) |

실행하지 않은 것:
- JDK 21로 JAR를 직접 띄우는 `verify_dashboard_learning.py`·`verify_feedback_learning.py`, 실행 중인 core·learning을 전제로 하는 `verify_children_records.py`·`verify_analysis_evidence.py`: 로컬에 JDK 17만 있음
- `validate_admin_operations_contracts.py`: 실제 실행에서 내보낸 응답 JSON 입력이 필요하고 테스트 산출물이 없음
- `verify_scoring_*`·`scoring_model_probe.py`: 저장소 밖 모델 archive 필요
- 웹 Playwright 스크립트(`tests/*-browser.mjs`): Node용 Playwright 미설치

### 3.2 1장 미해결 항목 재판정

| # | 현재 상태 | 근거 |
|---|---|---|
| B3 | 해결 | learning `StudentDeletedConsumer`·`StudentDeletionService`·`CoreClient` 완료 보고(#128) |
| B4 | 해결 | `ReportEntitlementService` → `ProductEntitlementService`(#48), 조회 헤더(#129) |
| B5 | 해결 | 기본 worker 파이프라인(#56), ai 서술 API(#64) |
| B8 | #131 구현 브랜치에서 보완(병합 전) | 학생별 선두·1/5/15분 재시도·격리·동일 이벤트 수동 재처리. 다른 학생의 발행과 동시 처리 순서를 검증한다. [구현·검증](issue-131-outbox-recovery.md) |
| B9 | 해결 | core 주기 점검·report 상태 복구·영구 job guard·삭제 시 미종료 작업 종료(#132) |
| B10 | 미해결(임시 결정 유지, #133) | `StudentDeviceController`가 `remoteAddr` 사용, 신뢰 프록시 설정과 함께 처리 |
| B11·B13 | 해결 | #134 |
| B12(#93·#97) | 해결 | 관리자 모델 요청이 `RegisterModelVersion`·`ActivateModelVersion`·`RollbackModelVersion`과 일치, `/auth/login`·`/auth/signup`은 MSW 시연 전용 파일에만 남음 |
| B17 | #135 구현 브랜치에서 보완(병합 전) | report 조회 HTTP·S3는 lifespan에서 재사용. 기존 사용 URL과 ai의 #68·#69 예정 설정 유지 근거를 기록했다. [#135·#139·#140](issues-135-139-140.md) |

### 3.3 발견 항목과 처리

| # | 종류 | 내용 | 처리 |
|---|---|---|---|
| B18 | 결함(중간) | core 관리자 미션 프록시가 learning 404(없는 미션 `NOT_FOUND`)를 503 `ADMIN_MISSIONS_UNAVAILABLE`로 바꿈. api-spec 2.8이 #145 이전에 정한 규칙이고 learning 보고서 10절에서 core가 고치기로 함 | 이슈 #163(api-spec 2.8 변경 동반) |
| B19 | 결함(낮음) | core 신고·정정이 learning 403(학생 범위 밖)을 503 `SUPPORT_DEPENDENCY_UNAVAILABLE`로 바꿈(api-spec 1.3·5.7 "기타 비-2xx는 503"). 신고는 막히지만 원인 구분 불가 | 이슈 #163(계약 결정 필요) |
| B20 | 스크립트 | `check_policy_migrations.py`가 #19 당시 최신 버전 수(core 7, learning 5)를 고정해 V8 이후 추가로 항상 실패 | 수정: #19 정책 버전까지만 `-target`으로 적용(`POLICY_HEAD`). 이후 버전은 `check_db_migrations.py`가 검사 |
| B21 | 스크립트 | `verify_feedback_learning.py`가 learning에 `CORE_URL`을 넘기지 않아 피드백이 결제 사용 확인에서 503(learning 보고서 10·11절) | #164 작업 브랜치에서 실제 core URL·전용 Redis·익명 볼륨까지 정리 보완. JDK 21 기존 전체 6사례와 정상/기동 실패 후 실제 자원 정리 통과. 전제·범위·한계는 [learning 보고서 15절](learning.md#15-피드백-실제-연동-검증-환경-복구-164) |
| C16 | 코드↔문서 | class-diagram 3.2가 `Conversation*`·`AiClient`·`LearningClient.evidence`·`correctJudgment`를 미구현으로 표기(#41·#46 구현) | 구현 상태와 실제 클래스 대응으로 수정 |
| C17 | 코드↔문서 | class-diagram은 "클래스명은 구현 기준"이나 3.3~3.5가 설계 이름(`ReportScheduler`·`ReportEventConsumer`·`ReportCommandWriter`·`SubscriptionService`·`BillingScheduler`·`AdminController`·`AdminJobService` 등)과 낡은 경로(`support/client/LearningClient.kt`)를 유지, "`AdminController`는 구현 완료 표시가 아님"(#47 구현) | 절마다 구현 이름 대응 추가, 낡은 문장 수정. 그림 자체는 유지 |
| C18 | 코드↔문서 | ai 분석 에이전트: class-diagram 5.2·architecture 2.6의 `service.py`·`verifier.py`·`rule_responder.py`가 실제는 `router.py` 실행·`verification.py`·`templates.py`, 노드 이름도 다름(#65·#66). architecture 2.6 ai `scoring_client.py`·`core_client.py`·`messaging/consumer.py`는 없음 | 실제 파일·노드 대응으로 수정, 없는 파일은 "(예정)" |
| C19 | 코드↔문서 | api-spec 4.5 "삭제 학생 queued job 정리·늦은 이벤트 무시는 core 미구현(B9)" | #132 구현 내용으로 수정 |
| C20 | 코드↔문서 | state-diagram 4.4 "실패 알림 재처리는 미구현" | #47 관리자 재처리(`RUNNING` 선점) 반영 |
| C21 | 코드↔문서 | report 보고서 9장 "남은 연결" 4개 중 상품 권한·표시 이름·생성기 조립·삭제 전체가 이미 연결됨 | 연결 상태로 수정, 제목 "연결 상태" |
| D15 | 문서 간 | `docs/README.md` 색인에 보고서 6개 누락(#47·#48·#119·#56·프론트 요구사항 대조·웹 통합 PR) | 추가 |
| D16 | 문서 간 | 이슈별로 덧붙인 절이 번호 체계 밖: erd `### #45`(3.1과 3.1.1 사이)·`### 이슈 #41`·`### report_job_guard`(12장 아래, report_db는 5장), architecture `### #46`·`## 이슈 #41`·`## 이슈 #132`, state-diagram 9장 아래 `### 4.1 보완` | 미수정(구조 이동, 진행 중 브랜치와 충돌 우려). 이슈 #165 |

### 3.4 API 변경

없음. 수정은 문서·수동 검증 스크립트만이다.

### 3.5 테스트 공백

| 서비스 | 대상 | 우선순위 |
|---|---|---|
| core | `InternalPaymentUsageController`(`/internal/payment-usage/reservations`·`completions`)의 STUDENT·학생 범위 검사 HTTP 테스트. 서비스(`beginFeedback`)만 확인 | 중간 |
| core | 관리자 미션 프록시의 learning 404·409·422 전달(B18 수정 시 함께) | 중간 |
| ai | `analysis_agent/templates.py`·`graph.py`·`nodes/`(라우터 테스트로만 간접 확인) | 낮음 |
| web | `src/presentation/service/*`·`support/*` 신규 화면. Playwright 스크립트는 수동 실행만 가능 | 중간 |
| 통합 | JDK 21 전제 수동 스크립트 4개(3.1 실행하지 않은 것)가 CI 밖이고 로컬 JDK에 의존 | 중간 |

1장 1.6의 core 경로 정규화(B1·B2)·`ReportScheduleService` 실패 격리는 1장 처리에서 테스트 추가됨. scoring 메시징·모델 로딩은 125건으로 확대됨.

#139·#140 구현 브랜치는 report run 조립·취소·표시/검증 직접 테스트 20개와 scoring 연결·봉투·내부 헤더·설정 테스트 19개를 추가한다. 1장의 당시 결과는 유지하고 최신 실행 수치·#131 의존 관계는 [통합 검토](issues-135-139-140.md)에 기록한다.

### 3.6 CI 공백

1장 1.7 항목이 그대로 남아 있다(#143에서 처리).
- `_web.yml`이 `npm test`(111건)를 실행하지 않음. `tsconfig.app.json` include가 `src`뿐이라 `tests/`는 타입 검사 밖
- 루트 계약 테스트(`scripts/tests`, 83건)는 `ci-db-schema.yml` 경로 필터(마이그레이션·ERD·scripts/tests 등)에 걸릴 때만 실행. `contracts/openapi/**`·컨트롤러 변경 PR에서는 미실행
- `ci-report-service.yml` 경로 필터에 `contracts/openapi/report-service.yaml` 없음(계약만 바꾼 PR에서 일치 테스트 미실행)
- `validate_*_contracts.py`는 core 테스트 산출물을 쓰는 수동 스크립트로 CI 미실행

### 3.7 아키텍처 원칙 정합성

[아키텍처](../design/architecture.md) 1.1~1.6(서비스 경계·통신·메시징)·2.1~2.4(백엔드 레이어)·3장(프론트엔드)·4장(인프라) 원칙을 HEAD 코드와 대조. core·learning은 패키지 import를 레이어(`controller`·`consumer`·`scheduler` / `service`·`facade` / `domain` / `repository`·`client`·`messaging`)로 분류해 전수 검사하고, 나머지는 클라이언트·트랜잭션·설정을 grep으로 확인.

지켜지는 원칙:

| 원칙 | 확인 결과 |
|---|---|
| 서비스 DB 직접 접근 금지(1.1) | 각 서비스 DB URL은 자기 DB만. 다른 서비스 데이터는 내부 API·이벤트로만 조회 |
| core만 공개 API·JWT 검증(1.1·2.3) | 웹 `apiClient`는 core `/api/v1`만 호출. JWT 검증은 core만, 내부 호출은 내부 토큰 + 컨텍스트 헤더 |
| 컨텍스트 전파(2.3) | ai `clients/base.py`가 받은 `X-User-*`·`X-Student-Scope`를 learning 호출에 부착. report 소비자는 `SYSTEM` + 이벤트 학생 범위 |
| 레이어 단방향·기능 간 service 경유(2.2) | core·learning에서 controller→repository 0건, 다른 기능 repository 참조 0건, Presentation의 `@Transactional` 0건. support의 learning client 재사용은 #46 결정 |
| 트랜잭션 안 외부 호출 금지(2.2) | 리포트 복구 `NOT_SUPPORTED`, 알림 Redis 발행 `AFTER_COMMIT`, learning 피드백은 `FeedbackFacade` 트랜잭션 밖 AI 호출, report Outbox는 advisory lock·짧은 트랜잭션. 예외 A1 |
| 재시도 계층(1.3) | 재시도는 ai LLM 호출(1회, 1초)과 되묻기 유출 재생성(1회)만. core·learning·report 서비스 간 호출은 재시도 없음 |
| Outbox·멱등 소비(1.6) | Outbox는 core·report만, learning은 발행 없음, ai·scoring은 best-effort 발행. core·learning 리스너는 수동 ACK·`RetryingConsumer` |
| readiness(4.4) | core·learning `readinessState,db,rabbit`, ai RabbitMQ, scoring RabbitMQ·모델, report DB. 하위 서비스 호출 없음 |
| 스케줄 중복 방지(1.5) | 정기·복구 스케줄러 4개(주간 리포트·리포트 복구·결제 갱신·결제 복구) 모두 ShedLock |
| 프론트엔드(3장) | access token 메모리 보관, 서버 상태는 TanStack Query만, 전역 상태 라이브러리 없음, `domain`이 `data`·`presentation`을 참조하지 않음 |

원칙과 다른 구현:

| # | 내용 | 원칙 | 근거 | 처리 |
|---|---|---|---|---|
| A1 | core `OutboxRelay.relay`가 `@Transactional`(미발행 행 `FOR UPDATE SKIP LOCKED`) 안에서 AMQP 발행·publisher confirm 대기. 브로커 지연 동안 DB 연결·행 잠금 보유 | 2.2 트랜잭션 안 AMQP 금지 | `core/_common/messaging/OutboxRelay.kt:21-31` | 이슈 #166 |
| A2 | 서킷 브레이커가 core→learning(`learning-json`·`learning-feedback`), learning→ai에만 있음. core→ai(분석 대화)·core→report·core→토스는 타임아웃만 | 1.3 타임아웃 + 재시도 제한 + 서킷 브레이커 | `core/conversation/client/AiClient.kt`, `core/report/client/ReportClient.kt`, `core/payment/client/TossClient.kt` | 이슈 #167에서 AI·report·토스 조회 서킷 추가. 토스 쓰기는 준비 거래 복구 정책 때문에 예외로 유지(architecture 1.3). 최종 검증은 해당 주제 보고서 참고 |
| A3 | domain 8개 파일이 `HttpStatus`(BusinessException 생성)·Jackson(`JsonNode`·`@JsonIgnore`·`@JsonInclude`) 참조 | 2.1 Domain 프레임워크 의존 금지 | core `conversation/domain/Conversations.kt`·`payment/domain/Payments.kt`, learning `answer/domain/AnswerContent.kt`·`attempt/domain/Attempt.kt`·`judgment/domain/Judgment.kt`·`judgment/domain/Support.kt`·`mission/domain/Mission.kt`·`record/domain/Period.kt` | 이슈 #168(core)·#169(learning) |
| A4 | 레이어 방향 역참조: `usage/service/LlmUsageService` → `usage.consumer.LlmUsageRecorded`, `payment/client/PremiumUsageClient` → `payment.service.PaymentTransactions.unavailable`. 수신 역할인 `notification/messaging/NotificationRedisSubscriber`가 Infrastructure 위치에서 service 호출 | 2.2 단방향 의존 | 해당 파일 import | 이슈 #168 |
| A5 | 시연 컴포넌트 `presentation/student/DemoStudentEntry.tsx`가 `apiFetch` 직접 호출·`mocks/fixtures` 참조 | 3장 컴포넌트 API 직접 호출 금지 | `frontend/web/src/presentation/student/DemoStudentEntry.tsx:2-10` | 이슈 #170 |
| A6 | ai→scoring 교차 확인 호출자 없음(ai `scoring_url` 미사용), ai `model.version.activated` 소비 없음 | 1.2·1.5 판정 흐름, 1.6 브로드캐스트 | `ai-service/app/config.py:16-17`, `versions.py` | 기존 #69·#68 |
| A7 | 저장소 인프라가 `platform-data` chart·kind뿐. 앱 Helm chart·Ingress·NetworkPolicy·HPA·KEDA·PDB·Argo CD 앱 배포, OpenTelemetry·Prometheus·Langfuse 의존성 없음 | 4.3·4.4·4.6, 1.6 Langfuse 보정 | `infrastructure/`, 각 `pyproject.toml`·`build.gradle.kts` | 이슈 #171, architecture 해당 절에 "(예정, 저장소 미구성)" 표기 |

## 4. develop 종합 검증 (2db122c)

3장 이후 PR(#161·#172~#198, 73커밋·281파일) 병합 직후 develop `2db122c`의 테스트·코드↔문서·문서 간·아키텍처 정합성 점검. 번호는 3장에 이어 결함 B22~, 코드↔문서 C22~, 문서 간 D17~, 아키텍처 A8~.

### 4.1 실행 결과

Windows 11 로컬 실행. CI와 같은 명령, core·learning은 3장과 같이 `gradle:8.14.6-jdk21` 컨테이너(저장소 마운트, Docker 소켓, `TESTCONTAINERS_HOST_OVERRIDE=host.docker.internal`).

| 대상 | 명령 | 결과 |
|---|---|---|
| ai-service | `uv sync --frozen` → `ruff check` → `ruff format --check` → `pytest` | 통과. 298건(135초) |
| scoring-service | 동일 | 통과. 144건(30초) |
| report-service | 동일 + `playwright install chromium` | 통과. 311건(137초), 경고 1건(`starlette.testclient`의 httpx 사용 폐기 예정) |
| core-service | `./gradlew test bootJar` | 404건 중 400건 통과, `SupportIntegrationTest` 4건 실패(25분). 원인은 공유 PostgreSQL 연결 고갈(B27). 같은 클래스 단독 재실행 22/22 통과, 같은 커밋 CI 통과 |
| learning-service | 동일 | 통과(8분 8초) |
| web | `npm ci` → `npm run lint` → `npm test` → `npm run build` | 통과(수정 전·후). lint 경고 1건(4.3 B23), 단위 148건, 빌드 성공(번들 673 kB, 500 kB 초과 경고) |
| web 운영 산출물 | `node tests/production-mocks.mjs` | 통과 |
| 루트 계약 테스트 | PyYAML 6.0.3·jsonschema 4.26.0, `python -O -m unittest discover -s scripts/tests` | 통과. 94건(수정 후. 지문 갱신은 4.3 C24) |
| DB 마이그레이션 | 임시 `postgres:17.11-alpine`에서 `scripts/check_db_migrations.py`·`check_policy_migrations.py` | 통과. core 44/407, learning 19/160, report 8/63(테이블/컬럼), 위반 입력 63건, CHECK 값 76종, 인덱스 25개, 재실행·Alembic 왕복(20초). 정책 마이그레이션 통과(87초) |
| 계약 산출물 | core 테스트 산출물로 `validate_{report,notification,support,payment,analysis}_contracts.py` | report·notification·payment·support 통과. `validate_analysis_contracts.py`는 실제 SSE 실행 결과 파일이 필요해 미실행 |

정적 대조:

| 대상 | 결과 |
|---|---|
| core·learning 컨트롤러 경로 ↔ OpenAPI | core 128/128(학생 로그아웃 추가), learning 35/35 일치 |
| ai·report·scoring 라우트 ↔ OpenAPI | ai 5/5, report 7/7, scoring 3/3. 스키마 차이는 ai `NarrativeMissionRef.title` 1건(C22) |
| api-spec 엔드포인트 표 ↔ OpenAPI | 149행 대조. 누락 3건(C26), 목업 `students/me/preferences`·시연 전용 경로 외 일치 |
| 웹 API 호출 ↔ core OpenAPI | 결제(#184)·관리자 재처리·학생 로그아웃·분석 일치. 도달 불가 화면의 없는 PATCH 1건(B22) |
| 이벤트·큐 | `definitions.json` exchange 3·큐 25·바인딩 12 ↔ 발행자·소비자·`QueueManagementClient` 일치. ai `model.version.activated` 봉투 ↔ 스키마 일치 |
| 환경 변수 | compose·`.env.example`·`application.yml`·Python `Settings` 일치. 예외: 관리자 큐 조회 변수 compose 누락(B24) |
| 상태 값 | state-diagram ↔ ERD CHECK 일치. 예외 D19·D20 |
| 문서 링크 | 상대 링크·앵커 229개 깨짐 0건(추적 md 전체) |
| P12 값·포트·FN/UC/NFR/P ID·오류 코드 | 문서 간 일치. 설계 문서의 상태 접두 오류 코드 90종 모두 코드에 존재 |

실행하지 않은 것: JDK 21 JAR 전제 `verify_*`·모델 archive 전제 `verify_scoring_*`·웹 Playwright 스크립트(3장과 같은 사유).

### 4.2 3장 미해결 항목 재판정

| # | 현재 상태 | 근거 |
|---|---|---|
| B8 | 해결 | #131 병합(#175). 학생별 선두 발행·1/5/15분 재시도·격리·운영 CLI(`outbox/manage.py`) |
| B10 | 미해결(#133 열림) → **#133 해결**(5장) | `StudentDeviceController`가 `remoteAddr` 사용 |
| B17 | 해결 | #135 병합(#177). ai `scoring_url`은 #69 예정 설정으로 유지 |
| B18·B19 | 해결 | #163. 관리자 미션 404 전달·지원 403 구분([#46 보고서](issue-46-support.md)) |
| A1 | 해결 | #166. `OutboxRelay.relay`는 트랜잭션 밖 발행·confirm 후 짧은 트랜잭션 기록 |
| A2 | 해결 | #167·#192. `ai-analysis`·`report-query`·`report-recovery`·`toss-lookup`·`toss-transactions` 서킷 추가, 토스 쓰기는 예외 유지 |
| A3 | 일부 해결 | #168·#169로 domain의 `HttpStatus`·Jackson 직접 import 0건. `BusinessException`(HttpStatus 필드) 간접 의존은 남음(A8) |
| A4 | 일부 해결 | `LlmUsageRecorded`→`usage/domain`, `PremiumUsageClient` 역참조 제거, Redis 구독→`notification/consumer`. `NotificationRedisPublisher`→service는 남음(A9) |
| A5 | 해결 | #170. 같은 종류 위반이던 `SupportResults.tsx`(A14)도 #255에서 해결 |
| A6 | 일부 해결 | ai `model.version.activated` 소비 #68(#194). ai→scoring 교차 확인은 #69 예정 |
| A7 | 유지 → **#204(#171) 병합으로 local 앱 chart·Ingress·NetworkPolicy·HPA·KEDA·PDB·관측 구성**(5장) | #171은 "EKS 사용 확정"으로 종료됐으나 앱 chart·Ingress·NetworkPolicy·HPA·KEDA는 저장소에 없음. architecture "(예정)" 표기 유지 |
| D16 | 미해결(#165 열림) → **#165 일부 해결**(#229, 4.6) | 번호 체계 밖 절이 #47·#48 절 추가로 늘어남(4.5) |

### 4.3 발견 항목과 처리

| # | 종류 | 내용 | 처리 |
|---|---|---|---|
| B22 | 결함(낮음) | 웹 `data/serviceApi.ts` `answerInquiry`가 core에 없는 `PATCH /admin/inquiries/{id}` 호출. 사용처 `ServiceCenter.tsx` `AdminHelpdesk`는 ADMIN에 `support` 경로가 없어 도달 불가, MSW만 지원. 실제 관리자 답변은 `data/admin/serviceApi.ts`의 `POST …/answer` | 도달 불가 `AdminHelpdesk`와 전용 API 3개(`adminInquiries`·`answerInquiry`·`publishNotice`)·MSW PATCH 핸들러 제거, `tests/serviceCompletion.test.ts`를 MSW `POST …/answer`로 전환, api-spec 3.13 PATCH 문장을 2.8 `POST …/answer`로 교체 |
| B23 | lint(낮음) | `AdminOperations.tsx:204` `key.current = null`에 oxlint `react(immutability)` 경고. `useRef` 값을 이벤트 처리기에서 바꾸는 정상 코드로 판단 | 미수정(동작 문제 없음) |
| B24 | 설정(낮음) | core가 읽는 `ADMIN_RABBIT_MANAGEMENT_URL`·`_USERNAME`·`_PASSWORD`가 compose에 없어 로컬 `GET /admin/queues`가 항상 503 `QUEUE_MANAGEMENT_NOT_CONFIGURED` | compose core 환경에 `http://rabbitmq:15672`와 기존 `RABBITMQ_USER`·`RABBITMQ_PASSWORD` 연결 |
| B25 | 확인(결함 아님) | `ConversationRetryWorker.poll`은 stale 종료 예외 시 그 회차 pending 처리를 건너뜀. `failGeneration`은 DB 예외만 던지고 메시지 삭제 시 요청 행도 CASCADE 삭제되므로 영구 정지 경로 없음 | 조치 없음 |
| B26 | 확인(낮음) | ai `messaging/consumer.py` `receive`가 `ValueError`·`TypeError` 외 예외에서 ACK하지 않음. 현재 `ActiveVersions.apply`·pydantic 검증 경로에서 다른 예외는 발생하지 않음 | 조치 없음(처리 로직 변경 시 재확인) |
| B27 | 테스트 환경(중간) | core 전체 테스트 중 `SupportIntegrationTest` 4건이 `FATAL: sorry, too many clients already`로 30초 연결 대기 후 500. 테스트별 설정이 다른 Spring 컨텍스트가 캐시에 누적(HikariPool-28)되어 JVM당 1개인 PostgreSQL 컨테이너의 연결 한도(기본 100)를 소진. 실행 순서·속도에 따라 재현(같은 커밋 CI는 통과) | 미수정. 컨텍스트 캐시 상한·테스트 풀 크기·컨테이너 `max_connections` 중 선택 필요(이슈 후보) |
| C22 | 코드↔문서 | `ai-service.yaml` `NarrativeMissionRef`가 `title`을 required에만 두고 properties에 없음(코드 `report_narrative/models.py`는 `title: str`) | properties에 `title` 추가 |
| C23 | 코드↔문서 | `POST /admin/jobs/{jobId}/retry` OpenAPI에 실제 404·409·422·503 응답 미선언, 재처리 오류 코드 7종이 api-spec 1.3 표에 없음 | OpenAPI 응답 선언, api-spec 1.3에 `JOB_*`·`REPORT_ALREADY_RETRIED`·`REPORT_RETRY_STUDENT_UNAVAILABLE` 추가 |
| C24 | 코드↔문서 | api-spec 1.3·core OpenAPI 리포트 5개 경로의 `REPORT_ENTITLEMENT_UNAVAILABLE`은 테스트 대역에서만 사용. 실제 `ProductEntitlementService`는 503 `PAYMENT_ENTITLEMENT_CONFIRMING`·`PAYMENT_PRODUCT_UNAVAILABLE`·`PAYMENT_FREE_PRODUCT_UNAVAILABLE` | 문서·OpenAPI 설명을 실제 코드로 정정. `test_admin_operations_contract`의 검토 지문 5개 경로 갱신(설명 문자열 변경만) |
| C25 | 코드↔문서 | api-spec 1.3 `AI_UNAVAILABLE` 503. core 분석 대화 `AiClient`는 502 | 503/502 구분 기재 |
| C26 | 코드↔문서 | api-spec 표에 `GET /subscriptions/{id}/billing-key`, `POST /internal/payment-usage/reservations`·`completions` 행 없음 | 2.6·4.5 표에 추가 |
| C27 | 코드↔문서 | CONVERSATION·REPORT 관리자 재처리가 구현됐는데 "JOB_RETRY_UNAVAILABLE 차단·#47 후속"으로 남음: api-spec 2.8·5.5.1, architecture 1.6, sequence 6.1, `report-admin-retry/README.md`, `report-messages.md`, `issue-152-report-admin-retry.md` | 구현 상태로 정정(보고서는 "검증 당시" 표기로 보존) |
| C28 | 코드↔문서 | 분석 대화 SSE 수명 "120초 + 여유(#41 미구현)": architecture 1.3, class-diagram 2.1. 코드는 125초 `open`·120초 취소 | 정정 |
| C29 | 코드↔문서 | `OutboxRelay`를 `FOR UPDATE SKIP LOCKED`·`@Transactional` 안 발행으로 기술: class-diagram 2.1, report 보고서 1장(#166 이후 코드와 다름) | 정정 |
| C30 | 코드↔문서 | 분석 대화 단절 실패 코드 `CLIENT_DISCONNECTED`(state 4.3·sequence 5장·class 3.2). 코드는 `STREAM_INTERRUPTED` | 정정 |
| C31 | 코드↔문서 | ERD 8장 버전·수치가 V16·69/613. 실제 V19·71/630(core 44/407) | 갱신 |
| C32 | 코드↔문서 | user-flow 7장 "학부모 구독 결제·관리 화면 없음". #184로 `/parent/billing`·`/payment/*` 구현 | 구현 흐름으로 정정 |
| C33 | 코드↔문서 | architecture 2.6 트리 누락: core `_common/persistence`·`_common/web/repository`·`account/client`·`account/config`·`admin/client`·`admin/consumer`·`conversation/scheduler`·`usage/domain`·`payment/client/PremiumUsageClient.kt`, learning `_common/persistence`·`record/{client,consumer,domain}`, learning `deletion/`은 빈 폴더(실제 소비는 `record/`), scoring·report 실제 파일 다수 | 실제 구조로 트리 갱신 |
| C34 | 코드↔문서 | 상태 서술 잔존: ai 보고서 3장·5장 "#68 후속"(7장에서 구현), learning 보고서 미션 감사 "#47 후속"(`MissionAuditService` 구현), report 보고서 닉네임 "미연결"(#56 연결), api-spec 프롬프트 예시 `judge@4`·`report@2`(실제 `judge@2`·`report@1`), class-diagram 2.2 소비자 "report 구현됨"(ai·scoring 포함), ai `connection.py` "서비스 코드에서 큐 선언 안 함" 주석 | 정정 |
| D17 | 문서 간 | `docs/README.md` 색인 누락 5개(#184·#195·#196·관리자 화면 PR·learning 프론트 정렬), #41·#131 항목이 브랜치 규칙 아래에 위치 | 색인에 추가·이동 |
| D18 | 문서 간 | `docs/README.md` "core 임시 통합 경로" 규칙의 `feature/core-integration` 브랜치가 원격에 없음 | 종료된 임시 예외로 절 삭제 |
| D19 | 문서 간 | state 4.4 Mermaid에 `notification.status` `RUNNING` 없음(본문·ERD CHECK에는 있음) | 관리자 재처리 전이 추가 |
| D20 | 문서 간 | `conversation_job_retry.status`(V19) 상태 표 없음, state 4.3이 관리자 재처리를 사용자 재시도와 같은 `retry()`로 기술 | 4.3에 관리자 세대 선점 행과 요청 상태 표 추가 |
| D21 | 문서 간 | 루트 `MERGE_RESOLUTION_20261029.md`가 다른 PC 절대경로·"커밋 전" 상태의 인수인계 파일. 내용은 [웹 통합 PR](pr-web-develop-integration.md)에 있음 | 삭제 |

### 4.4 API 변경

없음. 코드 동작 변경은 웹 도달 불가 화면 제거와 compose 환경 변수뿐이다. OpenAPI는 실제 응답 선언·설명 정정만이다.

### 4.5 아키텍처 원칙 정합성

core·learning은 import를 레이어로 분류해 전수 검사, Python·웹은 grep으로 확인.

지켜지는 원칙: 3장 3.7 표의 항목 유지. 추가 확인:
- domain 파일의 Spring·Jackson·MyBatis 직접 import 0건, Presentation→Infrastructure 직접 import 0건(`_common/messaging` ACK 제외), `@Transactional`은 service·facade·`OutboxWriter(MANDATORY)`만
- 트랜잭션 안 외부 호출 없음(1단계 호출까지): Google·토스·learning·ai·report HTTP, Redis 페어링·분석 사용량. `PremiumUsageClient`·`PaymentUsageClient`·learning `CoreClient`는 트랜잭션 비활성을 단언
- 재시도: ai LLM 1회(1초)·되묻기 유출 재생성 1회만. provider SDK `max_retries=0`, report boto3 `total_max_attempts=1`
- Outbox는 core·report만, `@RabbitListener` 3개 모두 `RetryingConsumer`, 수동 ACK·`missing-queues-fatal: false`
- `ConversationRetryWorker`(#47)는 ShedLock 대신 메시지 행 잠금·조건부 UPDATE로 레플리카 간 1회 선점
- 웹: 전역 상태 라이브러리 없음, access token 메모리 보관, `domain`이 `data`·`presentation`을 참조하지 않음, presentation의 `mocks`·raw `fetch` 참조 없음

원칙과 다른 구현(이번에 수정하지 않음, 리팩터 범위 결정 필요):

| # | 내용 | 원칙 | 근거 |
|---|---|---|---|
| A8 | domain이 `BusinessException(ErrorKind…)`을 던지고 `BusinessException`이 `HttpStatus` 필드를 가짐(간접 프레임워크 의존) — #249 해결(HTTP 상태 없는 `DomainException`, [#249 절](issue-168-core-layer-deps.md#249-domain-예외-분리-corelearning-1102)) | 2.1 Domain 프레임워크 의존 금지 | core `conversation/domain/Conversations.kt`, learning `answer/domain/AnswerContent.kt`·`attempt/domain/Attempt.kt`·`judgment/domain/Judgment.kt`·`mission/domain/Mission.kt`·`record/domain/Period.kt`, 양쪽 `_common/exception/BusinessException.kt` |
| A9 | Infrastructure→Application 역참조 — #250 해결([#250 절](issue-168-core-layer-deps.md#250-알림-발행결과-기록-분리-core-1103)) | 2.2 단방향 | core `notification/messaging/NotificationRedisPublisher.kt`가 `NotificationDeliveryService.record` 호출 |
| A10 | 기능 간 controller·config 참조 — #251 해결([#251 절](issue-168-core-layer-deps.md#251-기능-간-controllerconfig-직접-참조-제거-corelearning-1103)) | 2.2 기능 간은 service로만 | core 9개 컨트롤러가 `account.controller.AuthController.IDENTITY` 참조, `guardianship/service/StudentPinService`→`account.config.StudentDeviceProperties`, `_common/security/PublicAuthFilter`→account 기능, learning `attempt/controller/AttemptResponses.kt`·`record/controller/RecordResponses.kt`가 다른 기능 controller DTO 참조 |
| A11 | report 기능 간 DB 직접 접근 — #252 로컬 해결·미병합 → **#258 병합** | 2.1·2.2 | query는 generation service, 생성·조회·복구·worker는 deletion service 경유. 삭제 DB 작업은 deletion.repository, 리포트·Outbox 삭제는 각 소유 service/repository로 분리. 기존 테이블 import 호환만 state의 지연 재노출로 유지. 검증 근거: [report #252 기록](report.md#252-report-기능-간-db-직접-접근-제거) |
| A12 | ai 분석 에이전트 Application 계층 부재 — #253 해결(`AnalysisService`가 learning 연결 생성·그래프 실행·이벤트 변환, `AgentContext`는 `context.py`로 이동) | 2.2 계층 건너뛰기 금지 | `analysis_agent/router.py`가 `LearningClient` 생성·그래프 실행, `state.py`가 `tools`·`llm`·`versions` 참조 |
| A13 | ai·scoring 소비자에 revision 조정 업무 로직, ai `versions.py`에 router·모델·상태 저장 혼재 | 2.1 Presentation 업무 로직 금지 | `ai-service/app/messaging/consumer.py`, `scoring-service/app/messaging/consumer.py`, `ai-service/app/versions.py`. ai는 #254에서 `prompt_versions/`(models·registry·service·router)로 분리하고 `versions.py` 제거, 소비자는 검증·ACK·`PromptSync.offer`만. scoring 소비자의 `ModelStartup` 생성·조정은 남음 |
| A14 | 웹 컴포넌트 API 직접 호출·서버 상태 직접 보관 | 3장 | `presentation/support/SupportResults.tsx`의 `apiFetch`, `parent/ParentPayments.tsx`(`PaymentResult`)·`BillingResult.tsx`의 `useState`·폴링, `domain/payment.ts`의 `sessionStorage` 접근. **#255 해결**: `data/support/{api,queries}.ts`, `data/payment/{queries,checkoutStorage}.ts`로 이동 |
| A15 | 설계 문서상 위치와 다른 구현 | 2.6 | learning `student.deleted` 소비가 `deletion/`이 아닌 `record/consumer`·`record/service`(빈 `deletion/` 폴더 잔존). 트리에 실제 위치 표기 |

- A15 처리: #256에서 빈 `deletion/` 폴더를 지우고 architecture 2.6·class-diagram 4.3을 `record/` 기준으로 정리했다(코드 변경 없음, [learning 보고서](learning.md) 9절).

### 4.6 남은 공백

| 대상 | 내용 |
|---|---|
| 오류 코드 문서 | 결제(약 30종: `PAYMENT_PG_UNAVAILABLE`·`PAYMENT_NOT_FOUND`·`SUBSCRIPTION_NOT_ACTIVE`·`REFUND_STATE_CHANGED`·`BILLING_KEY_REQUIRED` 등)·`QUEUE_MANAGEMENT_*`·`EVIDENCE_UNAVAILABLE`(410)·`SUPPORT_STATE_CONFLICT`·`LEARNING_STATS_UNAVAILABLE`·`ANALYSIS_USAGE_UNAVAILABLE`이 api-spec 1.3에 없음 → **5장 C35 반영**(`ANALYSIS_USAGE_UNAVAILABLE`은 #225로 미사용). #245 재대조(예외 생성 코드 122종 + core SSE 오류 이벤트): 분석 대화 SSE `error` 전용 `ANALYSIS_FIRST_RESPONSE_TIMEOUT`·`ANALYSIS_TIMEOUT`(504)·`ANALYSIS_FAILED`(502) 3종을 1.3에 추가, 그 외 공개 응답 누락 0. `AI_BAD_RESPONSE`·`AI_CIRCUIT_OPEN`은 learning 판정 실패 기록 코드, `FINAL_RESPONSE_VERIFICATION_FAILED`는 ai→core 스트림 내부 코드로 공개 응답은 `AI_UNAVAILABLE` |
| 목업 계약 | `GET/PUT /students/me/preferences`(api-spec 3.12)는 백엔드 미구현 → **#234 해결**(core V23·OpenAPI `StudentLook`) |
| 종료 이슈 문구 | #171 종료 후 architecture "(예정, #171)", #184 종료 후 `tosspayments-checkout.md` "자동 종료하지 않음" 문구(과거 기록) → **#245 정리**(architecture 문구는 이미 제거됨, tosspayments는 당시 결정임을 표기) |
| 번호 체계 밖 절(#165) | erd·architecture·state-diagram은 #165에서 번호 절로 이동 완료. api-spec·sequence·class·ai 보고서의 이슈별 절은 남음 → **#245 정리**: api-spec 2.8.1·4.3.1~4.3.3·5.7.1~5.7.3·5.10~5.16(첫 절 #206·#207은 5.15), sequence 6.1.1·6.4, class 3.3.1, ai 2장 하위·8장, functional-spec 2.6.1. 본문 변경 없음(제목·위치만) |
| 보고서 정리 | `learning-frontend-alignment.md`의 다른 PC 절대경로, `pr-admin-screen-completion.md` 제목(H1) 없음, `issue-47-admin-operations.md`·`issue-46-support.md`의 #163 절 중복 → **#245 정리**(절대경로 → 당시 검증 PC의 로컬 산출물 폴더, H1 추가, #163 절은 #46 보고서에 두고 #47 보고서는 링크) |
| 인프라·설계 차이 | 멘토링 결정(#211 Karpenter·#212 S3 Gateway, 열림)과 architecture의 Cluster Autoscaler·NAT 단독 기술 |
| 테스트 공백 | ai `analysis_agent` 노드는 #138로 보강. 웹 `presentation` 화면·Playwright 스크립트는 여전히 수동 실행만 가능 → **`_web.yml` `test:browser`(tests/browser)로 CI 실행**, `tests/*-browser.mjs`는 수동 |

## 5. develop 종합 검증 (92d522b)

4장 이후 PR 28개(#203~#271, 133커밋·414파일) 병합 직후 develop `92d522b`의 테스트·코드↔코드·코드↔문서·문서 간·아키텍처 정합성 점검. 번호는 4장에 이어 결함 B28~, 코드↔문서 C35~, 문서 간 D22~, 아키텍처 A16~.

### 5.1 실행 결과

Windows 11 로컬 실행. CI와 같은 명령, core·learning은 4장과 같이 `gradle:8.14.6-jdk21` 컨테이너(저장소 마운트, Docker 소켓, `TESTCONTAINERS_HOST_OVERRIDE=host.docker.internal`), helm은 `alpine/helm:4.3.1` 컨테이너.

| 대상 | 명령 | 결과 |
|---|---|---|
| ai-service | `uv sync --frozen` → `ruff check` → `ruff format --check` → `pytest` | 통과. 307건(130초) |
| scoring-service | 동일 | 통과. 144건(24초) |
| report-service | 동일 + `playwright install chromium` | 통과. 337건(202초), 경고 1건(`starlette.testclient`의 httpx 사용 폐기 예정) |
| core-service | `./gradlew test bootJar` | 449건 중 448건 통과(38분). 실패 1건은 B31 회귀 테스트가 수정 전 본 코드로 컴파일된 실행에서 `TEMPLATE_PROPOSAL_EXPIRED`를 받은 것(수정 전 실패 확인). 수정 후 `ReportTemplate*`·`ReportRepositoryTest` 4개 클래스 14건 재실행 통과 |
| learning-service | 동일 | 통과. 279건(12분) |
| web | `npm ci` → `npm run lint` → `npm test` → `npm run build` → `npm run test:browser` | 통과(수정 전·후). lint 경고 1건(4장 B23), 단위 199건, `test:types` 통과, 빌드 성공(최대 청크 280 kB, #247 이후 500 kB 경고 없음), 브라우저 21건(B28 신규 1건 포함) |
| web 운영 산출물 | `node tests/production-mocks.mjs` | 통과 |
| 루트 계약 테스트 | PyYAML 6.0.3·jsonschema 4.26.0, `python -O -m unittest discover -s scripts/tests` | 통과. 99건(수정 후, GitOps revision 검사 1건 추가) |
| DB 마이그레이션 | 임시 `postgres:17.11-alpine`에서 `check_db_migrations.py`·`check_policy_migrations.py` | 통과. core 46/425, learning 19/160, report 8/63(테이블/컬럼), 위반 입력 63건, CHECK 값 78종, 인덱스 32개, 재실행·Alembic 왕복(26초). 정책 마이그레이션 통과(115초) |
| GitOps | `ci-gitops.yml`과 같은 local 환경별 `helm lint --strict`·`helm template`(Kubernetes 1.35.8) | 통과(8개 release). kubeconform은 원격 스키마 카탈로그가 필요해 미실행(develop CI 통과) |
| ml | `ci-ml-m1.yml`·`ci-ml-m2.yml`과 같은 `ruff check`·`ruff format --check`·`pytest` | 통과. m1 3건(1건 건너뜀), m2 9건(3건 건너뜀) |

정적 대조:

| 대상 | 결과 |
|---|---|
| core·learning 컨트롤러 경로 ↔ OpenAPI | core 139/139, learning 36/36 일치 |
| ai·report·scoring 라우트 ↔ OpenAPI | ai 6/6, report 7/7, scoring 3/3. #209·#254 스키마(`TemplateSettings`·`TemplateProposal`·`NarrativeRequest.tone`·`/versions`) 일치. 4장 C22(`NarrativeMissionRef.title`) 반영 확인 |
| api-spec 엔드포인트 표 ↔ OpenAPI | 본문 서술에만 있고 표에 없는 경로 다수(C37) |
| 웹 API 호출 ↔ core OpenAPI | 경로는 시연 전용(`/auth/login`·`/auth/signup`·`/auth/student/demo-device`·`/__payment-test`) 외 일치. 지원 화면 요청·응답 모양 불일치(B28) |
| 서비스 간 HTTP 클라이언트 ↔ 호출 대상 | core→learning·ai·report, learning→ai·core, ai→learning, report→core·learning·ai 경로·DTO 일치. 상태 코드 변환 1건(B34) |
| 이벤트·큐 | `definitions.json` exchange 3·큐 30·바인딩 20 ↔ 발행자·소비자·`QueueManagementClient` 일치. 4장 이후 이벤트 스키마 변경 없음, #208 감사 큐는 봉투 메타데이터만 저장 |
| 공유 상수 | 내부 헤더(`X-Internal-Token`·`X-User-*`·`X-Student-Scope`·`X-Report-Narrative-Enabled`)·큐 이름·P12 시간 제한(learning→ai 35초, ai 서술 28초 < report 30초, core→ai 설정 제안 25초 > ai 20초) 일치 |
| 환경 변수 | compose·`.env.example`·`compose.e2e.yaml`·`application.yml`·Python `Settings` 일치. GitOps local 누락 1건(B30), 미사용 `SCORING_URL`(#69 예정), `LANGFUSE_*`는 기본 비활성 |
| 상태 값 | state-diagram ↔ ERD CHECK·enum 일치(#241 `LEASE_EXPIRED`는 CHECK 없는 `failure_code`) |
| FN/NFR/UC ID | 참조 ID 모두 정의됨(FN 120·NFR 39·UC 28). FN-AGT-12 구현 차이 1건(5.6) |
| 문서 링크 | 상대 링크·앵커 305개 중 깨짐 1건(D23) |

실행하지 않은 것: JDK 21 JAR 전제 `verify_*`·모델 archive 전제 `verify_scoring_*`·`tests/*-browser.mjs`(수정한 `requirements-browser.mjs`만 실행, 5.6), compose 전체 스택 E2E(`e2e.yml`, develop 실행 이력 없음 C43).

### 5.2 4장 미해결 항목 재판정

| # | 현재 상태 | 근거 |
|---|---|---|
| B10 | 해결 | #133(#232). `forward-headers-strategy: native`와 신뢰 프록시 대역 판정(api-spec 3.11) |
| B23 | 유지 | `AdminOperations.tsx:204` oxlint 경고 1건(동작 문제 없음) |
| B27 | 재현 안 됨 | #218(core 통합 테스트 연결 풀) 이후 core 전체 449건 실행에서 연결 고갈 실패 없음 |
| A7 | 해결(local) | #204(#171) app-service chart·NetworkPolicy·HPA·KEDA·PDB·Argo CD local·관측 chart. 운영(EKS·prod) 구성은 "(예정)" |
| A8 | 해결 | #272(#249). domain은 HTTP 상태 없는 `DomainException` 사용(`ReportTemplate.kt` 포함), [#249 절](issue-168-core-layer-deps.md#249-domain-예외-분리-corelearning-1102) |
| A9 | 해결 | #250. 커밋 후 발행·결과 기록은 `NotificationDispatchService`(service), `NotificationRedisPublisher`는 Redis 발행만, [#250 절](issue-168-core-layer-deps.md#250-알림-발행결과-기록-분리-core-1103) |
| A10 | 해결 | #251. 요청 속성 상수는 `_common/security/RequestAttributes`, PIN 한도는 guardianship `PinRules`, learning 공유 응답 DTO는 `_common/web`, [#251 절](issue-168-core-layer-deps.md#251-기능-간-controllerconfig-직접-참조-제거-corelearning-1103) |
| A11 | 해결 | #258(#252) 병합 |
| A12 | 해결 | #253. `analysis_agent/service.py`(`AnalysisService`), router는 의존성·SSE 형식만, `state.py`는 models·calculators만 참조 |
| A13 | 일부 해결 | ai는 #254(`prompt_versions/`). scoring 소비자의 `ModelStartup` 생성·revision 조정은 남음 |
| A15 | 해결 | #256 |
| D16 | 해결 | #165(#229)로 erd·architecture·state-diagram, #245로 api-spec·sequence·class·ai·functional-spec #209 정리. functional-spec 맨 위 "추가 확정"(#206·#207·#213)은 해당 FN 항목에 반영된 변경 요약으로 유지 |
| 4.6 오류 코드 | 해결 | 5.3 C35 |
| 4.6 테스트 공백 | 일부 해결 | 웹 `tests/browser`(Playwright)가 `_web.yml`에서 실행. `tests/*-browser.mjs`는 수동 |
| 4.6 보고서 정리 | 해결 | #245 |
| 4.6 인프라·설계 차이 | 유지 | #211(Karpenter)·#212(S3 Gateway) 열림, architecture 4.2~4.4는 Cluster Autoscaler·NAT 기술 |

### 5.3 발견 항목과 처리

| # | 종류 | 내용 | 처리 |
|---|---|---|---|
| B28 | 결함(중간) | 웹 `/{student,parent}/support`(`SupportEntry`→`ServiceCenter`)·`/help`·`/notices`가 #46 이전 목업 계약 사용. 실서버에서 문의 `{category:OTHER,comment}`는 400(core는 `ACCOUNT\|USAGE\|PAYMENT`·`title`·`body`), 오류 신고는 `Idempotency-Key` 미전송으로 400, 목록 `id`·`answer`, 공지 `id`·`content`·`startsAt`, 도움말 `id`·`content`를 읽어 본문 미표시. MSW `/notices`가 옛·새 필드를 함께 돌려 가려짐, `handlers/service.ts`의 `/notices`·`/admin/inquiries`·`POST /admin/notices`는 `adminService.ts`에 가려져 실행되지 않음 | `data/support/api.ts`에 `submitReport`(같은 내용 재전송 시 같은 키)·`submitInquiry` 추가, `ServiceCenter`가 `SupportReport`·`SupportInquiry`·공지·도움말 실제 필드 사용(문의 제목 입력 추가, 문의 유형에서 `OTHER` 제거). `serviceApi.cases`·`createCase`·`SupportCase` 제거. MSW를 core 모양으로 맞추고 가려진 핸들러 제거, 본인 신고·문의 상세 핸들러 추가. 테스트: `serviceCompletion`(옛 문의 400·키 없는 신고 400), `support`, 브라우저 `학부모 도움말·공지·문의 접수는 core 계약 모양을 쓴다` |
| B29 | 설정(중간) | GitOps local `migration.revision`이 core `v19`·learning `v7`·report `20261030-04`. 이름이 revision으로 고정된 PreSync Job이 성공 후 남아 core V20~V23·learning V8·report `20261102_05`가 일반 sync에서 적용되지 않음(#171 검증 기록의 v19·v7·`20261030_04` 그대로) | `v23`·`v8`·`20261102-05`로 갱신. `scripts/tests/test_core_migration_versions.py`에 최신 마이그레이션 ↔ revision 검사 추가(수정 전 실패 확인) |
| B30 | 설정(낮음) | GitOps local core에 `ADMIN_RABBIT_MANAGEMENT_URL`·`_USERNAME`·`_PASSWORD` 없음 → kind `/admin/queues` 503(4장 B24의 GitOps판, 15672 egress는 이미 허용) | local core env에 RabbitMQ 관리 API URL과 기존 secret 키 연결. helm template 렌더 확인 |
| B31 | 결함(낮음) | `ReportTemplateService.forStudent`가 학생 삭제 요청·비활성 시 409 `TEMPLATE_PROPOSAL_EXPIRED`(제안 만료 코드) | 409 `STUDENT_UNAVAILABLE`(기존 꾸미기·공개 설정과 같은 코드), OpenAPI 409 선언. 테스트: `ReportTemplateHttpIntegrationTest`(삭제 요청 접수 직후 내부 조회) |
| B32 | 잠재 결함(낮음) | `forStudent`가 `activeParents().singleOrNull()`로 학부모 2명 이상 연결 시 404 → report 주간 생성 실패. 현재 연결은 `REGISTER` 경로뿐이라 발생하지 않음 | 미수정(다중 보호자 정책 결정 필요). 이슈 #275 |
| B33 | 확인(결함 아님) | 리포트 설정 제안이 AI 호출 전 분석 사용량 차감, AI 실패 시 환원 없음 | api-spec #209 절 "AI 실패·확인 질문도 접수된 시도로 취급" 결정과 일치. 조치 없음 |
| B34 | 결함(낮음) | learning `PaymentUsageClient:30`이 core 409 전부를 `REFUND_IN_PROGRESS`로 변환. `PAYMENT_USAGE_RETRY_REQUIRES_NEW_SOURCE`·`PAYMENT_USAGE_STATE_CHANGED`도 "환불 처리 중" 안내 | #276 해결: `PaymentUsageClient`가 core Problem Details `code`를 읽어 세 코드만 같은 코드 409와 코드별 안내로 전달, 목록 밖·형식 오류 409는 `PAYMENT_USAGE_UNAVAILABLE` 503(환불 안내 안 함). 웹은 core SSE `error`의 `title`을 그대로 표시해 변경 없음. api-spec 1.3·4.5, learning OpenAPI 갱신. 테스트: `PaymentUsageClientTest`(코드별 변환, 목록 밖 코드·본문 없음·JSON 아님·문자열 아닌 code → 503) |
| B35 | 결함(낮음) | `SupportService.adminNotices`가 입력 검사(400)를 권한 검사(403)보다 먼저 수행. 비관리자의 잘못된 `status`에 400(OpenAPI는 403) | #277 해결: core·MSW 모두 `access.admin`(MSW `admin()`)을 page/size·status·role 검사보다 먼저 수행. 테스트: `SupportIntegrationTest`(학부모·학생·CONTENT 관리자 + 잘못된 status·role·size → 403, 관리자 + 잘못된 값 → 400), `adminScreenCompletion`(결제 관리자·학부모 + 잘못된 status·role → 403) |
| A16 | 아키텍처(낮음) | core `report/domain/ReportTemplate.kt`가 `org.springframework.http.HttpStatus` 직접 import(#168 이후 회귀) | `ErrorKind.INVALID`(같은 400). #272(#249)에서 `DomainException(ErrorKind.INVALID)`로 정리 |
| C35 | 코드↔문서 | api-spec 1.3 누락 오류 코드: 신규 `STUDENT_RECORDS_PRIVATE`·`STUDENT_UNAVAILABLE`·`INVALID_TEMPLATE_SETTINGS`·`TEMPLATE_PROPOSAL_EXPIRED`, 4장 4.6의 결제 약 32종·`QUEUE_MANAGEMENT_*` 5종·`EVIDENCE_UNAVAILABLE` 등, 본문에만 있던 관리자 미션·프롬프트·scoring 코드 | 1.3 표에 실제 상태·조건으로 추가 |
| C36 | 코드↔문서 | api-spec 1.3 `VALIDATION_FAILED`는 400만 기재. PIN 규칙·꾸미기 선택값은 422 | 400 / 422 구분 기재. MSW 꾸미기 주석의 "목업 계약" 정정 |
| C37 | 코드↔문서 | api-spec 표에 없는 경로: `/attempts/{id}/comparison`, `/conversations/{id}/report-template`·`/proposals`·`/confirm`, `/admin/inquiries/{id}`, 내부 `/internal/analysis/report-template`·`/internal/students/{id}/profile`·`/report-template`·`/internal/report-jobs/{id}/reconcile`·learning `/internal/payment-usage/students/{id}`, 서술 요청 `tone` | 2.2·2.4·2.8·4.1·4.2·4.4·4.5 표에 추가. sharing-preferences 3개는 문서 첫 절(#206) 서술 유지 |
| C38 | 코드↔문서 | api-spec 3.13이 `/help`·`/notices`·신고·문의·`POST /admin/notices`를 옛 목업 DTO로 기술, "#206 develop 미병합", 탈퇴 사전 확인 응답에 `pendingPayments` 누락(#136 보고서 지적) | 3.13을 core 계약으로 교체, #206 병합 표기, `pendingPayments` 추가 |
| C39 | 코드↔문서 | ERD 8장 V19·71/630, 14장 "(로컬 구현 후보)", Redis 값 목록의 "요금제 사용 한도 일 단위 카운터"(미구현, #225로 분석 사용량은 PostgreSQL) | V23·learning V8·report `_05`·73/648, 제목 정정, Redis 값은 SSE 중계만·미션 한도 미정(#210) |
| C40 | 코드↔문서 | architecture 2.6 트리에 #209 `template_settings.py`(ai·report)·#208 감사/보존 정리 없음. 5장에 없는 `externalsecret.yaml`·`<target>-stub.yaml`·`argocd/apps`·`argocd/prod`·`addons/`, 실제 `migration-networkpolicy`·`namespace-default-deny`·`values.schema.json`·`gitops/migrations/`·`policies/local/` 누락, 워크플로 목록에 `ci-gitops`·`ci-ml-*` 없음, `ci-<service>`가 모두 `contracts/**`를 본다는 서술(learning·web은 아님), "#171 브랜치에…" 문구 | 트리·워크플로를 실제 구조로, 없는 것은 "(예정)", #171은 PR #204 병합 표기 |
| C41 | 코드↔문서 | class-diagram `ActiveVersions`→`versions.py`(#254 이후 `prompt_versions/registry.py`), report `DeletionRepository`→`deletion/state.py`(#252 이후 `repository.py`), #206·#208·#209·#234 클래스 대응 없음 | 파일 위치 정정, 3.1·3.3 구현 상태와 2.1 공통 표에 대응 추가, `PromptSync` 기동 순서 기재 |
| C42 | 코드↔문서 | user-flow에 생각 활동(FN-DSH-04, #240)·학생 공개 설정(#206)·학부모 리포트 표시 설정(#209) 화면 없음 | 학생·학부모 흐름에 추가 |
| C43 | 코드↔문서 | `ai.md` "AI 계측 SDK는 #171 후속"(langfuse·OTLP 의존성 존재), `e2e.yml`·#246 보고서 "매일 03:00 KST(develop)" — GitHub schedule은 기본 브랜치(main) 워크플로만 실행하고 main에 `e2e.yml` 없음(develop 실행 이력 0건) | 문구 정정 |
| C44 | 코드↔문서 | ai OpenAPI `/analysis/report-template`의 400·401·403·503에 Problem 스키마 없음 | 다른 내부 경로와 같은 Problem·`retryable` 선언 |
| D22 | 문서 간 | `docs/README.md` 색인 누락: `issue-208-event-log.md`·`learning-cold-start.md`·`mentoring-20261029.md` | 추가 |
| D23 | 문서 간 | `ml/m2/README.md` 앵커 `#최신-kluerobertabase-…`(실제 `klueroberta-base`) | 정정 |
| D24 | 문서 간 | 4장 표의 낡은 상태(B10·A7·D16·A11·4.6 오류 코드·테스트 공백) | 4장 해당 행에 후속 처리 표기 |
| D25 | 문서 간 | `core-gateway.md` 6장 Redis 사용처 표가 #225 이전 코드(분석 사용량 Redis Lua) 기준임을 밝히지 않음 | 검토 당시 기준과 #225 이후 위치 문장 추가 |

### 5.4 API 변경

| 대상 | 변경 |
|---|---|
| core `GET /internal/students/{studentId}/report-template` | 학생 삭제 요청·비활성 시 409 코드 `TEMPLATE_PROPOSAL_EXPIRED` → `STUDENT_UNAVAILABLE`(상태 동일, report는 비-2xx 모두 실패 처리) |
| ai OpenAPI | `/analysis/report-template` 오류 응답에 Problem 스키마 선언(동작 변경 없음) |
| 웹 | 지원 화면이 core 실제 계약으로 요청(문의 제목 필수, 문의 유형 `OTHER` 제거, 신고 `Idempotency-Key`) |

### 5.5 아키텍처 원칙 정합성

core·learning은 import를 레이어로 분류해 전수 검사, Python·웹은 grep으로 확인.

지켜지는 원칙: 3장 3.7·4장 4.5 항목 유지. 4장 이후 코드 추가 확인:
- 트랜잭션 안 외부 호출 없음: `ReportTemplateService`는 두 잠금 트랜잭션 사이에서 AI 호출, `ReportQueryService`는 report 호출 후 `@Transactional` 진입, #225 `AnalysisUsageService.consume`은 Redis 없이 DB만
- 새 주기 작업(learning `StuckJudgmentScheduler` #241, core `EventRetentionCleanup`·learning `ProcessedEventCleanup` #208)은 ShedLock 대신 조건부 UPDATE·멱등 DELETE로 레플리카 중복 실행 안전. 판정 lease 90초 > learning→ai 35초 + 35초
- 새 공개 경로(sharing-preferences·`/students/me/preferences`·report-template·comparison·`/admin/notices`)는 `PublicAuthFilter` 역할 검사와 서비스 재검사 모두 적용
- 웹: 새 화면(`ThinkingActivities`·`Customize`·`StudentSharingPage`·`AttemptComparisonPanel`·알림 SSE)은 TanStack Query로 서버 상태 조회, presentation의 `apiFetch`·`mocks` 참조 없음

원칙과 다른 구현(이번에 수정하지 않음, 리팩터 범위 결정 필요):

| # | 내용 | 원칙 | 근거 |
|---|---|---|---|
| A17 | #208 이벤트 기록·보존 정리가 Presentation·진입점에서 repository 직접 호출. learning 정리 작업은 `@Scheduled`가 service 패키지에 위치(#241 `StuckJudgmentScheduler` 분리 방식과 다름) | 2.1·2.2 | core `_common/messaging/EventAuditConsumer.kt`·`EventRetentionCleanup.kt`, learning `record/service/ProcessedEventCleanup.kt`, report `worker.py` `prune_event_records`. 이슈 #278 |
| A18 | 기능 간 client·repository 직접 참조 | 2.2 기능 간은 service로만 | core `report/service/ReportTemplateService.kt` → `conversation.client.AiClient`·`guardianship.repository.StudentAccessRepository`. 이슈 #279 |
| A19 | ai 리포트 설정 제안이 프롬프트 레지스트리 밖 고정 버전(`analysis-template@1`)이라 #68 활성 본문 검사 대상 밖. core `AiClient.reportTemplate`은 서킷 브레이커 없음(`ai-analysis`는 `stream`만) | 1.3·1.5 | ai `analysis_agent/template_settings.py`, core `conversation/client/AiClient.kt`. 이슈 #280 |

### 5.6 남은 공백

| 대상 | 내용 |
|---|---|
| OpenAPI | `STUDENT_RECORDS_PRIVATE`(403)가 api-spec에만 있고 core OpenAPI 응답 설명에 없음(기록·근거·분석 대화·리포트 근거/다운로드 경로) |
| 요구사항 차이 | FN-AGT-12 "수학 점검 예시 질문"이 구현 예시 질문 5개에 없고, 가능 여부를 기록 유무 하나로 정함(`ConversationService.examples`). api-spec 2.4 행에 현재 동작 기재 |
| 테스트 공백 | core HTTP 테스트 없음: `/attempts/{id}/comparison` 프록시(learning은 `AttemptComparisonIntegrationTest`), sharing-preferences(서비스 테스트만) |
| CI | `e2e.yml` 야간 실행은 main 병합 전까지 동작하지 않음. `tests/*-browser.mjs`·JDK 21 `verify_*`는 수동 |
| 수동 브라우저 스크립트 | `tests/requirements-browser.mjs`가 develop에서 이미 실패: 지원 단계(목록 제목 엄격 모드 중복)와 계정 화면 자녀 정보 저장 단계(`자녀 정보를 저장했습니다.` 미표시). 지원 단계는 B28과 함께 수정, 계정 단계는 남음(worktree로 develop 재현) |
| 번호 체계 밖 절 | api-spec 첫 절(2026-11-01 #206·#207)·functional-spec #206·#207·#209 절(5.2 D16) → **#245 정리**(functional-spec 맨 위 변경 요약 절은 유지) |
| 발행 이슈 | B32 #275, B34 #276, B35 #277, A17 #278, A18 #279, A19 #280 |
