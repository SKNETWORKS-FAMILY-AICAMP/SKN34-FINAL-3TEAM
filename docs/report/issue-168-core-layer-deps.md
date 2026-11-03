# #168 core 레이어 의존 정리

## 범위와 결정

[점검 기록](audit.md) 3.7 A3·A4에서 찾은 core의 아키텍처 2.1·2.2 위반 7건을 정리한다. 기준은 develop `d651aa1`이다.

| 위반 (develop) | 정리 |
|---|---|
| `conversation/domain/Conversations.kt`가 `HttpStatus`로 `BusinessException` 생성 | domain은 `ErrorKind`만 넘기고 상태 변환은 `_common/exception` |
| `payment/domain/Payments.kt`가 Jackson `JsonNode`·`@JsonIgnore` 사용 | `JsonObject` 값 타입, PG 키는 응답 DTO에서 뺌 |
| `usage/service/LlmUsageService` → `usage.consumer.LlmUsageRecorded` (Application → Presentation) | `LlmUsageRecorded`를 `usage/domain`으로 |
| `payment/client/PremiumUsageClient` → `PaymentTransactions.unavailable` (Infrastructure → Application) | client 안 `unavailable` (기존 `TossClient` 방식) |
| `notification/messaging/NotificationRedisSubscriber`가 Infrastructure 위치에서 service 호출 | `notification/consumer`로, 구독 연결은 `notification/config` |

확인 필요 항목(domain에서 HttpStatus 허용 여부)은 learning #169와 같이 **허용하지 않음**으로 정했다. 방식도 #169와 같다(B1: `BusinessException`에 오류 종류를 받는 보조 생성자). 응답(code·status·본문)은 바뀌지 않는다.

## 정한 내용

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 오류 종류 | core `ErrorKind { INVALID, NOT_FOUND, CONFLICT }` → 400·404·409. learning의 `ErrorKind`(400·409·422)를 그대로 쓰지 않고 core domain이 실제로 쓰는 종류만 둠 | `Conversations.kt`의 `invalid`·`missing`·`conflict`가 400·404·409. 새 종류가 필요하면 `ErrorKind`와 변환을 함께 늘림 |
| 결제 응답 경계 | `payment/controller/PaymentResponses.kt`의 `RefundRequestResponse`(cancelKey 없음)·`PaymentViewResponse`(환불 목록도 DTO)를 결제 확인·상태·목록·환불 요청·관리자 결제/환불 목록·승인·반려가 내보냄. 멱등 저장본(`idempotency_record.response_body`)도 DTO를 직렬화. 칸 이름·순서는 기존 domain 직렬화와 같음 | develop은 domain 객체를 그대로 직렬화하고 `@JsonIgnore`만으로 `cancelKey`를 막았음(테스트 없음). annotation만 지우면 바로 노출 |
| 로그 보호 | `Payment`·`RefundRequest`에 `toString` 재정의(키 없음). 기존 `Subscription`과 같은 방식 | `@JsonIgnore`는 `toString`을 막지 못했음. 기존 로그는 id·code만 남기지만 앞으로의 실수를 막음 |
| `JsonNode` 대체 | `_common/json/JsonObject`(프레임워크 없는 `Map<String, Any?>` 값 타입). Jackson 변환은 `JsonObjectJsonComponent`, MyBatis 변환은 `JsonObjectTypeHandler`를 이 타입에만 등록 | `Map`을 쓰려면 `java.util.Map` 변환기를 전체 등록해야 하는데, `PostgresTypeHandlers`·[db-dev-guide](db-dev-guide.md) 2장이 "Any·Map 전체 등록 금지". 진행 중인 #47 같은 다른 mapper에 영향이 갈 수 있음 |
| 읽는 곳 의미 | `JsonNode` 검사를 같은 의미로 옮김: `isIntegralNumber && canConvertToInt` → `is Int`(Jackson은 int 범위 정수를 Int로 읽음), `isIntegralNumber` → `Int·Long·BigInteger`, `intValue()` → `(as? Number)?.toInt() ?: 0`, `isBoolean` → `is Boolean`. `treeToValue`·`valueToTree` → `convertValue` | `PaymentService`(상품 조건), `ProductEntitlementService`(권한), `PaymentAnalysisEntitlementProvider`(분석 권한), `RenewalService`(청구 금액), `PaymentTransactions`(스냅샷 상품) |
| `LlmUsageRecorded` | `usage/domain/LlmUsageRecorded.kt`로 옮김(내용 그대로). RabbitMQ 수신 JSON은 타입 정보 없이 메서드 인자로 변환해 패키지 이동과 무관 | 이슈 해야 할 일 2 |
| 증빙 client | `PremiumUsageClient`가 같은 code·문구(`REFUND_USAGE_UNAVAILABLE`, 503)로 자기 `unavailable`을 던짐 | 기존 `TossClient.unavailable`과 같은 방식 |
| 알림 구독 | `NotificationRedisSubscriber` → `notification/consumer`, `NotificationRedisConfiguration`(구독 연결·채널 이름) → `notification/config`. 클래스 이름·동작 그대로 | Subscriber만 옮기면 `messaging → consumer` 역참조가 새로 생김. 여러 레이어를 묶는 연결은 기존 `account/config`·`learning/config`처럼 `<기능>/config` |

