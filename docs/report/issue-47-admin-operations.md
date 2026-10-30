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

## 미션 후속 — 2026-10-30

승인 범위: 실제 404 전달, 전체 상태 counts, 인증 관리자·미션/버전 쓰기 감사와 불확실 결과. `feature/core-admin-mission-integration`은 develop 640e0a2에서 분기했다. 기존 learning 작성·검토·게시 로직과 프론트는 변경하지 않는다.

HTTP 전 REQUESTED를 짧은 독립 트랜잭션으로 남기고 응답 후 SUCCEEDED/REJECTED/UNKNOWN을 기록한다. 프로세스 중단·결과 감사 저장 실패에는 REQUESTED만 남을 수 있으며 변경 성공 여부는 learning에서 대조해야 한다. 요청·오류 원문은 저장하지 않는다. 새 migration은 없다. 프론트는 missionCounts의 상태·count 배열과 missionInclusionRule을 연결하면 된다. 자동 재요청 기능은 추가하지 않는다.

최종 검증:
- Temurin 21 Linux `./gradlew test bootJar`: core 334개, 실패·오류·생략 0. learning은 변경 없이 실제 연동용 bootJar 빌드 통과.
- Python 계약 검사 83개와 OpenAPI validator 통과. 실제 overview 응답도 OpenAPI JSON Schema에 부합한다.
- 전용 core·learning·PostgreSQL·Redis·RabbitMQ에서 실제 HTTP 10건: 생성 201, 수정 후 버전 2, 조회/쓰기 404, 기존 게시 상태 409, SERVICE_OPS 쓰기 403, 필터와 무관한 전체 counts/overview, detail 없는 감사 목록을 확인했다. 계정·세션/JWT는 검증용 합성 데이터이며 Google 로그인 검증은 아니다.
- core 감사 INSERT에만 전용 DB trigger로 장애를 주입했다. 실제 learning 생성은 유지되고 core는 503 MISSION_AUDIT_UNAVAILABLE, 요청 감사만 보존했다. trigger는 finally에서 제거했다. 정상·거부·미확정 요청을 합쳐 해당 검증 관리자 감사 9행을 대조했고 원문 미저장을 확인했다.
- timeout·잘못된 응답·요청/결과 감사 실패는 별도 core 테스트에서 검증했다. timeout은 명시적 클라이언트 대역이며 실제 네트워크 timeout으로 표현하지 않는다.
- 초기 컴파일의 Kotlin List.size 표기와 연동 검증의 게시 예상값(기존 learning은 DRAFT에서 409)을 수정했다. production learning 로직은 바꾸지 않았다.
- 이 브랜치에는 DB migration이 없다. REPORT 측 전체 migration 검증과 최종 통합 시 V17→V18 순서 확인은 별도다. 프론트·원격 CI·배포는 이번 검증에 포함하지 않는다.


## CONVERSATION 후속 (2026-10-30)

