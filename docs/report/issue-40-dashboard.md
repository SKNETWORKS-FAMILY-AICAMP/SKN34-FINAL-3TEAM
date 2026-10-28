# #40 학생·학부모 대시보드 조회

> 현재 계약과 재검증은 아래 **#27 실제 공급자 통합** 절을 따른다. 초기 검증 수치는 당시 실행 이력이다.

## 기준 및 범위

- 2026-10-28 origin/develop `78bbdc1`에서 `feature/core-dashboard-queries` 분기. #37·#38·#39 및 #42·#45 포함. 기존 체크아웃은 전환하지 않았다.
- core `learning/`의 7개 공개 조회만 구현한다. #44 알림, #58 기기·PIN, preferences 및 learning 공급자의 DB 집계는 범위 밖이다.
- #27은 확인 시 open이며 `/exists`만 구현되어 있다. 아래 추가 내부 경로는 **소비자 구현용 예정 계약**이며 실제 공급자 구현 완료를 뜻하지 않는다. 공급자 코드 복사나 중복 집계는 하지 않는다.

## 계약 결정 근거

- api-spec 1.1·1.5·1.6·2.3·3.8·3.9·4.1·5.3, P05·P08, frontend의 `StudentHome`, `Summary`, `ThinkingResponse`, `RecordPage`, `PublicAttempt`를 대조했다.
- 프론트 목업의 고정 날짜는 운영 기본값이 아니다. 날짜를 모두 생략하면 KST 오늘 포함 최근 7일, 한쪽만 전달하면 400으로 확정한다. 상세도 동일 기간을 받되 원문은 전체 시도 이력을 반환한다. period는 learning이 실제 적용한 기간을 보존한다.
- 학생 home은 core의 현재 Child 프로필과 learning의 `{studentId,state,period,resume,missions}`를 조합한다. 학년·demo는 기존 StudentLearningContextService에서 얻어 전달한다. records의 resume는 기간 밖/제출 전 시도도 식별할 수 있으나 초안은 포함하지 않는다. 공개 home의 초안은 기존 학생 전용 시도 상세에서 조합하며 집계는 P08만 사용한다.
- 기록 목록은 학생·학부모 모두 P08 대상, page=0/size=20(최대 100), 선택 status=IN_PROGRESS|COMPLETED. 초안만 있는 이어하기는 home으로 분리한다.
- 학부모 상세는 기존 Attempt 필드를 최상위에 유지하고 state·period를 추가한다. draft와 모든 중첩 memo는 응답 직렬화 전에 제거한다. 소수는 BigDecimal로 읽어 Metric 정밀도를 유지한다. 원문의 text 자체는 변경하지 않는다. 오류 응답도 같은 개인정보 경계를 적용한다.
- 공통 LearningRecordService → LearningRecordClient → LearningClient의 learning-json 서킷·내부 인증을 재사용한다. 현재 연결·ACTIVE·동의를 기존 service로 검사하고 하위 scope는 자녀 하나로 축소 후 finally 복원한다.
- 공급자의 성공 응답이 JSON/식별자/필수 조회 봉투 계약을 위반하면 502 LEARNING_CONTRACT_INVALID다. 공급자 오류·통신 실패는 NO_RECORD로 바꾸지 않는다. core에서 건수·비율·state를 계산하지 않는다.

## 연결 조건 및 검증

- #27 공급자: 예정 OpenAPI 6개 경로(학생/학부모 attempts 공유) 구현, 단일 scope 검사, P08 집계·KST 경계 적용, home의 초안 및 공개 미션 제한, 상세의 답변·되묻기·도움·돌아보기 제공이 필요하다.
- HTTP 대역 검증은 실제 #27 집계 SQL·실제 learning 연결 검증을 대신하지 않는다. core 테스트는 실제 인증 필터·JWT·PostgreSQL과 내부 HTTP 대역을 사용한다. Google OAuth 공급자는 이번 테스트에서 실제 호출하지 않는다.

## 검증 환경 및 중간 실패

