# #48 결제·구독과 실제 상품 권한 공급

## 범위·기준

전용 `feature/core-payments` worktree에서 구현했다. 최초 기준은 origin/develop b344797, 최종 검증 기준은 `7f30c2ee0691b301d32e7ef757eff2547e73eb3a`다. 기존 checkout은 전환하지 않았다. 최신 develop 반영 전에 전체 source/sha256 백업과 stash `28b9a93f7dd5dd36eccf14b32a63f7070245f233`를 보존했고, architecture 문서의 #50/#48 내용을 함께 유지하여 충돌을 해결했다. 기능 PR base와 GitHub 실제 기본 브랜치는 develop이다.

#46 support와 #41 conversation 구현은 수정하지 않았다. 사용자 승인으로 #41 소비 인터페이스 `AnalysisEntitlementProvider.kt`만 원문 그대로 공유했다. 원본과 복사본 SHA-256은 `708b0c5651346c41b46a7577cbcf0d179cf292f71ae6f7009457e5c7806bc330`으로 일치한다. learning 최소 증빙 API·피드백 사용 예약 연결도 사용자 승인 범위에 포함된다. 새로운 production 의존성은 없다.

## 공개 기능과 호출 경계

- 상품 목록, 주문 생성, 서버 승인, 본인 결제·구독·환불 이력, 빌링 등록/변경, 갱신 해지/철회, 정기 청구, 환불 요청·관리자 승인/반려, 관리자 거래/대조/환불 조회, 서명 웹훅을 구현했다.
- Controller → payment service → Repository/Mapper → core_db. 다른 기능은 payment service만 사용하며 payment repository를 직접 참조하지 않는다.
- 주문의 구매자·현재 연결/동의·상품·확정 금액을 서버에서 검증한다. 승인 전에 주문 금액을 대조하고 PG 응답의 주문·paymentKey·금액·MID·KRW·상태를 확인한다. 클라이언트 복귀 화면·웹훅 본문으로 성공을 결정하지 않는다.
- PAYMENT_VIEW와 PAYMENT_REFUND를 구분한다. 환불 목록 GET은 PAYMENT_VIEW, 승인/반려 POST는 PAYMENT_REFUND다. 서버의 최신 계정·세션·권한 검사를 유지한다.

## 트랜잭션과 실패 복구

| 단계 | 처리 |
|---|---|
| 주문/승인 준비 | 공통 AccountAccessService.lockParent로 parent 계정 행 잠금 → 소유권·자녀·상품·금액 확인 → 상품 snapshot 및 charge intent/CONFIRMING 저장 → commit |
| 외부 승인 | DB 트랜잭션·parent 잠금을 해제한 뒤 저장된 PG 요청 식별자로 호출 |
| 승인 기록 | parent 재잠금 → 현재 거래/PG 응답 검증 → APPROVED/RECOVERY_REQUIRED 저장·commit |
| 권한 반영 | 별도 parent 잠금 트랜잭션에서 구독 생성/갱신·order 연결·APPLIED 저장 |
| 환불 | REQUESTED 동결 commit → learning 증빙 HTTP 조회 → parent 재잠금·조건 재확인 → 관리자 APPROVED/cancel key commit → 외부 PG 취소 → parent 재잠금·결과 반영 |

공통 IdempotencyService의 HTTP 캐시와 PG 거래 멱등성을 분리했다. HTTP 키가 달라도 동일 거래는 기존 intent를 사용한다. 결제·환불의 4xx는 같은 HTTP 키로 동일 결과를 반환하며 5xx는 캐시하지 않는다. 캐시된 202는 POST 재호출로 바뀌지 않으므로 GET 결제 상태로 현재 결과를 확인한다.

승인 응답 유실은 CONFIRMING으로 남고 PG 조회로 복구한다. 승인 기록 이후 권한 DB 저장 실패는 APPROVED/RECOVERY_REQUIRED를 유지하며 추가 청구 없이 재반영한다. 취소 응답 유실은 환불 APPROVED를 유지하고 조회로 확정한다. PG에 기록이 없는 미확정 준비 거래도 성공/실패로 추측하지 않으며 운영 대조가 필요하다. 단건 결제 GET은 불명확 환불도 조회 복구한다. 지연 DONE은 REFUNDED/CANCELED를 되돌리지 않는다.