새 계층은 없다. 새 공통 타입은 `JsonObject` 하나다(값 타입, 공통 라이브러리 아님).

## 파일

- 새 파일: `_common/json/JsonObject.kt`·`JsonObjectJsonComponent.kt`, `payment/controller/PaymentResponses.kt`, `usage/domain/LlmUsageRecorded.kt`, 테스트 `conversation/ConversationDomainErrorTest`·`payment/PremiumUsageClientTest`
- 옮긴 파일: `notification/messaging/NotificationRedisSubscriber.kt` → `notification/consumer/`, `notification/messaging/NotificationRedisConfiguration.kt` → `notification/config/`
- 기존 파일 수정: `_common/exception/BusinessException.kt`(보조 생성자·`ErrorKind`), `_common/persistence/PostgresTypeHandlers.kt`·`PersistenceConfig.kt`(`JsonObjectTypeHandler` 등록), `conversation/domain/Conversations.kt`, `payment/domain/Payments.kt`, `payment/controller/PaymentController.kt`, `payment/service/`(`PaymentService`·`PaymentTransactions`·`ProductEntitlementService`·`PaymentAnalysisEntitlementProvider`·`RenewalService`), `payment/client/PremiumUsageClient.kt`, `usage/consumer/LlmUsageConsumer.kt`, `usage/service/LlmUsageService.kt`, `notification/messaging/NotificationRedisPublisher.kt`(채널 이름 import)
- 다른 팀원 테스트 수정(타입·위치 변경으로 꼭 필요한 곳만): `admin/ModelVersionHttpTest`·`usage/LlmUsageQueryTest`(`LlmUsageRecorded` import), `notification/NotificationIntegrationTest`(옮긴 두 클래스 import), `conversation/ConversationPaymentIntegrationTest`(테스트 상품을 `JsonObject`로), `payment/PaymentIntegrationTest`(`limits[...]` 비교 1줄, 새 테스트 3개)
- 설계 문서: class-diagram 1장 공통 표(`ErrorKind`)·3.3(`NotificationRedisSubscriber` `<<consumer>>`, 위치)·3.4(응답 경계·`JsonObject`), architecture 패키지 트리(`_common/json`, notification). api-spec·OpenAPI는 응답 모양이 같아 변경 없음

## 검증

- 레이어 import 재검사(audit 3.7 기준 스크립트: domain 프레임워크·다른 레이어 import, Application → Presentation, Infrastructure → Application/Presentation, Presentation → repository): develop 7건 → 이 브랜치 이슈 대상 0건. learning 0건
- core 테스트 335개 통과(새 6: 대화 domain 오류 상태, 결제·환불 응답과 멱등 재생·저장본·`toString`의 PG 키 없음, 반려 응답, 상품 조건 숫자·불리언 규칙, 증빙 client 503). scripts/tests 83개(일반·`-O`)
- 응답 모양: 결제 실제 응답 5종(상품·주문·결제 확인·구독·환불 후 상태)을 develop에서 만든 응답과 칸 이름·타입·중첩 구조까지 비교해 같음. 계약 검사 `validate_payment_contracts`·`validate_notification_contracts`·`validate_report_contracts`·`validate_support_contracts` 통과
- 같은 의미 확인: 새 테스트 중 develop에서도 컴파일되는 것(상품 조건 규칙, 대화 domain 오류, PG 키 응답·반려, 증빙 client)을 develop 원본(`JsonNode`·`HttpStatus`·`@JsonIgnore`)에서도 돌려 모두 통과. `toString` 확인만 develop에서 실패(새로 막은 것)
- 보호 장치 14개: 하나씩 틀리게 하면 각각 실패(`INVALID`·`NOT_FOUND`·`CONFLICT` 변환, 환불 DTO에 `cancelKey` 추가, 승인·상태 응답을 domain 객체로, `Payment.toString`, 상품 조건 정수, 권한의 int 범위 밖 정수, 분석 권한 int, 청구 금액, `JsonObject` DB·JSON 변환 등록, 증빙 client 503)

## 확인 필요

