# #184 학부모 결제·구독 화면

## 기준과 범위

`feature/parent-payments-184`에서 구현했습니다. 최신 `origin/develop` cc2ccc6을 일반 merge로 반영했고 TossClient 충돌은 조회 서킷 브레이커·HTTP 테스트 주입과 새 시크릿 키 fallback을 모두 보존했습니다. 공개 API 모양은 바꾸지 않았고, 최신 core의 PaymentViewResponse·RefundRequestResponse를 소비합니다.

2026-10-30 사용자 결정: **화면·모의 검증까지 우선 PR**. 실제 토스 승인·빌링 등록 1회 검증은 후속이며 #184를 자동 종료하지 않습니다. 실결제 키는 지원하지 않습니다.

## 구현

- 서버 상품의 가격·월 청구 주기·자녀 수·이용 기능·한도·기간을 표시합니다. 무료 조건도 별도로 표시하고 임의로 무료 상품을 선택하지 않습니다.
- 연결된 자녀를 선택해 주문을 만들고 같은 자녀의 ACTIVE·RENEWAL_FAILED 구독이 있으면 구매를 제한합니다. 최종 검사는 core가 수행합니다.
- 주문 생성과 승인은 UUID 멱등 키를 유지합니다. 저장한 주문과 성공 URL의 주문번호·금액을 대조한 뒤 core 승인 API를 호출하며, `APPROVED`와 `APPLIED`가 모두 확인되어야 이용권 적용 완료로 표시합니다.
- `CONFIRMING`과 `RECOVERY_REQUIRED`는 GET 상태 조회로 확인합니다. 자동으로 새 주문·재결제를 만들지 않습니다. 실패 URL에서는 승인하지 않습니다.
- 빌링 GET의 customerKey로 SDK 인증을 시작하고 등록·변경 전에 자동 갱신 동의를 확인합니다. 콜백 고객 범위·만료를 검사하고 authKey를 core에 전달합니다. 카드 원문·paymentKey·authKey·시크릿 키는 브라우저 저장소에 남기지 않습니다.
- 구독 상태·기간·다음 청구일·갱신 금액·빌링 등록 여부, 갱신 실패 유예 종료·재시도 횟수·예정일을 서버 응답으로 표시합니다. 자동 갱신 해지와 철회는 확인 후 서버 응답을 다시 조회합니다.
- 본인 거래의 결제·취소·환불 이력과 전액 환불 요청을 제공합니다. REQUESTED·APPROVED·FAILED·COMPLETED를 서로 다르게 표시하며, 검토 중 결제수단 변경·갱신 철회를 제한합니다.
- 동의 철회·자녀 연결 해제 상태에서도 본인 거래 조회·자동 갱신 해지·환불 복구 접근을 유지합니다. 신규 구매·승인·빌링 등록·갱신 재개는 기존 서버 동의·연결 검사를 따릅니다.

## 환경 변수

루트 `.env.example`에 실제 값 없이 이름만 기록했습니다. `.env`와 기존 PDF·RunPod 변경은 PR에 포함하지 않습니다.

| 변수 | 사용 위치 |
|---|---|
| TOSSPAYMENTS_CLIENT_KEY | Vite가 공개 값만 VITE_TOSSPAYMENTS_CLIENT_KEY로 전달, test_gck_ SDK 결제위젯 |
| TOSSPAYMENTS_SECRET_KEY | core 일반결제용 TOSS_TEST_SECRET_KEY가 비어 있을 때 서버 fallback |
| TOSS_TEST_BILLING_CLIENT_KEY | Vite가 공개 값만 VITE_TOSS_TEST_BILLING_CLIENT_KEY로 전달, 별도 빌링 상점 test_ck_ |
| TOSS_TEST_BILLING_SECRET_KEY | 기존 core 빌링 전용 서버 키, 일반 결제위젯 키로 대체하지 않음 |
| TOSS_TEST_MID / TOSS_TEST_BILLING_MID | 해당 상점 ID, core가 PG 응답과 대조 |
| PAYMENT_BILLING_ENCRYPTION_KEY | 기존 빌링키 암호화 설정 |
| TOSSPAYMENTS_ENV_DIR | 별도 worktree에서 `.env`가 있는 원래 저장소 디렉터리를 Vite 실행 환경으로 지정할 때만 사용 |

