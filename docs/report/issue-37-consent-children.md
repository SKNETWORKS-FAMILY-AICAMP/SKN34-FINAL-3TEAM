# 이슈 #37 동의·자녀 등록

> 최신 develop 통합·검증과 PR 준비 기준은 [PR 준비 보고서](issue-37-pr-preparation.md)를 따른다. 아래 SHA·미커밋/미푸시 표시는 각 검증 시점의 기록이다.

> 후속 작업으로 learning 최소 exists API를 추가하고 실제 두 서비스·DB의 기록 유무 연동을 완료했다. 최신 계약·검증·#27 인계는 [기록 존재 확인 보고서](issue-37-record-existence.md)를 따른다. 아래 attempts 경로·공급자 미구현 기록은 후속 작업 전 검증 이력이다.

## 기준과 경계

`origin/develop` ecd6ecf7880e90341855d2fad6d9e773f3711c67(PR #61 포함)에서 `feature/core-consent-children` 전용 worktree로 분기했다. 원본 체크아웃을 전환하지 않는다. #38 learning·멱등성, #43 모델·사용량, #45 삭제·탈퇴, #58 PIN·기기 DB/로그인, #59 기기 화면은 변경하지 않는다. V1~V8을 보존하며 이 기능은 기존 테이블을 사용하므로 새 migration 번호를 소비하지 않는다.

## 계약과 근거

- 기존 프론트 `Consent`의 `{documentId,version,agreed}`를 유지한다. Google 최초 로그인 뒤 `POST /me/consents`로 저장하고 `/me`를 다시 읽는다. TERMS·PRIVACY는 계정 범위, GUARDIAN은 `childId` 범위다. 자녀 등록은 기존 `consents` 배열과 프로필을 같은 트랜잭션으로 저장한다.
- 문서별 현재 버전은 KST 시행일 이하에서 effective_from, created_at, id 내림차순으로 고른다(#36과 동일). 숫자/문자열 version의 대소 비교를 사용하지 않는다. 필수 문서 누락·빈 본문·필수 GUARDIAN 설정 누락은 503 CONSENT_DOCUMENTS_UNAVAILABLE이다. 운영 문서 본문을 앱이 임의 생성하지 않는다. 운영자가 검토된 3종 문서를 DB에 게시해야 한다.
- 문서 ID·버전·범위가 현재 문서와 다르면 409 CONSENT_DOCUMENT_CHANGED, 중복·누락·필수 거부는 400 VALIDATION_FAILED다. 선택 거부도 agreed=false로 기록한다. 같은 현재 선택의 재전송은 기존 행을 재사용하고, 변경·철회 후 재동의는 새 행을 추가한다. 권한 판정은 해당 문서·주체·자녀의 최신 행만 사용한다. 현재 문서·권한 조회는 MyBatis 1차/2차 캐시를 사용하지 않아 같은 트랜잭션의 재조회도 새 게시·철회를 반영한다. 철회는 본인 행만 갱신하며 과거 행 철회로 최신 재동의를 취소하지 않는다.
- 보호자 계정 행의 FOR UPDATE 잠금으로 동의 변경·철회·등록을 직렬화한다. 최대 3명은 LINKED 연결 전체를 센다. 학생·연결·GUARDIAN 동의는 원자 저장한다. 학년 3~6, 공백 아닌 별명(최대 40자), 출생연도 1900~현재 KST 연도를 검사한다. 나이를 임의 계산해 P01의 전원 14세 미만 정책을 바꾸지 않는다.
- `linkedStudents`는 관리할 연결 목록을 유지한다. `requireOwned`는 동의 재확보용 소유 확인이며 `requireLinked`는 같은 반환형을 유지하면서 현재 법정대리인 동의까지 검사한다. 인증 서비스는 현재 동의가 있는 자녀만 내부 scope에 넣는다. 공통 필터의 최소 변경은 `/children/{UUID}` 경로의 현재 scope 검사와 동의 전 복구 경로의 HTTP 메서드 제한이다. GET /me, GET·POST /me/consents, POST 철회만 예외로 두어 PATCH /me로 동의 검사를 건너뛰지 못하게 한다. 기존 세션의 학생 동의 검사는 유지한다.
- 사용자가 승인한 기록 계약: `hasRecords`는 boolean 또는 null, `recordState`는 AVAILABLE·UNAVAILABLE·CONSENT_REQUIRED다. 실제 learning `/internal/records/students/{studentId}/attempts?from=1900-01-01&to=<KST 오늘>&page=0&size=1` 응답의 childId·state·totalElements를 검사한다. 정상 집계만 boolean으로 반환한다. 공급자 부재·HTTP 장애·계약 위반은 null/UNAVAILABLE로 표시한다. 동의 없는 자녀는 원격 조회하지 않고 null/CONSENT_REQUIRED다. learning DB를 직접 읽지 않는다. 기준 브랜치에 이 공급자 Controller가 없으므로 실제 양 서비스 연동 완료로 표시하지 않는다.
- 사용자가 승인한 대로 pinSet은 제외한다. 기존 프론트용 `id`를 응답 식별자로 사용한다. `plan`은 #37에서 임의 생성하지 않는다. 기존 화면 모델의 선택적 상품 정보는 후속 상품 연동 범위다.

## 검증 결과

- 프론트 `npm test`: 57/57 통과(실패·생략 0). 추가한 #37 소비자 테스트 3개는 단계 전환·현재 문서 버전 전달·기록 미확인·철회/재동의·학생 철회 시 부모 refresh 금지를 검증한다.
- `npm run lint`, `npm run build`, `node tests/production-mocks.mjs` 통과. 이용권 정보가 없는 자녀를 프리미엄으로 잘못 표시하지 않도록 최종 검토에서 표시를 수정한 뒤 영향 범위 lint·타입/build·운영 mock 제외 검사를 다시 통과했다. 기존 500KB chunk 안내는 남아 있고 성능 효과를 측정하지 않았다.
- `python -O -m unittest discover -s scripts/tests -v`: 25/25 통과. 기존 #36 여섯 인증 operation 검사를 유지하면서 #37 여섯 operation과 nullable 기록 상태를 대조한다.
- 임시 `uvx` 환경의 `openapi-spec-validator`: OpenAPI 3.1 표준 검사 통과. 저장소 production/test 의존성·lock은 변경하지 않았다.
- 기존 `scripts/check_db_migrations.py`를 별도 `issue37-postgres`와 `issue37-verify` 네트워크에서 실행해 전체 적용, 60개 테이블/518개 컬럼 ERD 대조, 47개 제약 위반 입력 거부, 62개 CHECK 값 집합, 19개 인덱스 검사, migration 재실행 이력 불변, report downgrade/upgrade를 통과했다. 기존 compose·공유 DB를 사용하거나 수정하지 않았다.
- Windows JDK 21 실행은 production 컴파일 전에 JDK Unix socket loopback 오류로 중단됐다. IPv4/Selector 실행 옵션도 해결하지 못해 저장소 설정을 바꾸지 않고 전용 Temurin JDK 21 Docker 실행으로 전환했다. core 결과와 실제 브라우저 결과는 아래에 기록한다.

## 남은 연동

- 당시 기준 develop에는 learning 기록 공급자가 없었다. 이후 사용자 승인으로 최소 exists API를 추가했고 GET /children에서 실제 DB의 0건 false·1건 이상 true를 확인했다. 이 연동의 상세와 #27 전체 미구현 범위는 후속 보고서를 따른다.
- 운영용 동의 문서 본문·버전·시행일의 검토와 DB 게시가 필요하다. 시험 본문을 운영 seed나 fallback으로 넣지 않았다.
- #45 삭제·탈퇴/Google 재인증, #58 PIN·기기 저장과 로그인, #59 기기 화면은 남은 범위다. #37의 pinSet 제외와 기록 UNAVAILABLE 정책은 이번 작업에서 사용자에게 확인했다.
- commit·push·PR·squash·운영 배포·원격 CI는 실행하지 않는다. 실제 Google 로그인은 #36 소유이며 이번 검증은 합성 부모 세션으로 시작한다.


## core 최종 검증 상세

- Temurin JDK 21.0.12.1 Docker + Testcontainers에서 `gradlew test bootJar --no-daemon`을 실행했다. 새 테스트의 JUnit/Kotlin `Test` import 중복으로 최초 테스트 컴파일이 실패해 JUnit import를 명시한 뒤 다시 실행했다.
- 전체 58개 실행 결과는 57개 통과·1개 실패였다. 실패는 새 문서 게시 후 같은 트랜잭션의 MyBatis 1차 캐시가 이전 권한 값을 돌려주는 경우다. 현재 문서·필수/법정대리인 동의 조회에 `flushCache=true`, `useCache=false`를 적용했다. 테스트를 캐시 비우기로 우회하지 않았다.
- 수정 후 `--tests com.sagomungchi.core.consent.ConsentChildrenTest --tests com.sagomungchi.core.account.AuthFlowIntegrationTest`와 bootJar를 실행했다. 동의·자녀 13/13은 통과했고, 기존 인증 테스트 기반의 RabbitMQ definitions import가 큐 누락 오류를 내 인증 12개가 초기화 단계에서 실행되지 못했다. 공통 메시징 기반이나 실제 서비스 설정은 수정하지 않았다.
- 새 Testcontainers 환경에서 인증 `--tests com.sagomungchi.core.account.AuthFlowIntegrationTest bootJar`를 다시 실행해 12/12 통과(실패·생략 0), BUILD SUCCESSFUL을 확인했다. 수정 영향 25개는 모두 통과했고 영향 없는 나머지 33개는 앞선 전체 실행의 통과 결과를 유지한다. 당시에는 최종 소스로 전체 58개를 한 번에 재실행하지 않았다. 이후 전체 재실행 결과는 아래 추가 검증 절을 따른다.
- 검증 범위: 동의 전 차단(본인 수정 우회 포함), KST 현재 문서·미래 버전 제외·새 버전 재동의, 선택 거부 이력, 반복 저장·철회·재동의, 타 보호자 403, 학년/출생연도·필수값 검증, 학생·연결·법정대리인 동의 원자성, 4번째 자녀 거부, 2명에서 5개 동시 등록 요청 중 정확히 1개 성공(최종 3명), 기존 부모/학생 세션의 철회 후 접근 차단과 복구.
- 실제 MockMvc → public filter → 인증 → 동의 → 자녀 → 동석 학생 발급의 생산자·소비자를 PostgreSQL과 함께 검증했다. 기록 클라이언트는 로컬 HTTP 공급자 대역으로 내부 토큰/검증 scope·범위 전달, 실제 응답의 기록 유무, 404·503·잘못된 응답·대상 불일치의 UNAVAILABLE 구분과 재시도 없음까지 확인했다.
- 생성 JAR의 ConsentAccessMapper.xml이 최종 소스와 바이트 단위로 같음을 확인했다. 기존 OutboxWriter/메시징 테스트의 Kotlin annotation 경고는 이번 변경 전부터 있던 것으로 보존했다.

## 실제 브라우저·격리 JAR/DB 연결

production build(MSW 제외), 최종 core JAR, 전용 PostgreSQL과 임시 로컬 프록시를 연결했다. 다른 채팅의 localhost 인증 쿠키와 섞이지 않도록 `issue37.localhost` 호스트에서 Secure 쿠키를 사용했다. 이 기동 설정은 임시 실행 인수이며 저장소 인증 정책·공유 compose를 바꾸지 않는다. 합성 부모 세션·비구속 시험 문서만 준비했고 실제 Google 로그인은 호출하지 않았다.

- `/oauth/complete` → `/parent/onboarding`: refresh 200, /me 200, 현재 문서 200.
- 계정 동의 저장 200 → /me의 CHILD_REGISTRATION_REQUIRED를 따라 `/parent/children/new`.
- 합성 자녀+법정대리인 동의 등록 201 → /me READY → 학부모 화면·실제 자녀 목록 200.
- 실제 기록 공급자 부재는 null/UNAVAILABLE로 표시했다. 대시보드·학생 학습 API는 기준 develop에서 미구현인 404가 그대로 표시된다. 이를 실제 학습/기록 공급 연동 성공으로 표현하지 않는다.
- 법정대리인 동의 철회 200 → 이력 보존·동석 진입 버튼 비활성화·재동의 안내. 재동의 저장 200 → 새 이력 추가·진입 복구.
- 계정 필수 동의 철회 200 → 실제 /children 403 → 필수 동의 화면 복귀. 재동의 후 READY 복구.
- 동석 진입 200 → `/student/home`·해당 합성 학생 역할/별명 표시. 이후 학습 홈·미션 API 404는 후속 기능 경계로 확인했다.
- 전용 DB 집계: 연결 자녀 1명, 동의 AGREED 3행·WITHDRAWN 2행, 세션 STUDENT/version 2/학생 범위 존재, 미사용 refresh 0행. 원문 토큰·실제 계정 정보는 보고서에 기록하지 않는다.

## 최종 상태

`feature/core-consent-children`, 기준/HEAD `ecd6ecf7880e90341855d2fad6d9e773f3711c67`, 기능 PR 기준 develop이다. 새 커밋 0개, 변경은 미커밋이며 commit·push·PR·squash를 하지 않았다. 다른 작업 폴더·브랜치와 기존 V1~V8은 보존했다. 공통 변경은 PublicAuthFilter의 복구 경로/자녀 scope 검사, AuthService의 부모 scope, 계정 잠금 service/Mapper, OpenAPI·공통 프론트 세션 처리·온보딩 연결이다. learning/IdempotencyService·모델·사용량 코드는 변경하지 않았다.


### 종료 시 원격 문서 변경·환경 정리

- 작업 시작 때 최신 origin/develop은 ecd6ecf였고 PR #61을 포함했다. 종료 시 다른 작업의 fetch/병합으로 origin/develop이 `1b600850b0aee73983d646819933585fd2b44934`(PR #70, 8ef2bbb 문서 정합성 변경 포함)까지 진행됐다. 차이는 문서 10개이며 실행 코드·DB 스키마·계약 동작 변경은 없다. 관련 API·아키텍처·ERD·기능 명세 차이를 검토했다. 이번 feature에 다른 작업을 섞거나 커밋을 만들지 않았으므로 기준 SHA는 유지했고 최신 문서의 통합은 남아 있다.
- 임시 브라우저 탭·프록시·core/PostgreSQL 실행 컨테이너·검증 네트워크를 종료했다. 전용 worktree와 Gradle 캐시는 보존한다. 원본 체크아웃은 feature/core-google-auth / a2439e6 그대로이고 작업 트리는 깨끗하다. 다른 채팅의 worktree는 전환·수정하지 않았다.
- 최종 변경 40개 파일에서 비밀키 패턴·실제 .env 포함·경계 밖 learning/사용량/모델·기존 migration 변경이 없음을 확인했다. 최종 git diff --check를 통과했다. 원격 CI·운영 배포·실제 Google 및 실제 learning 공급자 통합은 미검증이다.


## 2026-10-27 최종 소스 core 전체 재실행

사용자 요청에 따라 선택 필터 없이 최종 소스의 core 전체 테스트를 다시 실행했다. 기존 `issue-37` worktree와 `issue37-gradle-cache`, Temurin JDK 21 Docker 실행 방식을 재사용했다. PostgreSQL·RabbitMQ는 기존 테스트 기반의 Testcontainers에서 새로 격리 기동했으며 공유 실행 DB·compose·다른 채팅 서비스는 변경하지 않았다.

```text
bash gradlew test --no-daemon --max-workers=2 --no-watch-fs --console=plain
```

- 종료 코드 0, `BUILD SUCCESSFUL in 5m`.
- JUnit XML 12개 클래스·58개 테스트 전부 통과: failures=0, errors=0, skipped=0.
- `--tests` 등 선택 필터 없이 전체 test task가 실제 실행됐다. 컴파일만 UP-TO-DATE로 재사용했고 test task는 재실행됐다.
- 실행 전후 core 소스·테스트·리소스·빌드 설정 및 RabbitMQ definitions 129개 파일의 SHA-256이 동일했다. 이번 재실행을 위해 production 코드·테스트 코드를 수정하지 않았다.
- 기존 간헐적 RabbitMQ definitions 초기화 오류는 이번 실행에서 발생하지 않았다. 전체 테스트가 한 명령으로 성공했으므로 **`./gradlew test` 통과 완료 조건을 체크할 수 있다.**
- 테스트 컨테이너와 전용 실행 컨테이너가 종료·정리됐음을 확인했다. 전용 Gradle 캐시는 유지한다.
- 이번 작업은 결과 보고서만 갱신했고 commit·push·브랜치 전환을 하지 않았다. 기준 HEAD는 ecd6ecf7880e90341855d2fad6d9e773f3711c67이며 최신 develop 통합 검증은 별도다. 실제 learning 기록 공급자 연동은 기존 남은 항목으로 유지한다.
