# core 학습 프록시·피드백 SSE·대시보드·알림 (#38·#39·#40·#44)

통합 원본: issue-38-core-learning-proxy, issue-39-core-feedback-sse, issue-40-dashboard, issue-44-notifications

계약은 [API 명세](../design/api-spec.md) 1.4·2.2·2.3·2.7·3.2, 구조는 [아키텍처](../design/architecture.md) 1.3·1.6.

## 1. 학생 미션 공개 API·멱등성 (#38)

- 공개 미션·시도 경로를 learning 내부 경로로 전달. 업무 검증·DB 조회는 learning 소유, core는 검증된 STUDENT 컨텍스트만 사용
- 학생 학년·시연 여부는 `StudentLearningContextService`(core 소유 `grade`·`is_demo` 조회)로 정해 `grade`·`demo` 쿼리로 전달. 공개 쿼리·위조 헤더는 근거로 쓰지 않음(미션 조회·시도 시작 공통)
- 서킷: Resilience4j(production 의존성) 최근 20건·최소 20건·실패율 50%·차단 30초·half-open 1건. 전송 오류·5xx만 실패로 집계, 4xx는 정상 HTTP 결과. HTTP 자동 재시도 없음. 일반 JSON 연결 2초·응답 30초
- 멱등성: 기존 `idempotency_record`만 사용. PostgreSQL 세션 advisory lock과 같은 auto-commit 연결에서 레코드를 읽고 쓰므로 이 Repository만 JDBC 사용. HTTP 동안 연결 1개를 보유하고 트랜잭션은 없음(풀 크기와 HTTP 타임아웃이 동시 처리 상한)
  - 동시 재요청 409 + `Retry-After`, 같은 계정의 경로·학생·본문 불일치 422
  - 확정 응답은 원문·필수 헤더·상태를 보관. 미확정·5xx·전송 실패는 같은 키로 learning 재호출. core 저장 실패는 503(learning 성공을 성공으로 가장하지 않음)
  - learning이 키의 UK·본문 대조·최초 응답 재구성·답변/판정 원자적 저장을 제공해야 두 DB 사이 중복 생성이 없음(core TTL 24시간 이후에도 learning UK 유지)
- 일일 한도(P13)는 core Redis 책임(미구현). learning의 신규 `201`·이어하기 `200`을 그대로 전달하고, 한도 연계 시 `201`만 집계·한도 도달 시 신규 생성만 차단

## 2. 피드백 SSE (#39)

- 피드백 조합은 #38의 `LearningProxyService`·`LearningClient`를 그대로 쓰고 read timeout만 80초. `SseEmitters`는 virtual task·15초 heartbeat·90초 연결·정리만 담당, 전송 실패·종료 콜백은 heartbeat만 취소(learning 작업 유지). 사용자 컨텍스트는 명시적으로 전달·정리
- learning DONE(HELD 포함) → `result`, RUNNING → `status`, learning 오류 → `error`, 이후 `done`. core는 판정 전이·리스·실패 재실행 캐시를 구현하지 않음
- 서킷 분리: 일반 JSON은 `learning-json`, 피드백은 `learning-feedback`. 전송 실패·시간 초과·계약된 Problem Details가 아닌 5xx만 실패로 셈. `application/problem+json`에 비어 있지 않은 `code`가 있으면 업무 실패(`error` 이벤트)로 전달하고 서킷 실패로 다시 세지 않음(learning의 AI 서킷과 이중 차단 방지)
- 전송·종료 상호 배제는 `ReentrantLock`(synchronized 안의 블로킹 전송이 virtual thread carrier를 고정하지 않도록, JFR `jdk.VirtualThreadPinned`로 확인)
- 스트림 시작 전 인증 DB 실패는 `PublicAuthFilter`의 503 `AUTH_UNAVAILABLE`
- 종료 예산: preStop + Spring/Tomcat 종료 + executor 85초·timer 5초 + 여유보다 긴 `terminationGracePeriodSeconds` 필요. 앱 Deployment가 저장소에 없어 실제 롤링 종료 검증은 미실시

## 3. 학생·학부모 대시보드 (#40)

