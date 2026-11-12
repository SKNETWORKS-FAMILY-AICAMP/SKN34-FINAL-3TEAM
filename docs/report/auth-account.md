# 인증·계정

계약은 [API 명세](../design/api-spec.md) 3.11·5.1·5.3·5.4·5.6과 [core OpenAPI](../../contracts/openapi/core-service.yaml), 저장 구조는 [ERD](../design/erd.md) 3.1.

## 1. Google OAuth·토큰 (#36)

- Google Authorization Code + PKCE S256을 core 콜백에서 처리. `authorize` → Google → `callback`(refresh 쿠키 설정) → web `/oauth/complete` → `POST /auth/refresh` → `GET /me`. 서비스 토큰은 URL에 넣지 않음
- access JWT는 HS256(Spring Security JOSE), 부모·학생 기본 15분, 프론트 메모리에만 보관. refresh는 256비트 난수·SHA-256 해시 저장, HttpOnly·Secure·SameSite=Strict, 부모·관리자 세션은 최초 발급부터 7일(회전으로 연장 안 함). 학생은 refresh 없음
- Google ID 토큰은 JWKS 서명·iss·aud·exp·nonce 검증. OAuth 상태 쿠키는 HttpOnly·SameSite=Lax·10분. web origin과 `/api`는 동일 origin, 쿠키 API는 Origin·`X-Requested-With` 검사
- 계정 식별은 `(oauth_provider, oauth_subject)`. 이메일은 연락 정보이며 기존 이메일 계정과 자동 연결하지 않음(같은 이메일은 `ACCOUNT_EXISTS`). 기존 계정에 가짜 subject를 채우지 않고 비밀번호 컬럼은 nullable로 보존·사용 중단. 신규 계정은 PARENT, 관리자는 운영자가 role·권한 지정(관리자 ID·비밀번호 로그인은 11장 `admin_credential`, 학부모 ID·비밀번호 가입·로그인은 12장 `parent_credential`)
- 매 요청에서 DB의 세션·계정·연결 상태 확인. 로그아웃·역할 전환 후 이전 access 즉시 거부. refresh는 원자적 1회 소비, 재사용 시 해당 세션 폐기(다른 기기 유지)
- 같은 브라우저의 탭은 역할을 공유하며 Web Locks로 refresh·전환·로그아웃을 직렬화하고 BroadcastChannel로 알림. 학생 전환을 받은 탭은 토큰·캐시를 지우고 학생 진입 화면으로. 보호자 복귀는 보호자 비밀번호(7장) 또는 다시 로그인(Google 또는 아이디, 12장)
- 키: JWT 키는 base64 32바이트 이상 난수, core에만 Secret으로 주입. 단일 HS256 키라 교체 시 기존 access·OAuth 상태 토큰이 무효화됨. Google 키가 없으면 로그인 시작은 명시적 503(가짜 로그인 없음)
- Google SSO가 보호자 본인 재확인을 보장하지는 않음(추가 본인 확인은 별도 제품 정책)

## 2. 동의·자녀 등록 (#37)