- Windows JDK 21 Gradle은 loopback 연결 오류로 실행하지 못했다. 전용 Temurin JDK 21 Linux 컨테이너·전용 소스/캐시 볼륨으로 전환했다. 기존 #39 캐시는 읽기 전용으로 복제했다.
- Docker 소켓 마운트는 자동 승인 검토에서 거부되었고, 사용자에게 권한 범위를 설명한 뒤 명시적으로 허용받아 Testcontainers를 실행했다. 공유 compose·기존 DB는 사용하지 않았다.
- 첫 컴파일에서 기존 GuardianshipRecordsTest의 LearningRecordService 생성자 호출 누락을 보완했다. 기존 동의·자녀 service 인터페이스와 업무 코드는 변경하지 않았다.
- 첫 전체 테스트 실행은 183개 중 142개 통과, 41개 실패(생략 0). 검증 복사본에 저장소 루트 RabbitMQ 정의 파일이 없어 IntegrationTestSupport 초기화와 그 상속 테스트가 실패했다. 해당 파일과 이벤트 봉투 스키마를 읽기 전용으로 제공하고 실패 6개 클래스 및 소수 정밀도 수정 영향 범위만 재검증했다. 통과한 기존 SSE 80초 타임아웃 테스트 등은 반복하지 않는다.
- 프론트 첫 실행은 worktree 의존성 미설치로 실패했다. 기존 lockfile로 npm ci 후 test 75개 및 build가 통과했다. 프론트 코드·package/lockfile은 변경하지 않았다. Vite의 기존 500 kB 번들 경고는 남아 있다.
- 계약 검사: `python -m unittest discover -s scripts/tests -v` 55개 통과. core·learning OpenAPI 3.1 표준 검사 통과(기존 검증용 Python 환경의 openapi-spec-validator 사용).


## 최종 검증 결과 (2026-10-28)

| 항목 | 결과 |
|---|---|
| core JDK 21 | 전체 실행 + 실패/수정 영향 10개 클래스 재실행을 합산한 최종 **183개 통과**, 실패·오류·생략 0. 재실행 56개 모두 통과, `bootJar` 성공 |
| #40 신규 | DashboardIntegrationTest 9개, DashboardQueryTest 2개 통과. 실제 인증·타 자녀/비활성/동의 철회·KST 자정·기간/페이지/상태·단일 scope/trace·메모 미노출·NO_RECORD와 초안 공존·조회 실패·소수 정밀도 검증 |
| 내부 HTTP | 기존 LearningHttpStub가 실제 HTTP 서버로 동작. core DB는 Testcontainers PostgreSQL. #27의 실제 learning 서버/집계 SQL은 미연결 |
| 계약 | scripts/tests 55개 통과, core·learning OpenAPI 3.1 표준 검사 통과. 기존 OpenAPI 경로·스키마의 의미 변경 없음 확인 |
| 프론트 | npm test 75개 통과, npm run build 성공. 기존 번들 크기 경고. 브라우저 E2E는 미실행 |
| 변경 검토 | production 수정은 core learning 패키지만. 공통 인증·서킷·notification·PIN·기기·동의·자녀 service 구현 및 DB 변경 없음. 기존 GuardianshipRecordsTest는 생성자 인자만 보완 |
| Git | 최종 git diff --check 통과. PR 생성·병합·배포는 수행하지 않음 |

첫 실행의 183개 항목에는 ReportHttpTest 초기화 실패의 합성 `executionError` 1개가 포함되어 있었다. 최종 재실행은 해당 클래스 실제 9개와 새 소수 정밀도 테스트 1개를 포함해 고유 테스트 총 183개다. 모든 테스트를 최종 소스에서 한 번에 통과시켰다는 뜻이 아니라, 전체 실행 뒤 실패 및 변경 영향 범위를 재검증한 합산이다. 재실행 명령의 `--tests`를 `bootJar` 뒤에 둔 실행은 옵션 오류로 테스트 전 중단되었으며, `test --tests ... bootJar` 순서로 수정했다.

