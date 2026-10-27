# 이슈 #36 Google OAuth·access/refresh 인증

> PR #49의 개정 P01에 맞춰 기존 Google·동석 인증 코드를 정렬한다. 학생 기기·PIN 신규 API·화면은 별도 후속 범위이며 [학생 로그인 분리 보고서](student-login-separation.md)를 따른다.

## 확정한 계약

Google Authorization Code + PKCE S256 로그인은 core 콜백에서 처리한다. access JWT는 HS256이며 부모 기본 15분, 학생 기본 15분(별도 설정)으로 프론트 메모리에만 둔다. refresh는 256비트 난수이고 HttpOnly·Secure·SameSite=Strict 쿠키로 전달하며 SHA-256 해시만 저장한다. 부모·관리자 로그인 세션은 최초 발급부터 기본 7일이며 회전으로 연장하지 않는다. 학생은 access 만료까지만 유효하고 refresh를 발급하지 않는다. JWT 서명 검증은 Spring Security JOSE, Google ID 토큰은 Google JWKS 서명·iss·aud·exp·nonce 검증을 사용한다.

`GET /api/v1/auth/google/authorize` → Google → `GET /api/v1/auth/google/callback` → refresh 쿠키 설정 → web `/oauth/complete` → `POST /auth/refresh` → `GET /me` 순서다. 서비스 토큰은 URL에 넣지 않는다. OAuth 상태 쿠키는 별도로 HttpOnly·SameSite=Lax, 10분 만료로 사용한다. 공개 web origin과 `/api`는 동일 origin으로 구성하고 쿠키 API의 Origin을 검사한다.

로그인 계정은 `(oauth_provider, oauth_subject)`로 식별한다. 이메일은 표시·연락 정보이며 기존 이메일 계정과 자동 연결하지 않는다. 기존 계정은 V8에서 삭제하거나 가짜 subject로 채우지 않는다. 비밀번호 컬럼은 nullable로 보존하고 실제 사용은 중단한다. 신규 계정은 PARENT, 관리자는 승인된 계정의 role·admin_permission을 운영자가 지정한다.

## 세션·권한

access에는 sub(보호자/관리자 계정), sid, 세션 버전, role, 학생 범위를 연결한다. 매 요청에서 DB의 현재 세션·계정·연결 상태를 확인한다. 로그아웃·역할 전환 후 이전 access는 즉시 거부하며 서비스 간 헤더는 클라이언트 입력이 아닌 검증 결과로 생성한다. admin 세부 권한도 DB의 최신 값을 확인한다.

refresh는 원자적으로 한 번만 소비한다. 사용 이력을 남기고 이미 소비한 토큰이 다시 제시되면 해당 로그인 세션을 폐기한다. 다른 기기의 로그인은 유지한다. 학생 진입 시 연결된 활성 학생과 현재 법정대리인 동의를 확인하고 현재 세션의 role·student_id·version·만료를 변경한다. 부모 refresh를 소비하고 쿠키를 삭제한다. refresh는 부모·관리자 전용이며 학생 세션에서는 거부한다. 같은 브라우저의 탭은 역할을 공유하며 Web Locks로 refresh/전환/로그아웃을 직렬화하고 BroadcastChannel로 상태 변경을 알린다. 학생 전환을 받은 탭은 메모리 토큰·캐시를 지우고 학생 진입 화면으로 이동한다. 학생 만료·새로고침 시 자동 refresh로 권한을 복원하지 않는다. 토큰·인증정보는 영구 저장하지 않는다. 보호자 복귀는 기존 보호자 access를 복원하지 않고 Google 로그인을 다시 시작한다. Google SSO가 실제 보호자 재확인을 보장하는 것은 아니며 추가 본인 확인은 별도 제품 정책이다.

## #37·#45 경계와 프론트 영향

