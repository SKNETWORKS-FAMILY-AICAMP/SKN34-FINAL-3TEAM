# #39 core 피드백 SSE

## 기준·선행 계약

- 전용 worktree `issue-39-worktree`, 브랜치 `feature/core-feedback-sse`, develop 기준 `3e3273152e6a27e60e4febf96aa8749dd21b0d73`.
- 사용자 후속 지시로 선행 미병합 중 독립 구현을 허용했다. #38 PR #75의 현재 head `4641953f269a09ad2f45b2c76c474c2d81d0f77c`를 읽고 기존 LearningClient·LearningProxyService를 재사용한다. 선행 코드를 이 브랜치에 복사·재구현하지 않는다. 선행 클래스가 없는 develop 단독 빌드는 병합 전까지 불가능하며 별도 검증 소스에만 해당 선행 변경을 통합해 검사한다.
- #37 현재 작업 파일의 StudentAccessService는 `requireLinked(userId, studentId)` 계약을 유지하며 내부에서 현재 필수·법정대리인 동의 검사까지 강화한다. 생성자에 ConsentAccessService가 추가되지만 #39가 이 객체를 직접 생성하지 않아 호출 계약은 호환된다. #36 PublicAuthFilter·AuthService가 실제 세션·동의·학생 연결을 확인한다. #39는 account/·guardianship/·report/를 수정하지 않는다.
- #25의 실제 피드백 내부 API는 기준 develop에 없다. HTTP 대역의 전달·연결 검사는 learning 실제 상태 전이·DB 저장·AI 판정 검증을 뜻하지 않는다.

## 구현·공통 변경

- 설계 → 공개 OpenAPI → 구현 순서로 SSE 이벤트 종료·내부 DONE/RUNNING·오류 계약을 구체화한다.
- 피드백용 조합에서 #38의 Application/Client를 그대로 사용하고 read timeout만 80초로 구성한다. 일반 JSON 경로·멱등성·인증 필터·공유 설정·production 의존성·DB는 변경하지 않는다.
- `_common/web/SseEmitters`는 이번 피드백의 virtual task·15초 heartbeat·90초 연결·정리만 구현한다. 전송 실패/종료 콜백은 heartbeat만 취소하고 이미 시작한 learning 작업은 유지한다. 사용자 컨텍스트를 명시적으로 전달하고 작업 종료 시 제거한다.
- DONE 응답은 HELD를 포함해 result로, RUNNING 응답은 status로 전달한다. learning 오류는 error로 보존하며 done 후 종료한다. core에서 판정 전이·리스·실패 재실행 캐시를 구현하지 않는다.

## 검증

코드·설정·테스트 작성을 마친 뒤 일괄 검증했다. 최종 fetch의 develop은 기준 SHA 그대로이며 PR #75는 여전히 미병합이다. 아래 전체 core 결과는 **develop + 현재 #38 + #39의 임시 소스 통합 결과**로, 실제 develop 병합 후 결과가 아니다.

| 검증 | 실제 결과 |
|---|---|
| JDK 21 core 전체 | eclipse-temurin:21-jdk 전용 컨테이너에서 `./gradlew test bootJar --no-daemon --max-workers=2 -Pkotlin.compiler.execution.strategy=in-process -Dorg.gradle.jvmargs=-Xmx768m`: **96/96 통과**, 실패·오류·생략 0, bootJar 성공 |
| 신규 8개 | 실제 Tomcat·PublicAuthFilter·JWT/세션·동의·학생 연결·폐기 가능한 PostgreSQL·learning HTTP 대역의 통합 6개와 SSE 생명주기 단위 2개 통과 |
| HTTP·이벤트 | STUDENT 헤더·scope·내부 토큰·traceparent 전달, 공개 위조 헤더 무시, 부모/관리자/잘못된 토큰/연결 해제 거부. DONE·HELD result, FAILED 오류 뒤 같은 answer 재요청, RUNNING status, DONE 재요청 모두 매번 내부 HTTP 호출. 알 수 없는 성공 상태·잘못된 JSON은 명시적 502 오류, 403 및 오류 확장 필드 보존 |
| 실제 시간·연결 | 15초 heartbeat 포함 테스트 15.808초, 80초 timeout 테스트 80.423초(각 테스트 전체 소요 시간). timeout은 error(504 LEARNING_TIMEOUT, retryable) → done, 재시도 없음. 클라이언트 body/연결 종료 후에도 대역 작업 완료 및 다음 요청 성공 확인 |
| 자원·컨텍스트 | virtual thread 사용·검증된 컨텍스트 전달, 연결 종료 후 heartbeat 해제·작업 계속, 작업 스레드 종료, 예외 시 연결·예약 작업 정리, executor/timer 종료 확인. 실제 필터 요청 후 호출 스레드 컨텍스트 없음 확인 |
| 계약 | 임시 통합 소스에서 `python -O -m unittest discover -s scripts/tests -v`: **35/35 통과**. `python -m openapi_spec_validator contracts/openapi/core-service.yaml`: OpenAPI 3.1 표준 검사 통과 |
| 코드·경계 검토 | controller → FeedbackService → 기존 LearningProxyService → LearningClient → InternalRestClientFactory 흐름. 외부 호출 중 새 DB 트랜잭션·피드백 캐시·판정 전이 없음. 기존 프론트 apiGateway의 이벤트 소비 계약을 읽어 대조했으며 프론트 실행/브라우저 검증은 미실행 |

