# #45 계정 관리·재인증·삭제·탈퇴

> 2026-10-28 PR 준비: 사용자 지정 중간 통합 대상은 `feature/core-integration`이다. #37이 포함된 `40a2501`을 반영했다. 아래 미병합/미커밋 기록은 당시 이력이며 최신 결과는 마지막 절을 따른다.

기준 origin/develop 3e3273152e6a27e60e4febf96aa8749dd21b0d73, feature/core-account-management 전용 worktree. #37/#38 미병합 차단 조건은 사용자가 해제했다. 두 worktree 구현/보고서는 읽기만 했으며 복사·cherry-pick하지 않는다. #37의 StudentAccessService/ConsentAccessService 확장과 account 행 잠금 규약, #38의 기존 인증·학생 scope 소비 계약을 확인했다. 설계 → OpenAPI → 구현 순서로 반영한다.

사용자가 5분·세션/작업/자녀 결합·1회 사용을 확정했다. Google 계정 확인은 비밀번호/MFA 재입력 보장이 아니다. 새 production 의존성은 없다. 기존 GoogleOAuthClient·TokenService·OutboxWriter·InternalAuthFilter·테스트 기반을 재사용한다. 상태 조회 영수증은 탈퇴 후 로그인 차단과 상태 조회를 동시에 제공하기 위한 최소 공개 계약이다.

검증은 코드·설정·테스트를 마친 뒤 일괄 진행한다. 구현/검증 결과 및 선행 병합 후 통합 검증은 작업 종료 전에 갱신한다.


## 구현 경계

- account/guardianship 신규 서비스가 기존 인증·동의 서비스를 재사용한다. #37 서비스·#38 learning/멱등성 구현은 복사하지 않았다.
- 최소한의 payment/service·repository는 기존 core subscription/refund_request에 대한 탈퇴 자격 조회만 담당한다. PG/결제/구독 쓰기 구현은 없다. conversation/service·repository는 P09의 기존 core 대화·근거 삭제만 담당한다. 다른 기능 repository를 우회 참조하지 않는다. #39 learning/SSE·#42 report/스케줄은 변경하지 않는다.
- 재인증과 서비스별 완료 행은 신규 V9다. 기존 migration·공유 compose·실행 DB는 수정하지 않는다. 새 기기 테이블/가짜 device cleanup은 없다.
- RECORDS 삭제 이후 학습 재개는 downstream 삭제 표식 수명주기가 확정되지 않아 자동 허용하지 않는다. 상태는 완료여도 student는 DELETION_REQUESTED로 차단 유지한다. PROFILE 요청/탈퇴는 계속 가능하다.
- #58 통합 전 기기 매핑 제거·기기 revoked_at 처리는 남는다. 현재 학생 세션은 revoke하고 매 요청의 계정/연결/학생 상태 검사로 차단한다.
- core/학습·리포트의 실제 DB를 연결한 전체 삭제 검증은 소비자 구현 후 필요하다. 현재 작성한 완료 보고는 테스트 전용 소비자 대역이다.


## #58 재사용 호출

1. 로그인한 원래 세션에서 `POST /api/v1/me/reauth`에 `{"purpose":"PIN_CHANGE","childId":"<실제 자녀 UUID>"}`를 전송한다. `Origin`과 `X-Requested-With: XMLHttpRequest`가 필요하다.
2. 응답 authorizationUrl을 새 창에서 열고 Google 계정을 확인한다. Google 콘솔에 `<webOrigin>/api/v1/auth/google/reauth/callback`을 별도 redirect URI로 등록해야 한다. callback은 JSON VERIFIED 안내만 제공하며 기존 로그인/refresh를 바꾸지 않는다.
3. 원래 세션에서 같은 endpoint에 `{"challengeId":"<응답 UUID>"}`를 전송해 reauthToken을 한 번 수령한다. 메모리 보관, 5분 만료, 세션 만료/폐기/역할 변경 시 사용 불가다.
4. PIN 변경 요청의 `X-Reauth-Token`으로 전달한다. #58의 실제 PIN service는 현재 자녀/동의 권한을 검사한 다음 PIN을 바꾸는 트랜잭션 안에서 `ReauthenticationService.consume(identity, token, ReauthPurpose.PIN_CHANGE, childId)`를 호출한다. `consume`는 MANDATORY이므로 트랜잭션 밖에서 토큰만 먼저 소모하지 않는다. 변경 실패 시 소비도 롤백한다.

소유 파일: account/controller/ReauthenticationController.kt, account/service/ReauthenticationService.kt, account/domain/Reauthentication.kt, account/repository/ReauthenticationRepository.kt 및 account/ReauthenticationMapper.xml. 기존 GoogleOAuthClient는 로그인 메서드 시그니처를 보존하고 재인증 redirect 전용 wrapper만 추가했다.

## 현재 검증 기록