이메일·비밀번호 공개 로그인/가입 API는 폐지한다. 기존 MSW 이메일 fixture 로그인은 개발 전용 시연으로만 유지한다. 실제 모드의 로그인·가입 화면은 Google 진입으로 교체한다. `/me`는 `nextAction`(CONSENT_REQUIRED, CHILD_REGISTRATION_REQUIRED, READY)과 `startPath`를 돌려준다. 동의 완료 전에는 본인 조회·로그아웃·동의 관련 요청만 허용한다. 실제 동의 저장·자녀 등록은 #37 소유이며 미구현 API 실패를 성공으로 숨기지 않는다. 비밀번호 복구·로그인 수단 변경 API는 제외한다. Google 재인증 토큰과 계정 관리 API는 #45 소유다.

## 배포·변경

JWT 키는 base64로 인코딩한 최소 32바이트 난수이며 환경/Secret으로 core에만 주입한다. Google Client ID·Secret·web origin은 환경별로 분리한다. Kubernetes 앱 chart가 아직 없으므로 실행용 Secret 참조 계약을 문서화하고 새 배포 계층은 추가하지 않는다. Secure=false는 로컬 HTTP에서만 사용한다. Google 키가 없으면 로그인 시작은 명시적 503이며 가짜 로그인 fallback은 없다.

이후 알고리즘·만료·권한 정책을 변경할 수 있다. 변경 시 기존 토큰/세션의 교체·폐기와 DB 마이그레이션, 공개 계약 및 프론트 소비자를 함께 갱신한다. 현재는 단일 HS256 키를 사용하므로 키 교체는 기존 access·OAuth 상태 토큰을 무효화한다.

## 검증

구현과 테스트 작성을 완료한 뒤 로컬 단위·DB/HTTP 계약·프론트 테스트·lint·build·스키마 검사 및 diff 검사를 일괄 실행한다. 실제 Google 로그인은 환경별 자격 증명·등록된 redirect URI가 있어야 별도 확인할 수 있다. 원격 CI·실제 Google API·배포 검증과 로컬 대역 테스트를 구분해 결과를 기록한다.

## 개정 P01 후속 경계
학생 기기·PIN 신규 API 7개·화면·Redis·PIN 저장 구조는 이번 기존 구현 정렬에 포함하지 않는다. PIN 설정의 Google 재인증 선행 시점과 기기/PIN 마이그레이션 번호를 별도로 확정한다. 학생 기기 해제 후 이미 발급된 access는 만료까지 유효하다는 최신 정책을 유지한다. refresh 재사용 검사는 DB 행 잠금 뒤 MyBatis 캐시를 비우고 다시 읽으며, 시각은 PostgreSQL 마이크로초 정밀도로 맞춘다.


## 2026-10-27 로컬 최종 검증 결과