PG·learning HTTP는 트랜잭션 밖에서 실행한다. 준비 거래·권한 복구·미처리 환불은 #45 탈퇴를 차단한다. PG 호출 중 계정 잠금을 유지하지 않는다. 기존 활성/기간 내 구독 차단을 유지하고 환불 완료 및 KST 기간 경계와 정렬했다. pendingPayments는 미처리 환불 수와 별도로 반환한다.

## 상품·청구·해지

2026-10-28 사용자 확정: 무료 상품은 `PAYMENT_FREE_PRODUCT_ID`로 명시한다. 미지정·존재하지 않음·비활성·0원 아님은 503이다. FREE 코드나 최신 0원 행을 추측하지 않는다. 가격·features·limits는 product에서 읽고 주문/구독 snapshot으로 당시 조건을 보존한다. 승인된 상품 데이터는 운영 입력이며 임의 상품 시드를 만들지 않았다.

최초 결제일의 일자를 anchor로 보존하고 매월 같은 날(없으면 말일), KST 09시에 청구한다. periodEnd는 다음 청구일의 09시가 배타 경계이며 1/31 → 2월 말일 → 3/31로 복원한다. 최초 결제 뒤 빌링 등록 전은 autoRenew=false/nextBillingDate=null이다. 빌링 등록은 ACTIVE 및 유예 중 RENEWAL_FAILED에서 허용하며 유예·재청구 횟수를 초기화하지 않는다.

월별 논리 주문 `(subscription_id,billing_period_start)` UK를 유지한다. 확정 실패 후 일별 재청구만 새 charge attempt/PG 주문으로 기록한다. 각 attempt는 고유한 PG 멱등키를 보존한다. 초기 실패 후 3일 유예·매일 1회 최대 3회 재청구하며, 불명확한 attempt는 조회만 한다. ShedLock과 DB UK/parent 잠금/last attempt date를 함께 사용한다.

해지는 다음 청구를 중단하고 이미 결제한 기간을 유지한다. PG 갱신 중 해지도 허용하며 늦은 성공 반영이 autoRenew=false를 덮어쓰지 않는다. 유효 기간 전 ACTIVE 구독만 철회할 수 있다. 빌링 발급은 외부 호출 전후 subscription.revision을 대조하므로 발급 중 해지를 늦은 응답이 취소하지 못한다. 만료와 주요 결제·환불·구독 전이는 NotificationService.payment를 통해 알리고 기존 수신 설정·중복 방지·commit 후 Redis 전달을 재사용한다.

#45 복구 경계로 필수 동의 철회 후에도 본인 거래 GET·환불 POST·해지 DELETE를 허용한다. 자녀 연결 해제 후에도 본인 구독 청구를 중단할 수 있다. 신규 구매/승인·빌링 등록·해지 철회에는 현재 동의·연결 검사를 유지한다.

## 사용 증빙·환불 조건

7일은 환불 요청 시각 기준이며 전액만 지원한다. 승인 시 요청 당시 기간·금액·사용을 다시 확인한다. REQUESTED는 새 프리미엄 사용의 동결 상태다. 증빙 조회 실패는 503이며 미사용으로 간주하지 않는다. snapshot/charge attempt가 없는 과거 거래도 사용 근거 불명확으로 차단한다.

- `payment_premium_usage`는 FEEDBACK/CONVERSATION/REPORT_VIEW의 RESERVED/USED 증빙을 소유한다. 미완료 예약을 미사용으로 간주하지 않는다.
- learning의 SYSTEM+정확한 학생 scope 증빙 API는 결제 이후 DONE 및 진행 중 피드백을 실제 learning DB에서 확인한다. MyBatis 캐시를 사용하지 않고 매번 조회한다. 원문은 반환하지 않는다.
- FeedbackFacade는 답변·시도 소유권 확인 → core 사용 예약 → 판정 리스/처리·DB commit → core 완료 순서다. 다른 자녀의 답변으로 사용 예약을 만들지 못한다. 응답 유실은 예약을 남겨 보수적으로 판단한다.
- 환불 완료는 즉시 구독 종료·무료 전환이다. 반려는 사용 동결을 해제하며 확정 실패와 불명확 취소를 구분한다.

