# 인증·계정 (#36·#37·#45·#58, P01 개정)

## 동의 문서 3종 출처와 시드 (#235, 2026-11-03)

### 배경
- `consent_document`에 게시 문서가 없어 새 환경에서 `GET /consent-documents`가 503 `CONSENT_DOCUMENTS_UNAVAILABLE`이었고 학부모 가입·자녀 등록이 막혔다. api-spec 5.3에 따라 문구를 지어내지 않고 공식 원문·표준 양식을 서비스에 맞게 고쳐 등록했다.

### 결정
- core V25 `seed_consent_documents`: TERMS·PRIVACY·GUARDIAN 각 1행, 고정 UUID `00000000-0000-4000-8000-00000235000{1,2,3}`, `version='1.0'`, `required=true`(선택 동의 항목 없음), `effective_from=2026-11-03`(커밋일), `created_at`=마이그레이션 시각(같은 날 로컬 DB에 넣은 확인용 문서보다 최신으로 선택됨).
- 운영자는 가상 정보 "사고뭉치 프로젝트팀(SKN34 3팀)", 연락처 `sagomungchi-team@example.com`, 개인정보 보호책임자는 역할(팀장)만 적었다(사용자 결정).
- 세 문서 맨 위에 "교육 과정 시연용, 법률 검토 없음" 한 줄을 둔다. 공식 원문에 근거 문구가 없어 설계 문서·구현을 바탕으로 새로 쓴 문장은 `[초안]`으로 표시하고, TERMS·PRIVACY 맨 위에 그 뜻을 한 줄로 안내한다(사용자 결정).
- **개정 규칙**: 게시한 행은 고치지 않는다. 문구를 바꾸거나 `[초안]`을 확정하면 같은 kind에 새 `version`(예: `1.1`)·새 `effective_from` 행을 추가한다. 현재 문서는 시행일·생성 시각 순으로 바뀌고, 이전 버전에 대한 동의는 새 필수 문서가 게시되면 다시 받는다(#37 동작). LLM 제공자(`LLM_PROVIDER`)·수탁자·보관 리전이 바뀌어도 PRIVACY·GUARDIAN 새 버전이 필요하다.

### 출처 (확인일 2026-11-03)

| kind | 발행 기관 | 원문 | 가져온 부분 | 서비스에 맞게 바꾼 부분 |
|---|---|---|---|---|
| TERMS | 공정거래위원회 | [전자상거래(인터넷사이버몰) 표준약관 제10023호](https://www.ftc.go.kr/www/selectBbsNttView.do?key=202&bordCd=201&nttSn=11139) (2015. 6. 26. 개정, 누리집 최신본) | 목적·정의·약관 명시와 개정·서비스 제공과 중단·회원가입과 탈퇴·통지·구매신청·계약 성립·지급방법·환급·청약철회와 효과·개인정보보호·운영자와 이용자 의무·저작권·분쟁해결·재판권 조항 | "몰"→운영자, 배송·마일리지·연결몰 조항 삭제, Google 로그인·자녀 등록·보호자 비밀번호·PIN 반영 |
| TERMS | 공정거래위원회 | [온라인게임 표준약관 제10069호](https://www.ftc.go.kr/www/selectBbsNttView.do?key=202&bordCd=201&nttSn=11197) (2024. 2. 23. 개정) | 무료·유료서비스 정의(제18조①), 청약철회 방법(제21조⑤), 탈퇴 시 본인 확인(제23조①) | - |
| TERMS | 국가법령정보센터 | [전자상거래법](https://www.law.go.kr/법령/전자상거래등에서의소비자보호에관한법률) 제17조 (시행 2026. 7. 21.) | 디지털콘텐츠 제공 개시 시 청약철회 제한(제2항제5호)과 표시·시험 사용 의무(제6항) | P14 "결제 7일 이내·프리미엄 기능 미사용 시 전액 환불"의 근거로 사용 |
| PRIVACY | 개인정보보호위원회 | [개인정보 처리방침 작성지침](https://www.pipc.go.kr/np/cop/bbs/selectBoardArticle.do?bbsId=BS217&mCode=D010030000&nttId=12018) (2026. 4. 개정) | 기재 사항 목록과 서문·처리 목적·항목·14세 미만 아동·보유기간·파기·위탁·국외이전·안전성·쿠키·권리행사·보호책임자·구제기관·변경 작성 예시, 부록1 생성형 AI 기재 고려사항 | 항목·보유기간은 P09·ERD, 결제 기록 5년(전자상거래법 시행령 제6조①2·3호) |
| PRIVACY·GUARDIAN | OpenAI | [Services Agreement](https://openai.com/policies/services-agreement/) (Effective 2026-01-01), [API Your data](https://developers.openai.com/api/docs/guides/your-data) | 계약 상대방 OpenAI OpCo, LLC(EEA·스위스 외 고객)·통지 주소, API 데이터 기본 학습 미사용, 오남용 감시 기록 최대 30일 | 기본 `LLM_PROVIDER=openai` 기준. 전송 항목은 ai-service 코드 기준(학년·답변·기록 요약·학부모 질문) |
| PRIVACY | AWS | [AWS Contracting Party](https://aws.amazon.com/legal/aws-contracting-party/) | 한국 고객 계약 상대방 Amazon Web Services Korea LLC | 서울 리전은 S3 설정 `ap-northeast-2` 기준 |
| PRIVACY·TERMS | 토스페이먼츠 | [누리집 사업자 정보](https://www.tosspayments.com/) | 법인명 토스페이먼츠 주식회사 | - |
| GUARDIAN | 개인정보보호위원회 | [아동·청소년 개인정보 보호 안내서](https://www.pipc.go.kr/np/cop/bbs/selectBoardArticle.do?bbsId=BS217&mCode=D010030000&nttId=10896) (2024. 12.) | 제22조의2 법정대리인 동의 의무, 거부·철회 시 처리 | - |
| GUARDIAN | 개인정보보호위원회 | [알기쉬운 개인정보 처리 동의 안내서](https://www.pipc.go.kr/np/cop/bbs/selectBoardArticle.do?bbsId=BS217&mCode=D010030000&nttId=7912) (2022. 3., 누리집 분류 "과거 안내서") | 동의서 작성 예시(수집·이용 내역, 거부권·불이익, 동의 확인 문구, 처리자 귀중) | 서명란 대신 화면 동의 표시, 항목·보유기간은 P01·P09 |

- `[초안]` 위치: TERMS 제2조④·제6조⑤·제7조① 단서·제13조①후단~④·제15조② 후단·제16조④·제19조①, PRIVACY 3.②·8.8). GUARDIAN은 없음.
- 쓰지 않은 원문: 개인정보 처리방침 표준(안)(2026. 2.)은 공인중개사·노인복지관·여행업 업종용이라 제외했다.

### 한계
- 법률 검토를 받지 않았다. 특히 TERMS 제15조②(디지털콘텐츠 청약철회 제한과 "무료 서비스로 미리 사용")가 전자상거래법 제17조제6항 조치로 충분한지 확인하지 않았다.
- 개인정보보호위원회 누리집에 현재 유효한 "법정대리인 동의서" 공식 양식이 없어, 형식은 과거 안내서(2022. 3.)의 작성 예시를 따랐다.
- 법정대리인 동의 확인은 "로그인한 학부모가 화면에서 동의 + 동의 기록 저장"이다. 시행령 제17조의2의 확인 방법(문자메시지·카드·본인인증 등)은 구현하지 않았다.
- 작성지침 예시의 "소비자 불만·분쟁처리 기록 3년"은 넣지 않았다. P09가 결제 거래 기록만 5년 보관하고 나머지는 탈퇴·삭제 시 즉시 파기로 정했기 때문이다.
- TERMS 제7조①은 표준약관의 "즉시 탈퇴"에 P09 단서(진행 중 구독·미처리 환불 먼저 처리)를 붙였다.
- 웹은 `content`를 `<p>`로 출력해 줄바꿈이 보이지 않는다(프론트 후속).
- 로컬·kind DB에 손으로 넣은 확인용 문서(`local-205`, "Synthetic non-binding notice")는 V25와 버전이 달라 충돌하지 않으며, 지워도 된다. 테스트·`scripts/verify_*.py`의 합성 문서는 무작위 version이라 그대로 둔다.

### 검증
- core: `ConsentChildrenTest`에 마이그레이션 직후 `GET /consent-documents`가 V25 문서 3종(고정 id·`1.0`·필수·시행일·시연 안내 첫 줄)을 반환하는 테스트 추가. 기존 합성 문서 테스트는 무작위 version이라 UK `(kind, version)` 충돌이 없다.
- GitOps local `migration.revision` v25.

## 동석 학습 뒤 보호자 비밀번호로 학부모 화면 복귀 (2026-11-03)

### 배경
- 팀 피드백: 학부모가 "이 자녀로 학습 시작"을 누르면 학부모 화면이 사라지고, 학습 뒤 학부모 화면으로 돌아가려면 Google 로그인을 다시 해야 했다. core가 학부모 세션 자체를 학생 세션으로 바꾸고 학부모 refresh 쿠키를 지웠기 때문이다(FN-ACC-05 "학부모 화면 전환 시 학부모 로그인 필요").
- 새 창으로 열어 학부모 세션을 그대로 두는 방식은 같은 기기에서 아이가 학부모 탭으로 바로 넘어갈 수 있어, 담당자 결정으로 **학부모 세션은 잠근 채 유지하고 보호자 비밀번호만 입력하면 돌아오는 방식**을 택했다. 학부모 계정은 Google 로그인만 있어 서비스 비밀번호가 없으므로, **보호자 비밀번호를 새로 정하는 방식**(숫자 4~6자리)을 택했다.

### 결정
- 동석 진입 `POST /auth/student-sessions`는 학부모 세션을 바꾸지 않고 `locked_at`·version 증가로 잠그고, `parent_session_id`를 가진 별도 학생 세션을 만든다. 학부모 refresh 쿠키는 지우지 않는다. 잠긴 동안 `/auth/refresh`는 refresh 토큰을 소비하지 않고 401 `PARENT_SESSION_LOCKED`, 기존 학부모 access는 `SESSION_CHANGED`다. 학생 세션 권한·만료(15분)는 그대로다.
- 복귀 `POST /auth/parent-unlock {password}`: refresh 쿠키의 잠긴 세션과 보호자 비밀번호를 확인한다. 성공하면 잠금 해제·version 증가, 그 세션에서 들어간 학생 세션 폐기, refresh 회전. 실패 횟수는 오류 전에 커밋하며 5회째부터 423 `GUARDIAN_PASSWORD_LOCKED`, 미설정은 409 `GUARDIAN_PASSWORD_NOT_SET`이다. 이때는 Google 로그인으로 돌아오고, 새 로그인은 이전(잠긴) 세션과 학생 세션을 함께 폐기한다.
- 보호자 비밀번호는 학생 PIN과 같은 규칙(숫자 4~6자리, 반복·연속 불가)·PBKDF2 해시·5회 잠금을 재사용한다. `GET·PUT /me/guardian-password`, 설정·변경은 기존 Google 재인증에 `GUARDIAN_PASSWORD` 목적을 추가해 1회 소비한다. 저장은 core V24 `guardian_password`(계정당 1행), 탈퇴 요청 시 삭제한다.
- 웹: 학생 화면의 "학부모 로그인" 버튼은 그대로 로그인 화면으로 가고, 이 탭에서 동석 진입했으면 로그인 화면 위에 "학부모 화면으로 돌아가기"(보호자 비밀번호 입력)를 띄운다. 잠금 여부 표시는 탭의 sessionStorage에 여부만 두며 토큰은 저장하지 않는다. 비밀번호 설정은 "자녀 기기·PIN" 화면의 "보호자 비밀번호" 카드(Google 본인 확인 → 두 번 입력)다.

### API·문서 변경
- api-spec 1.3 오류 코드 4종, 2.1 표 3행, 5.1 동석 진입·복귀 계약, 5.6 재인증 목적. OpenAPI `/auth/student-sessions`(Bearer만, Set-Cookie 없음)·`/auth/parent-unlock`·`/me/guardian-password`·`GuardianPasswordState`·재인증 목적. 기존 계약 지문 테스트(`test_admin_operations_contract.py`)에는 승인된 변경 필드만 원래 값으로 되돌리는 정규화를 추가했다.
- functional-spec FN-ACC-05, ERD 3.1.1(`auth_session.locked_at`·`parent_session_id`, `guardian_password`)·3.1.2 재인증 목적·6장 인덱스, GitOps local `migration.revision` v24.

### 검증
- core: `AccountManagementTest`에 재인증 필요·규칙 422(grant 미소비)·잠금 refresh 거부(토큰 미소비)·틀린 비밀번호 남은 횟수·성공 시 학생 세션 폐기와 refresh 쿠키 회전·5회 잠금·미설정·새 로그인 시 학생 세션 폐기 테스트. `AuthFlowIntegrationTest` 동석 진입 테스트를 잠금·쿠키 유지로 갱신.
- web: `guardianPassword.test.ts`(잠금 표시·복귀 요청 모양·남은 횟수·잠김/미설정 시 입력 닫기·MSW 전체 흐름), Playwright "동석 학습 뒤 보호자 비밀번호로 Google 로그인 없이 학부모 화면에 돌아온다"(laptop·tablet·compact).

### 한계
- 같은 기기에서 아이가 보호자 비밀번호를 알면 학부모 화면에 들어갈 수 있다. 비밀번호는 아이가 모르는 값으로 정하도록 안내한다.
- 학생 화면을 새로고침하거나 학생 access(15분)가 만료되면 기존처럼 학생 진입 화면으로 간다. 학부모는 로그인 화면의 보호자 비밀번호로 돌아올 수 있다(같은 탭).
- 다른 탭에 열려 있던 학부모 화면은 잠금 동안 쓸 수 없고 로그인·학생 진입 화면으로 이동한다. 보호자 비밀번호 입력은 동석 진입한 탭의 로그인 화면에서 보인다.
- 실서버 모드 브라우저 확인은 하지 않았다(MSW·core 통합 테스트 기준).

## 학생 전역 학부모 공개 설정 (#206, 2026-11-01)

- 사용자 확정: **비공개로 시작하고 학생이 공개를 선택**합니다. core V21은 기존/신규 학생 모두 `parent_sharing_enabled NOT NULL DEFAULT false`를 적용합니다. `StudentLearningContext`의 기존 조회 계층을 재사용하며, 공개 상태를 추정하는 프론트 전용 필드는 만들지 않습니다.
- 학생 `GET·PUT /students/me/sharing-preferences`, 학부모 읽기 전용 `GET /children/{childId}/sharing-preferences`를 제공합니다. 세션의 단일 학생·활성 보호 관계·역할·범위를 확인하며 nullable 본문은 400, 학부모/관리자의 학생 설정 변경은 403입니다. no-store 응답입니다.
- 학생 설정 변경은 학생 행을 잠급니다. 분석은 기존 parent → student → conversation 순서로 생성·기존 대화·근거·스트림 전송/완료를 재검사합니다. 기록 API는 외부 HTTP 전후에 공개 설정을 확인하며, 리포트는 외부 HTTP를 마친 뒤 별도 parent → student 트랜잭션에서 최종 공개/상품 권한을 확인합니다. 외부 요청 중 DB 트랜잭션을 열어 두지 않습니다.
- 비공개 시 학부모 답변 목록·상세·근거와 기존 분석 대화는 `STUDENT_RECORDS_PRIVATE`로 차단합니다. 요약·생각 유형 집계는 유지합니다. 부모 화면에는 상태만 안내하며 변경 스위치를 제공하지 않습니다.
- 단위/HTTP 설정·권한 회귀와 원문 경계 테스트, MSW 공개→비공개 재차단 및 브라우저 저장 흐름을 추가했습니다. Docker 복구 후 실제 PostgreSQL 기본값·설정 영속화·리포트 조회 중 비공개 전환·파일 서명 중 비공개 전환까지 검증했습니다. core 관련 단위·HTTP·DB 회귀 64건이 통과했습니다. 운영 반영/병합 완료를 의미하지 않습니다.

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
- 현재 문서는 KST 시행일 이하에서 `effective_from`·`created_at`·`id` 내림차순 첫 문서(버전 문자열 비교 안 함). 문서 미게시는 503, 앱이 본문을 생성하지 않음. 1.0 문서 3종은 core V25가 게시(#235, 위 절)
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