- core: JDK 21에서 `gradlew.bat test bootJar --no-daemon`으로 production 컴파일·실행 JAR을 생성했다. 인증 18개를 포함한 전체 29개 테스트는 테스트 컨텍스트 격리 수정 후 `gradlew.bat test --no-daemon`으로 29/29 통과(건너뜀 0)했다. PostgreSQL·RabbitMQ Testcontainers를 사용했고 실제 Google 대신 로컬 HTTP/JWKS 대역 및 OAuth client 대역을 사용했다.
- 최초 전체 검증에서는 새 인증 테스트 컨텍스트의 사용량 Consumer가 기존 메시징 테스트와 같은 큐를 소비해 1개 실패했다. 인증 테스트에서만 AMQP listener 자동 시작을 끄고 전체 29개를 다시 실행해 통과했다. 기존 메시징 테스트·production Consumer는 그대로 유지했다.
- refresh 동시 소비는 세션 행 잠금 후 캐시를 비운 토큰 재조회로 처리하고, 재사용 시 세션 폐기가 실제 commit되는지 확인했다. PostgreSQL 저장 정밀도에 맞춰 로그인 시각을 마이크로초로 정규화했다.
- frontend: `npm test` 54/54 통과, `npm run lint`, `npm run build`, `node tests/production-mocks.mjs` 통과. 라우팅 경쟁 수정 후 영향 범위인 lint·타입/build·운영 mock 제외·실제 브라우저 동작을 다시 확인했다. 빌드의 500kB chunk 안내는 남아 있으며 성능 측정이나 번들 분할은 수행하지 않았다.
- 실제 Chrome 2개 탭 + production build + 로컬 API 대역으로 Google 완료 경로→동의 단계, 부모 복원, 동석 학생 진입, 다른 탭의 학생 진입 화면 이동, 학생 만료·새로고침을 확인했다. 학생 새로고침 전후 refresh 집계는 12→12, 학생 refresh 0회, 동시 부모 refresh 최대 1회, 두 탭 JS 오류 0건이었다. 실제 Google 로그인·실제 배포 검증을 뜻하지 않는다.
- `python -O -m unittest discover -s scripts/tests` 18/18 통과. V8은 앞선 격리 PostgreSQL 전체 마이그레이션 검증에서 적용·ERD·47개 제약 거부 사례·재실행·report downgrade/upgrade를 통과했다. 이번 P01 정렬은 DDL을 바꾸지 않았으며 저장소의 최신 기기·PIN 예정 구조를 실제 적용했다고 주장하지 않는다.
- 문서 충돌 표시 제거, 이전 LinkedStudent package 참조 제거, 새 링크와 ERD 계약 대조 및 `git diff --check`를 확인했다. API·ERD의 기존 기획서 PDF 참조 누락은 이번 변경 전부터 있던 항목으로 보존했다.
- 최초 로컬 대역 검증 시점에는 실제 Google API를 실행하지 않았다. 이후 실제 Google 검증 결과는 아래 별도 절에 기록한다. 원격 CI·배포는 commit/push하지 않아 미실행이며 GitHub #36 제목·본문은 사용자 요청에 따라 수정하지 않았다.

### 남은 기능 경계

#37의 동의 저장·자녀 등록, #45의 중요 작업 Google 재인증, 등록 기기·PIN 신규 API 7개와 관리 화면은 후속 작업이다. 이 기능은 테스트 대역이나 준비 화면으로 실제 구현 완료를 대신하지 않는다. 병렬 에이전트는 실행하지 않았다.


## 2026-10-27 실제 Google 로그인 연동 검증

사용자가 로컬 `.env`에 설정한 자격 증명으로 실제 Google Authorization Code + PKCE 흐름을 검증했다. 키·비밀번호·계정 식별정보·토큰 원문은 출력하거나 보고서에 기록하지 않았다. `.env`는 검사 전후 무결성 대조로 변경하지 않았음을 확인했다.

- 필수 설정 입력·JWT Base64 키 형식·Origin/쿠키 정책과 `.env` → 실행 컨테이너 → 인가 요청의 설정 일치를 값 공개 없이 확인했다.
- Client ID 복사 형식 문제로 Google이 처음 `401 invalid_client`를 반환했다. 사용자가 ID를 다시 입력한 뒤 core만 재생성해 반영했고, 이후 Google 계정 선택 화면에 정상 도달했다.
- 실제 Docker 이미지 빌드·core 실행·PostgreSQL/RabbitMQ/Redis 준비 상태와 로컬 DB Flyway V8 적용을 확인했다. core·web은 HTTP 200이었다. 기존 데이터·볼륨을 삭제하지 않았다.
- Google 계정 선택·필요한 인증/동의는 사용자가 직접 수행했다. 실제 Google 응답 처리 후 `/parent/onboarding`의 필수 동의 안내로 돌아왔다.
- DB 집계: Google 계정 0→1, 활성 부모 세션 0→1, refresh 2행 중 사용 이력 1행·활성 1행. 원문 대신 해시 저장을 확인했다.
- 페이지 새로고침 후 같은 온보딩 화면 유지, 계정 1개 유지. refresh는 3행 중 사용 이력 2행·활성 1행으로 회전했다.
- 서비스 로그아웃 후 `/login`으로 이동했고 새로고침해도 로그인 화면을 유지했다. DB의 활성 부모 세션·활성 refresh는 각각 0개, 폐기된 세션은 1개였다. Google 계정 자체의 로그아웃을 수행한 것은 아니다.
- 이 검증은 실제 Google·로컬 core/web/DB 연동이다. 원격 CI·HTTPS 운영 배포·관리자 운영 계정·#37 동의/자녀 등록·#58 PIN/기기 전체 흐름을 검증한 것은 아니다.

