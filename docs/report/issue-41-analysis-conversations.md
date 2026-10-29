# 이슈 #41 분석 대화 계약

기준: origin/develop b344797. PR base develop. #46 support·#48 payment 쓰기와 분리한다.

## 확정 정책
- core가 conversation/message/evidence UUID를 생성한다. AI messageId는 신뢰하지 않는다.
- 기본 기간은 Asia/Seoul 오늘 포함 7일이다. scope를 본문에 명시하면 해당 범위에 대한 사용자 확인으로 취급한다. 자녀 변경은 새 대화를 만들고, 기간 변경은 scope.changed=true로 명시한다. 이력은 정확히 동일한 자녀·기간의 완료 메시지 최근 10쌍(20 turn, 질문/답변)만 전달한다.
- SSE status→delta*→result 또는 clarification 또는 error→done. delta는 저장하지 않는다. result는 scope 일치·verification 둘 다 true·source 및 근거 식별자 형식을 검사한다. 숫자/인용 대조·TEMPLATE 생성은 AI 책임이다. 완료 이벤트를 받을 때까지 result를 임시 보관하고 done 이후 DB 확정 후 공개한다. EOF·잘못된 순서·중복 terminal은 실패다.
- 첫 AI 이벤트 20초, 전체 120초. heartbeat 15초는 첫 응답에 포함하지 않는다. 연결 종료·권한 소실·삭제·시간초과 시 HTTP body를 닫고 작업 thread를 interrupt한다. 피드백은 기존대로 취소하지 않는다. 실패는 같은 message 행 FAILED, retry_count로 시도 fencing한다.
- 보호자 계정→학생→대화 잠금으로 시작/확정/취소를 직렬화한다. 동시에 하나의 RUNNING만 허용한다. 삭제된 행은 UPDATE만 하므로 재생성하지 않는다. 권한 확인과 전송은 짧은 트랜잭션 안에서 삭제와 직렬화한다. 네트워크가 지연되면 해당 트랜잭션도 지연될 수 있다.
- 사용 한도: 대화 생성은 권한/0 한도 확인만 하고 차감하지 않는다. 새 질문 및 재시도마다 AI 호출 직전 자녀별 KST 일자 Redis 카운터를 Lua로 원자 증가한다. 실패·취소·clarification도 실제 호출 시도 비용이므로 환급하지 않는다. AI 호출 전 거부는 차감하지 않는다. 키 analysis:daily:v1:{childId}:{yyyy-MM-dd}, 만료 다음 KST 자정+1일(진행 중 요청 유예). 무제한 암묵값 없음. Redis 장애 503.

## payment 공급 계약 (#48)
#41은 conversation.service.AnalysisEntitlementProvider 소비 port만 선언한다. 구현 bean은 #48 소유다. fun entitlement(parentId: UUID, childId: UUID): AnalysisEntitlement. 반환 productId: UUID, dailyConversations: Int(product.limits.dailyConversations, 0 무료 차단), validUntil: Instant?(무료 null 가능). 음수·누락·만료는 503. 구현이 없으면 PAYMENT_ENTITLEMENT_UNAVAILABLE 503. 무료·프리미엄·유예·해지 기간 판정과 상품 선택은 payment가 소유한다. repository 직접 참조·가짜 상품·성공 fallback 없음. premium 사용 추적은 실패/취소도 포함한 시도이며 향후 환불 판단 공급 연결은 #48과 통합 검증해야 한다.

## 내부 AI·learning 계약
POST /internal/analysis/stream: {conversationId,messageId,question,scope:{studentId,from,to},history:[{role:USER|ASSISTANT,text}]}.
X-Internal-Token 및 검증된 PARENT context를 기존 InternalRestClientFactory로 전달하고 studentScope는 대상 하나로 축소한다. 사용자 임의 헤더는 사용하지 않는다. 내부 result scope는 studentId, 공개 응답은 childId다(호환을 위해 내부 childId도 수용하되 동일 UUID 필수).
근거는 ID만 저장. LearningRecordService를 통해 /internal/records/evidence?answerIds=... 조회하고 현재 권한/삭제/ID를 다시 검사한다. learning quote를 공개 quote로 매핑한다. 삭제된 근거는 available:false만 표시하며 다른 원문으로 대체하지 않는다.

