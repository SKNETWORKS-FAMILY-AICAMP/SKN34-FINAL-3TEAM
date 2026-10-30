# 토스페이먼츠 결제 연결

학부모의 `이용권·결제`에서 상품을 고르고 서버 주문을 생성한 뒤, 토스 결제수단·약관을 표시합니다. 인증 성공은 결제 완료로 처리하지 않고 서버 승인 결과를 확인합니다. 자동결제 등록은 이번 범위에 포함하지 않습니다.

## 환경 변수

- 루트 `.env`의 `TOSSPAYMENTS_CLIENT_KEY`: `test_gck_`로 시작하는 결제위젯 키. Vite가 공개 클라이언트 키만 `VITE_TOSSPAYMENTS_CLIENT_KEY`로 전달합니다. 변경 후 Vite를 재시작하거나 재빌드합니다.
- `TOSSPAYMENTS_SECRET_KEY`: `test_gsk_` 키. 서버에서만 사용하며 브라우저에 전달하지 않습니다.
- core는 일반결제용 `TOSS_TEST_SECRET_KEY`가 비어 있을 때 새 시크릿 키를 사용합니다. 기존 키가 있으면 기존 값을 우선합니다. Compose에도 새 변수를 전달합니다.
- core의 `TOSS_TEST_MID`는 해당 결제 상점아이디로 설정해야 합니다. PG 승인 응답의 MID·주문·금액·통화를 기존 서버 로직이 검증합니다.
- 빌링은 기존 `TOSS_TEST_BILLING_SECRET_KEY`와 해당 MID를 별도로 사용합니다. 일반 결제위젯 키를 빌링 키로 대체하지 않습니다.
- 별도 worktree에서 원래 저장소의 `.env`를 읽어야 한다면 Vite 실행 환경의 `TOSSPAYMENTS_ENV_DIR`에 그 `.env`의 디렉터리를 지정합니다. 실제 경로·키는 커밋하지 않습니다.

## 실제 core 사용

1. DB와 core-service를 기존 Compose 절차대로 실행합니다. 상품·학부모·연결 자녀가 준비되어 있어야 합니다.
2. `frontend/web`에서 `npm run dev`를 실행합니다. API 목업을 끈 상태로 학부모 로그인 → 이용권·결제로 이동합니다.
3. `GET /products`의 서버 가격을 표시하고 `POST /orders`에 상품·자녀 ID만 보냅니다. 주문 생성·승인 모두 UUID 멱등 키를 사용합니다.
4. 토스 SDK v2의 `widgets().setAmount` → `renderPaymentMethods`·`renderAgreement` → `requestPayment`를 호출합니다.
5. `/payment/success`는 탭에 저장한 주문과 리다이렉트 주문·금액을 대조하고 `POST /payments/confirm`을 호출합니다. 실제 금액은 저장한 주문 값을 전달하며 core가 DB 값과 다시 검증합니다.
6. 서버가 `APPROVED`와 `APPLIED`를 모두 반환할 때에만 이용권 적용 완료로 표시합니다. `202/CONFIRMING`·이용권 복구 대기는 GET으로 조회하며 새 주문을 만들지 않습니다.
7. `/payment/fail`에서는 승인하지 않습니다. 새로고침한 결과 페이지는 주문번호로 조회하며, paymentKey는 주소에서 제거하고 저장소에 남기지 않습니다.

## DB 없이 토스 테스트 결제 확인

```powershell
cd frontend/web
# 같은 저장소의 루트 .env를 사용하면 다음 환경 변수는 필요 없습니다.
$env:TOSSPAYMENTS_ENV_DIR = '원래 저장소의 루트 디렉터리'
npm run dev:payment -- --port 5251
```

`http://127.0.0.1:5251/login` → 시연 계정으로 로그인 → 이용권·결제 → 테스트 이용권 선택 → 결제수단 선택 → 카드사 선택 → 결제하기 순서로 확인합니다. 카드사 인증은 소유자가 직접 수행합니다. 인증 성공 시 승인 요청과 결과 화면 이동은 자동입니다.

이 모드는 **학습·계정만 가상 데이터**, **결제창과 승인은 실제 토스 테스트 API**입니다. 주문은 1시간 동안 개발 서버 메모리에 저장되고 재시작하면 사라집니다. 가격 14,900원·테스트 상품은 검증용 고정값이며 운영 상품이 아닙니다. 승인 응답의 이용권 상태는 `SANDBOX_ONLY`로 구분하고 DB·실제 이용권을 변경하지 않습니다.

개발 서버의 `/__payment-test`는 `payment-test` 모드에서만 열리며 localhost 요청, 개별 HttpOnly 쿠키, Origin·전용 헤더, 서버 주문 금액을 확인합니다. 라이브 키는 거부하며 서버 프록시·시크릿은 production 번들에 포함하지 않습니다. **일반 개발 모드와 production에서 API 실패를 이 모드로 자동 전환하지 않습니다.**

## 검증 범위

프론트 테스트에는 리다이렉트 변조·중복 값·만료, 서버 금액 사용, 타인 주문 차단, 멱등 주문·동시 승인, PG 응답 불일치, 타임아웃 후 조회 복구가 포함됩니다. 실제 카드사 인증 후 승인·DB 이용권 반영 결과는 실행 환경과 별도로 확인해야 합니다.

2026-10-30 확인: production 빌드·린트·프론트 테스트 131개 통과, 실제 시크릿 키의 브라우저 번들 포함 여부 0건. 실제 토스 테스트 결제수단·약관·카드사 인증창 렌더링까지 확인했습니다. 본인 카드사 인증 및 PG 성공 승인 응답은 사용자 확인 대기입니다. Docker 엔진은 실행되지 않은 상태이며, core 컴파일은 Gradle의 `Unable to establish loopback connection` 환경 오류로 검증하지 못했습니다. DB 이용권 반영을 검증했다고 간주하지 않습니다.

디자인은 기존 학부모 셸과 한국어 폰트를 유지하며, 금액·자녀·이용권을 주문 확인란에 모았습니다. Achromatic ledger, seed 1509786548에서 결제 내용만 적용했고 기존 내비게이션은 유지했습니다. 태블릿에서는 주문 요약과 결제수단을 세로로 배치합니다.

참고: [토스 결제위젯 연동](https://docs.tosspayments.com/guides/v2/payment-widget/integration), [키 종류와 용도](https://docs.tosspayments.com/reference/using-api/api-keys).
