# #136 core HTTP 경로·이용권 테스트 공백

## 범위와 결정

[점검 기록](audit.md) 1.6 "통합 테스트 없음"에서 서비스 수준 테스트만 있던 core 경로 7묶음에 HTTP 테스트를 더한다. 기준은 develop `b35e381`이다(측정은 `2db122c`에서 했고, 그 뒤 core 코드 변경 없음). 운영 코드·API 계약은 바꾸지 않는다.

| 해야 할 일 | 처리 |
|---|---|
| HTTP 테스트 7묶음 | `account/AccountHttpTest`(새 파일, 테스트 9개). `MockMvc`로 실제 `PublicAuthFilter`·컨트롤러·서비스·DB를 거침 |
| 권한 실패(학생·다른 보호자·재인증 누락) | 경로마다 포함. 재인증은 `X-Reauth-Token`을 쓰는 연결 해제·PIN 설정 두 경로에만 해당 |
| 실제 `ReportEntitlementService` 테스트(#129 후) | #129에서 들어온 `report/ReportEntitlementIntegrationTest`(테스트 9개)가 이미 실제 공급자로 확인. 이번에 더하지 않음 |

## 정한 내용

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 파일 위치 | 새 파일 `account/AccountHttpTest.kt`. 기존 `AccountManagementTest`·`StudentDeviceAuthTest`는 다른 팀원 파일이라 손대지 않음. 이름은 기존 `ReportHttpTest`·`ModelVersionHttpTest`와 같은 형식 | |
| 테스트 기반 | `PostgresRepositoryTest` 상속, `@Transactional(NOT_SUPPORTED)`와 행 정리, 페어링용 Redis 컨테이너는 클래스 안에서 띄움(형제 `StudentDeviceAuthTest`와 같은 구성) | [아키텍처](../design/architecture.md) 2.3 테스트 줄·[db-dev-guide](db-dev-guide.md) 2장: 메시징이 없는 테스트는 `PostgresRepositoryTest`, `IntegrationTestSupport`는 메시징 통합용. 처음에 `IntegrationTestSupport`로 만들었다가 설계대로 바꿈(아래 확인 필요의 연결 한도 참고) |
| 준비 함수 | 보호자·자녀·동의·재인증 토큰 준비 함수를 이 파일 안에 둠(기존 `StudentDeviceAuthTest`와 같은 SQL·흐름) | 기존 함수가 각 파일 `private`이라 재사용 불가. 공통 fixture 파일을 새로 만들지 않음 |
| 학생 세션 | 같은 보호자의 다른 로그인 세션에서 동석 진입(`enterStudent`)한 access | 기존 `AccountManagementTest`와 같은 방식. 보호자 원래 세션은 그대로 |
| 응답 기준 | 코드 동작 그대로 확인. 계약과 다르면 테스트를 맞추지 않고 확인 필요로 남김 | 이슈 범위가 테스트 추가 |
| 학생 차단 위치 | 학생 403은 응답과 함께 컨트롤러에 닿지 않았는지(MockMvc `handler` 없음)로 필터 차단까지 확인 | 학생 차단은 `PublicAuthFilter`(역할별 경로)와 서비스 `AccountManagementService.lock`(학부모만) 두 겹이고 둘 다 403 `FORBIDDEN`이라 응답만으로는 필터 규칙이 빠져도 알 수 없음(보호 장치 첫 실행에서 확인) |

## 경로별 확인

표의 학생 403은 모두 `FORBIDDEN`이고 필터에서 막혀 컨트롤러에 닿지 않음까지 확인한다.

| 경로 | 성공 | 실패 |
|---|---|---|
| `GET /me/withdrawal/precheck` | 200·`no-store`, 칸 5개(`canWithdraw`·`activeSubscriptions`·`unresolvedRefunds`·`retainedTransactionsYears`·`pendingPayments`). 구독·미처리 환불·확인 중 결제가 있으면 `canWithdraw=false`(409 아님). 필수 동의 철회 뒤에도 조회 | 로그인 없음 401 `UNAUTHENTICATED`, 학생 403 |
| `GET /children/{id}/deletion-impact` | 200·`no-store`, `actions` UNLINK·PROFILE·RECORDS, `retainedTransactionsYears=5`, `deviceCleanupPending=false`. 동의 철회 뒤에도 조회 | 다른 보호자 403 `CHILD_NOT_LINKED`, 학생 403 |
| `DELETE /children/{id}/link` | 204·`no-store`, `UNLINKED`, 감사 `CHILD_UNLINKED` | 재인증 누락·다른 목적(PIN_CHANGE) 토큰 403 `REAUTH_REQUIRED`, 다른 보호자 403 `CHILD_NOT_LINKED`, 학생 403. 실패 뒤 연결 유지 |
| `POST /student-devices/pairings` | 200·`no-store`, 8자리 영숫자 코드·`expiresAt`. 받은 코드로 실제 기기 등록 201 | 다른 보호자 자녀 403 `CHILD_NOT_LINKED`, 빈 목록·중복·4명 400 `VALIDATION_FAILED`, 학생 403 |
| `GET /student-devices` | 200·`no-store`, 등록 기기(label·children·createdAt·expiresAt), 해제 기기 제외, 토큰 해시 없음 | 다른 보호자 목록에 없음, 학생 403 |
| `DELETE /student-devices/{id}` | 204·`no-store`, 다시 호출해도 204, 감사 `STUDENT_DEVICE_REVOKED` 1건 | 다른 보호자·없는 기기 404 `NOT_FOUND`, 학생 403 |
| `PUT /children/{id}/pin` | 204·`no-store`, PIN 설정, 감사 `STUDENT_PIN_CHANGED` | 규칙 위반(`1234`) 422 `VALIDATION_FAILED`(재인증보다 먼저 검사), 재인증 누락·다른 목적 토큰 403 `REAUTH_REQUIRED`, 다른 보호자 자녀 403 `CHILD_NOT_LINKED`(필터에서 차단), 학생 403. 실패 뒤 PIN 미설정 |
| `GET /auth/google/authorize` | 로그인 없이 302, `no-store`·`Referrer-Policy: no-referrer`, 상태 쿠키 `sagomungchi_oauth`(HttpOnly·SameSite=Lax·`/api/v1/auth/google`·600초), 쿠키 state와 Google URL state 일치, URL에 서비스 토큰 없음 | Google 설정 없음 503 `OAUTH_UNAVAILABLE` |

## 파일

- 새 파일: `backend/core-service/src/test/kotlin/com/sagomungchi/core/account/AccountHttpTest.kt`
- 운영 코드·설계 문서·api-spec·OpenAPI 변경 없음

## 검증

- core 전체 413개 통과(새 9개). 실행 중 테스트 DB 연결 수를 5초마다 측정: `IntegrationTestSupport` DB 최대 99/100(이 파일 없는 develop 원본과 같음), `PostgresRepositoryTest` DB 최대 36/100(develop 32~33, 이 파일의 연결 풀 상한 5 안)
- 보호 장치 14개: 운영 코드를 하나씩 틀리게 하면 새 테스트가 각각 실패, 원래 코드에서는 모두 통과
  - 필터: 기기 경로·자녀 경로 학부모 전용, 학생 `/me/` 차단, precheck·deletion-impact 동의 철회 예외, Google 시작 공개 경로
  - 서비스: 영향 조회 소유 확인, 연결 해제·PIN 재인증 소비, PIN 규칙 검사 순서, 페어링 자녀 연결 확인, 기기 해제 소유자 확인, 재해제 감사 중복
  - OAuth 상태 쿠키 SameSite
- 첫 실행에서 필터 학생 차단 2개는 서비스 `lock`이 같은 403을 내 실패하지 않음 → 학생 403에 컨트롤러 미도달 확인을 더한 뒤 실패 확인
- 처음 `IntegrationTestSupport`로 만들었을 때는 그 DB가 100/100에 닿아 `SupportIntegrationTest`가 `too many clients`로 실패(18·22개). 설계대로 바꾼 뒤 위 결과

## 확인 필요

- precheck 응답 칸: api-spec 3.13은 `{canWithdraw,activeSubscriptions,unresolvedRefunds,retainedTransactionsYears}` 4칸인데 실제 응답은 #48에서 더한 `pendingPayments`까지 5칸([#48 리포트](issue-48-payments.md)에만 기록). api-spec에 칸을 더할지는 결제·계정 담당 확인 필요
- Google 503: 이 파일은 재인증 준비 때문에 `GoogleOAuthClient`를 mock으로 바꿔 써서, HTTP 테스트는 client가 던진 503이 응답으로 바뀌는 것만 확인. "설정이 없으면 client가 503"은 기존 `GoogleOAuthClientTest`가 확인
- [점검 기록](audit.md) 1.6 표의 해당 줄 처리 표시는 audit 담당 확인 후 반영
- `IntegrationTestSupport` DB 연결 한도: develop 원본(`2db122c`)만으로 최대 99/100(98개가 idle). 설정이 다른 클래스마다 캐시된 Spring 컨텍스트가 연결 10개(Hikari 기본값)를 계속 쥠. `PostgresRepositoryTest`처럼 연결 풀 상한(`maximum-pool-size=5`·`minimum-idle=0`)이 없어, 이 기반을 쓰는 클래스가 하나 더 생기면 PostgreSQL이 `too many clients`로 거절(로컬에서 develop `7eb829d`도 27개 실패한 적 있음). 공통 기반 조정은 이 이슈 밖이라 core 담당 판단 필요
