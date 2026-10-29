# #47 관리자 운영 구현

최초 기준은 원격 재조회한 `8883528aa763809a93119c8c4cb160c7d032b5c6`, base `feature/core-support-payments-integration`, head `feature/core-admin-operations`다. develop `c608f52aa0f7b651133603a629a8347be61b3282`를 포함한다. 기존 checkout은 전환하지 않고 전용 worktree를 만들었다. origin은 팀 원본, upstream은 없다.

사용자가 PublicAuthFilter의 정확한 overview/audit GET 두 경로만 ADMIN 역할로 여는 변경을 승인했다. 다른 기존 로직·마이그레이션·공개 계약은 보존한다. 새 관리자 응답은 frontend 목업의 updatedAt·errorDetail 등을 만들어 채우지 않는다. 사용자 추가 승인으로 프론트 운영 타입·API·화면·해당 목업을 실제 응답에 연결한다. 미션 집계는 미연결로 표시하고 서버의 retryable 조건으로 재처리 버튼을 제어한다. #43 계약 테스트의 전체 /admin 가정은 승인받아 본래 모델·AI 사용량 경로로 한정한다.

설계: controller → admin service → 기능별 operations service → 각 소유 테이블 repository. execution/audit은 admin repository가 조회한다. learning 통계/미션은 learning 기능 service → 기존 LearningClient → InternalRestClientFactory다. 다른 서비스 DB를 조회하지 않는다. 큐는 읽기 전용 관리 HTTP이며 별도 환경 변수로 설정한다. production 의존성·DDL 추가 없음.

재처리: REPORT의 regenerate는 새 판/새 작업 생성이다. report-service GenerationService/get_or_create는 같은 jobId가 FAILED면 재생성하지 않고, core ReportLifecycleService도 종료 상태를 보존한다. 따라서 기존 job 재처리와 동치로 취급하지 않는다. CONVERSATION은 통합 기준에 삭제 service만 있고 관리자 실행 공급자가 없다. 둘 다 명시적인 JOB_RETRY_UNAVAILABLE로 남긴다. Notification은 기존 publisher/DeliveryService를 호출하고 외부 Redis 발행을 트랜잭션 밖에 둔다. 기존 감사·리포트·알림·공통 멱등성 구현을 재작성하지 않는다.

learning stats는 #27 실제 구현·OpenAPI가 존재한다. 관리자 미션 공급자는 기준 브랜치에 없다. 프록시의 HTTP 계약은 테스트 대역으로 확인하며 실제 learning 콘텐츠 관리·미션 상태 집계 연결은 후속이다. #41/#48 병렬 worktree와 파일은 변경하지 않는다. 새 migration을 만들지 않아 V14/V15 번호를 사용하지 않는다.

최종 구현·검증은 아래 #48 병합 반영 후 결과를 따른다.

## #48 병합 반영

사용자 추가 지시에 따라 origin을 다시 fetch했다. PR #121/#48 병합 기준 `85bf107`을 확인하고 미커밋 38파일을 ZIP·SHA-256·binary diff 및 stash `49abc61ef023771a3f856204f628c5e67e0b60df`로 보존했다. 전용 브랜치만 최신 통합 기준으로 fast-forward한 뒤 재적용했다. PublicAuthFilter는 #48의 결제 복구·POST 웹훅 예외·GET 환불 조회 PAYMENT_VIEW를 그대로 보존하고 승인된 두 GET 예외만 접합했다. OpenAPI는 최신 통합 문서 원문에 #47 신규 경로·스키마만 추가했다. #43 테스트 한정 수정은 #48에도 같은 내용이 반영되어 최신 기준을 유지했다. 이력 재작성은 없다. 최종 검증 기준은 `85bf107`이다.

## 최종 검증 (2026-10-29)

최종 base/HEAD는 `85bf1079c34a3e713bcf5eedf0cfdfd7822dc5a4`이며 종료 전 원격 재조회와 같다. 이전 기준의 실패/중단 실행은 합산하지 않았다.

