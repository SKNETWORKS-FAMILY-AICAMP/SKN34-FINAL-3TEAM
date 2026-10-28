# #42 core 주간 리포트

## 범위와 선행 계약

최초 구현은 develop `3e32731`에서 시작해 `d3d2814`를 반영했으며, 현재 검증 기준은 `40a2501223defd69bcc55595643a6fecf81e9df3`이다. 전용 `feature/core-weekly-reports`에서 작업한다. #37·#38·#39 병합본을 통합했고 다른 worktree 파일은 수정하지 않았다. 현재 report 접근 검사는 필수/법정대리인 동의를 포함하는 실제 #37 `StudentAccessService.requireLinked(UUID, UUID)`로 위임한다. 스케줄 대상 선정은 기존 ConsentAccessService를 함께 사용한다. #38 공통 HTTP·멱등성 및 #39 SSE 코드는 재작성하지 않는다.

2026-10-27 사용자 확인: narrativeEnabled 제공 상품·구독 계약은 아직 없다. ReportEntitlementService는 명시적인 `503 REPORT_ENTITLEMENT_UNAVAILABLE`를 반환한다. 운영에서 false/true를 가정하거나 상품·구독 기능을 중복 구현하지 않는다. 따라서 이 연결 전에는 정기/재생성 요청이 job·Outbox를 만들지 못하며 실패가 노출된다. 테스트에서만 이 서비스를 대역으로 바꿔 양 상품의 생성 흐름을 검증한다. 조회·이벤트 소비는 이 서비스와 독립적이다.

## 구현 계약

- 매주 월요일 07:00 Asia/Seoul. 직전 월요일~일요일 LocalDate를 명령에 넣고, 집계 시각 경계는 해당 월요일 00:00 KST 이상·다음 월요일 00:00 KST 미만이다. 기록 없는 자녀도 대상이며 기록 조회를 생성 조건으로 사용하지 않는다.
- ShedLock Spring/JDBC 6.10.0, 기존 shedlock 테이블, usingDbTime. 전역 잠금에 더해 기존 SCHEDULE 부분 UK로 재실행 중복을 방지한다. 자녀/기간별 PostgreSQL advisory transaction lock으로 정기·재생성 동시 생성을 직렬화한다. 새 migration은 사용하지 않는다.
- 작업 저장과 OutboxWriter.append는 같은 Application 트랜잭션이다. report.generate는 기존 OutboxRelay가 cmd.direct에 발행한다. HTTP는 해당 트랜잭션 밖이다. 기존 OutboxRelay 자체의 브로커 호출 트랜잭션은 기존 기반의 제한이며 이번 report 구현에서 재작성하지 않는다.
- 부모는 자녀/주 리포트 계열에 REGENERATE 작업 1회, SERVICE_OPS 관리자는 ADMIN_RETRY 작업으로 무제한. 재생성 결과를 다시 요청해 제한을 우회할 수 없다. 기존 job/report를 덮어쓰지 않는다. revision은 report가 자녀/주별로 원자 배정하며 core는 배정하지 않는다.
- lifecycle data는 jobId·studentId·reportId이며 failed에 failureReason(원문 없는 오류 코드)이 추가된다. 봉투 subject=studentId, source=report-service, dataschema=<type>.v1. core는 식별자 대조 후 processed_event와 조건부 전이·job_execution을 원자 저장한다. COMPLETED/FAILED는 종료 상태이며 뒤늦은 started·상반된 종료 이벤트는 상태를 바꾸지 않는다.
- 완료/실패 전이가 실제 반영된 때에만 ApplicationEvent `ReportJobFinished(sourceEventId, jobId, studentId, reportId, status)`가 발행된다. #44는 BEFORE_COMMIT 트랜잭션 이벤트 리스너에서 sourceEventId로 알림을 멱등 저장할 수 있다. 외부 SSE/Redis 발행은 커밋 이후에 수행한다. 현재 #44 리스너와 알림 발송은 구현하지 않는다.
- 공개 조회는 Controller → ReportQueryService → ReportClient. reportId의 자녀는 core report_job으로 식별하고 연결·현재 동의 확인 후 내부 scope를 그 자녀 하나로 제한한다. 목록·근거·파일은 report-api 응답을 전달하며, 상세 응답의 자녀·기간·UUID를 대조하고 실제 반환된 판의 ID로 report_view를 저장한다. 상세 조회 성공마다 1행이며 목록·다운로드는 열람으로 세지 않는다.
- 내부 상세는 revision query를 전달한다. 다운로드는 pdf/md만 허용하고 `{url, expiresAt}`를 반환한다. 부모 외 상세 조회는 금지하고, 관리자 예외는 재생성 POST 한 경로에만 둔다.

