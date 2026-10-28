# #46 신고·문의·공지·도움말

기준 origin/develop 8202f584faebc58459bc1a485cfeb5accd1cd6f4, feature/core-support 전용 worktree. 기존 checkout·공유 서비스 불변. PR base develop.

## 설계 근거
기존 신고 student_id는 대상 학생이며 요청 역할을 구분하지 못하고 문의는 user_id만 있다. V14에 요청 역할·학생 주체를 분리한다. 기존 이력에 역할을 추정하지 않는다. 새 production 의존성 없음.

학생 결과는 본인 목록/상세에서 확인하며 보호자 계정 알림에 보내지 않는다. 보호자 결과만 #44 service 확장과 NotificationStored/커밋 후 Redis를 재사용한다.

learning 실제 controller와 OpenAPI에는 정정·대상 확인·관리자 원문 API가 없다. 별도 공급자 필요 계약에 구체화하고 core에서 성공 fallback을 만들지 않는다. HTTP 대역은 테스트 전용이다.

정정은 durable intent → HTTP(트랜잭션 밖) → finalize + 알림. 동일 신고의 고정 correction ID를 공급자 멱등 키로 쓴다. 완료 전 오류는 재시도 가능, 공급자 멱등 계약 없이는 실제 중복 방지를 보장할 수 없다.

## 검증
최종 로컬 검증은 아래 결과를 따른다. learning 공급자 E2E·원격 CI·배포는 미검증이다.

마이그레이션 병렬 작업 확인: #41은 V13까지, #48은 V15를 사용 중임을 실제 worktree에서 확인했다. #46은 V14이며 기존 V13을 수정하지 않는다. 기존 복수 correction 이력은 유지하고 새 request_key가 있는 행만 신고당 1개로 제한한다.

관리자 정정 소비자는 신고 UUID를 Idempotency-Key로 사용한다. 신고당 1개 정정 의도 계약에 맞춰 화면 새로고침·재진입 후에도 같은 요청으로 재개한다. core는 별도 영속 correction UUID를 learning 멱등 키로 사용하며 호출자의 키를 새로 생성하지 않는다.

## 실제 호출 흐름·권한

- SupportController → SupportService → SupportRepository/SupportMapper → core_db. Controller는 인증 identity와 DTO/헤더만 전달한다. 다른 기능 저장소는 참조하지 않는다.
- 대상 검증: support service → StudentAccessService(연결·동의), ConversationSupportService(본인 완료 메시지), ReportSupportService(완료 리포트), LearningSupportClient → 기존 LearningClient → InternalRestClientFactory(내부 토큰·검증된 컨텍스트·타임아웃·서킷).
- 원문: 저장된 attemptId/studentId → learning HTTP → 학생/시도 일치 검사·draft/memo 제외 → audit_log 별도 트랜잭션 성공 → 응답. 다른 attemptId query는 원문 대상을 바꾸지 않는다. context가 없으면 관리자 역할을 만들어 내지 않는다.
- 정정: 신고 행 잠금으로 단일 의도 저장 → 잠금/트랜잭션 종료 → 고정 correction UUID로 learning 호출 → 신고 행 재잠금 → 공급자 결과·이전 결과·영향·완료 시점·신고 완료·감사·알림 저장. HTTP 오류는 FAILED, core finalize 실패는 이전 의도를 유지한다. 공급자에서 같은 UUID/본문을 같은 결과로 재구성하는 계약이 필수다.
- 알림: support → NotificationService.support → 기존 NotificationRepository.insert(수신 설정·유일성) → NotificationStored → 기존 커밋 후 Redis publisher → NotificationDeliveryService. 비활성 계정·철회 동의·해제 자녀는 생성하지 않는다. sourceEventId는 신고/문의 ID, 원문 없는 완료 안내만 생성한다. 학생 건은 보호자에게 보내지 않는다.
- 공지: 등록/수정/종료 전후를 audit_log에 보존하며 DELETE는 ended_at만 기록한다. help/notices만 PublicAuthFilter의 공개 예외에서 제거하고 Google·기기·PIN·탈퇴 상태 토큰의 정확한 예외는 유지한다.
- 프론트는 기존 관리자 신고 화면의 enum 정정 입력·안정적인 키·객체 impact 표시를 맞추고, 학생/학부모 support 결과 경로를 추가했다. 문의 등록·공지 관리 등 새 운영 화면은 이번 범위에 추가하지 않는다.

## 공급자에 필요한 확인

`contracts/openapi/support-learning-required.yaml`은 구현되어 있다는 주장이 아닌 협의용 계약이다. learning 담당자는 대상 ID→학생/시도 매핑, 단일 학생 scope의 ADMIN 원문 조회(draft/memo 제외), 정정 idempotency/reportId 중복 방지와 최초 결과 재구성, impact의 실제 반영 범위를 구현·확인해야 한다. core는 미구현/HTTP 실패를 SUPPORT_DEPENDENCY_UNAVAILABLE로 반환하고 완료 처리하지 않는다. ANALYSIS/REPORT 정정은 별도 공급자 계약이 없어 422 CORRECTION_TARGET_UNSUPPORTED이며 이번 작업에서 ai/report 정정을 확장하지 않는다.