| 검증 | 실행 결과와 경계 |
|---|---|
| JDK 21 core | Temurin 21 전용 Linux 소스/캐시 볼륨에서 `bash gradlew test bootJar --no-daemon --max-workers=2 --no-watch-fs --console=plain -Pkotlin.compiler.execution.strategy=in-process`와 검증 전용 CPU/메모리 제한으로 실행. 44클래스 **270개 통과**, 실패·오류·생략 0, BUILD SUCCESSFUL(7m26s). #47 신규 12개와 #48 결제·기존 신고/계정/리포트/알림/인증 회귀 포함. |
| 새 관리자 통합 테스트 | 실제 JWT/MVC/PostgreSQL·Redis로 권한/기간/목록/실제 ID/이력/민감 문자열 제거, 같은 키 응답 재현·다른 키 동시 실행 방지, 실행/감사 원자 저장, 트랜잭션 밖 발행을 검사. Redis 실패 결과 시나리오는 기존 publisher를 테스트 spy로 바꾼 대역이며 실제 Redis 성공과 구분한다. |
| 큐 관리 | 별도 RabbitMQ 4.3.7 관리 API에 실제 definitions를 적용하고 `/`의 25큐를 조회. 별도 HTTP 대역으로 인증 오류·잘못된 JSON·누락 큐·5초 타임아웃을 확인. 테스트 관찰만 통계 준비를 기다리며 production 자동 재시도는 없음. |
| learning 프록시 | 테스트 HttpServer로 stats 계약/장애와 미션 10종 메서드·경로·본문·ADMIN 사용자·빈 학생 범위·내부 토큰을 검사. 422 코드/필수 누락 필드 보존과 자유형 상세 제거, 공급자 404→503 확인. 실제 learning 관리자 API 실행은 아님. |
| 프론트 | `npm test` **93/93**, `npm run lint`, `npm run build` 통과. build는 기존 크기 경고(500kB 초과)를 보고하며 이번 범위 밖 번들 분할은 하지 않음. 실제 연결에서 발견한 빈 미션 필터를 생략하도록 고친 뒤 최종 일괄 검증을 다시 통과. |
| 실제 브라우저 연결 | VITE_API_MOCK=false, headless Chrome → 전용 Vite → 실제 최종 core JAR → 별도 PostgreSQL/Redis/RabbitMQ. SERVICE_OPS/CONTENT/PAYMENT_VIEW 화면의 6개 시나리오, 관리자 API HTTP 응답 13건, pageerror 0, service worker 응답 0. 알림 재처리 완료·실제 감사·25큐·권한 403·미션 503 표시 확인. 로그인 부트스트랩만 합성 JWT 응답 대역이고 core는 실제 DB 세션으로 검증. overview의 learning은 명시적 테스트 HTTP 대역, Google/실제 learning 검증이 아님. |
| 계약 | `python -O -m unittest discover -s scripts/tests -v` **69/69**, core OpenAPI 3.1 표준 검사 통과. 브라우저에서 받은 실제 overview/jobs/job/queues/audit 응답 5종을 `scripts/validate_admin_operations_contracts.py`로 공개 스키마와 대조해 통과. 통합 기준의 기존 경로·스키마 값 보존 검사 포함. |
| DB·소스·JAR | #47 DDL 변경 없음. 별도 빈 DB에 기존 13개 마이그레이션(V1~V9,V12~V15) 적용 성공; 전체 ERD/downgrade cycle을 이번에 반복하지 않음. 검증한 core/contract/definition 328파일과 현재 원문 SHA-256 일치. 실행 JAR에 Flyway/Testcontainers/JUnit/Mockito 없음. JAR SHA-256 `5cd8afbe4c1f09cff15013c7d74c2a982af34649004fae8d9ac243fb055ca41b`. |

초기 Windows Gradle은 loopback 연결을 만들지 못해 테스트 시작 전에 실패했다. 전용 Linux 실행으로 전환했다. 초기 YAML 앵커 중복과 새 테스트 fixture의 scope_changed 누락은 수정했고 위 결과는 수정 후 최신 #48 기준 단일 전체 실행이다. 브라우저 검증 선택자는 감사 이력 여러 건과 오류 코드 뒤 trace 번호를 허용하도록 보완했다. 원격 CI·배포·실제 PG/Google·실제 learning 미션 관리·#41 대화 재처리는 미검증이다.

## 남은 공급자와 한계

- REPORT 기존 실패 job 재처리는 아직 연결하지 않는다. 같은 jobId로 Outbox만 다시 넣어도 report의 job 멱등성과 core의 종료 상태가 이를 실행하지 않는다. core/report 양쪽의 시도 식별·종료 이벤트·소비자 계약을 먼저 합의하고 기반영 수정 허락을 받아야 한다. 새 판 regenerate로 대체하지 않는다.
- CONVERSATION 관리자 실행 공급자와 learning 관리자 미션/상태 집계 공급자는 없다. #41 코드나 learning DB를 복사하지 않고 명시적인 미연결 상태를 유지한다. 미션 콘텐츠 DTO/게시 정책은 실제 공급자의 OpenAPI 확정 후 최종 대조해야 한다.
- 알림 재처리는 Redis 발행 확인까지다. 브라우저 수신 보장이 아니며 프로세스 중단·결과 저장 실패로 RUNNING 이력이 남으면 자동 재실행하지 않는다. 네트워크 발행 자체에 분산 트랜잭션/정확히 한 번 보장을 추가한 것은 아니다. common IdempotencyService의 24시간 응답 저장을 재사용하며 5xx는 저장하지 않는 기존 정책을 유지한다.
- #47 전체 완료 조건이 아직 충족되지 않았으므로 이슈를 완료 처리하거나 Closes #47로 해결 완료를 주장하지 않는다. 현재 커밋은 독립적으로 검증한 운영 조회·알림 재처리·미션 프록시 범위다. 공급자 연결 후 실제 해결 범위를 확인한 PR에 Closes #47을 포함한다. 중간 base 병합만으로 자동 종료되지 않으며 최종 develop PR에도 필요하다.

Git 이력 재작성·PR 생성·공용 브랜치 push는 하지 않는다. 기능 head만 push하며, 사용자 직접 PR 작성용 초안은 별도 전달한다. 개인 작업 규칙을 저장소 문서에 추가하지 않았다.