## 외부 구현 상태
초기 b344797에는 #27 실제 기록 API만 있고 AI 분석 라우터가 없었다. 최신 7f30c2e에는 실제 AI 분석 라우터가 포함돼 전송 계약을 대조했다. 최종 TEMPLATE 검증 메타데이터·돌아보기 근거 참조의 차이는 아래 통합 조건을 따른다. 실제 AI 전체·payment 연동 완료를 뜻하지 않는다.

## 검증
최종 최신 develop 7f30c2e 기준 JDK 21 전체 **212/212 통과**(37개 클래스, 실패/오류/건너뜀 0), bootJar 성공이다. 기존 알림 6개·SseEmitters 4개와 피드백 회귀를 포함한다. core 검증은 전용 컨테이너 CPU 2, Gradle heap 768MiB, test heap 512MiB/fork 1/Netty loop 2 제한으로 수행했다. 실행은 test bootJar --no-daemon --max-workers=1 --no-watch-fs --console=plain과 검증 전용 init script를 사용했고 저장소의 production 설정은 변경하지 않았다. 최종 BUILD SUCCESSFUL(10m5s), 전체 XML·JAR·로그를 외부 issue41-verification 폴더에 보존했다.

- 격리 JDK 21.0.12.1 Linux에서 core 전체 test·bootJar 실행. 첫 전체 실행은 209개 중 207개 통과, 2개 실패였다. ConversationIntegrationTest의 동시 재시도 Future 대기 3초 초과와 기존 NotificationIntegrationTest의 Redis 최초 handshake 300ms 초과다. 전자는 테스트 대기만 20초로 변경했고 제품 제한(20/120초)은 유지했다. 기존 알림 테스트는 변경하지 않았다. 최종 전체 결과는 아래에 기록한다.
- Python 계약 검사 56개 통과, OpenAPI 3.1 표준 검사 통과. actual evidence 응답도 OpenAPI JSON Schema로 검증했다.
- 전용 PostgreSQL 전체 cycle 통과: core 40테이블/351컬럼, learning 19/156, report 6/44. 제약 위반 입력 57건 거부, CHECK 값 집합 65개·ERD 인덱스 23개 확인, 반복 migration 이력 불변, report downgrade/upgrade 후 재대조 통과. 공유 compose DB는 사용하지 않았다.
- frontend 초기 test 75개 통과, oxlint 통과, tsc/Vite build 통과. 500KB chunk 경고는 남으며 이 작업에서 별도 번들 최적화는 하지 않았다.
- Chrome·기존 MSW 가상 계정으로 범위 확인 → 확인 선택 → 확정 TEMPLATE 답변/실제 표시 기간/근거 모달을 확인했다. 전역 자녀 변경 시 이전 대화 결과가 사라지고 해당 자녀의 새 대화 화면으로 바뀌는 것도 확인했다. 브라우저 대역 검증이며 실제 AI·결제·Google 로그인을 뜻하지 않는다.
- 실제 #27 연결: 격리된 실제 core JAR → 실제 learning JAR → 각 PostgreSQL에서 본인 근거 원문/버전/ID 조회, 타 보호자 404, 위조 messageId 404, learning 학생 범위 위조 403, 답변 물리 삭제 후 available:false와 quote 제거를 확인했다. 재현 스크립트는 scripts/verify_analysis_evidence.py이며 issue41_core/issue41_learning DB 이름을 강제한다. AI와 payment 공급자가 없어도 저장된 근거 조회 생산자/소비자 검증은 실제 구현으로 수행했다.
- 실제 AI(#65~#67), #48의 payment→AnalysisEntitlementProvider adapter·환불 경합 통합, 원격 CI·배포는 미검증이다. 미연결 provider는 production에서 503이며 테스트 공급자를 production에 등록하지 않는다.

- #41은 신규 production 의존성·DB migration을 추가하지 않는다. TEMPLATE fallback.reason은 기존 COMPLETED 행 failure_code에 보존하고 공개 실패 코드는 FAILED에서만 노출한다. 저장 확정 이후 연결 종료는 이미 완료된 메시지를 FAILED로 되돌리지 않는다. 원문 전송은 emitter lock→DB 잠금 순서로 삭제와 직렬화하며, 외부 AI/learning HTTP는 DB 트랜잭션 밖에서 호출한다.

## #48 병렬 초안 확인과 연결 조건 (통합 이전 기록)
#48 worktree의 ProductEntitlementService 초안을 읽어 당시 공급 모양을 확인했다(이 절은 공급자 병합 전 기록이다). forParent(parent,student)의 product.id·product.limits.dailyConversations·conversationEnabled·periodEnd/graceUntil을 AnalysisEntitlement로 투영하는 adapter는 payment가 공급한다. conversationEnabled=false(환불 진행 포함)는 한도와 무관하게 차단한다. validUntil은 ACTIVE periodEnd의 KST 자정(배타), RENEWAL_FAILED graceUntil 다음 날 KST 자정이며 무료는 null이다.
recordAttempt(parent,child,sourceId)는 같은 parent 잠금 트랜잭션에서 beginUsage(...,"CONVERSATION",sourceId)와 finishUsage(...,true)를 호출해야 한다. 차감 대상은 성공 답변이 아닌 처리 시도이므로 실패/취소도 보존한다. 새 질문/재시도마다 별도 source UUID를 생성한다. 이 port에 default 구현은 없다. 실제 #48 adapter/환불 경합 통합은 별도 검증 조건이며, 미연결 상태는 503이다. 상대 worktree는 수정하지 않았다.

프론트 최소 연결: 다른 자녀 clarification 선택 시 onScope로 명시적으로 전역 자녀·기간을 전환한다. ParentWorkspace의 범위 key 변경으로 기존 스트림을 취소하고 새 대화를 시작한다. 같은 자녀의 기간 선택은 기존 scope 확인 요청을 사용한다.

현재 실제 /children은 프론트 목업의 plan 값을 제공하지 않는다. plan 누락을 무료로 단정하여 질문 UI를 숨기던 조건을 제거하고, core의 실제 상품/구독 권한·한도 응답을 기준으로 차단한다. 무료임이 표시된 경우 안내는 유지하며 서버 검사를 우회하지 않는다. 프론트 source 타입도 LLM_RETRY를 포함한다.

## 공개 응답 보완과 운영 경계
대화 목록은 본인·현재 연결 자녀의 최신 100개를 반환하며 상세는 소유 conversationId로 조회한다. 목록은 답변 본문을 싣지 않으므로 프론트는 비어 있는 messages 배열을 실제 질문 수로 표시하지 않는다. 구독 만료 후에도 현재 소유/연결/동의가 유효하면 저장된 본인 이력은 조회하며 신규 분석은 상품 권한을 다시 검사한다.

## PR 준비 초안
대상 SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM, base develop, head feature/core-analysis-conversations. 실제 기본 브랜치도 develop으로 확인했다. PR은 사용자가 생성한다.
제목: feat: 분석 대화 SSE·이력과 분석 사용 한도 구현

```markdown
Closes #41

학부모 분석 대화의 생성·목록·상세·질문 SSE·실패 재시도·근거·예시 질문 API를 구현합니다.

- core 소유 ID·확정 범위 이력, 매 요청의 소유권·현재 연결·동의 검사
- 임시 delta와 검증된 result 분리, heartbeat·첫 응답 20초/전체 120초·취소·FAILED 보존
- 실행 세대 fencing·삭제와 전송/저장 경합 방지, 실제 learning 근거 조회
- product.limits 소비 계약과 자녀별 Redis KST 일 한도, 실패/취소/재시도 차감 정책
- 프론트의 상품 값 누락 차단 오류와 자녀 범위 전환 최소 연결

검증: core JDK 21 전체 212개·bootJar, 프론트 82개·lint·build, Python 계약 56개·OpenAPI 표준 검사 통과. 실제 알림/리포트 JSON·이벤트 계약과 실제 core→learning 근거 조회도 확인했습니다. DB DDL 변경이 없어 앞선 전체 migration cycle 결과를 유지합니다.

연동 조건: payment adapter 미연결 시 503으로 차단합니다. 최신 AI의 검증 메타데이터 null/false인 TEMPLATE 및 answerId 없는 돌아보기 근거는 공개 검증·참조 계약을 충족하지 않아 실패 처리합니다. 실제 AI 전체·payment/환불 통합, 원격 CI·배포는 미검증입니다.
```

등록 라벨은 공개 API로 확인했다. 추천은 enhancement(New feature or request)와 area:core(core 영역)이며 기존 이슈의 P0은 필요하면 유지한다. 조직 Type 공개 API는 401로 등록값을 확인하지 못했으므로 특정 Type이 등록됐다고 추정하지 않는다. PR 메타데이터는 설정하지 않았다.

## 최신 develop 통합 (2026-10-28)
7f30c2e로 작업 브랜치만 fast-forward했다. 변경 전 26개 파일을 외부 검증 폴더 ZIP·SHA256과 stash에 보존했으며 재적용 충돌은 없었다. 최신 실제 AI에 맞춰 history를 최근 10쌍/20 turn의 {role,text}, 질문 1,000자로 정렬했다. clarification은 {reason,message,current}를 공개 {question,options:[],reason,current}로 변환하고 EOF 종료를 인정한다. 사용자에게 없는 자녀·기간 선택지를 만들어 주지 않으며 질문 수정 또는 상단 범위 변경으로 확인한다. 일반 result의 부분 스트림은 여전히 done이 없으면 실패다. AI의 answerVersion이 null이면 현재 learning 응답의 실제 버전을 사용하며 ID/기간 검사는 유지한다.

최신 AI 공급자 제한: verification이 null/false인 TEMPLATE와 answerId가 null인 돌아보기 근거는 현재 공개 검증/DB 참조 계약을 충족하지 않아 AI_INVALID_RESPONSE로 실패한다. core는 이를 검증 성공·임의 답변 ID로 바꾸지 않는다. AI의 최종 TEMPLATE 검증 메타데이터 및 돌아보기 참조 저장 계약은 공급자와 추가 정렬이 필요하며 실제 AI 전체 연동 완료로 안내하지 않는다. AI의 수치·인용 대조나 규칙 문장 생성은 이 core 작업에 추가하지 않았다.

최종 브라우저에서 무료 생성 거부 후 입력이 RUNNING으로 남는 경로를 발견해 catch에서 FAILED·임시 출력 제거로 정리했다. 한도/공급자 오류가 나도 영구 대기 화면으로 남지 않고 질문을 수정해 다시 시도할 수 있다.

## PR 준비 최종 확인
- 최종 프론트 82/82·lint·build 성공, 번들 500KB 경고만 남는다. 브라우저에서 1,000자 제한, 무료 429 후 입력 재활성화, clarification 뒤 수정 질문 전송을 추가 확인했다(MSW).
- 실제 테스트 산출물의 알림 목록·설정 JSON, report 4종 RabbitMQ 봉투/데이터, core report 상세 JSON의 최종 OpenAPI/이벤트 schema 대조를 통과했다. bootJar 89개 라이브러리에 Testcontainers/JUnit/Mockito/Flyway가 포함되지 않음을 확인했다.
- 최신 develop 반영 후 DB migration 파일과 DDL은 변경되지 않았다. 새 production 의존성·migration이 없다.
- 원격 CI·배포는 실행하지 않았다. PR은 생성하지 않으며 사용자가 develop 대상 PR을 생성한다.

## PR #114 최신 develop 충돌 해결 (2026-10-29)

PR base는 develop이며, origin/develop c608f52를 기존 feature/core-analysis-conversations에 일반 merge한다. 이전 기능 커밋 f30db4d는 보존하고 squash/rebase/history rewrite를 하지 않는다. 로컬·원격 main은 97b0f0f로 새 파일 변경이 없으며 main은 수정하지 않았다. 병합 전 Git bundle을 저장했다.

충돌 파일은 LearningRecordClient.kt, LearningRecordService.kt, contracts/openapi/core-service.yaml 3개다. develop의 #40 대시보드 메서드·조회 검증·생성자·의존성과 공개 명세를 보존하고 #41 evidence 메서드·Analysis 경로/스키마만 접합했다. 두 Kotlin 파일에서 #41 추가 메서드를 제거하면 develop 원문과 동일하며, OpenAPI 역시 #41 추가 블록을 제거하면 develop 원문과 동일함을 대조했다. develop의 모든 operation/schema와 #41 분석 operation/schema가 그대로 유지된다. 이미 반영된 조회 로직이나 계약을 수정하지 않았다.

자동 병합된 SseEmitters의 heartbeat 설정 주입과 기존 피드백/알림 동작, #40 테스트 연결 풀 제한, 최신 learning/report 변경을 그대로 유지한다. 별도 production 의존성·migration을 추가하지 않는다. 프론트 UI 수동 수정은 없고 parent DTO의 자동 병합 결과를 대조한다. 실제 AI TEMPLATE/돌아보기 및 payment 공급자 연결 조건은 이전 기록과 동일하다.

최종 통합 검증: JDK 21 core 전체 227/227 통과(39개 클래스, 실패/오류/건너뜀 0), test bootJar 단일 실행 BUILD SUCCESSFUL(8m32s)이다. #41 대화 통합 15개·AI HTTP/SSE client 5개·한도 계약 2개, #40 대시보드 통합 13개, 알림 통합 6개·SseEmitters 4개와 기존 피드백 회귀를 함께 실행했다. 실제 PostgreSQL·Redis·RabbitMQ와 AI/learning HTTP 대역을 구분하며 실제 AI 전체 연결을 의미하지 않는다.

Python 계약 검사 60개와 core OpenAPI 3.1 표준 검사, 실제 알림 목록/설정 JSON·리포트 4종 이벤트 봉투/데이터·HTTP 상세 응답의 최종 명세 대조가 통과했다. bootJar의 Testcontainers/JUnit/Mockito/Flyway 제외도 확인했다. 프론트 전체 87개 테스트·전체 oxlint·tsc/Vite build 통과이며 기존 500KB 청크 경고는 남는다. 별도 UI 수동 수정이 없어 브라우저 검증은 이번에 반복하지 않았다.

현재 core DB의 전체 Flyway는 Testcontainers로 적용했다. 이번 변경에서 learning/report 코드·migration은 develop 원본 그대로 받았으며 해당 서비스 전체 테스트·DB 전체 cycle·실제 AI/payment 연동·배포는 추가 실행하지 않았다. 이전 실행 결과를 이번 실행 결과로 합산하지 않는다. 테스트 XML·JAR·로그·요약은 외부 검증 폴더의 merge-20261029-*에 보존했다. 기존 실제 AI/payment 연동 제약은 유지된다.

## develop c44ace8·최신 이슈 대조 (2026-10-29)

PR #127의 경로 정규화·리포트 오류/스케줄 격리·V14 SPEECH 제거와 보고서 통합을 기존 로직 그대로 받는다. 기존 topic 보고서와 설계 본문은 수정하지 않고 #41 부록만 유지한다. 이제 공통 근거는 auth-account.md, core-gateway.md, learning.md, ai.md, report.md, audit.md를 사용한다. 이미 삭제·통합된 옛 보고서를 복원하지 않는다.

GitHub #41·#27·#65·#66·#67·#48·#39·#44·#45 본문과 전체 댓글을 대조했다. #41의 최근 수정은 완료 체크 갱신이며 신규 기능 요구 추가는 없다. #41의 'AI 미구현' 및 #65~#67의 미완료 표기는 실제 develop의 AI 라우터/그래프 구현과 다르므로 상태/체크 여부만으로 구현 여부를 판단하지 않는다. #45의 기존 댓글은 1단계 삭제·재인증·student.deleted 계약이며 현재 #41 삭제 경합 정책과 일치한다. 원격 이슈 본문·댓글은 수정하지 않았다.

확인된 #41 보완: P08의 기간 내 집계 대상 시도는 시작일 이전 최초 답변도 비교 기준으로 사용할 수 있다. 이전 답변은 evidence의 학생/시도/답변/버전·종료일을 검증한 뒤 기존 LearningRecordService.parentDashboard의 기간별 attempts 목록에 해당 시도가 실제 포함되는지 확인한다. 상세 API는 기간을 자르지 않으므로 포함 여부 확인용으로 사용하지 않는다. 존재하지 않거나 기간 밖인 시도, 종료일 이후 답변, 조회 실패는 확정하지 않는다. 집계·숫자·인용 재계산은 core에 추가하지 않는다.

AI verification.contentAllowed가 명시되어 false/잘못된 형식이면 다른 두 대조 값이 true여도 #41에서 확정하지 않는다. 값이 없는 기존 두 플래그 계약은 보존한다. AI·learning·공통 필터·기존 조회 service 로직은 바꾸지 않고 #41 코드/명세/회귀 테스트만 보완한다. 정규화 URL에서 #41의 인증·역할·소유권·SSE 거부도 직접 확인한다. TEMPLATE/돌아보기 참조 및 payment 공급자 미연결 조건은 아직 해소되지 않았다.

## 검증 중 추가 병합된 develop 13a6376 반영 (2026-10-29)

c44ace8 통합 체크포인트는 core 233개·front 87개·계약 60개 통과였다. 최종 확인 중 PR #126이 병합돼 13a6376이 새 기준이 되었고 #46·#48·#47·#119 코드가 포함됐다. 수동 파일 8개를 ZIP·SHA256과 Git bundle로 보존·검증한 뒤 미커밋 병합만 재시작했다. Git 이력과 기존 커밋은 바꾸지 않았다. 새 develop에 없는 #41 source/test/report만 복원했고, 새로 반영된 문서/OpenAPI는 원문 바이트를 유지한 채 #41 블록만 추가했다.

#48·#46 이슈는 추가 확인 시 closed로 변경됐다. 실제 PaymentAnalysisEntitlementProvider가 현재 #41 포트와 동일한 인터페이스를 구현하므로 'payment 공급자 미연결'은 이제 과거 상태다. 유효 시각은 공급자의 실제 KST 09:00 경계이며, 앞선 초안의 자정 표기는 사용하지 않는다. 분석 Redis 일 카운터는 별도 KST 자정 경계를 유지한다. payment·support·관리자·프로필의 이미 반영된 로직은 수정하지 않는다.

#41 테스트에 공급자를 mock하지 않는 별도 실제 통합 경로를 추가했다. 실제 product/subscription PostgreSQL fixture·Spring payment provider·입장 트랜잭션·Redis·core HTTP/SSE를 사용하고 AI 응답만 HTTP 대역, PG와 정기 청구는 테스트 대역이다. 무료 0 한도 차단, 상품 설정 불가 503, 상품 데이터 한도 2회·실패도 USED 사용 이력, 초과 재시도의 추가 차감/사용 이력/AI 호출 방지, 자동갱신 해지 예약 상태 유지·유예·만료·09시 경계를 확인한다. 이 검증은 실제 PG 승인/청구·실제 AI·환불 경합 전체 흐름 검증이 아니다. production에 가짜 상품이나 공급자는 추가하지 않았다.

13a6376 기준 core 314개 전체 통과(실패·오류·건너뜀 0), test bootJar 성공(6m24s). 실제 payment 공급자 연결 테스트 4개를 포함한다. 계약 76개·OpenAPI 표준 검사, frontend 93개·lint·build 통과. 실제 PG·실제 AI 전체·환불 경합 전체 흐름은 이번 검증에 포함하지 않았다.
