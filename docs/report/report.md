# 주간·일일 리포트

계약은 [API 명세](../design/api-spec.md) 3.4·4.1.1·4.2.1·4.4·5.5, 메시지는 [report-messages](../../contracts/events/report-messages.md).

## 1. core 주간 리포트 (#42)

- 매주 월요일 00:00 Asia/Seoul(일요일 자정, 21장), 직전 월~일 `LocalDate`, 집계 경계 `[월 00:00 KST, 다음 월 00:00 KST)`. 기록 없는 자녀도 대상
- P24 일일 리포트([기획 3.5](planning.md#35-일일-리포트리포트-대화-p24p25)): core 몫(매일 00:00 전날 작업·`report_job.period_type`·정기 UK·알림·조회)은 20장(#390). report 몫(`weekly_report.period_type`, 재생성 UK·revision 잠금, 일일 템플릿·테마 요약)은 #391로 구현([ERD 5.2](../design/erd.md#52-일일주간-기간-분리-391), 마이그레이션 `20261109_06`·`20261109_07`)
- ShedLock(Spring/JDBC, 기존 `shedlock` 테이블, `usingDbTime`) + SCHEDULE 부분 UK로 재실행 중복 방지, 자녀·기간별 advisory transaction lock으로 정기·재생성 직렬화. 자녀별 실패는 격리하고 실행 끝에 전파
- 작업 저장과 `OutboxWriter.append`는 같은 트랜잭션, HTTP는 밖. core `OutboxRelay`는 #166 이후 DB 트랜잭션 밖에서 발행·confirm을 기다리고 발행 시각만 짧은 트랜잭션으로 기록
- 재생성: 부모는 자녀·주 계열 REGENERATE 1회(재생성 결과로 다시 요청해도 우회 불가), SERVICE_OPS 관리자는 ADMIN_RETRY 무제한. revision은 report가 배정
- 상품 권한: #48에서 `ReportEntitlementService → ProductEntitlementService`를 연결했다. 생성 시 실제 상품·구독의 narrativeEnabled를 사용하며 설정·판정 오류는 job·Outbox 생성 전에 전파한다. 조회 연결은 13장(#129)을 따른다.
- lifecycle 이벤트 data는 `jobId·studentId·reportId`(failed는 `failureReason`). core는 식별자 대조 후 `processed_event`·조건부 전이·`job_execution`을 원자 저장. 종료 후 늦은 started·상반된 종료 이벤트는 무시. 종료 전이가 반영될 때만 `ReportJobFinished` 발행(알림 연결점)
- 조회: Controller → `ReportQueryService` → `ReportClient`. reportId의 자녀는 core `report_job`으로 식별, 연결·동의 확인 후 scope를 그 자녀로 제한. 상세 응답의 자녀·기간·UUID 대조 후 실제 반환 판 ID로 `report_view` 저장(목록·다운로드는 열람 아님). 다운로드는 pdf·md만

## 2. 생성 기반 (#50)

- report-worker가 `report.generate`를 받아 작업 상태·결과 이벤트를 중복 없이 저장·발행. 공유 v1 스키마를 재사용(`report.generate` data는 `jobId·studentId·periodFrom·periodTo·trigger·narrativeEnabled` 6개, 요청 시각은 봉투 `time`)
- `narrativeEnabled`는 필수 boolean. 누락·잘못된 형식은 DLQ
- `app/messaging/contracts.py`는 엄격한 수신 DTO, `app/generation/codec.py`가 payload를 내부 모델로 변환. `requested_at`은 봉투 time을 보존(삭제 장벽에서 사용)
- Outbox는 학생별 미발행 선두 중 적격 후보 100개에서 선점하며, 발행은 최대 15초다. #131에서 학생별 순서를 유지하고 실패한 학생만 1·5·15분 지연 후 격리한다. 다른 학생은 계속 처리한다. 브로커 대기 동안 트랜잭션·행 잠금은 없지만 학생별 session lock용 연결 1개를 사용한다(연결 풀과 worker 동시 실행 수를 함께 관리). [격리 조회·수동 재처리·마이그레이션](#11-outbox-실패-격리와-학생별-발행-순서-131)
- #56에서 기본 진입점에 core 별명 조회 → 기록 집계 → 서술 검증 → 파일 저장 생성기를 연결했다. 테스트용 `run(generator=...)` 주입도 유지한다.

## 3. 수치 계산 (#51)

- 연결어는 `왜냐하면·때문·그래서·따라서`(사용자 승인, `generation/metrics.py:REASON_CONNECTIVES`), 비중첩 등장 횟수 합
- 표본: 0건 `NO_RECORD`, 1~4건 `INSUFFICIENT_SAMPLE`, 5건 이상 `OK`. 비율 분모 5 미만은 value null, count에 분자 보존
- KST 양 끝 포함. 시작일 이전 최초 답변·도움도 입력으로 받고 종료일 뒤 답변·완료·돌아보기는 과거 주에 포함하지 않음. PENDING·RUNNING은 FAILED로 취급하지 않음
- 수치는 `answers[].content`의 학생 작성 칸만 셈(서술 text, 풀이 steps 후 finalAnswer, 논술 claim·reasons·rebuttal을 LF로 연결, 고르기·순서·분류는 빈 문자열). 표시용 `text`의 칸·선택지 이름을 세지 않음. 글자 수는 코드포인트, 문장은 `.?!`·LF(learning `TextCounts`와 같음)
- `reflection:null`·생략은 미작성, 난이도만 있고 글이 없으면 `written:true, text:null`. 저장 난이도는 `EASY·NORMAL·HARD`
- `followup:null`은 그대로 저장·조회하고 PDF·HTML·MD에서는 질문 문구 생략
- 메모·초안·추가 필드 제외. 잘못된 식별자·버전·기간·페이지·필수 내용은 빈 기록이나 정상 리포트로 바꾸지 않음

## 4. 서술 요청·검증 (#52)

- AI 시간 초과·5xx·스키마 오류·원문 조회 실패는 FAILED, 대조 실패만 템플릿 전환(사용자 결정). 템플릿은 계산된 시도 건수와 기록 확인 안내만, 검증 실패한 저녁 질문은 저장하지 않음
- 검증기(`generation/verifier.py`): 서술·저녁 질문의 숫자가 계산 결과에 있는지, 인용이 원문 부분문자열이고 answer ID·attempt ID·version이 맞는지. 근거 없는 따옴표 인용·지원하지 않는 한글 수사·과학적 표기·수치 레벨·등급·사고력 향상 단정은 통과로 보지 않음(의미·인과까지 증명하지는 않음)
- `verification`은 `numbersMatched`·`quotesMatched`·`contentAllowed` 보존
- evidence는 50건 단위 조회, 410·삭제 표식은 이용 불가(원문 미반환), 누락·다른 버전·예상 밖 답변은 거부
- ai 요청 `quotes[]`에는 근거 링크의 `answerVersion`을 붙여 보냄(ai `citedQuotes` 버전 출처, #64). 저장 payload·상세 `quotes`에는 넣지 않음
- 무료·NO_RECORD는 AI 생략. 알려진 닉네임은 본문에서 가리고 이름·학생 식별 필드는 요청에 넣지 않음. 닉네임은 공유 메시지에 추가하지 않고 core 내부 별명 조회(#119)로 공급(#56, 10장)

## 5. 렌더링·파일 저장 (#53)

- HTML·PDF(Playwright Chromium)·Markdown. 이름·원문 escape, Chromium의 JavaScript·외부 요청 차단. 조회와 파일이 같은 조립 규칙(`generation/presentation.py`), 검증되지 않은 인용 원문은 노출하지 않음
- 난이도 표시는 `쉬웠어요·보통·어려웠어요`로 출력 시점에만 변환(저장 payload는 코드 유지)
- 키 `reports/{studentId}/{reportId}/r{revision}/{full|free}/{pdf|md|html}`. 같은 판의 full·free 6개 객체를 만들고 `report_file`에는 full 3행. 무료 투영은 AI 서술·생각 유형 summary·저녁 질문 제외
- 업로드 실패 시 부분 객체 정리 시도 후 FAILED. 남은 prefix는 학생 삭제 때 정리(주기 점검은 인프라 후속)
- 다운로드 URL 수명 기본 300초(설정). 공개 MinIO 주소는 `S3_PUBLIC_ENDPOINT_URL`
- 한글 PDF: Dockerfile에 Chromium·Noto CJK 준비, non-root·read-only root·`/tmp` tmpfs에서 생성 확인. HTML·MD는 전문 스냅샷, PDF는 공백 제외 논리 텍스트 비교 + 시각 검토. CI의 report-service에만 Chromium·폰트 설치 단계

## 6. 조회 내부 API (#54)

| API | 동작 |
|---|---|
| 목록 | 학생 범위 확인 → 학생·주별 최신 revision → status 필터 → 페이지 |
| 상세 | 소속 학생 확인 → 같은 학생·주 최신판 기본, `revision`으로 이전판, revisions 포함 |
| 근거 | reportId·itemId 소속 확인 → learning 원문 재조회. 삭제 원문은 `available:false`(저장된 quote로 대체하지 않음) |
| 파일 | 판의 메타데이터·학생·형식·키를 검사하고 현재 권한의 full·free 파일만 서명 |

- 범위 밖 403, 없는 보고서·판·항목·파일 404, 형식 오류 400(problem+json), 학생 삭제 진행 중 409 `DELETION_IN_PROGRESS`, 원문·저장소 장애 503 `DATA_UNAVAILABLE`. 응답 스키마 오류 로그에 원문을 남기지 않음
- 이용 권한은 core가 `X-Report-Narrative-Enabled`로 전달(없으면 false). 생성 당시 유료였다는 이유로 유료 파일을 서명하지 않음. core의 상세·파일 요청에서 설정하며 반환 직전 권한 재확인도 수행한다(13장)

## 7. 학생 삭제 (#55)

1. 학생 단위 exclusive advisory lock(생성은 같은 학생 shared lock + job lock). 실행 중 생성이 있으면 삭제는 재시도 큐로
2. `report_deletion_guard`를 PENDING으로 커밋(새 생성·조회 차단)
3. `reports/{studentId}/` S3 객체 삭제. 실패하면 DB 행과 PENDING을 남기고 재시도(S3·DB 원자성은 없음)
4. evidence → item → file → weekly_report와 해당 학생 Outbox 삭제, guard COMPLETED·`processed_event`를 한 트랜잭션
5. core 완료 API에 `{service:"report"}`. 실패하면 재전달 시 삭제를 반복하지 않고 보고만 재전송(다른 요청이 진행 중일 때 재전달돼도 보고만 재전송)

- PROFILE·RECORDS 모두 리포트 내용·파일 삭제와 이후 생성 차단(core가 RECORDS 후에도 학생을 `DELETION_REQUESTED`로 유지). 재개는 별도 계약 필요
- guard 테이블(`20261027_02`): `student_id` PK, `scope`, `cutoff_at`, `deletion_request_id`, `status`, `updated_at`. 이름·답변·경로는 저장하지 않음. 롤백은 표식을 제거하므로 운영 중 무조건 수행 금지. S3 버전·복제본 삭제 정책은 인프라에서 확정

## 8. learning 연동 검증과 재현

- #27 실제 응답에 맞춰 수정: 내부 응답 식별자 `studentId`, 학생 작성 칸만 집계, `followup:null` 보존
- 재현: learning `bootJar`를 먼저 빌드(오래된 JAR은 거부)한 뒤 저장소 루트에서

```powershell
& .\backend\report-service\.venv\Scripts\python.exe -X utf8 -u scripts/verify_report_learning.py --output output/report27-live-rerun
```

  일회용 PostgreSQL·RabbitMQ와 loopback 포트를 쓰고 종료 시 정리. 공유 DB·운영 AWS·실제 학생 자료 미사용

## 9. 연결 상태

상품 권한(#48·#129, 13장), 표시 이름(#56), 생성기 조립(#56·#64), 학생 삭제(#128·#132, 14장)가 모두 연결됨. 운영 S3·Pod Identity·공개 endpoint는 AWS 데모에서 부모 다운로드까지 확인([infra 4.2](infra.md#42-실제-서비스-검증-11-0304)). Chromium `/tmp` 쓰기 볼륨·guard 표식 보존·SIGTERM 유예·DLQ 복구는 배포 values 기준([prod README](../../infrastructure/gitops/environments/prod/README.md)).

## 10. 기본 worker 연결 (#56·#130)

- 기본 `python -m app.worker`가 `CoreClient.lookup` → `RecordGenerator` → `NarrativeGenerator` → `RenderingGenerator`를 실행(#130은 이 #56 구현으로 충족). 테스트용 생성기·별명 공급자 주입은 유지
- core `GET /internal/students/{studentId}/profile`(#119)에 기존 내부 클라이언트로 내부 토큰·SYSTEM 역할·해당 학생 scope 전달. `NamedGenerator`가 ID 일치와 비어 있지 않은 별명을 검사하고 AI 입력 가림과 파일 표시에 같은 값 사용
- 403·404·시간 초과·잘못된 응답은 `FAILED / GENERATION_FAILED`와 `report.failed`. 가짜 별명·NO_RECORD 대체, HTTP 재시도 추가 없음
- worker가 HTTP·S3 클라이언트 수명 관리. 조회 API(#135)도 learning HTTP·S3 클라이언트를 lifespan에서 한 번 만들어 재사용하고, 권한 헤더는 요청마다 ContextVar에서 읽어 이전 학생 헤더를 공유하지 않음. S3 생성·종료는 `run_blocking`
- 서비스 URL 설정(#135): report `ai_url`·`core_url`, scoring `core_url`, ai `scoring_url`·`core_url`·`learning_url` 모두 실제 사용처가 있어 유지

### Compose 연동 검증 (`scripts/report_integration/compose.yaml`)

고유 프로젝트·일회용 DB/볼륨에서 core·learning(최신 소스 JAR), report 운영 이미지(worker·API·Outbox·렌더러), 실제 PostgreSQL·RabbitMQ·MinIO, 합성 학생·학습 기록, AI HTTP 대역(정상·숫자 불일치·503). 팀 `.env`·AWS·실제 학생 데이터 미사용, 호스트 포트 미공개.

```powershell
# core·learning: Java 21 ./gradlew bootJar --no-daemon (runner는 JAR보다 소스가 최신이면 중단)
& backend/report-service/.venv/Scripts/python.exe -X utf8 scripts/verify_report_compose.py --output <저장소 밖 경로>
# 관리자 재처리(#152) 시나리오는 --admin-retry 추가(worker 2개)
```

검사: 직접 발행 → COMPLETED·`report.completed`, HTML/PDF/MD 메타데이터와 서명 URL 다운로드, 상세 응답 `ReportDetail` 스키마, 빈 기록 NO_RECORD·AI 호출 0회, 정상 LLM·대조 실패 TEMPLATE·AI 503 FAILED, core 내부 API 401·scope 403·no-store, AI 최종 payload의 별명·학생 ID 제거, 중복 메시지 단일 행, 저장 장애 시 파일 행 0개, 이벤트의 저장소 JSON Schema 검증.

## 11. Outbox 실패 격리와 학생별 발행 순서 (#131)

승인된 정책:

- subject(학생 UUID)별 발행 순서 유지. 실패한 학생만 대기하고 다른 학생은 계속 처리
- 최초 실패 후 1·5·15분으로 재시도 3회, 총 4번 실패하면 격리
- 격리된 선두를 포함한 그 학생의 뒤 이벤트는 건너뛰지 않음. 운영자가 원인을 고친 뒤 선두를 수동 재처리하면 뒤 이벤트도 순서대로 진행
- 원래 이벤트 id·payload 보존. 발행 후 DB 기록 전 장애 등은 동일 id 재전달이며 core 멱등 처리와 종료 상태 방어 유지

구현(기존 OutboxRepository·OutboxRelay·worker relay_loop 사용):

- `published_at IS NULL`인 학생별 가장 앞 행(created_at, id)만 선점. 앞 행이 백오프/격리 상태여도 뒤 행을 선택하지 않음. 100개 조회 제한은 적격 학생별 선두에 적용
- PG publish 세션 advisory lock을 학생별로 유지. AMQP를 기다리는 동안 DB 트랜잭션을 열어 두지 않음
- enqueue는 별도 키의 짧은 PG 트랜잭션 잠금으로 생산자끼리 순서를 정함. 미커밋 선두가 뒤 커밋에 추월되지 않음
- 발행 예외/timeout만 짧은 트랜잭션으로 실패 횟수·다음 시각 저장. confirm 이후 mark_published 저장 실패는 발행 실패로 오분류하지 않고 원래 id 재발행
- CancelledError는 시도 횟수를 소모하지 않고 선점 해제. 학생 삭제로 없어진 Outbox는 되살리지 않음
- `BROKER_UNAVAILABLE|PUBLISH_TIMEOUT|PUBLISH_FAILED`만 저장. 원문 예외·학생 내용·자격 증명은 DB/운영 로그에 넣지 않음. 격리는 ERROR 로그로 알리고 CLI에서 조회

DB 적용과 롤백: Alembic `20261030_04`(직전 `20261029_03` #132 job guard). 기존 행의 두 카운터만 0으로 초기화, 영구 SQL DEFAULT 없음. 기존 worker를 멈춘 뒤 `alembic upgrade head` → 새 worker 기동(구버전 혼합 실행 미지원). 다운그레이드는 worker 중지 후 수행하며 실패/격리/수동 재처리 메타데이터가 사라지므로 먼저 운영 상태 보관.

수동 운영(HTTP 권한 우회 API 아님, 신뢰된 report 운영 환경의 DB 권한으로 실행):

```powershell
uv run python -m app.outbox.manage list --limit 100
uv run python -m app.outbox.manage requeue <event-uuid>
```

list는 payload·학생 식별자 없이 이벤트 id/type·실패 코드/횟수·격리 시각·수동 이력만 표시. 재처리는 격리된 미발행 행만 1회 조건부 갱신하며 경쟁 중/삭제됨/이미 발행됨은 NOT_REQUEUED(종료 코드 2). id·내용·순서 위치는 유지, 실패 카운터·백오프 초기화, `manual_retry_count`·`last_requeued_at` 기록. 관리자 작업 재생성(#152, 새 jobId)과 달리 이미 만들어진 결과 이벤트 전달만 다시 시도.

## 12. 관리자 실패 리포트 재처리 (#152)

- 경계: core #47은 관리자 요청 접수·권한·멱등, 원작업과 새 작업 연결, 생성 요청 발행, 결과별 상태·실행·감사 기록. report는 새 jobId 실행, 중복·동시 전달 방어, 이전 판 보존, 요청 jobId에 맞는 시작·성공·실패 이벤트
- core는 새 jobId를 발행하며 같은 관리자 요청 재전송에는 그 ID 유지. report 이벤트에 originalJobId를 추가하지 않음. report는 생산자가 적법한 재처리를 발행했다고 신뢰하며 원작업을 core DB에서 조회하지 않음
- 제품 실행 코드·DB·HTTP·이벤트 스키마 변경 없이 기존 경로 재사용

| 요구 | 재사용 코드 | 판단 |
|---|---|---|
| ADMIN_RETRY 수신 | ReportV1Codec, GenerationConsumer | 기존 v1 enum·SYSTEM scope 그대로 |
| 새 작업 실행 | GenerationService.generate | 기존 생성 파이프라인 |
| 이전 실패 단순 재전달 종료 | get_or_create + RUNNING 검사 | 기존 COMPLETED/FAILED는 생성기·이벤트 추가 없이 반환 |
| 같은 요청 동시 전달 | JobLocks의 PG 세션 advisory lock | 한 worker만 실행, 나머지는 consumer 지연 재시도 |
| revision·이전 판 보존 | ReportRepository.get_or_create | 학생/주 PG 트랜잭션 잠금 + 다음 revision, 기존 행 수정 없음 |
| 원자성 | GenerationService._start/_finish, OutboxRepository | 시작·종료 변경과 각 Outbox가 같은 트랜잭션 |
| 현재 권한 | core의 narrativeEnabled 계산 | 요청 값을 그대로 사용, 과거 유료 값을 복사하지 않음 |
| 삭제 | report_deletion_guard + core ACTIVE 프로필 조회 | 기존 장벽 유지 |

테스트: `backend/report-service/tests/test_admin_retry.py`(실제 Alembic DB·JobLocks, 합성 생성기)와 Compose `--admin-retry`(성공·재실패·무료 재처리, 두 worker 중복 명령, 원작업의 늦은 이벤트에도 종료 상태 불변, 기존 S3 파일 바이트 보존). 요청·결과 예시 7개는 [contracts/examples/report-admin-retry](../../contracts/examples/report-admin-retry/).

## 13. 현재 이용권 연결 (#129)

조회 클라이언트가 이용권 헤더를 보내지 않으면 report는 기본 false를 적용하므로, 기존 공급자를 재사용하고 상세·파일 요청에 검증된 현재 권한을 전달한다. API 명세 5.8의 요청 시 선택 범위와 반환 직전 재확인 규칙을 따른다.

- core의 `ReportClient`, `ReportQueryService`, `ReportViewService` 및 관련 테스트가 변경 대상이다. 기존 payment 판정·report 공급자·DB·메시지 형식은 유지한다.
- 무료 상세의 AI 세 필드(서술·저녁 질문·생각 유형 summary)를 가리고, 무료 다운로드는 이미 생성된 free 파일을 사용한다. full URL은 최종 권한 상실 시 거부한다.
- 무료 응답을 요청한 뒤 권한이 생긴 경우 프리미엄 사용을 기록하지 않는다. 환불과 같은 parent 잠금, 학생·동의 검사, 응답 학생·기간·판본 검사를 보존한다.
- 데모 특례와 새로운 의존성은 추가하지 않는다. #132 작업 고착 정리는 별도 범위다.
- P13·P24(#391): 일일 리포트는 서술이 없어 무료·프리미엄 동일 제공, 이 절의 무료 가림은 주간 리포트에만 적용

## 14. 종료 이벤트 유실 복구 (#132)

사용자 승인(10/29): v1 이벤트 변경 대신 core 주기 점검과 report 실제 상태 복구, 삭제 연동을 채택한다. 기본 1분 주기/생성 후 60분 후보 선정은 운영 정책이며 성능 측정/강제 실행 종료 시간이 아니다. #129 이용권·full/free 파일 선택·최종 권한 확인은 보존한다.

- 종료 이벤트 유실은 저장된 결과 재조회, 행 생성 전 실패/DLQ는 영구 job guard, 고아 RUNNING은 기존 session 잠금 획득 후 실패 종료로 처리한다. 실행 중 BUSY/DB·통신 장애/식별 불일치는 종료로 단정하지 않는다.
- guard의 보존·학생 삭제 시 제거와 영구 삭제 표식 승계는 ERD의 #132 절을 따른다. 원문은 저장하지 않는다. reportId 없는 실패는 내부 복구 응답으로만 처리하며 가짜 리포트/알림 링크를 생성하지 않는다.
- core 학생 → 주/job 잠금을 생성·이벤트·복구에서 통일한다. 삭제의 기존 parent → student 순서와 기존 파일 삭제/완료 보고를 보존한다. 삭제 확정 트랜잭션에서 미종료 작업/실행 이력을 STUDENT_DELETED로 종료하며 새 실패 알림은 보내지 않는다.

- 복구 전용 ReportClient 요청 팩토리는 HTTP/1.1 고정: JDK 기본 h2c 업그레이드를 포함한 POST를 Uvicorn이 400으로 거부. 기존 InternalRestClientFactory의 내부 토큰·사용자 컨텍스트 interceptor와 설정된 connect/read timeout을 보존한다. 공통 HTTP 팩토리나 기존 조회 클라이언트는 변경하지 않는다. 테스트의 HTTP 서버도 Upgrade 헤더 부재를 확인한다. 장애 동안 작업은 미종료 상태를 유지하고 다음 점검으로 남았다.

## 15. 하위 호출 서킷 브레이커 (#167)

report-query와 report-recovery를 분리한다. 4xx·DATA_UNAVAILABLE 매핑, 2xx BUSY/FAILED, 학생 scope 복원을 보존한다. OPEN은 REPORT_UNAVAILABLE이며 복구는 다음 점검으로 남긴다. 관리자 재처리는 기존 Outbox 경로다.

최근/최소 20건·실패율 50%·30초 차단·half-open 1건. 신규 production 의존성·오류 코드·Retry-After 없음.

## 16. 학생 공개 설정과 원문 제외 (#206)

- 생성 입력은 메시지의 과거 공개 값에 의존하지 않음. `NamedGenerator`가 내부 core 프로필의 현재 `parentSharingEnabled`를 조회하며 누락은 비공개. 생성 직전 원문·돌아보기 문장·인용 후보·근거 링크를 제거하고 AI 서술 호출을 생략
- 학습 횟수·분모/분자·기간·유형과 전후 글자/문장 수는 유지. 원문을 새 문장으로 대체 생성하지 않음
- 이미 공개 상태에서 만든 리포트도 core 상세에서 현재 설정을 다시 검사해 원문·인용·파생 서술을 제거. 비공개 중 파일 URL 재발급과 근거 조회는 403. 이미 전달한 파일은 회수하지 못함
- 다시 공개해도 비공개 중 생성한 리포트에 원문을 자동 복원하지 않음(필요하면 재생성)
- 일일 리포트(#391)도 같은 규칙
- 리포트 HTTP는 DB 트랜잭션 밖. HTTP 완료 뒤 `ReportViewService.recordWithSharing` 또는 파일 최종 기록 단계가 parent → student 순서로 현재 상품·공개 권한을 다시 확인. 조회·서명 도중 비공개로 바뀌면 원문·URL을 반환하지 않음

## 17. 학부모 대화 기반 리포트 표시 설정 (#209, #72)

#72 논의를 #209의 11/1 결정과 담당자 승인 범위로 구현.

- 원문 공개는 학생 본인의 전역 설정(#206). 학부모 설정으로 공개를 강제하거나 섹션을 임의 삭제하지 않음
- 순서: 생각 유형·전후 변화·돌아보기·원문 인용·요약·저녁 질문 6개 전체 순열. 학생·기간·상태·집계 기준·수치 표는 유지
- 강조: 기존 ATTEMPTS·COMPLETED·UNASSISTED 지표의 표시만 조정(계산식 불변)
- 톤: DEFAULT·EASY·CONCISE만. 숫자·인용 대조와 실패·대체 정책 유지
- 흐름: 분석 대화 화면에서 자연어 요청 → 변경안 또는 확인 질문 → 명시적 확인 → 저장. 취소·만료·입력 수정·대화 전환·오류에는 자동 저장하지 않음. AI는 허용 목록만 해석하며 학생 기록을 입력으로 받지 않음. 프롬프트 `analysis-template@1`
- core는 외부 AI HTTP 동안 DB 잠금을 유지하지 않고 응답 후 권한 재확인. 제안은 10분 만료·대화 ID 일치·일회성 확인·revision 검사. 제안 접수는 분석 사용 한도에 기록, 조회·확정은 추가 차감 없음
- 저장: 학부모별 `parent_report_template`(V22). report `CoreClient`가 학생 공개 상태와 학부모 확정 설정을 모두 읽음. 설정 조회 오류를 기본값으로 숨기지 않음
- 새 리포트에 `versions.template={settings,revision}`을 저장하고 full/free HTML·PDF·Markdown에 순서·강조 반영. 과거 판은 다시 쓰지 않음. 배포는 core V22와 내부 설정 API 먼저, report worker 나중
- 연결 검증: `REPORT_TEMPLATE_PROBE_PYTHON`에 report-service 가상환경 Python 경로를 지정하고 core에서 `gradlew test --tests '*ReportTemplate*' --rerun-tasks`. 보조 실행기 `scripts/verify_report_template_rendering.py`. 학습 기록·AI 응답·파일 저장소는 합성

## 18. report 기능 간 DB 직접 접근 제거 (#252)

응답·이벤트 계약·DB 스키마 변경 없음.

- query의 SQL을 generation의 `ReportRepository`로 옮기고 `ReportReadService`를 통해 호출
- deletion의 테이블·DB 접근은 `deletion/repository.py`. state에는 삭제 명령과 DB를 쓰지 않는 판정만. HTTP 409는 deletion service에서 생성
- 생성·복구는 `ensure_generation_allowed`, 조회는 `ensure_query_allowed`, worker 보존 기간 정리는 `prune_processed`. 호출 서비스가 소유한 세션을 전달하고 repository에서 commit하지 않음
- 삭제 완료는 generation의 학생 리포트 삭제 → outbox의 subject 삭제 → 삭제 장벽 완료·처리 이력 저장을 한 트랜잭션에서. 순서(잠금 → 장벽 저장 → S3 삭제 → DB 삭제 → core 완료 보고) 유지
- generation과 deletion은 서로의 서비스가 필요해 삭제 완료 조합 함수에서만 generation service를 지연 import
- 검증: 삭제 완료 실패 주입(장벽 완료 기록 단계 오류 → DB 전체 롤백, PENDING 유지, 완료 콜백 미전송, 재시도 성공)

## 19. 판정 요소 지표 연결 (#344)

기록 API의 판정 결과로 FN-RPT-05 생각 요소 지표를 계산해 기존 `Metric`에 붙인다. 공개 계약(learning `Element`, report `Metric`)은 바꾸지 않는다.

- learning: `ElementView`·`StoredElement`에 `code`·`goodThought`. 데모 시드 요소 code를 #262 대조표대로 변경
- report: `FeedbackInput`이 `judgment`(result·trial·elements)를 읽음. `status`가 `DONE`일 때만 쓰고, 필드가 빠지거나 같은 요소가 두 번 오면 기록 계약 오류로 생성 실패(빈 지표로 바꾸지 않음)
- **배포 순서**: learning 먼저. report는 판정이 있는 답의 `code`·`goodThought`를 필수로 읽음
- 지표는 기존 METRIC 3개 뒤에 붙어 화면·렌더러·서술 요청·숫자 대조가 그대로 사용

| 라벨 | 분자 / 분모 |
|---|---|
| 처음 답에서 확인된 생각 요소 (전체·유형별) | 처음 답에서 확인된 필수 생각 요소 수 / 처음 답의 필수 생각 요소 수 |
| 되묻기 후 새로 확인된 생각 요소 | 처음 답에서 빠졌다가 뒤 답 중 하나에서 확인된 필수 요소 수 / 처음 답에서 빠진 필수 요소 수 |
| 따져 보기 논술 · 주장·근거·반론을 모두 쓴 처음 답 | 세 코드가 처음 답에 모두 확인된 시도 수 / 세 코드를 가진 따져 보기 논술 시도 수 |
| 들어가면 좋은 생각 | 시도의 답 중 하나에서 확인된 수 / 그 요소 수 |
| 생각 요소 · {요소 이름} (표준 코드별) | 처음 답에 그 요소가 확인된 시도 수 / 그 요소가 있는 시도 수 |

결정(`generation/metrics.py` `element_tallies`):

1. **시범 판정 포함**: 사람 검증(P11) 전이라 판정이 모두 `trial`. 포함하고 `formula` 끝에 "(시범 판정 포함)"
2. **제외**: 처리 중·실패와 `HELD`, 정정된 판정(#244)은 분자·분모에서 제외. 처음 답이 제외되면 그 시도는 처음 답·보완·논증·표준 요소 지표에서 빠짐
3. **정답 요소 제외**: `ANSWER_KEY`·`FINAL_ANSWER`는 생각 요소가 아님. 고르기·순서·분류만 한 기간에는 요소 지표 없음
4. **보완은 뒤 답 중 하나**: 보완 답의 판정은 그 답 글만 보므로, 처음에 확인된 요소가 뒤에서 빠져도 줄이지 않음
5. **비율**: 기여 시도 5개 미만이면 `value` null·`INSUFFICIENT_SAMPLE`
6. **출처**: 항상 `sourceType = AI_OBSERVATION`(생각 요소는 LLM만 판정)
7. **고유 요소 `e*`**: 처음 답·보완 지표에는 넣고 표준 요소별 출현에는 넣지 않음
8. **판정이 없는 기간**: 기존 METRIC 3개만
9. **관찰은 답을 낸 주에 한 번**: 처음 답·논증·표준 요소 지표는 기간 안에 낸 처음 답만. 보완은 기간 안의 뒤 답만 보고 기간 전에 이미 채운 요소는 제외

범위 밖: 같은 유형·학년군 미션끼리 기간 비교, 요소 기반 추천(FBF-38)·생각 조각(FN-DSH-13). E2E의 llm-stub는 항상 모든 요소를 찾으므로 실제 LLM E2E는 별도.

테스트: `test_element_metrics.py`, `test_learning_client.py`.

## 20. core 일일 리포트 일정·작업·알림·조회 (#390)

P24의 core 몫. 일일 리포트를 기간 종류(`period_type`)로 일반화해 주간의 작업·Outbox·복구·재처리·알림·다운로드 경로를 그대로 쓴다.

- DB: V29·V30 `report_job.period_type`(기본값 없음), `ck_report_job_daily_period`(일일은 `period_from = period_to`), 정기 UK `(student_id, period_type, period_from) WHERE trigger='SCHEDULE'`. 알림 유형 `DAILY_REPORT_COMPLETED`·`DAILY_REPORT_FAILED`
- 일정: `DailyReportScheduler` 매일 00:00 KST, ShedLock `core-daily-reports`(주간과 별도라 월요일에 둘 다 실행). 기록 없는 날도 작업 생성
- advisory lock·정기 작업 조회·진행 중 검사·학부모 재생성 1회 모두 `(학생, period_type, period_from)` 단위
- 조회: `GET /children/{childId}/reports?periodType`. 목록·상세 응답에 항상 `periodType`. 항목 종류가 필터와 다르거나 기간 모양이 종류와 맞지 않으면 502 `REPORT_CONTRACT_INVALID`
- 재생성·재처리는 원작업의 `period`(종류 포함)를 그대로 사용
- 보호자 공개가 꺼지면 일일 `problems[]`도 판정·요소 라벨만 남김

결정:

1. **주간 명령은 `periodType`을 생략**: report-worker 수신 DTO가 `extra="forbid"`라 주간에 새 필드를 넣으면 구버전 worker에서 DLQ. 계약상 생략 = WEEKLY, 일일에만 `"DAILY"`
2. **일일은 상품 권한을 조회하지 않음**: 서술이 없어 `narrativeEnabled`는 항상 false. 결제 장애가 일일 생성·열람을 막지 않고, 일일 열람은 프리미엄 사용으로 기록하지 않음
3. **무료 사용자의 일일 상세(확인 필요)**: P24대로 무료도 전체 제공. P13 "무료는 수치만"과 겹치는 열린 결정이라 판단을 `ReportEntitlementService.dailyDetailEnabled` 한 곳에 모음(지금은 항상 true)
4. **복구·lifecycle 계약은 그대로**: jobId로 작업을 찾으므로 기간 종류를 넣지 않음
5. **목록 필터는 report에 맡김**: core가 항목을 걸러내면 페이지 봉투가 어긋나므로 필터를 전달하고 결과만 대조

테스트: `DailyReportScheduleTest`, `ReportHttpTest`, `ReportMessagingTest`, `ReportPeriodTest`.

## 21. 리포트 생성 시각 자정 변경 (#400)

2026-11-09 결정: 다음 날·월요일 아침 생성은 그날·그 주 기록을 바로 볼 수 없어 대상 기간이 끝나는 자정에 생성. 주간 `0 0 0 * * MON`, 일일 `0 0 0 * * *`. 주 경계·대상 기간 규칙·알림 즉시 발송·ShedLock 설정은 그대로. API·메시지·DB 변경 없음.

- **조기 실행 여유 1분**: 00:00은 기간 경계 바로 위라 스케줄러가 몇 ms 일찍 깨면 KST 날짜가 전날이 되어 일일은 이틀 전, 주간은 2주 전을 고름. 스케줄러가 `clock.instant() + EARLY_RUN_GRACE`(1분)를 넘김. 기간 함수의 의미는 그대로
- 테스트: `ReportPeriodTest`(조기 -100ms·정각·지연 경계)

## 22. 일일 리포트와 주간 테마 요약 (#391, 2026-11-09)

P24의 report 몫.

- 일일 리포트는 LLM 없이 문제별 판정·되묻기와 보완 답변·마지막 답변·생각 요소·돌아보기·검증된 인용을 조립. 무료·full 파일이 같은 내용. 비율·서술·저녁 질문·학부모 표시 설정은 적용하지 않음. 기록이 없으면 `COMPLETED`/`NO_RECORD`
- 기존 P08 조회는 제출일 기준이라 전날 제출하고 오늘 마무리한 시도가 빠짐 → learning 기록 조회에 daily-attempts 추가(기존 주간 계산 불변). 기록 응답에 `attempt.context` 추가
- 공개 인용은 learning evidence로 재조회해 학생·시도·답변 버전·부분 문자열 일치 확인. 실패를 정상 인용이나 `NO_RECORD`로 처리하지 않음
- `themeSummary`는 별도 learning API에서 읽음. 비교는 learning이 `COMPARABLE`로 준 요소만 표시
- DB: Alembic `20261109_06`(준비)·`20261109_07`(NOT NULL·CHECK·UK 확정, `report_item.PROBLEM`). 재생성 revision·최신 판 선택은 학생·기간 종류·시작일별. 일일 데이터가 있으면 downgrade 거부
- `report.generate.v1`의 `periodType` 생략은 WEEKLY. 복구 요청에도 `periodType` 전달
- **배포 순서**: DB 백업 → report worker 소비 중단·구버전 쓰기 차단 → 마이그레이션 → 새 learning·report-api·report-worker. 구버전 writer와 최종 스키마를 섞는 롤링 배포는 불가. learning producer(#385·#391)를 report worker보다 먼저
- `REPORT_THEME_SUMMARY_ENABLED=true`가 기본. false면 새 주간 생성에서 테마 조회만 생략

## 23. 판정 정정 영향 조회와 요소 지표 제외 (#244, 2026-11-09)

- 내부 API `GET /internal/reports/correction-impact?studentId&attemptId`: 그 시도로 만든 완료 판 목록. core가 정정 성공 후 호출(api-spec 4.4·5.7)
- 주간은 `THINKING_TYPE.missions[].attemptId`, 일일은 `PROBLEM.attemptId`로 찾음. 보호자 공유가 꺼진 판은 근거 연결을 저장하지 않아 `report_item_evidence`로는 찾을 수 없음
- `judgment.corrected`가 true인 판정은 요소 지표와 일일 요소 표시에서 제외(제외 경로는 `HELD`와 같음)
- 이미 만들어진 판은 바꾸지 않음. 표시·기록은 [core 21절](core-gateway.md#21-신고문의공지도움말-46) 「정정 영향 판정과 표시」

## 24. 일일·주간 리포트 실서버 생성 확인 (#424, 2026-11-10)

local kind에서 core → RabbitMQ → report-worker → core 알림까지 확인. 일일·주간 작업 생성, KEDA의 worker 0→1 기동, `COMPLETED`, 완료 알림까지 정상. 실제 00:00 정각 실행은 코드 테스트로만 검증.

- **운영 주의**: 약관·처리방침을 개정하면 기존 학부모가 재동의 전까지 필수 동의 판정에서 빠져 리포트 생성·알림이 멈춤(설계대로). 시연 계정은 개정 뒤 다시 로그인해 동의
- **kind 주의**: platform-data 차트를 새 큐 정의 전에 적용했으면 core가 큐 선언 오류를 반복 → platform-data를 다시 적용

## 25. 주간 대표 답변 설명 연동 (#479, 2026-11-10)

에픽 #473(설명 sLLM)의 report 몫. 계약은 api-spec 3.4·4.2.3.

- 주간·프리미엄·원문 공개 대상만 설명 단계 실행. 기존 수치 집계·요약 뒤의 선택 단계라 점수 조회나 설명 실패가 리포트 생성을 실패시키지 않음. 일일·무료는 `explanations=null`
- 후보: SYSTEM 범위 기록 목록에 `includeModelScores=true`. `modelScores.m2`가 있는 기간 내 답변을 최신순으로, 생각 유형 중복 없이 최대 3개
- 학년은 core 학생 프로필의 `grade`. 서술 초5~6·논술 초4~6만 호출. 학년이 없으면 임의로 정하지 않고 설명만 미포함
- `POST /internal/report-explanations` 요청은 `{grade,inputType,text,scores}`. 닉네임·식별자를 글에서 가리고 식별 필드는 넣지 않음
- 받은 설명의 숫자·점수·등급·금지 표현과 인용을 다시 검사. 인용은 같은 답변·버전 원문과 요청 글 양쪽의 부분 문자열이어야 함. `quote=null`은 정상(인용 영역만 생략)
- 상태: 하나 이상 검증되면 `INCLUDED`, 대상은 있지만 미활성·실패·검사 탈락이면 `NOT_INCLUDED`, 대상 없음·원문 비공개면 `NO_TARGET`. `weekly_report.verification.explanationState`에 저장, 본문은 `report_item.EXPLANATION`(Alembic `20261110_08`, 항목 CHECK만 확장). 기존 `narrative.modelExplanation`은 계속 null
- 상세·HTML·PDF·Markdown에 같은 상태와 검증된 설명 표시. 무료 다운로드 변형에는 넣지 않음. core도 현재 이용권·공개 상태로 다시 가림
- 대기 상한(CPU 실측 전 기준안): `REPORT_EXPLANATION_TIMEOUT_SECONDS=130`(ai 125초 마감보다 길게), `REPORT_EXPLANATION_BUDGET_SECONDS=400`. 최대 3건 순차, 재시도 없음. 상한 초과 시 이미 검증한 항목은 보존
- 배포 순서: core 사용량(#490) → ai API(#491), learning 점수 공급(#489)과 함께. 공급자가 구버전이면 설명 미포함으로 기존 리포트 유지
- 미실시: 실제 CPU 모델의 품질·지연 측정(#475), sLLM 서버(#476), 운영 배포

## 26. 학부모 리포트 목록 전체 반환 (#500, 2026-11-11)

- 원인: core가 report `GET /internal/reports`에 `page`·`size`를 넘기지 않아 기본 20건만 반환. 공개 `ReportList`는 `{items}`뿐이라 약 2.5주 뒤부터 과거 리포트가 목록에서 사라짐
- 결정(사용자 승인): 공개 API에 페이지를 추가하지 않고 core가 `page=0`부터 `size=100`으로 짧은 페이지가 나올 때까지 조회해 합침. 자녀 1명당 1년 약 420건이라 응답 크기가 작음
- 각 페이지에 기존 계약 검사를 적용하고 한 페이지라도 위반하면 502 `REPORT_CONTRACT_INVALID`. 50페이지(5000건)를 넘어도 같은 502
- report는 `(period_from desc, period_type)`으로 정렬하며 이 조합이 유일해 offset 페이지 사이 중복·누락 없음
- 계층 정리: `ConversationService`가 `ReportJobRepository`를 직접 쓰던 것을 `ReportQueryService.job(reportId)`로 변경

## 27. 설명 후속: 대기·종료 시간, 검사 오탐, 후보 대체 (#508, 2026-11-11)

- **복구 후보 기준 60분 → 4시간**(`app.report.recovery.stale-after` 기본 `PT4H`): 월 00:00에 주간·일일 작업이 함께 생기고 report-worker 1대·prefetch 1로 차례로 처리되어, 60분 기준에서는 설명이 켜진 뒤 약 9건 이후 대기 작업이 `REPORT_NOT_CREATED`로 실패할 수 있었음. 기준 > 주간 설명 대상 수 × (400초 + 기본 생성 시간) + 일일 처리 시간. 데모 30명 기준 약 215분. 학생 수나 설명 시간이 바뀌면 다시 계산. 진짜 유실 작업의 발견은 최대 4시간으로 늦어짐
- sLLM 가동 창(일 23:50~월 02:00)은 그대로. 창 밖 호출은 설명만 빠지고(`NOT_INCLUDED`) 리포트는 완료
- 설명 지표는 `explanationState` 비율로 정함([아키텍처 4.7](../design/architecture.md#47-운영-경보-구성-경계-187)). 규칙·임계값은 실측 뒤
- 종료 유예: report-worker `terminationGracePeriodSeconds` 480초(설명 단계 400초 + 여유 80초). prod에 설명·테마 요약 환경 변수 명시
- 수량 검사 오탐: `KOREAN_COUNT` 앞에 한글 음절이 오면 수 관형사로 보지 않음("정확한 문장" 통과, "한 문장"·"두번" 거부). 요약 검증의 같은 오탐도 해소
- 후보 선정: 생각 유형마다 최신 답변부터 시도. ai 호출 전 제외(정정·빈 답변·학년·입력 유형·점수 형식·원문 대조 실패)는 같은 유형의 다음 답변으로. ai를 한 번 부른 유형은 결과와 관계없이 다시 부르지 않음(유형당 1회, 최대 3유형)
- web 설명 본문 `white-space: pre-line`
- 미실측: 실제 sLLM·클러스터에서의 월요일 배치 시간(#475·#476). 4시간은 계산값
