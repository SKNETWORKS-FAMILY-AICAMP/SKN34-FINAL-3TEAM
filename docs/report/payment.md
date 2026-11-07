# 결제·구독과 상품 권한 (#48·#184·#167)

토스페이먼츠 테스트 환경만 연동(실결제 키는 네트워크 호출 전 거부). 계약은 [API 명세](../design/api-spec.md) 2.6·3.5, 상태는 [상태 다이어그램](../design/state-diagram.md) 6장, 저장은 [ERD](../design/erd.md) 3.4.

## 1. 공개 기능과 호출 경계 (#48)

- 상품 목록, 주문 생성, 서버 승인, 본인 결제·구독·환불 이력, 빌링 등록/변경, 갱신 해지/철회, 정기 청구, 환불 요청·관리자 승인/반려, 관리자 거래/대조/환불 조회, 서명 웹훅
- Controller → payment service → Repository/Mapper → core_db. 다른 기능은 payment service만 사용하며 payment repository를 직접 참조하지 않음
- 주문의 구매자·현재 연결/동의·상품·확정 금액을 서버에서 검증. 승인 전에 주문 금액을 대조하고 PG 응답의 주문·paymentKey·금액·MID·KRW·상태 확인. 클라이언트 복귀 화면·웹훅 본문으로 성공을 결정하지 않음
- PAYMENT_VIEW와 PAYMENT_REFUND 구분. 환불 목록 GET은 PAYMENT_VIEW, 승인/반려 POST는 PAYMENT_REFUND

## 2. 트랜잭션과 실패 복구

| 단계 | 처리 |
|---|---|
| 주문/승인 준비 | 공통 `AccountAccessService.lockParent`로 parent 계정 행 잠금 → 소유권·자녀·상품·금액 확인 → 상품 snapshot 및 charge intent/CONFIRMING 저장 → commit |
| 외부 승인 | DB 트랜잭션·parent 잠금을 해제한 뒤 저장된 PG 요청 식별자로 호출 |
| 승인 기록 | parent 재잠금 → 현재 거래/PG 응답 검증 → APPROVED/RECOVERY_REQUIRED 저장·commit |
| 권한 반영 | 별도 parent 잠금 트랜잭션에서 구독 생성/갱신·order 연결·APPLIED 저장 |
| 환불 | REQUESTED 동결 commit → learning 증빙 HTTP 조회 → parent 재잠금·조건 재확인 → 관리자 APPROVED/cancel key commit → 외부 PG 취소 → parent 재잠금·결과 반영 |

- 공통 IdempotencyService의 HTTP 캐시와 PG 거래 멱등성을 분리. HTTP 키가 달라도 동일 거래는 기존 intent 사용. 결제·환불 4xx는 같은 HTTP 키로 동일 결과, 5xx는 캐시하지 않음. 캐시된 202는 POST 재호출로 바뀌지 않으므로 GET 결제 상태로 현재 결과 확인
- 승인 응답 유실은 CONFIRMING으로 남고 PG 조회로 복구. 승인 기록 이후 권한 DB 저장 실패는 APPROVED/RECOVERY_REQUIRED를 유지하며 추가 청구 없이 재반영. 취소 응답 유실은 환불 APPROVED 유지 후 조회로 확정. PG에 기록이 없는 미확정 준비 거래는 성공/실패로 추측하지 않고 운영 대조. 지연 DONE은 REFUNDED/CANCELED를 되돌리지 않음
- PG·learning HTTP는 트랜잭션 밖. 준비 거래·권한 복구·미처리 환불은 #45 탈퇴를 차단하며 `pendingPayments`는 미처리 환불 수와 별도로 반환

## 3. 상품·청구·해지

