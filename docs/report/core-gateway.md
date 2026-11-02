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