전체 실행 명령은 `bash gradlew test bootJar --no-daemon --max-workers=2 --no-watch-fs --console=plain -Pkotlin.compiler.execution.strategy=in-process -Dorg.gradle.jvmargs=-Xmx1024m`이다. 재실행 대상은 AuthFlowIntegrationTest, ModelVersionMessagingTest, ReportHttpTest, ReportMessagingTest, MessagingIntegrationTest, RabbitDefinitionsTest, DashboardIntegrationTest, DashboardQueryTest, LearningRecordClientTest, LearningRecordServiceTest다.

최종 JAR SHA-256: `4413f7c21ee1cfb857723ad0be95b421e7cd0ecb2b134880915b350006e39c1d`. 검증 컨테이너의 learning production Kotlin 파일 전체와 현재 worktree 파일을 바이트 단위로 대조해 일치를 확인했다. 실제 AI·Google·learning 대시보드·원격 CI·배포 검증 결과로 확대 해석하지 않는다.

## PR 전달 기준

- base: develop / head: feature/core-dashboard-queries. 확인한 저장소 기본 브랜치도 develop이다.
- 제목: `feat: 학생·학부모 대시보드 조회 API 구현`
- 본문에 `Closes #40` 포함. #40 core 소비자 구현과 HTTP 대역 검증 범위를 해결하며, #27 실제 공급자 구현/연결은 별도 후속이다. #27을 종료 대상으로 포함하지 않는다.
- 등록 라벨과 설명을 조회한 추천: enhancement(New feature or request), area:core(core 영역), 필요 시 P1(우선1·제안). #40의 Type은 조회 시 null이며 PR의 별도 Type 지원은 확인하지 않았다.
- 사용자가 PR을 직접 생성한다. 커밋·push 결과와 CI 상태는 최종 전달에서 실제 상태로 보고한다.


## #40 재리뷰 (2026-10-28)

- 최신 #27은 open·댓글 없음이며 실제 공급자는 여전히 대기 상태다. origin/develop은 47e5ffe로 갱신됐으나 신규 변경은 비용 집계·SPEECH 제거 등 #40과 별개다. 기존 feature 브랜치/이력을 유지한다.
- 확인한 문제: 학생 records의 기간 미전달, 페이지 첫 20건만 소비, 학부모 상세의 기간 유실, reflection 내부 enum/null과 화면 DTO 차이, Metric·생각 유형 내부 항목 미검사.
- 내부 공용 records는 studentId로 통일하고 core가 공개 parent childId를 변환한다. 예정 계약 수정이며 #27 담당자가 확정/구현한 계약으로 표현하지 않는다.
- 현재 StudentAccessService의 LINKED·ACTIVE·계정/법정대리인 동의 검사 및 요청 필터를 재사용한다. 단일 자녀 scope 제한과 finally 복원은 변경하지 않는다.
- 메모·draft 제거는 학부모 성공/오류 JSON의 중첩 배열에도 적용한다. 학생 resume의 본인 초안은 보존한다. 조회 실패를 NO_RECORD·임의 Metric으로 대체하지 않는다.
- 수정 및 최종 검증 결과는 다음 절을 따른다.

- 추가 계약 충돌: #27은 메모를 조회하지 않으므로 records/home.resume도 draft 없는 공개 시도로 정정했다. core는 제공된 attemptId로 기존 학생 전용 `/internal/attempts/{id}`를 호출해 본인 초안을 조합한다. 공급자가 선택한 이어하기 대상을 사용하며 core가 최신 시도를 계산하지 않는다. 두 번째 응답의 학생/시도 ID·마무리 공개 조건을 검사하며 실패하면 전체 홈 조회를 실패시킨다.


### 재리뷰 수정 결과

