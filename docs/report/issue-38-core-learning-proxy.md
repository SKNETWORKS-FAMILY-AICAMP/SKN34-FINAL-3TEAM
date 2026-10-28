# #38 학생 미션 공개 API·멱등성

## 기준과 범위

- 최초 구현·검증 기준: origin/develop `ecd6ecf7880e90341855d2fad6d9e773f3711c67` (#36 PR #61 병합 포함). PR 준비 기준은 아래 별도 절을 따른다.
- 전용 worktree·feature/core-learning-proxy 사용. 원본 체크아웃·다른 작업의 변경을 보존한다. 최초 구현 단계에서는 commit·push·PR 생성을 수행하지 않았다.
- 공개 미션/시도 10개 경로를 learning 내부 경로로 전달한다. #37·#43·#39·#58 업무는 추가하지 않는다.
- 최초 구현 시 #22·#23·#24·#26은 open·댓글 없음이고 기준 코드에 실제 핸들러가 없었다. PR 준비 중 #22/PR #62가 추가 병합되어 미션 조회 2개는 실제 연결까지 검증했다. 나머지 8개 시도 API는 HTTP 대역 검증과 실제 미연동을 구분한다.

## 결정과 영향

- 설계 → OpenAPI → 구현 순서로 일반 JSON 프록시·장애·멱등성 계약을 보충한다. 미션 업무 검증·DB 조회는 learning 소유다. core는 #36의 검증된 STUDENT 컨텍스트만 사용한다.
- 기존 InternalRestClientFactory의 컨텍스트 전달을 재사용한다. 인증·#37 service 인터페이스는 변경하지 않는다.
- Resilience4j circuitbreaker 2.3.0 production 의존성을 추가한다. P12의 최근 20건·실패율 50%·30초 차단과 half-open 복구를 담당한다([공식 설정 문서](https://resilience4j.readme.io/docs/circuitbreaker)). HTTP 자동 재시도는 없다. 일반 호출 연결 2초·응답 30초, 피드백 80초는 #39 범위다.
- 기존 idempotency_record만 사용한다. 세션 advisory lock과 같은 auto-commit 연결에서 레코드를 읽고 쓴다. HTTP 중 트랜잭션 없음. MyBatis의 요청별 연결 반환과 달리 잠금 소유 연결을 명시적으로 보유해야 하므로 이 Repository만 JDBC를 사용한다. 요청당 DB 연결 1개를 HTTP 동안 보유하는 비용이 있으며 풀 용량과 HTTP 타임아웃이 동시 처리 상한을 결정한다.
- 동시 재요청은 409·Retry-After, 같은 계정의 endpoint/학생/원문 불일치는 422. 확정 응답은 원문·필수 헤더와 상태를 보관한다. 미확정·5xx·전송 실패는 같은 키로 다시 learning에 호출한다. core 저장 실패 시 503이며 최초 learning 성공 응답을 성공으로 가장하지 않는다.
- learning은 전달받은 키의 UK·본문 대조·최초 응답 재구성 및 답변/판정 원자적 저장을 제공해야 한다. 이 선행 계약 없이는 core만으로 두 DB 사이 exactly-once를 보장할 수 없다. core TTL이 지나도 learning의 답변 UK는 유지한다.
- 스키마 변경·신규 Flyway 버전 없음. V1~V8 보존. 24시간 만료는 DB 시계와 주기 삭제로 처리한다.
- 기존 프론트 `frontend/web/src/data/classroom/apiGateway.ts`의 미션/시도 경로·답변 키·초안 If-Match 사용을 확인했다. 경로/헤더 계약 변경이 없어 소비자 코드는 수정하지 않는다. 실제 응답 DTO 및 화면 통합은 learning API 제공 이후 확인한다.

## 공통 파일 변경

| 파일/영역 | 변경 |
|---|---|
| core build.gradle.kts | circuitbreaker 의존성 1개 |
| InternalRestClientFactory | 기존 기본값을 유지하는 선택 readTimeout 인자. #36 호출/인터페이스 변경 없음 |
| `_common/web/` | 공통 멱등성 조합·JDBC Repository·원문 HTTP 결과·Retry-After 오류 처리 |
| core-service OpenAPI | Learning 10개 operation 및 전용 parameters/requestBody/responses 추가, 기존 Auth/Account 유지 |
| 설계 3개 문서 | 장애·동시성·응답 봉투·트랜잭션 경계·시도 시작 내부 경로 보충 |
| test_auth_openapi.py | 기존 인증 6개 operation 검사 범위를 Auth/Account로 유지. Learning 별도 검사 추가 |
| guardianship의 새 StudentLearningContext service/domain/Repository/Mapper | #62 연동에 필요한 core 소유 학생 학년·시연 여부 읽기. 기존 StudentAccessService 및 반환 모델은 유지 |

application.yml·인증 필터·기존 account/consent/guardianship service 인터페이스·V1~V8·프론트는 변경하지 않는다. #37·#43의 OpenAPI·Gradle·설계 변경과 통합할 때 이번 추가 구간을 함께 보존해야 한다.
병렬 worktree의 #37 Consent/Children, #43 Admin/ModelRegistry 태그 추가를 읽기 확인했다. 기존 인증 검사는 Auth/Account 태그만 선택해 해당 경로와 충돌하지 않게 한다. 다른 worktree 파일을 수정하거나 변경분을 이 브랜치에 합치지 않는다.

## 실제 learning 연결 조건

1. #22 미션 목록·상세의 실제 연결은 아래 최종 검증에서 확인했다. #23·#24·#26의 나머지 8개 operation과 본인 학생 범위 검사는 해당 구현이 제공된 뒤 연결한다.
2. #24는 동일 키 동시 제출·본문 불일치·UK 충돌 시 최초 응답 재구성·답변/판정 원자적 저장을 제공한다. core 실패 후 재전달 및 core TTL 이후에도 같은 답변을 중복 생성하지 않아야 한다.
3. 실제 learning URL/내부 토큰을 설정하고 6종 입력 방식, 초안 충돌·마무리 조건·돌아보기·자기 평가의 요청/응답과 프론트 DTO를 연결 검증한다. 여기의 대역 성공을 이 검증의 대체 근거로 사용하지 않는다.
4. 피드백 SSE(#39), core Redis 사용 한도 연계, 기기/PIN(#58)은 해당 담당 범위에서 연결한다. 이 작업은 그 기능을 구현하거나 완료로 표시하지 않는다. 한도 연계의 신규 `201`만 집계·이어하기 `200` 미집계 조건은 아래 #23 보완 절을 따른다.
5. PR 준비 중 #22/PR #62가 develop에 병합됐다. 이에 맞춰 미션 목록·상세는 core의 연결된 활성 학생에서 grade/demo를 결정하고 공개 query의 위조 값을 사용하지 않게 보완했다. #22의 완료 체크와 core→실제 learning 연결 검증 결과는 구분하며 최신 결과는 아래 최종 검증 절에 기록한다.

## 최초 구현 검증 (PR #62 반영 전)

코드·설정·테스트 작성 후 한 단계로 실행했다. 실제 learning·원격 CI·배포 검증은 별도다.

| 범위 | 실제 결과 |
|---|---|
| core 전체 | JDK 21.0.12.1, `test bootJar --no-daemon` 성공. XML 집계 **60개 통과·실패 0·오류 0·건너뜀 0**. 기존 44개 + 신규 16개 |
| 신규 HTTP client 검사 5개 | 테스트 전용 실제 HTTP 서버로 원문·URL 인코딩·If-Match·컨텍스트 전달, 504 timeout, 연결 장애 503, 자동 재시도 없음, 최근 20건 실패율 50% 차단, 4xx 비실패 집계, half-open 성공/실패 전이 확인. 30초 차단은 설정 대조 후 명시적 half-open 전이로 검증하며 운영 시간 측정이 아니다 |
| 신규 공개 API 통합 9개 | 실제 PublicAuthFilter·JWT/세션 인증·core PostgreSQL·learning HTTP 대역 연결. 10개 operation, 역할/학생 연결/위조 컨텍스트 헤더, 같은 키 최초 응답 재사용, 다른 본문/endpoint/학생 422, 처리 중 409·Retry-After, core 응답 저장 실패 후 같은 키 재전달, 5xx 후 재요청, 24시간 만료/삭제, 4xx 최초 오류 재사용, 초안 409·ETag·If-Match·Problem Details·확장 필드·499 포함 상태 보존 확인 |
| 신규 Repository 2개 | PostgresRepositoryTest 재사용. 실제 PostgreSQL 17.11과 V1~V8, 별도 연결/Repository 사이 세션 잠금, 미확정 행 재개, 소유 DB 연결 강제 종료 후 잠금 해제·재획득 확인 |
| 트랜잭션 경계 | 외부 HTTP 대역 처리 중 실제 `pg_stat_activity`에서 idle-in-transaction 연결 0개 확인. core 응답 저장 실패는 테스트 DB의 해당 키에만 CHECK를 걸어 실제 UPDATE 실패를 유발하고 finally에서 제약 제거 |
| 배포 JAR | 생성 성공. resilience4j-circuitbreaker/core 2.3.0 포함, Flyway·Testcontainers·learning HTTP 대역/통합 테스트 클래스 미포함 확인 |
| OpenAPI·기존 스크립트 | `python -O -m unittest discover -s scripts/tests -v` **27/27 통과**. 기존 인증 6개·DB 검증기 18개 + 새 learning 계약 3개. 별도 임시 venv의 openapi-spec-validator 0.7.2로 OpenAPI 3.1 표준 검사 통과 |
| 변경 검토 | 학습 DB 직접 참조·production 대역/재시도·계층 건너뛰기 없음. package/경로 일치, 기존 V1~V8 미변경, `git diff --check` 통과 |

테스트 DB는 PostgresRepositoryTest의 폐기 가능한 컨테이너다. 세션 잠금·동시 요청 검증을 위해 신규 테스트의 고유 fixture만 commit 가시성을 사용하며 @AfterEach에서 FK 순서대로 지운다. 기존 compose DB·서비스·다른 채팅 컨테이너는 변경하지 않는다. HTTP 대역의 중복 저장 효과 1회 확인은 **실제 learning DB의 UK/트랜잭션 검증이 아니다**.

Windows 네이티브 Gradle은 컴파일 전 `Unable to establish loopback connection`으로 실패해 전용 `eclipse-temurin:21-jdk` 컨테이너와 작업 전용 Gradle cache volume으로 전환했다. 첫 Docker 실행은 새 테스트의 wildcard `Test` import 충돌로 테스트 컴파일에 실패했고 명시적 JUnit import로 수정했다. 이후 전체 실행이 위 60개 통과 결과다. 두 번째 실행은 자원 경합을 줄이기 위해 test 환경에만 `JAVA_TOOL_OPTIONS=-XX:ActiveProcessorCount=2 -XX:TieredStopAtLevel=1`, Gradle `--max-workers=2 -Pkotlin.compiler.execution.strategy=in-process -Dorg.gradle.jvmargs=-Xmx768m`을 사용했다. production JVM 설정은 변경하지 않는다. 기존 messaging/security 코드의 annotation target 안내는 남아 있으며 테스트 실패가 아니다.

OpenAPI 표준 검사에서 발견한 inline YAML description의 쉼표 구문도 따옴표로 고친 뒤 통과를 확인했다. 병렬 #37·#43 태그를 고려한 인증 검사 보완 후 스크립트 27개를 다시 실행해 통과했다.

미실행: 실제 learning API/DB와 프론트 연결, 실제 Google 재로그인, 다른 서비스 전체 테스트·3개 DB migration CI·원격 CI·배포. learning 핸들러가 없고 다른 서비스/DDL/프론트를 변경하지 않은 범위이므로 이번 결과와 구분한다. 실제 learning 연결 조건은 앞 절을 따른다.

## 구현·검증 완료 시점 Git 상태

- branch: `feature/core-learning-proxy`, 통합 대상: `develop`.
- HEAD/base: `ecd6ecf7880e90341855d2fad6d9e773f3711c67`. 시작 시 fetch한 origin/develop과 일치하며 #36 PR #61 병합 포함.
- 이 작업 커밋 **0개**, 미stage 변경 보존. commit·push·PR 생성·squash·이력 재작성 없음.
- origin은 팀 원본 저장소이며 upstream은 등록되어 있지 않다. 원본 체크아웃의 feature/core-google-auth·깨끗한 작업 트리를 유지했다. 전용 worktree는 검토를 위해 남긴다.

## PR 준비 (2026-10-27)

- PR 준비 첫 fetch에서 origin/develop `1b600850b0aee73983d646819933585fd2b44934`를 확인했다. 이 시점에는 구현 기준 이후 PR #70의 문서 정합성 수정만 추가됐고 backend 실행 코드·설정·테스트·OpenAPI 변경은 없었다.
- #38 변경 21개 파일을 저장소 밖 ZIP·binary patch·SHA-256 manifest·고유 stash로 보존한 뒤, 이 작업 브랜치만 최신 develop으로 fast-forward하고 복원했다. 문서 3개는 충돌 없이 병합됐고 #70의 인증 설명·링크 수정과 #38 계약 추가를 모두 유지한다. 공용 브랜치·원본 체크아웃·다른 worktree는 전환하지 않았다.
- PR #70 반영 시 복원한 코드·설정·OpenAPI·테스트 17개 파일은 검증본과 내용이 같았다(체크아웃 줄바꿈 정규화 제외). 해당 단계는 backend base의 실행 파일도 변경되지 않아 기존 JDK 21 core 60/60·bootJar 결과를 유지했다. 이후 PR #62 반영의 실행 코드 보완은 아래처럼 다시 검증했다.
- 최신 문서 기준 계약/DB 검증기 회귀 **27/27**과 OpenAPI 3.1 표준 검사를 다시 실행해 통과했다. 보고서 링크·package 경로·미포함 파일 및 `git diff --check`도 확인한다. PR에는 #38 변경만 포함하고 실제 learning 미연동 및 #24 멱등 계약의 후속 검증 조건을 명시한다.
- 이번 PR 준비 요청은 검증한 작업 파일의 commit·push까지 포함한다. 이력을 squash/rebase하거나 공용 기준 브랜치를 변경하지 않으며 PR 생성·메타데이터 설정은 사용자가 직접 수행한다.

### PR #62 추가 병합 반영

stage 직전 재확인에서 origin/develop이 `7188b696e6e28d537d015a0e7c4eab3346a65976`로 진행돼 다시 백업·fast-forward·복원했다. API 명세 4.1의 한 충돌은 #62의 grade/demo 조회 계약과 #38의 시도 시작 경로를 함께 보존해 해결했다. #62의 learning 구현·시드는 base에 속하며 이 PR의 변경분으로 복사하거나 수정하지 않는다.

기존 StudentAccessService/LinkedStudent에는 is_demo가 없으므로, 기존 인터페이스를 고치는 대신 core guardianship에 현재 요청용 읽기 service·Repository·Mapper를 추가했다. core_db의 연결된 활성 학생 grade/is_demo만 조회하고, 문항 노출 조건은 learning에 맡긴다. 공개 미션 목록은 page/size만 받으며 클라이언트 grade/demo는 전달하지 않는다. 미션 상세에도 같은 검증된 프로필 조건을 붙인다.

이 보완은 실행 코드 변경이므로 이전 60개 결과만으로 완료 처리하지 않는다. 코드·설정·테스트 작성을 마친 뒤 core 전체 test/bootJar와 실제 미션 조회 연결을 최종 단계에서 다시 검증한다. 시도·답변 등 아직 없는 내부 API는 HTTP 대역 결과와 실제 미연동 범위를 계속 구분한다.

### 최종 검증 결과 (PR #62 반영)

- 기준: develop `7188b696e6e28d537d015a0e7c4eab3346a65976`. core 전체 `test bootJar` **62개 중 61개 통과·Repository fixture 검사 1개 실패·건너뜀 0개**였다. 실패는 테스트 트랜잭션 안의 JDBC fixture 갱신을 MyBatis 세션 캐시가 반영하지 못한 것이었다. 테스트에서 fixture 변경 뒤 SqlSessionTemplate.clearCache()를 호출하도록 고쳤으며 production 코드·설정은 바꾸지 않았다.
- 실패한 StudentLearningContextRepositoryTest **1/1 재검증 통과**. 이미 통과한 61개는 반복하지 않았다. 최종적으로 62개 검증 항목을 통과했으며 전체 실행 61개와 수정 후 재실행 1개의 결과를 구분한다. 새 HTTP 통합 검사에는 클라이언트 grade/demo/studentId query 무시와 요청 간 실제 학생 프로필 변경 반영이 포함된다.
- core **bootJar 성공**, 실제 조회 검증에 사용한 변경 없는 learning **bootJar 성공**. JDK 21.0.12.1 컨테이너와 앞서 기록한 worker/JVM 설정을 사용했다. Windows bind mount를 직접 반복 탐색하지 않도록 컨테이너의 임시 Linux 작업 복사본에서 빌드하고 결과를 전용 worktree에 복사했다.
- 실제 core JAR → learning JAR → 분리된 core_db/learning_db PostgreSQL 17.11로 **HTTP 검사 11/11 통과**. 두 DB에 기존 migration을 적용하고 learning의 기존 데모 시드와 합성 계정·학생·동의·로그인 세션만 사용했다. JWT는 검증용 HS256 키로 만들고 실제 PublicAuthFilter·세션/동의/연결 검사를 거쳤다. Google 외부 로그인이나 실제 사용자 계정을 사용한 검증은 아니다.
- 실제 HTTP 확인: 초3 목록 5개·상세 200과 정답/기준표 비노출, page/size 전달, 다른 학년 상세 409 및 Problem Details 보존, 클라이언트 grade/demo 위조 무시, 일반 학생의 시연 전용 목록/상세 접근 거부, core의 시연 학생 flag를 켰을 때 목록/상세 허용, 잘못된 토큰 401, 연결 해제 학생 403. 시연 전용 조건은 이 검증의 임시 learning DB에서만 변경했으며 seed 파일·기존 compose DB는 수정하지 않았다.
- grade/demo 계약 검사를 추가한 scripts/tests **28/28 통과**, OpenAPI 3.1 표준 검사 통과. 초기 27개 결과를 최신 28개 결과로 대체한다. 기존 V1~V8과 learning migration·seed·코드는 base 그대로다.
- 실제 미연동은 #23·#24·#26의 8개 API(시작·시도 조회·초안·생각 열기·답변·마무리·자기 평가·돌아보기)다. 이 경로들의 HTTP 대역 통과를 실제 learning 저장·판정 처리·멱등 UK 검증으로 해석하지 않는다. #24의 중복 키/본문 대조·최초 응답 복원 및 core 저장 실패 후 재전달 연결은 여전히 후속 조건이다.

## #23 시도 시작의 학생 조건 전달 보완 (2026-10-27)

- 작업 시작 시 `feature/core-learning-proxy`의 HEAD와 원격 브랜치는 모두 `a06b0170526908e367f5a2dfdc7cb4b0a3893481`이고 작업 트리는 깨끗했다. 기존 #38 구현은 이미 커밋·push된 상태다. 당시 fetch로 확인한 `origin/develop` `7188b696e6e28d537d015a0e7c4eab3346a65976`은 HEAD의 조상이므로 추가 병합 없이 기존 커밋을 보존했다. 이 구현 단계의 요청 범위는 커밋·push 전까지였다. 이후 PR 준비는 아래 별도 절을 따른다.
- 조회 두 개는 이미 `StudentLearningContextService.requireLinked`로 인증된 학생의 현재 학년·시연 여부를 조회해 전달하지만, 시도 시작 POST에는 해당 조건이 빠져 있었다. API 명세 4.1·아키텍처·공개 OpenAPI에 시작의 내부 쿼리 계약을 먼저 반영했다.
- 호출 흐름: 공개 Controller → `LearningProxyService` → `StudentLearningContextService` → core Repository/Mapper로 연결된 활성 학생의 `grade`·`is_demo` 조회 → `LearningClient`가 `/internal/missions/{id}/attempts?grade&demo` 호출. 공개 query와 위조 사용자 컨텍스트 헤더는 학생 조건의 근거로 사용하지 않는다. 목록의 `page`·`size`는 그대로 전달한다.
- 기존 조회 경로와 같은 service를 재사용하며 새 의존성·DB 스키마·실행 계층은 추가하지 않는다. 문항 공개·학년·시연 범위에 따른 신규 시도 제공 가능 여부와 기존 시도의 시작 당시 버전 유지는 learning #23이 처리한다. 현재 base에는 해당 시작 Controller가 없어 실제 시도 생성·이어하기 저장 검증은 별도 후속이다.
- 추가로 전달받은 #23 합의에 따라 일일 한도 판단은 core Redis 책임으로 명시했다. learning은 한도 계산에 관여하지 않고 신규 생성 시 `201`, 기존 진행 시도 반환 시 `200`을 반환하며 core는 두 상태를 그대로 전달한다. 공개 OpenAPI 응답 설명과 API 명세 2.2·4.1을 함께 정정하고, HTTP 대역으로 두 상태의 전달을 각각 검증한다.
- 후속 Redis 한도 연계 조건: 신규 생성 `201`만 카운트하고 이어하기 `200`은 카운트하지 않는다. 한도 도달 시에도 기존 시도는 이어갈 수 있고 신규 생성만 차단해야 한다. 따라서 시작 요청 전체를 선차단하지 않도록 기존 시도 판별·한도 검사·신규 생성 차단의 처리 순서를 후속에서 확인한다. 이번에는 Redis 카운터·한도 차단 기능을 구현하거나 검증 완료로 표시하지 않는다.

### 이번 보완 검증

코드·설정·테스트 작성을 마친 뒤 검증했다. 검증 중 추가로 전달받은 `201`·`200` 합의는 문서와 테스트에 반영하고, 변경한 프록시 테스트 전체와 계약 검사를 다시 실행했다. 이 추가 합의에 따른 production 코드 변경은 없다.

| 범위 | 실제 결과 |
|---|---|
| core 회귀 | 최초 `test bootJar`의 63개 중 44개 통과·19개 실패·생략 0개. 실패는 검증용 복사본에 서비스 외부 RabbitMQ 정의·이벤트 계약 파일이 빠져 발생했다. 저장소 상대 경로를 복원한 뒤 실패한 인증·메시징·RabbitMQ 정의 19개만 재실행해 19/19 통과. 재실행 준비 중 Gradle `--tests` 옵션 위치 오류로 테스트 시작 전에 실패한 실행도 있었으며 검증 스크립트만 수정했다 |
| 최종 프록시 통합 | 추가 합의를 반영한 `LearningProxyIntegrationTest` 13/13 통과. 실제 JWT·인증 필터·core PostgreSQL·HTTP client와 learning HTTP 대역을 사용. 세 경로의 현재 `grade`·`is_demo` 전달, 중복된 위조 query·위조 컨텍스트 무시, 연결 해제/잘못된 토큰 차단, 신규 `201`과 이어하기 `200` 및 응답 원문 보존을 각각 확인 |
| 고유 core 테스트 집계 | 최초 실행·환경 보정 재실행·추가 합의 후 프록시 재실행 결과를 테스트 이름별로 대조해 **65개 고유 항목 모두 통과**. 한 번의 전체 실행에서 65개가 통과한 결과로 표현하지 않음 |
| 빌드 | JDK 21 Docker에서 core·learning `bootJar` 성공. 기존 worker/JVM 제한을 검증 환경에만 사용. 검증용 소스 해시로 기존 통과 항목의 production 코드가 추가 합의 전후에 같음을 확인 |
| 계약 | 최종 문서 기준 `python -O -m unittest discover -s scripts/tests -v` 28/28 통과, `python -m openapi_spec_validator contracts/openapi/core-service.yaml` 통과. `200`·`201` 응답 설명과 core Redis 후속 책임을 명시한 OpenAPI 3.1 검사 포함 |
| 실제 조회 연동 | 전용 core·learning 앱과 PostgreSQL DB에 합성 데이터·기존 시드를 넣어 HTTP 검사 11개 통과. 목록/상세·페이지·학년 범위 409·일반 학생 시연 전용 접근 거부·실제 시연 학생 접근 허용·위조 query 무시·잘못된 토큰 401·연결 해제 403 확인. 기존 실행 서비스·compose DB는 변경하지 않았고 이번 검증 컨테이너·네트워크만 정리 |
| 최종 변경 검토 | Controller → Application service → 다른 기능 service → Repository/Mapper 의존 방향 유지, production 의존성·DB 스키마·패키지·파일 이동 없음. 변경한 문서 참조·소유권 설명과 `git diff --check` 확인 |

실제 learning 시도 시작 Controller가 현재 base에 없으므로 신규 생성·이어하기의 저장 동작과 `201`·`200` 생성 주체의 실연동은 미검증이다. 이번 상태 코드 확인은 HTTP 대역을 사용한 core 전달 검증이다. Redis 일일 집계·한도 차단·한도 도달 시 이어하기 허용은 후속 구현·검증 조건이며 이번 테스트 통과로 완료 처리하지 않는다. learning 전체 테스트·브라우저·원격 CI·배포 검증은 이번 범위에서 실행하지 않았다.

구현·검증 완료 시점에는 `feature/core-learning-proxy`, 통합 대상 `develop`, 기존 커밋 1개(`a06b017`, `feat: 학생 미션 learning 프록시와 공통 멱등성 구현`)를 유지했다. 당시 보완 6개 파일은 미stage·미커밋이었고 새 commit·push·PR 생성·이력 재작성은 수행하지 않았다.
- 검증용 core·learning·PostgreSQL 컨테이너 및 전용 네트워크를 정리했다. 기존 compose·실행 DB·다른 채팅 자원은 변경하지 않았다. 원격 CI·운영 배포·프론트 화면 E2E·실제 Google 재로그인은 미실행이다.

## 보완 커밋·push 및 PR 준비 (2026-10-27)

- 사용자가 보완 6개 파일의 commit·push와 PR 제목·본문 준비를 요청했다. PR 생성·메타데이터 설정은 사용자가 직접 수행한다.
- 재확인한 최신 `origin/develop`은 `b2441711e12ff949cb2859df058a119f0181032c`(#43 PR #73 병합)이다. 기존 원격 작업 브랜치는 `a06b017` 그대로였다. 기존 커밋을 재작성하지 않고 develop을 merge로 반영한다.
- 보완 6개 파일을 저장소 밖 ZIP·binary patch·SHA-256 목록과 고유 stash로 이중 보존했다. OpenAPI의 서비스 설명·응답 컴포넌트 충돌은 #38과 #43 계약을 함께 보존했고, 인증 계약 검사는 기존 Auth/Account 태그 한정을 유지해 두 기능의 추가 operation과 구분했다. #43 실행 코드·기능 계약은 변경하지 않는다.
- merge index와 보완 6개 파일의 working tree 변경을 분리해, 최신 develop 반영 커밋과 보완 커밋을 따로 유지한다. 통합된 최종 소스의 검증을 마친 뒤에만 커밋·push한다. 단일 커밋 정리를 위한 squash·rebase·force push는 수행하지 않는다.

### 최신 develop 통합 후 검증

- JDK 21 격리 Docker에서 최종 소스의 `test bootJar --no-daemon` 전체 실행 **88/88 통과**, 실패·오류·건너뜀 0개. #43 관리자·사용량 기능과 #38 인증·프록시·멱등성 회귀를 함께 포함한다. 앞 절의 65개 누적 결과와 달리 이번에는 한 번의 전체 실행 결과다.
- 최종 병합 문서의 계약 검사 **33/33 통과**, OpenAPI 3.1 표준 검사 통과. 두 기능의 operation·응답 컴포넌트와 기존 인증 계약을 함께 확인했다.
- 통합된 core JAR와 변경 없는 learning JAR를 전용 DB에 연결해 실제 미션 목록·상세 HTTP 검사 **11/11 재통과**. 학년·시연 전용 범위, 위조 query 무시, page/size, 409·401·403 전달을 포함한다. 검증용 앱·DB·네트워크만 정리했다.
- 시도 시작의 `201`·`200` 전달은 이번 전체 실행의 HTTP 대역 테스트로 확인했다. PR #74는 미병합이므로 실제 시도 생성·이어하기 연결과 Redis 일일 한도는 계속 후속 범위다. 원격 core CI는 feature 브랜치 push가 아닌 PR 생성 시 실행되는 워크플로이므로, 로컬 검증과 원격 CI 결과를 구분한다.
- 커밋 직전 원격을 다시 읽어 develop `b244171`과 원격 작업 브랜치 `a06b017`이 검증 기준 그대로임을 확인했다. 보완 커밋 대상은 기존 6개 파일만이며, develop 병합 변경은 별도 merge 커밋에 유지한다. PR의 base는 `develop`, head는 `feature/core-learning-proxy`다.
