# #47 관리자 운영 구현

최초 기준은 원격 재조회한 `8883528aa763809a93119c8c4cb160c7d032b5c6`, base `feature/core-support-payments-integration`, head `feature/core-admin-operations`다. develop `c608f52aa0f7b651133603a629a8347be61b3282`를 포함한다. 기존 checkout은 전환하지 않고 전용 worktree를 만들었다. origin은 팀 원본, upstream은 없다.

사용자가 PublicAuthFilter의 정확한 overview/audit GET 두 경로만 ADMIN 역할로 여는 변경을 승인했다. 다른 기존 로직·마이그레이션·공개 계약은 보존한다. 새 관리자 응답은 frontend 목업의 updatedAt·errorDetail 등을 만들어 채우지 않는다. 사용자 추가 승인으로 프론트 운영 타입·API·화면·해당 목업을 실제 응답에 연결한다. 미션 집계는 미연결로 표시하고 서버의 retryable 조건으로 재처리 버튼을 제어한다. #43 계약 테스트의 전체 /admin 가정은 승인받아 본래 모델·AI 사용량 경로로 한정한다.

설계: controller → admin service → 기능별 operations service → 각 소유 테이블 repository. execution/audit은 admin repository가 조회한다. learning 통계/미션은 learning 기능 service → 기존 LearningClient → InternalRestClientFactory다. 다른 서비스 DB를 조회하지 않는다. 큐는 읽기 전용 관리 HTTP이며 별도 환경 변수로 설정한다. production 의존성·DDL 추가 없음.

재처리: REPORT의 regenerate는 새 판/새 작업 생성이다. report-service GenerationService/get_or_create는 같은 jobId가 FAILED면 재생성하지 않고, core ReportLifecycleService도 종료 상태를 보존한다. 따라서 기존 job 재처리와 동치로 취급하지 않는다. CONVERSATION은 통합 기준에 삭제 service만 있고 관리자 실행 공급자가 없다. 둘 다 명시적인 JOB_RETRY_UNAVAILABLE로 남긴다. Notification은 기존 publisher/DeliveryService를 호출하고 외부 Redis 발행을 트랜잭션 밖에 둔다. 기존 감사·리포트·알림·공통 멱등성 구현을 재작성하지 않는다.

learning stats는 #27 실제 구현·OpenAPI가 존재한다. 관리자 미션 공급자는 기준 브랜치에 없다. 프록시의 HTTP 계약은 테스트 대역으로 확인하며 실제 learning 콘텐츠 관리·미션 상태 집계 연결은 후속이다. #41/#48 병렬 worktree와 파일은 변경하지 않는다. 새 migration을 만들지 않아 V14/V15 번호를 사용하지 않는다.

최종 구현·검증은 아래 #48 병합 반영 후 결과를 따른다.

## #48 병합 반영

사용자 추가 지시에 따라 origin을 다시 fetch했다. PR #121/#48 병합 기준 `85bf107`을 확인하고 미커밋 38파일을 ZIP·SHA-256·binary diff 및 stash `49abc61ef023771a3f856204f628c5e67e0b60df`로 보존했다. 전용 브랜치만 최신 통합 기준으로 fast-forward한 뒤 재적용했다. PublicAuthFilter는 #48의 결제 복구·POST 웹훅 예외·GET 환불 조회 PAYMENT_VIEW를 그대로 보존하고 승인된 두 GET 예외만 접합했다. OpenAPI는 최신 통합 문서 원문에 #47 신규 경로·스키마만 추가했다. #43 테스트 한정 수정은 #48에도 같은 내용이 반영되어 최신 기준을 유지했다. 이력 재작성은 없다. 최종 검증 기준은 `85bf107`이다.

## 최종 검증 (2026-10-29)

최종 base/HEAD는 `85bf1079c34a3e713bcf5eedf0cfdfd7822dc5a4`이며 종료 전 원격 재조회와 같다. 이전 기준의 실패/중단 실행은 합산하지 않았다.

