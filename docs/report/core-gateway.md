# core 학습 프록시·SSE·대시보드·알림·분석 대화·이벤트 기록·포인트 (#38·#39·#40·#41·#44·#119·#168·#195·#208·#210·#225·#243·#286·#387·#389·#392)

계약은 [API 명세](../design/api-spec.md) 1.4·2.2·2.3·2.7·3.2, 구조는 [아키텍처](../design/architecture.md) 1.3·1.6.

## 1. 학생 미션 공개 API·멱등성 (#38)

- 공개 미션·시도 경로를 learning 내부 경로로 전달. 업무 검증·DB 조회는 learning 소유, core는 검증된 STUDENT 컨텍스트만 사용
- 학생 학년·시연 여부는 `StudentLearningContextService`(core 소유 `grade`·`is_demo` 조회)로 정해 `grade`·`demo` 쿼리로 전달. 공개 쿼리·위조 헤더는 근거로 쓰지 않음(미션 조회·시도 시작 공통)
- 서킷: Resilience4j(production 의존성) 최근 20건·최소 20건·실패율 50%·차단 30초·half-open 1건. 전송 오류·5xx만 실패로 집계, 4xx는 정상 HTTP 결과. HTTP 자동 재시도 없음. 일반 JSON 연결 2초·응답 30초
- 멱등성: 기존 `idempotency_record`만 사용. PostgreSQL 세션 advisory lock과 같은 auto-commit 연결에서 레코드를 읽고 쓰므로 이 Repository만 JDBC 사용. HTTP 동안 연결 1개를 보유하고 트랜잭션은 없음(풀 크기와 HTTP 타임아웃이 동시 처리 상한)
  - 동시 재요청 409 + `Retry-After`, 같은 계정의 경로·학생·본문 불일치 422
  - 확정 응답은 원문·필수 헤더·상태를 보관. 미확정·5xx·전송 실패는 같은 키로 learning 재호출. core 저장 실패는 503(learning 성공을 성공으로 가장하지 않음)
  - learning이 키의 UK·본문 대조·최초 응답 재구성·답변/판정 원자적 저장을 제공해야 두 DB 사이 중복 생성이 없음(core TTL 24시간 이후에도 learning UK 유지)