- 계약/스크립트 32개 통과, OpenAPI 3.1 표준 검사 통과. 최초 생성 YAML anchor 충돌과 변경된 NULL 계약의 기존 기대값을 수정한 결과다.
- 별도 PostgreSQL 17.11: core 9개·learning 5개 migration 적용, 63테이블/537컬럼 ERD 일치, 49개 제약 위반 거부·65 CHECK 집합·19 인덱스 검사 통과. 재실행 적용 0건/이력 불변, report downgrade/upgrade 후 동일 schema 재검사까지 통과했다. 최초 ERD의 새 student FK 표시 누락을 수정했고 전체 절차를 새 빈 DB에서 다시 통과했다.
- core 전체 test/bootJar 결과는 종료 시 아래에 기록한다. 테스트 전용 Google/삭제 소비자 대역과 실제 Google·learning/report 삭제 검증을 구분한다.


## #38 병합 반영

작업 중 PR #75가 develop에 병합됐다. #45의 42개 변경 파일을 ZIP/SHA-256 manifest와 stash로 보존한 뒤 전용 feature만 develop d3d28140d5b5a2e74cfd6c32f2ef2a983a25a016으로 fast-forward했다. 작업 커밋·이력 재작성은 없다. 인증 계약 검사 파일의 충돌은 기존 #36 여섯 operation과 새 #45 operation 검사를 모두 유지하도록 해결했다. #38의 learning/공통 멱등성 production 코드는 수정하지 않는다.

실제 병합된 StudentLearningContextService는 LINKED+ACTIVE만 조회하고 LearningProxyService는 검증된 STUDENT scope를 소비한다. 새 #45 통합 테스트는 실제 인증·공개 필터·#38 프록시·PostgreSQL을 HTTP 대역 learning과 연결해 정상 호출 후 연결 해제/삭제 확정 시 기존 학생 토큰이 401이 되고 추가 learning 호출이 없음을 검사한다. 이는 실제 learning 기록 삭제 검증은 아니다. #37 미병합 서비스는 여전히 복사하지 않는다.


## #37 병합 후 반드시 대조할 부분

미병합 #37 PublicAuthFilter는 모든 /children/{id} 경로에 현재 studentScope(법정대리인 동의 포함)를 요구한다. #45의 파기/연결 해제/삭제 상태 조회는 동의 철회·연결 해제 뒤에도 보호자 등록 이력과 재인증으로 접근해야 하므로, 병합 시 이 경로들을 정밀하게 구분해야 한다. 일반 자녀 조회/수정의 scope 검사는 유지한다. #37의 실제 동의 저장·철회/재동의 API와 #45 재인증·삭제/탈퇴를 한 흐름으로 확인하는 검증은 #37 병합 후에만 수행할 수 있다. 이번에는 해당 선행 필터/서비스를 복사하지 않았으며 현재 기반의 AuthService/ConsentAccessService로 가능한 권한 흐름을 검증한다.

병합 전 최종 소스 스냅샷의 core 전체 88개 테스트(실패/오류/생략 0)와 bootJar가 통과했다. #38 병합 후 계약 스크립트 36개와 OpenAPI 3.1 재검사도 통과했다. 병합 후 core 전체 결과는 아래 최종 기록을 따른다.


## 최종 검증·Git 상태

