# #246 실서버 브라우저 E2E와 Google·LLM·토스 스텁

## 목적과 결정

- 기존 브라우저 테스트(`playwright.config.ts`)는 전부 MSW 목업 대상이라 실제 core·learning·ai·report 연동 미검증 (NFR-QA-01)
- 외부 의존(Google OAuth·LLM·토스페이먼츠)을 `infrastructure/stubs/` 대역으로 바꾼 compose 스택에서 핵심 흐름 E2E 실행
- 담당자 결정 (2026-11-02)
  - 로그인 대체: Google 스텁(token·JWKS) + Playwright의 authorize 리다이렉트 재작성. 테스트 전용 로그인 API 미추가
  - CI 실행 시점: 수동·E2E 구성 파일 변경 PR. 매일 03:00 KST schedule은 GitHub가 기본 브랜치(main)의 워크플로만 예약 실행하므로 main 병합 후부터 동작(develop 대상 아님)
  - 토스: core에 PG 주소 설정 추가, toss-stub, 결제 승인 E2E 1건
- 실제 Google·토스·LLM 키와 GitHub secrets 미사용. 모든 값은 `infrastructure/stubs/e2e.env`의 합성 값

## 설정 변경 (공개 API 계약 변경 없음)

| 대상 | 변경 | 기본값·영향 |
|---|---|---|
| core `app.payment.toss-base-url` (`TOSS_API_BASE_URL`) | `TossClient` 요청 주소를 설정값으로 변경 | 기본 `https://api.tosspayments.com`. 미지정 환경은 동작 동일, `test_sk_`·`test_gsk_` 키 검사 유지 |
| core `app.auth.google-token-url`·`google-jwk-url` | 코드 변경 없음. Spring 완화 바인딩 환경 변수 `APP_AUTH_GOOGLETOKENURL`·`APP_AUTH_GOOGLEJWKURL`를 E2E 오버레이에서만 지정 | 기본 Google 주소 |
| ai-service | 코드 변경 없음. 기존 `OPENAI_BASE_URL`(OpenAI 호환 서버)로 llm-stub 지정 | E2E 오버레이에서 실제 키 변수를 빈 값으로 고정 |

`docs/design/api-spec.md` 변경 없음.

## 스텁 (`infrastructure/stubs/<target>-stub/`)

Node 22 alpine 표준 라이브러리만 사용 (RS256 서명 필요, 기존 `tests/student-device-live-browser.mjs` Google 대역과 같은 런타임). 각 이미지에 `GET /health` 헬스체크.

| 스텁 | 구현 경로 | 동작 |
|---|---|---|
| google-stub | `GET /jwks`, `POST /token` | 기동 시 RSA 키 생성. `code`는 base64url JSON `{sub,email,name,nonce,challenge,redirectUri}`라 상태 없음. client_id·secret·redirect_uri·PKCE(S256) 검증 후 `iss=https://accounts.google.com`, `aud=GOOGLE_CLIENT_ID`, `email_verified=true` id_token 발급 |
| llm-stub | `POST /v1/chat/completions` | `response_format.json_schema.name`으로 응답 선택. `Extraction`은 프롬프트의 모든 `elementId`를 답변 원문 인용·FOUND로 반환(정답 판정), `GeneratedQuestion`·`GeneratedNarrative`(숫자 없음)·`Classification`·`TemplateProposal` 고정 응답, `stream:true`는 SSE 조각·사용량·`[DONE]`. 그 외 이름은 400 |
| toss-stub | confirm, `orders/{orderId}` 조회, billing 발급·청구, cancel, transactions | 메모리 저장. Basic 키는 `test_` 접두사만 허용, 정기결제 키면 `TOSS_TEST_BILLING_MID`, 아니면 `TOSS_TEST_MID`. 조회 실패는 404 `NOT_FOUND_PAYMENT` |

## 스택·시드

- `compose.e2e.yaml`: `compose.yaml`·`compose.minio.yaml`(리포트 저장)과 함께 지정하는 오버레이
  - 스텁 3종, core·ai 환경 변수 재정의, report-api·worker는 버킷 생성 완료 후 기동
  - `e2e-seed`: 마이그레이션 직후 `frontend/web/tests/e2e/seed/core.sql`(core_db)과 기존 `backend/learning-service/db/seed/demo_missions.sql`(learning_db) 실행
  - scoring-service는 E2E 흐름에서 호출하지 않아 기동 대상 제외
- `core.sql` (재실행 시 결과 동일): 필수 동의 문서 3종, 무료(`PAYMENT_FREE_PRODUCT_ID`)·유료(`E2E 프리미엄`, 14,900원) 상품, ADMIN 계정(Google sub `e2e-admin`)과 관리자 권한 4종
- 주간 리포트: cron이 월요일 07:00·지난주 기간이라, 테스트가 `report_job`(QUEUED)과 `report.generate` outbox 이벤트를 이번 주 기간으로 직접 삽입 (`tests/e2e/support/db.ts`). 이후 OutboxRelay → RabbitMQ → report-worker → 완료 이벤트는 실제 경로

## 테스트 (`frontend/web/tests/e2e/`, `npm run test:e2e`)

`playwright.e2e.config.ts`를 별도 파일로 둠 (webServer가 설정 파일 단위라 MSW 설정·`npm run test:browser`와 분리). 웹은 `http://127.0.0.1:5272` Vite dev(`VITE_API_MOCK=false`)로 실행해 `/api`를 core로 프록시.