| 검증 | 실행 결과와 경계 |
|---|---|
| JDK 21 core | Temurin 21 전용 Linux 소스/캐시 볼륨에서 `bash gradlew test bootJar --no-daemon --max-workers=2 --no-watch-fs --console=plain -Pkotlin.compiler.execution.strategy=in-process`와 검증 전용 CPU/메모리 제한으로 실행. 44클래스 **270개 통과**, 실패·오류·생략 0, BUILD SUCCESSFUL(7m26s). #47 신규 12개와 #48 결제·기존 신고/계정/리포트/알림/인증 회귀 포함. |
| 새 관리자 통합 테스트 | 실제 JWT/MVC/PostgreSQL·Redis로 권한/기간/목록/실제 ID/이력/민감 문자열 제거, 같은 키 응답 재현·다른 키 동시 실행 방지, 실행/감사 원자 저장, 트랜잭션 밖 발행을 검사. Redis 실패 결과 시나리오는 기존 publisher를 테스트 spy로 바꾼 대역이며 실제 Redis 성공과 구분한다. |
| 큐 관리 | 별도 RabbitMQ 4.3.7 관리 API에 실제 definitions를 적용하고 `/`의 25큐를 조회. 별도 HTTP 대역으로 인증 오류·잘못된 JSON·누락 큐·5초 타임아웃을 확인. 테스트 관찰만 통계 준비를 기다리며 production 자동 재시도는 없음. |
| learning 프록시 | 테스트 HttpServer로 stats 계약/장애와 미션 10종 메서드·경로·본문·ADMIN 사용자·빈 학생 범위·내부 토큰을 검사. 422 코드/필수 누락 필드 보존과 자유형 상세 제거, 공급자 404→503 확인. 실제 learning 관리자 API 실행은 아님. |
| 프론트 | `npm test` **93/93**, `npm run lint`, `npm run build` 통과. build는 기존 크기 경고(500kB 초과)를 보고하며 이번 범위 밖 번들 분할은 하지 않음. 실제 연결에서 발견한 빈 미션 필터를 생략하도록 고친 뒤 최종 일괄 검증을 다시 통과. |
| 실제 브라우저 연결 | VITE_API_MOCK=false, headless Chrome → 전용 Vite → 실제 최종 core JAR → 별도 PostgreSQL/Redis/RabbitMQ. SERVICE_OPS/CONTENT/PAYMENT_VIEW 화면의 6개 시나리오, 관리자 API HTTP 응답 13건, pageerror 0, service worker 응답 0. 알림 재처리 완료·실제 감사·25큐·권한 403·미션 503 표시 확인. 로그인 부트스트랩만 합성 JWT 응답 대역이고 core는 실제 DB 세션으로 검증. overview의 learning은 명시적 테스트 HTTP 대역, Google/실제 learning 검증이 아님. |
| 계약 | `python -O -m unittest discover -s scripts/tests -v` **69/69**, core OpenAPI 3.1 표준 검사 통과. 브라우저에서 받은 실제 overview/jobs/job/queues/audit 응답 5종을 `scripts/validate_admin_operations_contracts.py`로 공개 스키마와 대조해 통과. 통합 기준의 기존 경로·스키마 값 보존 검사 포함. |
| DB·소스·JAR | #47 DDL 변경 없음. 별도 빈 DB에 기존 13개 마이그레이션(V1~V9,V12~V15) 적용 성공; 전체 ERD/downgrade cycle을 이번에 반복하지 않음. 검증 직후 core/contract/definition 328파일 원문 SHA-256 일치. 최종 stage 검사에서 OperationsQuery.kt 끝 빈 줄만 제거했고 이를 제외한 327파일 원문과 해당 파일의 끝 공백 정규화 내용은 같다. 실행 로직 변경은 없다. 실행 JAR에 Flyway/Testcontainers/JUnit/Mockito 없음. JAR SHA-256 `5cd8afbe4c1f09cff15013c7d74c2a982af34649004fae8d9ac243fb055ca41b`. |

초기 Windows Gradle은 loopback 연결을 만들지 못해 테스트 시작 전에 실패했다. 전용 Linux 실행으로 전환했다. 초기 YAML 앵커 중복과 새 테스트 fixture의 scope_changed 누락은 수정했고 위 결과는 수정 후 최신 #48 기준 단일 전체 실행이다. 브라우저 검증 선택자는 감사 이력 여러 건과 오류 코드 뒤 trace 번호를 허용하도록 보완했다. 원격 CI·배포·실제 PG/Google·실제 learning 미션 관리·#41 대화 재처리는 미검증이다.

## 남은 공급자와 한계