## 최종 검증 재개·최신 develop 반영

2026-10-28 작업을 외부 tar·binary diff·해시와 stash로 보존한 뒤 feature/core-support를 origin/develop 7f30c2ee0691b301d32e7ef757eff2547e73eb3a로 fast-forward하고 변경을 복원했다. 기존 체크아웃은 전환하지 않았다. #27의 실제 기록 상세는 PARENT/STUDENT/SYSTEM만 허용하므로 관리자 원문 공급자로 위장 재사용하지 않는다. learning 정정·target ID 조회·관리자 원문 공급자는 여전히 미구현이다.

멱등 응답 재구성 검토에서 최초 접수 응답에 처리 후 상태·정정 이력이 섞일 수 있는 경로와 DB 시각 정밀도 차이를 보완했다. POST 응답은 최초 RECEIVED 영수증을 재구성하고 현재 상태는 GET에서 제공한다. 문의는 원래 명세 2.7대로 세 분류를 학생·보호자 모두 허용하며 결제 데이터 접근 권한은 부여하지 않는다.

앞선 실행은 테스트 import 충돌 수정 후, Windows bind 경로의 Redis 2초 연결 초기화 실패와 이후 Docker 연결 unexpected EOF로 완료되지 않았다. 기존 DLQ 30초 대기 실패의 코드/환경 원인은 재실행 결과와 구분하여 기록한다. 실패한 실행을 통과한 것으로 집계하지 않는다.


## 최종 검증 결과 (2026-10-28)

- 기준: 최신 origin/develop `7f30c2ee0691b301d32e7ef757eff2547e73eb3a` + 이번 작업. 검증한 core·프론트·OpenAPI 소스의 SHA-256과 현재 worktree 파일 일치를 확인했다. 최초 작업 기준 `8202f58`과 최신 통합 기준을 구분한다.
- JDK 21 `test bootJar` 성공: 36개 클래스, 204개 테스트, 실패·오류·건너뜀 0. SupportIntegrationTest 12개 + PostgresRepositoryTest 기반 SupportRepositoryTest 2개를 포함한다. 기존 알림·리포트·인증·학생 기기·SSE·메시징 회귀도 같은 전체 실행에 포함된다.
- 실행: `docker run --rm --name issue46-core-verify --memory=2g --cpus=2 ... eclipse-temurin:21-jdk bash gradlew test bootJar --no-daemon --max-workers=1 --no-watch-fs --console=plain '-Dorg.gradle.jvmargs=-Xmx512m -XX:ActiveProcessorCount=2' '-Pkotlin.compiler.execution.strategy=in-process' --init-script /verify/limits.gradle`. 전용 Linux source/cache 볼륨, test fork 1·heap 512MiB·CPU 2. 기존 공유 서비스 대신 IntegrationTestSupport의 실제 PostgreSQL·Redis·RabbitMQ를 사용했다.
- 이전 DLQ 30초 대기 테스트는 timeout이나 production 로직을 바꾸지 않은 최종 전체 실행에서 통과했다. 이전 Docker unexpected EOF의 시스템 원인을 확정한 것은 아니며, 실패/중단한 실행을 성공 수치에 합산하지 않았다.
- 신규 검증: 학생/형제/보호자 scope 분리, 신고 대상 위조와 공급자의 범위 밖 원문 거부, 저장된 연결 ID만 원문 조회, 열람별 감사·감사 실패 응답 차단, 신고 접수 후 정정 미발생, 동시 신고·최초 응답 저장 유실·관리자 처리 뒤 접수 응답 재구성, 정정 동시 재시도·응답 유실·core finalize 롤백, 이전 판정 코드·사유·시점·공급자 결과 보존, 문의 답변 불변·학생 건 보호자 알림 제외, 수신 거부·해제/탈퇴 제외·롤백·커밋 후 실제 Redis 전달, 공지 역할/미래/종료 기간·종료 이력, help/notices 인증을 확인했다.
- learning HTTP는 test-only LearningHttpStub 계약 대역이다. supplier ledger에 적용한 뒤 응답 연결을 끊는 경우와 core 저장 trigger 실패를 주입하여 고정 요청 ID의 1회 적용을 확인했다. 실제 learning 판단 변경·집계/대화/리포트 반영 검증으로 표현하지 않는다. learning ERD의 judgment_correction.previous/corrected 전체 JSON 보존은 공급자 책임이며 core에는 이전 판정 코드와 처리 확인 결과를 저장한다.
- `python -O -m unittest discover -s scripts/tests -q`: 56개 통과. `validate_support_contracts.py`: 실제 MockMvc 응답 5종(신고·관리자 원문 상세·문의·공지·도움말)의 스키마·UUID/시각 형식 통과. `validate_notification_contracts.py`: 실제 알림 목록·설정 통과. `validate_report_contracts.py`: 실제 RabbitMQ 이벤트 4종 봉투/데이터와 core HTTP 상세 통과. 처음 report artifact 회수 경로를 빠뜨린 검사 명령은 파일 없음으로 실패했으며 build/contracts를 회수한 뒤 재검증했다.
- 새 `issue46-resume-schema-postgres`에서 `check_db_migrations.py` 전체 cycle 통과: core 40테이블/365컬럼, learning 19/156, report 6/44, 위반 입력 57건·CHECK 69집합·ERD 인덱스 23개. 재실행 migration 0·이력 불변, report downgrade/upgrade와 재대조 통과. 기존 공유 DB는 사용하지 않았다.
- 최신 프론트 `npm test`: 83개 통과, lint·build 성공. 기존 500KB 초과 번들 안내는 남아 있다. 새로운 production 의존성은 없다.
- 별도 core bootJar + PostgreSQL·Redis·RabbitMQ 전용 네트워크에서 실제 프론트 apiFetch/adminApi 소비자를 실행했다. 문의·REPORT 대상 신고 접수 → 관리자 답변/검토 완료 → `/parent/support` 알림 링크의 본인 상세 조회, 학생의 보호자 문의·ADMIN 도움말 접근 거부를 확인했다. notification 2건의 실제 Redis 발행 성공 후 COMPLETED·failure_reason NULL 저장과 core health UP도 확인했다. 합성 인증 fixture이며 실제 Google 로그인·브라우저 UI E2E·배포 검증은 아니다.
- bootJar SHA-256: `6648c2ac2980d3ae49b348c112b071d832c19189a9c523d2bcd8a0daf3dbeaf6`. spring-data-redis·Lettuce 포함, Testcontainers·JUnit·Mockito·Flyway 미포함을 확인했다.
- 최종 변경의 계층·소유권·호출 흐름을 대조했고 `git diff --check` 통과. source 외의 토큰·합성 DB fixture·로그·아카이브·빌드 산출물은 저장소에 포함하지 않는다.

