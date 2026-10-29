# 인증·계정 (#36·#37·#45·#58, P01 개정)

통합 원본: issue-36-google-auth, issue-37-consent-children, issue-37-record-existence, issue-37-review-followup, issue-37-pr-preparation, issue-45-account-management, issue-58-student-device-auth, student-login-separation

계약은 [API 명세](../design/api-spec.md) 3.11·5.1·5.3·5.4·5.6과 [core OpenAPI](../../contracts/openapi/core-service.yaml), 저장 구조는 [ERD](../design/erd.md) 3.1·10·11장.

## 1. Google OAuth·토큰 (#36)

- Google Authorization Code + PKCE S256을 core 콜백에서 처리. `authorize` → Google → `callback`(refresh 쿠키 설정) → web `/oauth/complete` → `POST /auth/refresh` → `GET /me`. 서비스 토큰은 URL에 넣지 않음
- access JWT는 HS256(Spring Security JOSE), 부모·학생 기본 15분, 프론트 메모리에만 보관. refresh는 256비트 난수·SHA-256 해시 저장, HttpOnly·Secure·SameSite=Strict, 부모·관리자 세션은 최초 발급부터 7일(회전으로 연장 안 함). 학생은 refresh 없음
- Google ID 토큰은 JWKS 서명·iss·aud·exp·nonce 검증. OAuth 상태 쿠키는 HttpOnly·SameSite=Lax·10분. web origin과 `/api`는 동일 origin, 쿠키 API는 Origin·`X-Requested-With` 검사
- 계정 식별은 `(oauth_provider, oauth_subject)`. 이메일은 연락 정보이며 기존 이메일 계정과 자동 연결하지 않음(같은 이메일은 `ACCOUNT_EXISTS`). 기존 계정에 가짜 subject를 채우지 않고 비밀번호 컬럼은 nullable로 보존·사용 중단. 신규 계정은 PARENT, 관리자는 운영자가 role·권한 지정
- 매 요청에서 DB의 세션·계정·연결 상태 확인. 로그아웃·역할 전환 후 이전 access 즉시 거부. refresh는 원자적 1회 소비, 재사용 시 해당 세션 폐기(다른 기기 유지)
- 같은 브라우저의 탭은 역할을 공유하며 Web Locks로 refresh·전환·로그아웃을 직렬화하고 BroadcastChannel로 알림. 학생 전환을 받은 탭은 토큰·캐시를 지우고 학생 진입 화면으로. 보호자 복귀는 Google 로그인부터 다시 시작
- 키: JWT 키는 base64 32바이트 이상 난수, core에만 Secret으로 주입. 단일 HS256 키라 교체 시 기존 access·OAuth 상태 토큰이 무효화됨. Google 키가 없으면 로그인 시작은 명시적 503(가짜 로그인 없음)
- Google SSO가 보호자 본인 재확인을 보장하지는 않음(추가 본인 확인은 별도 제품 정책)

## 2. 동의·자녀 등록 (#37)