## 남은 실제 연결

#50은 이 작업의 네 가지 v1 스키마를 재사용하고 job_id UK·자녀/주별 revision 직렬화를 구현해야 한다. #51~#54 후 생성→학습 기록 계산→렌더링/파일 저장→실제 API 조회·근거·이전판·파일 URL을 검증한다. #64 연결 후 유료 서술/저녁 질문과 무료·NO_RECORD의 AI 미호출을 검증한다. URL 만료 시간은 #53/#54 소유이며 core가 임의 생성하지 않는다. 상품 계약 연결 후 정기/재생성의 실제 narrativeEnabled와 구독 유예기간을 함께 검증해야 한다.

## 검증 결과

검증은 구현을 마친 뒤 일괄 수행했다. 아래 날짜별 이력 중 가장 최근인 2026-10-28 결과를 현재 기준으로 사용한다. HTTP 대역·실제 RabbitMQ·실제 report-service E2E를 구분한다.

ShedLock 설정 근거: [고정 버전 6.10.0 공식 README](https://github.com/lukas-krecan/ShedLock/blob/shedlock-parent-6.10.0/README.md)의 Spring annotation 및 JDBC usingDbTime 설정을 따른다.


## #38 develop 통합

최초 기준 `3e32731`에서 core 91/91(리포트 신규 24), test·bootJar 및 실제 송수신 이벤트 4종/HTTP 상세 계약 검사를 통과했다. 그 뒤 #38 PR #75 병합을 확인했다. 현재 변경 34개 파일을 ZIP·SHA-256 manifest·binary patch로 보존·대조한 뒤 feature/core-weekly-reports를 develop `d3d28140d5b5a2e74cfd6c32f2ef2a983a25a016`으로 fast-forward하고 현재 작업을 3-way 재적용했다. 새 커밋·이력 재작성은 없다.

공통 HTTP 팩터리의 기본 readTimeout 인자가 유지되어 report create 호출은 수정하지 않았다. 기존 #38 Resilience4j 의존성을 유지하면서 ShedLock만 추가했다. OpenAPI에서 동시 경로 추가 충돌이 발생했고 #38의 모든 경로·schema를 그대로 보존한 뒤 report 경로·schema만 추가하는 방식으로 해결했다. API·아키텍처 문서는 양쪽 추가 내용을 유지했다. 이 조합에서 core 전체 test·bootJar와 계약·헤더·권한 흐름을 다시 검증한다.


최종 계층 검토에서 Application의 consumer DTO 의존을 제거했다. consumer가 원문 JSON 봉투의 필수/허용 필드, UUID·시각·type/source/dataschema/subject를 검사하고 Domain의 ReportLifecycleEvent로 변환한다. 공유 EventEnvelope는 발행용 id/time 기본값을 가지므로 소비자에서 누락 필드를 이 기본값으로 채우지 않는다. 형식 오류·지원하지 않는 스키마는 MessageConversionException으로 바로 DLQ, 올바른 형식의 미존재 job/식별자 불일치는 기존 RetryingConsumer로 재시도한다. 공통 봉투·RetryingConsumer는 수정하지 않는다.

#38 통합 후 계약 검사에서 OpenAPI 충돌 해결 중 report schema 블록이 빠진 것을 발견했다(37개 검사 중 참조 검사 1개 실패). components.schemas에 블록을 복구하고 기존 upstream 전체 경로·components 값의 동일성을 대조했다. #38이 추가한 requestBodies도 보존했다. 이 보완과 계층/봉투 검증 보완을 마친 뒤 최종 전체 검증을 다시 실행한다. 중간에 중단한 core 실행을 통과 결과로 합산하지 않는다.


## 최종 검증 (2026-10-27)

검증 기준 HEAD와 최종 fetch의 origin/develop은 모두 `d3d28140d5b5a2e74cfd6c32f2ef2a983a25a016`이다. #38 PR #75를 통합했고, #37의 현재 구현 `62e69ed`는 develop 조상이 아니며 이슈도 OPEN이다. #37 및 #42·#50~#56·#64 본문을 재조회해 최초 검토 이후 변경이 없음을 확인했다. #37 코드를 복사·cherry-pick하지 않았다.

| 검증 | 실제 실행과 결과 |
|---|---|
| 최종 core 전체 | Temurin JDK 21.0.12.1 Docker, `bash gradlew test bootJar --no-daemon --max-workers=1 --no-watch-fs --console=plain` + 검증 전용 JVM 메모리/CPU 제한·Kotlin in-process 설정. **113/113 통과**, 실패·오류·생략 0, BUILD SUCCESSFUL(7분 3초). 이전 91개 결과와 합산한 수가 아니라 최종 단일 전체 실행 결과다. |
| #42 신규 | 25개: 주 경계/cron/상품 미연결 3, Repository/생성/이력/전이 5, DB ShedLock/프록시 1, HTTP 대역 8, 실제 메시징/동시성/트랜잭션 8. Repository는 PostgresRepositoryTest, 실제 메시징은 IntegrationTestSupport 사용. |
| 실제 PostgreSQL | 스케줄 중복 생성, 동시 부모 재생성 1회, 작업+Outbox 및 상태+processed_event+execution의 rollback/재시도, 이전 report 보존, 종료 전이 불변, 열람 기록 확인. ShedLock은 실제 DB 잠금 보유 시 프록시 호출 skip과 lockAtLeastFor 중복 호출 skip을 확인했으며 실제 두 배포 Pod E2E는 아니다. |
| 실제 RabbitMQ | Outbox→cmd.direct 명령 수신/publisher confirm, events.topic→실제 core consumer, 같은 이벤트·역순 이벤트, 처리 실패의 retry 3회→DLQ, 잘못된 JSON·누락 id/time·지원하지 않는 스키마의 즉시 DLQ 확인. 기존 테스트 베이스가 retry TTL만 1초로 단축하며 큐 토폴로지는 production과 같다. 실제 1·5·15분의 전체 대기 시간 검증은 아니다. |
| report-api HTTP 대역 | 실제 JWT·MVC·core DB·RestClient와 테스트 전용 HttpServer 사용. 단일 학생 scope·내부 토큰·사용자·trace 헤더, 조회 필터·revision·근거·PDF/MD URL 경로, 타 보호자/학생/관리자 조회 차단·동의 철회, 관리자 SERVICE_OPS 재생성, 열람 기록·오류/계약 위반·트랜잭션 밖 HTTP 확인. 실제 report-service 실행은 아니다. |
| 계약 | `python -O -m unittest discover -s scripts/tests -v` **37/37**, OpenAPI 3.1 표준 검사 통과. `python scripts/validate_report_contracts.py`로 최종 실제 송수신 이벤트 4종의 봉투/data 및 core HTTP 상세 응답을 이벤트/공개 OpenAPI 스키마와 대조해 통과. |
| 스키마 | 별도 issue42-schema-postgres·network에서 기존 `scripts/check_db_migrations.py` 실행. core V1~V8, learning V1~V5, report Alembic 적용. 60개 테이블/518개 컬럼, 47개 제약 위반 입력, 62개 CHECK 집합, 19개 ERD 인덱스 통과. 재실행 이력 불변·report downgrade/upgrade 통과(17.3초). 기존 migration과 공유 compose/DB는 변경하지 않음. |
| 배포 JAR | ShedLock core/Spring/JDBC 6.10.0 포함, Flyway·Testcontainers·JUnit·Mockito·테스트 payload/HTTP 서버 클래스 및 제거한 consumer DTO 미포함 확인. 원격 CI·배포·실제 Google 로그인·브라우저는 미실행. |

초기 검증 실행은 전용 shell 스크립트 CRLF 때문에 test 시작 전에 실패했고 검증 스크립트만 LF로 보정했다. OpenAPI CLI가 기본 Python에 없어 검증 전용 폴더에 설치했다. #38 통합 중 참조 검사 실패와 중단된 core 실행은 위 최종 성공 결과와 구분한다. 저장소 production/lock에 Python 검증 의존성을 추가하지 않았다. Kotlin annotation target 및 JVM class sharing 안내가 있었으며 검증 실패는 아니다.

## 공통 파일·Git 상태

#42의 공통 tracked 변경은 5개뿐이다: `backend/core-service/build.gradle.kts`(ShedLock 2개 모듈), `_common/security/PublicAuthFilter.kt`(SERVICE_OPS 관리자의 정확한 재생성 POST 경로만 허용), `contracts/openapi/core-service.yaml`, `docs/design/api-spec.md`, `docs/design/architecture.md`. 나머지는 core report/·그 Mapper·테스트, 리포트 이벤트 계약, 검증 스크립트, 이 보고서다. #38 공통 HTTP/멱등성, #39 SSE, #45 삭제, #44 알림, report-service 계산/서술/렌더링 코드를 수정하지 않았다. 새 migration·애플리케이션 설정·compose 변경은 없다.

2026-10-27 작업 종료 시점의 브랜치는 `feature/core-weekly-reports`, 통합 대상은 develop, 당시 이 작업에서 만든 커밋은 0개였다. 원본 checkout은 feature/core-google-auth 그대로다. 모든 작업 변경은 미stage·미커밋이며 push·PR 생성·history rewrite를 수행하지 않았다. develop 반영은 fast-forward라 새 merge commit도 만들지 않았다.

## 남은 조건과 검증 경계

- #37 선행 조건은 2026-10-28 통합·재검증으로 해소했다. 현재 필수·법정대리인 동의, 철회, 문서 개정에 따른 기존 세션 차단을 실제 병합 서비스로 검증했다. 아래 최신 결과를 따른다.
- 사용자 확인대로 상품 계약은 아직 없다. `ReportEntitlementService.narrativeEnabled(studentId)` 연결 전 운영 정기 생성/재생성은 503으로 실패하고 job/Outbox를 저장하지 않는다. 테스트의 false/true는 테스트 대역이며 실제 상품 판정·유예기간·생성 시점 vs 조회 시점 무료 전환 정책 검증이 아니다.
- #50은 공유 v1·source/subject·reportId와 jobId의 구분·job 멱등성·자녀/주별 revision 배정 계약을 대조해야 한다. #54와 목록 `{items}`·항목 근거 JSON의 구체적인 필드·revision 및 presigned URL 만료 시간을 확정해야 한다. report가 명령을 아직 소비하지 않은 QUEUED 작업의 목록 표시 방식도 공급자와 조율해야 하며, core가 jobId를 reportId로 꾸며 반환하지 않는다.
- #50~#54 연결 후 core 정기/재생성→실제 worker→이벤트→목록/상세/이전판/근거→실제 PDF/MD 파일 다운로드 E2E를 실행한다. #64 연결 후 프리미엄 서술·저녁 질문, 무료/NO_RECORD AI 미호출을 확인한다. #45/#55 연결 후 삭제·생성 경합과 삭제 근거의 available=false·재조회 거부를 검증한다. #44는 위 ReportJobFinished의 BEFORE_COMMIT 알림 저장 지점을 연결해야 한다.
- **공통 기반의 기존 미해결 제약:** OutboxRelay.relay는 @Transactional 안에서 브로커 발행과 confirm 대기를 수행한다. 따라서 요청한 “브로커 호출도 트랜잭션 밖” 조건은 기존 relay에서 아직 충족되지 않는다. 이번 기능의 작업/Outbox 원자성과 HTTP 분리는 검증했지만 이 제한을 해결했다고 주장하지 않는다. 공통 메시징 재작성 금지 경계를 지켜 relay/claim 처리·스키마를 변경하지 않았다.

최종 변경 34개 파일의 변경 줄/신규 파일 공백 검사와 `git diff --check`를 통과했고 index는 비어 있다. 검증용 schema 컨테이너·네트워크와 실행 컨테이너는 정리했다. Gradle 캐시·검증 로그·백업은 저장소 밖 issue42-tools/전용 캐시에 보존했다.


## 2026-10-28 최신 develop 통합·재검증

사용자 요청으로 최신 develop과 기존 작업 상태를 확인했다. 이전 최종 manifest의 34개 파일이 누락/변경 없이 같음을 대조했다. #37 PR #77과 #39 PR #83이 포함된 develop `40a2501223defd69bcc55595643a6fecf81e9df3`을 전용 feature 브랜치에 fast-forward했다. #42의 34개 파일은 별도 ZIP·SHA-256·patch로 보존하고 재적용했다. OpenAPI와 API 문서 충돌은 최신 upstream 전체 경로·components·동의/SSE 계약을 유지하고 #42 리포트 계약만 추가해 해결한다.

#37의 requireLinked(UUID, UUID)는 반환형을 유지하면서 현재 필수/법정대리인 동의까지 검사하는 실제 서비스로 병합됐다. 따라서 report 접근 서비스의 임시 중복 동의 검사를 제거하고 해당 서비스로 위임한다. 스케줄 대상 선정은 기존 ConsentAccessService를 사용한다. HTTP/메시징·Outbox 및 상품 경계는 변하지 않는다. 현재 개발 브랜치의 report-service 기능과 상품/구독 공급자는 여전히 미구현이며, 이전 기록의 #37 미병합 조건만 해소됐다. 사용자에게 커밋·push 허가를 새로 받았으므로 통합 필수 검증이 끝나면 #42 범위만 feature 브랜치에 커밋·push하고 PR은 생성하지 않는다.


### 2026-10-28 최종 결과·커밋 준비

- 기준: develop `40a2501223defd69bcc55595643a6fecf81e9df3`(#37 PR #77·#39 PR #83 포함). 원래 #42의 34개 변경은 모두 보존했다. requireLinked 실제 계약과 대조해 중복 동의 검사만 제거하고 공유 서비스로 위임했다.
- JDK 21 전체 `test bootJar`: **150/150 통과**, 실패·오류·생략 0, BUILD SUCCESSFUL(10분 14초). 검증 전용 test heap은 512MiB, Gradle heap 512MiB·worker 1·CPU 2다. #42는 **26개**이며 새 동의 문서가 게시되면 기존 세션의 목록·상세·근거·다운로드·재생성이 차단되고 HTTP/열람 기록이 생기지 않는 검증을 포함한다.
- 계약 검사 **46/46**, OpenAPI 3.1 표준 검사 통과. 최종 실제 송수신 report.generate/started/completed/failed 4종과 HTTP 대역 상세 응답의 스키마 대조 통과. 실제 PostgreSQL·RabbitMQ는 기존 테스트 기반을 재사용했다. report-api는 여전히 HTTP 대역이며 실제 report-service 전체 E2E가 아니다.
- 검증 중 30개 non-Markdown 변경 파일의 SHA-256이 그대로임을 확인했고, JAR의 Flyway·Testcontainers·JUnit·Mockito·테스트 payload 미포함을 확인했다. DB migration은 바뀌지 않아 10/27의 전체 3-DB cycle을 반복하지 않았으며, 현재 core 전체 테스트는 기존 V1~V8을 실제 임시 DB에 적용했다.
- 원격 CI·운영 배포·실제 report-service/상품/AI 연결은 이번 결과에 포함하지 않는다. 상품 미연결의 명시적 503과 기존 공통 OutboxRelay의 트랜잭션 제한은 남는다. #44 알림 연결 지점 및 #50~#54·#64 실제 연동 후 검증 조건은 위 경계를 유지한다.
- Git 준비: #42 변경 34개 파일만 명시적으로 stage하는 한 기능 커밋으로 정리한다. 메시지는 `feat: core 주간 리포트 작업·스케줄·조회 구현`, push 대상은 origin의 `feature/core-weekly-reports`, PR base는 develop이다. 원본 checkout 및 다른 작업 브랜치를 변경하지 않으며 PR은 생성하지 않는다. 실제 커밋 SHA·push 결과는 최종 작업 보고와 Git 기록을 따른다.

### core-integration 대상 PR 준비

2026-10-28 요청에 따라 최신 develop과 같은 `40a2501223defd69bcc55595643a6fecf81e9df3`에서 `feature/core-integration` 브랜치를 생성·push했다. 기존 checkout을 전환하지 않았다. 이 시점의 #42 head는 `f744baf44ef6b3c1dc88e27e358b414eff210e79`이며, 실제 PR base는 이제 feature/core-integration이다. core 임시 통합 경로를 docs/README.md에 명시하고 최종 반영은 develop을 유지한다. PR 생성·메타데이터 설정·병합은 직접 수행하지 않는다.

PR 준비 중 ci-db-schema가 report-service의 production 의존성만 설치하는데 새 계약 테스트는 jsonschema를 import하는 것을 확인했다. 기존 로컬 환경에는 설치되어 있어 46개 검사가 통과했지만 그대로는 CI에서 import가 실패한다. 따라서 해당 CI의 테스트 환경에만 jsonschema 4.26.0 설치 단계를 추가한다. report-service pyproject.toml·uv.lock·production 의존성 및 업무 코드는 바꾸지 않는다. locked --no-dev 의존성 + 명시적인 계약 검사 도구를 새 검증 환경에 설치해 전체 scripts/tests를 검증한다. core 업무 코드와 API/이벤트 계약이 변하지 않아 이미 통과한 JDK 21 전체 150개를 반복하지 않는다.

CI 의존성 조합 검증 결과: 새 Python 3.12.10 환경에서 report-service lock의 --no-dev 36개 패키지와 jsonschema 4.26.0만 설치해 scripts/tests 46/46 통과(실패·생략 0). workflow YAML, sync→검사 도구 설치→unittest 순서, core/schema PR의 base 브랜치 제한 없음, production pyproject/lock 미변경 및 git diff --check를 확인했다. 이는 로컬 의존성 재현 검증이며 아직 생성하지 않은 PR의 원격 CI 성공을 뜻하지 않는다.
