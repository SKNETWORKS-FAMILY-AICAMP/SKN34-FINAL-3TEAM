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
| B8 | 미해결(#131) | report Outbox가 여전히 가장 오래된 행부터 선택(`outbox/repository.py` `claim_next`), 순서 정책 결정 필요 |
| B9 | 해결 | core 주기 점검·report 상태 복구·영구 job guard·삭제 시 미종료 작업 종료(#132) |
| B10 | 미해결(임시 결정 유지, #133) | `StudentDeviceController`가 `remoteAddr` 사용, 신뢰 프록시 설정과 함께 처리 |
| B11·B13 | 해결 | #134 |
| B12(#93·#97) | 해결 | 관리자 모델 요청이 `RegisterModelVersion`·`ActivateModelVersion`·`RollbackModelVersion`과 일치, `/auth/login`·`/auth/signup`은 MSW 시연 전용 파일에만 남음 |
| B17 | 일부(#135) | report `ai_url`·`core_url`, scoring `core_url`은 사용. ai `scoring_url`·`core_url`은 미사용(M2 교차 확인·활성 버전 조회 예정) |

### 3.3 발견 항목과 처리

| # | 종류 | 내용 | 처리 |
|---|---|---|---|
| B18 | 결함(중간) | core 관리자 미션 프록시가 learning 404(없는 미션 `NOT_FOUND`)를 503 `ADMIN_MISSIONS_UNAVAILABLE`로 바꿈. api-spec 2.8이 #145 이전에 정한 규칙이고 learning 보고서 10절에서 core가 고치기로 함 | 이슈 #163(api-spec 2.8 변경 동반) |
| B19 | 결함(낮음) | core 신고·정정이 learning 403(학생 범위 밖)을 503 `SUPPORT_DEPENDENCY_UNAVAILABLE`로 바꿈(api-spec 1.3·5.7 "기타 비-2xx는 503"). 신고는 막히지만 원인 구분 불가 | 이슈 #163(계약 결정 필요) |
| B20 | 스크립트 | `check_policy_migrations.py`가 #19 당시 최신 버전 수(core 7, learning 5)를 고정해 V8 이후 추가로 항상 실패 | 수정: #19 정책 버전까지만 `-target`으로 적용(`POLICY_HEAD`). 이후 버전은 `check_db_migrations.py`가 검사 |
| B21 | 스크립트 | `verify_feedback_learning.py`가 learning에 `CORE_URL`을 넘기지 않아 피드백이 결제 사용 확인에서 503(learning 보고서 10·11절) | 미수정(JDK 21 없이 실행 확인 불가). 이슈 #164 |
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
| A2 | 서킷 브레이커가 core→learning(`learning-json`·`learning-feedback`), learning→ai에만 있음. core→ai(분석 대화)·core→report·core→토스는 타임아웃만 | 1.3 타임아웃 + 재시도 제한 + 서킷 브레이커 | `core/conversation/client/AiClient.kt`, `core/report/client/ReportClient.kt`, `core/payment/client/TossClient.kt` | 이슈 #167, architecture 1.3에 현재 적용 범위 표기 |
| A3 | domain 8개 파일이 `HttpStatus`(BusinessException 생성)·Jackson(`JsonNode`·`@JsonIgnore`·`@JsonInclude`) 참조 | 2.1 Domain 프레임워크 의존 금지 | core `conversation/domain/Conversations.kt`·`payment/domain/Payments.kt`, learning `answer/domain/AnswerContent.kt`·`attempt/domain/Attempt.kt`·`judgment/domain/Judgment.kt`·`judgment/domain/Support.kt`·`mission/domain/Mission.kt`·`record/domain/Period.kt` | 이슈 #168(core)·#169(learning) |
| A4 | 레이어 방향 역참조: `usage/service/LlmUsageService` → `usage.consumer.LlmUsageRecorded`, `payment/client/PremiumUsageClient` → `payment.service.PaymentTransactions.unavailable`. 수신 역할인 `notification/messaging/NotificationRedisSubscriber`가 Infrastructure 위치에서 service 호출 | 2.2 단방향 의존 | 해당 파일 import | 이슈 #168 |
| A5 | 시연 컴포넌트 `presentation/student/DemoStudentEntry.tsx`가 `apiFetch` 직접 호출·`mocks/fixtures` 참조 | 3장 컴포넌트 API 직접 호출 금지 | `frontend/web/src/presentation/student/DemoStudentEntry.tsx:2-10` | 이슈 #170 |
| A6 | ai→scoring 교차 확인 호출자 없음(ai `scoring_url` 미사용), ai `model.version.activated` 소비 없음 | 1.2·1.5 판정 흐름, 1.6 브로드캐스트 | `ai-service/app/config.py:16-17`, `versions.py` | 기존 #69·#68 |
| A7 | 저장소 인프라가 `platform-data` chart·kind뿐. 앱 Helm chart·Ingress·NetworkPolicy·HPA·KEDA·PDB·Argo CD 앱 배포, OpenTelemetry·Prometheus·Langfuse 의존성 없음 | 4.3·4.4·4.6, 1.6 Langfuse 보정 | `infrastructure/`, 각 `pyproject.toml`·`build.gradle.kts` | 이슈 #171, architecture 해당 절에 "(예정, 저장소 미구성)" 표기 |