- REPORT 기존 실패 job 재처리는 아직 연결하지 않는다. 같은 jobId로 Outbox만 다시 넣어도 report의 job 멱등성과 core의 종료 상태가 이를 실행하지 않는다. core/report 양쪽의 시도 식별·종료 이벤트·소비자 계약을 먼저 합의하고 기반영 수정 허락을 받아야 한다. 새 판 regenerate로 대체하지 않는다.
- CONVERSATION 관리자 실행 공급자와 learning 관리자 미션/상태 집계 공급자는 없다. #41 코드나 learning DB를 복사하지 않고 명시적인 미연결 상태를 유지한다. 미션 콘텐츠 DTO/게시 정책은 실제 공급자의 OpenAPI 확정 후 최종 대조해야 한다.
- 알림 재처리는 Redis 발행 확인까지다. 브라우저 수신 보장이 아니며 프로세스 중단·결과 저장 실패로 RUNNING 이력이 남으면 자동 재실행하지 않는다. 네트워크 발행 자체에 분산 트랜잭션/정확히 한 번 보장을 추가한 것은 아니다. common IdempotencyService의 24시간 응답 저장을 재사용하며 5xx는 저장하지 않는 기존 정책을 유지한다.
- #47 전체 완료 조건이 아직 충족되지 않았으므로 이슈를 완료 처리하거나 Closes #47로 해결 완료를 주장하지 않는다. 현재 커밋은 독립적으로 검증한 운영 조회·알림 재처리·미션 프록시 범위다. 공급자 연결 후 실제 해결 범위를 확인한 PR에 Closes #47을 포함한다. 중간 base 병합만으로 자동 종료되지 않으며 최종 develop PR에도 필요하다.

Git 이력 재작성·PR 생성·공용 브랜치 push는 하지 않는다. 기능 head만 push하며, 사용자 직접 PR 작성용 초안은 별도 전달한다. 개인 작업 규칙을 저장소 문서에 추가하지 않았다.

## Git 전달 기록

구현 커밋은 `8d08cfa7eeae8f2ae1af65efe94e5f720eb15bca` (`feat: 관리자 운영 조회·알림 재처리·미션 프록시 구현`)이다. 신규 파일이 stage되면서 처음 검사된 OperationsQuery.kt의 EOF 빈 줄 경고를 확인했지만 커밋 명령이 이어진 실행 실수를 바로잡았다. 해당 빈 줄만 제거하고 최종 기록과 함께 후속 커밋으로 남긴다. 구현 커밋을 amend/squash하지 않는다. 최종 base 대비 diff 전체에 git diff --check를 수행하며, 두 커밋의 기능 브랜치만 origin에 push한다. PR은 생성하지 않는다.

## PR #123 CI 이력 의존성 보완

PR #123은 base feature/core-support-payments-integration, head b017044이며 GitHub mergeable=true다. 병합 충돌이 아니라 ci-db-schema run 40806885690/job 123227860037의 계약 검사 실패였다. checkout fetch-depth=1인 CI에서 #47의 test_existing_contracts_preserved가 git show 85bf107을 호출해 exit 128이 발생했다. 로컬 전체 이력 검증에서는 발견하지 못한 테스트 환경 의존성이다. 공용 workflow의 fetch 범위를 바꾸지 않고, 검토한 base의 기존 91경로·114스키마를 canonical JSON SHA-256 fixture로 저장해 기존 계약 보존 검사를 유지한다. 테스트는 Git 이력·네트워크·현재 브랜치 이름에 의존하지 않는다. production/DB/프론트 변경은 없다. 검증은 전체 Python 계약 검사와 Git 메타데이터가 없는 격리 복사본의 동일 검사로 수행한다.

CI 보완 로컬 검증: 전체 Python 계약 검사 69/69 통과. 별도 복사본에서 `.git` 없이 PATH도 비운 상태로 동일한 69/69 통과했다. 이 복사본의 기존 `/admin/ai-usage` 계약을 의도적으로 바꾸면 보존 검사가 실패함을 확인해, 검사 생략으로 통과시킨 것이 아님을 확인했다. git diff --check 통과. 테스트/fixture/기록만 변경해 기존 JDK·프론트 전체 검증은 반복하지 않는다. 원격 결과는 후속 push의 새 run을 기준으로 확인한다.

## Core CI #77 메시지 테스트 순서 보완

후속 head ef1383d의 schema/web/ai는 성공했지만 core run 40807420742/job 123229580279에서 270개 중 ReportMessagingTest의 중복·역순 이벤트 사례 1개가 실패했다. COMPLETED 검사는 통과했고 startedAt이 null이라는 검사만 실패했다. 완료→시작의 브로커 발행 순서를 DB 커밋 순서로 가정한 것이 원인이다. 공유 Testcontainers 브로커를 사용하는 복수 Spring context의 consumer는 메시지를 서로 다른 시점에 처리할 수 있다. 직전 b017044의 같은 core workflow는 성공했으므로 이력 검사 오류와 별개의 간헐적 테스트 순서 의존성이다.