검증 종료 시 서비스는 로그아웃 상태다. 로컬 core·web·의존 인프라는 추가 확인을 위해 실행 상태로 유지했다. 코드 동작은 변경하지 않았고 작업 커밋·push는 하지 않았다.


## #58 기기 인증 경로의 Bearer 필터 인계

- `POST /api/v1/auth/student/devices`, `GET /api/v1/auth/student/profiles`, `POST /api/v1/auth/student/login`만 사용자 Bearer 인증에서 제외한다. HTTP 메서드와 경로를 정확히 대조하며 `/auth/student/*` 전체를 열지 않는다.
- POST는 기존 쿠키 API와 같은 정확한 web Origin·X-Requested-With 검사를 유지한다. 페어링 코드·기기 쿠키·PIN의 실제 유효성 검사는 #58의 담당이며, Bearer 제외를 기기 인증 성공으로 취급하지 않는다.
- 동석 진입 `/auth/student-sessions`, 일반 본인·자녀·관리자 API, 다른 메서드·하위/유사 경로는 계속 Bearer를 요구한다. 기존 내부 토큰 인증과 사용자 컨텍스트 생성 흐름은 유지한다.
- 테스트 전용 #58 핸들러 대역과 실제 PublicAuthFilter를 MockMvc로 연결해 기기 쿠키 거부/성공, 잘못된 Bearer·위조 사용자 헤더의 미해석, Origin 방어와 보호 경로를 확인한다. 실제 Spring Boot 통합 테스트에서는 #58 핸들러가 없어 MVC의 404까지 도달하는 것을 확인하며 신규 #58 API 구현 완료로 표시하지 않는다.


### #58 필터 인계 검증 결과 (2026-10-27)

- `gradlew.bat test bootJar --no-daemon`: 총 38개 항목을 실행했다. 기존 인증·메시징 회귀 및 새 실제 Spring Boot 경로 검증 30개는 통과했고, 필터 단위 테스트의 오류 응답 JSON 직렬화 설정 차이 1개를 수정했다.
- production에서 사용하는 Spring ProblemDetail mixin을 테스트 ObjectMapper에도 적용한 뒤 `gradlew.bat test --tests 'com.sagomungchi.core._common.security.PublicAuthFilterTest' bootJar --no-daemon`으로 영향 범위 8개를 재실행해 8/8 통과(건너뜀 0)했다. 변경되지 않은 다른 30개는 반복하지 않았다. 실행 JAR도 확인했다.
- 테스트 전용 기기 핸들러는 TestComponent로 표시해 일반 Spring Boot 통합 테스트에 자동 등록되지 않게 했다. 이 핸들러는 페어링/기기 인증 경계 대역이며 실제 #58 기능 구현이 아니다.
- 로컬 core Docker 이미지를 다시 빌드하고 core만 재생성했다. 키·토큰 값은 출력하지 않았고 `.env`·DB·다른 서비스·볼륨은 수정하지 않았다.
- 실제 로컬 HTTP 8건 통과: 지정한 3개 경로는 올바른 Origin에서 Bearer 없이 404 NOT_FOUND(핸들러 미구현), 동석 전환·본인 조회·잘못된 메서드·유사 하위 경로는 401 UNAUTHENTICATED, 잘못된 Origin의 PIN 로그인 POST는 403 FORBIDDEN이었다.
- `git diff --check` 및 현재 작업 외 미커밋 파일의 내용 보존을 확인했다. 프론트·마이그레이션 변경이 없어 관련 전체 검증은 반복하지 않았다. 실제 Google 재로그인·원격 CI·운영 배포 검증은 이번 필터 변경에서 실행하지 않았다.
- 현재 브랜치 feature/core-google-auth, PR base develop. 이번 작업 커밋 0개·미stage 상태이며 push·이슈 수정은 하지 않았다.