- 저장 형식은 웹 `Consent`의 `{documentId,version,agreed}` 유지. TERMS·PRIVACY는 계정, GUARDIAN은 자녀 범위. 자녀 등록은 프로필과 GUARDIAN 동의를 한 트랜잭션
- P20(#388, [기획 3.2](planning.md#32-커뮤니티-p20)): 선택 동의 문서 `COMMUNITY`(자녀 범위) 추가. 없으면 학생 커뮤니티 공개를 켤 수 없고, 철회 시 공개 설정을 끄고 공유물을 비공개로 바꾼다
- 현재 문서는 KST 시행일 이하에서 `effective_from`·`created_at`·`id` 내림차순 첫 문서(버전 문자열 비교 안 함). 문서 미게시는 503, 앱이 본문을 생성하지 않음. 1.0 문서 3종은 core V25가 게시(#235, 8장)
- 선택 거부도 `agreed=false`로 기록. 같은 선택 재전송은 행 재사용, 변경·철회 후 재동의는 새 행. 판정은 같은 문서·주체·자녀의 최신 행만. 현재 문서·권한 조회는 MyBatis 캐시를 쓰지 않음
- 보호자 계정 행 `FOR UPDATE`로 동의 변경·철회·등록을 직렬화, LINKED 연결 수로 최대 3명. 나이를 계산해 P01(전원 14세 미만 간주)을 바꾸지 않음
- 필터 예외: 동의 전에는 `GET /me`, `GET·POST /me/consents`, 철회만 허용(PATCH /me로 동의 검사를 건너뛰지 못하게 메서드까지 제한). `/children/{UUID}` 경로는 현재 scope 검사
- 기록 유무: `hasRecords` boolean|null, `recordState` AVAILABLE·UNAVAILABLE·CONSENT_REQUIRED. learning 전용 `exists` API(사용자 승인으로 #27보다 먼저 최소 구현)를 호출하며, 공급자 장애·계약 위반은 null·UNAVAILABLE(기록 없음으로 바꾸지 않음), 동의 없는 자녀는 원격 조회 없이 CONSENT_REQUIRED
- 기록 조회 경로는 guardianship → learning `LearningRecordService` → `LearningRecordClient` → `LearningClient`(학생 전용 `LearningProxyService`와 분리, `learning-json` 서킷 공유). 최대 3명을 virtual thread로 병렬 조회하고 컨텍스트는 finally에서 정리
- `plan`은 이 API에서 만들지 않음(상품 연동 후속)

## 3. 계정 관리·재인증·삭제·탈퇴 (#45)

- 재인증 토큰 5분·세션/작업/자녀 결합·1회 사용(사용자 결정). Google 계정 확인은 비밀번호·MFA 재입력을 보장하지 않음
- 재인증 사용 절차(#58 당시 PIN 변경 예. PIN 설정은 15절에서 재인증을 제거했고, 같은 절차를 탈퇴·보호자 비밀번호·자녀 해제 등에 쓴다)
  1. 원래 세션에서 `POST /me/reauth {"purpose":"PIN_CHANGE","childId":...}`(Origin·`X-Requested-With` 필요)
  2. 응답 `authorizationUrl`을 새 창에서 열어 Google 확인. Google 콘솔에 `<webOrigin>/api/v1/auth/google/reauth/callback` 등록 필요. callback은 VERIFIED 안내만, 로그인·refresh는 바꾸지 않음
     - #425: callback은 JSON 대신 안내 HTML. 같은 출처 `BroadcastChannel('sagomungchi-reauth')`로 challengeId만 알리고 창을 닫음(닫히지 않으면 안내 문구). 팝업 `opener=null` 유지 때문에 postMessage는 쓰지 않음. CSP nonce·`no-store`·`no-referrer`·`nosniff`. 실패도 스크립트 없는 안내 HTML(403)
  3. 원래 세션에서 `{"challengeId":...}`로 `reauthToken` 1회 수령(메모리 보관). 웹은 `useReauthReturn`(`frontend/web/src/data/reauthReturn.ts`)으로 채널 알림을 받으면 자동 수령, 수동 "완료 확인"은 대체 수단
  4. 변경 요청의 `X-Reauth-Token`. 서비스는 권한 검사 후 같은 트랜잭션에서 `ReauthenticationService.consume(...)`(MANDATORY, 실패 시 소비도 롤백)
- 탈퇴 자격 조회용 최소 payment service·repository(결제 쓰기 없음), P09 core 대화·근거 삭제용 conversation service. 기능 간 접근은 service 경유
- 재인증·서비스별 완료 행은 V9. 상태 조회 영수증(`statusToken`)은 탈퇴 후 로그인 차단과 상태 조회를 함께 제공하기 위한 최소 계약
- RECORDS 삭제 이후 학습 재개는 하위 서비스 삭제 표식 수명주기가 정해지지 않아 자동 허용하지 않음(완료 후에도 `DELETION_REQUESTED`로 차단 유지)
- 동의 철회·연결 해제 뒤에도 삭제·연결 해제·삭제 상태 조회는 보호자 등록 이력과 재인증으로 접근 가능(일반 자녀 경로의 scope 검사는 유지)
- P09 개정(#386~#389): 자녀 기록 삭제·탈퇴 시 커뮤니티 공유물·남긴 반응·포인트 원장·잔액·해금·착용 정보·`mission_daily_usage`도 함께 파기. #289 이관 수락 시 공유물은 새 보호자 `COMMUNITY` 동의 전까지 비공개

## 4. 학생 기기·PIN 로그인 (P01 개정, #58)

### 배경과 결정

기존 P01은 학부모 로그인 → 자녀 선택 → `POST /auth/student-sessions`로만 학생 세션을 만들어 학부모 부재 시 자녀 단독 학습이 불가능했음. 참고한 서비스: Khan Academy(자녀 아이디·비밀번호), Seesaw·ClassDojo(코드·QR), Epic(프로필 + PIN), Google Family Link(기기 추가 시 학부모 승인).

| 방식 | 판단 |
|---|---|
| 자녀 아이디·비밀번호 | 초3~6이 관리하기 어렵고 유출 시 어느 기기에서나 사용 가능 → 비채택 |
| QR·코드 단독 | 코드가 소지형 자격증명이라 종이·사진 유출에 취약 → 기기 등록 수단으로만 |
| PIN 단독 | 4~6자리는 추측 공격에 약함 → 비채택 |
| **학부모 승인 기기 등록 + 자녀 PIN** | 기기(소지)와 PIN(지식) 2요소, 자녀가 이메일·OTP를 관리하지 않음 → **채택** |

### 구현 결정

- 기기는 등록일부터 고정 90일(사용 시 연장 없음), PIN 5회 실패 잠금, 학생 access TTL은 `AUTH_STUDENT_ACCESS_TTL`
- 부모 세션을 바꾸지 않고 학생 전용 `auth_session`을 만듦(refresh 없음). 기기 해제는 다음 PIN 로그인부터 차단, 기존 access는 만료까지 유효
- account가 기기·페어링·학생 토큰, guardianship이 PIN 저장·잠금과 자녀 권한을 소유. 계정 행 → 기기·학생 행 순서로 잠금. PIN 실패는 커밋 후 HTTP 오류로 변환해 카운터가 롤백되지 않게 함
- 페어링은 Redis 해시 키·10분 TTL·원자적 단회 소비. 키 접두사 `student-device:pairing:`·`student-device:attempt:`. 원문 PIN·코드·토큰은 로그에 남기지 않음
- PIN은 PBKDF2-HMAC-SHA256(600,000회, 16바이트 salt), 기기 토큰은 256비트 난수·SHA-256 해시
- 마이그레이션 V13(V10·V11은 결번): V12가 먼저 적용된 DB에서 Flyway가 V10을 거부해 미병합 파일만 번호 변경(outOfOrder·repair 사용 안 함)
- 자녀 기기에 학부모 Google 세션이 남지 않도록 기기 등록은 코드·QR이 기본
- 미정: PIN 잠금·새 기기 등록 시 학부모 알림

## 5. 학생 종료와 보호자 로그인 전환 (#196)

- 문제: 학생 홈의 보호자 전환 버튼이 공통 `/auth/logout`을 호출해 같은 브라우저의 보호자 세션도 폐기
- 결정: 학생 세션만 종료하고 보호자 세션 유지, 학생 탭에서는 보호자 인증 요구
- 웹은 학생 모드에서만 `POST /auth/student/logout` 호출. core는 학생 Bearer를 검증하고 해당 auth_session만 폐기, 보호자 refresh·기기 쿠키는 읽거나 만료시키지 않음
- 누락·위조·만료 Bearer 401, 다른 역할·출처 403. 저장소·전송 장애를 성공 종료로 표시하지 않음
- 비밀정보 없는 sessionStorage 표식으로 보호자 로그인 대기 상태를 탭에 유지(새로고침에도 보호자 쿠키 자동 복원 차단)
- 다른 탭의 보호자 로그인 알림은 활성 학생 탭 또는 보호자 로그인 대기 탭의 역할을 바꾸지 않음

## 6. 탈퇴 전 자녀 이관 (#289)

#275의 다중 학부모 연결 전제를 바로잡은 후속. 상대방 동의와 재인증을 거쳐 현재 연결을 새 보호자로 교체하며, DB에서도 자녀당 현재 보호자 한 명만 허용.

### 구조와 결정

- V26: 이관 요청 테이블, `guardianship.transferred_at`, 학생당 LINKED 한 행 고유 인덱스, 재인증 목적 확장. 기존 중복 LINKED 데이터는 자동 삭제하지 않고 migration 실패로 별도 검토
- 신규 대상 조회·요청·수락 API는 `APP_GUARDIAN_TRANSFER_ENABLED=true`, 화면은 `VITE_GUARDIAN_TRANSFER_ENABLED=true`일 때만(기본 false). 플래그는 DB 되돌리기 수단이 아님
- **회복 경로(#307)**: 본인의 기존 요청 조회·취소·거절(GET 목록, POST 개별 취소·거절·보낸 요청 일괄 취소)과 `/parent/transfers` 관리 경로는 플래그·필수 동의와 관계없이 유지. 대기 요청이 탈퇴·해제·삭제를 막는데 동의가 빠졌거나 플래그가 꺼지면 정리할 수 없던 문제 때문. PENDING 행을 자동 정리하지 않고 취소만으로 탈퇴·삭제가 실행되지 않음
- 계정 → 학생 → 이관 요청 잠금 순서와 한 트랜잭션으로 수락·취소·3명 한도 직렬화. 동의·재인증 실패 시 연결 교체도 롤백
- 이전 학부모의 이관된 연결은 삭제 권한·탈퇴 삭제 대상에서 제외. 선택한 상담(분석 대화)만 새 학부모 소유로 바꿈(체크박스 기본 해제)
- 구독·결제·환불은 명의를 바꾸지 않음. 대상 자녀의 활성 구독·진행 중 결제·환불이 없어야 요청·수락 가능. 진행 중 분석이 있으면 수락 보류
- 학생 공개 설정과 리포트 기록은 유지, 학부모 전역 리포트 설정은 이전하지 않음
- 수락 시 기존 학생 세션과 기기 해제(새 학부모가 기기 재등록)
- 이관은 자녀별이며 수락 후 자동 탈퇴하지 않음. 자녀가 없는 학부모도 받은 요청 확인·수락 가능
- 재인증: `CHILD_TRANSFER`는 대상 자녀와 결합, `TRANSFER_ACCEPT`는 자녀 없는 계정 범위. 오류 코드 6종·경로 7개는 api-spec 1.3·2.1·5.17

### 격리 로컬 체험

```powershell
.\scripts\start_transfer_local.ps1     # 재시작 시 -SkipBuild
.\scripts\start_transfer_web.ps1       # 최초에는 frontend/web에서 npm ci
.\scripts\stop_transfer_local.ps1      # guardian-transfer-289 컨테이너와 이 저장소의 5195 웹만 중지
```

- 별도 Compose 프로젝트·볼륨·네트워크, loopback 포트만(API 18095, 웹 `http://127.0.0.1:5195`, PostgreSQL 15495, Google stub 18096). 기존 개발 웹과 origin을 달리해 refresh 쿠키가 섞이지 않음
- scoring을 함께 실행하고 호스트 포트는 공개하지 않음([infra 3.3](infra.md#33-교차-확인이관content_3-설정-전달-312))
- 합성 계정: `sender@example.test`(자녀 2명), `receiver@example.test`(없음), `full@example.test`(3명, 한도 확인), `spare@example.test`. 수동 체험 데이터 준비는 `zz-demo-seed.spec.ts`
- 테스트: `GuardianTransferIntegrationTest`, `frontend/web/tests/transfer-local/`(`npx playwright test -c playwright.transfer-local.config.ts`)
- MSW 목업 체험: `VITE_API_MOCK=true`, `VITE_GUARDIAN_TRANSFER_ENABLED=true`, `VITE_SHARED_DEVICE_MOCK=false`. 탭 메모리 기반이라 같은 탭에서 계정을 바꿔 확인

### 남은 일

- 이관 대기 요청의 만료, 수신 알림 채널, 운영자 복구 절차는 미구현(이관 페이지에서 5초 간격 갱신). 완료된 이관을 되돌리는 사용자 기능 없음
- V26은 운영 RDS에 사전 점검 위반 0건으로 적용됨(2026-11-04). prod values에는 이관 기능 설정이 없어 기능은 꺼져 있음
- 아이디·비밀번호 학부모는 이관을 받는 쪽이 될 수 없음(받는 학부모 조회가 Google 이메일 기준)
- 외부 Google·결제 연동과 서비스 전체 삭제 완료를 잇는 실서버 E2E는 미실시

## 7. 동석 학습 뒤 보호자 비밀번호로 학부모 화면 복귀

팀 피드백: "이 자녀로 학습 시작" 뒤 학부모 화면으로 돌아가려면 Google 로그인을 다시 해야 했음. 새 창 방식은 같은 기기에서 아이가 학부모 탭으로 넘어갈 수 있어, 담당자 결정으로 **학부모 세션은 잠근 채 유지하고 보호자 비밀번호(숫자 4~6자리)만 입력하면 돌아오는 방식** 채택.

- 동석 진입 `POST /auth/student-sessions`는 학부모 세션을 `locked_at`·version 증가로 잠그고 `parent_session_id`를 가진 별도 학생 세션을 만듦. 학부모 refresh 쿠키는 지우지 않음. 잠긴 동안 `/auth/refresh`는 토큰을 소비하지 않고 401 `PARENT_SESSION_LOCKED`
- 복귀 `POST /auth/parent-unlock {password}`: 성공하면 잠금 해제·version 증가, 그 세션에서 들어간 학생 세션 폐기, refresh 회전. 실패 횟수는 오류 전에 커밋, 5회째부터 423 `GUARDIAN_PASSWORD_LOCKED`, 미설정은 409 `GUARDIAN_PASSWORD_NOT_SET`(이때는 다시 로그인, 새 로그인은 잠긴 세션과 학생 세션을 함께 폐기)
- 보호자 비밀번호는 학생 PIN과 같은 규칙·PBKDF2 해시·5회 잠금. `GET·PUT /me/guardian-password`, 설정·변경은 재인증 `GUARDIAN_PASSWORD` 목적 1회 소비. 저장은 core V24 `guardian_password`(계정당 1행), 탈퇴 요청 시 삭제
- 웹: 이 탭에서 동석 진입했으면 로그인 화면 위에 "학부모 화면으로 돌아가기"를 띄움. 잠금 여부만 sessionStorage에 두고 토큰은 저장하지 않음
- 한계: 아이가 보호자 비밀번호를 알면 학부모 화면에 들어갈 수 있음. 다른 탭의 학부모 화면은 잠금 동안 쓸 수 없음. 보호자 비밀번호 입력은 동석 진입한 탭에서만 보임

## 8. 동의 문서 3종 출처와 시드 (#235)

`consent_document`에 게시 문서가 없어 새 환경에서 가입·자녀 등록이 503으로 막혔다. 문구를 지어내지 않고 공식 원문·표준 양식을 서비스에 맞게 고쳐 등록했다.

- core V25 `seed_consent_documents`: TERMS·PRIVACY·GUARDIAN 각 1행, 고정 UUID `00000000-0000-4000-8000-00000235000{1,2,3}`, `version='1.0'`, `required=true`, `effective_from=2026-11-03`
- 운영자는 가상 정보 "사고뭉치 프로젝트팀(SKN34 3팀)", 연락처 `sagomungchi-team@example.com`(사용자 결정)
- 세 문서 맨 위에 "교육 과정 시연용, 법률 검토 없음". 공식 원문에 근거가 없어 새로 쓴 문장은 `[초안]` 표시(TERMS 제2조④·제6조⑤·제7조① 단서·제13조①후단~④·제15조② 후단·제16조④·제19조①, PRIVACY 3.②·8.8))
- **개정 규칙**: 게시한 행은 고치지 않음. 같은 kind에 새 `version`·새 `effective_from` 행을 추가. 새 필수 문서가 게시되면 기존 회원도 다시 동의. LLM 제공자·수탁자·보관 리전이 바뀌어도 PRIVACY·GUARDIAN 새 버전 필요
- 개정 이력: TERMS·PRIVACY 1.1(V39, 2026-11-09, 아이디·비밀번호 가입 반영), COMMUNITY 1.0(V31, 선택 동의)

### 출처 (확인일 2026-11-03)

| kind | 원문 | 가져온 부분 |
|---|---|---|
| TERMS | 공정거래위원회 [전자상거래 표준약관 제10023호](https://www.ftc.go.kr/www/selectBbsNttView.do?key=202&bordCd=201&nttSn=11139) | 목적·정의·약관 개정·서비스 제공과 중단·가입과 탈퇴·계약·환급·청약철회·의무·분쟁 조항. "몰"→운영자, 배송·마일리지 조항 삭제 |
| TERMS | 공정거래위원회 [온라인게임 표준약관 제10069호](https://www.ftc.go.kr/www/selectBbsNttView.do?key=202&bordCd=201&nttSn=11197) | 무료·유료서비스 정의, 청약철회 방법, 탈퇴 시 본인 확인 |
| TERMS | [전자상거래법](https://www.law.go.kr/법령/전자상거래등에서의소비자보호에관한법률) 제17조 | 디지털콘텐츠 청약철회 제한과 표시·시험 사용 의무(P14 환불 근거) |
| PRIVACY | 개인정보보호위원회 [개인정보 처리방침 작성지침](https://www.pipc.go.kr/np/cop/bbs/selectBoardArticle.do?bbsId=BS217&mCode=D010030000&nttId=12018) (2026. 4.) | 기재 사항 목록과 작성 예시, 생성형 AI 기재 고려사항. 항목·보유기간은 P09·ERD, 결제 기록 5년 |
| PRIVACY·GUARDIAN | OpenAI [Services Agreement](https://openai.com/policies/services-agreement/), [API Your data](https://developers.openai.com/api/docs/guides/your-data) | 계약 상대방, API 데이터 기본 학습 미사용, 오남용 감시 기록 최대 30일 |
| PRIVACY | [AWS Contracting Party](https://aws.amazon.com/legal/aws-contracting-party/), [토스페이먼츠](https://www.tosspayments.com/) | 계약 상대방·법인명 |
| GUARDIAN | 개인정보보호위원회 [아동·청소년 개인정보 보호 안내서](https://www.pipc.go.kr/np/cop/bbs/selectBoardArticle.do?bbsId=BS217&mCode=D010030000&nttId=10896), [알기쉬운 개인정보 처리 동의 안내서](https://www.pipc.go.kr/np/cop/bbs/selectBoardArticle.do?bbsId=BS217&mCode=D010030000&nttId=7912) | 제22조의2 법정대리인 동의 의무, 동의서 작성 예시 |

### 한계

- 법률 검토를 받지 않음. 특히 TERMS 제15조②가 전자상거래법 제17조제6항 조치로 충분한지 미확인
- 법정대리인 동의 확인은 "로그인한 학부모가 화면에서 동의 + 기록 저장". 시행령 제17조의2의 확인 방법(문자·카드·본인인증)은 미구현
- 개인정보 처리방침은 커뮤니티 공개(다른 학생에게 별명·답변 표시)를 처리 목적에 넣는 개정이 필요
- 웹은 `content`를 `<p>`로 출력해 줄바꿈이 보이지 않음

## 9. 학생 전역 학부모 공개 설정 (#206)

- 사용자 확정: **비공개로 시작하고 학생이 공개를 선택**. core V21 `parent_sharing_enabled NOT NULL DEFAULT false`
- 학생 `GET·PUT /students/me/sharing-preferences`, 학부모 읽기 전용 `GET /children/{childId}/sharing-preferences`. 학부모·관리자의 변경은 403. no-store
- 설정 변경은 학생 행을 잠금. 분석은 parent → student → conversation 순서로 생성·기존 대화·근거·스트림 전송/완료를 재검사. 기록 API는 외부 HTTP 전후에 공개 설정 확인. 외부 요청 중 DB 트랜잭션을 열어 두지 않음
- 비공개 시 학부모 답변 목록·상세·근거와 기존 분석 대화는 `STUDENT_RECORDS_PRIVATE`. 요약·생각 유형 집계는 유지
- 커뮤니티 공개 설정(`student.community_enabled`)은 별도 설정(10절)

## 10. 커뮤니티 공개 설정과 COMMUNITY 선택 동의 (#388, P20)

P20의 core 몫(공개 설정·보호자 선택 동의·작성자 표시·신고 연결). 공유물·반응 저장과 열람 검사는 learning #386.

- 저장: V31·V32 `community_enabled`(DEFAULT false, `verify_db_schema.py` 예외 등록)·`community_updated_at`, 동의 문서 kind `COMMUNITY`(선택, `required = false`)
- **공개 판정**: `community_enabled`와 **현재 연결 보호자**의 현재 문서 `COMMUNITY` 동의가 모두 있어야 참. 동의를 학생 행에 복사하지 않고 매번 확인하므로, 이관(#289) 뒤에는 새 보호자가 동의하기 전까지 자동 비공개
- 설정 API: 학생 `GET·PUT /students/me/community-settings`. 켜기는 동의가 없으면 409 `COMMUNITY_CONSENT_REQUIRED`. 같은 값을 다시 보내도 learning 공개 상태를 다시 맞춰 이전 반영 실패를 보충
- 동의 API: `POST /me/consents`의 자녀 요청은 `GUARDIAN`·`COMMUNITY` 중 보낼 문서만 담을 수 있음. COMMUNITY만 보낼 때는 그 자녀의 현재 법정대리인 동의가 필요(없으면 400)
- 동의 거부·철회는 같은 트랜잭션에서 자녀 설정을 끄고, 동의는 켜 둔 설정의 공유물을 복원
- learning 반영: 트랜잭션 안에서 공개 여부를 정하고 **커밋 뒤** learning `PUT /internal/students/{id}/community-visibility`. 실패는 기록만 하고 사용자 요청은 성공. 대신 core 목록·반응 응답이 현재 설정·동의로 다시 걸러 비공개를 지킴
- 공유 요청: 돌아보기 저장 2xx 뒤 공개 판정이 참이면 learning `POST /internal/community/posts`를 SYSTEM으로 호출. 실패해도 학습 응답은 그대로. 반환한 `postId`로 공유 포인트 적립([core 14절](core-gateway.md#14-참여-포인트꾸미기-해금-389))
- 작성자 표시: 학생 ID를 별명·꾸미기로 바꾸고 학생 ID·반응 수를 지움. 본인 글, 지금 공개할 수 없는 작성자, 신고 숨김 공유물은 core가 제외
- 학생 삭제 확정 시 `community_enabled` false. 공유물·반응 파기는 learning이 `student.deleted`로 처리
- 한계: learning 반영 실패 시 learning 저장 상태는 다음 설정 저장·재처리 때까지 늦을 수 있음(자동 재시도 없음). COMMUNITY 문서를 개정하면 옛 판 동의는 바로 무효가 되지만 learning 공유물은 다음 반영 때까지 `VISIBLE`(core 응답에서는 빠짐)

## 11. 관리자 ID·비밀번호 로그인 (#369)

Google 로그인만 있어 관리자 계정을 만들 방법이 SQL 손작업뿐이었다. 계약은 api-spec 2.1·5.1, 저장은 ERD 3.1.1 `admin_credential`.

### 결정 (2026-11-09 사용자 확인)

- 운영 환경에서도 사용. 주소는 `/admin/login` 그대로, 사용자 화면의 관리자 링크·문구는 지움. 운영 플래그 없음(`admin_credential` 행이 없으면 아무도 로그인하지 못함)
- 관리자는 가입하지 않음. 운영자가 `scripts/admin_account_sql.py`로 행을 만듦

### 설계

- 관리자 신원은 기존 `user_account(role=ADMIN)`·`admin_permission` 그대로. 관리자 행위자 FK가 모두 `user_account(id)`를 가리키기 때문. `admin_credential`(V36)은 **비밀번호 로그인이 허용된 관리자 목록**이며 해시·실패 횟수·잠금 시각만 담음
- 로그인 ID는 `user_account.login_id`. 레거시 `user_account.password_hash`는 읽지 않음(옛 데이터가 로그인 수단으로 되살아나지 않게)
- 해시는 `PinHasher`(PBKDF2-SHA256 60만 회). 스크립트는 Python 표준 라이브러리로 같은 형식을 만들고 같은 고정 벡터를 core 테스트와 스크립트 테스트가 함께 검사
- `POST /auth/admin/login`은 정확한 web Origin·`X-Requested-With` 요구. 성공하면 Google 로그인과 같은 `startSession`
- 실패: 없는 ID·틀린 비밀번호·ADMIN이 아니거나 비활성은 모두 401 `INVALID_CREDENTIALS`(없는 ID에도 더미 해시 검사). 연속 5회째 실패에 15분 잠금(423 `ADMIN_LOGIN_LOCKED`). 실패 횟수는 오류 응답 전에 커밋
- 시간 잠금을 고른 이유: 영구 잠금은 ID를 아는 누구나 관리자를 막을 수 있음
- 성공한 로그인은 `audit_log` `ADMIN_PASSWORD_LOGIN`. 실패는 행위자 FK가 없어 남기지 않음
- 주소를 숨기는 것은 보안 수단이 아님(SPA 번들에 라우트가 모두 있음). 실제 보호는 잠금·감사·권한 검사

### 운영 사용법

```bash
# 생성·재설정(같은 ID 재실행 = 비밀번호 재설정·잠금 해제). --permissions를 빼면 기존 권한 유지
python scripts/admin_account_sql.py --login-id ops-kim --name 김운영 --permissions ALL | psql "$CORE_DB_URL"
# 비대화형: ADMIN_PASSWORD 환경 변수(12~128자). 출력에는 해시만 들어간다
# 비활성화: 자격 삭제 + 그 계정의 세션 폐기
python scripts/admin_account_sql.py --login-id ops-kim --disable | psql "$CORE_DB_URL"
```

권한 값은 `CONTENT`·`PAYMENT_VIEW`·`PAYMENT_REFUND`·`SERVICE_OPS` 또는 `ALL`. 같은 `login_id`가 ADMIN이 아니거나 비활성이면 SQL이 예외로 멈춤.

### 남은 위험

- 다중 인증(MFA)·IP 허용 목록 없음. 잠금은 ID 단위라 같은 IP에서 여러 ID를 시도하는 것은 막지 않음
- 화면설계서 캡처(C03·A00)는 변경 전 화면

## 12. 학부모 ID·비밀번호 가입·로그인 (#415)

Google 계정이 없는 사용자는 가입할 수 없었고 부하 시험 계정도 Google 계정 수만큼만 만들 수 있었다. 계약은 api-spec 1.3·2.1·5.1·5.6, 저장은 ERD 3.1.1 `parent_credential`.

### 결정 (2026-11-09 사용자 확인)

- 학부모는 Google 또는 아이디·비밀번호로 가입·로그인. 두 방법은 자동 연결하지 않고 한 계정은 한 가지 수단만
- 아이디는 영문·숫자 4~30자(소문자로 저장·비교). `@`를 쓸 수 없어 Google 계정의 `login_id`(이메일)와 겹치지 않음. 비밀번호 8~128자
- 비밀번호 찾기는 제공하지 않음(메일 발송은 별도 과제)
- 중요 작업의 본인 재확인은 비밀번호 계정이면 로그인 비밀번호 재입력. 실패 횟수는 로그인과 함께 셈

### 설계

- `parent_credential`(V38)은 `admin_credential`과 같은 모양. 검사·잠금은 `PasswordCredentialService` 하나로 공유. 탈퇴 완료 시 행 삭제, `login_id`는 `withdrawn:<id>`로 바뀌어 아이디가 풀림
- 가입 `POST /auth/parent/signup {loginId,password,name}`: 409 `LOGIN_ID_TAKEN`, 같은 IP는 Redis 고정 창으로 기본 10분 5회(`AUTH_SIGNUP_LIMIT_PER_IP`·`AUTH_SIGNUP_LIMIT_WINDOW`, 넘으면 429 `SIGNUP_RATE_LIMITED`, Redis 장애 503 `SIGNUP_UNAVAILABLE`). 성공하면 Google 신규 가입과 같은 `startSession`. `AUTH_NEW_ACCOUNT_DEMO=true`면 `is_demo`
- 로그인 `POST /auth/parent/login`: 없는 ID·틀린 비밀번호·Google 계정·관리자·비활성은 같은 401 `INVALID_CREDENTIALS`. 5회째 실패에 15분 잠금(423 `LOGIN_LOCKED`)
- 비밀번호 재확인 `POST /me/reauth/password {purpose,childId?,scope?,password}`: 맞으면 `reauth_challenge`와 `reauth_grant`를 한 번에 만들어 `{reauthToken,expiresAt}` 반환. 기존 사용처의 consume 검사는 불변. 틀리면 403 `REAUTH_PASSWORD_INVALID`, Google 계정은 409 `REAUTH_METHOD_MISMATCH`
- `GET /me`에 `authMethod`(`PASSWORD`·`GOOGLE`)와 `loginId` 추가. 비밀번호 학부모의 `email`은 null
- 별도 경로로 둔 이유: `/me/reauth`에 `password`를 더하면 Google 시작 응답과 바로 발급 응답이 한 경로에 섞임
- 시험 계정을 SQL이 아니라 공개 가입 API로 만드는 이유: 동의 문서 버전·기기 토큰 해시·PIN까지 SQL로 맞추면 깨지기 쉬움

### 부하 시험 계정

- `evaluation/load/prepare_accounts.py`가 공개 API로 계정 생성(가입 → 동의 → 자녀 3명 → 기기 등록 → PIN). 비밀번호·PIN·기기 쿠키는 저장소 밖 비밀 파일에만
- k6 `setup()`은 계정마다 빈 쿠키 저장소(`jar: new http.CookieJar()`)로 로그인. 앞 계정의 refresh 쿠키가 남으면 `startSession`이 그 세션을 폐기하기 때문
- 가입 IP 제한 값은 compose·`.env.example`·로컬 GitOps에 전달(#517). 로컬 부하 시험은 `.env`에서 늘림
- 학생 기록 비공개 기본값(`403 STUDENT_RECORDS_PRIVATE`)이 조회 오류로 섞이므로 시험 전 공개 설정 필요

### 남은 위험

- CloudFront·ALB 뒤에서는 가입 IP 한도가 엣지 단위로 묶일 수 있음(#384 때 확인)
- 로그인 상태에서 비밀번호를 바꾸는 기능·비밀번호 찾기·MFA 없음
- 아이디 존재 여부는 가입 409로 알 수 있음(일반적인 가입 UX 수준으로 수용)

## 13. 학년 자동 진급 (#432, P26)

### 결정 (2026-11-09 동섭)

- 매년 3월 1일(KST)에 자동으로 한 학년 올림
- 초6은 졸업 처리하지 않고 중1로. 학년은 중3까지 저장하되 문항·테마·채점은 초3~6뿐이라 중학생은 초6 문제와 초5~6 테마를 받음
- 새 등록은 초3~6(P03)만, 수정은 중3까지(진급이 틀렸을 때 고치기 위해)

### 설계

| 항목 | 내용 |
|---|---|
| 일정 | `GradePromotionScheduler` 3월 매일 00:05 KST, ShedLock `core-grade-promotion`. 3월 1일을 놓쳐도 그 달 안의 다음 실행이 따라잡음 |
| 대상 | 활성·비시연 학생 중 학년 3~8, 그 학년도 2월 1일(KST) 전에 학년을 정했고(`COALESCE(grade_changed_at, created_at)`) 그 학년도 진급 이력이 없는 학생 |
| 중복 방지 | `student_grade_promotion` PK `(student_id, school_year)`. 학부모가 3월에 되돌려도 다시 올리지 않음 |
| 미리 바꾼 학생 | 1~2월에 새 학년을 미리 넣은 경우를 2월 1일 기준으로 가름. 학부모 수정은 학년이 실제로 바뀔 때만 `grade_changed_at` 기록 |
| 알림 | 진급과 같은 트랜잭션에서 `GRADE_PROMOTED`(링크 `/parent/settings`). 수신 거부해도 학년은 오름 |
| 학습 전달 | `StudentLearningContext.learningGrade = min(grade, 6)` |
| 삭제 | 프로필 삭제 때 진급 이력 삭제 |

- 진행 중인 시도는 시작 때 학년으로 끝냄. 3월 1일이 주 중간인 해에는 4→5학년만 학년군이 바뀌어 그 주 주말 되돌아보기가 새 학년군 기준(그대로 둠)
- DB: core V41(`ck_student_grade` 3~9, `student.grade_changed_at`, `student_grade_promotion`)
- 한계: 중학교 과정은 별도 이슈(`StudentGrade.LEARNING_MAX`와 learning·ai 학년 범위를 함께 넓힘). 2월 이후 학년을 고친 학생은 그 해 자동 진급에서 빠짐. 실제 환경의 3월 실행은 미확인
- 테스트: `GradePromotionTest`

## 14. 웹 로그인 유지·복구 보완 (2026-11-09)

서버 정책(access 15분, 학부모·관리자 refresh 7일, 학생은 access 전용)은 그대로.

- `refreshAccessToken`이 연결 오류·잘못된 성공 응답·요청 제한을 인증 만료로 바꾸던 문제 수정. 서버가 실제 401을 확인한 경우만 세션 정리
- 로그인 전환과 토큰 갱신을 구분. 이전 로그인의 늦은 응답이 새 로그인 상태를 지우지 않고, 이전 쓰기 요청을 새 계정 토큰으로 재전송하지 않음
- 세션 복원은 진행 중 요청만 합침(완료된 Promise를 보관하지 않음). 세션 확인 장애 화면에는 재확인 버튼. OAuth 완료 실패 시 Google 코드를 재사용하지 않고 쿠키 기반 복원 재시도
- sessionStorage·BroadcastChannel 제한이 정상 토큰 발급을 로그인 실패로 바꾸지 않게 함
- 검증: `npm run test:auth`(운영 빌드 + 합성 쿠키, 웹 CI 포함). 실제 Google·kind 검증은 아님

## 15. 학생 PIN 추가 재인증 제거 (2026-11-10)

사용자 요청으로 학생 PIN 설정의 재인증을 제거했다. `StudentPinService.set`은 활성 보호자 세션 잠금·현재 자녀 권한을 검사하고 같은 트랜잭션에 감사를 기록한다. 다른 중요 작업의 재인증과 학생 PIN 로그인·기기 등록 정책은 유지한다. `PIN_CHANGE` 재인증 발급은 이전 클라이언트 호환용으로 남는다.

- 잔재 정리(#516): 부하 시험 계정 준비의 PIN_CHANGE grant 발급·`X-Reauth-Token` 전송 제거, 웹 `finishPinReauth`를 `finishGuardianReauth`로 이름 변경
- UI 범위는 [frontend 16절](frontend.md#16-리포트챗봇과-학부모-설정-동선-통합-2026-11-10)