| 발견 항목 | 수정 |
|---|---|
| 학생 선택 기간 미전달·목록 첫 페이지만 사용 | 학생 API에 from/to를 전달하고 배열 소비자는 페이지를 끝까지 조회한다. 페이지·대상·기간·중복/변동 건수 불일치는 명시적 오류다. 학부모 대시보드는 이전/다음 페이지를 제공하며 query key에 페이지·상세 기간을 포함한다. |
| #27 메모 제외 계약과 home의 private draft 요구 충돌 | records/home.resume는 DashboardPublicAttempt로 정정. 이어할 시도가 있으면 같은 검증된 STUDENT scope로 기존 `/internal/attempts/{id}`를 호출한다(없으면 records 1회, 있으면 총 2회). 두 번째 응답의 학생·시도 ID, IN_PROGRESS, 초안 version/content, 마무리 공개 조건을 검사한다. |
| 내부 식별자의 역할별 DTO 차이 | 공용 내부 records는 studentId, 공개 parent summary/thinking-types/attempts는 core가 childId로 매핑한다. 집계는 변경하지 않는다. |
| Metric·유형 내부 항목 미검사 | 필수 수치·문자열·상태·기간·출처 타입과 다섯 유형의 누락/중복을 검사한다. 계약 위반은 502이며 임의 수치나 NO_RECORD를 만들지 않는다. |
| 빈 finishedAt으로 공개 조건 통과 가능 | non-null finishedAt은 유효한 Instant여야 한다. 빈 문자열·잘못된 시각은 502로 거부한다. |
| reflection wire enum/null과 화면 DTO 차이 | 공용 기록 표시 어댑터에서 EASY/NORMAL/HARD 및 nullable text를 기존 한국어 표시값으로 변환한다. 원문은 보존하고 알 수 없는 값은 오류로 처리한다. |
| 실패/처리 중을 정상 관찰·빈 기록으로 표시 | 목록/상세 상태를 구분해 표시하고 배열 소비 경로에서는 실패/처리 중을 오류로 전달한다. |

자녀 권한 검사의 우회는 이번 리뷰 범위에서 발견하지 않았다. 기존 PublicAuthFilter → AuthService/StudentAccessService의 현재 연결·활성·계정 및 법정대리인 동의 검사, 단일 scope와 finally 복원을 유지했다. 타 자녀·연결 해제·비활성·동의 철회 및 공급자의 타 학생 응답 거부를 검증했다. 학부모 성공/오류 응답의 중첩 객체·배열 memo/draft 제거와 학생 홈의 본인 초안 보존을 확인했다.

### 재리뷰 최종 검증

- JDK 21 전체 `test bootJar`: **185/185 통과**, 실패·오류·생략 0 (10m45s).
- 추가 홈 수정 후 DashboardIntegrationTest·DashboardQueryTest·LearningRecordClientTest·LearningRecordServiceTest 및 bootJar 재검증: **19/19 통과** (2m14s). 최종 고유 테스트 **186개 통과**이며 전체 실행+영향 범위 재검증 합산이다. 기존 전체 성공 테스트를 모두 다시 실행한 결과로 표현하지 않는다.
- `npm test`: **79/79 통과**. `npm run build` 성공. 변경 프론트 파일 11개의 oxlint 성공. 기존 Vite 500 kB 번들 경고만 남았다.
- 계약 scripts/tests 전체 **56/56 통과** 후 홈 경계 수정의 dashboard 계약 **4/4 통과**(신규 1개 포함, 고유 57개). core·learning OpenAPI 3.1 검사 통과. 최종 git diff --check 통과.
- 최종 JAR SHA-256: `c4f11b89a7af84157300ed216ee46db4c9d4ca74b8831325675ad53083e3ceeb`. 검증 컨테이너의 수정 클라이언트와 worktree 소스 바이트 일치를 확인했다.
- HTTP 대역은 records 응답과 기존 학생 attempt 상세 응답 모두에 사용했다. 실제 learning 대시보드·실제 두 learning API의 연결·브라우저 E2E·배포는 검증하지 않았다. #27은 open이며 새 내부 계약은 공급자 확인/구현 대기 상태다.
- 새 production 의존성·마이그레이션·#44 notification·#58 PIN/기기/재인증 구현은 추가/변경하지 않았다. 기존 커밋은 보존하고 같은 feature 브랜치에 후속 커밋한다. PR은 생성하지 않는다.