- 진행 중 작업과 합치기
  - #162 `origin/feature/ai-analysis-verification`과 합치면 `Conversations.kt`만 충돌(실제 merge-tree로 확인). 해결: `EvidenceRow`는 #162 줄(`answerId`·`answerVersion` nullable, `kind`), 아래 `invalid`·`missing`·`conflict` 세 줄은 이 브랜치(`ErrorKind`) 줄. import는 자동으로 합쳐짐
  - #47 미커밋 구현은 볼 수 없어 겹침을 확인하지 못함. 합친 뒤 core 전체 테스트와 계약 검사를 다시 돌려야 함
- 이번 기준보다 엄격한 검사에서 1건이 더 나옴: `notification/messaging/NotificationRedisPublisher`(커밋 후 이벤트 수신·Redis 발행)가 `NotificationDeliveryService.record`를 부름(Infrastructure → Application). 이슈·audit A4 목록 밖이고 #47 `NotificationRetryService`가 이 Publisher를 직접 써서 이번에는 바꾸지 않음. core 담당자 판단 필요
- service에서 Jackson `convertValue`를 쓰는 것은 develop의 `treeToValue`·`valueToTree`와 같은 자리(db-dev-guide "Jackson 변환은 Infrastructure 안에서만"과 원래부터 다름, 이번에 늘리지 않음)
- db-dev-guide 2장 표(jsonb ↔ `JsonNode`)에 "domain이 드는 jsonb 객체는 `JsonObject`" 한 줄을 더할지는 문서 담당 확인 필요

## #249 domain 예외 분리 (core·learning, 11/02)