## #41·#42 권한 공급

`ProductEntitlementService.forParent(parent,student)`는 현재 연결/동의를 검사하고 product/features/limits, 구독 상태, autoRenew, periodEnd, graceUntil, refundPending, conversationEnabled, narrativeEnabled를 제공한다. 유효 구독은 당시 snapshot을 사용하고 유예 동안 권한을 유지한다. 미확정 갱신의 기간 만료를 임의 무료 전환으로 숨기지 않는다.

payment의 `PaymentAnalysisEntitlementProvider`는 #41 포트의 productId/dailyConversations/validUntil/conversationEnabled를 공급한다. validUntil은 실제 KST 09시 경계다(#41 초안의 자정 표기와 구분). recordAttempt는 입장 트랜잭션을 요구하고 동일 parent 잠금에서 기록한다. #41 계약에 따라 분석 입장 시도(재시도·실패 포함)를 사용으로 기록한다. conversation 실행·Redis 일별 카운터 자체는 #41 소유다.

ReportEntitlementService를 실제 공급자에 연결했다. 2026-10-28 사용자 추가 확정에 따라 과거 리포트에도 현재 권한을 적용한다. 무료 상세의 narrative/eveningQuestion은 null, 수치는 유지한다. 기존 유료 파일은 현재 권한이 없으면 403 REPORT_PREMIUM_REQUIRED이며 수치 파일 생성 전까지 제공하지 않는다. 수치 전용 파일은 무료에서도 허용한다. 파일 메타데이터가 식별한 동일 불변 reportId를 사용하고 URL 반환 직전 parent 잠금에서 권한과 사용 기록을 함께 확정한다.

## PG 검증·운영 입력

POST /api/v1/webhooks/tosspayments만 Bearer 예외다. 원문:transmission-time의 HMAC SHA-256과 복수 v1 서명을 검증하고, 두 테스트 상점 보안 키를 지원한다. PG 조회 1회 후 실제 상태를 반영하며 transmission ID와 상태 전이/알림 UK가 중복을 막는다.

관리자 대조는 from/to를 요구한다. 로컬 주문과 두 상점의 PG 거래 페이지를 비교해 MISSING_LOCAL/MISSING_PG/DUPLICATE/MISMATCH/UNKNOWN/MATCH/NO_PG_ATTEMPT를 구분한다. 거래 목록 실패는 503이며 자동 청구·취소하지 않는다. 공식 거래 조회의 최소 60초 timeout을 사용한다.

- 환경/Secret: TOSS_TEST_SECRET_KEY, TOSS_TEST_BILLING_SECRET_KEY, 각 TOSS_TEST_*MID, TOSS_TEST_WEBHOOK_SECURITY_KEY, TOSS_TEST_BILLING_WEBHOOK_SECURITY_KEY.
- 빌링 암호화: PAYMENT_BILLING_ENCRYPTION_KEY는 별도의 무작위 32바이트 AES 키(base64). AES-GCM으로 저장하고 카드 원문은 수신/저장하지 않는다. 실결제 키는 네트워크 호출 전 거부한다.
- 과거 snapshot/anchor가 없는 구독은 승인된 backfill 전 자동 청구하지 않는다. V13은 보존하고 #46 V14를 확인해 신규 V15를 추가했다. 병렬 브랜치 통합 시 번호·적용 순서를 확인해야 한다.

