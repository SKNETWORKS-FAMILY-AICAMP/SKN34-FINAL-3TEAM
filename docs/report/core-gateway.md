# core 서비스: 학습 프록시·SSE·대시보드·알림·분석 대화·이벤트·포인트·신고·결제

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
- 일일 한도(P13): PostgreSQL `mission_daily_usage`로 집계(#387, 13절). 2026-11-10 개정(#485, 18절) 뒤에는 무료 테마 문제를 세지 않고 무료 상품에서 다시 켠 무료 `EXTRA`만 셈

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
- 권한 공급: `conversation.service.AnalysisEntitlementProvider` 포트(`entitlement(parentId, childId)` → productId·dailyConversations·validUntil)는 payment 구현(24.5). 미연결·음수·누락·만료는 503 `PAYMENT_ENTITLEMENT_UNAVAILABLE`, `conversationEnabled=false`(환불 진행 포함)는 한도와 무관하게 차단
- 내부 AI 호출 `POST /internal/analysis/stream {conversationId,messageId,question,scope:{studentId,from,to},history}`. 내부 토큰·검증된 PARENT context를 InternalRestClientFactory로 전달하고 studentScope는 대상 하나로 축소. 내부 result scope는 studentId, 공개 응답은 childId
- 근거는 ID만 저장. `LearningRecordService`로 `/internal/records/evidence?answerIds=...`를 조회하며 현재 권한/삭제/ID 재검사. 삭제된 근거는 `available:false`만 표시하고 다른 원문으로 대체하지 않음
- 대화 목록은 본인·현재 연결 자녀의 최신 100개(답변 본문 없음), 상세는 소유 conversationId로. 구독 만료 후에도 소유/연결/동의가 유효하면 저장된 이력 조회 가능, 신규 분석은 상품 권한 재검사
- TEMPLATE fallback.reason은 COMPLETED 행 failure_code에 보존하고 공개 실패 코드는 FAILED에서만 노출
- 하위 호출 서킷(#167): AI 전체 스트림 집계. OPEN은 기존 AI_UNAVAILABLE/FAILED, 사용자 취소·core 소비자 실패는 집계 제외, 차감은 보존. 최근/최소 20건·실패율 50%·30초 차단·half-open 1건
- 재현: `scripts/verify_analysis_evidence.py`(실제 core·learning JAR로 근거 조회·타 보호자 404·위조 messageId 404·학생 범위 위조 403·삭제 후 `available:false` 확인)

- 정정 안내(#244): 대화 상세의 답변별 `correctionNotice`. 기록과 판단은 21절 「정정 영향 판정과 표시」

## 6. Redis 사용 필요성과 PostgreSQL 대체 비교 (#210)

10/29 [멘토링](planning.md#1-1029-오프라인-멘토링-결정후속)의 재검토 권고에 따라 core의 Redis 사용처와 PostgreSQL 대체안을 비교했다. 부하·비용 수치는 실측이 없어 추정이다.

### 사용처와 장애 시 동작

| 사용처 | Redis가 보장하는 성질 | Redis 장애 시 |
|---|---|---|
| 학생 기기 페어링 코드 | 해시 키 `SET NX`·10분 TTL, Lua `GET`+`DEL` 1회 소비 | 503 `STUDENT_AUTH_UNAVAILABLE`. 등록된 기기의 프로필·PIN 로그인은 DB만 써서 영향 없음 |
| 기기 등록·페어링 발급 rate limit | Lua `INCR` 후 첫 증가에만 `EXPIRE 600`(10분 고정 창, 기본 20회) | 위와 같은 503 |
| 알림 다중 레플리카 SSE 중계 | 채널 `core:notifications:v1` fan-out(at-most-once), 커밋 후 발행 | 알림 `FAILED`·`REDIS_PUBLISH_FAILED`. 알림 행·리포트 상태는 유지, 목록 재조회로 복구 |
| 분석 대화 일일 사용량·관리자 재처리 표식 | (#225로 PostgreSQL 이전) | 영향 없음 |

- 운영 코드의 Redis 접근은 위 용도뿐이고 **조회 캐시로는 쓰지 않는다**. learning·ai·scoring·report는 Redis를 쓰지 않는다
- readiness 그룹은 `readinessState,db,rabbit`이라 Redis 장애 시 Pod는 Ready를 유지하고 기능별로만 503
- Redis는 EKS `platform` namespace의 StatefulSet(replicas 1) + EBS PVC. 금액보다 운영 항목(이미지 갱신·AOF·Secret·NetworkPolicy·관측)이 비용

### 선택지와 결정

| 선택지 | 내용 | 판단 |
|---|---|---|
| A. 전부 유지 | 미션 한도도 Redis로 구현 | 분석 사용량과 DB 트랜잭션 불일치·재처리 표식 제약이 남음 |
| **B. 부분 대체** | 분석 사용량·재처리 표식(+미션 한도 신규)은 PostgreSQL, 페어링·rate limit·알림 중계는 Redis | **채택(2026-11-02, 담당자)** |
| C. 전부 대체 | 위 대체 + 알림을 `LISTEN/NOTIFY`로 | 알림 리스너 직접 구현·다중 레플리카 재검증 필요, 비인증 경로의 DB 쓰기 |

결정 기준: "DB 저장과 함께 커밋·롤백되어야 하는 값은 PostgreSQL, 짧은 수명 값과 레플리카 간 fan-out은 Redis".

- 분석 사용량은 이미 보호자·학생 행 잠금 트랜잭션 안에서 차감되므로 PostgreSQL로 옮기면 롤백 불일치와 분산 원자성 제약이 함께 사라짐
- 페어링·rate limit은 TTL·짧은 수명 데이터라 Redis가 자연스럽고, 남용 트래픽을 RDS 쓰기로 옮기지 않음
- 알림을 `LISTEN/NOTIFY`로 바꾸면 풀 밖 전용 연결·재연결·재`LISTEN`을 직접 구현해야 하고 유실 특성은 같아 이득이 없음. 연결을 다중화하는 프록시(PgBouncer transaction pooling·RDS Proxy)를 도입하면 제약이 됨
- 운영 항목 축소가 우선이 되면 C를 다시 검토(알림 리스너 구현·다중 레플리카 검증을 먼저 별도 이슈로)
- 미션 일일 한도는 PostgreSQL `mission_daily_usage`로 구현(#387, 13절). #485 뒤에는 무료 `EXTRA`를 다시 켤 때만 사용(18절)

### 분석 대화 사용량 DB 이관 구현 (#225)

새 테이블 없이 **기존 결제 사용 이력 `payment_premium_usage` 집계**로 구현했다. 유료 구독의 분석 시도는 이미 같은 트랜잭션에서 `CONVERSATION` 행을 남기므로 그 행 수가 일 사용량이다. 무료 상품은 분석 대화 0회(P13)라 기존 0 한도 차단으로 처리된다.

- 한도 판정: `ProductEntitlementService.reserve`가 보호자 잠금 안에서 오늘(KST 0시) `CONVERSATION`·`RESERVED/USED` 행 수가 `limits.dailyConversations` 이상이면 `429 USAGE_LIMIT_REACHED`
- `AnalysisUsageService.consume(parent, child, source)` 하나가 0 한도·유효기간 확인 후 provider에 기록. 메시지 저장 전 1회 호출(리포트 설정 제안 #209도 같음)
- 관리자 재시도는 영속 요청 ID(`conversation_job_retry.id`)를 source ID로 `consume`. 이미 기록된 source는 `UNIQUE(kind, source_id)`의 기존 행을 재사용해 추가 차감이 없음
- 차감 정책은 그대로: 새 질문·재시도마다 1회, 실패·취소·clarification도 차감, AI 호출 전 거부는 차감하지 않음
- 차감 행은 메시지 저장·실행 선점과 같은 트랜잭션이라 함께 롤백. 집계는 자녀 기준이며 같은 날 구독이 바뀌어도 합산
- `ANALYSIS_USAGE_UNAVAILABLE`은 더는 발생하지 않음. 과거 작업 실행 기록 표시를 위해 `admin/domain/Operations.kt`의 안전 코드 목록에는 남김
- 관리자 재실행 130초 만료는 실행 만료(대화 RUNNING 고착 판정과 같은 값)로 유지
- 프리미엄 피드백 50회 한도(P13)는 미구현
- 테스트: `AnalysisUsageContractTest`, `ConversationPaymentIntegrationTest`(30개 동시 접수 중 한도만큼만 차감), `AdminConversationRetryTest`

## 7. 관리자 대화 재처리 시각 출처 통일 (#286)

`ck_conversation_job_retry_order`(V19, `started_at >= accepted_at`) 위반이 간헐적으로 났다. `accepted_at`은 앱 `Instant.now()`, `started_at`·`finished_at`은 DB `CURRENT_TIMESTAMP`라 앱 시계가 앞서면 순서가 역전됐다. DB 시계로 통일했다(V19 CHECK·기존 마이그레이션 불변).

- 접수 `insert`의 `accepted_at`을 매퍼에서 DB `CURRENT_TIMESTAMP`로 기록. 202 응답은 접수 직후 다시 읽은 행이라 이미 DB 값
- 선점 전 만료 판정도 앱 시각 비교에서 매퍼 `claimable`(`claim` UPDATE와 같은 조건·같은 트랜잭션 시각)로 변경. 130초 경계 근처에서 앱 판정 "유효"·DB `claim` "만료"로 갈리면 사용량 차감을 지난 뒤 트랜잭션 전체가 롤백되던 문제 제거
- 회귀 테스트: `AdminConversationRetryTest`(앱 시각이 DB보다 5초 앞선 행, DB 기준 131초 지난 요청은 선점되지 않음)

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

아키텍처 2.1·2.2 위반을 [점검 원장](testing-ci.md#5-develop-종합-점검-원장-16회차)의 A3·A4·A8~A10에서 찾아 정리. 응답(code·status·본문)과 API·이벤트 계약은 변경 없음.

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

P25(FN-RPT-16)의 core 몫. 학부모가 일일 리포트에서 만든 분석 대화를 자녀·그날·리포트 판으로 고정한다. 계약은 [API 명세](../design/api-spec.md) 2.4·4.2, 흐름은 [시퀀스 5.1](../design/sequence-diagram.md#51-일일-리포트-대화-p25).

- DB: V33 `conversation.report_id`·`report_revision`(NULL 허용). CHECK 3개(함께 NULL 또는 함께 값, 판 1 이상, 고정이면 `period_from = period_to`)
- 생성 `POST /conversations {childId, reportId}`: ① 자녀 연결·공유·이용권(무료 429) ② core `report_job`으로 일일·같은 자녀 확인(아니면 422, report 호출 없음) ③ 트랜잭션 밖에서 최신 판·`COMPLETED` 확인 ④ 재확인 후 `from = to = 대상일`과 판 저장. `reportId`와 `from`·`to`를 같이 보내면 400
- 메시지마다 ai 호출 직전(트랜잭션 밖) 고정 판을 `?revision=N`으로 다시 읽어 ai 요청 `report`에 요약을 넣음. 재생성으로 새 판이 생겨도 대화는 처음 판 사용
- 고정 대화에 다른 기간 `scope`를 보내면 400(차감 전). 질문 속 다른 날은 ai `DIFFERENT_PERIOD` 범위 확인이 새 대화로 안내
- 한도는 분석 대화 하루 30회 공유
- 판 조회 실패는 메시지 `FAILED`·SSE `error`(`REPORT_UNAVAILABLE`·`REPORT_NOT_FOUND`·`REPORT_CONTRACT_INVALID`·`REPORT_SCOPE_REJECTED`)

결정:

1. **요약은 개수·판정만**: `{reportId, revision, date, metrics[], problems[{title, context, judgment, elements[]}]}`. 되묻기·최종 답·돌아보기·인용 원문은 넣지 않음. 인용 근거는 그날 learning 기록만 써서 기존 근거 ID 저장·숫자/인용 대조 유지
2. **판 조회는 `detail`이 아닌 `pinned`**: `detail`은 `report_view` 열람 기록을 남기므로, 대화 메시지마다 열람으로 세지 않도록 같은 소유·계약 검사만 하는 `ReportQueryService.pinned`를 둠
3. **일일 여부는 core `report_job` 기준**: 다른 보호자 리포트도 같은 422로 존재 여부를 구분하지 않음
4. **무료 판정(429)이 422보다 먼저**
5. **판 조회 실패도 차감 유지**(5장 "받아들인 질문은 환불 없음")

테스트: `ReportConversationIntegrationTest`.

## 13. 주간 테마 프록시·무료 하루 1개·추가 문제 프리미엄 (#387)

P23·P13·P14의 core 몫. 무료 한도·추가 문제·일요일 규칙은 2026-11-10 개정으로 바뀌어 **18절이 우선**한다. 여기에는 지금도 유효한 구조만 남긴다.

- **학생 주간 테마**: `GET /students/me/weekly-theme`·`POST …/review-views`를 learning `/internal/students/{studentId}/weekly-theme…?gradeBand&date`로 전달. 학년군은 core 학년, 날짜는 `paymentClock` 기준 KST 오늘. 클라이언트 query는 버림. `Cache-Control: no-store`
- **시도 `context`**: `POST /missions/{id}/attempts`의 본문 없음·`{}`·`context: null`은 `EXTRA`. 허용 밖 값은 learning 호출 전 400. `themeId`는 넘기지 않음(그 주 테마는 learning이 학년·날짜로 정함). 요일·되돌아보기 검사는 learning
- **판정 한 곳**: 무료·프리미엄 판단은 `ProductEntitlementService`의 `missionStart`·`missionStarted`에만 둠. `limits.dailyMissions`·`features.extraMissions`가 없거나 형식이 틀리면 503 `PAYMENT_PRODUCT_UNAVAILABLE`(임의 값 대체 없음)
- **기록**: learning이 신규 `201`을 돌려준 뒤에만 기록. 무료 한도 대상은 `mission_daily_usage(attempt_id PK, student_id, mission_id, usage_date)`, 프리미엄 `EXTRA`는 부모 잠금 안에서 `payment_premium_usage(kind = EXTRA_MISSION)`(환불 판정의 프리미엄 사용, P14). 이어하기 `200`은 기록하지 않음
- **한도 뒤 이어하기**: 한도 확인은 learning 호출 전이라 이어하기와 신규를 구분할 수 없음. 한도에 닿았으면 같은 학생·미션의 마지막 기록 시도를 learning에서 읽어 `IN_PROGRESS`일 때만 넘김
- **실패 처리**: 기록 저장 실패는 학습 응답(201)을 바꾸지 않고 ERROR 로그만(같은 요청 재전송은 200 이어하기라 학생이 막히지 않음)
- **동시 요청**: 한도 확인과 기록 사이에 잠금 없음(learning HTTP 동안 DB 잠금을 잡지 않는 원칙). 서로 다른 미션을 동시에 시작하면 1건 넘길 수 있는 허용 오차
- **관리자 주간 테마**: `/admin/weekly-themes…`를 learning으로 관리자 미션과 같은 방식(CONTENT, ADMIN + `X-User-Id` + 빈 학생 범위)으로 전달. 요청 감사 → learning 1회 → 결과 감사(`WEEKLY_THEME_*`). 게시 검사 실패 `422 WEEKLY_THEME_PUBLISH_INCOMPLETE`는 코드만 전달
- **학생 삭제**: 삭제 확정 트랜잭션에서 `mission_daily_usage` 삭제(P09). `payment_premium_usage`는 거래 기록이라 유지
- **위치**: 집계·한도 확인·삭제는 `usage` 패키지. `learning` 패키지는 DB·JDBC·`@Transactional`을 쓰지 않음(`test_learning_openapi.py`)
- **배포 후 확인**: `scripts/verify_cd_deployment.py`는 평일 오늘 `OPEN` 문제를 `THEME_DAY`로, 주말은 마무리한 문제를 `THEME_REVIEW`로 시작([CD README](../../infrastructure/cd/README.md) D)
- 마이그레이션 V34. 운영 무료 상품 값은 `infrastructure/aws/set-free-product-daily-missions.sql`
- 테스트: `WeeklyThemeProxyIntegrationTest`, `PaymentIntegrationTest`, `scripts/tests/test_weekly_theme_contract.py`

## 14. 참여 포인트·꾸미기 해금 (#389)

P21·P22의 core `reward` 도메인. 계약은 [API 명세](../design/api-spec.md) 2.8·2.10·3.12, 저장은 [ERD 3.5.1](../design/erd.md#351-포인트꾸미기-p21p22-389)(V35). 결제와 패키지·테이블을 나눔(포인트는 돈이 아니고 환급 경로가 없음).

### 결정과 근거

- **적립 진입점 하나(`RewardService.earn`)**: 규칙 조회 → 학생 활성 확인 → 잔액 잠금 → 같은 사건 확인 → 하루 상한 → 원장 1행 + 잔액 갱신. 적립하지 않은 이유(`DUPLICATE`·`DAILY_CAP_REACHED`·`RULE_INACTIVE`·`STUDENT_UNAVAILABLE`)는 예외 없이 결과로 돌려 학습 응답을 막지 않음. `REQUIRES_NEW`
- **멱등은 사건 키 UK**: `(student_id, event_type, source_key)`. 저장 실패 뒤 같은 사건 재요청·주간 테마 조회 때 같은 `earn`을 다시 부르는 것으로 보충(재시도 큐·Outbox 없음)
- **하루 상한은 횟수, KST 자정 경계**: 운영이 점수를 바꿔도 "하루 반응 다섯 번"의 뜻 유지
- **잠금 순서 학생 행(공유) → 잔액 행(배타)**: 학생 삭제 확정은 학생 행을 `FOR UPDATE`로 잡으므로, 삭제와 겹치면 삭제가 끝난 뒤 `ACTIVE`가 아님을 보고 멈춤. 같은 학생의 적립·해금은 잔액 행으로 직렬화
- **해금 이중 방어**: `Idempotency-Key`(같은 요청 재전송) + 해금 PK `(student_id, item_key)`·원장 UK(다른 키로 보낸 같은 해금). 재요청은 "이미 해금 200"
- **테마·캐릭터는 코드 상수, 아이템만 테이블**: 값 목록이 V23 CHECK·웹 상수와 묶여 있음. 관리자 아이템 `code`는 `^[A-Z0-9_]{3,40}$`라 `THEME:`·`COMPANION:` 키와 겹치지 않음
- **판매 중단**: 영구 해금이라 해금한 학생 목록에는 `onSale:false`로 남고 계속 착용
- **잠금 전 선택 이관**: V35가 기존 유료 테마·캐릭터 선택을 `ledger_id` NULL 해금 행으로 옮김(차감·원장 기록 없음)
- **`equipped` 생략은 유지**: 웹은 테마·캐릭터만 바꿀 때 `equipped`를 보내지 않음. 비우려면 슬롯을 null로
- **학부모 조회**: 포인트는 학습 원문이 아니라 #206 공개 설정과 무관하게 연결 학부모가 조회
- **학생 삭제**: `StudentLookService.clear`가 착용 → 해금 → 원장 → 잔액을 같은 트랜잭션에서 삭제

### 적립 연결

`ParticipationRewardService` 한 곳에 모아 각 프록시 경로는 사건 확인 뒤 한 줄로 부른다.

| 사건 | 부르는 곳 | 조건 | 사건 키 |
|---|---|---|---|
| 학습 완료 `MISSION_COMPLETED` | `LearningProxyService.reflection` | 돌아보기 저장 2xx 또는 `409 ATTEMPT_CLOSED` 뒤 learning 시도 상세가 `COMPLETED` | 시도 상세 `mission.id` |
| 공유 `COMMUNITY_POSTED` | 같은 곳 | 공유 응답 201·200 | `postId` |
| 반응 `REACTION_GIVEN` | `CommunityService.react` | 반응 남기기 2xx(취소는 적립 없음) | `postId:reaction` |
| 되돌아보기 `REVIEW_VIEWED` | `LearningProxyService.reviewViewed` | 열람 기록 200 | 그 주 월요일(KST) |
| 개근 `THEME_COMPLETED` | 같은 곳·주간 테마 조회 | 응답 `completed:true` | 그 주 월요일 |
| 당일 풀이 `THEME_ON_TIME`·주간 완주 `THEME_FINISHED` | `LearningProxyService.weeklyTheme` 조회 보충 | 18절 | `weekStart:day`, `weekStart` |

- **응답을 바꾸지 않음**: 응답 해석·`earn` 실패는 로그만 남기고 던지지 않음. 적립 결과는 `GET /students/me/points`로 확인
- **학습 완료 미션은 시도 상세로 확인**: 돌아보기 응답에 미션 ID가 없어 저장 뒤 `GET /internal/attempts/{id}`를 한 번 더 호출. 다시 풀기는 같은 미션 키라 적립 없음(P21 미션당 최초 1회)
- **보충**: 같은 돌아보기 재요청(`409 ATTEMPT_CLOSED`)에도 학습 완료·공유 적립을 다시 시도. 주간 테마 조회는 이번 주 요일 문제 중 완료한 미션만 보충하고 추가 문제(EXTRA)는 응답에 없어 보충하지 않음. 되돌아보기 열람 보충은 열람 재요청으로만
- 커뮤니티 작성자 표시에 착용 네 슬롯(`look.equipped`) 추가
- 테스트: `RewardIntegrationTest`, `RewardEarnIntegrationTest`, `LookUnlockMigrationTest`, `scripts/validate_reward_contracts.py`

## 15. 테마 초안 관리자 프록시·이야기 열람 프록시·사용량 THEME_DRAFT (#439)

에픽 #436(주간 테마 LLM 생성과 시작·종료 화면)의 core 몫. 계약은 api-spec 2.8·2.11·4.1.

- **관리자 경로**: `/admin/theme-drafts`(요청·목록·상세·adopt·discard·regenerate, CONTENT)를 미션 초안(#355)과 같은 방식으로 learning에 전달. 본문 값 검사와 상태 전이는 learning 소유. `status`·`source`·페이지 밖 값은 learning 호출 전 400
- **감사**: 요청 감사 → learning 1회 → 결과 감사(`THEME_DRAFT_*`). 채택은 만든 테마 `themeId`(`WEEKLY_THEME`, `detail.draftId`)가 대상이라 이후 `WEEKLY_THEME_*` 감사와 이어짐. 응답에 대상 ID가 없으면 `UNKNOWN` + `503 LEARNING_INVALID_RESPONSE`, 다시 부르지 않음
- **이야기 열람** `POST /students/me/weekly-theme/story-views`: 학년·KST 날짜는 core가 정하고 본문은 `{kind: INTRO|OUTRO}`만 다시 만들어 전달. 요일·주 1회 멱등 판정은 learning. 포인트 적립 없음
- **학년별 테마(에픽 #436, #438 뒤 머지)**: core가 학생 학년 그대로 `grade=G{학년}`(`G3`~`G6`, 중학생은 #432대로 `G6`)을 넘긴다. 이번 주 테마·되돌아보기 열람·이야기 열람 세 경로가 같은 `themeQuery`(#485 `sundayTheme` 포함)를 쓴다. 관리자 주간 테마 목록 필터도 `grade`(`G3`·`G4`·`G5`·`G6`), 테마 초안 요청 본문 `grade`는 learning이 검사(core는 JSON object만 확인). learning은 전환 기간에 `gradeBand`도 받아 `G3_4`→`G3`, `G5_6`→`G5`로 읽는다(core 머지 뒤 제거 요청)
- **이미지 URL**: learning이 준 값을 core가 바꾸지 않고 전달
- **사용량**: `THEME_DRAFT`·`THEME_IMAGE`를 이벤트 스키마·core `CallType`·OpenAPI·ERD·ai/scoring 발행 목록에 같은 순서로 추가(V40). 이미지 호출은 토큰이 없어 `cost_usd` null, `unpricedCalls`로 집계
- 테스트: `AdminOperationsIntegrationTest`, `WeeklyThemeProxyIntegrationTest`, `scripts/tests/test_theme_drafts_contract.py`(learning OpenAPI에 경로가 올라오면 3자 대조가 켜짐)

## 16. 리포트 고정 대화·참여 포인트·커뮤니티 신고 실서버 확인 (#424, 2026-11-10)

local kind에서 테스트 계정으로 core 공개 API를 실제 호출해 확인. 프리미엄은 결제 완료와 같은 모양의 구독 행을 kind DB에 넣음.

- 리포트 고정 대화: 학부모 원문 공개 전에는 403 `STUDENT_RECORDS_PRIVATE`, 켠 뒤 201·그날 범위 고정. "오늘 …" 질문이 같은 날짜인데도 `DIFFERENT_PERIOD` 되묻기 → #454
- 사용량: 질문마다 `CONVERSATION` 1건(되묻기 포함)
- 포인트: 미션 완료 +10, 공유 +5, 반응 +1, 해금 차감·착용 저장. 착용 아이템이 캐릭터에 그려지지 않는 것은 웹 미구현 → #455
- 커뮤니티 신고: 접수 → `IN_REVIEW` → `RESOLVED`. `RECEIVED`에서 바로 `RESOLVED`는 409 `SUPPORT_STATE_CONFLICT`
- 미확인: 되돌아보기 열람·개근 적립(주말·5일 연속 학습 필요)

## 17. 리포트 설명 사용량 REPORT_EXPLANATION·설명 모델 등록 (#480, 2026-11-10)

에픽 #473(설명 sLLM)의 core 몫.

- `GET /admin/ai-usage?callType`과 `llm.usage.recorded` 이벤트에 `REPORT_EXPLANATION` 추가(V42). 설명 항목 1개당 sLLM 1회라 답변 하나에 최대 2건
- 클러스터 안 CPU sLLM이라 토큰 단가 없음. `cost_usd` null, `unpricedCalls`로 집계
- **모델 레지스트리 코드 변경 없음**: 이름·scope가 자유 형식이라 `MODEL` `report-explanation`, scope `explanation/grade-{학년}/{narrative|essay}`를 그대로 등록·승인·복귀 가능
- 호출 종류를 더할 때는 이벤트 스키마·core `CallType`·core OpenAPI·ERD Mermaid 주석·ai/scoring 발행 목록·`ck_llm_usage_call_type` 마이그레이션·web `callTypeLabel`·MSW 필터를 함께 고침(`test_admin_mission_drafts_contract.py`가 목록 7곳 대조)

## 18. 무료 테마 주 5문제·추가 문제 프리미엄 전용·프리미엄 일요일·당일 풀이·주간 완주 포인트 (#485, 2026-11-10)

주간 테마 규칙 개정(#483)의 core 몫. 문제 공개·엔딩·일요일 닫힘 판정과 당일 풀이·개근·주간 완주 값은 learning #484가 정하고, core는 상품으로 무료·프리미엄을 판단해 learning에 넘기고 learning 응답으로 포인트를 적립한다. 13·14절과 다른 부분은 이 절이 우선한다.

### API 변경

| 경로 | 변경 |
|---|---|
| `POST /missions/{missionId}/attempts` | 무료 `THEME_DAY`를 하루 한도에서 뺌. 무료 `EXTRA`는 `403 PREMIUM_REQUIRED`. learning 쿼리에 `sundayTheme=true\|false` 추가 |
| `GET /students/me/weekly-theme` | learning 쿼리에 `sundayTheme`. 200 뒤 당일 풀이·개근·주간 완주 적립 보충(응답 본문 그대로) |
| `POST …/review-views`·`story-views` | learning 쿼리에 `sundayTheme` |
| `GET /students/me/points`·`GET /children/{childId}/points` | `items[].eventType`에 `THEME_ON_TIME`·`THEME_FINISHED` |

### learning과 맞춘 계약

| 방향 | 이름 | 뜻 |
|---|---|---|
| core → learning | 쿼리 `sundayTheme` | 시도 시작·주간 테마 조회·열람 기록에 항상 붙임. KST 일요일이고 상품이 허용할 때만 `true` |
| learning → core | `days[].completedOnDay` | 그 요일 문제를 그 요일 KST 안에 학습 완료(당일 풀이) |
| learning → core | `completed` | 월~금 모두 당일 풀이(개근). 새 칸 `perfectAttendance`가 아니라 기존 칸(#506) |
| learning → core | `finished` | 토요일 23:59(KST)까지 다섯 문제 학습 완료(주간 완주) |

learning이 위 칸을 주지 않으면 core는 그 적립만 건너뜀(boolean `true`일 때만 적립). 모르는 쿼리는 무시되므로 배포 순서와 무관.

### 결정과 근거

- **무료 한도**: `THEME_DAY`·`THEME_REVIEW`는 상품 조회·한도 확인 없이 통과. 무료 "테마 문제 주 5개"는 learning 누적 공개가 곧 상한이라 core가 세지 않음. `mission_daily_usage`·`limits.dailyMissions`는 무료 상품에서 `EXTRA`를 다시 켤 때의 하루 한도로만 남김
- **추가 문제 프리미엄 전용**: 코드 분기는 그대로 두고 V43이 무료 상품 `features.extraMissions`를 `false`로. 프리미엄 `EXTRA` 신규 시도는 `EXTRA_MISSION` 프리미엄 사용으로 기록
- **값이 없을 때**(`extraMissions`·`sundayTheme` 공통, #506): 무료는 거부, 구독 중은 허용. 구독은 결제 시점 상품 스냅숏을 써서 기존 스냅숏에 값이 없기 때문. boolean이 아니면 503 `PAYMENT_PRODUCT_UNAVAILABLE`. 무료 상품을 새로 만들 때는 값을 명시(`set-free-product-daily-missions.sql`이 함께 넣음)
- **일요일만 상품 조회**: 평일 조회·시작에 결제 조회 실패 경로를 만들지 않으려고 일요일이 아니면 `false`를 넘김. 일요일 조회·열람 기록은 상품 확인이 실패해도 `false`(닫힘)로 넘기고, 시도 시작은 503
- **일요일 거부는 learning**: `sundayTheme=false`로 learning이 판정, core는 오류 전달
- **포인트 사건**: `THEME_ON_TIME`(+5, 키 `weekStart:day`)·`THEME_FINISHED`(+10, 키 `weekStart`) 추가. 개근 +30은 기존 `THEME_COMPLETED`. 매일 푼 학생 50+25+30+10 = 115점, 몰아 푼 학생 50+10 = 60점. 값은 `reward_rule` 행
- **적립 시점**: 일요일이 닫혀 되돌아보기 열람이 줄므로 주간 테마 조회 200마다 `completedOnDay`·`completed`·`finished`를 읽어 사건 키로 보충. 주간 완주는 이 조회 보충으로만 적립(열람 응답에서는 읽지 않음)
- **`weekStart`**: 주간 테마 응답 값 사용. 월요일이 아니면 새 사건 적립만 건너뜀
- **마무리한 당일 문제 재시작**: 무료 `THEME_DAY`를 한도에서 빼면서 열린 경로. learning #484에서 409로 막기로 함(구현 전까지 허용)
- **E2E 무료 상품**: `frontend/web/tests/e2e/seed/core.sql`은 무료 `{"extraMissions":true,"sundayTheme":false}`(학습 여정 E2E가 무료 학생으로 `EXTRA`를 풀기 때문)
- web: `POINT_EVENT_LABELS`에 두 사건 추가(모르는 사건 종류는 내역에서 걸러짐). 당일 풀이·주간 완주는 learning #484가 값을 내보낼 때까지 "준비 중" 표시

마이그레이션 `V43__theme_free_limit_and_daily_points.sql`. 테스트: `PaymentIntegrationTest`, `WeeklyThemeProxyIntegrationTest`, `RewardEarnIntegrationTest`. 남은 확인: 병합 후 kind에서 learning과 함께 한 주 흐름.

## 19. 지식 임베딩 사용량 KNOWLEDGE_EMBEDDING (#467, 2026-11-11)

에픽 #463(지식 RAG)의 core 몫. ai 임베딩 API([ai 16장](ai.md#16-지식-임베딩-api-467-2026-11-11))가 요청마다 발행하는 사용량을 받는다.

- `GET /admin/ai-usage?callType`과 `llm.usage.recorded` 이벤트에 `KNOWLEDGE_EMBEDDING` 추가(V44). 지식 적재·관계 후보·검색 질의 임베딩을 한 종류로 셈(요청 1회 = 본문 최대 64개 = 1건)
- 임베딩은 입력 토큰만 있어 ai가 `outputTokens = 0`으로 보냄. 단가(`app.llm-pricing.text-embedding-3-small.input`)를 넣기 전에는 `cost_usd` null
- 같은 CHECK를 넓히는 #439 후속 `THEME_VIDEO`는 이 V44 다음 번호인 V45로 옮겼다(25절)

## 20. 리포트 설명에 필요한 프로필·열람 경계 (#479, 2026-11-10)

- SYSTEM 전용 `GET /internal/students/{studentId}/profile`에 `grade` 추가(report가 설명 대상 학년을 임의로 정하지 않도록). 기존 검사와 `no-store` 유지
- 공개 리포트 상세의 `explanations`는 report 계약대로 전달하되 무료 이용권·원문 비공개이면 null로 가림. 인용 `quote`는 null 허용

## 21. 신고·문의·공지·도움말 (#46)

계약은 [API 명세](../design/api-spec.md) 2.7·2.8·5.7·5.12·5.14, 원문 보기·정정 흐름은 [사용자 흐름](../design/user-flow.md) 6장.

- 기존 신고 `student_id`는 대상 학생이며 요청 역할을 구분하지 못하고 문의는 `user_id`만 있어 V16(구 V14)에 요청 역할·학생 주체를 분리. 기존 이력에 역할을 추정하지 않음
- 학생 결과는 본인 목록/상세에서 확인하며 보호자 계정 알림에 보내지 않음. 보호자 결과만 #44 알림(NotificationStored/커밋 후 Redis) 재사용
- 호출 경계: SupportController → SupportService → SupportRepository/SupportMapper → core_db. 대상 검증은 StudentAccessService(연결·동의), ConversationSupportService(본인 완료 메시지), ReportSupportService(완료 리포트), LearningSupportClient → 기존 LearningClient → InternalRestClientFactory(내부 토큰·검증된 컨텍스트·타임아웃·서킷)
- 원문: 저장된 attemptId/studentId → learning HTTP → 학생/시도 일치 검사·draft/memo 제외 → audit_log 별도 트랜잭션 성공 → 응답. 다른 attemptId query는 원문 대상을 바꾸지 않음
- 정정: 신고 행 잠금으로 단일 의도 저장 → 잠금/트랜잭션 종료 → 고정 correction UUID를 learning `Idempotency-Key`로 호출 → 신고 행 재잠금 → 공급자 결과·이전 결과·영향·완료·감사·알림 저장. HTTP 오류는 FAILED, core finalize 실패는 이전 의도 유지. 관리자 정정 요청은 신고 UUID를 공개 Idempotency-Key로 사용해 새로고침·재진입 후에도 같은 요청으로 재개
- 알림: support → `NotificationService.support` → 기존 insert(수신 설정·유일성) → 커밋 후 Redis. 비활성 계정·철회 동의·해제 자녀는 생성하지 않음. sourceEventId는 신고/문의 ID, 원문 없는 완료 안내만
- 공지: 등록/수정/종료 전후를 audit_log에 보존하며 DELETE는 `ended_at`만 기록. help/notices는 인증 필요(PublicAuthFilter 공개 예외에서 제거)
- ANALYSIS/REPORT 대상 정정은 공급자 계약이 없어 422 `CORRECTION_TARGET_UNSUPPORTED`
- 대상 `COMMUNITY_POST`(P20·P10, #388): 접수 즉시 숨김, 처리 결과로 다시 공개 또는 계속 숨김, 원문 열람 감사. 결정은 23절
- FN-ADM-22·23(#387·#389·#395): 관리자 주간 테마(learning 프록시, 미션과 같은 작성→검토→게시)·꾸미기 아이템(core 소유) 관리, CONTENT 권한·`audit_log`

### 정정 impact 의미

- `impact.aggregation`은 학습 수치 집계 반영 여부. 개별 기록 상세의 판정 표시는 조회 시 최신 정정 적용 규칙
- APPLIED=반영 확인, NOT_APPLIED=반영하지 않았음을 확인(집계가 판정 결과를 쓰지 않아 변경 대상이 없는 경우 포함, 오류 아님), UNKNOWN=확인하지 못함. conversation/report UNKNOWN 허용
- 모든 impact가 UNKNOWN이어도 공급자 정정이 성공이면 core는 RESOLVED 저장 가능. 파생 결과까지 반영됐다고 표시하지 않음
- 공급자(learning #80) 계약: 내부 토큰·ADMIN·단일 대상 학생 scope·X-User-Id 검사. DONE 이전 409, 같은 reportId의 다른 키 409, 같은 키의 다른 본문 422, 같은 키·본문은 최초 응답 재현. 원판정·원본 답변 불변
- 관리자 화면은 raw impact JSON 대신 분석 대화·학습 수치 집계·리포트별 확인 상태를 구분 표시

### 정정 영향 판정과 표시 (#244)

| 항목 | 내용 |
|---|---|
| 값 | `conversation`·`report`에 `AFFECTED`/`NOT_AFFECTED` 추가(이슈), 조회 실패는 `UNKNOWN`. `aggregation`과 learning→core 응답 값은 그대로 |
| 계산 | core가 정정 성공 후 트랜잭션 밖에서 조회(`SupportService.correct`). 조회 실패는 정정 성공을 막지 않고 다시 조회하지 않음 |
| 기록 | `correction.impact`에 값과 `reportIds`·`messageIds`·`conversationIds`. 마이그레이션 없음(ERD: `correction`이 영향 범위 기록) |
| 영향 있을 때 동작 | 정정 표시(사용자 결정). 재생성 안내·자동 재생성 안 함. 학부모 재생성은 리포트당 1회라 정정 때문에 쓰게 하지 않음 |
| 요소 지표 | 정정된 판정은 새 리포트의 요소 지표(FN-RPT-05)·일일 요소 표시에서 제외. 정정은 결과만 바꾸고 요소는 원판정 그대로이기 때문. learning 기록 응답의 `judgment.corrected`로 판단, 제외 경로는 `HELD`와 같음 |
| 표시 | 리포트 상세·대화 답변의 `correctionNotice`. 내용은 그대로, 재생성한 새 판은 리포트 ID가 달라 표시 안 됨 |
| 리포트 찾기 | 시도 ID로 찾음. 보호자 공유가 꺼지면 근거 연결을 저장하지 않고(`record_generator`), 일일은 인용이 없으면 근거 연결이 없음. 주간 `THINKING_TYPE.missions`·일일 `PROBLEM`의 `attemptId`는 공유가 꺼져도 남음 |
| 대화 찾기 | 정정한 판정의 답변 ID(기존 `GET /support/attempts/{attemptId}`)로 `message_evidence.answer_id`(`ANSWER`) 조회 + 영향받은 일일 판의 고정 대화 전체(인용 기록 없이 질문마다 고정 판을 다시 읽음, #392) |
| 노출 | `impact`는 관리자 응답에만. 신고자 응답은 `null`(학생 신고자에게 학부모의 리포트·대화 정보가 가지 않게) |

- 이슈와 다른 점: 일반 대화는 이슈대로 판정의 답변 단위로 찾지만, 리포트는 시도 단위로 찾고(공유가 꺼진 판은 근거 연결이 없음) 고정 대화는 대화 전체를 대상으로 함(위 이유). 이슈 확인 필요의 값 계산 주체는 작업 위치대로 core, report에는 조회 API 하나 추가. 요소 지표 제외는 이슈 할 일에 없지만 설계(FN-RPT-05)가 #244 몫으로 정해 포함, 작업 위치에 없던 learning `judgment.corrected`도 그래서 추가
- 이슈 범위 밖: 자동 재생성, 학부모 재생성 안내
- 프론트 담당 확인(2026-11-09): `correctionNotice`·`corrected`는 선택 필드로 읽음, 신고자 `impact: null` 문제없음, 관리자 문구는 영향과 반영을 구분. 리포트 문구 끝에 "최신 결과는 학습 기록에서 볼 수 있습니다"를 붙이자는 선택 제안은 학부모 학습 기록 화면이 판정을 표시하지 않아 넣지 않음. core의 impact 코드 검사(`LearningSupportClient`)는 learning 응답만 보므로 새 값을 넣지 않음
- 그대로 둔 것: 학생 피드백 화면의 요소 표시, 주간 테마 재시도 비교(#207)의 요소 값
- 한계: 리포트는 같은 시도의 다른 답변을 정정해도 표시될 수 있음, 조회 실패 건은 표시되지 않음, 정정 순간 생성 중인 리포트는 빠질 수 있음, 다운로드 파일에는 문구 없음, 일반 분석 대화는 인용한 답변만 찾음

### learning 공급자 오류의 공개 표시 (#46·#163)

| 경로 | learning 응답 | core 공개 응답 |
|---|---|---|
| 정정 POST | 409 / 422 | 409 `SUPPORT_CORRECTION_CONFLICT` / 422 `SUPPORT_CORRECTION_REJECTED` |
| 지원 target·original GET | 정상 Problem Details 403 / 404 | 같은 상태·공통 코드(`FORBIDDEN`·`NOT_FOUND`)와 고정 문구 |
| 관리자 미션 | 정상 404 `NOT_FOUND` | 고정 문구 404. 불명확한 404·405·501은 503 `ADMIN_MISSIONS_UNAVAILABLE`, 409·422 allowlist와 정제한 `missingFields` 유지 |
| 그 밖의 비-2xx / 잘못된 2xx / 전송 실패 | — | 503 `SUPPORT_DEPENDENCY_UNAVAILABLE` / 502 `SUPPORT_INVALID_RESPONSE` / 기존 `LEARNING_*` |

- "정상 Problem Details"는 `application/problem+json` JSON 객체·HTTP와 일치하는 정수 status·허용 문자열 code. 오류 원문·내부 URI·공급자 trace·임의 code는 공개하지 않음. 신규 공개 코드 없음
- 최초 정정 POST도 대상 GET으로 사전 확인하므로 403/404가 공개될 수 있고, 이때 정정 의도·공급자 호출·완료 알림을 만들지 않음. 공급자 실패 시 정정 FAILED·신고 IN_REVIEW·완료 알림 없음
- `FORBIDDEN`은 learning의 학생 범위·역할·scope 형식 거부를 구별하지 못하고 `NOT_FOUND`는 경로 부재와 리소스 부재를 완전히 구별하지 못함(존재 여부 정보 차이 포함해 승인)

### 관리자 공지 전체 목록 (#242)

- `GET /api/v1/admin/notices?status&role&page&size`. 권한은 쓰기 API와 같은 `SupportAccessService.admin`(ADMIN + SERVICE_OPS). 권한 검사가 입력 검사보다 먼저라 권한 없는 요청은 값이 잘못돼도 403(#277)
- 응답은 `GET /notices` 항목과 공통 목록 봉투 `{items,page,size,totalElements}`(OpenAPI `SupportNoticePage`), 상태 필드 추가 없음
- 상태는 조회 시각으로 계산: `SCHEDULED` 종료 기록 없음·공개 시작 전, `ACTIVE` 사용자 GET 공개 조건(`ended_at IS NULL`·`visible_from <= now < visible_to`), `ENDED` 종료 기록 있음 또는 기간 지남(구분은 `endedAt`). 웹 `domain/admin/service.ts`의 `noticeStatus`도 같은 규칙
- 역할 필터는 `target_roles` 포함, 정렬 `visible_from DESC, id DESC`. 원문·개인정보가 없어 조회 감사 없음, 마이그레이션 없음

## 22. 관리자 운영 (#47)

- 설계: controller → admin service → 기능별 operations service → 각 소유 테이블 repository. execution/audit은 admin repository가 조회. learning 통계/미션은 learning 기능 service → 기존 LearningClient. 다른 서비스 DB를 조회하지 않음. 큐는 읽기 전용 RabbitMQ 관리 HTTP(별도 환경 변수)
- PublicAuthFilter는 overview/audit GET 두 경로만 ADMIN 역할로 개방. 관리자 응답은 프론트 목업의 `updatedAt`·`errorDetail` 등을 만들어 채우지 않음
- 알림 재처리(NOTIFICATION)는 기존 publisher/DeliveryService 호출, Redis 발행은 트랜잭션 밖. 200 결과 계약. Redis 발행 확인까지이며 브라우저 수신 보장 아님. 프로세스 중단으로 RUNNING 이력이 남으면 자동 재실행하지 않음. 공통 IdempotencyService의 24시간 응답 저장 재사용(5xx 미저장)

### REPORT 재처리 (#47·#152)

- 같은 jobId로 Outbox만 다시 넣어도 report job 멱등성과 core 종료 상태 때문에 실행되지 않으므로 새 jobId·ADMIN_RETRY로 접수. report 쪽 처리는 [report](report.md) 12장
- 원작업당 직접 자식 1개, 재실패 시 그 자식에서 다음 재처리. 관계는 V17
- 응답 202 `{originalJobId,jobId,type:REPORT,status:QUEUED,acceptedAt}`, Location은 새 작업 조회 URL. 화면은 '접수'로 표시하고 새 jobId GET으로 진행/완료/실패 확인. 원작업 상세의 `retryJobId`, 새 작업의 `retryOfJobId`를 이동 링크로. 이미 연결된 원작업은 `REPORT_ALREADY_RETRIED`
- 종료 감사: `ReportJobOutcomeRecorded` 내부 이벤트를 정상 종료·#132 복구·삭제의 조건부 전이가 실제 반영된 때에만 발행(reportId 없는 실패 포함). 감사는 BEFORE_COMMIT으로 소비하며, 삭제 결과 감사가 실패하면 학생 차단·삭제 요청·작업 종료·실행 이력도 함께 롤백. 중복·지연 결과는 감사를 추가하지 않음
- 접수 후 학생 삭제로 report 소비자가 생성을 막은 queued 작업의 정리 정책은 후속 검토

### CONVERSATION 재처리 (#47·#67·#162)

- 관리자 백그라운드 실행, 공통 분석 경로·권한/한도·감사/복구, 새 요청 테이블 V19. 기존 jobId의 Location
- 사용량 차감과 DB가 단일 원자 트랜잭션이 아니므로 요청 ID 표식으로 중복 차감 방지, 접수/실제 실행 이력 구분. 최초 202도 DB 저장값으로 반환(재접수 응답과 timestamp 정밀도 일치)
- 202 후 core 강제 종료 시 새 프로세스에서 1회 실행, 실행 중 종료는 대기 시각 경과 후 FAILED 이력/감사 1회로 복구
- `OperationRetryService`가 인증된 관리자 identity를 두 접수 서비스에 전달. 202 OpenAPI는 REPORT/CONVERSATION oneOf

### 관리자 미션 프록시 감사 (#47)

- learning 관리자 미션 10종 프록시. 실제 404 전달, 필터와 무관한 전체 상태 counts(`missionCounts`·`missionInclusionRule`)
- HTTP 전 REQUESTED를 짧은 독립 트랜잭션으로 남기고 응답 후 SUCCEEDED/REJECTED/UNKNOWN 기록. 프로세스 중단·결과 감사 저장 실패에는 REQUESTED만 남을 수 있어 변경 성공 여부는 learning에서 대조. 요청·오류 원문 미저장, 자동 재요청 없음
- 감사 저장 실패 시 503 `MISSION_AUDIT_UNAVAILABLE`(learning 변경은 이미 반영됐을 수 있음)

### 검증 범위

core 통합 테스트(실제 JWT/MVC/PostgreSQL·Redis·RabbitMQ)로 권한·기간·목록·민감 문자열 제거, 같은 키 응답 재현·다른 키 동시 실행 방지, 실행/감사 원자 저장, 트랜잭션 밖 발행, REPORT·CONVERSATION 재처리 경합·복구를 확인. 관리자 운영 응답 5종은 [testing-ci](testing-ci.md) 1장 계약 CI에서 공개 스키마와 대조. 실제 report-worker를 포함한 관리자 POST → 생성 파이프라인 E2E와 실제 외부 LLM 호출은 미검증.

## 23. 커뮤니티 공유물 신고 연결 (#388, P20·P10)

- 접수: 기존 `POST /error-reports`에 `targetType: COMMUNITY_POST`, `targetId: postId`(유형 5종 그대로). 학생 세션만 받고 학부모는 400. learning `GET /internal/community/posts/{postId}`로 대상을 확인해 본인 글 409 `COMMUNITY_OWN_POST`, 없거나 볼 수 없는 글(설정·검토 숨김, 작성자 비공개) 404 `COMMUNITY_POST_NOT_FOUND`
- 신고 행: `student_id`·`requester_student_id`는 신고한 학생, `attempt_id`는 NULL. 작성자 학생 ID를 core 신고 행에 남기지 않아 기존 본인 목록·상세 권한 검사(`student_id ∈ scope`)를 그대로 쓰고, 작성자 삭제로 신고 이력이 깨지지 않음
- 숨김: 신고 행 저장 뒤 트랜잭션 밖에서 learning `moderation {status: HIDDEN_REPORT, errorReportId}`. 실패해도 접수는 201로 두고 기록만 남김. 같은 멱등 키 재전송·검토 처리 때 다시 보냄. 그 사이에도 core 목록·반응은 신고 행(접수·처리 중, 또는 처리 결과가 `VISIBLE`이 아님)으로 그 공유물을 바로 숨김
- 처리: 기존 `PATCH /admin/error-reports/{id}`(SERVICE_OPS). `RESOLVED`로 바꿀 때 `reviewResult`는 `VISIBLE`(다시 공개)·`REMOVED`(계속 숨김)만, 생략하면 `REMOVED`(현재 관리자 화면 #395는 결과를 보내지 않아 계속 숨김이 기본). 같은 공유물에 신고가 여럿이면 계속 숨김이 하나라도 있으면 `REMOVED`, 처리 중이 있으면 `HIDDEN_REPORT`, 모두 다시 공개일 때만 `VISIBLE`을 보냄. 정정(`corrections`)은 판정만이라 422 그대로
- 원문 열람: 관리자 상세에 `linkedPost {postId, available, missionId, status, answer, authorStudentId}`. 열람마다 `SUPPORT_ORIGINAL_VIEW`(`ERROR_REPORT`, detail `postId`·`available`) 감사. 파기된 공유물은 `available: false`만
- 학생 결과 알림은 기존처럼 보호자 계정에 보내지 않음(학생 본인 목록에서 확인)
- 검증: core `CommunityIntegrationTest`(실제 JWT·MVC·PostgreSQL, learning만 내부 계약 가짜 서버)로 접수 즉시 숨김·같은 키 재전송·learning 반영 지연 중 core 숨김·다시 공개·계속 숨김·복수 신고·원문 열람 감사를 확인. 실제 learning #386과의 연동은 미검증
- 후속: 관리자 화면(#395)에 다시 공개·계속 숨김 선택과 `linkedPost` 표시 추가 필요. learning #386 `moderation`·`GET posts/{id}` 구현과 응답 모양 대조 필요

## 24. 결제·구독과 상품 권한 (#48·#184·#419)

토스페이먼츠 테스트 환경만 연동(실결제 키는 네트워크 호출 전 거부). 계약은 [API 명세](../design/api-spec.md) 2.6·3.5, 상태는 [상태 다이어그램](../design/state-diagram.md) 6장, 저장은 [ERD](../design/erd.md) 3.4.

### 24.1 공개 기능과 호출 경계 (#48)

- 상품 목록, 주문 생성, 서버 승인, 본인 결제·구독·환불 이력, 빌링 등록/변경, 갱신 해지/철회, 정기 청구, 환불 요청·관리자 승인/반려, 관리자 거래/대조/환불 조회, 서명 웹훅
- Controller → payment service → Repository/Mapper → core_db. 다른 기능은 payment service만 사용하며 payment repository를 직접 참조하지 않음
- 주문의 구매자·현재 연결/동의·상품·확정 금액을 서버에서 검증. 승인 전에 주문 금액을 대조하고 PG 응답의 주문·paymentKey·금액·MID·KRW·상태 확인. 클라이언트 복귀 화면·웹훅 본문으로 성공을 결정하지 않음
- PAYMENT_VIEW와 PAYMENT_REFUND 구분. 환불 목록 GET은 PAYMENT_VIEW, 승인/반려 POST는 PAYMENT_REFUND

### 24.2 트랜잭션과 실패 복구

| 단계 | 처리 |
|---|---|
| 주문/승인 준비 | 공통 `AccountAccessService.lockParent`로 parent 계정 행 잠금 → 소유권·자녀·상품·금액 확인 → 상품 snapshot 및 charge intent/CONFIRMING 저장 → commit |
| 외부 승인 | DB 트랜잭션·parent 잠금을 해제한 뒤 저장된 PG 요청 식별자로 호출 |
| 승인 기록 | parent 재잠금 → 현재 거래/PG 응답 검증 → APPROVED/RECOVERY_REQUIRED 저장·commit |
| 권한 반영 | 별도 parent 잠금 트랜잭션에서 구독 생성/갱신·order 연결·APPLIED 저장 |
| 환불 | REQUESTED 동결 commit → learning 증빙 HTTP 조회 → parent 재잠금·조건 재확인 → 관리자 APPROVED/cancel key commit → 외부 PG 취소 → parent 재잠금·결과 반영 |

- 공통 IdempotencyService의 HTTP 캐시와 PG 거래 멱등성을 분리. HTTP 키가 달라도 동일 거래는 기존 intent 사용. 결제·환불 4xx는 같은 HTTP 키로 동일 결과, 5xx는 캐시하지 않음. 캐시된 202는 POST 재호출로 바뀌지 않으므로 GET 결제 상태로 현재 결과 확인
- 승인 응답 유실은 CONFIRMING으로 남고 PG 조회로 복구. 승인 기록 이후 권한 DB 저장 실패는 APPROVED/RECOVERY_REQUIRED를 유지하며 추가 청구 없이 재반영. 취소 응답 유실은 환불 APPROVED 유지 후 조회로 확정. PG에 기록이 없는 미확정 준비 거래는 성공/실패로 추측하지 않고 운영 대조. 지연 DONE은 REFUNDED/CANCELED를 되돌리지 않음
- PG·learning HTTP는 트랜잭션 밖. 준비 거래·권한 복구·미처리 환불은 #45 탈퇴를 차단하며 `pendingPayments`는 미처리 환불 수와 별도로 반환

### 24.3 상품·청구·해지

- 무료 상품은 `PAYMENT_FREE_PRODUCT_ID`로 명시(10/28 사용자 확정). 미지정·없음·비활성·0원 아님은 503. FREE 코드나 최신 0원 행을 추측하지 않음. 가격·features·limits는 product에서 읽고 주문/구독 snapshot으로 당시 조건 보존. 상품 데이터는 운영 입력(임의 시드 없음)
- 최초 결제일의 일자를 anchor로 보존하고 매월 같은 날(없으면 말일) KST 09시 청구. periodEnd는 다음 청구일 09시가 배타 경계(1/31 → 2월 말일 → 3/31). 최초 결제 뒤 빌링 등록 전은 autoRenew=false/nextBillingDate=null. 빌링 등록은 ACTIVE 및 유예 중 RENEWAL_FAILED에서 허용(유예·재청구 횟수 초기화 안 함)
- 월별 논리 주문 `(subscription_id,billing_period_start)` UK 유지. 확정 실패 후 일별 재청구만 새 charge attempt/PG 주문으로 기록(attempt마다 고유 PG 멱등키). 초기 실패 후 3일 유예·매일 1회 최대 3회 재청구, 불명확 attempt는 조회만. ShedLock과 DB UK/parent 잠금/last attempt date 병용
- 해지는 다음 청구를 중단하고 이미 결제한 기간 유지. PG 갱신 중 해지도 허용하며 늦은 성공 반영이 autoRenew=false를 덮어쓰지 않음. 유효 기간 전 ACTIVE 구독만 철회 가능. 빌링 발급은 외부 호출 전후 subscription.revision 대조
- 만료와 주요 결제·환불·구독 전이는 `NotificationService.payment`로 알림(기존 수신 설정·중복 방지·commit 후 Redis 전달 재사용)
- #45 복구 경계: 필수 동의 철회 후에도 본인 거래 GET·환불 POST·해지 DELETE 허용, 자녀 연결 해제 후에도 본인 구독 청구 중단 가능. 신규 구매/승인·빌링 등록·해지 철회는 현재 동의·연결 검사 유지
- 과거 snapshot/anchor가 없는 구독은 승인된 backfill 전 자동 청구하지 않음

### 24.4 사용 증빙·환불 조건

- 7일은 환불 요청 시각 기준, 전액만. 승인 시 요청 당시 기간·금액·사용을 다시 확인. REQUESTED는 새 프리미엄 사용의 동결 상태. 증빙 조회 실패는 503이며 미사용으로 간주하지 않음. snapshot/charge attempt가 없는 과거 거래도 사용 근거 불명확으로 차단
- `payment_premium_usage`가 FEEDBACK/CONVERSATION/REPORT_VIEW의 RESERVED/USED 증빙 소유. 미완료 예약을 미사용으로 간주하지 않음
- P14 개정(#387·#392, [기획 3절](planning.md#3-서비스-기획-방향-리텐션일일-리포트-2026-11-06-p20p25)): 프리미엄 추가 문제 시도 `EXTRA_MISSION` 종류를 추가하고, 일일 리포트 대화는 기존 CONVERSATION으로 기록. 배포 시점부터 기존 구독자 환불 판정에도 적용
- learning의 SYSTEM+정확한 학생 scope 증빙 API가 결제 이후 DONE 및 진행 중 피드백을 실제 learning DB에서 확인(MyBatis 캐시 없이 매번 조회, 원문 미반환)
- FeedbackFacade: 답변·시도 소유권 확인 → core 사용 예약 → 판정 리스/처리·DB commit → core 완료. 응답 유실은 예약을 남겨 보수적으로 판단
- core 예약·완료 409는 Problem Details `code`로 구분(#276). `REFUND_IN_PROGRESS`·`PAYMENT_USAGE_RETRY_REQUIRES_NEW_SOURCE`·`PAYMENT_USAGE_STATE_CHANGED`는 같은 코드 409와 코드별 학생 안내, 그 밖의 409는 `PAYMENT_USAGE_UNAVAILABLE` 503
- 환불 완료는 즉시 구독 종료·무료 전환. 반려는 사용 동결 해제

### 24.5 분석·리포트 권한 공급 (#41·#42)

- `ProductEntitlementService.forParent(parent,student)`: 현재 연결/동의 검사 후 product/features/limits, 구독 상태, autoRenew, periodEnd, graceUntil, refundPending, conversationEnabled, narrativeEnabled 제공. 유효 구독은 당시 snapshot 사용, 유예 동안 권한 유지. 미확정 갱신의 기간 만료를 임의 무료 전환으로 숨기지 않음
- `PaymentAnalysisEntitlementProvider`: #41 포트의 productId/dailyConversations/validUntil/conversationEnabled 공급. validUntil은 실제 KST 09시 경계. recordAttempt는 입장 트랜잭션에서 같은 parent 잠금으로 기록(재시도·실패 포함). 일별 사용 집계 저장은 `payment_premium_usage`([6절](#분석-대화-사용량-db-이관-구현-225))
- #387(P13 개정, 2026-11-08 확정): FREE `limits.dailyMissions` 3 → 1(당시 무료 `THEME_DAY`·`EXTRA` 신규 시작 합산, core `mission_daily_usage`). 2026-11-10 개정(#483, core #485 V43): 무료 테마 문제는 한도 없음, 추가 문제(`EXTRA`)는 무료 상품 `features.extraMissions = false`로 프리미엄 전용(값이 없으면 무료 거부·구독 중 허용 #506), 프리미엄 신규 `EXTRA`는 프리미엄 사용(`EXTRA_MISSION`)으로 기록. `limits.dailyMissions`는 무료 상품에서 `EXTRA`를 다시 켤 때의 무료 `EXTRA` 하루 한도로만 쓰며 값이 없으면 무료 `EXTRA`만 503 `PAYMENT_PRODUCT_UNAVAILABLE`. 운영 DB 무료 상품은 `infrastructure/aws/set-free-product-daily-missions.sql`로 한도·`extraMissions`·`sundayTheme`을 함께 넣는다. 유료 상품 `features.sundayTheme = true`(V43)는 프리미엄 일요일 테마 이용([core 보고서 13절](core-gateway.md#13-주간-테마-프록시무료-하루-1개추가-문제-프리미엄-387)). 일일 리포트 대화는 `dailyConversations`(30회)를 공유
- ReportEntitlementService: 과거 리포트에도 현재 권한 적용(10/28 사용자 확정). 무료 상세의 narrative/eveningQuestion은 null, 수치 유지. 기존 유료 파일은 현재 권한이 없으면 403 `REPORT_PREMIUM_REQUIRED`, 수치 전용 파일은 무료에서도 허용. URL 반환 직전 parent 잠금에서 권한과 사용 기록을 함께 확정
- 학부모 이용권 표시: `GET /api/v1/children/{childId}/entitlement`가 `forParent` 결과를 `Cache-Control: no-store`로 반환. 기본 무료 상품 미설정은 503 `PAYMENT_FREE_PRODUCT_UNAVAILABLE`, 구독이 없다는 이유로 임의 상품을 고르지 않음. 학부모 사이드바·대시보드 리포트 안내는 이 API의 상품명·한도·`narrativeEnabled`를 쓰고 `/children`의 목업 `plan`은 근거로 쓰지 않음. 자녀별 캐시 키, 오류는 이전 안내 대신 재시도 가능한 오류로 표시

### 24.6 PG 검증·운영 입력

- `POST /api/v1/webhooks/tosspayments`만 Bearer 예외. 원문:transmission-time의 HMAC SHA-256과 복수 v1 서명 검증, 두 테스트 상점 보안 키 지원. PG 조회 1회 후 실제 상태 반영, transmission ID와 상태 전이/알림 UK가 중복 차단
- 빌링 승인 시 웹훅이 전송되지 않으므로 조회 복구를 별도 실행
- 관리자 대조는 from/to 필수. 로컬 주문과 두 상점의 PG 거래 페이지를 비교해 MISSING_LOCAL/MISSING_PG/DUPLICATE/MISMATCH/UNKNOWN/MATCH/NO_PG_ATTEMPT 구분. 거래 목록 실패는 503, 자동 청구·취소 없음. 거래 조회 timeout 최소 60초
- 빌링 암호화: `PAYMENT_BILLING_ENCRYPTION_KEY`는 별도 무작위 32바이트 AES 키(base64), AES-GCM 저장. 카드 원문은 수신/저장하지 않음
- 하위 호출 서킷 브레이커(#167): toss-lookup과 toss-transactions 분리(일반/빌링 자격은 같은 구간 상태 공유). OPEN은 기존 Unknown/null로 연결해 상태 유지. 승인·청구·취소·빌링키 발급은 제외(PG에 보내지 않은 준비 거래는 조회만으로 확정 불가). 최근/최소 20건·실패율 50%·30초 차단·half-open 1건
- 공식 계약: [코어 API](https://docs.tosspayments.com/reference), [에러 코드](https://docs.tosspayments.com/reference/error-codes), [웹훅](https://docs.tosspayments.com/reference/using-api/webhook-events), [보안 점검](https://docs.tosspayments.com/reference/using-api/security-checklist), [빌링 연동](https://docs.tosspayments.com/guides/v2/billing/integration-api)

| 변수 | 사용 위치 |
|---|---|
| TOSSPAYMENTS_CLIENT_KEY | Vite가 공개 값만 `VITE_TOSSPAYMENTS_CLIENT_KEY`로 전달, `test_gck_` SDK 결제위젯 |
| TOSSPAYMENTS_SECRET_KEY | core 일반결제용 `TOSS_TEST_SECRET_KEY`가 비어 있을 때 서버 fallback |
| TOSS_TEST_SECRET_KEY | core 일반결제 서버 키(있으면 우선) |
| TOSS_TEST_BILLING_CLIENT_KEY | Vite가 공개 값만 `VITE_TOSS_TEST_BILLING_CLIENT_KEY`로 전달, 별도 빌링 상점 `test_ck_` |
| TOSS_TEST_BILLING_SECRET_KEY | core 빌링 전용 서버 키, 일반 결제위젯 키로 대체하지 않음 |
| TOSS_TEST_MID / TOSS_TEST_BILLING_MID | 해당 상점 ID, core가 PG 응답과 대조 |
| TOSS_TEST_WEBHOOK_SECURITY_KEY / TOSS_TEST_BILLING_WEBHOOK_SECURITY_KEY | 웹훅 서명 검증 |
| PAYMENT_BILLING_ENCRYPTION_KEY | 빌링키 암호화 |
| TOSSPAYMENTS_ENV_DIR | 별도 worktree에서 `.env`가 있는 원래 저장소 디렉터리를 Vite 실행 환경으로 지정할 때만 |

키를 바꾸면 Vite·core 재시작 또는 재빌드 필요. 문서 테스트 키 사용 시 주의 사항은 [infra 3.2](infra.md#32-kind-환경값외부-egress-236) 13장.

### 24.7 학부모 결제·구독 화면 (#184)

- 서버 상품의 가격·월 청구 주기·자녀 수·이용 기능·한도·기간 표시. 무료 조건 별도 표시, 임의로 무료 상품을 선택하지 않음
- 연결 자녀를 선택해 주문 생성, 같은 자녀의 ACTIVE·RENEWAL_FAILED 구독이 있으면 구매 제한(최종 검사는 core)
- 주문 생성·승인은 UUID 멱등 키 유지. 저장한 주문과 성공 URL의 주문번호·금액을 대조한 뒤 core 승인 API 호출, `APPROVED`와 `APPLIED`가 모두 확인되어야 이용권 적용 완료 표시
- `CONFIRMING`·`RECOVERY_REQUIRED`는 GET 상태 조회로 확인(자동 새 주문·재결제 없음). 실패 URL에서는 승인하지 않음
- 빌링 GET의 customerKey로 SDK 인증을 시작하고 등록·변경 전 자동 갱신 동의 확인. 콜백 고객 범위·만료 검사 후 authKey를 core에 전달. 카드 원문·paymentKey·authKey·시크릿 키는 브라우저 저장소에 남기지 않음
- 구독 상태·기간·다음 청구일·갱신 금액·빌링 등록 여부, 갱신 실패 유예 종료·재시도 횟수·예정일은 서버 응답 그대로. 해지·철회는 확인 후 서버 응답 재조회
- 본인 거래의 결제·취소·환불 이력과 전액 환불 요청. REQUESTED·APPROVED·FAILED·COMPLETED 구분 표시, 검토 중 결제수단 변경·갱신 철회 제한
- 동의 철회·자녀 연결 해제 상태에서도 본인 거래 조회·자동 갱신 해지·환불 복구 접근 유지

실행 모드:

1. 실제 core: `npm run dev`(목업 비활성). DB·core·상품·학부모·연결 자녀와 테스트 상점 설정 필요
2. 화면·모의 검증: `VITE_API_MOCK=true npm run dev`. 외부 PG 미호출, 상단 상태 선택기로 결제 확인 중·갱신 실패·환불 실패 시연. 고정 데이터는 `src/mocks/handlers/payments.ts`
3. 실제 PG 단건 연결 확인: `npm run dev:payment -- --port 5251`. 결제창과 서버 승인은 실제 토스 테스트 API, 주문은 메모리에만 보관하고 SANDBOX_ONLY 표시, 이용권 미부여. production 미포함. 테스트 상품 14,900원은 `scripts/payment-test-server.ts`

### 24.8 검증 범위와 한계

- core·learning 통합 테스트(실제 PostgreSQL·Redis·RabbitMQ, PG·learning HTTP는 계약 대역)로 금액/주문/소유권 위조, PG 응답 불일치, 동시 승인/취소, 응답 유실·권한 DB 실패 복구, 같은 기간 중복 청구, 말일·유예·3회 재청구, billing/해지 경합, 탈퇴/동의 철회 복구, 환불 조건·관리자 권한 검증
- 실제 bootJar 두 프로세스로 core→learning 증빙 조회, 환불 동결 차단, 반려 후 피드백 DONE/USED, 사용 후 409 환불 거부 확인(결제 상태는 합성 fixture)
- 실제 토스 테스트 결제 승인·구독 `ACTIVE`는 kind 환경에서 확인(#236, [infra 3.2](infra.md#32-kind-환경값외부-egress-236) 13장). 빌링 발급·정기 청구·취소·웹훅 송신은 실제 PG로 미검증

### 24.9 상태 전이 서술 정합화 (#419)

2026-11-09 develop 정합성 검증에서 나온 상태·권한 서술 차이는 모두 **문서를 코드에 맞추는 쪽**으로 정했다(사용자 확정, 동작 변경 없음). 반영 위치는 [상태 다이어그램](../design/state-diagram.md) 2.5·4.1·6.1~6.3, [API 명세](../design/api-spec.md) 시도 비교·리포트 재생성 행이다.

| 항목 | 결정 | 근거 코드 |
|---|---|---|
| A1 환불 `FAILED` | 종료 상태가 아니라 대기 환불. `FAILED → REJECTED`(관리자 반려)·`FAILED → COMPLETED`(웹훅 뒤 PG 취소 재확인) 추가, 재요청은 새 행 없이 기존 행 반환. 관리자 승인은 `REQUESTED`만 받아 같은 결제를 다시 취소하지 않음. `FAILED`가 탈퇴를 막는 기존 계약은 유지 | `RefundService.reject`(`REQUESTED`·`FAILED` 허용), `applyVerified`(`REQUESTED`·`APPROVED`·`FAILED` 허용), `PaymentMapper.xml` `pendingRefund`·`refundPending`, `PaymentWebhookService` |
| A2 결제 취소 | PG `CANCELED` 확인 시 승인 시각이 있으면 `REFUNDED`, 없으면 `CANCELED`. 승인 결제는 `REFUND_REVIEW` 없이 `APPROVED → REFUNDED`, 확인 중 결제는 `CONFIRMING → REFUNDED·CANCELED`. 대상 구독은 함께 `CANCELED` | `PaymentService.accept` `CANCELED` 분기 |
| A3 시도 비교 | `GET /attempts/{attemptId}/comparison`은 학생 본인 전용. 학부모 조회 기능은 만들지 않음 | core `PublicAuthFilter`(`/attempts/` 비학생 403), learning `AttemptController.comparison`의 `requireSelfStudent()`, OpenAPI `getAttemptComparison` |
| A4 리포트 재생성 | 관리자는 `SERVICE_OPS` 권한만 무제한 재생성 | `PublicAuthFilter` `adminReportRegeneration` → `requirePermission(SERVICE_OPS)`, OpenAPI `regenerateReport` |
| A5 시스템 반려 | `REQUESTED → REJECTED`를 시스템 전이로 추가(결제 후 프리미엄 사용 확인, `decided_by` 없음, 409 `REFUND_NOT_ALLOWED`) | `RefundService.request` 증빙 조회 뒤 분기 |
| 함께 정리 | 정기 리포트 작업 부분 UK `(student_id, period_type, period_from)`, 세션 진입에 `POST /auth/admin/login` 추가 | `V30__daily_report_period_type.sql`, `AuthService.adminLogin` → `startSession` |

- 검증 중 함께 찾은 차이: 대기 중인 `REQUESTED` 환불도 웹훅으로 PG 취소가 확인되면 바로 `COMPLETED`가 된다(`applyVerified`). 상태 다이어그램 6.3에 같이 적었다
- 코드·계약 변경이 없으므로 core 테스트·OpenAPI는 그대로다

## 25. 주간 테마 영상 사용량 THEME_VIDEO·응답 칸 추가 (에픽 #436, 2026-11-12)

learning #438이 이번 주 테마 응답에 큰 질문·후보·요일 단서와 시작·종료 장면 영상·움직임, 엔딩 뒤 정답을 더하고, ai #437이 시작·종료 장면 영상을 만든다. 학년 전달(15절)과 같은 PR이다.

- `GET /admin/ai-usage?callType`과 `llm.usage.recorded` 이벤트에 `THEME_VIDEO` 추가(V45). 이벤트 스키마·core `CallType`·OpenAPI·ERD·ai/scoring 발행 목록에 `KNOWLEDGE_EMBEDDING` 다음, `M2` 앞. 처음 V42였으나 #480(V42)·#485(V43)·#467(V44)이 먼저 머지되어 "먼저 머지되는 쪽이 다음 번호" 규칙으로 V45. gitops 로컬 core 리비전 v45
- 영상 호출은 토큰이 없어 이미지처럼 `cost_usd` null, `unpricedCalls`로 집계
- 요일 장면 영상은 없다(시작·종료만, learning `ThemeScene.videoUrl`은 ai 채택 테마에서 null). 사용량은 테마 하나에 최대 2건
- 이번 주 테마 응답은 core가 바꾸지 않고 전달하고 OpenAPI·api-spec 설명만 맞춤. core가 읽는 값은 포인트 적립용 `weekStart`·`completed`·`finished`·`days[].missionId`·`attemptStatus`·`day`·`completedOnDay`뿐(#389·#485). 정답·종료 이야기는 learning이 엔딩 전에 비움
- ai `app/llm/media.py`는 아직 `THEME_VIDEO`를 발행하지 않고 로그만 남긴다. 이 PR 머지 뒤 ai 발행을 켜고 관리자 사용량 집계를 확인
- 테스트: `ModelVersionHttpTest`(V45 CHECK 저장·조회·미산정), `WeeklyThemeProxyIntegrationTest`(`grade=G5&date=…&sundayTheme=…`), `scripts/tests/test_admin_mission_drafts_contract.py`·`test_admin_operations_contract.py`·`test_core_migration_versions.py`·`test_weekly_theme_contract.py`

## 26. 큰 질문 정답 고르기 프록시·엔딩 전 커뮤니티 잠김 문구 (#550, 2026-11-12)

주간 테마 규칙 개정(#483)에서 큰 질문 정답을 맞히면 바로 엔딩, 틀리면 토요일 다시 풀기 뒤 엔딩이 된다. learning #484가 정답 고르기와 엔딩 전 커뮤니티 잠김을 만들고, 학생 화면은 core를 거치므로 core에 경로와 공개 문구를 더했다. 계약은 api-spec 2.9·2.11·4.1.

### API 변경

| 경로 | 변경 |
|---|---|
| `POST /students/me/weekly-theme/answer-picks` (신규) | 학생 본인 세션, body `{pick}` → learning `POST /internal/students/{studentId}/weekly-theme/answer-picks?grade&date&sundayTheme`. 응답 `{correct, ending(NOT_ENDED\|ENDED), answer(엔딩일 때만)}`·오류 그대로, `Cache-Control: no-store` |
| 커뮤니티 목록·반응 | learning 새 코드 `403 COMMUNITY_LOCKED_UNTIL_ENDING`을 공개 오류로 전달("이번 주 테마 엔딩을 보면 친구들 생각을 볼 수 있어요.") |

새 오류 코드: `409 THEME_PICK_NOT_ALLOWED`(learning 판정, 금요일 문제 마무리 전·이미 고름 등)·`403 COMMUNITY_LOCKED_UNTIL_ENDING`.

### 결정과 근거

- **질의는 `themeQuery` 재사용**: 이야기·되돌아보기 열람과 같은 `grade=G{학년}`·KST `date`·`sundayTheme`. 고를 수 있는 날(토요일·프리미엄 일요일 판단 포함)을 learning이 같은 기준으로 판정하게 하려는 것. 일요일 상품 확인 실패는 다른 열람 기록처럼 `false`(닫힘)로 넘긴다
- **본문은 core가 모양만 확인**: `{pick}` 하나, 비어 있지 않은 문자열이 아니거나 다른 필드가 있으면 learning을 부르지 않고 `400 VALIDATION_FAILED`. `{pick}`만 다시 만들어 넘겨 클라이언트가 `correct`·날짜 같은 값을 끼워 넣지 못하게 한다(`story-views`와 같은 방식). 후보 안의 값인지·길이는 후보 목록을 가진 learning이 판정
- **응답·오류는 그대로 전달**: 정답 판정·엔딩 상태·정답 공개 시점은 learning 소유라 core가 응답을 읽거나 바꾸지 않는다. `409 THEME_PICK_NOT_ALLOWED`는 기존 `THEME_STORY_NOT_ALLOWED`처럼 learning Problem을 그대로 보여 준다
- **포인트 적립 없음**: #483 포인트 규칙에 정답 고르기 사건이 없다
- **잠김 코드를 따로 둠**: 기존 `COMMUNITY_LOCKED`는 "이 미션을 마무리하면…" 문구라 금요일 문제를 마무리했지만 정답을 틀린 학생에게 맞지 않는다. 문구는 이슈 기준안
- **머지 순서**: learning 경로가 생기기 전(#484 머지 전)에는 이 경로만 learning 404를 그대로 전달한다. 커뮤니티 새 코드는 learning이 보내기 전까지 쓰이지 않는다. 그래서 #484보다 먼저 머지해도 된다

테스트: `WeeklyThemeProxyIntegrationTest`(질의 `grade=G5&date=2026-11-09&sundayTheme=false`·본문 `{pick}`만 전달·200 두 모양·409 전달·적립 없음·400 7종), `CommunityIntegrationTest`(두 잠김 코드 문구). learning 계약 대조는 #484가 `learning-service.yaml`에 경로를 올린 뒤 추가할 수 있다. 남은 확인: #484 머지 뒤 kind에서 맞힘 → 즉시 엔딩, 틀림 → 토요일 다시 풀기 뒤 엔딩, 엔딩 전 커뮤니티 문구(#485 kind 확인과 함께).

## 27. 추억 검색·설명 프록시·하루 한도 (#566, 2026-11-12)

리텐션 확장 P27(에픽 #562)의 core 몫. 학생 추억 검색·설명을 learning(#563·#564)으로 넘기면서 하루 한도를 확인하고, 새 LLM 사용량 유형을 받는다. 결정 기록은 [리텐션 확장 9.1](retention-expansion.md#91-core-추억-검색설명-프록시하루-한도-566-2026-11-12), 계약은 api-spec 1.3·2.12, 저장은 ERD 3.4·3.5.

### API 변경

| 경로 | 변경 |
|---|---|
| `POST /students/me/memories/search` (신규) | 학생 본인 세션, body `{query}`(1~200자) → learning `POST /internal/students/{studentId}/memories/search`. 응답·오류 그대로, `Cache-Control: no-store` |
| `POST /students/me/memories/explanations` (신규) | body `{query, attemptIds}`(시도 1~3개, 중복 없음) → learning `POST /internal/students/{studentId}/memories/explanations` |
| `GET /admin/ai-usage?callType` | `MEMORY_EMBEDDING`·`MEMORY_EXPLANATION` 필터·집계(core `CallType` enum이라 별도 변경 없음) |

### 처리 순서

1. 세션의 학생 1명 확인, 본문 모양 확인 후 다시 만듦(다른 필드·형식 오류는 400, 사용량 미기록·learning 미호출)
2. 한도 값: 이용 중 상품 `limits`(없으면 무료 상품 값)
3. `MemoryUsageService.reserve`: 학생·종류별 advisory lock → 1행 기록 → KST 오늘 건수 > 한도면 롤백·429
4. `LearningMemoryClient`로 learning 호출(서킷 `learning-memory`, 검색 30초·설명 45초)
5. learning 5xx·시간 초과·연결 실패·서킷 차단이면 `release`로 그 행을 지움. 응답·오류는 그대로 전달
   - 설명의 ai 장애(질의 임베딩 실패, 생성 ai 503·시간 초과·연결 실패·서킷 열림)는 learning이 503 `AI_UNAVAILABLE`로 돌려주므로 이 규칙으로 되돌린다. core 코드 변경 없이 learning 판정을 바꿈(#592, [리텐션 확장 13.1](retention-expansion.md#131-ai-장애-때-설명-한도-미차감-592-2026-11-12))

### 저장·마이그레이션 (V46)

- `llm_usage.call_type` CHECK에 `MEMORY_EMBEDDING`·`MEMORY_EXPLANATION`(V45와 같은 방식, 허용 목록만 넓힘). 이벤트 스키마·core `CallType`·OpenAPI·ERD 주석·ai/scoring 발행 허용 목록을 함께 바꿈. ai가 실제로 보내는 것은 #565
- `memory_daily_usage(id, student_id FK, kind SEARCH|EXPLANATION, usage_date KST, created_at)`, 인덱스 `(student_id, kind, usage_date)`
- 기존 상품 행 `limits`에 두 키가 없으면 20·10을 넣음(이미 있으면 그대로). gitops 로컬 core 리비전 v46
- 학생 삭제 확정 트랜잭션(`ChildManagementService`)에서 `memory_daily_usage`도 지움

### 서킷

- `LearningClient.forMemory`가 서킷 `learning-memory` 하나를 검색·설명 두 전송에 나눠 줌. 기준은 `learning-json`과 같음(최근/최소 20건·실패율 50%·30초 차단·half-open 1건, 4xx 정상·5xx 실패)
- 설계는 검색을 `learning-json`에 두었으나, learning의 임베딩 장애 503이 일반 회로를 열어 주간 테마·시도까지 막을 수 있어 검색도 이 회로로 옮김(architecture 1.3 갱신)

### 테스트

- `MemoryProxyIntegrationTest`: 본문 재구성·경로·헤더·no-store·KST 날짜 기록, 한도 경계(2회 통과 → 3번째 429·learning 미호출, 종류별·날짜별 따로, 한도 0), 동시 6건 중 2건만 통과, learning 422 전달·셈, 503 전달·되돌림(검색·설명, #592), 설명 `FAILED` 셈, 서킷 분리(`learning-memory` OPEN에도 `learning-json` CLOSED·주간 테마 정상, 차단 시 503 `LEARNING_CIRCUIT_OPEN`·사용량 없음), 형식 오류 400 14종, 구독 스냅숏 키 없음 → 무료 값, 무료에도 없음 → 503
- `LearningClientTest`: 검색·설명이 한 서킷을 공유하고 응답 시간은 따로(검색 시간 초과·설명 성공), 기본 30·45초
- `AccountManagementTest`: 삭제 확정 때 대상 학생 사용량만 삭제
- 계약: `scripts/tests/test_admin_mission_drafts_contract.py`(호출 종류 목록 일치)·`test_admin_operations_contract.py`·`test_core_migration_versions.py`

### 남은 일

- learning #563·#564가 내부 경로를 만들기 전에는 learning 404를 그대로 전달한다. 머지 뒤 실제 연동 확인
- ai #565는 이 변경이 병합된 뒤에 새 `callType`을 발행
- web 관리자 사용량 화면의 호출 종류 이름표(`adminFormatting.ts`)·목 필터(`mocks/handlers/admin.ts`)에는 새 값이 없다(기존 `THEME_*`도 없음). web #567 범위

## 28. 추억 앨범 공개 프록시 (#560, 2026-11-12)

리텐션 확장 P27(에픽 #558)의 core 몫. 학생 추억 앨범을 learning(#559)으로 넘기고 목록 `displayed`를 추억의 벽 슬롯(#555)으로 채운다. 결정 기록은 [리텐션 확장 11장](retention-expansion.md#11-core-추억-앨범-공개-프록시-560-2026-11-12), 계약은 api-spec 2.12·4.1.4.

### API 변경

| 경로 | 변경 |
|---|---|
| `GET /students/me/album?page&size` (신규) | 학생 본인 세션 → learning `GET /internal/students/{studentId}/album`. 200이면 항목마다 `displayed` 추가, 그 밖 응답·오류 그대로, `Cache-Control: no-store` |
| `GET /students/me/album/{themeId}/{weekStart}` (신규) | → learning `GET /internal/students/{studentId}/album/{themeId}/{weekStart}`. 응답·오류(404 `THEME_FRAME_NOT_FOUND`) 그대로 |
| `POST /students/me/album/{themeId}/{weekStart}/seen` (신규) | → learning `POST …/seen`. 204·오류 그대로 |

### 처리

1. 세션의 학생 1명 확인(학생 이외 403, learning 미호출). 경로·쿼리 형식 오류는 Spring 400 `VALIDATION_FAILED`
2. `LearningMemoryClient`의 앨범 메서드가 일반 `LearningClient`(서킷 `learning-json`, 30초)로 호출
3. 목록 200: `items`가 배열이 아니거나 항목의 `themeId`·`weekStart`를 읽을 수 없으면 502 `LEARNING_CONTRACT_INVALID`. 빈 목록은 그대로, 아니면 `RoomFrameSlotService.displayedFrames`로 `displayed`를 더해 다시 직렬화

### 테스트

- `AlbumProxyIntegrationTest`: 걸린 회차만 `displayed:true`·나머지 칸 유지·`page`·`size`만 전달·학생 범위 헤더·쿼리 생략, learning 400·500 전달, 깨진 200 본문 4종 502, `learning-json` 서킷 사용, 상세 바이트 그대로·seen 204·404 `THEME_FRAME_NOT_FOUND` 전달, 학부모 403·형식 오류 400(learning 미호출)

### 남은 일

- learning #559(PR #571)는 병합됨. 배포 환경에서 실제 연동 확인. web #561이 이 경로를 쓴다