| 스펙 | 흐름 |
|---|---|
| `admin-home.spec.ts` | 관리자 Google 로그인 → `/admin/home` 운영 현황·실제 집계 기간·학습 시도·처리 현황 |
| `learning-journey.spec.ts` 1 | 학부모 로그인·동의·자녀 등록 → "이 자녀로 학습 시작" → 미션 "쉬는 시간을 늘린다면?" 작성·제출 → 정답 판정·되묻기 → 돌아보기 저장 → 공책 완료 → 답 공개 설정 |
| `learning-journey.spec.ts` 2 | 같은 학부모 재로그인 → 대시보드 학습 기록 표 완료·원문 보기 → 이번 주 리포트 생성 → "생성 완료" → 상세 기간·수치 리포트 안내 |
| `payment.spec.ts` | 유료 이용권 선택 → "결제수단 선택"(주문 생성) → `/payment/success` 리다이렉트 → core confirm이 toss-stub 호출 → "결제가 완료되었습니다" |

- 학생 토큰은 메모리에만 있어 학생 단계는 화면 내 이동만 사용
- 학생 모드 진입 시 학부모 refresh 쿠키가 지워져 학부모 단계는 새 컨텍스트에서 재로그인
- 토스 결제 위젯 JS·Google 폰트는 차단, 외부 네트워크 호출 없음

## 실행

```sh
COMPOSE="docker compose -p sagomungchi-e2e --env-file infrastructure/stubs/e2e.env -f compose.yaml -f compose.minio.yaml -f compose.e2e.yaml"
$COMPOSE up -d --build --wait core-service learning-service ai-service report-api report-worker
cd frontend/web && npm ci && npx playwright install chromium && npm run test:e2e
$COMPOSE down -v
```

- `--env-file` 지정으로 개발자 `.env` 미사용
- 인프라 포트(5432·5672·6379·8080 등) 고정이라 기본 compose 스택과 동시 실행 불가
- postgres 컨테이너 이름이 다르면 `E2E_POSTGRES_CONTAINER` 지정

## 검증 결과 (NFR-QA-04 구분)

| 구분 | 수행 | 결과 |
|---|---|---|
| core 단위 테스트 | `./gradlew test --tests '*TossCircuitTest*' --tests '*PaymentProtectionTest*'` (로컬) | 5건 통과 (기본·재정의 PG 주소 테스트 포함) |
| 실서버 E2E + 스텁 | 로컬 Windows 11·Docker 29.6.1·Compose v5.1.4, 2026-11-02, develop `51f67b5`(#252·#257 반영) 기준 재실행 | 4건 통과 (37.4초, 이미지 빌드 포함 스택 기동 149초) |
| 스텁 경유 확인 | 실행 후 DB 조회 | `llm_usage` 판정·되묻기 6건 모두 모델 `e2e-stub`, 되묻기 출처 `LLM`, `payment` 3건 `APPROVED`·구독 `ACTIVE`, `report_job` COMPLETED·report_id 연결 |
| 기존 MSW 화면 테스트 | `npm run test:browser` (로컬) | 14건 통과, 변경 없음 |
| 웹 타입·린트 | `npm run test:types`, `npm run lint` (로컬) | 타입 오류 없음, 린트 경고 1건은 기존 `AdminOperations.tsx` |
| 원격 CI | `e2e.yml` (PR) | 기록 예정 |
| 실제 Google·토스·LLM | 미수행 | 범위 밖 |

## 미검증 범위

- 학생 기기 등록·PIN 로그인, Google 재인증 팝업
- 토스 결제 위젯 JS, 정기결제 등록·갱신·실패·해지·환불 경로 (toss-stub 경로만 구현)
- 분석 대화 스트리밍·리포트 템플릿 제안 (llm-stub 응답만 구현)
- 지난주 기간 cron 스케줄링 자체 (리포트 생성 명령 이후 경로만 검증)
- kind `<target>-stub` Service·NetworkPolicy egress

## PR #300 E2E 동의 문서 호환성 보완 (2026-11-03)

- [원격 실패 실행](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/actions/runs/41593418014): 스택 기동·마이그레이션은 통과했으나, 학습·결제 테스트가 가입 화면의 `E2E 이용약관에 동의합니다.`를 찾다가 시간 초과됐다. 1개 통과·2개 실패·후속 리포트 1개 미실행이었다.
- 원인: #297의 V25가 게시한 동의 문서는 2026-11-03 시행이고, 합성 시드는 2026-01-01 시행이다. 서비스는 정상적으로 최신 문서를 선택했지만 공통 가입 도우미는 오래된 합성 문서 제목 3개를 고정해서 찾았다. 이 도우미는 #289 이전에도 동일했다.
- 수정: 화면이 조회한 `/api/v1/consent-documents` 응답에서 TERMS·PRIVACY·GUARDIAN 3종과 필수 여부를 검사하고, 현재 문서 제목에 해당하는 체크박스를 각각 선택한다. 동의 저장과 자녀 등록은 기존 UI 경로로 진행한다. 서비스 코드·동의 문서·DB 마이그레이션·기능 기본값은 변경하지 않았다.
- 수정 후 로컬 검증: 새 격리 Compose 스택에 전체 마이그레이션과 기존 E2E 시드를 적용하고, 서버·웹의 이관 기능을 모두 끈 상태에서 `npm run test:e2e`의 4개 시나리오가 재시도 없이 통과했다(1.2분). 관리자 로그인, 가입·미션·돌아보기, 학부모 대시보드·리포트, 결제 승인까지 확인했다.
- 테스트 타입 검사와 수정 파일 lint도 통과했다. 위 결과는 Windows·Chrome에서의 로컬 재검증이며, Linux·Chromium 원격 CI 재실행 통과와는 구분한다. 기존 이관 전용 `tests/transfer-local` 11개와 이번 CI E2E 4개도 별도 검증이다.