검증용 소스는 별도 `issue39-verification/source`에만 준비했다. Git merge-tree로 계산한 통합 tree `bc452068c6507ce3287e1a289e282a89aa0a7626`는 commit이 아니며 어떤 브랜치에도 연결하지 않았다. 이 통합 tree의 api-spec 4.1 충돌은 #38의 인증된 grade/demo·201/200·일일 한도 설명과 최신 develop의 생각 열기 응답 설명을 함께 보존해 임시 소스에서만 정리했다. #39의 작업 브랜치는 develop 기준으로 유지했다.

#38의 `LearningProxyIntegrationTest`에는 과거 범위의 피드백 404 단정이 있다. 임시 검증에서는 해당 한 줄만 제거하고 동일 테스트의 나머지 검사를 모두 실행했다. 새 FeedbackIntegrationTest가 실제 SSE 경로를 검증한다. **#38 병합 후 이 브랜치에서 해당 404 단정과 테스트 이름의 `feedback remains outside scope`를 제거해야 한다.** 선행 테스트 파일 전체를 이 브랜치로 복제하지 않았다.

첫 계약 검사에서는 검증 복사본에 tracked 문서 패치가 적용되지 않아 신규 1개가 실패했다(34개 통과). 복사본 적용 경로를 고친 뒤 35개 모두 통과했다. 기본 Python에는 openapi-spec-validator가 없어 기존 검증 전용 Python 환경을 사용했으며 production 의존성은 변경하지 않았다. core 첫 전체 실행은 96개 모두 통과했다. 기존 공통 코드의 Kotlin annotation target 안내만 남아 있다.

검증 컨테이너는 `--rm`, 테스트 DB/RabbitMQ는 Testcontainers/Ryuk로 정리됐다. #39 전용 Gradle 캐시와 검증 결과는 재현을 위해 남겼다. #38 캐시는 읽기 전용으로 복사해 사용했으며 공유 compose·실행 DB·다른 채팅 서비스는 변경하지 않았다.

