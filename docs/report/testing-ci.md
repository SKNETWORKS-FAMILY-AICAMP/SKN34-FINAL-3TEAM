# 테스트·CI·점검 원장

## 1. 계약 검사 CI (#143·#237)

DB 파일을 바꾸지 않은 API·이벤트 계약 변경도 CI에서 검사하도록 계약 검사를 `ci-contracts.yml`로 분리. 기존 테스트·검증 스크립트를 재사용하고 제품 API·DB 스키마는 변경하지 않음.

| 구성 | 동작 |
|---|---|
| `_web.yml` | npm ci → lint → **npm test** → build |
| `ci-contracts.yml` | PR·develop/main push·수동 실행. 계약·backend·web·scripts·설계 문서·Compose·RabbitMQ 정의 변경을 검사 |
| 계약 CI의 저장소 검사 | Python 3.12, PyYAML 6.0.3, jsonschema 4.26.0으로 `python -O -m unittest discover -s scripts/tests -v` |
| 계약 CI의 실제 응답 검사 | JDK21에서 core 통합 테스트 8개 클래스로 산출물을 생성하고 validator 7개 실행 |
| `ci-db-schema.yml` | DB 검증기 회귀와 실제 마이그레이션·ERD 대조 유지. API 계약용 jsonschema 별도 설치와 전체 계약 테스트 중복 실행 제거 |
| `ci-report-service.yml` | PR·push 모두 `contracts/openapi/report-service.yaml` 변경도 report CI 실행 |

- 계약 테스트가 컨트롤러 외 서비스·DTO·웹 어댑터도 읽으므로 `backend/**`, `frontend/web/**` 전체를 경로 필터에 포함. 보고서(`docs/report/**`)만 수정하면 CI 미실행. 경로 필터는 PR 전체 diff 기준
- `_spring.yml`의 서비스 전체 테스트·빌드·이미지 빌드는 유지. 계약 CI의 선택 테스트는 산출물 생성에 필요한 범위이며 core 전체 회귀를 대체하지 않음
- `clean test`로 이전 빌드 JSON 재사용 방지, 산출물 누락·스키마 불일치는 실패. continue-on-error·Docker 미존재 시 skip 없음. `test_contract_artifact_presence.py`가 산출물이 없는 임시 디렉터리에서 일곱 검증기 모두 실패하는지 검사

| 검사 | 실제 응답 생성 테스트 | 산출물 (core-service/build 기준) |
|---|---|---|
| 리포트 | ReportMessagingTest, ReportHttpTest | contracts/report-*.json |
| 알림 | NotificationIntegrationTest | generated-contracts/notification-*.json |
| 문의 | SupportIntegrationTest | generated-contracts/support-*.json |
| 결제 | PaymentIntegrationTest | generated-contracts/payment-*.json |
| 관리자 리포트 재처리 | AdminReportRetryIntegrationTest | admin-retry-contracts/report-retry-*.json |
| 분석 대화 | ConversationIntegrationTest | generated-contracts/analysis.json |
| 관리자 운영 | AdminOperationsIntegrationTest | generated-contracts/admin-operations.json |

- 분석 대화는 다섯 결과 유형(LLM, VERIFICATION_FAILED, AI_UNAVAILABLE, NO_RECORD, UNSUPPORTED) 테스트에서 core가 반환한 최종 SSE result를 내보냄(AI 대역 응답을 복사하지 않음). 관리자 운영은 인증된 MockMvc 요청으로 overview·jobs·job·queues·audit-logs 응답 생성, 큐 조회는 Testcontainers RabbitMQ 관리 API. 파일에 인증 헤더·토큰 미저장
- PostgreSQL·Redis·RabbitMQ와 core 코드는 실제, AI·learning·외부 결제는 테스트 대역. 운영 외부 연동 E2E로 해석하지 않음

### 로컬 재현

- Docker 실행 필수(core·learning·report 통합 테스트는 Testcontainers 사용, 합성 데이터·테스트 자격 증명)
- 웹: Node 22로 `npm ci`, `npm run lint`, `npm test`, `npm run build`
- 계약: `.github/workflows/ci-contracts.yml`의 테스트 8개 클래스와 검증 단계 7개를 그대로 실행. 분석·관리자 운영 검증기는 위 표의 JSON 경로를 인자로 받음
- Windows는 Python `.venv-contracts/Scripts/python.exe`, `gradlew.bat`, JAVA_HOME JDK21. Docker 컨테이너에서 Gradle을 실행하면 Docker 소켓 접근 설정 필요

## 2. 실서버 브라우저 E2E와 외부 스텁 (#246)

- 기존 브라우저 테스트(`playwright.config.ts`)는 전부 MSW 목업 대상이라 실제 서비스 연동 미검증(NFR-QA-01) → 외부 의존(Google OAuth·LLM·토스페이먼츠)을 `infrastructure/stubs/` 대역으로 바꾼 compose 스택에서 핵심 흐름 E2E
- 담당자 결정(2026-11-02)
  - 로그인 대체: Google 스텁(token·JWKS) + Playwright의 authorize 리다이렉트 재작성. 테스트 전용 로그인 API 미추가
  - CI 실행: 수동·E2E 구성 파일 변경 PR. 매일 03:00 KST schedule(GitHub는 기본 브랜치 main의 워크플로만 예약 실행, `e2e.yml`은 main에 반영됨)
  - 토스: core에 PG 주소 설정 추가, toss-stub, 결제 승인 E2E 1건