## #27 실제 공급자 통합 (2026-10-28)

- 같은 feature/core-dashboard-queries에서 origin/develop b344797(PR #105)을 merge한다. #44·#58·비용 집계 수정 등 develop의 병합된 코드를 보존한다. 기존 작업 커밋을 squash/rebase하지 않는다.
- learning OpenAPI는 #27의 실제 21개 경로·Record 스키마 하나로 통합하고 planned-issue-27 경로·중복 Dashboard 스키마를 제거한다. api-spec의 공급자 기록 절은 #27 정의를 유지한다.
- core 공개 Dashboard 시도·상세 및 홈 resume에 completedAt·hintUsages와 기록 reflection.createdAt을 보존한다. thinking-activities의 reflection은 공급자의 기본 Reflection(difficulty/text)이며 createdAt을 강제하지 않는다.
- 프론트 표시 어댑터는 새 필드를 보존한다. 홈은 records resume를 전체 교체하지 않고, 검증된 학생 전용 상세에서 draft만 조합해 기록 메타데이터 유실을 막는다.
- 실제 core/learning JAR·분리된 폐기 가능 DB·합성 fixture로 검증한다. 공유 compose·기존 DB는 사용하지 않으며 AI/Google 실호출은 범위 밖이다. 실행 결과는 최종 검증 후 기록한다.


### Docker 중단 당시 진행 기록

- scripts/tests 58개 통과, core·learning OpenAPI 3.1 검사 통과. 프론트 테스트 80개·build·변경 DTO lint 통과(기존 번들 크기 경고).
- backend 검증은 Docker Desktop 자원 경합으로 순차 실행으로 조정했다. learning production compile/bootJar 및 테스트 실행 단계까지 확인했지만, 이후 Docker Desktop API가 반복적으로 500을 반환하고 조회 명령이 멈춰 최종 결과를 수집하지 못했다. core 전체 테스트와 실제 core→learning 연결 결과도 아직 확정하지 않았다.
- 실제 연결 스크립트 scripts/verify_dashboard_learning.py를 작성했고, 전용 PostgreSQL/Redis/RabbitMQ·Python/JDK 런타임을 준비했다. 실제 연결 성공으로 보고하지 않는다.
- Docker 복구 후 backend 결과 수집/필요한 재실행과 실제 연결 검증을 마친 뒤에만 merge 커밋·push한다. 공유 Docker 재시작은 다른 채팅/서비스에 영향을 줄 수 있어 사용자 확인을 요청했다.


### #27 통합 최종 검증 (2026-10-28)

- Docker 복구 후 core의 중단 로그에서 Redis 의존성 Maven DNS 실패를 확인했다. 검증된 #58 Gradle modules 캐시를 읽기 전용으로 복제해 core는 offline으로 재실행했다. 공유 Docker/서비스는 임의 재시작하지 않았다.
- core 전체 205개 실행 중 20개 실패: DashboardIntegrationTest 13개는 #58 V13의 필수 pin_failed_count를 누락한 기존 #40 fixture였다. 합성 학생 INSERT 두 곳에 0을 넣어 13개 모두 재검증 통과. LlmUsageQueryTest 7개는 여러 Spring 테스트 컨텍스트가 공유하는 폐기 PostgreSQL의 연결 수 한도 초과였으며 별도 테스트 JVM에서 7개 모두 통과했다. production 풀 설정은 변경하지 않았다.
- 최종 core 고유 **205개 통과**, 실패·오류·생략 0(전체 실행 + 실패 범위 재검증 합산). core bootJar 성공. 모든 테스트를 최종 소스에서 한 번에 통과시킨 것으로 표현하지 않는다.
- learning 전체 **183개 통과**, 실패·오류·생략 0, bootJar 성공. learning production 소스는 develop b344797의 #27 구현을 그대로 사용했다.
- scripts/tests **58개 통과**, core·learning OpenAPI 3.1 검사 및 git diff --check 통과. 프론트 **80개 통과**, build·변경 DTO lint 성공(기존 번들 크기 경고).
- 실제 core/learning JAR + 전용 PostgreSQL 두 DB·Redis·RabbitMQ를 scripts/verify_dashboard_learning.py로 실행해 **9개 시나리오 통과**. Google identity/과거 시각은 합성 SQL fixture이며, 동의·자녀 등록·학생 진입·미션 시작·초안·답변 제출과 7개 공개 조회는 실제 HTTP를 사용했다. AI 호출은 하지 않았다.
- 실제 검증: 빈 기록/기본 KST 기간, 제출 전 초안 이어하기와 메타데이터 보존, 과거 목록의 종료일 경계와 상세 전체 이력, 5건 집계·페이지·status·다섯 유형, 인증·타 자녀·날짜·페이지·내부 scope, 비활성/연결 해제/동의 철회 거부, 실제 learning 접근 로그의 단일 parent scope·trace, learning 프로세스 중단 시 503 LEARNING_UNAVAILABLE 전달. 성공 응답은 공개 OpenAPI 스키마로 검사했고 학부모 응답의 draft/memo·메모 원문 미노출을 재귀 검사했다.
- 실제 core 상세 응답을 Node의 recordDto에 입력해 reflection.createdAt·hintUsages 보존도 통과했다. 브라우저 E2E·Google/AI 실호출·배포는 미검증이다.
- 실제 연결 첫 실행은 부하 상황의 Redis 초기 연결 2초 제한으로 core 기동이 실패했다. 검증 실행에만 Redis connect/read timeout 30초를 지정하고 새 폐기 DB에서 재실행해 통과했다. production Redis 설정이나 core→learning timeout은 변경하지 않았다.
- 실제 검증 JAR SHA-256: core `1f5bb658e8a8e72af32f19e557343e87274c24ddf0288a11a4350ec9ff99cd69`, learning `204400babbc545ca5149b9f8e8779e627595a40880b72910789ff92e5bf911b8`. 검증한 production client와 worktree 소스가 바이트 단위로 일치했다.
- 기존 #40 두 커밋을 보존하고 develop b344797과의 merge 커밋으로 통합한다. PR은 생성하지 않는다. 이전의 #27 공급자 대기 상태는 이번 통합으로 해소됐다.


## 최신 develop 추가 반영 (2026-10-28, 7f30c2e)

- 같은 feature/core-dashboard-queries에 origin/develop 7f30c2e를 merge했다. #50(PR #101)·#51(PR #108), AI 분석(PR #107), QR 시연(PR #106) 변경을 보존했으며 텍스트 충돌은 없었다.
- #40의 core/learning 소스·테스트·설정과 core/learning OpenAPI는 이전 검증 커밋 ce58afd에서 변경되지 않았음을 git diff로 확인했다. 앞선 core 205개 합산·learning 183개·실제 연결 9개 결과를 이번에 재실행한 것으로 표현하지 않는다.
- 변경 영향 검증: scripts/tests 58개, 프론트 테스트 87개, 프론트 build·전체 oxlint, core/learning/ai OpenAPI 3.1 검사 및 git diff --check 모두 통과했다. 기존 Vite 번들 크기 경고는 남아 있다.
- #40 대시보드 계약과 report의 studentId·조회 기간·시각 필드 계약을 대조했다. core/learning/리포트 전체 생성 E2E·실제 AI 호출·QR 브라우저 시연은 이번 통합에서 추가 실행하지 않았다. AI/report 서비스 내부 테스트는 해당 develop 병합 PR의 검증 범위이며 이번 #40 실행 결과로 합산하지 않는다.
- 기존 작업 커밋을 보존하고 추가 merge 커밋을 같은 작업 브랜치에 일반 push한다. PR은 사용자가 직접 생성한다.