[점검 기록](audit.md) 4.5 A8: domain이 `BusinessException(ErrorKind…)`을 던지고 `BusinessException`이 Spring `HttpStatus` 필드를 가져, domain이 간접적으로 프레임워크에 의존했다(#168·#169 한계 "예외 객체는 실행 중 HTTP 상태를 들고 있음"). 그 사이 core `report/domain/ReportTemplate.kt`는 `HttpStatus.BAD_REQUEST`를 직접 쓰는 회귀가 있었다.

### 정한 내용

| 항목 | 내용 | 근거 |
|---|---|---|
| domain 예외 | 각 서비스 `_common/exception/DomainException(kind, code, title, detail)`: Spring 타입 없음. `ErrorKind`도 이 파일로 옮김(core `INVALID·NOT_FOUND·CONFLICT`, learning `INVALID·CONFLICT·UNPROCESSABLE`, 값은 그대로) | 아키텍처 2.1 Domain 프레임워크 의존 금지, 이슈 해야 할 일 1 |
| 상태 변환 | `_common/exception/ErrorStatus.kt`의 `statusOf(kind)` 한 곳. `GlobalExceptionHandler.handleDomain`이 같은 Problem Details 형식으로 응답 | 아키텍처 2.3 예외 → 응답 변환은 `_common/exception` |
| 상태·code 읽기 | `errorInfoOf(Throwable)`(+`httpStatusOf`·`errorCodeOf`)가 `BusinessException`·`DomainException`을 같게 다룸. 예외에서 상태·code를 읽던 곳을 이 함수로 바꿈 | 이슈 해야 할 일 4 |
| `BusinessException` | `ErrorKind` 보조 생성자 제거(domain 밖 사용 0건). application·presentation 전용 | 이슈 해야 할 일 5 |
| domain 파일 | core `conversation/domain/Conversations.kt`(3곳), `report/domain/ReportTemplate.kt`(`HttpStatus.BAD_REQUEST` → `ErrorKind.INVALID`, 400 그대로). learning `AnswerContent`·`Attempt`·`Judgment`·`Mission`(`MissionPublishIncompleteException` 포함)·`Period` 10곳 | 이슈 해야 할 일 2 |

### 예외를 잡는 곳 (응답 code·status 유지)

domain 예외가 더는 `BusinessException`이 아니므로, `BusinessException`을 잡던 곳 중 domain 예외가 도달하는 곳은 함께 처리해야 응답이 바뀌지 않는다. core 16곳·learning 전부를 호출 경로로 따라가 확인했다.

| 위치 | domain 예외 도달 | 바꾼 것 |
|---|---|---|
| core `conversation/service/AnalysisStreamService` 98·101행 | 예(대화 domain `invalid`·`missing`·`conflict`를 쓰는 `ConversationService`를 스트림 안에서 부름) | `errorCodeOf`·`httpStatusOf`. 이슈 목록에는 101행만 있었음 |
| core `conversation/scheduler/ConversationRetryWorker` 42행 | 예(`ConversationAdminRetryService.claim`) | `errorCodeOf`. 이슈 목록에 없던 곳 |
| core `admin/service/OperationRetryService` 대화 분기 | 예(`ConversationAdminRetryService.request`의 충돌·없음) | `catch(BusinessException)` → `RuntimeException`을 잡고 `errorInfoOf`가 null이면 다시 던짐. 실패 감사·응답 그대로. 이슈 목록에는 `.status`만 있었음 |
| core `_common/security/PublicAuthFilter` | 사실상 아님(MVC 처리기가 먼저 처리) | `DomainException` catch 추가, 같은 Problem 응답. 뒤의 `DataAccessException` catch 순서 유지 |
| core `learning/controller/FeedbackController`, `payment/controller/PaymentController` | 아님 | 이슈 목록대로 `errorInfoOf`로 통일(`RuntimeException`을 잡고 아니면 다시 던짐) |
| learning `mission/controller/AdminMissionController` 게시 누락 처리기 | 예(`MissionPublishIncompleteException`이 domain 예외) | `statusOf(error.kind)` |
| core `StudentDeviceController`(`StudentPinFailure`)·`RetryableRequestException`, learning `AttemptController`(`DraftConflictException`)·`FeedbackController`(`AiUnavailableException`) | 아님(`BusinessException` 하위 클래스 전용 처리기) | 그대로 `ex.status`. 이슈 목록에 있었으나 domain 예외가 올 수 없어 바꿀 이유가 없음 |
| 나머지 core `catch`·`as?`(인증·결제·learning 프록시·리포트 복구 등) | 아님 | 그대로 |

### 이슈와 다른 점

- 이슈 목록에 없던 `AnalysisStreamService` 98행·`ConversationRetryWorker` 42행·`OperationRetryService`의 catch 범위를 고침(위 표, 호출 경로 확인 결과)
- `BusinessException` 하위 클래스 전용 처리기 4곳은 `ex.status` 유지(위 표)
- 상태 변환 함수 이름은 `statusOf`, 읽기 함수는 이슈의 `httpStatusOf`에 `errorInfoOf`·`errorCodeOf`를 더함(code·title·detail도 같이 필요한 곳이 있어서)
- #169는 별도 domain 예외를 두지 않기로 했었다(같은 code를 service도 던져 처리기·테스트가 갈리고 HTTP 상태 확인을 잃음, learning 보고서 13절). 이번에는 처리기는 공통 함수로 묶고, service 테스트는 `httpStatusOf`·`errorCodeOf`로 HTTP 상태까지 그대로 확인해 그 걱정을 피함

### 테스트

- domain 테스트는 `kind`·`code` 확인으로: core `ConversationDomainErrorTest`, learning `AnswerContentTest`·`JudgmentTest`·`MissionTest`·`RecordDomainTest`
- service 테스트는 던진 층과 관계없이 `httpStatusOf`·`errorCodeOf`로 HTTP 상태·code 확인 유지: learning `AnswerServiceTest`·`AttemptServiceTest`·`AttemptFinishTest`·`AdminMissionServiceTest`·`FeedbackFacadeTest`·`AttemptConcurrencyTest`
- 새 `ErrorStatusTest`(core·learning): 오류 종류별 상태(이전 값과 같음), 두 예외 모두 같은 응답 내용, 처리기의 Problem Details
- 바꾼 catch 지점 3곳은 기존 테스트가 확인하지 않아(되돌려도 대화 테스트 전부 통과) 새로 추가:
  - core `AdminConversationRetryTest` "HTTP retry of an already admitted message keeps the domain conflict as 409 with a failure audit": `POST /admin/jobs/{id}/retry`(`OperationRetryService`)에서 domain 충돌이 409 `ANALYSIS_IN_PROGRESS`·실패 감사 1건
  - core `ConversationDomainErrorPathTest`: 스트림(`AnalysisStreamService`)·재처리 작업(`ConversationRetryWorker`)이 domain 충돌의 code(`ANALYSIS_IN_PROGRESS`)를 실패 기록에 넘김. 실패 기록 SQL 조건이 충돌 조건과 같아 DB로는 볼 수 없어 서비스는 가짜로 둠
  - 세 곳을 `catch(BusinessException)`·`(ex as? BusinessException)`으로 되돌리면 위 테스트가 각각 실패함을 확인
- 기존 테스트의 `assertFailsWith<BusinessException>`이 domain 예외를 받던 곳: `ConversationIntegrationTest`(중복 질문·동시 재시도), `AdminConversationRetryTest`(동시 키, `httpStatusOf`로 202·409 유지), `ReportTemplateSettingsTest`(`ErrorKind.INVALID`·code)

### 검증

- 최신 develop(`92d522b`, #267~#271 머지 후) 위에서 core `./gradlew test bootJar` 455개 통과, learning `./gradlew test bootJar` 282개 통과
- core·learning domain 패키지의 `BusinessException`·`org.springframework` 참조 0건, `BusinessException(ErrorKind…)` 0건
- 그사이 develop에 들어온 코드(#267·#270)에 예외를 잡거나 `.status`를 읽는 곳이 새로 없음을 확인
- 추가 3곳을 원래 코드로 되돌리면 새 테스트가 각각 실패함을 확인(위 테스트 절)
- scripts/tests 통과, `git diff --check` 통과