- 저장 형식은 웹 `Consent`의 `{documentId,version,agreed}` 유지. TERMS·PRIVACY는 계정, GUARDIAN은 자녀 범위. 자녀 등록은 프로필과 GUARDIAN 동의를 한 트랜잭션
- 현재 문서는 KST 시행일 이하에서 `effective_from`·`created_at`·`id` 내림차순 첫 문서(버전 문자열 비교 안 함). 문서 미게시는 503, 앱이 본문을 생성하지 않음. 운영자가 검토된 3종 문서를 DB에 게시해야 함
- 선택 거부도 `agreed=false`로 기록. 같은 선택 재전송은 행 재사용, 변경·철회 후 재동의는 새 행. 판정은 같은 문서·주체·자녀의 최신 행만. 현재 문서·권한 조회는 MyBatis 캐시를 쓰지 않음
- 보호자 계정 행 `FOR UPDATE`로 동의 변경·철회·등록을 직렬화, LINKED 연결 수로 최대 3명. 나이를 계산해 P01(전원 14세 미만 간주)을 바꾸지 않음
- 필터 예외: 동의 전에는 `GET /me`, `GET·POST /me/consents`, 철회만 허용(PATCH /me로 동의 검사를 건너뛰지 못하게 메서드까지 제한). `/children/{UUID}` 경로는 현재 scope 검사
- 기록 유무: `hasRecords` boolean|null, `recordState` AVAILABLE·UNAVAILABLE·CONSENT_REQUIRED. learning 전용 `exists` API(사용자 승인으로 #27보다 먼저 최소 구현)를 호출하며, 공급자 장애·계약 위반은 null·UNAVAILABLE(기록 없음으로 바꾸지 않음), 동의 없는 자녀는 원격 조회 없이 CONSENT_REQUIRED
- 기록 조회 경로는 guardianship → learning `LearningRecordService` → `LearningRecordClient` → `LearningClient`(학생 전용 `LearningProxyService`와 분리, `learning-json` 서킷 공유). 최대 3명을 virtual thread로 병렬 조회하고 컨텍스트는 finally에서 정리
- `plan`은 이 API에서 만들지 않음(상품 연동 후속)

## 3. 계정 관리·재인증·삭제·탈퇴 (#45)

- 재인증 토큰 5분·세션/작업/자녀 결합·1회 사용(사용자 결정). Google 계정 확인은 비밀번호·MFA 재입력을 보장하지 않음
- 재인증 사용 절차(#58 PIN 변경 예)
  1. 원래 세션에서 `POST /me/reauth {"purpose":"PIN_CHANGE","childId":...}`(Origin·`X-Requested-With` 필요)
  2. 응답 `authorizationUrl`을 새 창에서 열어 Google 확인. Google 콘솔에 `<webOrigin>/api/v1/auth/google/reauth/callback` 등록 필요. callback은 VERIFIED 안내만, 로그인·refresh는 바꾸지 않음
  3. 원래 세션에서 `{"challengeId":...}`로 `reauthToken` 1회 수령(메모리 보관)
  4. 변경 요청의 `X-Reauth-Token`. 서비스는 권한 검사 후 같은 트랜잭션에서 `ReauthenticationService.consume(...)`(MANDATORY, 실패 시 소비도 롤백)
- 탈퇴 자격 조회용 최소 payment service·repository(결제 쓰기 없음), P09 core 대화·근거 삭제용 conversation service. 기능 간 접근은 service 경유
- 재인증·서비스별 완료 행은 V9. 상태 조회 영수증(`statusToken`)은 탈퇴 후 로그인 차단과 상태 조회를 함께 제공하기 위한 최소 계약
- RECORDS 삭제 이후 학습 재개는 하위 서비스 삭제 표식 수명주기가 정해지지 않아 자동 허용하지 않음(완료 후에도 `DELETION_REQUESTED`로 차단 유지)
- 동의 철회·연결 해제 뒤에도 삭제·연결 해제·삭제 상태 조회는 보호자 등록 이력과 재인증으로 접근 가능(일반 자녀 경로의 scope 검사는 유지)
- 미완료: learning `student.deleted` 소비·완료 보고가 없어 삭제가 COMPLETED가 되지 않음([점검 기록 B3](audit.md))

## 4. 학생 기기·PIN 로그인 (P01 개정, #58)

### 배경과 결정

기존 P01은 학부모 로그인 → 자녀 선택 → `POST /auth/student-sessions`로만 학생 세션을 만들어 학부모 부재 시 자녀 단독 학습이 불가능했음.

| 서비스 | 자녀 진입 | 학부모 역할 |
|---|---|---|
| [Khan Academy](https://support.khanacademy.org/hc/en-us/articles/202487460-If-my-child-is-under-age-13-what-login-options-are-there-) | 학부모가 만든 자녀 아이디·비밀번호 | 비밀번호 관리 |
| [Seesaw](https://help.seesaw.me/hc/en-us/articles/4424230271501-Seesaw-Codes) | 학생별 코드·QR(1년, 재발급) | 별도 가족 연결 |
| [ClassDojo](https://help.classdojo.com/hc/en-us/articles/360009869032-How-Students-can-Log-into-ClassDojo-at-Home) | 학부모 앱의 개별 QR | QR 발급 |
| [Epic](https://support.getepic.com/hc/en-us/articles/360027225131-How-do-I-add-edit-my-child-s-profile-PIN) | 하위 프로필 + 선택 4자리 PIN | 학부모 영역 재입력 |
| [Google Family Link](https://support.google.com/families/answer/7158477) | 기기 추가 시 학부모 승인 | 원격 관리 |

| 방식 | 판단 |
|---|---|
| 자녀 아이디·비밀번호 | 초3~6이 관리하기 어렵고 유출 시 어느 기기에서나 사용 가능 → 비채택 |
| QR·코드 단독 | 코드가 소지형 자격증명이라 종이·사진 유출에 취약 → 기기 등록 수단으로만 |
| PIN 단독 | 4~6자리는 추측 공격에 약함 → 비채택 |
| **학부모 승인 기기 등록 + 자녀 PIN** | 기기(소지)와 PIN(지식) 2요소, 자녀가 이메일·OTP를 관리하지 않음 → **채택** |

### 구현 결정

- 기기는 등록일부터 고정 90일(사용 시 연장 없음, 사용자 확인), PIN 5회 실패 잠금, 학생 access TTL은 `AUTH_STUDENT_ACCESS_TTL`
- 부모 세션을 바꾸지 않고 학생 전용 `auth_session`을 만듦(refresh 없음). 기기 해제는 다음 PIN 로그인부터 차단, 기존 access는 만료까지 유효(즉시 차단은 토큰 폐기 목록이 필요해 별도 검토)
- account가 기기·페어링·학생 토큰, guardianship이 PIN 저장·잠금과 자녀 권한을 소유. 계정 행 → 기기·학생 행 순서로 잠금(동의 철회·연결 해제·삭제·탈퇴와 같은 잠금 참여). PIN 실패는 커밋 후 HTTP 오류로 변환해 카운터가 롤백되지 않게 함
- 페어링은 Redis 해시 키·10분 TTL·원자적 단회 소비(DB 등록 실패 시 새 코드 발급). 키 접두사 `student-device:pairing:`·`student-device:attempt:`. 원문 PIN·코드·토큰은 로그에 남기지 않음
- PIN은 PBKDF2-HMAC-SHA256(600,000회, 16바이트 salt), 기기 토큰은 256비트 난수·SHA-256 해시. 단독 로그인 성공은 다른 탭에 부모 세션 변경을 알리지 않음
- 마이그레이션: 처음 V10을 썼으나 V12가 먼저 적용된 DB에서 Flyway가 `Detected resolved migration not applied to database: 10`으로 거부 → 미병합이던 #58 파일만 V13으로 변경(outOfOrder·repair 사용 안 함). V10·V11은 결번
- 자녀 기기에 학부모 Google 세션이 남지 않도록 기기 등록은 코드·QR을 기본으로 함
- 미정: PIN 잠금·새 기기 등록 시 학부모 알림(알림 유형 추가와 함께 결정)
