# #40 학생·학부모 대시보드 조회

## 기준 및 범위

- 2026-10-28 origin/develop `78bbdc1`에서 `feature/core-dashboard-queries` 분기. #37·#38·#39 및 #42·#45 포함. 기존 체크아웃은 전환하지 않았다.
- core `learning/`의 7개 공개 조회만 구현한다. #44 알림, #58 기기·PIN, preferences 및 learning 공급자의 DB 집계는 범위 밖이다.
- #27은 확인 시 open이며 `/exists`만 구현되어 있다. 아래 추가 내부 경로는 **소비자 구현용 예정 계약**이며 실제 공급자 구현 완료를 뜻하지 않는다. 공급자 코드 복사나 중복 집계는 하지 않는다.

## 계약 결정 근거

- api-spec 1.1·1.5·1.6·2.3·3.8·3.9·4.1·5.3, P05·P08, frontend의 `StudentHome`, `Summary`, `ThinkingResponse`, `RecordPage`, `PublicAttempt`를 대조했다.
- 프론트 목업의 고정 날짜는 운영 기본값이 아니다. 날짜를 모두 생략하면 KST 오늘 포함 최근 7일, 한쪽만 전달하면 400으로 확정한다. 상세도 동일 기간을 받되 원문은 전체 시도 이력을 반환한다. period는 learning이 실제 적용한 기간을 보존한다.
- 학생 home은 core의 현재 Child 프로필과 learning의 `{studentId,state,period,resume,missions}`를 조합한다. 학년·demo는 기존 StudentLearningContextService에서 얻어 전달한다. resume는 기간 밖/제출 전 초안도 포함할 수 있으며 집계는 P08만 사용한다.
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