최종 worktree의 계약 검사도 **31/31 통과**, OpenAPI 표준 검사 통과다(#38의 계약 4개는 아직 이 worktree에 없어 위 통합 35개와 수가 다름). 최종 `git diff --check` 및 신규 파일의 no-index whitespace 검사, 검증 소스와 작업 파일의 Kotlin 6개 SHA-256 일치를 확인했다. 검사 도구의 no-index 정상 차이 exit code를 처음에 오류로 취급한 wrapper는 수정했으며 실제 whitespace 오류는 없었다. 마지막 변경은 보고서와 OpenAPI 소개·태그뿐으로 실행 코드에 추가 변경은 없다.

종료 상태: 현재 `feature/core-feedback-sse`, target `develop`, 새 커밋 0개(HEAD는 위 develop 기준 SHA), 11개 파일 미stage·미커밋. push·PR 생성·이력 재작성 없음. 원본 체크아웃은 `feature/core-google-auth`와 깨끗한 작업 트리를 유지했다.

## 변경 파일

- `backend/core-service/src/main/kotlin/com/sagomungchi/core/learning/config/FeedbackConfiguration.kt`: #38 서비스/클라이언트 80초 조합.
- `backend/core-service/src/main/kotlin/com/sagomungchi/core/learning/service/FeedbackService.kt`: 피드백 Application 진입점.
- `backend/core-service/src/main/kotlin/com/sagomungchi/core/learning/controller/FeedbackController.kt`: 공개 SSE·이벤트 변환.
- `backend/core-service/src/main/kotlin/com/sagomungchi/core/_common/web/SseEmitters.kt`: 이번 요청에 필요한 heartbeat·연결·virtual task 생명주기.
- `backend/core-service/src/test/kotlin/com/sagomungchi/core/learning/FeedbackIntegrationTest.kt`, `_common/web/SseEmittersTest.kt`: HTTP 통합·생명주기 검사.
- `contracts/openapi/core-service.yaml`, `scripts/tests/test_feedback_openapi.py`: 공개 SSE 계약과 계약 검사.
- `docs/design/api-spec.md`, `docs/design/architecture.md`, 이 보고서: 설계·영향·결과.

공통 변경은 새 SseEmitters와 OpenAPI·설계의 피드백 구간뿐이다. Gradle·application.yml·인증 필터·DB migration·account/·guardianship/·report/·프론트는 변경하지 않는다.

## 2026-10-28 선행 병합 반영과 잔여 완료 조건 검증

- 원격 확인: #37 PR #77은 `9a372c588a4c6bdff18de7f1723da02c0e85167f`로, #38 PR #75는 `d3d28140d5b5a2e74cfd6c32f2ef2a983a25a016`으로 develop에 병합됐다. #38 이슈가 open인 것과 PR 병합 여부를 구분했다. #25 PR #78은 open·미병합이며 실제 구현 head는 `517cc231ea545f3bde7346f91d03dcbb4a6c5756`이다.
- 기존 11개 작업 파일을 저장소 밖 ZIP·binary patch·SHA-256 목록으로 보존한 뒤 고유 stash(`bcc9ed2a968530fa0ef45c070db4fae62676e4b4`)로 보존했다. 현재 작업 브랜치를 최신 develop `9a372c5`로 fast-forward하고 stash를 복원했다. feature 브랜치의 자체 커밋이 없어 merge commit 없이 기존 develop 이력만 반영했고 rebase/reset/이력 재작성은 하지 않았다.
- OpenAPI 충돌은 최신 develop의 모든 operation·동의·자녀·learning 계약을 보존하면서 #39 경로·태그·소개만 합쳤다. API·아키텍처의 #39 추가 설명은 자동 병합됐고 기존 Kotlin 6개 파일은 개행을 제외한 내용 보존을 대조했다. stash와 ZIP은 보존한다.
- 실제 작업 브랜치에서 #38 테스트의 과거 피드백 404 단정과 이름을 제거했다. 나머지 #38 회귀는 그대로 수행한다. #37·#38의 실제 호출 계약과 #25 PR #78의 DONE/RUNNING/Problem Details·retryable 계약은 #39와 호환되어 production 코드 수정은 없다.
- `scripts/verify_feedback_learning.py`는 실제 core/learning JAR·독립 PostgreSQL 2개 DB·AI HTTP 대역을 사용한다. #37의 동의 저장·자녀 등록·학생 세션과 실제 답변 제출을 거쳐 피드백을 호출하고 learning DB의 FAILED 커밋·같은 판정 재획득·DONE 저장 및 AI 호출 수를 확인한다. 전체 learning을 흉내 낸 대역 검사와 구분한다. 미병합 #25 소스는 별도 검증 디렉터리에만 추출하며 이 브랜치에 복사/병합하지 않는다.
- 검증용 DB는 전용 `issue39-feedback-db-*` 컨테이너의 `issue39_core_feedback`/`issue39_learning_feedback`만 사용한다. SQL migration을 번호순·파일별 트랜잭션으로 적용하며 애플리케이션 자동 마이그레이션은 계속 끈다. 최초 Windows 실행은 JDK loopback 오류로 실패해 최종 실행은 전용 Linux JDK 21/Python runner로 옮겼다. 스크립트가 두 JVM·AI 대역을 종료하고, 실행 측이 해당 sidecar DB·전용 네트워크를 제거했다. 공유 compose·실행 DB·다른 채팅 자원은 변경하지 않는다.

### 실제 learning 실행 결과

현재 #39 core JAR → PR #78 head `517cc231ea545f3bde7346f91d03dcbb4a6c5756`의 실제 learning JAR → 별도 learning DB를 실행했다. learning을 대역으로 바꾸지 않았다. **AI만 합성 HTTP 대역**이고 실제 AI 서비스·외부 LLM·판정 품질은 검증하지 않았다. #25는 여전히 미병합 소스라는 한계를 유지한다.

| 실제 연결 검사 | 확인 결과 |
|---|---|
| #37 인증 흐름 | 합성 부모/refresh 세션을 검증 DB에 만든 뒤 실제 refresh → 현재 문서 조회 → 동의 저장 → 자녀 등록 → 학생 세션 발급. 실제 공개 필터·JWT·세션·동의를 통과한 상태로 피드백 호출 |
| FAILED → 재실행 → DONE | 첫 AI 503 뒤 core `status → error(AI_UNAVAILABLE, retryable=true) → done`. 별도 DB 연결에서 judgment `FAILED`, retry_count=1, 요소/되묻기 0행과 원본 답변 보존 확인. 같은 answerId 재요청으로 **동일 judgment ID**가 DONE으로 바뀌고 요소 1행·되묻기 1행 저장 |
| DONE 재요청 | 저장 결과와 동일한 result 반환. 전체 AI 판정 호출 2회(실패 1 + 재실행 1), 되묻기 1회 유지. DONE 재요청에는 AI 추가 호출 0회 |
| 유효 RUNNING | 첫 요청의 실제 learning DB가 RUNNING인 동안 두 번째 요청은 status·done만 반환. AI 판정은 1회만 실행되고 첫 요청 완료 후 DONE 저장 |
| 클라이언트 종료 | core SSE 응답을 닫은 뒤 AI 대기를 해제해 실제 learning DB의 DONE·요소/되묻기 저장을 확인. 재요청은 저장 결과 반환, AI 추가 호출 없음 |
| HELD·재시도 불가 | HELD는 learning `DONE`과 result로 저장/전달. 별도 AI 503 `retryable=false`는 FAILED로 저장되고 core가 false를 보존 |

총 **6개 시나리오 PASS**다. FAILED 재요청의 core→learning 재전달만 확인했던 이전 HTTP 대역 검증보다 범위가 넓다. 실제 learning의 상태 획득·실패 커밋·결과 저장·재응답까지 확인했으며, 실제 AI·LLM 호출의 재실행 검증은 아니다.

- JDK `21.0.12.1`, Python 3.12, 검증 runner의 psycopg/psycopg-binary `3.3.6`. 이 패키지는 폐기되는 검증 컨테이너에만 설치했으며 production 의존성/lock 파일은 수정하지 않았다.
- core 실행 JAR SHA-256: `8583bb0e554446586f122c81eb6f5820f37b96e9bec71684f6e751aa81ad9e6d`.
- 최종 전체 재검증 bootJar SHA-256은 `351e85528f6bf9cd37c068b141d86a17da964978f08445d9da68b5e54fabf26c`다. 실행에 사용한 JAR와 ZIP 항목 이름·각 항목 내용을 모두 대조해 차이 0개를 확인했다(압축 파일 자체 메타데이터 차이).
- learning 실행 JAR SHA-256: `a39c2b7e828a2ca5ec06b6e1a39c9add70e3aff5e573e3bd13f5afb0147134bb`.
- 재현: `scripts/verify_feedback_learning.py --core-jar <현재 #39 bootJar> --learning-jar <517cc23 bootJar> --learning-source <517cc23 소스> --core-ref 9a372c588a4c6bdff18de7f1723da02c0e85167f --learning-ref 517cc231ea545f3bde7346f91d03dcbb4a6c5756 --output <검증 결과.json>`. Linux sidecar 모드는 `--java <JDK21 java> --db-host issue39-feedback-db-<전용이름>`을 추가하고 별도 PostgreSQL(POSTGRES_USER=issue39, POSTGRES_DB=issue39_core_feedback, 검증용 암호)을 준비·정리한다. 기본 자체 DB 모드와 sidecar 모드는 공유 DB를 사용하지 않는다.
- 검증 환경 준비에서 migration별 트랜잭션 누락·PostgreSQL 초기 임시 서버 준비 판정, Windows JDK loopback, RabbitMQ health contributor 없는 readiness 그룹 오류를 만났다. SQL 파일별 트랜잭션·최종 TCP 준비 대기·Linux runner·검증 프로세스 전용 readiness(include=readinessState,db)로 보정했다. 저장소 migration·production 설정은 변경하지 않았다. 준비 실패를 실제 learning 업무 테스트 실패로 합산하지 않는다.

### 최신 브랜치 core 검증

최초 JDK 21 `test bootJar` 전체 실행은 **117개 중 116개 통과·기존 LearningRecordServiceTest 1개 실패·생략 0개**, bootJar 생성 성공이었다. 실패는 서킷 차단 검사에서 HTTP 대역 수신 수 20개를 예상했으나 19개였고, 해당 테스트의 production 변경은 없다. 다른 #39 빌드를 끝낸 뒤 **동일 소스로 전체 `test bootJar`를 재실행해 117/117 통과·실패/오류/생략 0개, bootJar 성공**을 확인했다(4분 15초). 최초 실패는 이 전체 실행에서 재현되지 않았지만 원인을 확정하지는 않았다. 기존 기록 서비스 테스트의 단정이나 production timeout을 완화하지 않았다. 이전 절의 96개 임시 통합 결과와 달리 이번 최종 결과는 #37·#38을 반영한 실제 작업 브랜치 전체 실행이다.

현재 브랜치의 계약 검사 **42/42 통과**, OpenAPI 3.1 표준 검사 통과다. #37·#38 operation·SSE 계약을 함께 확인했다. 추가된 검증 스크립트는 Python 문법 검사와 위 실제 실행으로 확인했다.

### 완료 조건과 최종 상태

- [x] `FAILED` 후 동일 요청 재호출 시 재실행: 실제 learning PR #78 코드·DB에서 FAILED → 동일 judgment 재실행 → DONE → 저장 결과 재응답을 확인했다. AI는 대역이며 #25 미병합 상태는 별도로 남는다.
- [x] `./gradlew test` 통과: 최신 반영 브랜치의 JDK 21 전체 실행 **117/117** 및 bootJar 성공. 최초 실패 1개와 최종 전체 성공을 구분한다.
- 최종 보존 검사: upstream OpenAPI의 경로 25개와 components 전체가 동일하고 #39 경로만 추가됐다. production Kotlin 74개 파일이 검증 snapshot과 byte 단위로 같음을 대조했다. 기존 #39 production 4개/테스트 2개 파일도 선행 반영 전과 개행 외 변경이 없다.
- 현재 브랜치 `feature/core-feedback-sse`, 기준/target `develop` `9a372c588a4c6bdff18de7f1723da02c0e85167f`. 새 작업 커밋 0개, 변경 13개 파일 모두 미stage·미커밋. commit·push·PR 생성·이력 재작성 없음. 보호용 stash와 저장소 밖 ZIP/patch/해시·검증 결과를 보존했다.
- 이번 추가 변경은 #38의 과거 404 테스트 단정 제거, 실제 연결 검증 스크립트, 통합된 OpenAPI·설계·보고서다. application.yml·build.gradle.kts·migration·인증/동의/학생 연결 production 구현은 이번 작업에서 수정하지 않았다. 검증 전용 컨테이너·네트워크는 정리했고 JDK/Gradle 캐시·검증 산출물만 남겼다.
- 종료 직전 fetch에서도 HEAD와 origin/develop이 모두 `9a372c5`임을 확인했다. 충돌·stage된 파일 없음, `git diff --check` 및 신규 9개 파일의 CRLF를 고려한 whitespace 검사 통과. 검사 wrapper의 Windows cp949/CRLF 해석은 UTF-8·cr-at-eol 설정으로 보정했으며 파일 내용/개행을 다시 쓰지 않았다.
- #25 PR #78이 develop에 병합되면 **병합된 learning 소스와 검증한 고정 SHA의 계약·구현 차이를 다시 대조**한다. 변경이 있으면 core/learning 실제 연결과 영향 검증을 재실행한다. 현재 develop learning에는 피드백 Controller가 없어, 이번 결과를 develop에 병합된 learning 연결 완료로 표현하지 않는다. 실제 AI·LLM·원격 CI·배포·브라우저 E2E 및 learning 전체 테스트는 이번 작업에서 실행하지 않았다.

## 2026-10-28 commit·push 및 PR 준비

사용자가 #39 변경만 commit·push하고 develop 대상 PR 제목·본문·라벨 초안을 준비하도록 별도 요청했다. PR 생성·입력·메타데이터 설정은 수행하지 않는다. 기존 검증 종료 시점의 무커밋 상태와 이번 승인 범위를 구분한다.

- 대상 저장소는 `SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM`, origin도 동일 주소다. upstream은 없다. base와 저장소 기본 브랜치는 모두 `develop`, head는 `feature/core-feedback-sse`다. 최신 fetch에서 develop은 계속 `9a372c5`이고 원격 head 브랜치는 아직 없다.
- #39의 코드·테스트·계약·보고서·실제 연결 검증 스크립트 13개만 명시적으로 stage한다. 이미 통과한 JDK 21 전체 117개·bootJar·실제 learning/AI 대역 6개 결과의 production 소스가 그대로임을 대조하고, 실행 코드 변경이 없는 이번 단계에서는 해당 무거운 검증을 반복하지 않는다. 문서·계약·diff·포함 파일/secret 검토는 마친 뒤 커밋한다.
- #25 PR #78은 여전히 open·미병합, head `517cc231ea545f3bde7346f91d03dcbb4a6c5756`이다. 실제 learning 검증에 사용한 코드와 같다. 공통 조상은 `826e4dc71e60ba4d2396d3545f87a41524d6db83`이고, 양쪽 작업 파일의 교집합은 `docs/design/api-spec.md` 1개다. 저장소 밖 임시 파일을 Git 저장 형태인 LF로 맞춘 3-way 병합은 exit 0으로 충돌 없이 완료됐다. 실제 작업 파일·#25 브랜치는 변경하지 않았다.
- core의 피드백 Controller·서비스·SSE 공통 코드와 #25의 learning Controller·오케스트레이션·판정 Repository는 경로가 달라 직접 겹치지 않는다. #39가 추가하는 api-spec 3.2 중계 설명과 #25의 오류 코드·상태 처리·4.1 내부 응답 보완은 함께 보존된다. DONE/result·RUNNING/status·503/error와 retryable 보존은 실제 PR #78 JAR/DB·AI 대역으로 이미 확인했다.
- 현재 SHA 기준 텍스트·계약 충돌이 없다는 판단이며 앞으로 #25가 변경돼도 충돌하지 않는다는 보장은 아니다. 커밋 후 Git merge-tree로 양방향 통합 트리를 다시 계산해 확인하며, #25 코드를 이 브랜치에 병합하지 않는다.
- 원격 등록 라벨 설명을 재조회했다. 추천은 `enhancement`(New feature or request), `area:core`(core 영역), `P0`(12/7 필수, api-spec 핵심)다. 미등록 라벨을 만들거나 PR에 적용하지 않는다.
- PR 본문은 `Closes #39`를 포함한다. develop이 기본 브랜치이므로 해당 PR을 develop에 병합할 때 GitHub 자동 종료 대상이 된다. #25는 이 PR의 종료 대상이 아니며 미병합 의존성과 검증 범위를 본문에 명시한다.

최종 commit SHA·원격 반영 결과·Git merge-tree 결과는 대화의 완료 보고에 실제 값으로 제공한다. 원격 CI·PR 생성·병합·배포를 실행 완료로 표시하지 않는다.

## 이전 검증 시점의 후속 (현재 상태는 위 2026-10-28 절 우선)

- #37·#38 develop 병합 후 최신 develop을 merge하고 계약 차이를 확인한다. 수정이 없어도 인증·프록시·SSE 통합 영향과 전체 core test·bootJar·계약 검사를 수행한다.
- 현재 worktree에는 #38 클래스가 없어 단독 `test`·`bootJar`를 검증했다고 주장하지 않는다. `LearningClient`, `LearningHttpProperties`, `LearningProxyService`, `StudentLearningContextService`, `IdempotencyService`와 테스트의 `LearningHttpStub`가 #38에서 제공돼야 한다. #37의 현재 미커밋 구현도 임시 전체 검증에는 포함하지 않았으므로 강화된 최신 동의 정책과 실제 자녀 등록부터 이어지는 통합은 병합 뒤 확인한다.
- #25 실제 연결 뒤 DONE 재응답·RUNNING 미실행·FAILED 재실행·HELD 저장·연결 종료 뒤 저장을 실제 learning DB/AI 경로로 확인한다.
- 대역의 상태 응답 순서를 확인한 결과를 learning의 조건부 전이·리스·중복 실행 방지·DB 저장 검증으로 해석하지 않는다. 실제 #25 API·AI/DB 연결, 브라우저 E2E·원격 CI·배포는 미검증이다.
- commit·push·PR 생성·이력 재작성은 이번 요청 범위 밖이다.