- 공개 조회 7개(학생 home·attempts·thinking-activities, 학부모 summary·thinking-types·attempts·상세)는 `LearningRecordService` → `LearningRecordClient` → `LearningClient`(`learning-json` 서킷·내부 인증 재사용). 현재 연결·ACTIVE·동의 검사 후 하위 scope를 자녀 하나로 줄이고 finally 복원
- 기간: 둘 다 생략하면 KST 오늘 포함 최근 7일, 한쪽만은 400(웹 목업의 고정 날짜는 운영 기본값 아님). 상세도 같은 기간을 받지만 원문은 시도 전체 이력
- 학생 home: learning `records/.../home`의 resume는 초안 없이 식별만, core가 학생 전용 `/internal/attempts/{id}`로 본인 초안을 조합(두 번째 조회 실패도 홈 실패). 이어할 시도 선택은 learning 소유
- 학부모 상세: Attempt 최상위 필드 유지 + `state`·`period`, draft·중첩 memo는 성공·오류 JSON 모두에서 제거. Metric 소수는 BigDecimal로 읽어 정밀도 유지
- 내부 records 식별자는 `studentId`로 통일하고 core가 학부모 공개 응답의 `childId`로 바꿈
- 공급자 성공 응답이 JSON·식별자·필수 봉투 계약을 어기면 502 `LEARNING_CONTRACT_INVALID`. 공급자 오류는 `NO_RECORD`로 바꾸지 않고 core는 건수·비율·state를 계산하지 않음
- CI 연결 풀: 여러 캐시된 Spring 테스트 컨텍스트가 같은 PostgreSQL을 공유해 `too many clients`가 발생 → 테스트 전용 `maximum-pool-size=5`, `minimum-idle=0`

## 4. 앱 내 알림 (#44)

- Redis 연결은 Boot 표준 `spring.data.redis`(`REDIS_HOST`·`REDIS_PORT`·`REDIS_PASSWORD`), 채널 `core:notifications:v1`(학생 기기 페어링 키와 무관)
- 학생 세션은 보호자 계정 ID를 공유하므로 알림·설정 API 전체 금지
- 리포트 종료 전이(`ReportJobFinished`)와 같은 트랜잭션에서 저장. `processed_event`·상태 전이·notification UK가 재전달 중복을 막음. 실패는 독립 유형 `REPORT_FAILED`
- 커밋 후 Pub/Sub 발행, 실패는 `FAILED`(`REDIS_PUBLISH_FAILED`)로만 기록하고 리포트 상태를 되돌리지 않음. 발행 성공은 브라우저 전달 보장이 아님. 재시도 큐 없음
- 유실 복구는 SSE `ready` 후 목록 재조회와 주기적 동기화(Last-Event-ID replay 없음)
- 마이그레이션: 알림 유형 CHECK 확장은 V12
- 남은 연결: 학생 PIN 잠금·새 기기 알림 정책, 웹이 알림 링크(`/parent/report?childId&reportId`)로 자녀·상세를 자동 선택하는 처리


## 5. 지원·결제·관리자·학생 프로필 통합과 최신 develop 반영

