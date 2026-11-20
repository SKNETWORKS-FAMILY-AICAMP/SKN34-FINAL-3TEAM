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
| charts | `environments/prod/*.json`(#509): 저장소 chart values는 local과 같은 규칙으로 lint·template, `migrations/<release>.json`이 있으면 덮어써 migration Job까지 렌더. `kind`가 있는 manifest(NodePool·NetworkPolicy·ExternalSecret)는 그대로 kubeconform 대상 | 렌더 실패, 스키마 위반 |
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
| 재시도 계층(1.3) | 재시도는 ai LLM 호출(1회, 1초)과 되묻기 유출 재생성(1회)만. 서비스 간 호출은 재시도 없음. 모든 클라이언트에 타임아웃 |
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