- 무료 상품은 `PAYMENT_FREE_PRODUCT_ID`로 명시(10/28 사용자 확정). 미지정·없음·비활성·0원 아님은 503. FREE 코드나 최신 0원 행을 추측하지 않음. 가격·features·limits는 product에서 읽고 주문/구독 snapshot으로 당시 조건 보존. 상품 데이터는 운영 입력(임의 시드 없음)
- 최초 결제일의 일자를 anchor로 보존하고 매월 같은 날(없으면 말일) KST 09시 청구. periodEnd는 다음 청구일 09시가 배타 경계(1/31 → 2월 말일 → 3/31). 최초 결제 뒤 빌링 등록 전은 autoRenew=false/nextBillingDate=null. 빌링 등록은 ACTIVE 및 유예 중 RENEWAL_FAILED에서 허용(유예·재청구 횟수 초기화 안 함)
- 월별 논리 주문 `(subscription_id,billing_period_start)` UK 유지. 확정 실패 후 일별 재청구만 새 charge attempt/PG 주문으로 기록(attempt마다 고유 PG 멱등키). 초기 실패 후 3일 유예·매일 1회 최대 3회 재청구, 불명확 attempt는 조회만. ShedLock과 DB UK/parent 잠금/last attempt date 병용
- 해지는 다음 청구를 중단하고 이미 결제한 기간 유지. PG 갱신 중 해지도 허용하며 늦은 성공 반영이 autoRenew=false를 덮어쓰지 않음. 유효 기간 전 ACTIVE 구독만 철회 가능. 빌링 발급은 외부 호출 전후 subscription.revision 대조
- 만료와 주요 결제·환불·구독 전이는 `NotificationService.payment`로 알림(기존 수신 설정·중복 방지·commit 후 Redis 전달 재사용)
- #45 복구 경계: 필수 동의 철회 후에도 본인 거래 GET·환불 POST·해지 DELETE 허용, 자녀 연결 해제 후에도 본인 구독 청구 중단 가능. 신규 구매/승인·빌링 등록·해지 철회는 현재 동의·연결 검사 유지
- 과거 snapshot/anchor가 없는 구독은 승인된 backfill 전 자동 청구하지 않음

## 4. 사용 증빙·환불 조건