사용자가 기반영 ReportMessagingTest의 해당 사례만 동기화하는 변경을 명시적으로 허용했다. 완료 이벤트를 먼저 발행하고 processed_event의 커밋 및 COMPLETED를 확인한 뒤 중복 완료·늦은 시작·실패 이벤트를 발행한다. 기존 startedAt null·COMPLETED·실행 이력 1개 검사는 유지한다. 기존 ReportRepositoryTest의 정상 started→failed 상태·시각/실패 원인 검사도 유지한다. production·공통 consumer·workflow는 변경하지 않는다. 검증 후 기존 feature 브랜치에 후속 커밋하며 이력 재작성은 하지 않는다.

순서 보완 후 전용 JDK21 Linux 환경에서 core 전체 44클래스 270개 test·bootJar 통과(실패·오류·생략 0). 기존 메시징/상태 전이 검사와 #47 알림 재처리·#48 결제 회귀를 포함한다. 테스트 한 파일과 이 기록만 변경되었으며 git diff --check 통과 후 기존 feature head에 후속 커밋·push한다. 원격 4개 workflow의 최종 상태는 새 head를 기준으로 별도 확인한다.

## REPORT 관리자 재처리 core 후속 (#152)

최초 기준 develop `2538d195c53c70a17af84aadea9a3ab1b348840a`(PR #154), 전용 feature/core-admin-report-retry다. 사용자는 core 관리자 분기·report 생성/저장소·관계 migration·학생/상품 확인·감사·공개 응답/조회·설계/테스트 변경을 명시적으로 승인했다. report-service와 프론트는 수정하지 않는다. #152는 OPEN이며 실제 공급자 실행 결과를 완료로 간주하지 않는다. 기존 report.generate v1의 새 jobId/ADMIN_RETRY를 재사용한다. 기존 job 종료 상태와 알림 재처리는 보존한다. 원작업당 1개 재처리, 재실패 시 자식 작업 재처리, durable key 복원과 202 접수/실행 결과 구분은 API 2.8을 따른다.

현재 develop·report 권한 통합 브랜치와 학생 프로필 브랜치의 core migration을 대조했으며 최신 develop 최대 V16, 병렬 브랜치에 V17은 없다. V17로 관계만 추가하며 기존 migration의 이름·내용·checksum은 수정하지 않는다. 최종 검증은 구현·테스트 작성 후 한 단계로 모아 수행한다.

구현 중 PR #155/#129가 develop `14a97f8f2221f5db4fda5631650fd2242b10cf81`에 병합됐다. 작업 28파일을 ZIP/SHA-256/binary diff와 stash `ce7d99fa26a1554401f6f7fe8e19ae29bd9018f6`로 보존한 뒤 이 전용 브랜치만 fast-forward·재적용했다. 기존 ReportClient/ReportQueryService/ReportViewService와 #129 테스트는 그대로 보존했다. V17은 여전히 비어 있으며 최종 검증 기준은 이 최신 develop이다.

### REPORT 후속 최종 통합·검증

- 검증 중 #152가 PR #156으로 develop `deecc12dfe9a23a8e4d23d7b0fb1d02b289ca3d2`에 병합되어 작업을 보존하고 fast-forward·재적용했다. 기존 report-service 실행 코드와 프론트는 수정하지 않았다. #152의 새 jobId/ADMIN_RETRY/v1 필드를 재사용한다. 예시의 원작업 연결 방식은 core 소유이며, 이 API는 직접 자식 1개·재실패한 자식에서 다음 재처리 정책을 사용한다.
- JDK21 core 전체 **339개**, 실패·오류·생략 0, test/bootJar 성공(최종 실행 6m28s). 새 REPORT 재처리 16개 검사 및 기존 알림·리포트·결제·인증 회귀 포함.
- Python 계약 **77/77**, OpenAPI 표준 검사, 실제 테스트가 만든 202 접수/작업 상세 및 Outbox 봉투·report.generate v1 스키마 대조 통과.
- 격리 빈 PostgreSQL의 전체 migration cycle 통과: core 43테이블/395컬럼, learning 19/158, report 7/50. 기존 60개 위반 입력·74 CHECK 집합·23 ERD 인덱스, 무변경 재적용 이력, report downgrade/upgrade 후 재검사 통과. 새 관계의 자기 연결·FK·중복 자식·중복 요청 키 제약은 새 core DB 테스트에서 별도 검사했다.
- 동일 키 응답 유실 후 복원, 서로 다른 키 동시 요청, 새 작업 재실패 및 다음 작업 연결, 삭제와의 경합, 현재 상품 변경/장애, 요청·결과 감사 저장 실패 시 rollback, 과거/중복 이벤트의 결과 격리 통과. 실제 RabbitMQ Outbox 발행·core 소비를 확인했으며 report 결과 생산자는 테스트 대역이다.
- 초기 전체 실행은 새 테스트가 남긴 processed_event 때문에 기존 리포트 전체 건수 검사 1개가 실패했다. 새 테스트 자신의 이벤트 ID만 정리하도록 보완했다. 별도 재실행의 Redis 초기화 연결 실패는 환경 실패로 구분하고 새 JVM/컨테이너 실행에서 최종 339개를 통과했다. 소스 복사/해시 목록의 초기화 및 CRLF 문제도 검증 준비 단계 실패이며 성공 결과에 포함하지 않는다.
- 실제 report-worker를 포함한 관리자 POST→생성 파이프라인 E2E, 프론트 연결, 원격 CI·배포는 이번 검증에 포함하지 않는다. #152 공급자 자체의 실연동 결과와 이번 core 결과를 혼동하지 않는다. 접수 후 발생하는 학생 삭제로 report 소비자가 생성을 막은 경우의 queued 작업 정리 정책은 후속 연결 검토 사항이다.

프론트 전달: REPORT 재처리 응답은 202 `{originalJobId,jobId,type:REPORT,status:QUEUED,acceptedAt}`이며 Location은 새 작업 조회 URL이다. ‘접수’로 표시하고 새 jobId의 GET 결과를 조회해 진행/완료/실패를 표시한다. 원작업 상세의 retryJobId, 새 작업의 retryOfJobId를 이동 링크로 사용한다. 이미 연결된 원작업은 REPORT_ALREADY_RETRIED로 다시 접수하지 않고 재실패한 새 작업에서 요청한다. 기존 NOTIFICATION의 200 결과 계약은 유지한다.

이번 작업은 #47의 REPORT core 범위이며 #47 전체 해결/Closes #47을 주장하지 않는다. PR base는 develop, head는 feature/core-admin-report-retry이며 PR은 사용자가 생성한다.

## #132 복구·삭제 종료 감사 접합 (2026-10-30)

#67/#162는 별도 채팅으로 인계했고 해당 worktree·검증 환경을 조작하지 않는다. 이 브랜치에서 origin/develop 640e0a2를 일반 merge로 준비했다. 학생 잠금 3파일과 설계 3파일의 충돌은 #132의 lockStatus/lockActive 및 #47의 삭제 이력 확인과 관계 설계를 모두 보존해 해결했다.

사용자 승인으로 ReportJobOutcomeRecorded 내부 이벤트를 추가한다. 기존 정상 종료 및 #132 복구·삭제의 조건부 전이가 실제 반영된 때에만 발행하며, reportId 없이 실패한 경우도 포함한다. #47 감사는 이 이벤트를 BEFORE_COMMIT으로 소비한다. 기존 ReportJobFinished의 부모 알림 조건, 상태 전이·잠금 순서·외부 report 계약은 유지한다. 중복·지연 결과는 기존 조건부 전이로 감사를 추가하지 않는다. 삭제 결과 감사가 실패하면 학생 차단·삭제 요청·작업 종료·실행 이력도 함께 롤백한다.


### REPORT 종료 감사 최종 검증 (develop 640e0a2 병합)

- 전용 Temurin 21 Linux 환경의 `./gradlew test bootJar`: 349개, 실패·오류·생략 0, BUILD SUCCESSFUL. 정상 종료 외 reportId 없는 복구, 중복·늦은 이벤트, 학생 삭제, 감사 실패 시 전체 롤백과 부모 알림 억제를 검증했다.
- `python -m unittest discover -s scripts/tests`: 84개 통과.
- 새 전용 PostgreSQL의 전체 migration/재실행/report downgrade·upgrade: core 43개 표·395열, learning 19개 표·160열, report 8개 표·56열; 63개 거부 사례·74개 CHECK·23개 ERD 인덱스 통과. 기존 V17은 그대로이며 추가 migration은 없다.
- 이번 추가 검증은 실제 PostgreSQL을 사용하는 로컬 테스트다. report-worker 실제 생성→PDF와 원격 CI·배포를 재검증했다고 주장하지 않는다.
- #67·#162와의 최종 통합은 별도 담당 채팅에서 수행한다. 기능 브랜치를 보존하고 develop 개별 병합·PR 생성은 하지 않는다.