- 시도 상세(#195): core 공개 `GET /attempts/{attemptId}`는 `Cache-Control: no-store`, 웹도 상세·제출·마무리·돌아보기 후 재조회에 `cache: 'no-store'`. 초안 버전은 피드백·마무리·돌아보기 상태의 버전이 아니라서 상세 표현의 HTTP 캐시 검증자(ETag)로 쓰면 304로 상태 변경을 놓침. 초안 ETag/If-Match·409 계약은 그대로
- 일일 한도(P13): #387에서 구현(13절). 무료 하루 1개(당일 테마 문제 `THEME_DAY`, 2026-11-06 결정)를 #210 결정대로 PostgreSQL `mission_daily_usage`로 집계. learning의 신규 `201`·이어하기 `200`을 그대로 전달하고 `201`만 집계·한도 도달 시 신규 생성만 차단

## 2. 피드백 SSE (#39)

- 피드백 조합은 #38의 `LearningProxyService`·`LearningClient`를 그대로 쓰고 read timeout만 80초. `SseEmitters`는 virtual task·15초 heartbeat·90초 연결·정리만 담당, 전송 실패·종료 콜백은 heartbeat만 취소(learning 작업 유지). 사용자 컨텍스트는 명시적으로 전달·정리
- learning DONE(HELD 포함) → `result`, RUNNING → `status`, learning 오류 → `error`, 이후 `done`. core는 판정 전이·리스·실패 재실행 캐시를 구현하지 않음
- 서킷 분리: 일반 JSON은 `learning-json`, 피드백은 `learning-feedback`. 전송 실패·시간 초과·계약된 Problem Details가 아닌 5xx만 실패로 셈. `application/problem+json`에 비어 있지 않은 `code`가 있으면 업무 실패(`error` 이벤트)로 전달하고 서킷 실패로 다시 세지 않음(learning의 AI 서킷과 이중 차단 방지)
- 전송·종료 상호 배제는 `ReentrantLock`(synchronized 안의 블로킹 전송이 virtual thread carrier를 고정하지 않도록, JFR `jdk.VirtualThreadPinned`로 확인)
- 스트림 시작 전 인증 DB 실패는 `PublicAuthFilter`의 503 `AUTH_UNAVAILABLE`
- 종료 예산: preStop + Spring/Tomcat 종료 + executor 85초·timer 5초 + 여유보다 긴 `terminationGracePeriodSeconds` 필요. 앱 chart의 local core는 `terminationGracePeriodSeconds: 180`(`environments/local/core-service.yaml`). 실제 롤링 종료 검증은 미실시

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

## 5. 분석 대화 계약 (#41·#167)

계약 원본은 [API 명세](../design/api-spec.md) 5.10, 저장 규칙은 [ERD](../design/erd.md) 3.2.1.

- core가 conversation/message/evidence UUID 생성, AI messageId는 신뢰하지 않음
- 기본 기간은 Asia/Seoul 오늘 포함 7일. scope를 본문에 명시하면 해당 범위에 대한 사용자 확인으로 취급. 자녀 변경은 새 대화, 기간 변경은 `scope.changed=true`. 이력은 정확히 같은 자녀·기간의 완료 메시지 최근 10쌍(20 turn `{role,text}`)만 전달, 질문 1,000자
- P25(#392): 일일 리포트에서 만든 대화는 리포트 ID·판을 저장해 그날로 고정하고, 메시지마다 core가 report에서 그 판을 읽어 ai 요청에 넣는다(범위 변경 없음, 다른 날은 새 대화)
- SSE `status → delta* → result | clarification | error → done`. delta는 저장하지 않음. result는 scope 일치·verification 플래그 true·source 및 근거 식별자 형식을 검사(숫자/인용 대조·TEMPLATE 생성은 AI 책임). `verification.contentAllowed`가 명시되어 false/잘못된 형식이면 확정하지 않음(값이 없는 기존 두 플래그 계약은 보존). done 이후 DB 확정 후 공개. EOF·잘못된 순서·중복 terminal은 실패
- clarification은 AI `{reason,message,current}`를 공개 `{question,options:[],reason,current}`로 변환. 사용자에게 없는 자녀·기간 선택지를 만들어 주지 않음
- AI의 answerVersion이 null이면 현재 learning 응답의 실제 버전 사용(ID/기간 검사 유지). 시작일 이전 최초 답변은 evidence의 학생/시도/답변/버전·종료일 검증 뒤 해당 시도가 기간별 attempts 목록에 실제 포함되는지 확인
- 시간: 첫 AI 이벤트 20초, 전체 120초(heartbeat 15초는 첫 응답에 포함하지 않음). 연결 종료·권한 소실·삭제·시간 초과 시 HTTP body를 닫고 작업 thread를 interrupt. 실패는 같은 message 행 FAILED, retry_count로 시도 fencing. 저장 확정 이후 연결 종료는 완료 메시지를 FAILED로 되돌리지 않음
- 보호자 계정 → 학생 → 대화 잠금으로 시작/확정/취소 직렬화, 동시에 하나의 RUNNING만. 삭제된 행은 UPDATE만 하므로 재생성하지 않음. 원문 전송은 emitter lock → DB 잠금 순서로 삭제와 직렬화, 외부 AI/learning HTTP는 트랜잭션 밖
- 사용 한도: 대화 생성은 권한/0 한도 확인만, 새 질문·재시도마다 AI 호출 직전 차감. 실패·취소·clarification도 차감, AI 호출 전 거부는 차감하지 않음. 저장은 `payment_premium_usage` KST 일자 집계(6장 #225)
- 권한 공급: `conversation.service.AnalysisEntitlementProvider` 포트(`entitlement(parentId, childId)` → productId·dailyConversations·validUntil)는 payment 구현([payment](payment.md) 5장). 미연결·음수·누락·만료는 503 `PAYMENT_ENTITLEMENT_UNAVAILABLE`, `conversationEnabled=false`(환불 진행 포함)는 한도와 무관하게 차단
- 내부 AI 호출 `POST /internal/analysis/stream {conversationId,messageId,question,scope:{studentId,from,to},history}`. 내부 토큰·검증된 PARENT context를 InternalRestClientFactory로 전달하고 studentScope는 대상 하나로 축소. 내부 result scope는 studentId, 공개 응답은 childId
- 근거는 ID만 저장. `LearningRecordService`로 `/internal/records/evidence?answerIds=...`를 조회하며 현재 권한/삭제/ID 재검사. 삭제된 근거는 `available:false`만 표시하고 다른 원문으로 대체하지 않음
- 대화 목록은 본인·현재 연결 자녀의 최신 100개(답변 본문 없음), 상세는 소유 conversationId로. 구독 만료 후에도 소유/연결/동의가 유효하면 저장된 이력 조회 가능, 신규 분석은 상품 권한 재검사
- TEMPLATE fallback.reason은 COMPLETED 행 failure_code에 보존하고 공개 실패 코드는 FAILED에서만 노출
- 하위 호출 서킷(#167): AI 전체 스트림 집계. OPEN은 기존 AI_UNAVAILABLE/FAILED, 사용자 취소·core 소비자 실패는 집계 제외, 차감은 보존. 최근/최소 20건·실패율 50%·30초 차단·half-open 1건
- 재현: `scripts/verify_analysis_evidence.py`(실제 core·learning JAR로 근거 조회·타 보호자 404·위조 messageId 404·학생 범위 위조 403·삭제 후 `available:false` 확인)

- 정정 안내(#244): 대화 상세의 답변별 `correctionNotice`. 기록과 판단은 [support-admin](support-admin.md) 「정정 영향 판정과 표시」

## 6. Redis 사용 필요성과 PostgreSQL 대체 비교 (#210)

10/29 [멘토링](planning-decisions.md#1-1029-오프라인-멘토링-결정후속)의 재검토 권고에 따라 core의 Redis 사용처와 PostgreSQL 대체안을 비교한다. 담당자 결정은 **B. 부분 대체**(2026-11-02, [선택지와 결정](#선택지와-결정))이며, 대체 구현은 별도 이슈로 진행한다. 이 절 작성 시 코드·설정·계약·마이그레이션은 바꾸지 않았다. 부하·비용 수치는 실측이 없어 모두 추정이다. 코드 위치는 `backend/core-service/src/main/kotlin/com/sagomungchi/core/` 기준이다.

### 사용처와 장애 시 동작

#210 검토 당시 코드 기준이다. 분석 대화 일일 사용량·관리자 재처리 중복 차감 행은 #225 이후 PostgreSQL `payment_premium_usage`로 옮겨져 Redis를 쓰지 않는다([#225 구현](#분석-대화-사용량-db-이관-구현-225)).

| 사용처 | 코드 위치 | Redis가 보장하는 성질 | Redis 장애 시 현재 동작 |
|---|---|---|---|
| 학생 기기 페어링 코드 | `account/repository/PairingRepository.kt:12-17`, `account/service/StudentAuthService.kt:41-58` | 해시 키 `SET NX`·10분 TTL, Lua `GET`+`DEL` 1회 소비 | `DataAccessException` → 503 `STUDENT_AUTH_UNAVAILABLE`(`StudentAuthService.kt:121,127`). 등록된 기기의 프로필·PIN 로그인은 DB만 사용해 영향 없음(`:69-89`) |
| 기기 등록·페어링 발급 rate limit | `PairingRepository.kt:18,21`, `StudentAuthService.kt:42,55,120` | Lua `INCR` 후 첫 증가에만 `EXPIRE 600`(10분 고정 창, 기본 20회 `account/config/StudentDeviceProperties.kt:9`) | 한도 확인이 먼저라 발급·등록 모두 위와 같은 503 |
| 분석 대화 일일 사용량 | `conversation/service/AnalysisUsageService.kt:26-32,43-47,57-63` | Lua 확인+증가 원자 처리, 키 `analysis:daily:v1:{childId}:{KST 일자}`, `EXPIREAT` 다음 KST 자정+1일 | 503 `ANALYSIS_USAGE_UNAVAILABLE`(`:30`). 대화 생성·조회는 권한 확인만 해 영향 없음(`conversation/service/ConversationService.kt:43`) |
| 관리자 대화 재처리 중복 차감 방지 | `AnalysisUsageService.kt:33-39,48-56`, `ConversationService.kt:153` | 요청 ID 표식 `analysis:retry:v1:{requestId}` 확인·증가·표식 저장을 한 스크립트로 처리 | 같은 503, 재처리 실행 실패 |
| 알림 다중 레플리카 SSE 중계 | `notification/messaging/NotificationRedisPublisher.kt:17-26`, `notification/config/NotificationRedisConfiguration.kt:13-18`, `notification/consumer/NotificationRedisSubscriber.kt:14-17`, `notification/service/NotificationStreams.kt:29-33` | 채널 `core:notifications:v1` fan-out(at-most-once, 구독자 0명도 발행 성공), 커밋 후 발행 | 발행 예외 → `FAILED`·`REDIS_PUBLISH_FAILED`(`notification/service/NotificationDeliveryService.kt:12`). 알림 행·리포트 상태는 유지되고 목록 재조회로 복구. 관리자 재처리(`admin/service/OperationRetryService.kt:59`)도 같은 publisher 사용 |
| 무료 플랜 미션 일일 한도(미구현) | 설계만 존재([API 명세](../design/api-spec.md) 2.2 P13·4.1 `/internal/missions/{id}/attempts`) | #210 전 설계는 core Redis 카운터, 현재 설계는 PostgreSQL `mission_daily_usage`(무료 하루 1개, #387). 신규 `201`만 집계 | 코드 없음 |

전수 확인 결과(`StringRedisTemplate`·`RedisTemplate`·`RedisConnectionFactory`·`@Cacheable`·`spring.data.redis` 검색):

- 운영 코드의 Redis 접근은 위 4개 파일뿐이다. `@Cacheable`·`CacheManager`·세션 저장소 사용은 없어 Redis를 **조회 캐시로는 쓰지 않는다**. learning·ai·scoring·report 서비스는 Redis를 쓰지 않는다
- 연결은 `application.yml:21-27`(연결·명령 timeout 2초). readiness 그룹은 `readinessState,db,rabbit`(`application.yml:57-58`)으로 Redis를 포함하지 않아 Redis 장애 시 Pod는 Ready를 유지하고 기능별로만 503이 난다
- 배포·실행 설정: `compose.yaml:69-77,135-137`, platform-data chart `templates/redis.yaml`(replicas 1 `:11`, AOF·`maxmemory`·`noeviction` `:44-49`), `values.yaml:43-53`, local `environments/local/platform-data.yaml:42-52`, `environments/local/core-service.yaml:30,66`, NetworkPolicy `policies/local/platform.yaml:61`
- 테스트·검증: `IntegrationTestSupport.kt:38,61-62` Redis 컨테이너, `scripts/verify_*.py`, `scripts/report_integration/compose.yaml:29-60`
- 문서 표현 차이: [아키텍처](../design/architecture.md) 6장 사용 기술 표의 "SSE 중계·캐시", platform-data chart README의 "캐시·실시간 알림 중계"는 실제 사용(캐시 없음)과 달랐다. #210 결정 후 정리함(#245)
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
- 테스트·로컬: 전부 대체하면 compose·`IntegrationTestSupport`·검증 스크립트의 Redis 컨테이너가 빠진다. 과거 검증에서 Redis 최초 연결 지연으로 인한 테스트 실패가 있었다

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
| PostgreSQL로 신규 구현(후속 미정) | 무료 플랜 미션 일일 한도(P13, 2026-11-06 결정으로 하루 1개). 구현 이슈 #387. 설계는 core `mission_daily_usage`(ERD 3.6) |
| Redis 유지 | 학생 기기 페어링 코드, 기기 등록·페어링 발급 rate limit, 알림 Pub/Sub `core:notifications:v1` |

- 근거 1: 분석 사용량은 이미 보호자·학생 행 잠금 트랜잭션 안에서 차감되므로 PostgreSQL 조건부 UPSERT로 동시성 요구를 같은 수준으로 충족하면서 롤백 불일치와 분산 원자성 제약을 함께 없앤다. 아직 구현되지 않은 미션 한도도 같은 패턴으로 만들면 Redis 의존 기능을 새로 늘리지 않는다
- 근거 2: 페어링·rate limit은 TTL·짧은 수명 데이터라 Redis에 자연스럽고, 남용 트래픽을 RDS 쓰기로 옮기지 않는다
- 근거 3: 알림 중계를 `LISTEN/NOTIFY`로 바꾸면 전용 연결·재연결 코드를 새로 만들어야 하고, 유실 특성은 같아 기능상 이득이 없다. 12/7 배포 전 위험이 가장 크다
- 남는 부담: Redis StatefulSet 운영 항목은 그대로다. 운영 항목 축소가 우선이 되면 C를 다시 검토하며, 이때 알림 리스너 구현과 다중 레플리카 검증을 먼저 별도 이슈로 진행한다

결정 반영과 후속 작업:

- [아키텍처](../design/architecture.md) 6장 사용 기술의 Redis 용도와 7.1 구현 결정 요약에 반영했다. 1.1 서비스 표(core_db, Redis)·1.6 SSE 다중 레플리카·4장 상태 저장소 배치는 Redis를 유지하므로 바꾸지 않았다
- 후속 구현 이슈(별도): 분석 사용량·재처리 표식 PostgreSQL 이전은 #225로 구현했다([아래](#분석-대화-사용량-db-이관-구현-225)). 미션 일일 한도는 #387로 구현한다. API 명세(2.2·1.3)와 ERD 3.6은 이미 PostgreSQL `mission_daily_usage` 기준으로 갱신됨
- platform-data chart README의 "캐시·실시간 알림 중계" 표현은 실제 용도(페어링·rate limit·알림 중계)로 별도 정리한다 → #245에서 정리

### 분석 대화 사용량 DB 이관 구현 (#225)

위 대체안 표의 "새 일일 사용량 테이블 조건부 UPSERT" 대신, **새 테이블·마이그레이션 없이 기존 결제 사용 이력 `payment_premium_usage` 집계**로 구현했다. 유료 구독의 분석 시도는 이미 같은 트랜잭션에서 이 표에 `CONVERSATION` 행을 남기고 있었으므로(`PaymentAnalysisEntitlementProvider.recordAttempt`) 그 행 수가 곧 일 사용량이다. 구독이 없는 무료 경로는 행이 없지만 무료 상품은 분석 대화 0회(P13)라 기존 0 한도 차단으로 처리된다.

| 구분 | 변경 |
|---|---|
| 한도 판정 | `payment/service/ProductEntitlementService.reserve`가 보호자 잠금 안에서 같은 source 기존 행 확인 뒤, 오늘(KST 0시, `PaymentTransactions.today()` 기준) `CONVERSATION`·`RESERVED/USED` 행 수가 `limits.dailyConversations` 이상이면 `429 USAGE_LIMIT_REACHED`. 집계 쿼리는 `PaymentMapper.xml` `usageCountSince`(기존 `ix_payment_usage_refund(student_id,created_at,status)` 인덱스 사용) |
| Redis 제거 | `conversation/service/AnalysisUsageService`의 `CONSUME`·`CONSUME_RETRY` Lua 스크립트, `counterWindow`, `StringRedisTemplate` 의존 삭제. `consume(parent,child,source)` 하나가 0 한도·유효기간 확인 후 provider에 기록 |
| 호출 순서 정리 | `ConversationService.prepareFor`는 Redis 차감(기존 94행)과 메시지 저장 뒤 `recordAttempt`(기존 104행)를 따로 하던 것을 메시지 저장 전 `consume` 1회로 합쳤다. 리포트 설정 제안(#209 `ReportTemplateService.propose`)도 같은 두 호출을 `consume` 1회로 바꿨다 |
| 관리자 재시도 | `resumeAdminRetry`가 영속 요청 ID(`conversation_job_retry.id`)를 source ID로 `consume`. 이미 기록된 source는 `UNIQUE(kind,source_id)`의 기존 행을 재사용해 추가 차감·한도 재판정이 없다 |
| 문서 | API 명세 #41·#47 CONVERSATION 계약 문단, ERD Redis 보관 항목·#41·#47 절, 아키텍처 6장 저장소 행·7.1 #210 항목·#47 CONVERSATION 문단, 클래스 다이어그램 요금제 사용 한도, 이 문서 5장 사용 한도 |

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
- 무료 미션 하루 1개(#387)·프리미엄 피드백 50회 한도(P13, 미구현): 이번 범위가 아니다. 무료 미션은 `mission_daily_usage`로 정했고 피드백 한도 저장 방식은 구현 이슈에서 정한다

검증:

- 테스트: `AnalysisUsageContractTest`(Redis 없이 provider만으로 `consume`, 0 한도 미기록, provider 부재 503), `ConversationPaymentIntegrationTest`(실제 provider: 30개 동시 접수 중 한도 2회만 차감, KST 자정 직전·`FAILED` 행 미집계, 초과 재시도 429, `analysis:*` Redis 키 없음), `AdminConversationRetryTest`(실제 provider·사용 이력으로 전환: 같은 요청 ID 재실행 1회 차감, 롤백된 선점은 차감도 롤백, 접수 후 한도 축소 시 실행 전 실패), `ConversationIntegrationTest`(원 질문·재시도 source가 서로 다른 2건)

## 7. 관리자 대화 재처리 시각 출처 통일 (#286)

#284 병합 후 `AdminConversationRetryTest`에서 `ck_conversation_job_retry_order`(V19, `started_at >= accepted_at`) 위반이 간헐적으로 났다. 접수 시각 `accepted_at`은 앱 `Instant.now()`, 선점·종료 시각 `started_at`·`finished_at`은 DB `CURRENT_TIMESTAMP`라 앱 시계가 DB보다 앞서면 순서가 역전됐다. 이슈의 두 안 중 안 A(DB 시계로 통일)를 택했다. V19 CHECK와 기존 마이그레이션은 바꾸지 않았다.

| 위치 | 변경 |
|---|---|
| 접수 `insert` (#287) | `accepted_at`을 매퍼에서 DB `CURRENT_TIMESTAMP`로 기록. 서비스가 만드는 행의 `acceptedAt`(`Instant.now()`)은 INSERT에 쓰이지 않는 자리값이다 |
| 202 응답 `acceptedAt` | 변경 없음. 접수 직후 `find`로 다시 읽은 행을 응답·이벤트에 쓰므로 이미 DB 저장값이다 |
| 선점 전 만료 판정 | 서비스 `claim`이 앱 `Instant.now()-130초`와 DB `accepted_at`을 비교하던 것을 매퍼 `claimable`로 바꿨다. `claim` UPDATE와 같은 조건·같은 트랜잭션 `CURRENT_TIMESTAMP`를 쓰므로 사전 판정과 UPDATE가 어긋나지 않는다 |
| `pending`·`stale`·`claim`·`finish` | 원래 DB 시계 기준이라 변경 없음 |

만료 판정까지 바꾼 이유: 시계 차이가 수 ms여도 130초 경계 근처에서는 앱 판정이 "유효", DB `claim`이 "만료"로 갈릴 수 있다. 이때 `resumeAdminRetry`(사용량 차감 포함)를 지난 뒤 `check(requests.claim(...))`가 예외로 트랜잭션 전체를 롤백했다. 반대로 앱 시계가 앞서면 DB 기준으로 아직 유효한 요청을 건너뛰었다. 어느 쪽이든 데이터 손상은 없고 `stale` 회수로 정리되지만, 판정 기준을 하나로 두면 이런 경계 예외가 사라진다.

검증: `AdminConversationRetryTest`에 앱 시각이 DB보다 5초 앞선 행으로 선점·종료(`started_at >= accepted_at`, `finished_at >= started_at`) 회귀 테스트(#287 추가, 이번에 종료 확인 보강)와 DB 기준 131초 지난 요청은 예외 없이 선점되지 않고 `QUEUED`·실행 기록·차감 없음으로 남는 테스트를 두었다.

## 8. 리포트용 학생 별명 내부 조회 (#119)

`GET /internal/students/{studentId}/profile` → `200 {studentId, nickname}`, `Cache-Control: no-store`. 호출자는 report-worker([report](report.md) 10장).

| 조건 | HTTP / code |
|---|---|
| 내부 토큰 누락·불일치, Bearer만 전달 | 401 UNAUTHENTICATED |
| SYSTEM 외·역할 누락·학생 scope 누락/불일치 | 403 FORBIDDEN |
| 잘못된 UUID (유효 내부 토큰 사용) | 400 VALIDATION_FAILED |
| 미존재·ACTIVE 외 상태 | 404 NOT_FOUND |
| 예상하지 못한 조회 실패 | 500 INTERNAL_ERROR |

- 비활성이라는 이유로 임의 INACTIVE enum을 만들지 않으며 삭제 진행·완료 모두 404(RECORDS 완료 뒤에도 DELETION_REQUESTED 유지하는 #45 정책)
- `InternalAuthFilter` → `InternalStudentProfileController` → `InternalStudentProfileService` → `ChildManagementRepository.profile`. 서비스가 SYSTEM 확인 후 `UserContext.requireStudent`로 scope 검사. 기존 LinkedStudent 전체를 노출하지 않고 전용 DTO로 studentId·nickname만. 별명·토큰·학생 UUID를 로그에 남기지 않음
- report는 403·404를 생성 실패로 처리하고 UUID·빈 문자열·임의 별명으로 대체하지 않음. AI 요청 전 별명 가림은 report `NarrativeGenerator.scrub`

## 9. RabbitMQ 발행·소비 기록 (#208)

10/29 멘토링 의견에 따라 "이 메시지가 발행됐는지, 브로커를 거쳤는지, 누가 처리했는지"를 PostgreSQL에서 조회하도록 보완(11/1 결정). 기존 `outbox_event` + 작업 상태 + #131·#132 복구가 이미 재발행 역할을 하므로 작업 테이블에 컬럼을 추가하지 않고, 빠진 "통합 조회"와 "보존 정책"만 추가.

| 메시지 | 생산 → 소비 | 발행 기록 | 브로커 전달 | 소비 기록 |
|---|---|---|---|---|
| report.generate | core → report | core outbox_event | event_log | core report_job 상태, report weekly_report.job_id |
| report.started/completed/failed | report → core | report outbox_event (실패·격리 포함) | event_log | core processed_event |
| student.deleted | core → learning·report | core outbox_event | event_log | learning·report processed_event, core 완료 보고 행 |
| model.version.activated | core → ai·scoring 모든 Pod | core outbox_event | event_log | 기록 없음 (아래 4) |
| llm.usage.recorded | ai·scoring → core | 없음 | event_log | core llm_usage(event_id) |

1. **core 감사 큐 + `event_log`**: 큐 `core.event.audit`(재시도 1·5·15분, DLQ 포함)을 업무 routing key마다 바인딩. `EventAuditConsumer`가 봉투의 id·type·source·subject·time과 수신 시각만 저장(payload·원문 미저장), 같은 id는 `ON CONFLICT DO NOTHING`
2. **`#` 와일드카드 미사용**: report 발행자는 `mandatory=True`로 unroutable 메시지를 실패로 보고 #131 재시도·격리를 적용하는데, `#`에 바인딩하면 잘못된 routing key도 성공으로 처리됨. 업무 바인딩 키마다 감사 바인딩이 있는지 `RabbitDefinitionsTest`가 검사
3. **ai·scoring DB 신설 안 함**: 브로커에 도달한 발행은 event_log에 남고, 브로커 미연결·발행 실패 건은 서비스 로그(`이벤트 발행 실패`)로만 확인
4. **model.version.activated 소비는 예외**: 모든 Pod가 임시 큐로 받아 메모리 버전을 교체하며 DB가 없음. 기동·재연결 때 core snapshot 재조회로 누락을 복구하고 적용 전 readiness false
5. **보존 90일**: 발행 완료 `outbox_event`, `processed_event`, `event_log`를 90일 뒤 1시간 주기로 삭제(미발행·격리 outbox 행, `llm_usage`·`job_execution`은 유지). core `EventRetentionCleanup`, learning `ProcessedEventCleanupScheduler` → `ProcessedEventCleanupService`(`deleted_student` 유지), report worker cleanup 루프 `deletion/service.py` `prune_event_records`(`report_deletion_guard` 유지). 설정 `app.messaging.event-retention-days`·`EVENT_RETENTION_DAYS`(기본 90). 조건부 DELETE라 ShedLock 없음
6. **학생 식별자**: event_log.subject에 학생 UUID가 들어갈 수 있으나 payload·원문은 없음. 학생 삭제 시 즉시 지우지 않고 90일 보존 후 삭제

- 마이그레이션: core `V20__event_log_and_retention.sql`, learning `V8__processed_event_retention_index.sql`, report Alembic `20261102_05`(정리용 인덱스). RabbitMQ `definitions.json`에 큐 5개·바인딩 8개 추가(기존 환경은 definitions 재적용 필요), 관리자 큐 현황은 30개 큐
- 남은 누락: ai·scoring 발행 실패 건은 PostgreSQL에 남지 않음(서비스 로그로 확인, 11절). core outbox 실패 횟수·오류 코드·격리는 #243에서 보완(11절)

```sql
-- 특정 이벤트의 발행(core)·브로커 전달·core 소비
SELECT l.event_id, l.event_type, l.source, l.event_time, l.received_at,
       o.published_at, p.processed_at, u.occurred_at AS usage_occurred_at
FROM event_log l
LEFT JOIN outbox_event o ON o.id = l.event_id
LEFT JOIN processed_event p ON p.event_id = l.event_id
LEFT JOIN llm_usage u ON u.event_id = l.event_id
WHERE l.event_id = :event_id;

-- core가 발행했으나 감사 큐에 도달하지 않은 이벤트
SELECT o.id, o.event_type, o.published_at
FROM outbox_event o LEFT JOIN event_log l ON l.event_id = o.id
WHERE o.published_at IS NOT NULL AND l.event_id IS NULL;

-- 유형별 최근 24시간 전달 건수
SELECT event_type, count(*) FROM event_log
WHERE received_at > now() - interval '1 day' GROUP BY event_type;
```

## 10. 레이어·예외 경계 (#168·#249·#250·#251·#314)

아키텍처 2.1·2.2 위반을 [점검 기록](audit.md)의 A3·A4·A8~A10에서 찾아 정리. 응답(code·status·본문)과 API·이벤트 계약은 변경 없음.

### domain 예외 (#168·#249)

- domain은 Spring 타입을 쓰지 않음. 각 서비스 `_common/exception/DomainException(kind, code, title, detail)`과 `ErrorKind`(core `INVALID·NOT_FOUND·CONFLICT`, learning `INVALID·CONFLICT·UNPROCESSABLE`)
- 상태 변환은 `_common/exception/ErrorStatus.kt`의 `statusOf(kind)` 한 곳, `GlobalExceptionHandler.handleDomain`이 같은 Problem Details 형식으로 응답. `errorInfoOf(Throwable)`(+`httpStatusOf`·`errorCodeOf`)가 `BusinessException`·`DomainException`을 같게 다룸. `BusinessException`은 application·presentation 전용
- domain 예외가 도달하는 catch 지점(core `AnalysisStreamService`, `ConversationRetryWorker`, `OperationRetryService` 대화 분기, `PublicAuthFilter`, learning `AdminMissionController` 게시 누락)은 `errorInfoOf`·`statusOf`로 처리. `BusinessException` 하위 클래스 전용 처리기는 `ex.status` 유지
- service 테스트는 던진 층과 관계없이 `httpStatusOf`·`errorCodeOf`로 HTTP 상태·code를 계속 확인(#169의 "별도 domain 예외를 두면 처리기·테스트가 갈림" 걱정을 공통 함수로 해소)

### 기타 경계 (#168)

| 위반 | 정리 |
|---|---|
| `payment/domain/Payments.kt`가 Jackson `JsonNode`·`@JsonIgnore` 사용 | `_common/json/JsonObject`(프레임워크 없는 `Map<String, Any?>` 값 타입, Jackson은 `JsonObjectJsonComponent`, MyBatis는 `JsonObjectTypeHandler`를 이 타입에만 등록). `Any`·`Map` 전체 등록 금지 규칙([db-dev-guide](db-dev-guide.md) 5장) 때문 |
| PG 키(cancelKey) 노출 위험 | `payment/controller/PaymentResponses.kt`의 `RefundRequestResponse`(cancelKey 없음)·`PaymentViewResponse`를 모든 결제 응답과 멱등 저장본이 직렬화. `Payment`·`RefundRequest`에 키 없는 `toString` |
| `usage/service` → `usage.consumer.LlmUsageRecorded` | `usage/domain`으로 이동 |
| `payment/client/PremiumUsageClient` → `PaymentTransactions.unavailable` | client 안 `unavailable`(503 `REFUND_USAGE_UNAVAILABLE`) |
| `NotificationRedisSubscriber`가 Infrastructure에서 service 호출 | `notification/consumer`로, 구독 연결은 `notification/config` |

service에서 Jackson `convertValue`를 쓰는 것은 기존 `treeToValue`·`valueToTree` 자리 그대로(새로 늘리지 않음).

### 알림 발행·결과 기록 분리 (#250)

- `NotificationRedisPublisher.publish(value): Boolean`은 Redis 발행만(`true` = Redis가 받음, 구독자 0명도 성공)
- 새 `notification/service/NotificationDispatchService.dispatch(value)`가 `@TransactionalEventListener(AFTER_COMMIT)`로 커밋 후 이벤트를 받아 발행 → `delivery.record(id, failed)`. 기록 실패는 로그만 남기고 던지지 않음. 관리자 재처리 `NotificationRetryService.deliver`도 `dispatch` 호출
- 프로세스 안 이벤트를 service가 받는 것은 아키텍처 2.1이 금지하지 않음(설계에 service 리스너와 consumer 리스너 사례가 모두 있어 이슈가 정한 위치를 따름)

### 기능 간 controller·config 참조 제거 (#251)

| 항목 | 내용 |
|---|---|
| 요청 속성 상수 | `_common/security/RequestAttributes.IDENTITY`(값 `sagomungchi.identity` 그대로), `AuthController.IDENTITY` 제거 |
| `PublicAuthFilter` | `_common/security` → `account/controller`, 등록은 `account/config/AuthConfig` |
| PIN 실패 한도 | guardianship `PinRules.FAILURE_LIMIT = 5`(정책 고정값). `app.student-device.pin-failure-limit` 설정 삭제 |
| learning 공유 응답 DTO | `MissionResponse`·`MissionListItemResponse`·`AnswerItem`을 `_common/web/SharedResponses.kt`로. 기능 타입 없이 열거값은 이름 문자열, `Choice`·`Category`는 같은 모양의 `OptionResponse`, 피드백은 타입 인자 `AnswerItem<F>`. domain → DTO 변환은 쓰는 기능 controller의 companion 확장 `from`(매핑 중복 허용), `SharedResponsesJsonTest`가 세 변환의 JSON 동일성을 고정 |

### 멱등 키 정리 진입점 (#314)

- 감사 A21: `_common/web/IdempotencyService.kt`의 `IdempotencyCleanup`(`@Scheduled`)이 scheduler 패키지 밖에 있었음. #278 예외는 `_common/messaging`(`EventAuditConsumer`·`EventRetentionCleanup`·`OutboxRelay`)만 해당
- 결정: `_common` 예외 목록을 늘리지 않고 Presentation `scheduler`로 이동. 기능 소유자가 없는 공통 테이블(`idempotency_record`)이라 `_common/scheduler/IdempotencyCleanupScheduler`에 두고, 삭제는 기존 `IdempotencyService.deleteExpired` → `IdempotencyRepository.deleteExpired` 그대로
- 동작 변경 없음: 설정 키 `app.web.idempotency-cleanup-interval`(기본 1시간)·첫 실행 지연 1시간 유지. 만료 행 조건부 DELETE라 ShedLock 없이 레플리카 중복 실행 안전. `IdempotencyCleanupSchedulerTest`가 만료 행만 지우고 유효·진행 중 키는 남기는지 확인

## 11. core Outbox 실패 격리 (#243)

#208 9절 "남은 누락"(core outbox 실패 횟수·오류 코드 미저장, 영구 실패 1건이 뒤 발행 전체 차단) 해소. report #131([report.md 11절](report.md#11-outbox-실패-격리와-학생별-발행-순서-131))의 컬럼·격리 기준 재사용, #166 구조(발행·confirm은 DB 트랜잭션 밖, 기록만 짧은 트랜잭션) 유지. API·이벤트 계약 변경 없음.

- **순서**: `outbox_event.subject`(학생 UUID, `model.version.activated`는 모델 버전 id)별 미발행 선두만 조회. 선두가 백오프·격리 중이면 같은 subject 뒤 행은 선택하지 않고 다른 subject는 계속 발행. 같은 subject 연속 이벤트는 릴레이 주기(1초)당 1건
- **발행 단위**: 이벤트마다 `send` + `waitForConfirmsOrDie`(5초) 후 짧은 트랜잭션으로 `published_at` 기록. 기존 100건 일괄 confirm은 1건 실패 시 배치 전체가 매 주기 재시도되어 실패 이벤트를 구분할 수 없었음
- **재시도·격리**: 1·2·3번째 실패는 1·5·15분 뒤 재시도, 4번째 실패에 `quarantined_at` 기록(#131 동일). 증가·다음 시각·격리 판단은 조건부 UPDATE 1문장, 이미 발행·삭제된 행은 되살리지 않음
- **오류 코드**: `BROKER_UNAVAILABLE`(연결 실패) · `PUBLISH_TIMEOUT`(confirm timeout) · `PUBLISH_FAILED`(nack·그 외)만 저장, DB CHECK. 원문 예외·payload·subject는 DB·로그에 남기지 않음. 재시도 예정은 WARN, 격리는 ERROR `Outbox quarantined: id type code`
- **주기 중단**: `BROKER_UNAVAILABLE`·`PUBLISH_TIMEOUT`이면 그 1건만 기록하고 주기 종료. 남은 이벤트도 같은 결과일 가능성이 높고, 건당 5초 대기가 쌓이면 ShedLock `lockAtMostFor` 1분을 넘김. 장애 중에는 주기마다 첫 선두만 실패 횟수를 소모
- **confirm 후 기록 실패**: 발행 실패로 분류하지 않음. 다음 주기에 같은 id 재발행, 소비자 멱등 처리로 흡수(아키텍처 1.6)
- **마이그레이션**: core `V27__outbox_failure_quarantine.sql`. report와 같은 7개 컬럼, 카운터는 기존 행만 0(영구 DEFAULT 없음, insert에서 0 명시). 인덱스 `(created_at) WHERE published_at IS NULL` → `(subject, created_at, id) WHERE published_at IS NULL`. gitops 로컬 core 마이그레이션 리비전 v26 → v27(`test_core_migration_versions.py`)
- **재처리**: 관리자 API·#47 화면 노출 없음, 신뢰된 운영 환경에서 core DB 권한으로 아래 SQL 실행. 격리된 미발행 행만 조건부 갱신(0행이면 이미 발행·삭제·재처리됨). id·payload·순서 위치 유지, 실패 카운터·백오프 초기화, `manual_retry_count`·`last_requeued_at` 기록. 관리자 작업 재처리(#47·#152, 새 jobId)와 달리 이미 만든 이벤트 전달만 다시 시도
- **ai·scoring**: #208 결정 3 유지. DB를 두지 않고 발행 실패는 서비스 로그(`이벤트 발행 실패`)로 확인. 브로커 장애 시 core로 실패를 전달할 경로도 같은 브로커라 DB 기록 불가
- 검증: `MessagingIntegrationTest` 일시 실패 후 재시도 발행, 4번째 실패 격리·다른 subject 발행·재처리 SQL 후 순서대로 발행, 연결 실패 시 주기 중단

```sql
-- 격리 목록 (payload·subject 제외)
SELECT id, event_type, failure_count, last_error_code, quarantined_at, manual_retry_count, last_requeued_at
FROM outbox_event
WHERE quarantined_at IS NOT NULL AND published_at IS NULL
ORDER BY created_at, id;

-- 재처리: 원인 수정 후 실행, 다음 릴레이 주기에 원래 id로 발행
UPDATE outbox_event
SET failure_count = 0, next_attempt_at = NULL, quarantined_at = NULL,
    manual_retry_count = manual_retry_count + 1, last_requeued_at = now()
WHERE id = :event_id AND quarantined_at IS NOT NULL AND published_at IS NULL;
```

## 12. 일일 리포트 고정 대화 (#392)

2026-11-06 결정 P25(FN-RPT-16)의 core 몫. 학부모가 일일 리포트에서 만든 분석 대화를 자녀·그날·리포트 판으로 고정한다. 계약은 [API 명세](../design/api-spec.md) 2.4·4.2, 흐름은 [시퀀스 5.1](../design/sequence-diagram.md#51-일일-리포트-대화-p25).

### 구현

| 영역 | 내용 |
|---|---|
| DB | V33 `conversation.report_id uuid`·`report_revision int`(NULL 허용, 기본값 없음). `ck_conversation_report_pair`(함께 NULL 또는 함께 값)·`ck_conversation_report_revision`(1 이상)·`ck_conversation_report_day`(고정이면 `period_from = period_to`). 둘 다 NULL 허용이라 준비/최종 분리 없음 |
| 생성 | `POST /conversations {childId, reportId}` → `ConversationService.createForReport`. ① 트랜잭션: 자녀 연결·공유·이용권(무료 429) ② `ReportJobRepository.byReport`로 일일·같은 자녀 확인(아니면 422, HTTP 없음) ③ 트랜잭션 밖 `ReportQueryService.pinned(reportId, null)`로 최신 판·`COMPLETED` 확인 ④ 트랜잭션: 연결·이용권 재확인 후 `from = to = 대상일`, `report_id`·`report_revision` 저장. `reportId`와 `from`·`to`를 같이 보내면 400 |
| 응답 | 대화 생성·목록·상세에 `reportId`·`reportRevision`(일반 대화 null) |
| 메시지 | `AnalysisStreamService`가 ai 호출 직전(트랜잭션 밖) `ConversationService.report`로 고정 판을 `?revision=N`으로 다시 읽어 ai 요청 `report`에 요약을 넣는다. 재생성으로 새 판이 생겨도 대화는 처음 판을 쓴다 |
| 범위 | 고정 대화에 다른 기간 `scope`를 보내면 400(`scope_changed` 없음, 차감 전). 질문 속 다른 날은 ai `DIFFERENT_PERIOD` 범위 확인이 새 대화로 안내 |
| 한도 | 기존 `usage.consume` 경로 그대로라 분석 대화 하루 30회를 공유(질문마다 1회) |
| 오류 | 판 조회 실패는 메시지 `FAILED`·SSE `error`(`REPORT_UNAVAILABLE`·`REPORT_NOT_FOUND`·`REPORT_CONTRACT_INVALID`·`REPORT_SCOPE_REJECTED`). 관리자 작업 목록에 보이도록 `OperationErrors` 허용 목록에 추가 |

### 결정

1. **요약은 개수·판정만**: `{reportId, revision, date, metrics[{label, count}], problems[{title, context, judgment, elements[{label, satisfied}]}]}`. 되묻기·최종 답·돌아보기·인용 원문은 넣지 않는다. 인용 근거는 그날 learning 기록(`[원문]`)만 써서 기존 근거 ID 저장·숫자/인용 대조를 그대로 유지한다
2. **판 조회는 `detail`이 아닌 `pinned`**: `detail`은 `report_view` 열람 기록을 남기고 서술 권한을 조회한다. 대화 메시지마다 열람으로 세지 않도록 같은 소유·계약 검사(`validateDetail`, `detail`과 공유)만 하는 `ReportQueryService.pinned`를 두었다(서술 요청 false)
3. **일일 여부는 core `report_job` 기준**: report-api 응답 전에 core DB로 일일·자녀를 확인해 주간·다른 자녀·없는 리포트에 report 호출을 하지 않는다. 다른 보호자 리포트도 같은 422로 존재 여부를 구분하지 않는다
4. **무료 판정이 먼저**: 웹 목업(#394)과 같은 순서로 429를 422보다 먼저 돌려준다
5. **판 조회 실패도 차감 유지**: 기존 "받아들인 질문은 환불 없음" 원칙(5장)을 따른다

### API 변경

- core `POST /conversations` 요청 `reportId`(선택), 응답 `AnalysisConversation.reportId`·`reportRevision`(nullable), 400·422 `CONVERSATION_REPORT_INVALID`·429 명시
- ai `POST /internal/analysis/stream` 요청 `report`(선택, `AnalysisReportSummary`). 있으면 `scope.from = scope.to = report.date`([ai 보고서 10장](ai.md#10-일일-리포트-고정-대화-리포트-요약-입력-392))

### 검증

- core: 새 `ReportConversationIntegrationTest`(일일 고정·최신 판 고정·메시지마다 `?revision` 조회·요약에 원문 없음·30회 공유 1회 차감, 주간·다른 자녀·없음·미완료 422, 무료 429는 report 호출 없음, 다른 기간 400, 판 조회 실패 `FAILED`)와 `./gradlew test bootJar`
- DB: `verify_db_schema.py`에 쌍·판·하루 CHECK 음수 사례 3건
- 범위 밖: report 일일 상세 실제 생성(#391) 뒤 실서버 연결, 웹 실서버 확인(#394는 목업 기준)

## 13. 주간 테마 프록시·무료 하루 1개·추가 문제 프리미엄 (#387)

2026-11-06 결정(P23, P13·P14 개정, [서비스 방향](service-direction.md) 2.4·2.6)의 core 몫. 에픽 #396, #233 회의 안건(무료 미션 한도)의 구현. learning 테마 API(#385)는 동시에 구현 중이라 api-spec 2.11·4.1 계약대로 클라이언트를 만들고 테스트는 learning 계약 대역으로 했다.

- **학생 주간 테마**: `GET /students/me/weekly-theme`·`POST /students/me/weekly-theme/review-views`(`WeeklyThemeController`)를 learning `/internal/students/{studentId}/weekly-theme…?gradeBand&date`로 넘긴다. 학년군(초3~4 `G3_4`, 초5~6 `G5_6`)은 core 학년, 날짜는 `paymentClock` 기준 KST 오늘이라 무료 한도와 같은 날을 쓴다. 클라이언트 query는 버림. 요일 상태가 날마다 바뀌어 `Cache-Control: no-store`. 열람 기록에도 같은 query를 붙인다(4.1 표에 없던 값, learning이 학생의 주를 정하는 근거)
- **시도 `context`**: `POST /missions/{id}/attempts`의 본문 없음·`{}`·`context: null`은 `EXTRA`. `context` 외 필드나 허용 밖 값은 learning 호출 전 400. learning에는 학년·시연 query와 `{context}` 본문을 넘기고 `themeId`는 넘기지 않는다(그 주 테마는 learning이 학년·날짜로 정함, api-spec 4.1 비고를 이렇게 고침). 요일(`THEME_DAY_CLOSED`)·되돌아보기(`THEME_REVIEW_NOT_ALLOWED`) 검사는 learning이 하고 core는 그대로 전달
- **결정(2026-11-08 동섭)**: 무료 하루 1개(`limits.dailyMissions` 3 → 1, 신규 `201`만 집계)는 확정. 생각 유형별 고르기(`EXTRA`)의 프리미엄 전용은 미정이라 **지금은 무료도 허용**하고, 무료의 `EXTRA` 신규 시작도 `THEME_DAY`와 합쳐 하루 1개로 센다. 설계 문서(서비스 방향 2.4·기능명세 P13·api-spec 2.11 초안)의 'EXTRA는 프리미엄 추가 문제' 서술과 다르다. 프리미엄 전용으로 바꿀 때는 코드 수정 없이 상품 데이터만 바꾼다(아래 전환 방법)
- **판정 한 곳**: 무료·프리미엄 판단은 `ProductEntitlementService.forStudent`를 거치고, 시도 정책은 같은 서비스의 `missionStart`·`missionStarted`에만 둔다. learning 호출 전에 `THEME_REVIEW`는 상품과 무관하게 통과, `EXTRA`는 학생 상품의 `features.extraMissions`가 `false`면 403 `PREMIUM_REQUIRED`(없으면 허용, boolean이 아니면 503 `PAYMENT_PRODUCT_UNAVAILABLE`), 무료 `THEME_DAY`·`EXTRA`는 KST 오늘 `mission_daily_usage` 건수가 무료 상품 `limits.dailyMissions` 이상이면 429 `USAGE_LIMIT_REACHED`. 무료 상품에서 `EXTRA`가 꺼진 동안의 프리미엄 `EXTRA`만 프리미엄 사용이라 환불 처리 중이면 409 `REFUND_IN_PROGRESS`. `limits.dailyMissions`가 없거나 음수면 503 `PAYMENT_PRODUCT_UNAVAILABLE`(#48 원칙대로 임의 값으로 대체하지 않음). 프리미엄은 하루 미션 한도 없음(프리미엄 하루 피드백 50회는 이번 범위 밖)
- **기록**: learning이 신규 `201`을 돌려준 뒤에만 `missionStarted`가 무료 `THEME_DAY`·`EXTRA`는 `mission_daily_usage(attempt_id PK, student_id, mission_id, usage_date)`에, 무료 상품에서 `EXTRA`가 꺼진 동안의 프리미엄 `EXTRA`는 부모 잠금 안에서 `payment_premium_usage(kind = EXTRA_MISSION, source_id = 시도 ID, USED)`에 남긴다. 둘 다 시도 ID로 1회(PK·`UNIQUE(kind, source_id)`). `EXTRA_MISSION` 행은 기존 환불 검사(`usageCount`)가 그대로 세어 환불 판정의 프리미엄 사용이 된다(P14). 무료에도 열려 있는 지금은 프리미엄 `EXTRA`를 기록하지 않아 환불 판정에 영향이 없다. 이어하기 `200`은 기록하지 않는다
- **전환 방법**: (1) 무료 한도 수는 무료 상품(`PAYMENT_FREE_PRODUCT_ID` 행) `limits.dailyMissions`. 운영 DB는 `infrastructure/aws/set-free-product-daily-missions.sql`로 1로 바꾼 뒤 배포한다(값이 없으면 503). (2) `EXTRA` 프리미엄 전용 전환은 무료 상품 `features`에 `"extraMissions": false`를 넣는다(`UPDATE product SET features = jsonb_set(features, '{extraMissions}', 'false') WHERE id = <무료 상품 ID>`). 그 순간부터 무료 `EXTRA`는 403, 프리미엄 `EXTRA` 신규 시도는 `EXTRA_MISSION` 사용으로 기록된다. 되돌리려면 키를 지우거나 `true`. 프리미엄 상품 `features`는 비워 두면 허용
- **한도 뒤 이어하기**: 한도 확인은 learning 호출 전이라 이어하기(`200`)와 신규(`201`)를 구분할 수 없다. 한도에 닿았으면 같은 학생·미션의 마지막 기록 시도를 learning `GET /internal/attempts/{id}`로 읽어 `IN_PROGRESS`일 때만 넘긴다(learning은 미션당 진행 중 시도 하나를 200으로 반환). 그래서 ERD 3.6 설계에 `mission_id` 컬럼과 `(student_id, mission_id, created_at)` 인덱스를 더했다. 이미 마무리한 시도로 같은 날 다시 시작하는 것은 신규라 429
- **실패 처리**: 기록 저장 실패는 학습 응답(201)을 바꾸지 않고 ERROR 로그만 남긴다. 이미 learning에 시도가 생겼고, 같은 요청을 다시 보내면 200 이어하기라 학생이 막히지 않기 때문이다(그 대신 그 1건은 한도·환불 근거에서 빠질 수 있음). 학생 피드백 제출 때 프리미엄 `FEEDBACK` 사용은 따로 남으므로 환불 근거가 모두 사라지지는 않는다
- **동시 요청**: 한도 확인과 기록 사이에 잠금을 두지 않는다(learning HTTP 동안 DB 잠금을 잡지 않는 기존 원칙). 같은 미션은 learning이 진행 중 시도를 하나로 묶어 신규가 1건이지만, 무료 학생이 서로 다른 미션(`THEME_DAY`와 `EXTRA`, 또는 `EXTRA` 둘)을 동시에 시작하면 한도를 1건 넘길 수 있다. 하루 1개 정책의 학습 화면 흐름에서는 드물어 잠금 대신 허용 오차로 둔다
- **관리자 주간 테마**: `/admin/weekly-themes…`(`AdminWeeklyThemesController`)를 learning `/internal/admin/weekly-themes…`로 관리자 미션·미션 초안(#355)과 같은 방식(CONTENT, ADMIN + `X-User-Id` + 빈 학생 범위)으로 넘긴다. 목록 필터 `gradeBand`·`weekStart`(KST 월요일)·`status`는 core에서 검사. 작성·수정·검토 요청·게시·게시 중단은 요청 감사 → learning 1회 → 응답 `themeId`로 결과 감사(`audit_log` `WEEKLY_THEME_{CREATE,UPDATE,REVIEW_REQUEST,PUBLISH,UNPUBLISH}_*`, `target_type = WEEKLY_THEME`). 게시 검사 실패 `422 WEEKLY_THEME_PUBLISH_INCOMPLETE`는 코드만 전달하고 공급자 문구는 지운다
- **학생 삭제**: 삭제 확정(`ChildManagementService.confirm`) 트랜잭션 안에서 `MissionUsageService.deleteStudent`가 `mission_daily_usage`를 지운다(P09). `payment_premium_usage`는 거래 기록이라 남긴다
- **위치**: 아키텍처 1.1.1·2.6(c370228b)대로 집계·한도 확인·삭제는 기존 `usage` 패키지(`MissionUsageService`, `MissionDailyUsageRepository`, `mybatis/usage/`)가 맡는다. 어떤 시도를 셀지·한도 수·`EXTRA` 허용은 무료·프리미엄 판단과 함께 `ProductEntitlementService`가 정해 넘긴다. `learning` 패키지는 DB·JDBC·`@Transactional`을 쓰지 않는다(`test_learning_openapi.py`)
- **#389 연결 지점**: 이 PR에는 포인트 적립 코드를 넣지 않았다. 이후 #389 적립 연결에서 학습 완료 적립 보충을 `LearningProxyService.weeklyTheme()` 응답 뒤, 되돌아보기·완주 적립을 `reviewViewed()`의 `{firstViewThisWeek, completed}` 응답 뒤에 붙였다(14절 적립 연결)
- **마이그레이션**: core `V34__mission_daily_usage_and_extra_mission.sql`(develop V33 #392 다음)(새 테이블, `payment_premium_usage_kind_check`에 `EXTRA_MISSION` 추가, 기존 행 변경 없음). gitops 로컬 core 리비전 v33 → v34
- **배포 후 확인**: `scripts/verify_cd_deployment.py`가 body `{}`로 시도를 시작하면 이제 `EXTRA`라 무료 시연 학생은 하루 1개를 추가 문제로 쓰고, `EXTRA`를 프리미엄 전용으로 바꾸면 무료는 403·프리미엄은 배포마다 프리미엄 사용이 남는다. 그래서 주간 테마에서 평일은 오늘 `OPEN` 문제를 `THEME_DAY`로, 토·일은 마무리한 문제를 `THEME_REVIEW`로 시작하게 바꿨다([CD README](../../infrastructure/cd/README.md) D)
- **검증**: `WeeklyThemeProxyIntegrationTest`(무료 1개 뒤 429, 이어하기 허용·완료 시도 재시작 429, 되돌아보기 비집계, 무료 `EXTRA` 허용·합산, `extraMissions=false`면 무료 `EXTRA` 403, learning 409 전달, 학년군·KST 날짜, 삭제), `PaymentIntegrationTest`(`THEME_DAY`·`EXTRA` 합산 1개, KST 0시 초기화, `dailyMissions` 누락·`extraMissions` 형식 오류 503, 무료 상품 `extraMissions=false` 전환 후 무료 403·프리미엄 `EXTRA` 1회 기록·환불 거부 `REFUND_PREMIUM_USAGE_PRESENT`, 무료에 열려 있을 때 프리미엄 기록 없음), `AdminOperationsIntegrationTest`(주간 테마 7경로·CONTENT·감사·422), `LearningProxyIntegrationTest`(`context` 검사·본문 전달), `scripts/tests/test_weekly_theme_contract.py`·`test_cd_deployment.py`
- **남은 확인**: learning #385가 api-spec 4.1과 다른 경로·응답을 정하면 core 클라이언트와 `test_weekly_theme_contract.py`를 맞춘다. learning OpenAPI에 경로가 올라오면 #355처럼 core ↔ learning 3자 대조로 넓힌다
## 14. 참여 포인트·꾸미기 해금 (#389)

2026-11-06 결정 P21·P22([서비스 기획 방향](service-direction.md) 2.3)의 core `reward` 도메인 앞부분. 계약은 [API 명세](../design/api-spec.md) 2.8·2.10·3.12, 저장은 [ERD 3.5.1](../design/erd.md#351-포인트꾸미기-p21p22-389)(V35). 결제와 패키지·테이블을 나눴다(포인트는 돈이 아니고 환급·환불 경로가 없음).

### 범위

| 구분 | 이번 PR | 후속 |
|---|---|---|
| 규칙·원장·잔액 | `reward_rule`(P21 초기값 시드)·`reward_point_ledger`·`reward_point_balance`, 적립 진입점 `RewardService.earn` | - |
| 조회 | `GET /students/me/points`, `GET /children/{childId}/points` | - |
| 꾸미기 | `GET /students/me/look-items`, `POST …/unlock`, `PUT /students/me/preferences` 잠금·`equipped` | - |
| 관리자 | `/admin/look-items` 목록·등록·수정·판매 중단(CONTENT, 감사) | - |
| 적립 사건 연결 | 없음(서비스 메서드와 테스트만) | 후속 PR로 연결함(아래 "적립 연결") |

적립 연결을 뒤로 미룬 이유: 사건이 생기는 경로(`LearningProxyService`, 커뮤니티·주간 테마 프록시)를 #387·#388이 동시에 고치고 있어, 같은 파일을 두 PR이 바꾸면 충돌과 중복 적립 위험이 생긴다. 먼저 사건 키 멱등인 `earn`을 만들어 두면 후속 PR은 사건 확인 뒤 한 줄로 부르면 된다.

### 결정과 근거

- **적립 진입점 하나(`earn`)**: 규칙 조회 → 학생 활성 확인 → 잔액 잠금 → 같은 사건 확인 → 하루 상한 → 원장 1행 + 잔액 갱신. 적립하지 않은 이유(`DUPLICATE`·`DAILY_CAP_REACHED`·`RULE_INACTIVE`·`STUDENT_UNAVAILABLE`)는 예외 없이 결과로 돌려 학습 응답을 막지 않는다(P21 "적립 저장 실패는 학습 응답 유지"). `REQUIRES_NEW`라 호출자 트랜잭션이 있어도 적립 실패가 그 트랜잭션을 망치지 않는다
- **멱등은 사건 키 UK로**: `(student_id, event_type, source_key)`가 같으면 두 번째 적립이 없다. 그래서 저장 실패 뒤 같은 사건 재요청·주간 테마 조회 때 같은 `earn`을 다시 부르는 것으로 보충이 끝난다(별도 재시도 큐·Outbox 없음, 서비스 기획 방향 5장 "새 메시지를 두지 않음")
- **하루 상한은 횟수, 한국 시간**: `daily_cap`은 하루 적립 횟수다. 반응 1점·5회라 지금은 포인트와 같지만, 운영이 점수를 바꿔도 "하루 반응 다섯 번"이라는 뜻이 유지된다. 하루 경계는 학생 생활 기준인 KST 자정
- **잠금 순서 학생 행(공유) → 잔액 행(배타)**: 학생 삭제 확정은 학생 행을 `FOR UPDATE`로 잡고 포인트·해금을 지운다. 적립·해금이 학생 행을 `FOR SHARE`로 먼저 잡아, 삭제와 겹치면 삭제가 끝난 뒤 `ACTIVE`가 아님을 보고 멈춘다(삭제 뒤 원장이 다시 생기지 않음). 같은 학생의 적립·해금은 잔액 행으로 직렬화해 동시 해금도 1회만 차감되고 하루 상한도 넘지 않는다
- **해금 이중 방어**: `Idempotency-Key`는 같은 요청 재전송(응답 재사용)을, 해금 PK `(student_id, item_key)`와 원장 UK `(student, UNLOCK, itemKey)`는 다른 키로 보낸 같은 해금을 막는다. 공통 멱등 저장(`IdempotencyService`)은 업무 커밋 뒤 응답 저장 사이에 틈이 있는데(지원 신고와 같은 문제), 이 틈에서 재요청해도 "이미 해금 200"으로 끝나 차감이 두 번 일어나지 않는다
- **테마·캐릭터는 코드 상수, 아이템만 테이블**: 결정 "기존 테마·캐릭터 해금값은 코드 상수". 값 목록이 V23 CHECK·웹 상수와 이미 묶여 있어 테이블로 옮기면 세 곳이 어긋날 수 있다. 관리자 아이템 `code`는 `^[A-Z0-9_]{3,40}$`(DB CHECK)라 `THEME:`·`COMPANION:` 키와 겹치지 않는다
- **판매 중단과 착용**: 영구 해금이라 판매 중단 뒤에도 해금한 학생 목록에는 `onSale:false`로 남고 계속 착용한다. 해금하지 않은 학생 목록에서는 빠진다(웹 목업과 같은 동작)
- **잠금 전 선택 이관**: V35가 `student.look_theme`·`look_companion`(무료 제외)을 `ledger_id` NULL 해금 행으로 옮긴다. 포인트를 차감하지 않고, 원장에도 남기지 않는다(받은 적 없는 포인트를 쓴 기록이 생기지 않게)
- **`equipped` 생략은 유지**: 웹은 테마·캐릭터만 바꿀 때 `equipped`를 보내지 않는다(`studentLook/api.ts`). 생략·null을 "비우기"로 읽으면 테마를 바꿀 때마다 아이템이 벗겨진다. 비우려면 슬롯을 null로 보낸다
- **학부모 조회와 공개 설정**: 포인트는 학습 원문이 아니라 #206 학생 공개 설정과 무관하게 연결 학부모가 본다(결정 "잔액은 본인·학부모만")
- **학생 삭제**: 기존 `ChildManagementService.confirm`이 부르는 `StudentLookService.clear`가 착용 → 해금 → 원장 → 잔액을 같은 트랜잭션에서 지운다. `confirm` 본문을 바꾸지 않아 #388(`community_enabled` 끄기)과 같은 줄을 다투지 않는다

### 검증

- `RewardIntegrationTest`(PostgreSQL·RabbitMQ 컨테이너): 시드 규칙값, 사건 키 1회·KST 하루 상한(23:30·다음날 00:10), 비활성 규칙·삭제 진행 학생 미적립, 학생·학부모만 조회, 목록 가격·판매 중단 노출, 해금 키 재사용·다른 키 재해금 무차감·부족·중단·없는 항목, 다른 키 4건 동시 해금 1회 차감, 잠금 409·`equipped` 슬롯·생략 유지·판매 중단 아이템 착용, 관리자 CONTENT·형식·코드 중복·감사 4종, 학생 삭제 정리, DB 부호·UK·잔액 CHECK
- `LookUnlockMigrationTest`: V34 상태에 저장된 꾸미기를 넣고 V35 적용 → 유료 값만 `ledger_id` NULL 해금 행, 원장 0행
- 계약: `scripts/validate_reward_contracts.py`가 실제 MockMvc 응답(포인트·목록·착용·관리자 아이템)을 OpenAPI로 검사(`ci-contracts`). `scripts/verify_db_schema.py`에 `reward_rule` 시드 예외(`event_type` 키)와 V35 음성 사례 13건 추가
- 남은 일: 학습 완료 → 적립 → 해금 → 착용 실서버 종단 확인(이슈 완료 조건), 웹 실서버 연결 확인(#393~#395)

### 적립 연결 (후속 PR)

#387·#388이 머지된 뒤 사건이 생기는 프록시 경로에 `earn`을 붙였다. 연결은 `ParticipationRewardService` 한 곳에 모아 각 경로는 사건 확인 뒤 한 줄로 부른다.

| 사건 | 부르는 곳 | 조건 | 사건 키 |
|---|---|---|---|
| 학습 완료 `MISSION_COMPLETED` | `LearningProxyService.reflection` | 돌아보기 저장 2xx 또는 `409 ATTEMPT_CLOSED`(같은 사건 재요청) 뒤 learning 시도 상세가 `COMPLETED` | 시도 상세 `mission.id` |
| 공유 `COMMUNITY_POSTED` | 같은 곳, `CommunityService.shareCompleted` 결과 | 공유 응답 201(새 공유)·200(이미 있음) | `postId` |
| 반응 `REACTION_GIVEN` | `CommunityService.react` | 반응 남기기 2xx(취소는 적립 없음) | `postId:reaction` |
| 되돌아보기 `REVIEW_VIEWED` | `LearningProxyService.reviewViewed` | 열람 기록 200 | 그 주 월요일(KST) |
| 완주 `THEME_COMPLETED` | 같은 곳 | 열람 응답 `completed:true` | 그 주 월요일(KST) |
| 보충 | `LearningProxyService.weeklyTheme` | 조회 200의 `days[].attemptStatus == COMPLETED` 미션 | 학습 완료와 같음 |

- **응답을 바꾸지 않음**: `ParticipationRewardService`는 응답 해석·`earn` 실패를 모두 로그로만 남기고 던지지 않는다. `earn`은 자체 트랜잭션(`REQUIRES_NEW`)이고 프록시 경로에는 바깥 트랜잭션이 없어, 적립이 실패해도 learning 응답·상태 코드·본문이 그대로 나간다. 공개 API 응답 모양은 바뀌지 않았다(적립 결과는 `GET /students/me/points`로 본다). 시퀀스 다이어그램 설계안의 응답 `{earned}`는 넣지 않았다: 웹이 이미 잔액을 따로 조회하고, learning 응답을 그대로 넘기는 프록시 원칙을 지키려는 것
- **학습 완료 미션은 시도 상세로 확인**: learning 돌아보기 응답은 `{attemptId, status, reflection}`라 미션 ID가 없다. 저장 뒤 `GET /internal/attempts/{id}`를 한 번 더 불러 `COMPLETED`와 `mission.id`를 확인한다(클라이언트가 보낸 값은 쓰지 않음). 다시 풀기는 같은 미션 키라 적립하지 않는다(P21 미션당 최초 1회)
- **보충 경로**: 같은 돌아보기 재요청은 learning이 `409 ATTEMPT_CLOSED`를 돌려주지만 core는 그 응답을 그대로 넘기면서 학습 완료·공유 적립을 다시 시도한다. 반응은 이미 남긴 반응을 다시 보내면(`created:false`) 같은 키로 보충만 된다. 되돌아보기·완주는 열람 기록이 멱등이라 열람 재요청이 보충이다. 주간 테마 조회는 이번 주 요일 문제 중 학습 완료한 미션만 보충하고, 추가 문제(EXTRA)는 응답에 없어 보충하지 않는다(FN-RET-05). 주간 테마 조회는 열람 여부를 알려 주지 않아 되돌아보기·완주 보충은 하지 않는다
- **반복 적립 방지**: 반응 키 `postId:reaction`은 learning 반응 ID(같은 학생·공유물·반응이면 같은 ID)와 1:1이라 껐다 켜도 한 번이다. 하루 상한은 `earn`이 KST 하루 횟수로 막는다
- **주 시작일**: 열람 응답에는 `weekStart`가 없어 core가 learning에 넘긴 날짜(`entitlements.today()`, KST)의 월요일로 정한다. learning도 같은 날짜로 그 주를 정한다
- **작성자 `look.equipped`**: 커뮤니티 작성자 표시(`CommunityAuthorMapper`)에 착용 네 슬롯을 더했다(`StudentLook.equipped`와 같은 모양, 없으면 null). 공개 가능한 작성자만 한 번에 조회한다
- 검증: `RewardEarnIntegrationTest`(가짜 learning) — 미션당 1회·닫힌 재요청·다시 풀기 무적립, 적립 실패(`RewardService` spy가 예외) 중에도 돌아보기·반응·열람 응답 유지 후 재요청 보충, 주간 테마 조회 보충(완료 요일만·깨진 응답은 그대로 전달), 열람 주 1회·완주, 반응 키 1회·하루 상한 5, 학습 완료 적립 → 해금 → 착용 → 다른 학생이 본 작성자 `look.equipped`. 기존 `CommunityIntegrationTest`에 `equipped` 슬롯 확인 추가
- 남은 확인: kind 실서버에서 web → core → learning으로 "학습 완료 → 적립 → 해금 → 착용"을 직접 확인하지 않았다

## 15. 테마 초안 관리자 프록시·이야기 열람 프록시·사용량 THEME_DRAFT (#439)

에픽 #436(주간 테마 LLM 생성과 시작·종료 화면)의 core 몫. learning #438·ai #437이 동시에 진행 중이라 api-spec 2.8·2.11·4.1과 에픽 결정 요약대로 클라이언트를 만들고, 테스트는 learning 계약 대역(HTTP 서버)으로 했다.

### API 변경

| 경로 | 권한 | learning 내부 경로 | 응답·오류 |
|---|---|---|---|
| `POST /api/v1/admin/theme-drafts` | CONTENT | `POST /internal/admin/theme-drafts` | `202` 초안(`GENERATING`), 본문 그대로 전달 |
| `GET /api/v1/admin/theme-drafts?status&source&page&size` | CONTENT | 같은 경로·query | `status` 6종·`source`(`AUTO`·`ADMIN`)·페이지 밖 값은 learning 호출 전 `400 VALIDATION_FAILED` |
| `GET /api/v1/admin/theme-drafts/{draftId}` | CONTENT | `GET …/{draftId}` | 없는 초안 `404 NOT_FOUND`(고정 문구 "테마 초안을 찾을 수 없습니다.") |
| `POST /api/v1/admin/theme-drafts/{draftId}/adopt` | CONTENT | `POST …/adopt` | `201` 만든 테마(`themeId`). 미션 5개·테마 `DRAFT` 생성은 learning 한 트랜잭션 |
| `POST /api/v1/admin/theme-drafts/{draftId}/discard` | CONTENT | `POST …/discard` | `200` 초안. 상태상 불가 `409 CONFLICT` |
| `POST /api/v1/admin/theme-drafts/{draftId}/regenerate` | CONTENT | `POST …/regenerate` | `202` 초안(`GENERATING`) |
| `POST /api/v1/students/me/weekly-theme/story-views` | 학생 | `POST /internal/students/{id}/weekly-theme/story-views?gradeBand&date` | 본문 `{kind: INTRO\|OUTRO}`만 허용(그 밖 `400`), 응답·요일 오류는 learning 그대로 |
| `GET /api/v1/students/me/weekly-theme` | 학생 | (변경 없음) | `outro`·`introImageUrl`·`outroImageUrl`·`introSeen`·`outroSeen`을 바꾸지 않고 전달 |
| `GET /api/v1/admin/ai-usage?callType` | SERVICE_OPS | — | `callType`에 `THEME_DRAFT`·`THEME_IMAGE` 추가 |

### 결정과 근거

- **관리자 경로는 미션 초안(#355)과 같은 방식**: `AdminThemeDraftsController` → `AdminLearningService.themeDrafts`가 ADMIN + `X-User-Id` + 빈 학생 범위로 넘긴다. 요청 본문(학년군·주·주제·유형별 성취기준) 값 검사와 상태 전이는 learning 소유라 core는 JSON object인지만 본다. 컨트롤러를 `AdminWeeklyThemesController`에 넣지 않고 따로 둔 것은 미션 초안이 `AdminMissionDraftsController`로 따로 있는 것과 맞추고, 주간 테마 계약 검사(경로 7개)를 건드리지 않기 위해서다
- **감사**: 요청 감사 → learning 1회 → 결과 감사(`audit_log` `THEME_DRAFT_{REQUEST,DISCARD,REGENERATE,ADOPT}_*`). 요청·버리기·다시 생성은 응답 `draftId`(`target_type = THEME_DRAFT`), 채택은 만든 테마 `themeId`(`WEEKLY_THEME`, `detail.draftId`)가 대상이라 이후 `WEEKLY_THEME_*` 감사와 이어진다. 다시 생성은 learning이 같은 초안을 되살리든 새 초안을 만들든 응답 `draftId`를 대상으로 남긴다. 응답에 대상 ID가 없으면 `UNKNOWN`으로 남기고 `503 LEARNING_INVALID_RESPONSE`, 다시 부르지 않는다(#355와 같음)
- **이야기 열람**: 학년군·KST 날짜는 되돌아보기 열람(#387)과 같이 core가 정하고, 본문은 `{kind}`만 다시 만들어 넘긴다(클라이언트가 날짜 등을 끼워 넣지 못하게). INTRO 월요일·OUTRO 토요일·주 1회 멱등 판정은 learning이 `date`로 한다. 포인트 적립은 없다(되돌아보기 열람·완주 적립은 기존 `review-views` 그대로)
- **이미지 URL**: 기존 미션 장면(`sceneUri`·`staticSceneUri`)처럼 learning이 준 값을 core가 바꾸지 않고 전달한다. ai가 올린 S3 키를 브라우저가 열 수 있는 URL로 바꾸는 일은 learning 응답 몫이다(api-spec 2.11)
- **사용량**: `THEME_DRAFT`(텍스트 그래프 호출)·`THEME_IMAGE`(이미지 1장 호출)를 이벤트 스키마·core `CallType`·core OpenAPI·ERD·ai/scoring 발행 목록에 같은 순서로 더하고 `V40__theme_draft_call_type.sql`이 `ck_llm_usage_call_type`을 넓힌다(V28과 같은 방식, 기존 행 영향 없음). ai/scoring 발행 목록은 타입 목록만 바뀌고 실제 발행은 ai #437이 한다. 이미지 호출은 토큰이 없어 `cost_usd`가 null이고 관리자 사용량에서 `unpricedCalls`로 센다(장당 단가는 #437 측정 뒤 결정)
- **마이그레이션 번호**: 이슈 본문은 V38이지만 열린 #446이 V38·V39를 쓰므로 V40. gitops 로컬 core 리비전 v40. #446보다 먼저 머지하면 V38·V39가 이미 V40을 적용한 DB에서 순서 밖이 되므로 #446 뒤에 머지하고, 머지 직전 develop에 다른 core 마이그레이션이 생기면 번호를 다시 맞춘다

### 검증

- `AdminOperationsIntegrationTest`: 테마 초안 6경로가 CONTENT·관리자 헤더·빈 학생 범위로 넘어감, SERVICE_OPS 403, 필터 값·페이지 400(learning 미호출), 요청·다시 생성·채택·버리기 감사 대상(채택은 `WEEKLY_THEME` + `draftId`), 대상 없는 응답 `UNKNOWN`·재호출 없음, 404 고정 문구
- `WeeklyThemeProxyIntegrationTest`: 새 필드 그대로 전달, 이야기 열람 query·본문·학생 헤더, learning 409 전달, 잘못된 `kind`·추가 필드·배열 400(learning 미호출)
- `ModelVersionHttpTest`·`LlmUsageQueryTest`: `THEME_DRAFT`·`THEME_IMAGE` 저장(V40 CHECK)·호출 종류별 조회, 토큰 없는 이미지 호출 미산정
- `scripts/tests/test_theme_drafts_contract.py`: core 컨트롤러 ↔ 공개 OpenAPI 경로·query·상태/출처 값·CONTENT·감사 동작·`kind` 값. learning OpenAPI에 `/admin/theme-drafts`가 올라오면 3자 대조가 자동으로 켜진다(지금은 건너뜀). `test_admin_mission_drafts_contract.py` 호출 종류 목록 대조
- **남은 확인**: learning #438 머지 후 실제로 붙여 관리자 초안 요청 → 채택, 학생 월요일 INTRO 기록 확인. learning이 경로·query·응답 필드를 다르게 정하면 core와 `test_theme_drafts_contract.py`를 맞춘다

## 16. 리포트 고정 대화·참여 포인트·커뮤니티 신고 실서버 확인 (#424, 2026-11-10)

local kind(develop `b1562c2b`)에서 테스트 학부모·학생·관리자 계정으로 core 공개 API를 실제로 호출해 확인했다. 프리미엄은 토스 결제 대신 결제 완료와 같은 모양의 구독 행(로컬 프리미엄 상품, 한 달)을 kind DB에 넣어 줬다.

| 흐름 | 결과 |
|---|---|
| 리포트 고정 대화 생성 | 학생이 학부모 원문 공개를 켜기 전에는 403 `STUDENT_RECORDS_PRIVATE`. 켠 뒤 201, `reportId`·`reportRevision 1`·그날 범위로 고정 |
| 질문 | 날짜 표현 없는 질문은 학생 원문을 그대로 인용해 답변(`result`). "오늘 …"으로 물으면 같은 날짜인데도 `DIFFERENT_PERIOD` 되묻기 → #454 |
| 사용량 | 질문마다 `payment_premium_usage` `CONVERSATION` 1건(되묻기 포함, #41 시도 기준) |
| 참여 포인트 | 미션 완료 +10, 공유 +5, 반응 +1(잔액 15 → 16), 꾸미기 해금 차감·착용 저장. 착용 아이템이 캐릭터에 그려지지 않는 것은 웹 미구현 → #455 |
| 커뮤니티 신고 처리 | 학생 신고 접수 → 관리자 목록 1건 → `IN_REVIEW` → `RESOLVED`(`reviewResult: VISIBLE`). `RECEIVED`에서 바로 `RESOLVED`는 409 `SUPPORT_STATE_CONFLICT` |
| 알림 | 일일·주간 리포트 완료 알림이 학부모 알림 화면에 보이고 읽지 않음 개수로 표시 |

- 되돌아보기 열람(+10)·주간 테마 완주(+30) 적립은 주말·5일 연속 학습이 필요해 미확인