- 최종 기준/HEAD: `d3d28140d5b5a2e74cfd6c32f2ef2a983a25a016`(PR #75/#38 병합). 종료 전 fetch와 일치한다. #37 구현은 아직 develop에 없으므로 병합 후 동의/권한 통합 검증은 미실행이다. 향후 병합을 자동 감시하는 작업은 만들지 않았다.
- `feature/core-account-management`, develop 통합 대상. 이번 작업 커밋 0개, 모든 42개 변경은 미stage/미커밋이다. push·PR·이력 재작성 없음. 기존 checkout/다른 worktree의 브랜치·파일·실행 서비스는 변경하지 않았다. 원본 저장소는 origin, upstream 미등록이다.
- 최종 Temurin JDK 21.0.12.1 Docker/Linux 전용 볼륨에서 `bash gradlew test bootJar --no-daemon --max-workers=2 --no-watch-fs --console=plain -Pkotlin.compiler.execution.strategy=in-process -Dorg.gradle.jvmargs=-Xmx768m`: 종료 0, BUILD SUCCESSFUL(3m23s). **19개 클래스·110개 테스트, 실패/오류/생략 0**. #45 AccountManagementTest 21개, 기존 인증/Google/JWKS/메시징/Repository 및 병합된 #38 테스트를 함께 실행했다. 테스트 필터 없이 전체 test task가 실행됐다.
- 최초 Windows bind mount 실행은 파일 읽기 병목과 검증 중 계층 수정 때문에 결과를 완료로 집계하지 않고 종료했다. 동일 최종 소스를 Linux volume으로 옮겨 검증했다. 첫 Linux 실행은 #38 병합 전 88/88, 그다음 실제 #38 병합/새 연동 테스트를 포함한 전체 실행이 위 110/110이다.
- 마지막 스냅샷의 185개 core/config/test·이벤트·RabbitMQ 정의 파일은 원본과 SHA-256이 전부 일치했다. bootJar 내 모든 main/resources도 최종 원본과 바이트 단위로 일치했다. Flyway/Testcontainers/JUnit 라이브러리는 실행 JAR에 없다. JAR SHA-256: `86530c1c18ad43e2cae1a6581eed5c211134280bd542033cfe17a8f63612be3d`.
- `python -O -m unittest discover -s scripts/tests -v`: #38 병합 후 36/36 통과. 최종 OpenAPI 3.1 표준 검사 통과. DB 전체 migration cycle 통과는 위 기록을 따른다. #38은 DDL을 변경하지 않았으므로 통과한 전체 DB cycle을 다시 반복하지 않았다.
- Kotlin package/경로, 기능 간 service 호출, 기존 migration 보존, learning/report·#39·#42 범위 제외, 실제 .env·새 production 의존성 미포함 및 `git diff --check`를 확인했다.
- 공통 파일 변경: PublicAuthFilter(정확한 재인증 callback/영수증 경로와 동의 철회 후 파기 경로), GoogleOAuthClient(기존 로그인 보존·재인증 redirect wrapper), AuthProperties/application.yml/.env.example(reauth TTL), OpenAPI, API/아키텍처/ERD/README, 기존 인증·DB 계약 검사와 DB 음성 사례. 신규 V9가 서비스별 완료/재인증 저장과 삭제 프로필 NULL 표식을 제공한다.
- 검증 데이터는 합성 계정·자녀·결제/구독/환불 fixture이며 PostgreSQL/Testcontainers와 core HTTP를 실제 사용했다. Google은 로컬 JWKS/HTTP 및 client 대역, learning은 HTTP 계약 대역, 삭제 완료 보고는 테스트 전용 소비자 대역이다. 실제 Google 재인증·실제 learning/report 물리 삭제·#58 기기 정리·#48 결제 쓰기 통합·원격 CI·배포는 미검증이다.
- 남은 연결: #37 필터/동의 통합, #58의 PIN service에서 consume 호출 및 기기 매핑/폐기, #48의 계정 행 잠금 참여와 실 결제 상태 흐름, #55/learning의 실제 삭제/중복 이벤트/진행 작업 정지 및 RECORDS 이후 학습 재개 계약. 미구현 연동을 가짜 성공으로 대체하지 않았다.
- 복구용 ZIP·SHA manifest·stash(`79a5ddf93bc7ed5ed072925cc410502e69e6758a`)와 테스트 XML/JAR는 작업 폴더 옆 `issue45-verification`에 보존한다. stash는 보존용이며 feature 히스토리에 추가된 커밋이 아니다. 전용 worktree는 검토/후속 통합을 위해 유지한다.

검증 종료 시 이번 작업의 core 검증 컨테이너 2개·schema PostgreSQL 2개 및 전용 schema 네트워크를 실제 ID 확인 후 종료·제거했다. Testcontainers도 JVM 종료로 정리됐고, 공유 compose·실행 DB·다른 채팅 컨테이너는 변경하지 않았다. 최종 git diff --check 통과, stage된 파일과 unmerged index는 없다.


## 2026-10-28 core-integration PR 준비

사용자 요청에 따라 기능 PR base는 feature/core-integration, head는 feature/core-account-management다. 중간 통합 후 develop PR은 사용자가 진행한다. 최신 문서 작업을 임의로 덮어쓰지 않고 해당 통합 브랜치 40a2501을 fast-forward로 반영했다. 변경은 stash로 보존한 뒤 재적용했으며 이력 재작성은 없다.

#37의 일반 자녀 경로는 현재 studentScope 검사를 유지한다. #45의 정확한 삭제/연결 해제/상태 조회 경로는 동의 철회 후에도 서비스에서 보호자 등록 이력·현재 계정·재인증을 검사한다. 이 예외로 다른 보호자의 자녀나 일반 수정 경로가 열리지 않는다. #37 동의 서비스·#38 프록시·#39 SSE 코드는 통합 기준의 구현을 보존했다.

인증 검사·OpenAPI·README·API 문서 충돌을 양쪽 계약을 보존해 해결했다. 계약 스크립트 45개와 최종 OpenAPI 표준 검사를 실행한다. 최종 core 전체 결과는 후속 기록을 따른다. 실제 Google 및 learning/report 물리 삭제·#58 기기·#48 결제 쓰기 통합의 미검증 조건은 유지된다.

최종 통합 검증: JDK 21 core 전체 146개 테스트 통과(실패/오류/생략 0), test bootJar BUILD SUCCESSFUL(4m22s). #37 동의/자녀·#38 프록시·#39 SSE와 #45를 함께 실행했다. 계약 검사 45/45, OpenAPI 표준 검사 및 git diff --check 통과. 기존 V9/DDL 변경이 없어 앞선 DB 전체 cycle 결과를 유지한다. 검증 컨테이너는 종료·제거했다.
