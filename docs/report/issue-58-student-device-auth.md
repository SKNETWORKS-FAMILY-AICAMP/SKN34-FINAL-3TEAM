# #58 학생 기기 인증

기준: origin/develop `78bbdc1` (#45 DB 재인증 포함). PR base는 develop이다.

## 결정·계약

- 등록일부터 고정 90일, 사용 시 연장하지 않는다(사용자 확인). 학생 TTL은 기존 AUTH_STUDENT_ACCESS_TTL, 실패 5회 잠금이다.
- PIN 변경은 같은 DB 트랜잭션에서 ReauthenticationService.consume(identity, token, PIN_CHANGE, childId)를 호출한다. 실패 시 소비도 롤백한다.
- 기존 부모 세션을 바꾸지 않고 학생 전용 auth_session을 만든다. 학생 refresh는 발급하지 않는다. 기기 해제는 다음 PIN 로그인부터 차단하며 기존 access는 만료까지 유효하다.
- account는 기기·페어링·학생 토큰, guardianship은 PIN 저장·잠금과 자녀 권한을 소유한다. 다른 기능의 repository에 직접 접근하지 않는다.
- 계정 행 → 기기/학생 행 순으로 잠근다. 동의 철회·연결 해제·삭제·탈퇴와 같은 계정 잠금에 참여한다. PIN 실패 결과는 트랜잭션 커밋 후 HTTP 오류로 변환하여 카운터가 롤백되지 않게 한다.
- 페어링은 Redis 해시 키·10분 TTL·원자적 단회 소비. DB 등록 실패 시 코드 복원 없이 새 코드 발급을 요구한다. 원문 PIN·코드·기기/재인증 토큰을 로그에 기록하지 않는다.
- Redis starter는 Boot 관리 버전을 사용한다. 기존 Redis 연결을 공유하고 페어링 키는 `student-device:pairing:`·시도 제한 키는 `student-device:attempt:`로 분리한다.
- PIN 잠금·새 기기 알림은 제품 계약 미확정으로 연결하지 않는다. #40·#44 기능과 새 테마는 범위 밖이다.
- GET /children의 기존 id·동의·기록 계약을 유지하고 실제 저장 상태 pinSet·pinLocked를 추가한다. 프로필·프론트·MSW는 pinLocked로 통일한다.

## 검증

코드·설정·테스트 작성 완료 후 일괄 검증했다. 실패 원인과 수정 후 재검증을 아래에 구분했다. 실제 Google·배포·원격 CI 결과를 로컬 대역 검사로 대체하지 않는다.

## 통합 설정

#44 worktree의 최종 V12__report_failed_notification_type.sql과 충돌하지 않도록 #58은 V10을 사용한다. Redis starter와 spring.data.redis host/port/password, 2초 연결/명령 timeout을 동일하게 맞췄다. compose의 기존 redis를 사용한다. PIN 저장은 PBKDF2-HMAC-SHA256(600,000회, 16바이트 난수 salt), 기기 토큰은 기존 TokenService의 256bit 난수와 SHA-256 해시다. 단독 로그인 성공은 다른 탭에 부모 세션 역할 변경을 broadcast하지 않는다.


## 최종 검증 결과

- `npm test`: 75/75 통과. `npm run lint`, `npm run build`, `node tests/production-mocks.mjs` 통과. 기존 번들 500kB 경고는 남으며 성능 개선을 주장하지 않는다.
- #59 `student-device-browser.mjs`: 서로 다른 10개 사례 통과. 초기 잠금 대기 1회 timeout은 같은 사례 단독 재실행에서 통과했다. 첫 3개 + 잠금 1개 + 만료 필터 4개 + 학부모 필터 3개(첫 등록 사례 중복)로 검증했다.
- `student-device-live-browser.mjs`: MSW 없이 실제 core JAR·PostgreSQL·Redis·Chrome 연결 통과. Google authorize/token/JWKS 및 learning 기록 유무 조회만 테스트 HTTP 대역이다. 실제 Google 계정/콘솔 검증·실제 learning 기록 조회·학생 홈(#40) 품질 검증은 아니다. Google 대역의 RS256 서명·nonce·PKCE 교환은 실제 GoogleOAuthClient가 검증했다.
- 실제 연결 범위: Google 로그인 → 자녀별 재인증 → PIN 저장 → 페어링 → httpOnly 쿠키 → 5회 실패/잠금 → 새 재인증·PIN 재설정 → 학생 로그인·학부모 API 거부·refresh 미발급 → 부모 세션 유지 → 기기 해제 → 기존 access 유지/새 기기 진입 차단. GET /children의 id·기록 유무·동의 상태·pinSet/pinLocked를 함께 확인했다.
- 계약 Python 테스트: 최종 전체 54/54 통과. OpenAPI 3.1 표준 검사 통과. 기존 #36 테스트의 신규 경로 미구현 가정과 YAML 정리 중 보안 스키마 중복을 수정한 뒤 해당 검사를 재실행했다.
- 새 격리 PostgreSQL 17.11에서 core 10개·learning 5개·report migration 적용. 65개 테이블/551개 컬럼 ERD 일치, 56개 제약 음성 검사, 65 CHECK 집합, 23 인덱스 검사 통과. 두 번째 실행 적용 0개·이력 불변, report downgrade/upgrade 후 전체 schema 재검증 통과.
- Linux JDK 21.0.12.1 `test bootJar`: 최종 33개 클래스·182개 테스트 통과(실패/오류/생략 0), BUILD SUCCESSFUL. #58 신규 테스트 10개를 포함하며 기존 인증·동의·학습·SSE·계정 삭제·리포트 회귀도 함께 실행했다.
- 실제 PostgreSQL·Redis에서 통과: 실제 Redis 페어링 동시 소비·만료·재사용/시도 제한, 실제 PostgreSQL PIN 동시 실패·5회 잠금·재설정, 재인증 대상/작업/세션/만료/재사용/트랜잭션 롤백, 삭제·탈퇴와 PIN/기기 동시 요청 및 기존 core 회귀.
- Windows 로컬 JDK는 Gradle daemon 시작 중 `Unable to establish loopback connection` / `UnixDomainSockets.connect Invalid argument`로 실패했다. IPv4·짧은 임시 소켓 경로로도 동일하다. Docker 소켓 없는 별도 JDK 컨테이너로 컴파일은 완료했다.
- 초기 Docker 소켓 마운트는 자동 승인 검토에서 거부됐고, 사용자가 이번 #58 검증에 명시적으로 허용한 뒤 전용 JDK 컨테이너에서 전체 Testcontainers를 실행했다. 공유 서비스·DB를 사용하거나 수정하지 않았다.
- 실제 Google·원격 CI·배포 검증 미실행. PIN/새 기기 알림은 #44와 제품 계약 미확정으로 미연결. 학부모 대시보드·학생 홈·꾸미기 API를 추가하지 않았다.

## 회귀 수정과 검증 산출물

첫 전체 실행은 182개 중 ConsentChildrenTest 2개가 실패했다. 새 PIN 상태 조회가 외부 기록 조회용 worker 안에서 실행되어 호출 스레드의 미커밋 자녀를 보지 못했다. PIN 상태는 호출 스레드에서 먼저 읽고 외부 HTTP 조회만 기존 방식으로 병렬 실행하도록 수정했다. 자녀 응답의 이전 pinSet 미반환 기대도 실제 pinSet=false/pinLocked=false 계약으로 갱신했다. 최종 전체 test/bootJar를 다시 실행하여 모두 통과했다.

신규 테스트 annotation import 중복은 컴파일 단계에서 수정했다. 브라우저 harness의 OAuth 리다이렉트·learning 대역 경로·외부 글꼴 대기·비동기 응답 캡처도 수정했으며 실제 제품 오류와 구분한다.

최종 core 소스·설정·테스트 230개는 검증 컨테이너와 SHA-256으로 대조한다. 테스트 XML과 JAR는 저장소 밖 전용 검증 폴더에 보존하며 커밋하지 않는다.

## 전달 상태

작업 브랜치는 `feature/core-student-device-auth`, PR base는 `develop`, 구현 시작점은 `78bbdc1`이다. 검증 중 확인한 최신 develop `47e5ffe`의 별도 LLM 비용/주석 수정은 이 기능에 섞지 않는다. PR은 사용자가 직접 생성한다.

실제 해결 범위인 #58은 PR 본문에 `Closes #58`을 포함한다. 기본 브랜치도 develop임을 확인했다. #59는 필요한 API·재인증 연결만 수정했으므로 자동 종료 대상으로 넣지 않는다. 추천 라벨은 현재 등록·설명을 확인한 `enhancement`, `area:core`, `area:db`, `area:web`이며, #58의 현재 Type은 미설정이다.

최종 검증 JAR SHA-256: `2a650ca4311ebd00986a1d76fe5947e37cfe3dc20077289f1d26d8c8bd99e764`.