기존 TOSS_TEST_SECRET_KEY가 있으면 우선하며, 일반 결제위젯 키를 빌링에 사용하지 않습니다. 키를 바꾸면 Vite·core를 재시작하거나 재빌드해야 합니다.

## 실행 모드와 검증 경계

1. 실제 core: 일반 `npm run dev`, 목업 비활성. 기존 DB·core·상품·학부모·연결 자녀와 테스트 상점 설정이 필요합니다.
2. 화면·모의 검증: `VITE_API_MOCK=true npm run dev`. 기존 MSW 인증·계정·TanStack Query를 재사용하며, 모의 결제와 빌링 인증은 앱 안에서 이동합니다. 외부 PG를 호출하지 않습니다. 별도 실패 상태 시연은 상단 상태 선택기의 결제 확인 중·갱신 실패·환불 실패를 사용합니다.
3. 실제 PG 단건 연결 확인: `npm run dev:payment -- --port 5251`. 기존 계정 화면은 가상이며, 결제창과 서버 승인은 실제 토스 테스트 API를 사용합니다. 이 localhost 전용 모드는 주문을 메모리에만 보관하고 SANDBOX_ONLY로 표시하며 실제 이용권을 부여하지 않습니다. production에 포함되지 않으며 일반 모드의 실패를 이 경로로 자동 전환하지 않습니다.

시연 고정 데이터는 `src/mocks/handlers/payments.ts`의 무료·프리미엄 상품과 가상 프리미엄 구독입니다. PG 단건 테스트 전용 상품 14,900원은 `scripts/payment-test-server.ts`의 testProduct입니다. 실제 모드는 모두 core 상품 데이터를 사용합니다.

## 검증 결과

- 최신 develop 통합 뒤 프론트 전체 **143개 테스트**, build 통과. lint 종료 코드 0이며 기존 develop의 AdminOperations.tsx:204 immutability 경고 1건은 유지했습니다.
- 모의 승인 지연·조회 복구·중복 구독·빌링 고객 위조·동일 요청 키·금액 위조·다른 보호자 접근·동의 철회 복구·환불 실패와 검토 구분·월말 청구 날짜를 테스트했습니다.
- 브라우저에서 신규 모의 주문→승인→프리미엄 반영→빌링 등록 콜백, 자동 갱신 해지·철회, 전액 환불 접수를 확인했습니다. 모의 결과에는 실제 PG가 아님을 표시합니다.
- 1440·1024·390 폭에서 가로 넘침이 없음을 확인했습니다. 캡처는 저장소 외부의 별도 결과 폴더에 보관했습니다.
- 실제 토스 테스트 키의 거래 조회 HTTP 200 및 결제수단·약관·카드사 인증창은 앞선 연결 검증에서 확인했습니다. **실제 성공 승인·빌링 발급·DB 이용권 반영은 미검증**입니다.
- TossCircuitTest에 일반 키 우선순위·widget fallback·빌링 키 분리 회귀 테스트를 추가했습니다. 로컬 core 검증은 기존 Gradle 루프백 연결 오류로 미완료이며 원격 CI 결과를 별도로 확인합니다.

## 후속

#184의 실제 토스 테스트 승인·빌링 등록 1회 완료 조건은 미체크로 유지합니다. 빌링 테스트 키와 MID·암호화 설정을 core 담당과 준비한 뒤 실제 core 저장·이용권 반영까지 확인해야 합니다. 운영 실결제와 실제 카드사 모바일 앱 전환은 이번 모의 검증 범위가 아닙니다.

참고: [토스 결제위젯](https://docs.tosspayments.com/guides/v2/payment-widget/integration), [자동결제](https://docs.tosspayments.com/guides/v2/billing/integration), [API 키](https://docs.tosspayments.com/reference/using-api/api-keys).