## PR 준비: 최신 develop·공개 계약 정리

- 최신 develop의 PR #57(`1573924`)을 feature/core-google-auth에 fast-forward하고 기존 미커밋 변경을 재적용했다. 원본 파일 ZIP과 stash 백업을 보존했으며 코드·테스트의 기존 내용이 유지됨을 확인했다.
- 새 기기·PIN 구현은 #58 소유, OAuth·세션은 V8, 기기·PIN DB는 V8 이후 다음 버전으로 정리한 최신 설계를 반영했다. 자녀 기기에 Google 세션이 남는 위험을 줄이기 위한 코드·QR 기본 등록 방식과 예외 안내도 최신 원본 문서를 유지했다.
- `contracts/openapi/core-service.yaml`은 실제 구현한 #36 인증 경로 6개만 정의한다. #58 신규 API 7개·기기 테이블·PIN/Redis 구현은 포함하지 않으며 공개 Bearer 인계 경계만 설명한다.
- OpenAPI는 부모/학생 응답·학생 개인정보 제한·refresh 미발급·보안 쿠키·Origin/요청 헤더·302 콜백·오류 응답을 정의한다. scripts/tests의 계약 검사는 실제 Controller 경로·문서 참조·역할별 보안 계약과의 일치를 확인한다.
- 최종 커밋 전에 관련 코드·계약·migration·프론트 변경 범위와 secret/실제 .env 제외 여부를 검토한다. PR은 사용자가 develop 대상으로 직접 생성하며 원격 필수 CI는 PR 생성 후 확인한다.
- 최신화 후 scripts/tests 24/24와 OpenAPI 3.1 표준 검증을 통과했다. 추가한 계약 테스트 6개를 포함한다. 표준 검사 도구는 임시 환경에서 실행했으며 저장소 의존성·lock 파일은 변경하지 않았다.
- 첫 최신화 대상은 설계 문서였으나 push 직전 재확인에서 #14 Repository 기반 PR #60(`e3bb6ab`)이 추가 병합되어 다시 보존·fast-forward·재적용했다. 공통 UUID·시각 핸들러 및 앱 자동 migration 비활성화 정책을 유지한다.
- V8의 nullable password_hash 계약에 맞춰 새 예시 UserAccount의 passwordHash도 nullable로 맞추고 Repository 왕복 테스트에 포함한다. 새 Repository·빈 DB 기동 테스트는 production 키 대신 고정 테스트 JWT 키를 명시적으로 주입한다. 인증 구현은 기존 전용 조회 모델을 유지하며 무관한 Repository 통합 리팩터링은 하지 않는다.
- 최신 Repository 기반과 인증의 통합 영향은 core 전체 테스트·bootJar로 재검증한다. 프론트 실행 코드·V8 DDL은 보존했으므로 기존 프론트 54개 및 실제 Google 검증을 반복하지 않는다. 원격 core·DB 스키마 CI는 develop 대상 PR 생성 뒤 확인해야 한다.
- PR #60 반영·nullable Repository 정렬 후 `gradlew.bat test bootJar --no-daemon` 전체 44/44 통과(실패·건너뜀 0), 실행 JAR 생성 성공. 새 Repository 왕복·타입 핸들러·빈 DB 기동, 기존 메시징·OAuth·세션·필터를 함께 검증했다.
- 커밋 대상 62개 파일의 범위·기존 내용 보존·실제 환경 값 유출·개인 키 패턴 및 `git diff --check`를 확인했다. `.env`는 ignored·untracked 상태이며 변경하지 않았다. `.env.example`의 Google Client ID·Secret·JWT 키는 빈 입력란이다.