- 시나리오 추가 결정(#625, 2026-11-13)
  - 요일: 서버 날짜 고정 기능을 넣지 않고 KST 일요일에는 주간 테마 스펙을 건너뜀(무료 일요일 `THEME_DAY_CLOSED`). 월요일 문제는 월~토 열려 있어 나머지 요일은 같은 흐름
  - 지난 회차가 필요한 추억 앨범 회차 상세·기념 액자는 지난주 기록 준비 방식(#624)에 맞춰 후속으로 추가(#624는 core·learning 시험 시계 이미지 + 공개 API로 확정, [infra 9.7.1](infra.md#971-결정-담당자-확인-2026-11-13)), 추억 검색·설명은 웹 화면(#567) 구현 뒤 추가. 이번에는 내 방 → 빈 앨범까지
  - 주간 리포트 대표 답변 설명은 실제 카드 표시까지: M2 점수는 scoring-stub(실제 scoring은 S3 모델 아티팩트 필요), 설명 sLLM은 llm-stub
- 실제 Google·토스·LLM 키와 GitHub secrets 미사용. 모든 값은 `infrastructure/stubs/e2e.env`의 합성 값

### 설정 변경 (공개 API 계약 변경 없음)

| 대상 | 변경 | 기본값·영향 |
|---|---|---|
| core `app.payment.toss-base-url` (`TOSS_API_BASE_URL`) | `TossClient` 요청 주소를 설정값으로 | 기본 `https://api.tosspayments.com`. `test_sk_`·`test_gsk_` 키 검사 유지 |
| core `app.auth.google-token-url`·`google-jwk-url` | 코드 변경 없음. 완화 바인딩 환경 변수 `APP_AUTH_GOOGLETOKENURL`·`APP_AUTH_GOOGLEJWKURL`를 E2E 오버레이에서만 지정 | 기본 Google 주소 |
| ai-service | 코드 변경 없음. 기존 `OPENAI_BASE_URL`로 llm-stub 지정 | E2E 오버레이에서 실제 키 변수를 빈 값으로 고정 |
| ai-service M2·설명(#625) | 코드 변경 없음. 기존 `SCORING_URL`=scoring-stub, `M2_CROSS_CHECK_ENABLED=true`, `EXPLANATION_BASE_URL`=llm-stub을 E2E 오버레이에서만 지정 | 기본값(교차 확인 꺼짐·설명 주소 없음) 유지. E2E 오버레이 위에 얹는 보호자 이전 로컬 스택(`compose.transfer-local.yaml`)은 세 값과 기동 의존을 되돌려 실제 scoring-service·기본값을 유지(`scripts/tests/test_runtime_config.py`) |

### 스텁 (`infrastructure/stubs/<target>-stub/`)

Node 22 alpine 표준 라이브러리만 사용(RS256 서명 필요). 각 이미지에 `GET /health`.

| 스텁 | 구현 경로 | 동작 |
|---|---|---|
| google-stub | `GET /jwks`, `POST /token` | 기동 시 RSA 키 생성. `code`는 base64url JSON `{sub,email,name,nonce,challenge,redirectUri}`라 상태 없음. client_id·secret·redirect_uri·PKCE(S256) 검증 후 `iss=https://accounts.google.com`, `aud=GOOGLE_CLIENT_ID`, `email_verified=true` id_token 발급 |
| llm-stub | `POST /v1/chat/completions` | `response_format.json_schema.name`으로 응답 선택. `Extraction`은 프롬프트의 모든 `elementId`를 답변 원문 인용·FOUND로 반환(정답 판정), `GeneratedQuestion`·`GeneratedNarrative`(숫자 없음)·`Classification`·`TemplateProposal` 고정 응답, `stream:true`는 SSE 조각·사용량·`[DONE]`(리포트 설명 sLLM 평문도 이 응답, #625). 그 외 이름은 400 |
| scoring-stub(#625) | `POST /internal/m2/scores`, `POST /internal/m1/checks` | ai `ScoringClient`의 `M2Scores` 형식 고정 점수. 서술은 `hol` 4·나머지 8항목 5(평균이 `M2_NARRATIVE_HIGH` 이상이라 정답 판정과 불일치 보류 없음), 논술은 3항목 3. M1은 `{active:false}` |
| toss-stub | confirm, `orders/{orderId}` 조회, billing 발급·청구, cancel, transactions | 메모리 저장. Basic 키는 `test_` 접두사만 허용, 정기결제 키면 `TOSS_TEST_BILLING_MID`, 아니면 `TOSS_TEST_MID`. 조회 실패는 404 `NOT_FOUND_PAYMENT` |

### 스택·시드

- `compose.e2e.yaml`: `compose.yaml`·`compose.minio.yaml`과 함께 지정하는 오버레이. 스텁 4종, core·ai 환경 변수 재정의, report-api·worker는 버킷 생성 후 기동. scoring-service는 S3 모델 아티팩트가 있어야 기동해 제외하고 scoring-stub으로 대체(#625)
- `e2e-seed`: 마이그레이션 직후 `frontend/web/tests/e2e/seed/core.sql`(core_db), `backend/learning-service/db/seed/demo_missions.sql`·`frontend/web/tests/e2e/seed/learning.sql`(learning_db) 실행
- `core.sql`(재실행 결과 동일): 필수 동의 문서 3종, 무료(`PAYMENT_FREE_PRODUCT_ID`)·유료(`E2E 프리미엄`, 14,900원) 상품, ADMIN 계정(Google sub `e2e-admin`)과 관리자 권한 4종, 꾸미기 아이템 `E2E_HAT`(모자 10포인트, 미션 학습 완료 1회로 해금, #625)
- `learning.sql`(#625): 11번 미션(초5 서술) 기준표에 M2 입력 핵심어(`keywords`)만 채움. ai는 핵심어가 있어야 M2를 부르고 데모 시드는 비어 있음(V9 기존 행 NULL). 저장소 데모 시드는 그대로
- 주간 테마(#625): 시드 없이 테스트가 관리자 경로로 이번 주 초3 테마를 작성 → 검토 요청 → 게시(`tests/e2e/support/theme.ts`, 월=2번 서술·화~금=1·3·4·5번). 같은 학년·주 게시본이 있으면 재사용
- 설명 모델 활성(#625): ai는 core 모델 레지스트리의 `MODEL` `report-explanation`이 `explanation/grade-5/narrative`에 활성일 때만 설명 sLLM을 부름(아니면 `{active:false}` → "설명 미포함"). 테스트가 관리자 경로로 합성 평가 기록과 함께 등록 → 활성화(`support/admin.ts`, `model.version.activated` 이벤트로 ai 반영). 이미 활성이면 재사용
- 관리자 API 호출은 시드 관리자로 로그인한 화면이 보내는 요청의 `Authorization` 헤더를 재사용(토큰이 메모리에만 있음, 테스트 전용 로그인 API 미추가 결정 유지)
- 리포트: cron이 일일 00:00 전날·주간 월요일 00:00 지난주 기간이라 테스트가 `report_job`(QUEUED)과 `report.generate` outbox 이벤트를 오늘(일일)·이번 주(주간) 기간으로 직접 삽입(`tests/e2e/support/db.ts` `queueReport`). `narrativeEnabled`는 `ReportJobService`가 계산할 값(주간 && 이용권 `reportNarrative`)을 테스트가 맞춰 넣음. 이후 OutboxRelay → RabbitMQ → report-worker → 완료 이벤트는 실제 경로

### 테스트 (`frontend/web/tests/e2e/`, `npm run test:e2e`)

`playwright.e2e.config.ts` 별도 파일(webServer가 설정 파일 단위라 MSW 설정과 분리). 웹은 `http://127.0.0.1:5272` Vite dev(`VITE_API_MOCK=false`)로 `/api`를 core에 프록시.

| 스펙 | 흐름 |
|---|---|
| `admin-home.spec.ts` | 관리자 Google 로그인 → `/admin/home` 운영 현황·실제 집계 기간·학습 시도·처리 현황 |
| `learning-journey.spec.ts` 1 | 학부모 로그인·동의·자녀 등록 → 학습 시작 → 미션 작성·제출 → 정답 판정·되묻기 → 돌아보기 저장 → 내 공책 한 줄 '마무리' → 답 공개 설정 |
| `learning-journey.spec.ts` 2 | 같은 학부모 재로그인 → 대시보드 학습 기록·원문 보기 → 이번 주 리포트 생성 → 상세 기간·수치 |
| `payment.spec.ts` | 유료 이용권 선택 → 주문 생성 → `/payment/success` → core confirm이 toss-stub 호출 → 결제 완료 |
| `weekly-theme.spec.ts`(#625) | 관리자 테마 게시 → 학생 홈 테마 제목·요일 칩 → 월요일 문제 열기(월요일 "오늘 문제 풀기", 화~토 "아직 안 푼 문제 · 월요일") → 시작 이야기 화면(`/student/theme/intro`) → 미션 안내 → 답·정답 판정 → 되묻기 답 → 마무리·돌아보기 → 홈 월요일 칩 ✓ → 내 포인트 잔액·"미션 학습 완료" 내역 → 꾸미기 페이지 "옷 입히기" 탭 E2E 모자 해금(잔액 차감) → "이대로 입기". KST 일요일 skip |
| `community.spec.ts`(#625) | 학부모 커뮤니티 선택 동의 → 학생 친구 공개 켜기 → 같은 미션 마무리(공유) → 동의 없는 다른 학생은 마무리 전 "아직 마무리한 미션이 없어요"·마무리 뒤 "친구 생각"에서 미션 골라 답 열람 → 반응 "이유가 잘 보여" → 작성자 "내가 나눈 생각 보기"에 받은 반응 수 |
| `student-room.spec.ts`(#625) | 학생 메뉴 "내 방" → "○○의 미니룸" 가구 이름표 6개 → "추억 앨범 열기" → 기념 액자 0개·안내 칸(이번 주 테마가 있으면 "이번 주 액자 자리") → "← 내 방" |
| `parent-reports.spec.ts`(#625) | 설명 모델 등록·활성화 → 초5 자녀·프리미엄 결제 → 학생 학부모 공개 → 11번 서술 답·되묻기 → 일일 리포트 상세 "그날 푼 문제" 되묻기·마지막 답·원문 근거 → 주간 리포트 상세 "대표 답변 설명" 카드(미션 제목·AI 관찰) |

- 학생 토큰은 메모리에만 있어 학생 단계는 화면 내 이동만 사용. 학생 모드 진입 시 학부모 refresh 쿠키가 지워져 학부모 단계는 새 컨텍스트에서 재로그인
- 토스 결제 위젯 JS·Google 폰트 차단, 외부 네트워크 호출 없음
- 학생 기기 등록·PIN 로그인·서술 미션 풀이·결제는 `support/student.ts`·`support/payment.ts` 공용 도우미(#625에서 기존 스펙의 같은 단계를 옮김). 추가 문제는 홈 "더 풀어 보기"로 연다(테마 없는 학년의 홈에도 있음, #648)
- 가입 도우미는 동의 문서 제목을 고정하지 않고 화면이 조회한 `/api/v1/consent-documents` 응답의 TERMS·PRIVACY·GUARDIAN 3종 제목으로 체크박스 선택(V25 실제 문서가 합성 시드보다 최신이라 선택되는 문서가 바뀜, PR #300)

### 실행

```sh
COMPOSE="docker compose -p sagomungchi-e2e --env-file infrastructure/stubs/e2e.env -f compose.yaml -f compose.minio.yaml -f compose.e2e.yaml"
$COMPOSE up -d --build --wait core-service learning-service ai-service report-api report-worker
cd frontend/web && npm ci && npx playwright install chromium && npm run test:e2e
$COMPOSE down -v
```

- `--env-file` 지정으로 개발자 `.env` 미사용
- 인프라 포트(5432·5672·6379·8080 등) 고정이라 기본 compose 스택과 동시 실행 불가
- postgres 컨테이너 이름이 다르면 `E2E_POSTGRES_CONTAINER` 지정

검증(로컬, 2026-11-02·11-03): 4개 시나리오 통과, 실행 후 DB에서 `llm_usage` 모델 `e2e-stub`·되묻기 출처 `LLM`, `payment` `APPROVED`·구독 `ACTIVE`, `report_job` COMPLETED·report_id 연결 확인.

검증(로컬 Docker compose 새 스택 `down -v` 뒤 `up --build`, Windows 11·Docker 29.6, 2026-11-13 금요일 KST, #625): 기존 4개 + 신규 4개 스펙 9개 테스트 통과(2.0분). 실행 후 DB 확인: core `student_look_unlock` `E2E_HAT`(원장 연결)·`reward_point_ledger` `MISSION_COMPLETED` 10·`COMMUNITY_POSTED` 5·`REACTION_GIVEN` 1·`UNLOCK` -10, `model_version` `report-explanation` ACTIVE, learning `weekly_theme` PUBLISHED(주 2026-11-09)·`community_reaction` `CLEAR_REASON`·M2 점수가 저장된 판정 2건(핵심어를 넣은 11번 답·되묻기 답), report `report_item` `EXPLANATION` 1건. 수행 구분(NFR-QA-04): 모의 응답(LLM·M2·설명 sLLM·Google·토스 대역)만 사용, PG 테스트 거래·실제 API·배포 확인은 미수행, 원격 CI(`e2e.yml`)는 아직 미실행. 금요일 실행이라 월요일 문제 당일 풀이(+5)는 확인하지 않음. 같은 브랜치를 develop(#649 M2 경계·#639~641 풀이 화면 접근성 포함)에 맞춘 뒤 2026-11-15 일요일 KST 새 스택에서 다시 실행: 8개 통과·`weekly-theme.spec.ts` 1개는 일요일 skip(사유 표시), report `EXPLANATION` 1건·`community_reaction` `CLEAR_REASON` 재확인. 이 실행에서 커뮤니티 동의 상태 문구와 다른 동의 목록의 "불러오고 있습니다." status가 함께 잡히는 경우가 있어 현재 상태 문구(`현재 …`)만 보도록 선택자를 좁힘

검증(#648 새 학생 화면에 맞춤, 로컬 Docker 29.8 compose `e2e.yml`과 같은 명령, 2026-11-16 월요일 KST): `weekly-theme`·`community`·`learning-journey`·`student-room`·`parent-reports`와 `support/student.ts`를 새 화면(홈 요일 칩·시작 이야기 화면·꾸미기 페이지·내 공책 한 줄·친구 생각 미션 버튼·미니룸)에 맞춤([frontend](frontend.md) "실서버 E2E를 새 학생 화면에 맞춤"). 새 스택(`down -v` 뒤 `up --build`, 테마 없는 상태에서 시작) 9개 통과(6.0분), 같은 스택 재실행(초3 테마 있음 → 홈 "더 풀어 보기"·앨범 "이번 주 액자 자리" 경로) 9개 통과(4.6분). 실행 뒤 core `reward_point_ledger`: `MISSION_COMPLETED` 10×10·`THEME_ON_TIME` 5×2(월요일 당일 풀이 첫 확인)·`COMMUNITY_POSTED` 5×2·`REACTION_GIVEN` 1×2·`UNLOCK` -10×2. 중간 실행 1회에서 답 입력 직후 자동 저장과 "다 썼어요" 클릭이 겹쳐 제출되지 않은 채 멈춰, 도우미가 자동 저장 완료("저장했어요")를 본 뒤 보내게 함(화면도 저장 중에 누르면 저장 뒤 보내게 고침, [frontend](frontend.md) 같은 절). 수행 구분은 위와 같음(대역만, 원격 CI 미실행)

### 미검증 범위

- 학생 기기 등록·PIN 로그인, Google 재인증 팝업
- 토스 결제 위젯 JS, 정기결제 등록·갱신·실패·해지·환불 경로(toss-stub 경로만 구현)
- 분석 대화 스트리밍·리포트 템플릿 제안(llm-stub 응답만 구현)
- 지난주 기간 cron 스케줄링 자체
- kind `<target>-stub` Service·NetworkPolicy egress
- (#625) 지난 회차가 있는 추억 앨범·회차 상세·기념 액자·추억의 벽 걸기(#624), 추억 검색·설명(#567)
- (#625) 무료 일요일 닫힘·토요일 되돌아보기·월~금 개근·주간 완주 포인트, 테마 엔딩·정답 고르기(관리자 작성 본문에 이야기 정답 구조 미포함)
- (#625) 실제 M2 모델 점수·설명 sLLM 문장 품질(대역 고정 응답), 커뮤니티 신고·숨김

## 3. core 계정 HTTP 경로 테스트 (#136)

[점검 원장](#5-develop-종합-점검-원장-16회차)의 "통합 테스트 없음" 공백 중 core 계정·기기·Google 시작 경로 7묶음에 `account/AccountHttpTest.kt`(MockMvc로 실제 `PublicAuthFilter`·컨트롤러·서비스·DB 경유) 추가.

- 기반은 `PostgresRepositoryTest` 상속(메시징 없는 테스트, [db-dev-guide](db-dev-guide.md) 5장). 처음 `IntegrationTestSupport`로 만들었을 때 그 DB 연결이 100/100에 닿아 다른 통합 테스트가 `too many clients`로 실패
- 학생 403은 `PublicAuthFilter`(역할별 경로)와 서비스 `AccountManagementService.lock` 두 겹이고 둘 다 403 `FORBIDDEN`이라, 응답만으로는 필터 규칙 누락을 알 수 없음 → MockMvc `handler` 없음(컨트롤러 미도달)까지 확인
- 재인증 실패는 `X-Reauth-Token`을 쓰는 연결 해제 경로에만 해당. PIN 설정은 2026-11-10 재인증 제거([auth-account 15절](auth-account.md#15-학생-pin-추가-재인증-제거-2026-11-10)) 뒤 규칙 위반 422만 검사

| 경로 | 확인한 성공·실패 |
|---|---|
| `GET /me/withdrawal/precheck` | 200·`no-store`, 5칸(`pendingPayments` 포함), 구독·미처리 환불·확인 중 결제가 있으면 `canWithdraw=false`(409 아님). 401, 학생 403 |
| `GET /children/{id}/deletion-impact` | 200·`no-store`, UNLINK·PROFILE·RECORDS. 다른 보호자 403 `CHILD_NOT_LINKED` |
| `DELETE /children/{id}/link` | 204, 감사 `CHILD_UNLINKED`. 재인증 누락·다른 목적 토큰 403 `REAUTH_REQUIRED` |
| `POST /student-devices/pairings` | 8자리 코드로 실제 기기 등록 201. 빈 목록·중복·4명 400 |
| `GET`·`DELETE /student-devices` | 해제 기기 제외·토큰 해시 없음, 재해제 204·감사 1건. 다른 보호자 404 |
| `PUT /children/{id}/pin` | 204, 감사 `STUDENT_PIN_CHANGED`. `1234` 422 (재인증 없음, 2026-11-10) |
| `GET /auth/google/authorize` | 302, `Referrer-Policy: no-referrer`, 상태 쿠키 `sagomungchi_oauth`(HttpOnly·SameSite=Lax·600초), 쿠키·URL state 일치. 설정 없음 503 `OAUTH_UNAVAILABLE` |

남은 위험: `IntegrationTestSupport`는 연결 풀 상한이 없어 설정이 다른 클래스마다 캐시된 Spring 컨텍스트가 연결 10개(Hikari 기본값)를 계속 점유. develop 원본만으로 최대 99/100이라 이 기반을 쓰는 클래스가 하나 더 생기면 `too many clients` 위험(공통 기반 조정은 core 담당 판단).

## 4. GitOps chart CI (#238)

`.github/workflows/ci-gitops.yml`. `infrastructure/gitops/**`, migration 이미지가 복사하는 core·learning `db/migration/**`, 워크플로 파일 변경 PR과 `develop`·`main` push에서 실행.

| job | 검사 | 실패 조건 |
|---|---|---|
| charts | Helm v4.3.1·kubeconform v0.8.0을 공식 배포본에서 받아 SHA256 대조 | 체크섬 불일치 |
| charts | `environments/<env>/*.yaml`마다 `helm lint --strict`와 `helm template` | 렌더 실패, `values.schema.json` 위반, lint 경고 |
| charts | `environments/prod/*.json`(#509): 저장소 chart values는 local과 같은 규칙으로 lint·template, `images/<release>.json`(#857)이 있으면 함께 넘겨 PreSync migration Job·NetworkPolicy까지 렌더, ApplicationSet 목록과 images 파일 이름 일치 확인. `kind`가 있는 manifest(NodePool·NetworkPolicy·ExternalSecret)는 그대로 kubeconform 대상 | 렌더 실패, 스키마 위반 |
| charts | 렌더 결과와 `argocd/`·`policies/` 원본 manifest의 kubeconform `-strict` | 스키마 위반, 정의되지 않은 필드 |
| migrations | `migrations/*.Dockerfile`을 저장소 루트 context로 `docker build`(push 없음) | 빌드 실패 |

- 렌더 조합은 Argo CD 정의를 따름. 환경 파일 이름과 같은 chart가 있으면(`observability`·`platform-data`) 그 chart, 나머지는 파일 이름을 릴리스 이름으로 `app-service` chart에. namespace는 app-service `app`, observability `observability`, platform-data `platform`. 새 chart 추가 시 워크플로의 namespace 대응도 추가(빠지면 CI 오류). 의존 chart가 있으면 `helm dependency build` 선행(현재 없음)
- prod의 외부 chart values(`external-secrets`·`aws-load-balancer-controller`·`karpenter`·`argocd`)는 chart를 받아야 해서 검사하지 않음. 새 외부 chart values를 추가하면 워크플로 건너뛰기 목록에도 추가(빠지면 app-service로 렌더돼 CI 오류)
- `app-service` 기본 values는 `image.repository`가 빈 문자열이라 단독 lint 시 스키마 `minLength` 실패. 환경별 이미지를 강제하는 설계이므로 실제 배포 조합으로만 lint

### CRD 처리

kubeconform은 기본 Kubernetes 스키마 → 공개 CRD 카탈로그 순으로 찾고, 둘 다 없는 종류만 `-ignore-missing-schemas`로 건너뜀(건너뛴 `Kind/이름 (파일)` 목록·경고 annotation 출력). CRD 스키마를 저장소에 복사하는 방식은 업그레이드마다 갱신이 필요해 제외.

| 항목 | 고정 값 | 근거 |
|---|---|---|
| Kubernetes 스키마 | [yannh/kubernetes-json-schema](https://github.com/yannh/kubernetes-json-schema) `e0c72a1`의 `v1.35.8-standalone-strict` | kind 노드 이미지 v1.35.8과 같은 버전 |
| CRD 스키마 | [datreeio/CRDs-catalog](https://github.com/datreeio/CRDs-catalog) `27233a5` | KEDA 2.21.0 CRD 갱신(2026-11-01) 포함, Argo CD `Application`·`ApplicationSet` 포함 |

KEDA chart 버전을 올리면 카탈로그 커밋도 같은 버전 이후로 갱신. 카탈로그의 Argo CD `Application`·`ApplicationSet`·`AppProject` 스키마는 prod Argo CD v3.5.7(argo-cd chart 10.11.7) CRD와 필드 경로가 모두 같음을 확인(2026-11-20, #855, [infra 9.18.1](infra.md#9181-argo-cd-설치-값과-진입점-855-2026-11-20)). Argo CD를 올리면 같은 대조를 다시 한다. 로컬 v3.5.5와는 대조하지 않았다.

### 로컬 실행

Linux 셸(WSL 또는 컨테이너)에서 같은 버전의 두 도구 설치 후 저장소 루트에서 실행(워크플로 run 블록과 같은 명령).

```bash
cd infrastructure/gitops
out=/tmp/gitops-rendered; mkdir -p "$out/local"
for values in environments/local/*.yaml; do
  release="$(basename "$values" .yaml)"
  if [ -d "charts/$release" ]; then chart="$release"; else chart=app-service; fi
  case "$chart" in app-service) ns=app ;; observability) ns=observability ;; platform-data) ns=platform ;; esac
  helm lint --strict "charts/$chart" --namespace "$ns" -f "$values"
  helm template "$release" "charts/$chart" --namespace "$ns" --kube-version 1.35.8 -f "$values" > "$out/local/$release.yaml"
done
kubeconform -strict -summary -kubernetes-version 1.35.8 \
  -schema-location 'https://raw.githubusercontent.com/yannh/kubernetes-json-schema/e0c72a1bc5f409d1685c0e1323460c8a98cd7459/{{.NormalizedKubernetesVersion}}-standalone{{.StrictSuffix}}/{{.ResourceKind}}{{.KindSuffix}}.json' \
  -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/27233a506de0085e71c7f9702597806a7f95eb24/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json' \
  -ignore-missing-schemas "$out" argocd policies
```

migration 이미지는 `docker build -f infrastructure/gitops/migrations/core.Dockerfile .`처럼 확인.

### 검사하지 않는 항목

- Argo CD가 받는 외부 chart(KEDA 2.21.0, metrics-server 3.14.0) 렌더링
- 실제 클러스터 적용, Argo sync, admission webhook·NetworkPolicy 동작(스키마 검사는 필드 형식만)
- migration 이미지 실행·게시(#186)
- values 오타는 렌더되는 경로에서만 드러남. 스키마가 있는 `app-service`만 values 단계에서 차단

검증(2026-11-02): local 환경 파일 8개 lint·template 통과, 15개 파일 76개 리소스 Valid 76·Skipped 0. 타입 오류(`replicaCount: "one"`)는 helm lint, 스키마 없는 chart 필드 오타는 kubeconform이 실패 처리, 카탈로그에 없는 CRD는 건너뜀 목록으로 출력됨을 확인.

## 5. develop 종합 점검 원장 (1~6회차)

develop 종합 검증 회차별 결함 원장. 회차별 실행 결과 표와 재판정 표는 git 이력(삭제된 `docs/report/audit.md`) 참고. 번호는 결함 B, 코드↔문서 C, 문서 간 D, 아키텍처 A, 테스트 공백 T.

| 회차 | 기준 | 범위 | 번호 |
|---|---|---|---|
| 1 | develop `c608f52` | 코드 통합·코드↔문서·테스트·CI | B1~B17, C1~C15, D1~D14 |
| 2 | develop `40a2501` (PR #92) | 설계 문서 정합성 | D1~D11(결정 항목), #93~#97 |
| 3 | develop `640e0a2` | PR 16개 병합 후 + 아키텍처 원칙 | B18~B21, C16~C21, D15~D16, A1~A7 |
| 4 | develop `2db122c` | PR 73커밋 병합 후 | B22~B27, C22~C34, D17~D21, A8~A15 |
| 5 | develop `92d522b` | PR 28개 병합 후 | B28~B35, C35~C44, D22~D25, A16~A19 |
| 6 | develop `b97cc67` | PR 22개 병합 후 | B36~B43, C45~C59, D26~D29, A20~A21, T1 |

### 5.1 코드 결함·설정 (B)

B1~B43 모두 처리: 해결(1·4·5회차 직접 수정, #93·#97·#128·#129·#131~#135·#163·#164·#276·#277·#289·#305~#307·#310·#312·#313·#318 등), 결함 아님(B25·B26·B33), 재현 안 됨(B27, #218 이후). 항목별 내용·처리는 git 이력(이 절의 2026-11-20 이전 판).

### 5.2 코드↔문서 (C)

C1~C59 모두 해결(1·3·4·5회차, #308~#311·#315~#317).

### 5.3 문서 간 (D)

D1~D29 모두 해결·반영·삭제(1·2회차 결정 반영, #165·#245·#308·#309). D16·D26 "이슈별 절이 번호 체계 밖"은 2026-11-20 문서 정리에서 다시 맞춤.

### 5.4 아키텍처 (A)·테스트 공백 (T)

A1~A21 모두 해결(#69·#166~#171·#192·#204·#249~#256·#278~#280·#314·#632), T1 해결(#317, 대상 차이는 학생 전용 유지로 결정 #632).

### 5.5 남은 공백

- CI: `tests/*-browser.mjs`·JDK 21 `verify_*`는 수동. `e2e.yml` 야간 실행 결과 미확인
- 요구사항 차이: FN-AGT-12 수학 점검 예시 질문은 요구사항을 실제 동작(고정 5문항, 기록 유무로 일괄 판단)에 맞추고 M1 활성 후 추가로 정리(#632, 2026-11-13 결정)
- 로컬 실행 주의: core·learning이 Gradle 캐시 볼륨 하나를 함께 쓰면 잠금 충돌로 빌드가 시작 전 실패

## 6. 아키텍처 원칙 점검 기준

[아키텍처](../design/architecture.md) 1.1~1.6·2.1~2.4·3장·4장 원칙을 HEAD 코드와 대조한다. core·learning은 패키지 import를 레이어(`controller`·`consumer`·`scheduler` / `service`·`facade` / `domain` / `repository`·`client`·`messaging`)로 분류해 전수 검사하고, 나머지는 클라이언트·트랜잭션·설정을 grep으로 확인한다. 다른 구현은 A 번호로 원장에 기록한다.

| 원칙 | 확인 방법·현재 결과 |
|---|---|
| 서비스 DB 직접 접근 금지(1.1) | 각 서비스 DB URL은 자기 DB만. 다른 서비스 데이터는 내부 API·이벤트로만 |
| core만 공개 API·JWT 검증(1.1·2.3) | 웹 `apiClient`는 core `/api/v1`만. 내부 호출은 내부 토큰 + 컨텍스트 헤더 |
| 컨텍스트 전파(2.3) | ai `clients/base.py`가 `X-User-*`·`X-Student-Scope`를 learning 호출에 부착. report 소비자는 `SYSTEM` + 이벤트 학생 범위 |
| 레이어 단방향·기능 간 service 경유(2.2) | controller→repository 0건, 다른 기능 repository 참조 0건, Presentation의 `@Transactional` 0건. 예외는 기존 결정(`_common/messaging` #278, support의 learning client #46) |
| 트랜잭션 안 외부 호출 금지(2.2) | 리포트 복구 `NOT_SUPPORTED`, 알림 Redis 발행 `AFTER_COMMIT`, learning 피드백은 `FeedbackFacade` 트랜잭션 밖 AI 호출, report Outbox는 advisory lock·짧은 트랜잭션 |
| 재시도 계층(1.3) | 서비스 간 호출은 재시도 없음(예외: #878 learning→ai 추억 검색 질의 변환 1회, ai 쪽 그 LLM 호출은 재시도 0회라 증폭 없음). ai 내부에는 일반 LLM 재시도(1회, 1초), 되묻기 유출 재생성(1회), 리포트 상세 설명의 조건부 재생성(공유 마감 75초 안에서 1회, #850)이 있다. 모든 클라이언트에 타임아웃 |
| Outbox·멱등 소비(1.6) | Outbox는 core·report만, learning은 발행 없음, ai·scoring은 best-effort. 리스너는 수동 ACK·`RetryingConsumer` |
| readiness(4.4) | core·learning `readinessState,db,rabbit`, ai RabbitMQ, scoring RabbitMQ·모델, report DB. 하위 서비스 호출 없음 |
| 스케줄 중복 방지(1.5) | 정기·복구 스케줄러는 ShedLock 또는 레플리카 안전 조건부 UPDATE·DELETE |
| 프론트엔드(3장) | access token 메모리 보관, 서버 상태는 TanStack Query만, `domain`이 `data`·`presentation`을 참조하지 않음, presentation의 `apiFetch`·mocks 참조 0건 |


## 7. report PDF 실행 환경 설치 재시도 (#539)

report CI의 `Prepare report PDF runtime`에서 Ubuntu 패키지 미러 DNS 일시 장애가 나면 테스트 실행 전 설치가 실패했다. report 전용 `backend/report-service/scripts/install_pdf_runtime.sh`를 CI와 Docker 이미지 빌드에서 함께 사용한다. 다른 Python 서비스의 단계와 제품 API는 변경하지 않는다.

- OS 의존성(`playwright install-deps chromium`) → 한글 글꼴(`fonts-noto-cjk`) → Chromium(`playwright install chromium`) 순서로 분리한다. 실패한 단계만 최대 3회 실행하고 사이에 5초·10초 대기한다. 마지막 종료 코드를 그대로 반환해 지속 장애를 성공으로 숨기지 않는다.
- Playwright가 내부에서 실행하는 apt에도 적용되도록 `/etc/apt/apt.conf.d/80report-pdf-runtime`에 파일 다운로드 재시도 3회, HTTP·HTTPS 대기 30초, update 일부 실패도 오류로 처리하는 설정을 둔다. 단계 재시도와 APT 자체 파일 재시도는 서로 다른 계층이다.
- Chromium 다운로드 연결 대기는 45초, CI 설치 단계 전체 상한은 5분이다. 상한 초과나 최종 실패면 해당 테스트 작업은 실패한다. develop의 CI 병렬화에 따라 이미지 빌드는 별도 작업으로 실행되며, 이미지 안에서도 같은 설치 스크립트가 실패하면 빌드가 실패한다.
- CI의 일반 사용자에서는 필요한 apt 작업만 sudo, Docker 빌드에서는 root로 실행한다. Chromium 경로와 최종 이미지 사용자(uid 10001)는 유지한다.
- 같은 설치 실패가 이미지 빌드에서도 발생할 수 있으므로 Dockerfile도 적용했다. 새 액션·Python 패키지·외부 미러·기본 이미지 교체는 없다.

근거: [Playwright 브라우저·의존성 분리 설치](https://playwright.dev/python/docs/browsers), [APT 재시도 설정](https://manpages.debian.org/trixie/apt/apt.conf.5.en.html).

검증: `scripts/tests/test_report_pdf_runtime.py`는 실제 POSIX 스크립트에 격리된 명령을 연결해 정상 설치, 각 단계 일시·지속 실패, 후속 단계 차단, 종료 코드, sudo 경로를 확인한다. 테스트에서는 호스트 패키지를 설치하지 않는다. report 원격 CI 통과는 PR 생성 후 해당 커밋의 실행 결과로 별도 확인한다.

2026-11-12 로컬 검증(develop `0565ef3e` 기준):

- report 전체 pytest 426개 통과, Ruff check·format 통과. 기존 Starlette/httpx 사용 중단 예정 경고 1개가 있다.
- 설치 장애 회귀 테스트 8개: Windows Git Bash와 Linux POSIX 셸에서 통과.
- 실제 Docker 이미지 빌드 및 uid 10001·네트워크 차단 상태에서 합성 리포트 PDF·HTML·Markdown 생성 통과. Noto Sans CJK KR 글꼴 검색 확인. 별도 `fc-match` 실행에서는 쓰기 가능한 글꼴 캐시 디렉터리가 없다는 경고가 있었으나 글꼴 조회와 PDF 생성은 성공했다.
- 재사용 워크플로에서 report 전용 설치 단계를 제외한 구성이 기존과 동일함을 비교 확인.
- GitHub report CI는 PR 생성 후 검증할 항목이며, 위 로컬 결과로 원격 통과를 대신하지 않는다.

develop `7ef72985` 병합 시 PR #544의 테스트·이미지 빌드 병렬화, 이미지 캐시, 작업별 15분 제한과 report 설치 단계 5분 제한을 유지했다. report 설치 명령만 재시도 스크립트 호출로 대체한다.
병합 후 Linux 설치 장애 테스트 8개와 report 렌더링 테스트 11개가 통과했다. YAML 구조 비교로 최신 develop 대비 report 설치 명령 외 변경이 없음을 확인했다.

## 8. 비밀 정보 스캔 CI (#810)

`.github/workflows/ci-secrets.yml`. NFR-SEC-04 검증. 경로 필터 없이 모든 PR, `develop`·`main` push, 수동 실행에서 돈다. 결정과 걸렸을 때 대응은 [infra 4.3](infra.md#43-비밀-정보-스캔-ci-810).

| job | 검사 | 실패 조건 |
|---|---|---|
| gitleaks | Gitleaks 8.30.1 linux x64 공식 배포본을 받아 SHA256·버전 대조 | 체크섬·버전 불일치 |
| gitleaks | 루트 `.gitleaks.toml`(기본 규칙 + 검토한 합성 값 예외)로 `gitleaks git`. PR은 `base..head`, push는 `before..after`, 수동 실행은 전체 이력. `--redact=100` | 비밀 후보 1건 이상 |

- 체크아웃은 `fetch-depth: 0`, PR은 병합 커밋이 아닌 PR 머리 커밋 기준
- 실행 요약(`GITHUB_STEP_SUMMARY`)에 검사 범위와 커밋 수를 남긴다

## 9. 비기능 요구사항 검증 근거표 (#811)

[기능명세 3장](../design/functional-spec.md#3-비기능-명세) NFR 40개를 검증 방법이 실제로 실행됐는지 기준으로 한 표에 모은다(NFR-QA-01·QA-04). 결과·수치는 각 근거 절의 실제 실행 기록만 옮기고, 실행하지 않은 것은 "점검 예정"으로 둔다. 점검이 끝나면 해당 줄만 고친다.

### 9.1 읽는 법

- 기준: 2026-11-20, develop `a836e3e8`
- 상태: **충족** / **미충족**(사유) / **범위 밖**(결정 근거) / **점검 예정**(날짜·이슈, 9.4). 결과 칸의 "참고"는 같은 검증을 다른 환경에서 먼저 한 기록이며 상태 판정에 쓰지 않는다
- 검증 구분(NFR-QA-04)
  - 모의: 테스트 대역(LLM·결제·하위 서비스 스텁, MSW). DB·브로커는 Testcontainers 실제
  - PG: 토스페이먼츠 테스트 거래
  - 실API: 실제 OpenAI·SageMaker 호출
  - CI: 원격 GitHub Actions 실행(9.2)
  - 배포: 실환경 확인. kind(로컬 팀 클러스터), A(AWS A 계정 운영 데모), B(AWS B 계정 시연, #783)
- 테스트 경로 약어: core·learning = `backend/<서비스>-service/src/test/kotlin/com/sagomungchi/<core|learning>/`, ai·report = `backend/<서비스>-service/tests/`, web = `frontend/web/tests/`

### 9.2 CI·E2E 기준 실행 (2026-11-20 확인)

| 워크플로 | 대상 | 실행 ID | 결과 |
|---|---|---|---|
| ci-core-service·ci-learning-service·ci-ai-service·ci-report-service·ci-web·ci-contracts·ci-secrets | develop push `8034ca25` (11/20 14:07 KST) | 44678892265·44678892352·44678892303·44678892222·44678892251·44678892304·44678892089 | 모두 success |
| ci-contracts·ci-secrets | develop push `a836e3e8` (11/20 15:14 KST) | 44686359539·44686359553 | success |
| e2e(야간 schedule, 대역 스택) | develop `3a07ddc4` (11/20 09:06 KST) | 44643094168 | 9 passed (1.9분) |

- 표의 "CI"는 위 실행에서 해당 테스트가 통과했다는 뜻이다. 테스트 이름은 근거 칸에 적는다
- `e2e.yml`은 모의(Google·LLM·M2·설명 sLLM·토스 대역)만 쓴다. 실제 API·PG·배포 확인으로 해석하지 않는다(2절)

### 9.3 근거표

| NFR | 기준(요약) | 검증 구분 | 결과 | 근거 위치 | 날짜 | 상태 |
|---|---|---|---|---|---|---|
| SEC-01 | 만 14세 미만 법정대리인 동의 없이 자녀 등록 불가 | 모의·CI | 동의 전 `GET /children`·`PATCH /me` 403 `CONSENT_REQUIRED`, 동의 항목 누락 `POST /children` 400, 필수 문서가 바뀌면 기존 동의 무효. 동의한 적 없는 계정의 `POST /children`을 직접 보내는 시험은 없음 | core `consent/ConsentChildrenTest`, [auth-account 2](auth-account.md#2-동의자녀-등록-37) | 11/20 | 충족 |
| SEC-02 | 권한 규칙을 전 경로에 적용, 친구 방 응답에 학생 ID·회차 키 없음 | 모의·CI | 다른 보호자·학생의 자녀·시도·답변·리포트·대화·알림 요청 403·404, 친구 방 응답에 `studentId`·`themeId`·`weekStart`·`postId` 없음 | core `community/FriendRoomIntegrationTest`·`learning/DashboardIntegrationTest`·`report/ReportHttpTest`·`conversation/ConversationIntegrationTest`, learning `answer/service/AnswerServiceTest`, `scripts/tests/test_friend_room_contract.py`, [retention-expansion 20](retention-expansion.md#20-친구-방-구경-core-708learning-707-2026-11-16) | 11/20 | 충족 |
| SEC-03 | 외부 AI에 최소 기록만, 이름·불필요한 식별정보 제외 | 모의 | 대역 스택에서 외부로 나간 요청 12건(판정 5·되묻기 5·리포트 서술 1·설명 1)에 학생·시도·답변 ID·닉네임·보호자 이름 0건, 메시지 안 ID 키 0건. 분석 대화·추억 3종은 대역에서 안 돌아 테스트로, 주간 테마 생성은 코드로만 확인(ai 228·report 74·learning 73 통과). 판정·되묻기·분석 대화는 답 본문 속 닉네임을 가리지 않음(설계상 가리기 대상 아님) | [10절](#10-민감정보-점검-884-2026-11-22), [evidence/issue884-sensitive-audit](evidence/issue884-sensitive-audit/) | 11/22 | 충족 |
| SEC-04 | LLM·토스 키를 저장소·배포 파일·화면에 두지 않음 | CI | Gitleaks 전체 이력 스캔에서 합성 값 3건 예외 처리 뒤 0건. 이후 모든 PR·push에서 실행(9.2 `a836e3e8` success) | [8절](#8-비밀-정보-스캔-ci-810), [infra 4.3](infra.md#43-비밀-정보-스캔-ci-810) | 11/19 | 충족 |
| SEC-05 | 비밀번호·키·카드 정보·학생 원문을 운영 로그에 미기록 | 모의 | 대역 스택 E2E 1회 서비스 로그 219줄에서 비밀 값 27종 원문·키·토큰·카드번호·비밀번호·PIN·학생 답변 원문 0건. 잠재 위험: DB 제약 오류 상세·비밀 값 `toString()` #898(해결), ai·scoring 응답 검증 오류 입력값 #899(해결) | [10절](#10-민감정보-점검-884-2026-11-22), [evidence/issue884-sensitive-audit](evidence/issue884-sensitive-audit/) | 11/22 | 충족 |
| SEC-06 | 결제수단 민감 정보는 PG 처리, 화면·로그 비노출 | 모의·CI(저장 데이터) | 저장 데이터: 빌링 자격 무작위·암호화, 결제·환불 응답과 멱등 저장 기록에 PG 키 없음. 로그(모의): core 결제 테스트 51개(승인·실패 재청구·환불·웹훅·빌링) 출력과 E2E 결제 승인 로그에 PG 키·결제 필드·카드번호 0건. trace의 토스 URL 키는 Collector에서 저장 전 가림(#900, 운영 Tempo 확인은 배포 후) | core `payment/PaymentProtectionTest`·`payment/PaymentIntegrationTest`(#168), [core-gateway 24.6](core-gateway.md#246-pg-검증운영-입력), [10절](#10-민감정보-점검-884-2026-11-22) | 11/22 | 충족 |
| SEC-07 | 가상 학생·자체 미션만, 실제 아동 정보 미수집 | 배포(kind) | 참고: kind에서 `audit-demo-data.sql`(기준 월요일 12/7 사본) 3개 DB 통과. A·B 미실행 | `infrastructure/aws/audit-demo-data.sql`, [infra 9.7.2](infra.md#972-kind-확인-실제-17201745) | 11/13 | 점검 예정 12/5 |
| SEC-08 | PIN·기기 자격은 해시, 쿠키 httpOnly·Secure·SameSite=Strict | 모의·CI | 미등록·위조·다른 자녀·만료·해제 기기는 PIN 전 거부, 동시 실패 5회 잠금·해제 후 초기화, PIN `pbkdf2-sha256` 해시, 페어링 코드는 해시만 Redis, 쿠키 HttpOnly·SameSite=Strict. 시험 설정이 `cookie-secure=false`라 Secure 속성은 미확인 | core `account/StudentDeviceAuthTest`, [auth-account 4](auth-account.md#4-학생-기기pin-로그인-p01-개정-58) | 11/20 | 충족 |
| DAT-01 | 답변·판정·되묻기·돌아보기를 덮어쓰지 않음 | 모의·CI | 보완 답변 v2·v3 제출 뒤 v1 행 그대로, 시도 버전 [1,2,3] | learning `answer/service/AnswerServiceTest`·`attempt/service/AttemptComparisonIntegrationTest` | 11/20 | 충족 |
| DAT-02 | 결과마다 미션·기준표·모델·프롬프트 버전 연결 | 모의·CI | 판정·되묻기에 모델·프롬프트 버전, 답변에 기준표 버전 저장, 공개 중 수정은 새 버전·진행 중 시도는 시작 버전 유지. "판정 뒤 기준표 변경 → 과거 판정 재조회"를 한 번에 잇는 시험은 없음 | learning `judgment/facade/FeedbackFacadeTest`·`mission/service/AdminMissionServiceTest`·`attempt/service/AttemptServiceTest`, ai `test_active_versions.py` | 11/20 | 충족 |
| DAT-03 | AI Hub 데이터 저장소·화면 미포함, 생성형 AI 출력은 학습 자료로 미사용 | 저장소 점검 | `git ls-files`(`dadc2dd5` + 이 PR의 `ml/tox/results/887-compare` 요약): zip·parquet 0개, jsonl·csv 13개는 자체 작성 평가 자료·교육과정 지식(11/20 뒤 추가 1개는 추억 검색 평가셋 memory@2, 학습에 안 씀), AI Hub 이름·자료 번호가 든 4개(#887에서 `aihub_kid16k_pc_summary.json` 추가)는 집계 요약·스크립트로 원문 0건. `.gitignore` 16~22행이 AI Hub 폴더·파일명 차단. 생성형 AI 출력 쪽은 `ml/tox` 아이 말투 학습 문장만 기능명세 예외(#887, 2026-11-23) | 이 절 점검, [기능명세 NFR-DAT-03](../design/functional-spec.md), [ml/tox README](../../ml/tox/README.md) | 11/23 | 충족 |
| DAT-04 | 삭제 정책을 문제풀이·대화·리포트·대시보드에 동일 적용 | 모의·CI | 학생 삭제 뒤 learning 근거 `available=false`·원문 없음, report 삭제 대기 중 조회·생성 차단, core 대화 근거 이용 불가, 웹은 `available:false` 근거를 링크하지 않음. 화면 전체 미노출 확인은 수동 `parent-admin-browser.mjs`뿐(CI 밖) | learning `record/StudentDeletionTest`, report `test_deletion.py`, core `conversation/ConversationIntegrationTest`, web `reportHighlight.test.ts` | 11/20 | 충족 |
| DAT-05 | PITR 7일, RPO 5분·RTO 4시간, 복구 정합성 확인 | 배포(A) | RTO 요청→`available` 19분 8초. RPO 5분 23초(같은 날 다른 시점 3분 37초). 답변 2,814건 md5·스키마·열 지문 일치. 근거 연결·결제 행이 0건이라 그 정합성과 PG 대조는 실데이터로 미확인 | [infra 9.12](infra.md#912-rds-pitr-복구-시험-629-2026-11-18) | 11/18 | 미충족(RPO: PITR 로그 업로드 주기가 약 5분이라 5분을 넘을 수 있음. 목표는 유지, 2026-11-20 결정) |
| REL-01 | 제출·결제 승인·PG 통지·알림·재처리 1회만 반영 | 모의·CI | 같은 키 재제출은 첫 답변 반환, 동시 승인 → PG 호출 1·구독 1, 같은 갱신 기간 1회 청구, 서명된 중복 웹훅 1회 반영, 반복 사건 알림 1건, 소비자 `processed_event` 중복 무시 | learning `AnswerServiceTest`·`answer/service/AnswerConcurrencyTest`, core `payment/PaymentIntegrationTest`·`notification/NotificationIntegrationTest`·`_common/messaging/MessagingIntegrationTest` | 11/20 | 충족 |
| REL-02 | 지연·외부 장애 시 시간 초과·재시도·중복 방지(P12) | 모의·CI | 하위 서비스 대역 지연·장애로 504·재시도 없음·서킷 열림, 사용 증빙 6초 지연을 5초에 끊음, 전송 시간 초과는 두 번째 호출 없이 UNKNOWN 기록 | core `learning/LearningClientTest`·`payment/TossCircuitTest`·`payment/PremiumUsageClientTest`·`admin/AdminOperationsIntegrationTest`, learning `judgment/client/AiClientTest`·`_common/config/FeedbackTimeoutBudgetTest` | 11/20 | 충족 |
| REL-03 | 실패한 분석을 임의 결과로 대체하지 않음, 결제 불명확 시 추가 청구 전 확인 | 모의·CI | AI 실패는 FAILED·503 재시도 가능·답변 유지, 근거 없는 충족 응답은 `AI_BAD_RESPONSE`, 분석 대화 최종 검증 실패는 답을 저장하지 않음, 승인 응답 유실은 재청구 없이 조회로 복구 | learning `judgment/facade/FeedbackFacadeTest`, core `conversation/AdminConversationRetryTest`·`payment/PaymentIntegrationTest`, ai `analysis_agent/test_verification.py`, web `paymentCheckout.test.ts` | 11/20 | 충족 |
| REL-04 | 저장/AI 결과, 보류/실패, 기록 없음/조회 실패 분리 | 모의·CI | 보류는 DONE + 사유, 실패는 FAILED, core·report 클라이언트가 기록 없음과 조회 실패 구분, 웹은 조회 실패·처리 중을 빈 기록으로 바꾸지 않음 | learning `judgment/domain/JudgmentTest`, core `learning/LearningRecordClientTest`·`learning/FeedbackIntegrationTest`, report `test_learning_client.py`, web `dashboard40Contract.test.ts` | 11/20 | 충족 |
| PRF-01 | 제출·되묻기·분석 대화·리포트 지연 실측, 목표는 측정 후 합의 | 실API·배포(kind·A) | 실제 LLM·동시 1명: 판정 SSE p95 8.9초(kind)·8.8초(A), 판정+되묻기 12.5·12.8초, 분석 대화 8.9·8.1초, 주간 리포트 재생성 35.3초(kind만). LLM 스텁 부하: 300명 API p95 374ms(1차)·1,042ms(2차), 한계는 RDS CPU | [infra 9](infra.md#9-aws-데모-부하-시험-1차-361)·[9.10](infra.md#910-실제-llm-조건-로컬-응답-시간-실측-630-2026-11-16)·[9.10.6](infra.md#9106-aws-운영-데모-실측-2026-11-18)·[9.14](infra.md#914-aws-데모-부하-시험-2차-hpakarpenter-확장축소-384-2026-11-18), [ai 19.5](ai.md#195-aws-운영-데모-실측과-kind-비교-2026-11-18) | 11/05~11/18 | 충족(실측 기록. 응답 목표 수치는 "측정 후 합의"라 범위 밖, B 재측정 9.4) |
| PRF-02 | 호출별 입력·출력 토큰 기록, 학생 ID·답변 미기록, 원가 산식 | 모의·CI·실API | `llm.usage.recorded.v1` 스키마에 학생·답변 필드 없음(`additionalProperties: false`), 발행 본문 `subject` 없음 시험. 실제 OpenAI 호출 종류별 평균 토큰(판정 입력 585·출력 301)과 원가 산식 계산 | `contracts/events/llm.usage.recorded.v1.schema.json`, ai `messaging/test_usage_recorder.py`, [ai 19.2](ai.md#192-호출-종류별-평균-토큰비용-이번-측정)·[19.3](ai.md#193-원가-산식-기획서-39) | 11/16 | 충족 |
| PRF-03 | 리포트 설명 주 1회 일괄, 엔드포인트 일 23:30~월 02:00만 1대 | 실API·배포(A) | 참고: A 시험 예약으로 축소 → 사본 0(15:50)·인스턴스 0(16:01), 확장 → 준비 +20.5분, 주간 예약 설정. 실제 주간 창 뒤 0대 복귀는 미확인 | `infrastructure/aws/sagemaker/explanation-endpoint.json`, [infra 9.13.9](infra.md#콜드-시간과-예약-확장), [ai 24.6](ai.md#246-a-계정-실제-엔드포인트-확인-2026-11-18-가상-입력) | 11/18 | 점검 예정(B 첫 주간 창, #783) |
| AIQ-01 | 미션당 예시 20개·평가자 2명, 사람-사람·사람-AI QWK | 실API·배포(kind) | 데모 미션 5개 × 자체 작성 답안 20개: 결과 QWK 사람-사람 0.809·사람-AI 0.792, 요소 일치율 0.880·0.875, 보류 12%, 인용 불일치 0. 최저 DEMO-14 0.676. 합격선은 AIQ-06 | [ai 1 기준선 결과](ai.md#기준선-결과-585-2026-11-13), `evaluation/results/judgment/` | 11/13 | 충족 |
| AIQ-02 | M2 klue 학습, 처음 보는 주제 분리 평가, 기준선·공개 LLM 비교, 사람끼리 상관 함께 보고 | 학습 기록(RunPod) | Pearson 처음 보는 주제 서술 0.538·논술 0.452(사람끼리 0.694·0.560), 학습한 주제 0.685·0.700, 공개 LLM LoRA(Qwen3-1.7B 0.684·Kanana-2-3B 0.689) 비교 뒤 klue 유지. 규칙·TF-IDF 기준선은 2.0 모델(71819) QWK로만 있고 `c26d8455` 이전 `ml/m2/README.md`에 남음 | [ml/m2 README](../../ml/m2/README.md), [planning 2.3](planning.md#23-m2-중간-결과-112-기준) | 11/01~11/02 | 충족 |
| AIQ-03 | 설명 sLLM 인용·금지어 검사와 사람 검토 50개, 허용 기준 11/22 | 실API(SageMaker·RunPod) | 참고: 가상 글 1편 15회 `checks.py` 통과 LoRA 14/15·기반 단독 8/15, 파일럿 금지어 0·인용 4/4 원문 일치. 사람 검토 50개·3인 A/B 설문 미실시, 실제 학생 글 통과율 미집계, 허용 기준 미정 | [ml/sllm README 평가](../../ml/sllm/README.md#평가), [gemma-explanation-validation 3](gemma-explanation-validation.md#3-결과), [infra 9.13.9](infra.md#기반-단독과-lora-비교-746-d2) | 11/16~11/18 | 점검 예정 11/22 |
| AIQ-04 | M1 수학 문항 그룹 분할·학습·평가, 검증 범위만 활성화 | 학습 기록 | 시험 16,913개 균형 정확도: 다수 클래스 0.500, 규칙 0.642·0.703. 학습 모델은 코드 확인용(0.5)뿐이라 서비스 비활성 | `ml/m1/results/eval_m1.md`·`eda_71716.md` | 11/02 | 충족(후순위, 비활성 유지) |
| AIQ-05 | 활성화 전 고정 평가 비교, 기준 충족 범위만 승인 | 배포(A) | M2 b판 경계: 사전 검사 → 등록 → 승인·활성화(초5·6) → scoring `LOADED`, 실제 채점 5건 새 경계와 일치. 리포트 Gemma `gemma4-26b-a4b-lora-20261118-r2` 활성화(사람 검토 미실시 상태). 판정 프롬프트 `.evaluation.json` 준비 | [ai 3](ai.md#3-모델-레지스트리ai-사용량-43), [scoring 7.8](scoring.md#78-운영-적용-613-2026-11-17), [ml/sllm README](../../ml/sllm/README.md) | 11/17~11/18 | 충족 |
| AIQ-06 | 11/22까지 허용 기준, 넘은 범위만 서비스 적용 | — | 판정 QWK·M2·설명 sLLM·M1 허용 기준 모두 미정 | [ai 1](ai.md#1-판정되묻기-6), [planning 2.3](planning.md#23-m2-중간-결과-112-기준) | — | 점검 예정 11/22 |
| UX-01 | PC에서 학습 흐름, 학부모·관리자 768·390px 가로 넘침 없음 | 모의·CI | 대역 compose 실서버(#885, 1회 기록)에서 학부모 16·관리자 17화면과 로그인 2화면을 1440·768·390px로 재 105건 모두 넘침 0(추가 확인한 테마 초안 실패 상세 3건도 0). 같은 스택 PC 실서버 E2E 9 passed(6.3분), 야간 CI 9개 통과(9.2) | [evidence/issue885-ux-real-server](evidence/issue885-ux-real-server/README.md), [2절](#2-실서버-브라우저-e2e와-외부-스텁-246) | 11/23 | 충족 |
| UX-02 | 키보드·터치, 색 외 글 안내, 입력 이름·선택 대상 | 모의·CI | 대역 compose 실서버(#885, 1회 기록)에서 학생 18·학부모 16·관리자 17화면을 1440·390px(터치) axe 99회: critical 0, 학생 위반 0. serious는 관리자 15메뉴 전부 글자 대비(285건, 3.31~4.45:1, 추가 확인한 테마 초안 실패 상세도 13건)·로그인 2화면 대비·관리자 390 가로 스크롤 표 키보드 불가 3화면·학부모 동의 체크박스 크기 2화면·`aria-label` 금지 1·문장 속 링크 1. 키보드 Tab 99회 초점 유실 0(학부모·관리자 본문 건너뛰기, 대화 창 Esc 복귀), 이름 없는 입력 0, 선택 표시(`aria-current`·`aria-selected`·`aria-pressed`), 오류·진행은 `role=status`·`role=alert` 글. #805 색 단추의 고른 색 초점 안 보임은 찾아서 고침. 이후 관리자 대비·390 가로 스크롤 표는 #914로 고쳐 관리자 로그인·메뉴 16개·상세 2개 1440·390 axe serious 191건 → 0건(`tests/browser/admin-contrast.spec.ts`), 처리 중 단추 초점(아이템 저장 409·테마 초안 요청 오류를 키보드로 제출 시 `body`)은 #917로 고쳐 단추에 유지(1440·390, `tests/browser/admin-busy-focus.spec.ts`). 학부모 4종은 #915로 고친 뒤 같은 대역 스택·같은 점검 스크립트로 다시 재 99회 전체 serious·critical 0(학부모 16·공개 2화면 1440·390 34회 포함, #885 학부모·학부모 로그인 15건 → 0, 넘침 133회 0). 회귀는 MSW `tests/browser/accessibility.spec.ts`(#915 카드 역할·링크 밑줄·동의 체크박스 크기 추가)·위 두 시험(CI). 학부모 로그인 아이디 폼은 실제 모드에서만 나와 실서버 재점검으로만 확인. 화면 읽기 프로그램·실기기 미점검 | [evidence/issue885-ux-real-server](evidence/issue885-ux-real-server/README.md)·[issue914-admin-contrast](evidence/issue914-admin-contrast/)·[issue917-admin-busy-focus](evidence/issue917-admin-busy-focus/)·[issue915-parent-a11y](evidence/issue915-parent-a11y/README.md), [frontend 40](frontend.md#40-학생학부모-주요-화면-접근성-점검-nfr-ux-02-630-일부-2026-11-13)·[44](frontend.md#44-학생학부모-접근성-버그-수정-639640641-2026-11-13)·[50](frontend.md#50-관리자-글자-대비가로-스크롤-표-키보드-접근-914-nfr-ux-02-2026-11-23)·[51](frontend.md#51-관리자-처리-중-단추의-키보드-초점-유지-917-nfr-ux-02-2026-11-23)·[52](frontend.md#52-학부모-화면-접근성-serious-4종-수정-nfr-ux-02-915-2026-11-23) | 11/13~11/23 | 충족(대역 실서버 axe serious 0. 화면 읽기 프로그램·실기기는 범위 밖) |
| UX-03 | 학년이 이해할 길이·표현, 대표 시나리오에서 문구 확인 | 문서 점검 | 학생 화면 글자·간격·폭과 문구 47+12곳 정리, 넘긴 18줄 모두 반영 | [frontend 21](frontend.md#21-학생-화면-글자-크기간격폭과-문구-정리-431-2026-11-12)·[31](frontend.md#31-문제-푸는-화면-개편-440-2026-11-15) | 11/12~11/15 | 충족 |
| UX-04 | 미션 10분 안팎 | — | 콘텐츠 검토 기록 없음 | — | — | 미충족(검토 기록 없음) |
| OPS-01 | 환경별 데이터·외부 연동 분리, 시연·테스트 거래가 운영 통계에 안 섞임 | 배포(kind) | 참고: kind 감사 SQL 통과(SEC-07과 같은 실행). A는 신규 보호자 `is_demo=true`. B 미실행 | `infrastructure/aws/audit-demo-data.sql`, [infra 9.7.2](infra.md#972-kind-확인-실제-17201745) | 11/13 | 점검 예정 12/5 |
| OPS-02 | 승인 절차 배포·수행자·시점 기록, 시연 URL 경로 확인 | 배포(A) | 참고: A cd-release 5회(성공 3·실패 2) 모두 `prod` 승인·수행자·plan 호환성 기록. 성공 회차 경로 확인(학생 로그인 → 시도 → 답변 → 학부모 갱신 → 리포트 목록) 통과, 11/05 1회는 답변 422로 실패 처리. prod 배포는 Argo CD로 전환 중이라 B 점검은 그 경로 기준([infra 9.18](infra.md#918-prod-argo-cd-전환-에픽-859-2026-11-20)) | [infra 7.4](infra.md#74-운영-실행에서-얻은-주의점), [evidence/issue811-cd-history-a](evidence/issue811-cd-history-a/) | 11/04~11/19 | 점검 예정 11/28(B, #783) |
| OPS-03 | 장애 시 승인된 이전 버전 복구, 호환성·영향 확인 | 배포(A) | 참고: 11/04 scoring을 이전 release로 되돌리는 cd-release 실행·경로 확인 통과. 진행 중 학습·결제 영향 기록은 없음 | [infra 7.4](infra.md#74-운영-실행에서-얻은-주의점), `evidence/issue811-cd-history-a/20261104-41802823411-*.json` | 11/04 | 점검 예정 11/28~29(B, #783) |
| OPS-04 | 오류율·지연·적체 경보를 Grafana → 디스코드 | 배포(kind·A) | 참고: kind 실제 DLQ 적재 → 규칙 발생 → `aws-alerts` Firing·Resolved 수신, A 임시 규칙으로 수신 경로 확인. prod 규칙 16개 적용 시각 미확인 | [infra 8.2](infra.md#82-검증-상태) | 11/03~11/04 | 점검 예정 11/28~29(B, #783) |
| OPS-05 | 실패 요청을 학습·대화·리포트·결제 작업과 연결해 추적 | 배포(kind) | 참고: 명령 소비 → 동기 HTTP → 결과 이벤트 → 재시도·DLQ가 한 trace(span 67개). 로그인 사용자 요청 시작점·실패 요청 연결 미실행 | [infra 8.2](infra.md#82-검증-상태) | 11/12 기록 | 점검 예정 11/28~29(B, #783) |
| OPS-06 | DB 집계만, 기간·분모·대상 기록, 인과 주장 없음 | 배포(kind) | 지표 6개를 원본 행과 대조(학생 11명, 기준일 11/16·11/23), 대조에서 `seen_at` NULL 결함 발견·수정 | `scripts/retention_metrics/`, [retention-expansion 15.3](retention-expansion.md#153-kind-대조-2026-11-13-읽기-전용) | 11/13 | 충족 |
| QA-01 | 판정·화면·리포트·분석·권한 필수 자동 검증, 실패·중복·보류·선공개 포함 | CI | develop 서비스별 CI 전부 통과, 야간 실서버 E2E 9개 통과(9.2). 남은 위험: core 통합 테스트 DB 연결 최대 99/100(3절) | 9.2, [2절](#2-실서버-브라우저-e2e와-외부-스텁-246)·[3절](#3-core-계정-http-경로-테스트-136) | 11/20 | 충족 |
| QA-02 | 토스 테스트 결제로 승인·실패·중복 통지·갱신 실패·해지·환불 | 모의·CI·PG | 모의: 위 경로 전부 core 통합 테스트. PG: kind에서 테스트 결제 승인·구독 `ACTIVE` 1건만. 빌링 발급·정기 청구·취소·웹훅은 실제 PG 미검증, A는 공용 위젯 키 500으로 결제 불가 | core `payment/PaymentIntegrationTest`, [core-gateway 24.8](core-gateway.md#248-검증-범위와-한계), [infra 3.2](infra.md#32-kind-환경값외부-egress-236) | 11/03 | 미충족(실제 PG는 승인만) |
| QA-03 | 테스트 거래가 실제 결제·매출과 분리 | 모의·CI | 운영(`live`) 키·PG 설정 누락은 네트워크 호출 전 거부, 웹은 `live_gsk_` 거부·샌드박스 권한 표시. 거래 기록 점검은 미실행 | core `payment/PaymentProtectionTest`, web `paymentCheckout.test.ts` | 11/20 | 점검 예정 12/5(감사 SQL 결제 집계) |
| QA-04 | 모의·PG·실제 API·원격 CI·배포 확인을 각각 기록 | 문서 | 이 표의 검증 구분 칸 | 이 절 | 11/20 | 충족 |

### 9.4 점검 예정

| 날짜 | 대상 | 할 일 |
|---|---|---|
| 11/22 | AIQ-03·06 | 설명 sLLM 허용 기준 결정, 사람 검토 50개 표본 결과. 판정 QWK·M2 기준도 같은 기한 |
| 11/28~29 | OPS-02~05, PRF-01·03 | B 계정 배포 승인·경로 확인(Argo CD, 11/25 A에서 먼저 확인 #859), 복구 리허설, 경보 발생, 실패 요청 trace, 부하 재측정, 첫 주간 창 뒤 엔드포인트 0대 복귀(#783) |
| 12/5 | SEC-07, OPS-01, QA-03 | 시연 환경에서 `audit-demo-data.sql` 실행(가상 학생·시연 표시·결제 집계) |

### 9.5 미충족과 보강할 점

- DAT-05: RPO 1회 측정 5분 23초. 목표 5분 유지(2026-11-20 결정), 근거 연결·결제 행이 있는 상태의 복구 대조는 미실행
- QA-02: 실제 PG로 정기결제·실패·해지·환불·웹훅 미검증
- UX-04: 미션 분량(10분 안팎) 콘텐츠 검토 기록 없음
- 충족 줄의 시험 공백: SEC-01 미동의 계정 `POST /children`, SEC-08 Secure 속성, DAT-02 기준표 변경 후 과거 판정 재조회, DAT-04 화면 전체 미노출(수동만), AIQ-02 현재 모델의 기준선 비교, AIQ-05 리포트 Gemma 사람 검토 없이 활성화

### 9.6 증거 파일

- [evidence/issue811-cd-history-a](evidence/issue811-cd-history-a/): A 계정 cd-release 5회의 `history.json`(승인자·수행자·이미지 digest·migration·경로 확인)과 `plan.json`(사유·호환성 판단). Actions 산출물(보관 90일)에서 받은 원본이며 비밀 값 없음. 이미지 주소의 A 계정 번호는 저장소에 이미 공개된 값
- 저장소 안 결과 파일(`evaluation/results/`, `ml/*/results/`)은 복사하지 않고 근거 칸에서 원래 위치를 링크
- 저장소 밖 원본(M2 예측 CSV, 설명 sLLM 출력, k6 원시 출력)은 학생·AI Hub 글이 들어 있거나 일회성이라 넣지 않음

## 10. 민감정보 점검 (#884, 2026-11-22)

외부 LLM 요청 내용(NFR-SEC-03)과 운영 로그(NFR-SEC-05·06)에 학생 이름·ID·원문·비밀 값·결제수단 정보가 있는지 실제 실행분으로 점검. 기록에는 항목 이름·건수만 둠.

### 10.1 환경

- 기준: develop `22a42a54` + llm-stub 요청 기록 옵션(`LLM_STUB_RECORD_FILE`, 기본 꺼짐)
- 검증 구분: 모의. 2절 대역 스택(`compose.e2e.yaml`, LLM·토스·Google·M2 대역, DB·브로커 실제)을 로컬 Docker로 1회 기동. 실제 OpenAI·SageMaker·PG 호출과 kind·A·B 로그는 보지 않음
- 실행: `LLM_STUB_RECORD_FILE=/tmp/llm-requests.jsonl`로 기동 → `npm run test:e2e` 7 통과·1 실패·1 건너뜀
  - 실패: `learning-journey` 주간 리포트. 리포트 생성 완료 뒤 기간 문구가 화면 두 곳에 있어 locator 엄격 모드 위반(점검 대상 경로는 끝까지 실행됨)
  - 건너뜀: 주간 테마 시나리오(KST 일요일에는 무료 이용권 문제가 닫힘)
- Git Bash에서는 `MSYS_NO_PATHCONV=1`이 필요. 없으면 기록 경로가 Windows 경로로 바뀌어 대역이 종료됨(첫 실행). `down -v` 뒤 재실행분만 사용

### 10.2 대상과 방법

| 대상 | 수집 | 검사 |
|---|---|---|
| 외부 LLM 요청(SEC-03) | llm-stub이 받은 본문 12건(외부로 나가는 최종 요청) | 실행 뒤 DB에서 뽑은 학생 ID 7·닉네임 7·보호자 로그인 ID·표시 이름 10·시도 ID 4·답변 ID 5와 문자열 대조, 메시지 안 `studentId`·`attemptId`·`answerId`·`childId`·`nickname`·`name` 키, UUID(채점 요소 ID 56개와 대조해 분리) |
| 서비스 로그(SEC-05) | `docker compose logs` core·learning·ai·report-api·report-worker 219줄 | `e2e.env` 비밀 값 27종 원문, 토스 키 접두사(`test_sk_`·`test_gsk_`·`live_`), OpenAI 키, `Bearer` 토큰, JWT, 결제 필드 이름(`billingKey`·`customerKey`·`paymentKey`·`cardNumber`), 16자리 카드번호, `password=`, E2E PIN, 학생 답변 원문 5개(8자 이상 `plain_text`), 닉네임·보호자 이름, 학생·시도·답변 ID |
| 결제 로그(SEC-06) | core `payment` 패키지 테스트 51개(승인·위조 거부·응답 유실·갱신 실패 재청구·해지·환불·취소 유실·웹훅·빌링 등록) system-out 130줄 + 위 서비스 로그의 E2E 결제 승인분 | 위 패턴 + 테스트 대역 합성 PG 키(`synthetic-`·`test_sk_`·`test_gsk_`) |

- 검색 패턴 원본: [evidence/issue884-sensitive-audit/scan.py](evidence/issue884-sensitive-audit/scan.py), 결과: [scan-result.json](evidence/issue884-sensitive-audit/scan-result.json)(건수·요청 키·메시지 역할만, 원문·ID 값 없음)

### 10.3 결과

| 항목 | 결과 |
|---|---|
| LLM 요청 종류 | 판정(`Extraction`) 5, 되묻기(`GeneratedQuestion`) 5, 리포트 서술(`GeneratedNarrative`) 1, 리포트 설명(`ExplanationDetail`) 1 |
| LLM 요청의 학생·시도·답변 ID, 닉네임, 보호자 이름, ID 키 | 모두 0건 |
| LLM 요청의 UUID | 15개 모두 채점 요소 ID(판정 5건 × 3, 학생 기록 ID 아님). 그 밖 UUID 0 |
| LLM 요청의 학생 답변 원문 | 12건 모두 포함(판정·설명 대상이라 필요한 전달). 대조 문자열이 실제로 걸리는지 확인하는 양성 대조로도 씀 |
| 서비스 로그 비밀·결제·원문 패턴 | 모두 0건 |
| 서비스 로그 학생·시도·답변 ID | 50건. 내부 HTTP 접근 로그 URL(`/internal/reports?studentId=…` 등)과 판정 건너뜀 사유 로그(`attemptId=… reason=TIMEOUT`). SEC-05 대상(비밀번호·키·카드·원문) 아님 |
| 결제 테스트 출력 패턴 | 모두 0건 |

e2e로 안 도는 경로는 테스트로 확인(로컬 실행, 모두 통과)

| 경로 | 테스트 |
|---|---|
| 분석 대화 | ai `tests/analysis_agent/test_router.py::test_llm_requests_have_no_student_id`, `test_nodes.py`. 대역에서 안 돈 이유: E2E 시나리오 없음 |
| 추억 임베딩·설명·질의 변환 | learning `memory/MemoryEmbeddingClientTest`·`MemoryExplanationTest`·`MemoryQuerySearchServiceTest`·`MemorySearchTest`·`MemoryQueryAiClientTest`(닉네임 `[학생]`·UUID `[식별자]` 가림, #878 실패 로그는 `failureCode`·시도 번호만이고 질문·응답 원문 없음), ai `tests/memory_explanation`·`tests/memory_query`(ID 칸 거부). 대역에서 안 돈 이유: llm-stub 미지원 스키마, 임베딩은 OpenAI 주소 고정 |
| 주간 테마 생성 | 코드 확인만. learning `theme/client/ThemeDraftAiClient`가 보내는 칸이 학년·주차·주제·성취기준뿐이라 학생 데이터 입력 없음. 관리자 미션 초안은 ai `tests/mission_draft/test_prompts.py`(이름·`studentId` 없음) |
| 리포트 서술·설명 | report `tests/test_narrative.py::test_known_nickname_and_identity_fields_are_not_sent`, `tests/test_explanations.py` |
| 판정·되묻기 | ai `tests/judgment/test_service.py`·`tests/followup/test_service.py`, learning `judgment/facade/FeedbackFacadeTest` |

- 실행 수: ai 228, report 74, learning 73, core payment 51 통과

### 10.4 남은 위험

- 판정·되묻기·분석 대화는 답·질문 본문에 학생이 쓴 닉네임을 가리지 않고 보냄. 설계상 닉네임 가리기는 리포트 서술·설명과 추억 경로만이라 위반으로 보지 않음(2026-11-22 결정)
- 샘플에는 없었지만 코드상 생길 수 있는 경우
  - core·learning 전역 예외 로그에 DB 제약 오류 상세(답변 원문), 비밀번호·PIN data class 기본 `toString()`: #898에서 처리
    - 두 서비스 `application.yml` `spring.datasource.hikari.data-source-properties.logServerErrorDetail: false`. `DB_URL`과 상관없이 적용, 오류 로그에는 제약 이름·SQL(`?` 자리표시)만 남음
    - 비밀번호·PIN·토큰·연결 코드·`customerKey`를 담은 core 요청·결과 타입 17개는 `toString()`에서 값을 `***`로 가림
    - 시험: learning `answer/service/AnswerServiceTest`(답변 저장 CHECK 위반을 전역 예외 로그로 남겨도 원문 0건, 설정 전에는 실패 확인), core `_common/persistence/DbErrorDetailLogTest`·`account/SecretToStringTest`
  - ai·scoring 전역 예외 로그에 응답 검증 오류 입력값: #899 해결. ai·scoring 전역 처리기와 분석 대화가 Pydantic 검증 오류를 본문 없이 기록
  - OTel trace의 토스 호출 URL에 `billingKey`·`paymentKey`, Google 콜백 `code`(로그가 아닌 trace, Tempo 24시간): #900에서 조치. Collector traces pipeline `transform/redact`가 청구·취소 경로 키를 `{billingKey}`·`{paymentKey}`로 바꾸고 로그인·재인증 콜백 server span의 `url.query`를 지움. Collector 0.164.0에 prod 렌더 설정으로 가짜 span 6건을 보내 키·code 0건, 주문 조회·일반 경로는 그대로임을 확인. 운영 Tempo 검색 0건 확인은 배포 후(기존 span은 24시간 뒤 만료). 이후 URL 별칭과 span 이름을 포함한 검증은 10.5
- ai·scoring·report-api는 로깅 설정이 없어 WARNING 이상과 uvicorn 접근 로그만 남음(운영 이미지와 같은 조건). 로그 수준을 올리면 다시 점검 필요
- 운영 로그 중앙 수집이 없어(`OTEL_LOGS_EXPORTER=none`, Loki 없음) 배포 환경 샘플은 파드별 `kubectl logs`로만 얻을 수 있음. 이번 점검은 로컬 실행분만 봄

### 10.5 trace URL 비식별화 (#900, 2026-11-23)

- Collector의 trace 파이프라인에서 토스 빌링 청구·결제 취소 URL의 키를 경로 템플릿으로 바꾼다. Google 로그인·재인증 콜백에서는 쿼리 속성을 삭제하고, URL이나 span 이름에 포함된 쿼리도 제거한다. 변환 처리 오류는 원문 export 대신 실패로 처리한다.
- 검증 환경은 로컬 Docker Collector 0.164.0 → Tempo 2.10.10이다. Helm 4.3.1로 렌더링한 구성에서 변환 단계만 뺀 대조군과 변환 적용군에 동일한 합성 span 7개씩 전송했다. Tempo에서 두 trace를 조회한 결과 민감 값이 포함된 span은 4건에서 0건으로 줄었고, 양쪽 모두 7개를 저장했다. 상태 코드, 빌링 자격 발급 경로, 무관한 URL 및 속성은 유지됐다.
- Tempo 활성, Langfuse 전용, 메트릭 전용 차트 렌더링을 확인했다. 운영의 실제 기존 trace 조회와 배포 뒤 확인은 남아 있다. 운영에서는 Collector 전환 이후의 시간 범위에서 청구·취소의 키 경로와 콜백 쿼리 속성을 조회해 건수만 남긴다. 기존 저장분은 Tempo 보존 기간의 영향을 받는다.