- 7일은 환불 요청 시각 기준, 전액만. 승인 시 요청 당시 기간·금액·사용을 다시 확인. REQUESTED는 새 프리미엄 사용의 동결 상태. 증빙 조회 실패는 503이며 미사용으로 간주하지 않음. snapshot/charge attempt가 없는 과거 거래도 사용 근거 불명확으로 차단
- `payment_premium_usage`가 FEEDBACK/CONVERSATION/REPORT_VIEW의 RESERVED/USED 증빙 소유. 미완료 예약을 미사용으로 간주하지 않음
- 구현 예정(P14 개정, [서비스 기획 방향](service-direction.md)): 프리미엄 추가 문제 시도 `EXTRA_MISSION` 종류를 추가하고, 일일 리포트 대화는 기존 CONVERSATION으로 기록. 배포 시점부터 기존 구독자 환불 판정에도 적용
- learning의 SYSTEM+정확한 학생 scope 증빙 API가 결제 이후 DONE 및 진행 중 피드백을 실제 learning DB에서 확인(MyBatis 캐시 없이 매번 조회, 원문 미반환)
- FeedbackFacade: 답변·시도 소유권 확인 → core 사용 예약 → 판정 리스/처리·DB commit → core 완료. 응답 유실은 예약을 남겨 보수적으로 판단
- core 예약·완료 409는 Problem Details `code`로 구분(#276). `REFUND_IN_PROGRESS`·`PAYMENT_USAGE_RETRY_REQUIRES_NEW_SOURCE`·`PAYMENT_USAGE_STATE_CHANGED`는 같은 코드 409와 코드별 학생 안내, 그 밖의 409는 `PAYMENT_USAGE_UNAVAILABLE` 503
- 환불 완료는 즉시 구독 종료·무료 전환. 반려는 사용 동결 해제

## 5. 분석·리포트 권한 공급 (#41·#42)

- `ProductEntitlementService.forParent(parent,student)`: 현재 연결/동의 검사 후 product/features/limits, 구독 상태, autoRenew, periodEnd, graceUntil, refundPending, conversationEnabled, narrativeEnabled 제공. 유효 구독은 당시 snapshot 사용, 유예 동안 권한 유지. 미확정 갱신의 기간 만료를 임의 무료 전환으로 숨기지 않음
- `PaymentAnalysisEntitlementProvider`: #41 포트의 productId/dailyConversations/validUntil/conversationEnabled 공급. validUntil은 실제 KST 09시 경계. recordAttempt는 입장 트랜잭션에서 같은 parent 잠금으로 기록(재시도·실패 포함). 일별 사용 집계 저장은 `payment_premium_usage`([core-gateway](core-gateway.md#분석-대화-사용량-db-이관-구현-225))
- 구현 예정(P13 개정): FREE `limits.dailyMissions` 3 → 1(당일 테마 문제), 추가 문제는 프리미엄 기능. 일일 리포트 대화는 `dailyConversations`(30회)를 공유
- ReportEntitlementService: 과거 리포트에도 현재 권한 적용(10/28 사용자 확정). 무료 상세의 narrative/eveningQuestion은 null, 수치 유지. 기존 유료 파일은 현재 권한이 없으면 403 `REPORT_PREMIUM_REQUIRED`, 수치 전용 파일은 무료에서도 허용. URL 반환 직전 parent 잠금에서 권한과 사용 기록을 함께 확정
- 학부모 이용권 표시: `GET /api/v1/children/{childId}/entitlement`가 `forParent` 결과를 `Cache-Control: no-store`로 반환. 기본 무료 상품 미설정은 503 `PAYMENT_FREE_PRODUCT_UNAVAILABLE`, 구독이 없다는 이유로 임의 상품을 고르지 않음. 학부모 사이드바·대시보드 리포트 안내는 이 API의 상품명·한도·`narrativeEnabled`를 쓰고 `/children`의 목업 `plan`은 근거로 쓰지 않음. 자녀별 캐시 키, 오류는 이전 안내 대신 재시도 가능한 오류로 표시

## 6. PG 검증·운영 입력

- `POST /api/v1/webhooks/tosspayments`만 Bearer 예외. 원문:transmission-time의 HMAC SHA-256과 복수 v1 서명 검증, 두 테스트 상점 보안 키 지원. PG 조회 1회 후 실제 상태 반영, transmission ID와 상태 전이/알림 UK가 중복 차단
- 빌링 승인 시 웹훅이 전송되지 않으므로 조회 복구를 별도 실행
- 관리자 대조는 from/to 필수. 로컬 주문과 두 상점의 PG 거래 페이지를 비교해 MISSING_LOCAL/MISSING_PG/DUPLICATE/MISMATCH/UNKNOWN/MATCH/NO_PG_ATTEMPT 구분. 거래 목록 실패는 503, 자동 청구·취소 없음. 거래 조회 timeout 최소 60초
- 빌링 암호화: `PAYMENT_BILLING_ENCRYPTION_KEY`는 별도 무작위 32바이트 AES 키(base64), AES-GCM 저장. 카드 원문은 수신/저장하지 않음
- 하위 호출 서킷 브레이커(#167): toss-lookup과 toss-transactions 분리(일반/빌링 자격은 같은 구간 상태 공유). OPEN은 기존 Unknown/null로 연결해 상태 유지. 승인·청구·취소·빌링키 발급은 제외(PG에 보내지 않은 준비 거래는 조회만으로 확정 불가). 최근/최소 20건·실패율 50%·30초 차단·half-open 1건
- 공식 계약: [코어 API](https://docs.tosspayments.com/reference), [에러 코드](https://docs.tosspayments.com/reference/error-codes), [웹훅](https://docs.tosspayments.com/reference/using-api/webhook-events), [보안 점검](https://docs.tosspayments.com/reference/using-api/security-checklist), [빌링 연동](https://docs.tosspayments.com/guides/v2/billing/integration-api)

| 변수 | 사용 위치 |
|---|---|
| TOSSPAYMENTS_CLIENT_KEY | Vite가 공개 값만 `VITE_TOSSPAYMENTS_CLIENT_KEY`로 전달, `test_gck_` SDK 결제위젯 |
| TOSSPAYMENTS_SECRET_KEY | core 일반결제용 `TOSS_TEST_SECRET_KEY`가 비어 있을 때 서버 fallback |
| TOSS_TEST_SECRET_KEY | core 일반결제 서버 키(있으면 우선) |
| TOSS_TEST_BILLING_CLIENT_KEY | Vite가 공개 값만 `VITE_TOSS_TEST_BILLING_CLIENT_KEY`로 전달, 별도 빌링 상점 `test_ck_` |
| TOSS_TEST_BILLING_SECRET_KEY | core 빌링 전용 서버 키, 일반 결제위젯 키로 대체하지 않음 |
| TOSS_TEST_MID / TOSS_TEST_BILLING_MID | 해당 상점 ID, core가 PG 응답과 대조 |
| TOSS_TEST_WEBHOOK_SECURITY_KEY / TOSS_TEST_BILLING_WEBHOOK_SECURITY_KEY | 웹훅 서명 검증 |
| PAYMENT_BILLING_ENCRYPTION_KEY | 빌링키 암호화 |
| TOSSPAYMENTS_ENV_DIR | 별도 worktree에서 `.env`가 있는 원래 저장소 디렉터리를 Vite 실행 환경으로 지정할 때만 |

키를 바꾸면 Vite·core 재시작 또는 재빌드 필요. 문서 테스트 키 사용 시 주의 사항은 [local-platform](local-platform.md) 13장.

## 7. 학부모 결제·구독 화면 (#184)

- 서버 상품의 가격·월 청구 주기·자녀 수·이용 기능·한도·기간 표시. 무료 조건 별도 표시, 임의로 무료 상품을 선택하지 않음
- 연결 자녀를 선택해 주문 생성, 같은 자녀의 ACTIVE·RENEWAL_FAILED 구독이 있으면 구매 제한(최종 검사는 core)
- 주문 생성·승인은 UUID 멱등 키 유지. 저장한 주문과 성공 URL의 주문번호·금액을 대조한 뒤 core 승인 API 호출, `APPROVED`와 `APPLIED`가 모두 확인되어야 이용권 적용 완료 표시
- `CONFIRMING`·`RECOVERY_REQUIRED`는 GET 상태 조회로 확인(자동 새 주문·재결제 없음). 실패 URL에서는 승인하지 않음
- 빌링 GET의 customerKey로 SDK 인증을 시작하고 등록·변경 전 자동 갱신 동의 확인. 콜백 고객 범위·만료 검사 후 authKey를 core에 전달. 카드 원문·paymentKey·authKey·시크릿 키는 브라우저 저장소에 남기지 않음
- 구독 상태·기간·다음 청구일·갱신 금액·빌링 등록 여부, 갱신 실패 유예 종료·재시도 횟수·예정일은 서버 응답 그대로. 해지·철회는 확인 후 서버 응답 재조회
- 본인 거래의 결제·취소·환불 이력과 전액 환불 요청. REQUESTED·APPROVED·FAILED·COMPLETED 구분 표시, 검토 중 결제수단 변경·갱신 철회 제한
- 동의 철회·자녀 연결 해제 상태에서도 본인 거래 조회·자동 갱신 해지·환불 복구 접근 유지

실행 모드:

1. 실제 core: `npm run dev`(목업 비활성). DB·core·상품·학부모·연결 자녀와 테스트 상점 설정 필요
2. 화면·모의 검증: `VITE_API_MOCK=true npm run dev`. 외부 PG 미호출, 상단 상태 선택기로 결제 확인 중·갱신 실패·환불 실패 시연. 고정 데이터는 `src/mocks/handlers/payments.ts`
3. 실제 PG 단건 연결 확인: `npm run dev:payment -- --port 5251`. 결제창과 서버 승인은 실제 토스 테스트 API, 주문은 메모리에만 보관하고 SANDBOX_ONLY 표시, 이용권 미부여. production 미포함. 테스트 상품 14,900원은 `scripts/payment-test-server.ts`

## 8. 검증 범위와 한계

- core·learning 통합 테스트(실제 PostgreSQL·Redis·RabbitMQ, PG·learning HTTP는 계약 대역)로 금액/주문/소유권 위조, PG 응답 불일치, 동시 승인/취소, 응답 유실·권한 DB 실패 복구, 같은 기간 중복 청구, 말일·유예·3회 재청구, billing/해지 경합, 탈퇴/동의 철회 복구, 환불 조건·관리자 권한 검증
- 실제 bootJar 두 프로세스로 core→learning 증빙 조회, 환불 동결 차단, 반려 후 피드백 DONE/USED, 사용 후 409 환불 거부 확인(결제 상태는 합성 fixture)
- 실제 토스 테스트 결제 승인·구독 `ACTIVE`는 kind 환경에서 확인(#236, [local-platform](local-platform.md) 13장). 빌링 발급·정기 청구·취소·웹훅 송신은 실제 PG로 미검증