사용자 승인: 관리자 백그라운드 실행·공통 분석 경로·권한/한도·감사/복구 및 새 요청 테이블. 최신 develop e758e28에서 진행한다. 원격/로컬 브랜치의 V17(REPORT), V18(#162)을 확인했고 신규 V19를 사용한다. 기존 migration은 수정하지 않는다. Redis 사용량과 DB는 단일 원자 트랜잭션이 아니므로 요청 ID 표식으로 중복 차감을 방지하며 접수/실제 실행 이력을 구분한다. 최종 통합 브랜치는 별도 담당 채팅이 생성한다.

V19는 최종 통합에서 V17→V18→V19 순서로 적용한다. 통합 전 V19만 공용 DB에 먼저 적용하지 않는다. #163의 learning 오류 매핑 작업과 파일·브랜치를 공유하지 않는다.


### CONVERSATION 검증 진행 기록

- 기존 migration 수정 없음. 신규 V19의 전체 migrate·재실행·report downgrade/upgrade 및 ERD 대조 통과: core 43표/399열, learning 19표/160열, report 8표/56열. 공통 63개 거부 사례와 75개 CHECK 값 집합을 확인했다. 새 (status,accepted_at) 인덱스는 DB 정의와 별도 대조했다.
- 별도 V16 DB에 기존 ANSWER 근거를 넣은 후 V17→V18→V19 순차 적용 통과. 기존 ANSWER ID·버전 보존, REFLECTION 및 새 재처리 요청 저장을 확인했다.
- Python 계약 83개, OpenAPI validator, 실제 HTTP 202 응답 JSON Schema 검증 통과.
- 실제 core HTTP·PostgreSQL·Redis·RabbitMQ·결제 권한/사용 이력과 합성 AI HTTP 응답 서버를 사용했다. 202 후 core 강제 종료→새 프로세스에서 1회 실행, 멱등 캐시 삭제 후 동일 응답 복원을 확인했다. 실행 중 강제 종료 후에는 대기 시각만 검증 DB에서 앞당겨 복구를 확인했으며 FAILED 이력/감사 1회, 두 시나리오 총 AI 호출 2회·Redis 차감 2회·실제 결제 사용 이력 2행을 확인했다. 재기동이 65초 걸려 최초 50초 대기 제한을 넘겼으나 기동 후 결과를 대조했다. 실제 외부 LLM/PG 결제 호출은 없다.
- 첫 전체 core 345개 실행에서 최초/재접수 응답의 timestamp 정밀도 차이 1건을 발견해 최초 202도 DB 저장값으로 반환하도록 수정했다. 추가 권한 철회 사례와 함께 재검증 중이다. 테스트 import 충돌과 기존 동의 철회 오류 코드 기대값도 보완했다.
- 이후 전체 검증에서 기존 AiClientTest 2건 및 ConversationIntegrationTest 삭제 경합 1건이 응답 시작/취소 대기 제한을 초과했다. 당시 Windows 가용 물리 메모리는 약 485MB였다. 제한 시간·검증 조건을 완화하지 않고 검증 전용 JVM 메모리/캐시/순차 fork를 줄여 재실행하려 했으나 Docker 엔진 API가 500을 반환해 중단됐다. 당시 전체 core 통과가 미확정이어서 commit/push를 보류했다. 아래 재개 검증으로 해소했다.
- 검증 소스와 최종 core·테스트·OpenAPI 350파일 해시는 일치했다. 공유 분석 실행 본문은 #162의 기존 이벤트 검증·근거 확인·저장·취소 호출을 유지한다. #162와의 실제 통합 검증은 별도 담당 작업이며 이번에 통합 브랜치를 만들지 않았다. #163 파일·브랜치도 수정하지 않았다.

이슈 확인: #41은 Closed, #47·#67·#162는 Open이다. 기능 검증 통과와 이슈 통합/종료를 구분한다. 별도 통합 작업과 원격 CI 확인은 남아 있으며 이 채팅에서 이슈를 닫지 않는다.


### 환경 복구 후 최종 검증 (2026-10-30)

사용자가 Docker를 다시 실행한 뒤 #47 검증을 우선 재개했다. 코드는 변경하지 않았고 worktree의 core·테스트·OpenAPI 350파일이 저장된 검증 소스와 일치했다. 검증 전용 Gradle init에서 maxParallelForks=1, forkEvery=8, Test heap=640m, Spring test context cache=4를 사용하고 Gradle daemon heap=384m, CPU 2·컨테이너 메모리 1792MiB로 제한했다. 이 환경 제한은 저장소/production 설정에 추가하지 않았다. 기존 테스트의 제한 시간·검증 조건을 완화하지 않았다.

- `./gradlew test bootJar` 전체 실행: **53클래스 347개**, 실패·오류·생략 **0**, BUILD SUCCESSFUL(12m28s), 컨테이너 exit 0.
- 신규 AdminConversationRetryTest **18개**, AiClientTest **5개**, ConversationIntegrationTest **18개** 모두 통과했다. 이전 시간 제한 실패 3건을 포함한 전체 회귀를 확인했다.
- 앞서 통과한 migration 전체 검증, V17→V18→V19 기존 데이터 보존, 계약 83개, OpenAPI/실제 202 응답, 실제 프로세스 재시작·중단 복구 검증은 코드 변경이 없어 반복하지 않았다.
- #47 Docker 검증 사용을 종료했다. 공유 Docker 재시작·초기화·공유 자원 정리 및 다른 채팅 컨테이너 조작은 하지 않았다.
- 브랜치 기준은 develop e758e28이다. 원격 develop의 후속 변경과 #47 REPORT·미션 및 #67·#162 병합은 별도 통합 담당 작업으로 남긴다. V19 원격 번호 중복 없음과 기존 migration 불변을 다시 확인했다. #163·#164 작업 파일을 수정하지 않았다.

현재 결과는 기능 브랜치 보존을 위한 로컬 검증이다. 전체 통합·원격 CI·배포 검증이나 실제 외부 LLM 호출 완료로 표현하지 않는다. PR 생성·병합·이슈 종료는 수행하지 않는다.

## #47·#67·#162 통합 (2026-10-30)

최신 develop d651aa1에서 feature/admin-analysis-integration을 분기했다. REPORT 6be0eb8, 미션 d3d22c9, 분석 674ed64, CONVERSATION be78a29의 기존 커밋을 merge로 보존한다. 관리자·REPORT·분석 보고서와 ERD의 양쪽 내용을 함께 유지했다. OperationRetryService는 인증된 관리자 identity를 두 접수 서비스에 전달하며 REPORT의 새 jobId Location과 CONVERSATION의 기존 jobId Location을 구분한다. NOTIFICATION 200 결과는 유지하고 202 OpenAPI는 REPORT/CONVERSATION oneOf로 합쳤다. 작업 조회는 REPORT 원작업/후속 연결과 CONVERSATION 재처리 가능 여부를 함께 보존한다.

ConversationService의 최종 검증·fallback/notice·ANSWER/REFLECTION과 실행 세대·종료 감사는 모두 유지한다. migration은 V17→V18→V19를 포함하며 기존 파일을 수정하지 않는다. #163 오류 매핑 브랜치는 아직 이 통합 대상에 포함하지 않았다. develop에 반영되기 전 해당 정책을 임의로 덮어쓰지 않으며 향후 병합 시 관리자 미션 오류 매핑 충돌을 확인해야 한다.

최종 검증은 접합 완료 후 통합 소스 기준으로 수행하며 기능 브랜치의 과거 결과와 구분한다. PR은 develop 대상 하나이며 사용자가 생성한다.

### 통합 최종 검증

- core 전체 `test bootJar`: 55클래스 377개 중 375개 통과, 실패 2개·오류/생략 0. 관리자 테스트에는 양쪽 브랜치를 합치면서 남은 기존 “재처리 공급자 없음(503)” 기대값이 있었다. 현재 유효하지 않은 소유자 403·실행 이력 없음·실패 감사 1개로 정렬했다. AiClient 취소 검사는 상류 진입 대기 2초를 넘겼다. 해당 검사 코드를 바꾸거나 제한 시간을 늘리지 않았다. 두 영향 클래스의 18개 테스트와 bootJar를 다시 실행해 모두 통과했다(2분). 초기 전체 실패 로그와 최종 재검증 XML을 각각 보존한다. 이를 전체 377개 단일 실행 성공으로 표현하지 않는다.
- AI: 통합 소스 pytest 226개, Ruff check·format 통과.
- 프론트: 관리자 화면 추가 승인 후 최종 test 129개, lint·build 통과. 기존 500kB 초과 번들 경고는 남는다.
- 계약: Python 84개, core/AI/learning OpenAPI 표준 검사와 core YAML 중복 키 검사 통과. 실제 분석 SSE result 8개, REPORT/CONVERSATION 202 응답 5개가 공개 스키마에 맞는다.
- DB: 빈 전용 PostgreSQL의 전체 migration·재적용·report downgrade/upgrade 통과. core 44표/407열, learning 19/160, report 8/63; 위반 입력 63개·CHECK 집합 76개·ERD 인덱스 25개 검증. 별도 V16 DB의 기존 ANSWER를 V17→V18→V19로 올려 ID/버전 보존·REFLECTION/재처리 요청 공존을 확인했다. 세 migration 내용은 원본 브랜치와 동일하다.
- 실제 core→learning: 미션 생성/수정·404·409·권한·전체 counts·overview·감사 오류 10건, 감사 9행 확인. 실제 learning 변경 뒤 core 감사 저장 장애를 주입해 503과 요청 기록·learning 결과 보존을 확인했다.
- 실제 core→AI 그래프→learning: 정상·숫자/인용 불일치·키 미설정·기록 없음·지원 외·돌아보기·범위 확인·조회 장애/재시도 9개 시나리오 통과. 추가로 실제 SSE 연결 해제 시 FAILED/부분 답변 미저장, 다른 자녀 403, 무인증 401 통과.
- 실제 관리자 재처리→AI 그래프→learning: 숫자 실패 fallback, 지원 외 notice, REFLECTION 근거 3종을 저장·재조회했다. 작업별 실행 이력/관리자 완료 감사 1개와 멱등 캐시 제거 후 같은 접수 응답 복원을 확인했다.
- 학부모 브라우저: 통합 Vite→core→AI/learning의 규칙 응답·안내·돌아보기 5개 시나리오, 실제 API 응답 28건, pageerror 0. 로그인 부트스트랩과 LLM만 대역이다.
- 관리자 브라우저: 모의 HTTP 응답으로 REPORT/CONVERSATION의 QUEUED→RUNNING→COMPLETED, REPORT 새 jobId/원작업 이동, NOTIFICATION 완료를 확인했다. 세 사례 pageerror 0. 202를 완료로 안내하던 기반영 화면은 추가 승인 범위에서 응답 타입·조회 ID·수동 상태 갱신을 보완했다.

검증 소스는 컨테이너 복사 후 SHA-256으로 대조했다. 이후 수정은 관리자 테스트 1개, 승인된 관리자 프론트 및 관련 테스트·문서이며 해당 범위를 재검증했다. 오프라인 npm 캐시 누락, 초기 tar 복사 시점, AI 이미지의 검사 의존성/실행 경로, Gradle 필터 옵션 순서 오류는 준비 단계에서 바로잡았으며 성공 검증에 포함하지 않는다. 최종 코드에 production 의존성이나 검증용 자원 설정을 추가하지 않았다.

실제 외부 LLM·PG 결제·OAuth·report-worker PDF 생성 전체 파이프라인·원격 CI·배포는 이번 통합 검증 범위가 아니다. REPORT의 RabbitMQ 발행·종료 감사는 core 통합 테스트와 실제 생성 응답/이벤트 계약 검사 범위다. 성능·모델 품질 향상을 측정했다고 주장하지 않는다. 로컬 산출물은 admin-analysis-verification에 보존하고 합성 JWT가 든 fixture 파일은 공유/commit하지 않는다.

최종 origin/develop 재조회에서도 d651aa1을 확인했다. 현재 저장소 기본 브랜치도 develop이므로 이 통합 PR의 Closes #47, Closes #67, Closes #162는 해당 기본 브랜치 병합 시 적용된다. #163·#164는 별도 브랜치이며 이 PR의 종료 대상이 아니다.


## #163 learning 오류 매핑 변경 (2026-10-30)

사용자가 기반영 core 코드·공개 계약의 아래 범위를 명시적으로 승인했다. 기준 develop `7f1549ad8165e60895b96f3c0fb6d645e2e67149`, 전용 `feature/core-learning-error-mapping`에서 api-spec 1.3·2.8·5.7과 core OpenAPI를 먼저 변경한다. #47·#67·#162의 별도 worktree·작업은 합치거나 수정하지 않는다.

관리자 미션은 정상 Problem Details의 404 NOT_FOUND를 고정 문구의 404로, 불명확한 404와 405·501은 기존 503 ADMIN_MISSIONS_UNAVAILABLE로 처리한다. 기존 409·422 allowlist 및 정제한 missingFields는 유지한다. 지원 target/original GET은 정상 403 FORBIDDEN·404 NOT_FOUND를 같은 상태·기존 공통 코드와 고정 문구로 반환한다. 정상 오류는 application/problem+json JSON 객체·HTTP와 일치하는 정수 status·허용 문자열 code다. 오류 원문·내부 URI·공급자 trace·임의 code는 공개하지 않는다. 나머지 지원 HTTP 오류는 기존 503, 잘못된 2xx는 기존 502, 전송·시간 초과·서킷 오류는 기존 LearningClient 계약이다.

호출은 관리자 미션 controller → AdminLearningService → LearningClient → learning 관리자 API, 지원 controller → SupportService → LearningSupportClient → learning 지원 GET이다. 공개 신고/연결 문의 POST와 관리자 신고/문의 상세 GET에 영향이 있다. 최초 정정 POST 역시 대상 GET으로 사전 확인하므로 403/404가 공개될 수 있고 이때 정정 의도·공급자 정정 호출·완료 알림을 만들지 않는다. 실제 learning 정정 POST의 409/422·403/404 매핑은 유지한다. scope 설정·복원, 트랜잭션 밖 HTTP, 원문 allowlist·감사 저장·멱등성도 보존한다.

신규 공개 코드는 추가하지 않는다. FORBIDDEN은 learning의 학생 범위·역할·scope 형식 거부를 구별하지 못하고 NOT_FOUND는 프레임워크 경로 부재와 리소스 부재를 완전히 구별하지 못한다. 인증된 요청자의 403/404 구분에 따른 존재 여부 정보 차이를 포함해 승인받았다. learning production·frontend production·DB·의존성은 변경하지 않는다. frontend의 기존 ApiError·ErrorNotice·QueryFeedback는 상태·코드·고정 문구를 소비하고 404 안내·5xx 재시도 표시를 처리한다.

검증 결과는 구현·테스트 작성 후 일괄 검증을 마치고 아래에 추가한다. 과거 테스트 개수·실제 연동 결과를 이번 결과로 재사용하지 않는다.


### #163 최종 검증 결과 (2026-10-30)

| 검증 | 실제 결과와 경계 |
|---|---|
| core 전체 | Temurin JDK 21에서 `bash gradlew test bootJar --no-daemon --max-workers=1 --no-watch-fs --console=plain -Pkotlin.compiler.execution.strategy=in-process -Dorg.gradle.jvmargs=-Xmx384m -I <검증 전용 init>` 성공. **52클래스 339개**, 실패·오류·생략 0, BUILD SUCCESSFUL(10m 3s). 테스트 전용 CPU 2·메모리 1792MiB, Test heap 640m·forkEvery 8·Spring context cache 4. 이 자원 설정은 production이나 저장소 Gradle 설정에 추가하지 않았다. |
| core HTTP 회귀 | AdminOperationsIntegrationTest 11개·SupportIntegrationTest 22개 통과. 관리자 404/405/501/409/422, 지원 target/original 403/404·불명확한 오류·내부 401·장애·잘못된 2xx, 실제 정정 POST의 기존 409/422 및 403/404→503을 MockMvc 공개 경로 + learning HTTP 대역으로 확인했다. JWT/권한·학생 scope/복원·트랜잭션 밖 호출·오류 상세 비노출·정정 미저장/완료 알림 미발행을 포함한다. 실제 learning 공급자 검증과는 아래처럼 구분한다. |
| 계약·소비자 | `python -O -m unittest discover -s scripts/tests -v` **85개 통과**. core·learning·support 소비 OpenAPI 3개 표준 검사 통과. `validate_support_contracts.py`로 테스트가 생성한 지원 응답 7종, 별도 검사로 새 403/404 응답 2종을 공개 스키마에 대조해 통과했다. 기존 계약 fingerprint는 승인된 support 오류 응답만 정규화하고 나머지 원래 필드의 보존 검사를 유지했다. |
| 프론트 | `npm test` **118개 통과**, `npm run lint`·`npm run build` 성공. 관리자 미션 404와 신고·관리자 상세·정정 사전 조회 403/404의 ApiError 전달, 기존 정정 409/422 소비를 모의 fetch 응답으로 확인했다. 기존 500kB 초과 번들 경고는 남는다. frontend production 코드는 변경하지 않았다. |
| 실제 core→learning | 검증한 core JAR + 변경하지 않은 learning의 새 `bootJar`(성공) + 새 PostgreSQL/Redis/RabbitMQ, 합성 DB/JWT 계정으로 **오류 HTTP 12건** 통과. 관리자 미션 404 NOT_FOUND·409 CONFLICT·422 MISSION_PUBLISH_INCOMPLETE, 신고 대상 없음 404, 신고·시도 연결 문의·관리자 신고/문의 원문·정정 사전 조회의 범위 거부 403, 관리자 원문/정정 사전 조회의 대상 없음 404를 확인했다. 거부된 원문에서 성공 감사 증가 없음, 정정 사전 실패 시 correction/notification 0건·IN_REVIEW 유지 확인. 실제 OAuth·AI·브라우저·배포 검증은 아니다. 미지원 405/501·장애/잘못된 공급자 응답·learning 정정 POST의 409/422는 위 HTTP 대역 회귀 검증 범위다. learning 전체 테스트는 소스 변경이 없어 반복하지 않았다. |
| 소스·산출물 | worktree와 Docker 검증 소스 **764파일 SHA-256 일치**. 컨테이너/로컬 JAR SHA-256도 일치: core `f2e22f9dbad34ad7102552f68c30ac49406acadf0135621a9ffbf099cbc03a3c`, learning `5ab1010fd5ec30686dd525a3ec1955dd8eddb310f40bf68b59100543f1dbe9d0`. |

초기 저장공간 부족/Docker API 500으로 중단된 실행과, 잘못된 127.0.0.1 host override로 Ryuk 연결에 실패한 실행은 최종 통과 집계에 넣지 않았다. 복구 후 선행 #47의 Docker 사용 종료를 확인하고, 브리지 네트워크의 `TESTCONTAINERS_HOST_OVERRIDE=host.docker.internal` 및 위 검증 전용 자원 설정으로 core 전체를 다시 통과했다. core와 learning 빌드는 같은 전용 Gradle 캐시를 사용하므로 순차 실행해 초기 캐시 잠금 충돌을 피했다. 실제 연동의 전용 컨테이너/네트워크와 중지한 #163 빌드 컨테이너를 정리해 **Docker 검증 사용을 종료**했다. 재현용 소스·캐시 볼륨만 보존했다.

검증 기준은 최초 develop `7f1549a`다. 종료 전 확인한 최신 origin/develop 및 repository default branch는 `d651aa1`·`develop`이며, 후속 develop 변경과 이번 13개 변경 파일의 경로 겹침이 없음을 확인했다. 후속 develop 및 #47·#67·#162 기능을 이번 브랜치에 병합하지 않았으므로 최신 develop 통합 검증이나 원격 CI·배포 완료를 주장하지 않는다. 최종 문서 기록 뒤 `git diff --check`를 확인하고 현재 feature 브랜치에만 커밋·push하며 PR은 생성하지 않는다.

## 최신 develop 3dffad6 접합 (2026-10-30)

#163·#164를 포함한 최신 develop을 이력 보존 merge로 반영한다. 기존 미션 counts·요청/결과 감사·인증 관리자·버전 검증과 #163 Problem Details의 Content-Type/정수 status/code 대조를 모두 유지한다. sanitize는 검증된 404를 고정 문구의 안전한 응답으로 반환해 쓰기 처리의 UNKNOWN 예외 분기로 흘러 503이 되는 것을 방지한다. 정상 404 쓰기는 REJECTED와 X-Admin-Operation-Id를 남기며 불명확한 404·405·501은 503/UNKNOWN이다. 지원 GET 403/404 매핑과 #164 검증 도구 변경은 develop 그대로 보존한다. 과거 절의 “#163 미통합”은 해당 시점의 이력이다.

### 최신 develop 접합 검증 결과

- 원격 develop/MERGE_HEAD를 재조회해 모두 3dffad625890206af6b364e77a4925702d9833a4임을 확인했다.
- 영향 범위 core 6클래스 99개와 bootJar 통과(실패·오류·생략 0, 8m26s): AdminOperations 17, Support 22, 관리자 대화 재처리 18, 분석 대화 22, REPORT 재처리 19, REPORT 메시징 1. 검증된 404의 조회/쓰기 계약·REJECTED 감사·확인 번호와 불명확한 오류의 503/UNKNOWN, 기존 재처리·근거·저장 회귀를 포함한다.
- 계약 검사 93개 중 #164의 7개는 최초 샌드박스 임시 폴더 쓰기/정리 권한 오류로 실행되지 못했다. 다른 86개는 통과했고 쓰기 가능한 검증용 TEMP/TMP로 해당 7개를 재실행해 모두 통과했다. 테스트 코드나 판정 조건은 변경하지 않았다.
- core/AI/learning/support 소비 OpenAPI 4종의 표준·중복 키 검사, 실제 지원 HTTP 응답 7종 및 403/404 응답 2종의 공개 Problem 스키마 대조 통과.
- 프론트 131개 테스트·lint·build 통과. production 프론트는 기존 통합본과 같고 #163 소비자 테스트가 추가됐다. 기존 번들 크기 경고는 유지한다.
- 최신 core JAR→실제 learning HTTP 10건·감사 9행 통과. 조회·쓰기 NOT_FOUND의 고정 문구 및 쓰기 X-Admin-Operation-Id를 확인했고, 생성/수정·409·권한·전체 counts·감사 저장 장애의 결과 보존 검증도 유지했다. 합성 계정/JWT이며 실제 OAuth 검증이 아니다.
- #163 LearningSupportClient/SupportIntegrationTest와 #164 verify_feedback_learning.py는 develop 원본과 동일하다. 기존 AI·프론트 실행 코드·V17~V19 migration은 이전 통합 커밋과 동일하다. 변경 없는 AI·전체 migration·브라우저·프로세스 복구 검사는 반복하지 않았으며 앞 절의 결과를 이력으로 유지한다. 검증 컨테이너의 소스 해시 일치 및 최종 diff 검사를 확인했다.

이 절이 이전 “#163·#164 미반영” 상태를 대체한다. 두 이슈의 변경은 develop 이력으로 포함하며 이 PR의 해결 이슈는 #47·#67·#162다. 원격 CI·배포는 아직 검증하지 않았고 PR 생성 후 확인한다.