대상은 `feature/core-support-payments-integration`(기존 head `cd4f39b`)이며 develop `c44ace8`(#127)을 일반 merge한다. 기존 기능 커밋과 #127의 인증 경로 정규화·리포트 상태/오류 전달·자녀별 스케줄 실패 격리·알림 오류 코드·learning 잠금/readiness·report 삭제 멱등 처리를 보존한다. 지원·결제·운영·학생 프로필의 기존 API 및 공급자 미연결 경계도 유지한다. 설계 문서 충돌은 양쪽 계약을 보존하고, #48로 연결된 상품 권한을 미연결로 설명하던 문구만 실제 호출 경계에 맞춘다.

마이그레이션은 develop의 `V14__remove_speech_call_type.sql`과 결제 V15 SQL/체크섬을 보존하며, 지원의 `V14__support_scope_and_correction_requests.sql`을 **SQL 바이트 변경 없이 V16**으로 옮긴다. V15/V16은 서로 의존하지 않는다. 기존 지원 V14를 적용한 임시 검증 DB와 새 develop 이력은 호환된다고 가정하지 않으며 공유 DB·Flyway 이력·체크섬을 repair하지 않는다. 빈 격리 DB에서 전체 migration/ERD 왕복을 검증한다. 구 버전 번호를 포함한 기능 보고서는 당시 검증 이력이며 현재 적용 순서는 이 절과 ERD 8·12장을 따른다.

관리자 기존 계약 보존 fixture는 #127이 변경한 기존 경로/스키마의 fingerprint만 갱신하고 지원·결제 등 그 밖의 fingerprint는 유지한다. 최신 develop의 새 계약을 되돌려 통과시키지 않는다. 변경 파일은 sourceCommit(기존 기능 기준)과 upstreamSourceCommit(추가 develop 기준)을 함께 기록하며 얕은 CI checkout에서도 동작한다.

최종 통합 검증은 아래 결과를 따른다. #46의 실제 learning 지원 공급자, #47 REPORT/CONVERSATION 재처리·learning 관리자 공급자, #119 report-worker 호출·제목·최종 AI 요청 가림은 이번 통합으로 구현하지 않는다. 실제 PG/Google·배포 검증과 로컬 대역/서비스 연동을 구분한다.


### 최신 develop 통합 검증 결과

- JDK 21 격리 Linux 환경의 core 전체 **46클래스·285개**, learning 전체 **28클래스·191개** 테스트와 양쪽 `bootJar` 통과. 실패·오류·생략 0. 실제 PostgreSQL/Redis/RabbitMQ를 사용하는 기존 인증·관리자·결제·지원·학생 프로필·리포트 회귀를 포함한다. Gradle 명령은 `bash gradlew test bootJar --no-daemon --max-workers=1 --no-watch-fs --console=plain -Pkotlin.compiler.execution.strategy=in-process`이며 검증 전용 JVM/fork 자원 제한을 사용했다.
- `python -O -m unittest discover -s scripts/tests -q` **74개** 통과. 새 Flyway 버전 중복 검사 포함. core/learning/협의용 support-learning OpenAPI 표준 검사 통과. core OpenAPI 106경로·124스키마는 기존 feature 추가와 develop 변경을 재귀 비교한 의미상 합집합과 완전히 같다.
- 실제 테스트 산출물의 지원 HTTP 7종·결제 5종·알림 2종·report 이벤트 4종/상세 응답, 실제 실행 core 관리자 HTTP 5종을 공개 계약과 대조해 통과했다.
- 별도 PostgreSQL의 전체 migration/ERD cycle **39.4초** 통과: core 42테이블/390컬럼, learning 19/158, report 7/50. 위반 입력 60건·CHECK 값 집합 74개·ERD 인덱스 23개. 재실행 migration 0·이력 불변 및 report downgrade/upgrade 통과. 별도 core_upgrade_db에 develop의 원본 SQL로 V14까지 적용한 다음 최종 SQL로 V15/V16 **2개만 추가 적용**하는 경로도 통과했다. SQL 원문 보존을 확인했고 Flyway repair·공유 DB 변경은 없다.
- 프론트 `npm test` **93개**, lint·build 통과. 최초 빌드는 기존 node_modules의 lockfile 의존성(qrcode) 누락으로 실패했고 `npm ci --ignore-scripts`로 lockfile 그대로 복원한 뒤 빌드 성공했다. package/lockfile 변경은 없다. 기존 500kB 초과 번들 경고는 남아 있다.
- 최종 JAR 2개와 전용 DB/Redis/RabbitMQ에서 실제 core→learning 사용 증빙, 환불 동결의 learning→core 차단, 관리자 반려 후 피드백 core→learning→core DONE/USED, 사용 후 409 환불 거부, 실제 구독 기반 탈퇴 차단, 상품 기반 report Outbox narrativeEnabled true/false를 확인했다. 관리자 운영 5종·25큐 응답을 실제 서비스로 조회했다. 세미콜론/인코딩 관리자 경로의 학부모 403 및 내부 경로의 무토큰 401, SYSTEM·학생 scope 프로필 조회/no-store와 scope 불일치 403도 실제 HTTP로 확인했다.
- 실제 연동의 결제 상태·인증 계정은 합성 DB fixture이며 Toss/Google/AI API는 호출하지 않았다. learning 피드백은 CHOICE 규칙을 사용했다. Java 테스트·위 HTTP 호출자를 실제 report-worker·브라우저 E2E로 집계하지 않는다. #46 실제 지원 공급자, #47 REPORT/CONVERSATION 재처리·learning 관리자 미션 공급자, #119 실제 worker/제목/AI payload 가림, 배포는 계속 미검증이다.
- 격리 빌드 입력 501파일과 현재 runtime/contract 소스 바이트 일치, 설계 문서 링크·충돌 표시·마이그레이션 이전 경로 참조·`git diff --check`를 확인했다. 이전 V14 지원 경로는 이 절의 이동 설명에만 남기고 기능 보고서의 V14/V15 수치는 당시 이력으로 보존한다. 원격 CI는 push 후 새 head에서 별도 확인한다.

## 6. Redis 사용 필요성과 PostgreSQL 대체 비교 (#210)

10/29 [멘토링](mentoring-20261029.md)의 재검토 권고에 따라 core의 Redis 사용처와 PostgreSQL 대체안을 비교한다. 담당자 결정은 **B. 부분 대체**(2026-11-02, [선택지와 결정](#선택지와-결정))이며, 대체 구현은 별도 이슈로 진행한다. 이 절 작성 시 코드·설정·계약·마이그레이션은 바꾸지 않았다. 부하·비용 수치는 실측이 없어 모두 추정이다. 코드 위치는 `backend/core-service/src/main/kotlin/com/sagomungchi/core/` 기준이다.

### 사용처와 장애 시 동작

#210 검토 당시 코드 기준이다. 분석 대화 일일 사용량·관리자 재처리 중복 차감 행은 #225 이후 PostgreSQL `payment_premium_usage`로 옮겨져 Redis를 쓰지 않는다([#225 구현](#분석-대화-사용량-db-이관-구현-225)).

| 사용처 | 코드 위치 | Redis가 보장하는 성질 | Redis 장애 시 현재 동작 |
|---|---|---|---|
| 학생 기기 페어링 코드 | `account/repository/PairingRepository.kt:12-17`, `account/service/StudentAuthService.kt:41-58` | 해시 키 `SET NX`·10분 TTL, Lua `GET`+`DEL` 1회 소비 | `DataAccessException` → 503 `STUDENT_AUTH_UNAVAILABLE`(`StudentAuthService.kt:121,127`). 등록된 기기의 프로필·PIN 로그인은 DB만 사용해 영향 없음(`:69-89`) |
| 기기 등록·페어링 발급 rate limit | `PairingRepository.kt:18,21`, `StudentAuthService.kt:42,55,120` | Lua `INCR` 후 첫 증가에만 `EXPIRE 600`(10분 고정 창, 기본 20회 `account/config/StudentDeviceProperties.kt:9`) | 한도 확인이 먼저라 발급·등록 모두 위와 같은 503 |
| 분석 대화 일일 사용량 | `conversation/service/AnalysisUsageService.kt:26-32,43-47,57-63` | Lua 확인+증가 원자 처리, 키 `analysis:daily:v1:{childId}:{KST 일자}`, `EXPIREAT` 다음 KST 자정+1일 | 503 `ANALYSIS_USAGE_UNAVAILABLE`(`:30`). 대화 생성·조회는 권한 확인만 해 영향 없음(`conversation/service/ConversationService.kt:43`) |
| 관리자 대화 재처리 중복 차감 방지 | `AnalysisUsageService.kt:33-39,48-56`, `ConversationService.kt:153` | 요청 ID 표식 `analysis:retry:v1:{requestId}` 확인·증가·표식 저장을 한 스크립트로 처리 | 같은 503, 재처리 실행 실패 |
| 알림 다중 레플리카 SSE 중계 | `notification/messaging/NotificationRedisPublisher.kt:17-26`, `notification/config/NotificationRedisConfiguration.kt:13-18`, `notification/consumer/NotificationRedisSubscriber.kt:14-17`, `notification/service/NotificationStreams.kt:29-33` | 채널 `core:notifications:v1` fan-out(at-most-once, 구독자 0명도 발행 성공), 커밋 후 발행 | 발행 예외 → `FAILED`·`REDIS_PUBLISH_FAILED`(`notification/service/NotificationDeliveryService.kt:12`). 알림 행·리포트 상태는 유지되고 목록 재조회로 복구. 관리자 재처리(`admin/service/OperationRetryService.kt:59`)도 같은 publisher 사용 |
| 무료 플랜 미션 일일 한도(미구현) | 설계만 존재([API 명세](../design/api-spec.md) 2.2 P13·4.1 `/internal/missions/{id}/attempts`) | 설계상 core Redis 카운터, 신규 `201`만 집계 | 코드 없음 |

전수 확인 결과(`StringRedisTemplate`·`RedisTemplate`·`RedisConnectionFactory`·`@Cacheable`·`spring.data.redis` 검색):

- 운영 코드의 Redis 접근은 위 4개 파일뿐이다. `@Cacheable`·`CacheManager`·세션 저장소 사용은 없어 Redis를 **조회 캐시로는 쓰지 않는다**. learning·ai·scoring·report 서비스는 Redis를 쓰지 않는다
- 연결은 `application.yml:21-27`(연결·명령 timeout 2초). readiness 그룹은 `readinessState,db,rabbit`(`application.yml:57-58`)으로 Redis를 포함하지 않아 Redis 장애 시 Pod는 Ready를 유지하고 기능별로만 503이 난다
- 배포·실행 설정: `compose.yaml:69-77,135-137`, platform-data chart `templates/redis.yaml`(replicas 1 `:11`, AOF·`maxmemory`·`noeviction` `:44-49`), `values.yaml:43-53`, local `environments/local/platform-data.yaml:42-52`, `environments/local/core-service.yaml:30,66`, NetworkPolicy `policies/local/platform.yaml:61`
- 테스트·검증: `IntegrationTestSupport.kt:38,61-62` Redis 컨테이너, `scripts/verify_*.py`, `scripts/report_integration/compose.yaml:29-60`
- 문서 표현 차이: [아키텍처](../design/architecture.md) 6장 사용 기술 표의 "SSE 중계·캐시", platform-data chart README의 "캐시·실시간 알림 중계"는 실제 사용(캐시 없음)과 다르다. 결정 후 함께 정리한다
- #133(기기 등록 rate limit의 IP 기준)은 키를 무엇으로 정할지의 문제라 저장소 선택과 무관하며, 어느 쪽을 택해도 같은 키 정의를 적용한다

### 사용처별 PostgreSQL 대체안

| 사용처 | 대체 방식 | 현재와의 차이 | 변경 규모(추정) |
|---|---|---|---|
| 페어링 코드 | 테이블(`code_hash` PK·보호자·자녀 목록·`expires_at`). 발급 `INSERT … ON CONFLICT DO NOTHING`(충돌 시 현재처럼 최대 5회 재생성), 소비 `DELETE … WHERE code_hash=? AND expires_at>now() RETURNING …` | TTL은 만료 컬럼 조건으로 대신하고 만료 행은 기존 `_common/web/IdempotencyService.kt:64`·`_common/web/repository/IdempotencyRepository.kt:70`의 주기 `DELETE` 방식으로 정리. 정리가 늦어도 조회 조건 때문에 기능 영향 없음. 소비와 기기 저장을 한 트랜잭션에 넣으면 "등록 실패 시 코드 소멸"(API 명세 3.11)을 없앨 수 있으나 계약 변경이라 선택 사항 | 마이그레이션 1개, `PairingRepository` 교체, 기기 테스트 수정. 소 |
| rate limit 카운터 | 테이블(`key` PK·`window_start`·`count`). `INSERT … ON CONFLICT (key) DO UPDATE SET count = CASE WHEN 창 만료 THEN 1 ELSE count+1 END, window_start = … RETURNING count` | 행 잠금으로 동시 증가 보장, 10분 고정 창 동작 동등. 비인증 `register` 요청마다 RDS 쓰기 1건이 생겨 남용 트래픽이 DB 쓰기로 바뀜 | 마이그레이션 1개(페어링과 합칠 수 있음), 정리 작업. 소 |
| 분석 일일 사용량 | `(student_id, usage_date)` PK 테이블에 조건부 UPSERT `… DO UPDATE SET used = used+1 WHERE used < :limit RETURNING used`(0행이면 한도 도달). 날짜 컬럼이라 TTL 불필요, 보관 기간 정리만 | 차감은 이미 보호자·학생 행 잠금 트랜잭션 안에서 호출된다(`ConversationService.kt:62-69,92`). 현재 Redis 증가는 이 트랜잭션과 별개라, 차감 뒤 같은 트랜잭션이 실패하면(예: `recordAttempt`의 상품 충돌 `:102`) 카운트만 남는다(코드 읽기 기준, 테스트로 재현하지 않음). PostgreSQL로 옮기면 메시지 저장·사용 이력과 함께 커밋·롤백된다. 유료 구독은 같은 트랜잭션에서 사용 이력 행을 이미 남기지만(`payment/service/PaymentAnalysisEntitlementProvider.kt:24-29`) 구독이 없으면 행이 없어(`payment/service/ProductEntitlementService.kt:53`) 그것만으로 일 카운트를 대신할 수 없다 | 마이그레이션 1개, `AnalysisUsageService` 내부 교체(공급자 포트 유지), `AnalysisUsageContractTest` 갱신. 소~중 |
| 관리자 재처리 표식 | 요청 ID UNIQUE 행 삽입을 사용량 증가와 같은 트랜잭션에서 수행 | "사용량 Redis와 DB는 분산 원자 트랜잭션이 아니다"(API 명세 "#47 CONVERSATION 관리자 재처리")라는 제약과 표식 TTL·130초 실행 만료의 결합이 사라짐 | 위 테이블과 함께. 소 |
| 미션 일일 한도(미구현) | 분석 사용량과 같은 테이블 패턴(종류 컬럼으로 공용화 가능) | 어느 저장소든 신규 구현량은 비슷. learning 응답 `201` 이후 집계는 core 단독 트랜잭션 | 신규 구현과 같음 |
| 알림 Pub/Sub | `LISTEN/NOTIFY`(채널 예: `core_notifications_v1`) | 아래 별도 정리 | 마이그레이션 없음. publisher 교체 + 리스너 신규(전용 연결·재연결·종료 처리) + 다중 레플리카 통합 테스트 신규. 중 |

`LISTEN/NOTIFY` 대체 시 확인 사항(PostgreSQL 동작 기준, 이 저장소에서 시험하지 않음):

- 전달 시점: 트랜잭션 안의 `NOTIFY`는 커밋될 때만 전달되고 롤백되면 버려진다. 알림 저장 트랜잭션 안에서 `pg_notify`를 호출하면 현재 AFTER_COMMIT 발행과 같은 "커밋 후 전달"을 DB가 보장하지만, 발행 실패가 곧 커밋 실패가 되므로 `FAILED`·`REDIS_PUBLISH_FAILED` 상태의 의미를 다시 정해야 한다. 커밋 후 별도 `NOTIFY`(현재 구조 유지)도 가능하다
- payload: 기본 설정에서 8000바이트 미만. 현재 메시지는 UUID 2개(`notification/domain/Notifications.kt:10`)라 제한과 무관하다
- 수신 연결: 레플리카마다 `LISTEN`을 유지하는 상시 연결 1개가 필요하다. Hikari 풀 연결은 반납 후 다른 요청이 쓰므로 풀 밖 전용 연결에서 PgJDBC 알림 대기 루프, 끊김 감지·재연결·재`LISTEN`을 직접 구현해야 한다. Spring Data Redis의 `RedisMessageListenerContainer`에 해당하는 표준 구성이 core 의존성에는 없다
- 유실 특성: 리스너가 끊긴 동안의 알림은 Redis Pub/Sub과 마찬가지로 유실된다. 기존 `ready` 후 목록 재조회 복구([API 명세](../design/api-spec.md) 2.7)가 그대로 필요하고 그대로 유효하다
- 연결 경유: PgBouncer transaction pooling·RDS Proxy처럼 연결을 다중화하는 프록시를 거치면 `LISTEN` 세션이 유지되지 않거나 세션이 고정된다. 현재 설계에는 프록시가 없으나 도입 시 제약이 된다
- 커밋 경합: `NOTIFY`를 포함한 트랜잭션은 커밋 시 전역 잠금으로 서로 직렬화되는 것으로 알려져 있다. 리포트 종료·지원 알림 빈도에서는 영향이 작을 것으로 추정한다

### 운영 비용·부하

- 배치: Redis는 ElastiCache가 아니라 EKS `platform` namespace의 StatefulSet + EBS gp3 PVC이며 replicas 1이다([아키텍처](../design/architecture.md) 4.1·4.3, `templates/redis.yaml:11`). 운영 values는 저장소에 없고 local 값만 있다(requests 50m·64Mi, limits 250m·256Mi, `maxmemory 128mb`, PVC 512Mi)
- 유지 비용(추정): Pod 자원과 소용량 EBS의 금액은 작다. 실제 비용은 운영 항목 수다. 이미지 버전 갱신, AOF·PVC 보존, `REDIS_PASSWORD` Secret, NetworkPolicy, 관측·알람, 장애 대응 절차를 RabbitMQ와 별도로 유지해야 한다
- 장애 영향 범위: 단일 replica·복제 없음이라 노드 장애나 재스케줄 동안 페어링·기기 등록·분석 질문이 503이 되고 알림 실시간 전달이 멈춘다(AOF로 재시작 후 키 복원). 대체하면 상태 저장소 장애 지점이 RDS 하나로 모인다. RDS 장애 시에는 readiness에 `db`가 있어 core가 이미 대부분 실패하므로 대체로 추가로 잃는 기능은 적다(추정)
- 데이터 크기(추정): 12/7 배포는 데모 계정만 운영하므로 페어링·카운터·일 사용량 키는 수천 개 이하, 메모리 수 MB 미만으로 본다
- RDS 쓰기 부하(추정): 페어링 발급·등록당 1~2건, rate limit 요청당 1건, 분석 질문당 UPSERT 1건(같은 트랜잭션에 이미 메시지 INSERT·사용 이력이 있어 증분이 작음), 시간당 정리 `DELETE` 1회. 데모 규모에서는 무시할 수준으로 본다. 위험 요소는 비인증 `register` 경로 남용 시의 쓰기 증가다
- RDS 연결 수(추정): `application.yml`에 풀 설정이 없어 Hikari 기본 최대 10개 × core 레플리카다. `LISTEN/NOTIFY`를 쓰면 레플리카당 전용 연결 1개가 더해진다(HPA 최소 2, 아키텍처 4.4). RDS 최대 연결 수 대비 영향은 작다
- 테스트·로컬: 전부 대체하면 compose·`IntegrationTestSupport`·검증 스크립트의 Redis 컨테이너가 빠진다. 과거 검증에서 Redis 최초 연결 지연으로 인한 실패가 있었다([#41](issue-41-analysis-conversations.md)·[#47](issue-47-admin-operations.md) 보고서)

### 선택지와 결정

| 선택지 | 내용 | 장점 | 단점 | 후속 규모(추정) |
|---|---|---|---|---|
| A. 전부 유지 | 현재 구조 유지, 미션 한도도 Redis로 구현 | 추가 작업 없음, 검증된 경로 유지 | 운영 항목 유지, 분석 사용량과 DB 트랜잭션 불일치·재처리 표식 제약 유지 | 문서 정리만 |
| B. 부분 대체 | 분석 사용량·재처리 표식(+미션 한도 신규)은 PostgreSQL, 페어링·rate limit·알림 중계는 Redis 유지 | DB 트랜잭션과 정합해야 하는 값만 DB로 옮겨 롤백 정합성 확보, 휘발성·fan-out 용도는 Redis 그대로 | Redis 운영 부담은 그대로 | 마이그레이션 1개, core 1개 서비스·테스트. 소~중 |
| C. 전부 대체 | 위 표의 대체안 전부 + `LISTEN/NOTIFY` | StatefulSet·Secret·NetworkPolicy·테스트 컨테이너 제거, 상태 저장소 하나 | 알림 리스너 직접 구현·다중 레플리카 재검증, 비인증 경로의 DB 쓰기, 프록시 도입 시 제약 | 마이그레이션 1~2개, 3개 기능·테스트·compose·chart·NetworkPolicy. 중 |

결정(2026-11-02, 담당자): **B. 부분 대체**. 기준은 "DB 저장과 함께 커밋·롤백되어야 하는 값은 PostgreSQL, 짧은 수명 값과 레플리카 간 fan-out은 Redis"다.

| 구분 | 대상 |
|---|---|
| PostgreSQL로 이전 | 분석 대화 일일 사용량, 관리자 대화 재처리 중복 차감 방지 표식 |
| PostgreSQL로 신규 구현(후속 미정) | 무료 플랜 미션 일일 한도(P13). 구현 이슈 미정이며 그 전까지 API 명세의 "core Redis 책임" 문구는 바꾸지 않는다 |
| Redis 유지 | 학생 기기 페어링 코드, 기기 등록·페어링 발급 rate limit, 알림 Pub/Sub `core:notifications:v1` |

- 근거 1: 분석 사용량은 이미 보호자·학생 행 잠금 트랜잭션 안에서 차감되므로 PostgreSQL 조건부 UPSERT로 동시성 요구를 같은 수준으로 충족하면서 롤백 불일치와 분산 원자성 제약을 함께 없앤다. 아직 구현되지 않은 미션 한도도 같은 패턴으로 만들면 Redis 의존 기능을 새로 늘리지 않는다
- 근거 2: 페어링·rate limit은 TTL·짧은 수명 데이터라 Redis에 자연스럽고, 남용 트래픽을 RDS 쓰기로 옮기지 않는다
- 근거 3: 알림 중계를 `LISTEN/NOTIFY`로 바꾸면 전용 연결·재연결 코드를 새로 만들어야 하고, 유실 특성은 같아 기능상 이득이 없다. 12/7 배포 전 위험이 가장 크다
- 남는 부담: Redis StatefulSet 운영 항목은 그대로다. 운영 항목 축소가 우선이 되면 C를 다시 검토하며, 이때 알림 리스너 구현과 다중 레플리카 검증을 먼저 별도 이슈로 진행한다

결정 반영과 후속 작업:

- [아키텍처](../design/architecture.md) 6장 사용 기술의 Redis 용도와 7.1 구현 결정 요약에 반영했다. 1.1 서비스 표(core_db, Redis)·1.6 SSE 다중 레플리카·4장 상태 저장소 배치는 Redis를 유지하므로 바꾸지 않았다
- 후속 구현 이슈(별도): 분석 사용량·재처리 표식 PostgreSQL 이전은 #225로 구현했다([아래](#분석-대화-사용량-db-이관-구현-225)). 미션 일일 한도 구현은 미정이다. 구현 전에 API 명세(P13 일일 한도 "core Redis 카운터 책임", #47 CONVERSATION 관리자 재처리의 Redis 표식·분산 원자성 문구)와 ERD의 Redis 보관 항목(요금제 사용 한도 일 단위 카운터)을 먼저 갱신하고 마이그레이션을 추가한다
- platform-data chart README의 "캐시·실시간 알림 중계" 표현은 실제 용도(페어링·rate limit·알림 중계)로 별도 정리한다 → #245에서 정리

### 분석 대화 사용량 DB 이관 구현 (#225)

위 대체안 표의 "새 일일 사용량 테이블 조건부 UPSERT" 대신, **새 테이블·마이그레이션 없이 기존 결제 사용 이력 `payment_premium_usage` 집계**로 구현했다. 유료 구독의 분석 시도는 이미 같은 트랜잭션에서 이 표에 `CONVERSATION` 행을 남기고 있었으므로(`PaymentAnalysisEntitlementProvider.recordAttempt`) 그 행 수가 곧 일 사용량이다. 구독이 없는 무료 경로는 행이 없지만 무료 상품은 분석 대화 0회(P13)라 기존 0 한도 차단으로 처리된다.

| 구분 | 변경 |
|---|---|
| 한도 판정 | `payment/service/ProductEntitlementService.reserve`가 보호자 잠금 안에서 같은 source 기존 행 확인 뒤, 오늘(KST 0시, `PaymentTransactions.today()` 기준) `CONVERSATION`·`RESERVED/USED` 행 수가 `limits.dailyConversations` 이상이면 `429 USAGE_LIMIT_REACHED`. 집계 쿼리는 `PaymentMapper.xml` `usageCountSince`(기존 `ix_payment_usage_refund(student_id,created_at,status)` 인덱스 사용) |
| Redis 제거 | `conversation/service/AnalysisUsageService`의 `CONSUME`·`CONSUME_RETRY` Lua 스크립트, `counterWindow`, `StringRedisTemplate` 의존 삭제. `consume(parent,child,source)` 하나가 0 한도·유효기간 확인 후 provider에 기록 |
| 호출 순서 정리 | `ConversationService.prepareFor`는 Redis 차감(기존 94행)과 메시지 저장 뒤 `recordAttempt`(기존 104행)를 따로 하던 것을 메시지 저장 전 `consume` 1회로 합쳤다. 리포트 설정 제안(#209 `ReportTemplateService.propose`)도 같은 두 호출을 `consume` 1회로 바꿨다 |
| 관리자 재시도 | `resumeAdminRetry`가 영속 요청 ID(`conversation_job_retry.id`)를 source ID로 `consume`. 이미 기록된 source는 `UNIQUE(kind,source_id)`의 기존 행을 재사용해 추가 차감·한도 재판정이 없다 |
| 문서 | API 명세 #41·#47 CONVERSATION 계약 문단, ERD Redis 보관 항목·#41·#47 절, 아키텍처 6장 저장소 행·7.1 #210 항목·#47 CONVERSATION 문단, 클래스 다이어그램 요금제 사용 한도, [#41 보고서](issue-41-analysis-conversations.md) 사용 한도 |

유지한 정책과 동작:

- 차감 정책: 새 질문·재시도마다 1회, 실패·취소·clarification도 차감(행은 즉시 `USED`), AI 호출 전 거부(권한·범위·진행 중·입력 오류)는 차감하지 않는다. 무료 0 한도는 대화 생성·질문 모두 429
- 동시성: 분석 접수는 보호자 행 잠금(`tx.locked(parent)`)과 학생 행 잠금(`ConversationService.access`) 안에서 집계와 INSERT를 한다. 같은 자녀의 접수는 직렬화되고, READ COMMITTED에서 잠금을 얻은 뒤 실행하는 집계는 앞 트랜잭션의 커밋 행을 본다
- 롤백 정합성: 차감 행은 메시지 저장·실행 선점과 같은 트랜잭션이라 함께 롤백된다. 6절 표에서 지적한 "차감 뒤 같은 트랜잭션 실패 시 Redis 카운트만 남는" 불일치와 "분산 원자 트랜잭션이 아니다" 제약이 없어졌다
- Redis 장애는 분석 대화에 영향이 없다. Redis는 페어링 코드·기기 등록 rate limit·알림 Pub/Sub에만 남는다
- 일 경계는 계속 KST 자정이다. 집계는 자녀 기준이며 같은 날 구독이 바뀌어도 합산한다(Redis 키도 자녀·일자 기준이었다)
- 배포 전환: 유료 시도는 이미 사용 이력 행이 있으므로 당일 사용량이 그대로 이어진다. 남은 `analysis:daily:v1:*`·`analysis:retry:v1:*` 키는 읽지 않으며 최대 2일 안에 만료된다

확인 필요 항목의 결정(2026-11-02, 담당자):

- `ANALYSIS_USAGE_UNAVAILABLE`: 더는 발생하지 않는다. API 명세 1.3에 없던 코드([audit](audit.md))라 문서화된 계약 변경은 아니다. 과거 작업 실행 기록 표시를 위해 `admin/domain/Operations.kt`의 안전 코드 목록에는 남겼다
- 관리자 재실행 130초 만료: Redis 표식 TTL 전제가 아니라 실행 만료(대화 RUNNING 고착 판정 `ConversationService.kt:82`와 같은 값)로 유지한다. API 명세에서 "표식 TTL보다 짧은" 전제 문구만 지웠다
- 무료 미션 3회·프리미엄 피드백 50회 한도(P13, 미구현): 이번 범위가 아니다. API 명세 2.2·4.1의 "core Redis 책임" 문구는 그대로 두고, 저장소와 문구는 해당 구현 이슈에서 정한다

검증:

- 테스트: `AnalysisUsageContractTest`(Redis 없이 provider만으로 `consume`, 0 한도 미기록, provider 부재 503), `ConversationPaymentIntegrationTest`(실제 provider: 30개 동시 접수 중 한도 2회만 차감, KST 자정 직전·`FAILED` 행 미집계, 초과 재시도 429, `analysis:*` Redis 키 없음), `AdminConversationRetryTest`(실제 provider·사용 이력으로 전환: 같은 요청 ID 재실행 1회 차감, 롤백된 선점은 차감도 롤백, 접수 후 한도 축소 시 실행 전 실패), `ConversationIntegrationTest`(원 질문·재시도 source가 서로 다른 2건)
- 실행: JDK 21(`eclipse-temurin:21-jdk`) 격리 Docker 컨테이너에서 `bash gradlew test bootJar --no-daemon --max-workers=1 --no-watch-fs --console=plain -Pkotlin.compiler.execution.strategy=in-process`. core 전체 **67클래스·438개** 통과, 실패·오류·생략 0, `bootJar` 성공. IntegrationTestSupport의 실제 PostgreSQL·Redis·RabbitMQ를 사용하고 AI·PG는 대역이다
- 미검증: 실제 AI·토스 연동, 브라우저 화면, 다중 레플리카 배포 환경의 동시성, 원격 CI