공식 계약 확인(2026-10-28): [코어 API](https://docs.tosspayments.com/reference), [에러 코드](https://docs.tosspayments.com/reference/error-codes), [웹훅](https://docs.tosspayments.com/reference/using-api/webhook-events), [보안 점검](https://docs.tosspayments.com/reference/using-api/security-checklist), [빌링 연동](https://docs.tosspayments.com/guides/v2/billing/integration-api). 빌링 승인 시 웹훅이 전송되지 않으므로 조회 복구를 별도로 실행한다.

## 최종 검증

- JDK21 core 전체 226개, learning 전체 187개: 실패/오류/건너뜀 0. 양쪽 test·bootJar 성공. bytecode major 65, 실제 공급자/클라이언트 포함, Testcontainers/JUnit/Mockito/Flyway 등 test-only 라이브러리 미포함을 확인했다.
- 실제 격리 PostgreSQL 전체 마이그레이션 주기: core 42테이블/376컬럼, learning 19/156, report 6/44. 위반 입력 57건, CHECK 값 집합 68개, ERD 인덱스 23개. 재실행 이력 불변·report downgrade/upgrade·빈 DB 재검사 통과(65.2초). 공유 DB는 사용하지 않았다.
- 실제 Redis를 사용한 PAYMENT_CHANGED/SUBSCRIPTION_CHANGED 중복 방지·commit 후 전달 검증 포함.
- 금액/주문/소유권 위조, PG 응답 불일치, 동시 승인/취소, 응답 유실·권한 DB 실패 복구, 같은 기간 중복 청구, 말일·유예·3회 재청구, billing/해지 경합, 탈퇴/동의 철회 복구, 실제 report/analysis 공급자·환불 조건·관리자 권한을 검증했다.
- 계약 스크립트 56개 및 core/learning OpenAPI 표준 검사 통과. 실제 MockMvc 결제 응답 5종·알림 2종, 실제 RabbitMQ report 봉투/데이터 4종·리포트 상세 JSON을 OpenAPI/공유 계약과 대조했다.
- 실제 bootJar 프로세스 두 개와 전용 PostgreSQL/Redis/RabbitMQ에서 core→learning 증빙 조회, 환불 동결의 learning→core 차단, 관리자 반려 후 core→learning→core 피드백 DONE/USED, 사용 후 409 환불 거부, 실제 구독 기반 탈퇴 차단, paid/free 리포트 Outbox narrativeEnabled=true/false를 확인했다. 이 검사의 결제 상태는 합성 DB fixture이며 PG 호출은 없다. CHOICE 규칙을 사용하여 LLM도 호출하지 않았다.
- 검증 도중 디스크 부족·Docker 중단·손상된 전용 Gradle 캐시가 있었으며 복구 후 고정 source/sha256 기준으로 최종 실행했다. Mockito null matcher, 다운로드 열람 기대값, 테스트 풀 연결 수, 공유 문서 fixture 격리, 별도 동시성 컨텍스트 대역 누락·사용 증빙 캐시를 수정한 뒤 재검증했다. production DB 풀 설정은 변경하지 않았다.
- 런타임/계약/테스트 source가 검증 후 바뀌지 않았음을 manifest로 확인했다. 최종 문서·링크·diff 검사를 함께 수행한다.

## 한계와 PR 준비

실제 토스 테스트 키가 없어 실제 PG 승인·빌링 발급/청구·취소·서명 웹훅 송신은 미검증이다. PG 대역과 합성 결제 fixture 검증을 실제 PG 결과로 표현하지 않는다. 실제 Google 인증·#41 전체 대화/AI 흐름·실제 report worker 렌더링·배포·원격 CI는 이 작업의 통과 결과에 포함하지 않는다. 프론트는 변경하지 않았다.

PR은 사용자가 생성한다. base develop, head feature/core-payments. 제목은 `feat: 토스 테스트 결제·구독과 상품 권한 공급 구현`, 본문은 `Closes #48`을 포함한다. 현재 등록 설명으로 확인한 후보는 enhancement(New feature or request), area:core, area:learning이며 기존 P2는 우선순위 후보로 유지할 수 있다. Type 등록 값은 저장소 API 404·조직 API 401로 확인하지 못해 추정하지 않는다. feature push만으로는 현재 core/learning CI가 실행되지 않으며 PR 생성 후 CI를 확인해야 한다.


## 2026-10-29 임시 통합 base 준비

- 사용자 지시로 최신 develop `c608f52aa0f7b651133603a629a8347be61b3282`에서 `feature/core-support-payments-integration`을 생성·push했다. 기존 feature/core-integration과 develop checkout/이력은 변경하지 않았다. #48 head는 feature/core-payments, #46 head는 feature/core-support다. PR 생성은 사용자가 수행한다.
- #46 채팅에 새 base·기준 SHA·기반영 보존 원칙·V14/V15 순서·최종 develop PR의 Closes 필요를 전달했다. 이 base 대상 병합은 기본 브랜치 병합이 아니므로 이슈 자동 종료로 안내하지 않는다.
- #48에 새 base를 일반 merge로 반영했다. 충돌은 PostgresRepositoryTest.kt와 core OpenAPI 2곳이다. 풀 설정 파일은 기반영 base의 원문(최대 5/min idle 0)을 그대로 보존했다. 결제 스키마와 DashboardRecordReflection을 함께 유지했다.
- 기반영 API 경로 60개·스키마 79개와 공통 components/root metadata를 대조했다. 기존 사용자 승인 범위인 ReportDownload 설명 외에 기반영 정의를 교체하지 않았고, #48 추가 경로·스키마도 모두 보존했다. 결과 경로 77개·스키마 99개, YAML 중복 키 없음이다. FeedbackFacade의 결제 사용 예약/완료와 #79 최종 답 요소·AI rubric 필터 변경이 함께 유지된다.
- 추가 기반영 production 로직 수정은 하지 않았다. 아래 검증은 이 통합 결과를 대상으로 수행하며 결과를 이어 기록한다.


### 임시 base 통합 검증 결과

- JDK21 core 전체 **241개**, learning 전체 **190개**, 양쪽 test/bootJar 성공. 실패·오류·건너뜀 0. 실제 PostgreSQL/Redis/RabbitMQ 및 기존 인증·결제·알림·리포트·대시보드·피드백 회귀를 포함한다. 이 통합 실행은 PG/learning HTTP 계약 대역과 실제 서비스 검증 범위를 구분한다.
- 계약 스크립트 60개와 core/learning OpenAPI 표준 검사 통과. 실제 결제 응답 5종·알림 2종·report 이벤트 4종 및 HTTP 상세의 계약 대조 통과. 검증된 runtime/contract/test source와 작업 트리 sha256 일치 확인.
- 격리 PostgreSQL 전체 migration cycle 통과(50.3초): core 42테이블/376컬럼, learning 19/158, report 7/50. 위반 입력 60건, CHECK 값 집합 70개, ERD 인덱스 23개. 재실행 이력 불변 및 report downgrade/upgrade 후 재검사 통과. #46 V14는 아직 이 base에 없으므로 양쪽 기능이 함께 병합된 후 최종 DB 검사가 추가로 필요하다.
- 기반영 풀 설정 파일은 새 base와 동일하며, 기반영 경로·스키마 보존 검사도 통과했다. 추가 production 로직 수정·기존 커밋 이력 재작성·develop 직접 push·PR 생성은 하지 않았다.
- #46 채팅이 새 base용 PR 준비 문서 갱신·push(6604844)를 완료한 것을 확인했다. #46 먼저 새 base에 병합할 수 있으며, 그 뒤 #48의 공통 파일 충돌 여부를 다시 확인해야 한다. 실제 PG/Google·배포·원격 CI의 미검증 조건은 유지한다.


## 2026-10-29 #46 PR #120 병합 후 #48 접합

- PR #120이 feature/core-support에서 feature/core-support-payments-integration으로 병합된 것을 GitHub merged 상태와 통합 base 8883528로 확인했다. develop 직접 병합이 아니다.
- #48 head e3cbec3에 통합 base를 일반 merge했다. 충돌은 PublicAuthFilter.kt, NotificationService.kt, state-diagram.md 3곳이다.
- #46의 인증된 도움말/공지 계약은 그대로 보존하고 #48의 정확한 POST 웹훅 예외만 추가했다. support 알림 함수·수신자/동의 검사는 원문 그대로 유지하고 payment 알림 함수를 별도로 접합했다. 상태 문서는 양쪽 설명을 모두 유지했다.
- 기반영 API 경로 74개·스키마 94개 및 공통 components/root metadata를 대조했다. 이전 사용자 승인 범위인 ReportDownload 설명 외에는 기반영 정의를 교체하지 않았다. #48 정의도 보존했으며 병합 결과 91개 경로·114개 스키마, 중복 YAML 키 없음이다.
- learning은 #48의 이전 190개 통과 source와 동일하다. frontend는 #46에서 검증한 통합 base 원문과 같으며 #48에서 수정하지 않았다. 따라서 양쪽을 반복 실행하지 않는다. 이번 영향 범위는 core 전체·계약/실제 JSON·V14/V15 동시 DB 적용이다. 결과를 이어 기록한다.


### #46·#48 공존 검증 결과

- JDK21 core 전체 **258개** test·bootJar 통과, 실패·오류·건너뜀 0. #46 지원·#48 결제·기존 인증/알림/대시보드/리포트/피드백 회귀를 함께 실행했다. 실제 PostgreSQL/Redis/RabbitMQ는 격리 Testcontainers, PG·learning 외부 공급자 HTTP는 계약 대역이다.
- 계약 스크립트 **65개**와 OpenAPI 표준 검사 통과. 실제 MockMvc 지원 7종·결제 5종·알림 2종, report 이벤트 4종 및 HTTP 상세 JSON 계약 대조 통과.
- V14/V15 동시 전체 migration cycle·ERD 검사 통과(64.8초): core 42테이블/390컬럼, learning 19/158, report 7/50. 위반 입력 60건, CHECK 값 집합 74개, ERD 인덱스 23개. 재실행 이력 불변 및 report downgrade/upgrade 재검사 통과.
- runtime/test/contract/frontend source sha256 일치, 충돌 마커·unmerged path 없음, git diff --check 통과. learning 190개와 #46 frontend 92개/lint/build 결과는 source 변경이 없어 반복 실행하지 않고 앞선 검증 범위를 유지했다.
- #46 지원 알림과 인증/공개 계약은 그대로 보존했고 추가 기반영 production 로직을 바꾸지 않았다. #48 작업 브랜치에만 일반 merge commit을 추가하며 이력 재작성·통합 base 직접 수정·develop push·PR 생성은 하지 않는다.
- 현재 PR base는 feature/core-support-payments-integration이다. Closes #48은 이 중간 base 병합만으로 자동 종료되지 않으며, 실제 해결 범위를 확인한 최종 develop 통합 PR에도 필요하다. 실제 PG·Google·#41 전체 대화/AI·배포·원격 CI 미검증 조건은 유지한다.

## #167 하위 호출 서킷 브레이커 (2026-10-30)

toss-lookup과 toss-transactions를 분리하며 일반/빌링 자격은 같은 구간 상태를 공유한다. OPEN은 기존 Unknown/null로 연결해 상태를 유지한다. 승인·청구·취소·빌링키 발급은 제외한다. PG에 보내지 않은 준비 거래는 조회만으로 확정할 수 없기 때문이다. 재청구·취소 재전송·새 복구 정책은 추가하지 않는다.

최근/최소 20건·실패율 50%·30초 차단·half-open 1건. 신규 production 의존성·오류 코드·Retry-After 없음. 최종 검증 결과는 아래와 같다.

최종 검증: JDK 21 전용 Docker에서 `bash gradlew test bootJar --no-daemon --max-workers=1 --no-watch-fs --console=plain -Pkotlin.compiler.execution.strategy=in-process "-Dorg.gradle.jvmargs=-Xmx640m -XX:ActiveProcessorCount=2" -I /workspace/limits.gradle` 성공(17분 22초). 54개 클래스/346개 테스트, 실패·오류·생략 0. 검증 전용 init script는 test heap 640MiB·fork 1·8개 클래스마다 fork 교체·Spring context cache 4·CPU 2로 제한하며 저장소 실행 설정/테스트 제한 시간은 변경하지 않았다. `python -O -m unittest discover -s scripts/tests -p 'test_*contract.py' -v` 31개, `test_*openapi.py` 35개 통과. 실행한 core Kotlin/YAML/SQL 260개 파일이 최종 로컬 소스와 바이트 단위로 일치했다. `git diff --check` 통과.

core HTTP·DB/Redis/RabbitMQ 통합 테스트이며 AI/report는 로컬 HTTP 대역, PG는 HttpClient/TossGateway 대역이다. 실제 AI·report 프로세스·토스 API 호출, 브라우저·원격 CI·운영 배포·성능 측정은 이번 검증에 포함하지 않는다. 기존 분석/결제 사용량·복구 흐름은 전체 테스트와 변경 없음 대조로 확인했다. 통합 브랜치 a5b72f7의 factory 선택 인자와 AI HTTP/1.1 변경을 보존했고, #168 d6ebee1에는 TossClient 변경이 없어 직접 파일 충돌이 없음을 읽기 전용으로 확인했다.