## PR 준비 초안

- head: `feature/core-support`, base: `develop`. PR은 사용자가 직접 생성한다.
- 제목: `feat: 신고·문의·공지·도움말과 처리 결과 알림 구현`
- learning 공급자 구현/계약 수용 및 실제 연동은 미완료다. 아래 종료 구문은 core 이슈의 해결 범위를 검토한 뒤 사용할 PR 초안이며, 실제 공급자 연동 완료를 뜻하지 않는다.

```markdown
Closes #46

신고·문의·공지·역할별 도움말을 core API로 구현하고 보호자 처리 결과를 기존 알림 저장·커밋 후 Redis 전달에 연결합니다.

- 학생·형제·보호자의 공유 계정 ID를 요청 역할·학생 주체로 분리하고 대상 소유권을 검사
- 신고 중복/동시 제출과 최초 응답 복구, SERVICE_OPS 원문 연결 제한·필수 감사 저장
- 영속 정정 요청 → 트랜잭션 밖 learning HTTP → 결과·완료·알림의 원자적 저장, 재시도/응답 유실/저장 실패 처리
- 문의 답변 불변, 공지 역할·공개 기간·종료 이력, 인증된 도움말·공지 조회
- V14와 최소 프론트 정정 계약·알림 결과 조회 경로, 기존 V13 보존

검증: core 204개 테스트·bootJar, 프론트 83개·lint·build, 계약 56개 및 실제 JSON/이벤트 대조, 전체 DB migration/ERD cycle, 격리 core에 대한 실제 프론트 API 소비자 연결 통과.

한계: learning 대상 확인·관리자 원문·정정 API는 아직 공급자 구현이 없어 계약 HTTP 대역으로 검증했습니다. 실제 learning 정정·집계·대화·리포트 반영, 실제 Google/브라우저 E2E·원격 CI·배포는 완료로 표시하지 않습니다. 필요한 공급자 계약은 contracts/openapi/support-learning-required.yaml과 docs/report/issue-46-support.md를 참고합니다.
```


PR 메타데이터 후보(최종 준비 시 실제 등록값 재조회): `enhancement`(신규 기능) + `area:core`, 스키마·소비자 범위 보조로 `area:db`·`area:web`. 조직 Issue Type 목록 API는 401로 조회할 수 없어 Type 후보를 추정하지 않았다. 실제 저장소 기본 브랜치도 develop으로 확인했다. 해결 범위를 충족한 PR이 develop에 병합되면 `Closes #46` 자동 종료 조건에 해당한다. PR은 아직 생성하지 않았으며 공급자 실연동 미완료를 초안에 명시했다.
