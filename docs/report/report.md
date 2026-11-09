# 주간·일일 리포트 (#42·#50~#56·#129·#131·#132·#152·#167·#206·#209·#252·#344·#390·#400)

계약은 [API 명세](../design/api-spec.md) 3.4·4.1.1·4.2.1·4.4·5.5, 메시지는 [report-messages](../../contracts/events/report-messages.md).

## 1. core 주간 리포트 (#42)

- 매주 월요일 00:00 Asia/Seoul(일요일 자정, 21장), 직전 월~일 `LocalDate`, 집계 경계 `[월 00:00 KST, 다음 월 00:00 KST)`. 기록 없는 자녀도 대상
- P24 일일 리포트([서비스 기획 방향](service-direction.md)): core 몫(매일 00:00 전날 작업·`report_job.period_type`·정기 UK·알림·조회)은 20장(#390). report 몫(`weekly_report.period_type`, 재생성 UK·revision 잠금, 일일 템플릿·테마 요약)은 구현 예정([ERD 5.2](../design/erd.md#52-구현-예정-변경-report_db), #391)
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
- Outbox는 학생별 미발행 선두 중 적격 후보 100개에서 선점하며, 발행은 최대 15초다. #131에서 학생별 순서를 유지하고 실패한 학생만 1·5·15분 지연 후 격리한다. 다른 학생은 계속 처리한다. 브로커 대기 동안 트랜잭션·행 잠금은 없지만 학생별 session lock용 연결 1개를 사용한다(연결 풀과 worker 동시 실행 수를 함께 관리). [격리 조회·수동 재처리·마이그레이션](report.md#11-outbox-실패-격리와-학생별-발행-순서-131)
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

상품 권한(#48·#129, 13장), 표시 이름(#56), 생성기 조립(#56·#64), 학생 삭제(#128·#132, 14장)가 모두 연결됨. 운영 S3·Pod Identity·공개 endpoint는 AWS 데모에서 부모 다운로드까지 확인([aws-deploy](aws-deploy.md)). Chromium `/tmp` 쓰기 볼륨·guard 표식 보존·SIGTERM 유예·DLQ 복구는 배포 values 기준([prod README](../../infrastructure/gitops/environments/prod/README.md)).

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
- 구현 예정(P13·P24): 일일 리포트는 서술이 없어 무료·프리미엄 동일 제공, 이 절의 무료 가림은 주간 리포트에만 적용

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

- 생성 입력은 메시지의 과거 공개 값에 의존하지 않습니다. `NamedGenerator`가 내부 core 프로필의 현재 `parentSharingEnabled`를 조회하며 누락은 비공개입니다. 생성 직전 원문·돌아보기 문장·인용 후보·근거 링크를 제거하고 AI 서술 호출을 생략합니다. 이후 저장·HTML/PDF/Markdown 렌더링에도 제거된 항목만 전달됩니다.
- 학습 횟수·분모/분자·기간·유형과 전후 글자/문장 수는 동일하게 유지합니다. 원문을 새 문장으로 대체 생성하지 않습니다. nullable 원문 형태를 조회 스키마와 렌더러에 반영했습니다.
- 이미 공개 상태에서 만든 리포트도 core 상세에서 현재 설정을 다시 검사해 원문·인용·파생 서술을 제거합니다. 비공개 중 기존 파일 URL 재발급과 근거 조회는 403으로 막습니다. 수치 화면은 계속 제공하며 이미 전달한 파일 자체를 회수하지는 못합니다.
- 이번 구현은 비공개 전용 파일 재생성/다운로드 상품을 추가하지 않습니다. 다시 공개해도 비공개 중 생성한 리포트에 과거 원문을 자동 복원하지 않으며 필요하면 기존 재생성 규칙을 따릅니다.
- 구현 예정 일일 리포트도 같은 규칙으로 비공개 학생의 원문 인용을 제외하고 수치는 유지합니다(P24).

리포트 HTTP는 DB 트랜잭션 밖에서 실행합니다. HTTP 완료 뒤 `ReportViewService.recordWithSharing` 또는 파일 최종 기록 단계가 parent → student 순서로 현재 상품/공개 권한을 다시 확인합니다. 조회 도중 비공개 전환 시 과거 원문을 제거하고, 파일 서명 도중 전환 시 URL을 반환하지 않습니다.

## 17. 학부모 대화 기반 리포트 표시 설정 (#209, #72)

### 결정과 적용 범위

[#72](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/72)의 보고서 챗봇 논의를 [#209](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/209)의 11/1 결정과 사용자가 전달한 김태윤님 승인 답변 범위로 구현한다.

- 원문 공개는 학생 본인의 전역 설정(#206)이다. 학부모 설정으로 공개를 강제하거나 섹션을 임의 삭제하지 않는다. 메모는 제외한다.
- 순서: 생각 유형·전후 변화·돌아보기·원문 인용·요약·저녁 질문 6개 전체 순열. 학생·기간·상태·집계 기준·수치 표는 유지한다.
- 강조: 기존 ATTEMPTS·COMPLETED·UNASSISTED 지표의 표시만 조정한다. 계산식·판정 기준은 바꾸지 않는다.
- 톤: DEFAULT·EASY·CONCISE만 허용한다. 숫자·인용 대조와 기존 실패/대체 정책을 유지한다.

### 요청·저장·생성 흐름

기존 학부모 분석 대화 화면에서 자연어 요청 → 변경안 또는 확인 질문 → 명시적 확인 → 저장한다. 취소·만료·입력 수정·대화 전환·오류에는 자동 저장하지 않는다. AI는 허용 목록만 해석하며 학생 기록을 입력으로 보내지 않는다. 프롬프트 식별자는 `analysis-template@1`이다.

core는 기존 대화 소유권·연결·동의·이용권과 학부모 행 잠금을 재사용한다. 외부 AI HTTP 동안 DB 잠금을 유지하지 않고 응답 후 권한을 다시 확인한다. 제안은 10분 만료·대화 ID 일치·일회성 확인·revision 검사를 거친다. 제안 접수는 기존 분석 사용 한도와 사용 증빙에 기록하며 조회·확정에는 추가 차감하지 않는다.

학부모별 `parent_report_template`은 **V22**에 추가한다. 이미 병합된 #208 V20, #206 V21을 변경하지 않는다. report의 `CoreClient`는 현재 학생 공개 상태와 학부모 확정 설정을 모두 읽고, `NamedGenerator`가 두 값을 독립적으로 전달한다. 비공개면 기존 `RecordGenerator`가 원문·근거를 제거하고 AI 서술 호출을 생략한다. 설정 조회 오류를 기본값으로 숨기지 않는다.

새 리포트에 `versions.template={settings,revision}`을 저장하고 full/free HTML·PDF·Markdown에 순서·강조를 반영한다. 톤은 허용된 AI 서술 요청에만 전달한다. 과거 판은 다시 쓰지 않고 현재 권한으로 과거 원문/파일 접근을 막는 #206 로직을 유지한다. 배포는 core V22와 내부 설정 API를 먼저 제공한 후 report worker를 갱신한다.

### 실제 core → report 연결 재현과 한계

`REPORT_TEMPLATE_PROBE_PYTHON`에 report-service 가상환경 Python 절대 경로를 지정하고 core에서 `gradlew test --tests '*ReportTemplate*' --rerun-tasks`를 실행한다. Python 환경이 없으면 기본 CI는 core HTTP/DB 테스트만 수행하며 연결 검증을 수행했다고 집계하지 않는다.

`ReportTemplateHttpIntegrationTest`가 실제 core HTTP/JWT·PostgreSQL·Redis에서 제안 확인 후 revision 1을 저장한다. 보조 실행기 `scripts/verify_report_template_rendering.py`는 해당 core의 profile/template을 HTTP 조회해 report 생성 파이프라인과 실제 Chromium 파일 렌더링까지 실행한다. 공개·비공개 상태를 각각 확인하며 비공개는 AI 미호출·원문 제외, 공개는 EASY 톤 전달·숫자/인용 대조·무료 AI 문구 제외를 검사한다.

이 연결 검증의 학습 기록·AI HTTP 응답/서술·파일 저장소는 합성이다. 실제 외부 LLM 품질, PG, 운영 S3, 운영 배포, 브라우저부터 실제 모든 서비스까지 이어지는 단일 종단 시나리오는 검증하지 않았다. 실제 API 키나 학생 원문·모델 파일은 커밋하지 않는다.

## 18. report 기능 간 DB 직접 접근 제거 (#252)

사용자 응답(code·status·본문), 이벤트 계약, DB 스키마·마이그레이션은 변경하지 않음.

- query의 SQL을 generation의 `ReportRepository`로 이동하고 `ReportReadService`를 통해 호출한다. 최신 판을 먼저 고른 뒤 상태 필터를 적용하는 순서, 기간별 정렬·페이지, revision 선택, 항목 소속 검사, 파일 경로 검사는 유지한다.
- deletion의 테이블·DB 접근은 `deletion/repository.py`로 이동한다. state에는 삭제 명령과 DB를 사용하지 않는 중복·경합·생성 허용 판정을 둔다. HTTP 409 오류는 deletion service에서 만든다.
- 생성·복구는 `ensure_generation_allowed`, 조회는 `ensure_query_allowed`, worker의 보존 기간 정리는 `prune_processed`를 호출한다. 호출 서비스가 소유한 세션을 전달하고 repository에서 commit하지 않는다.
- 삭제 완료는 generation service의 학생 리포트 삭제 → outbox service의 subject 삭제 → 삭제 장벽 완료·처리 이력 저장을 기존 한 트랜잭션에서 실행한다. 잠금 → 장벽 저장 → S3 삭제 → DB 삭제 → core 완료 보고 순서를 유지한다.
- 이전 테스트의 `deletion.state` 테이블 import 호환은 `__getattr__`의 지연 재노출 두 이름만 남긴다. 업무 코드에서는 이 호환 경로를 사용하지 않는다. state에 SQLAlchemy·ApiError·DB 함수는 없다. 테이블의 정식 소유자는 deletion.repository다.
- generation과 deletion은 서로의 서비스 기능이 필요하므로 삭제 완료 조합 함수에서만 generation service를 지연 import한다. 새 공통 라이브러리 없이 기존 서비스 경계를 사용한다.
- repository의 `finish`는 자기 장벽·이력만 저장한다. 여러 기능을 정리하는 테스트는 서비스의 `finish_deletion`을 호출하도록 갱신했다.

검증은 report 전체 테스트와 삭제 완료 실패 주입을 사용한다. 실패 주입은 리포트·Outbox 삭제 이후 장벽 완료 기록 단계에서 오류를 발생시켜 DB 전체 롤백, PENDING 장벽 유지, 완료 콜백 미전송, 같은 명령 재시도 성공을 확인한다. 실제 학생 데이터·운영 DB는 사용하지 않는다.

## 19. 판정 요소 지표 연결 (#344)

주간 리포트가 판정 결과를 쓰지 않아 수치가 시도 수·완료 수·도움 없이 시작한 비율·글자 수 변화뿐이었다. 무료 플랜은 수치만 보므로(P13) 이것이 받는 정보 전부였다. 기록 API의 판정 결과로 FN-RPT-05 생각 요소 지표를 계산해 기존 `Metric`에 붙인다. 공개 계약(learning `Element`, report `Metric`)은 바꾸지 않는다.

### 연결

- learning: `ElementView`·`StoredElement`에 `code`·`goodThought`를 넣었다(`findStoredElements`가 `rubric_element` 조인에서 읽음, 체크리스트는 기준표 요소 값). 계약(OpenAPI `Element`)에는 #262에서 이미 있던 필드다. 데모 시드 요소 code를 #262 대조표대로 바꿨다(요소 56개: 표준 44·정답 7·고유 5). 같은 행의 code만 바꿔 지난 판정은 `rubric_element_id`로 이어진다
- report: `FeedbackInput`이 `judgment`(result·trial·elements의 code·goodThought·satisfied)를 읽는다. `status`가 `DONE`일 때만 쓰고, 필드가 빠지거나 같은 판정에 같은 요소가 두 번 오면 기록 계약 오류로 생성을 실패시킨다(빈 지표로 바꾸지 않음)
- 배포 순서: learning을 먼저 배포한다. report는 판정이 있는 답의 `code`·`goodThought`를 필수로 읽으므로, 이 필드를 주지 않는 이전 learning에 붙으면 판정이 있는 기간의 생성이 계약 오류로 실패한다(빈 지표로 넘어가지 않음)
- 지표는 기존 METRIC 3개 뒤에 붙는다. 화면(`MetricCards`)·파일 렌더러·서술 요청(`metric_line`)·숫자 대조(`allowed_numbers`)가 METRIC을 그대로 쓰므로 그쪽 코드는 바꾸지 않았다. 강조 지표(`highlightMetrics`)는 기존 3개 라벨만 가리킨다

### 지표 (`generation/metrics.py` `element_tallies`)

| 라벨 | 분자 / 분모 |
|---|---|
| 처음 답에서 확인된 생각 요소 (전체·기록 있는 유형별) | 처음 답에서 확인된 필수 생각 요소 수 / 처음 답의 필수 생각 요소 수 |
| 되묻기 후 새로 확인된 생각 요소 | 처음 답에서 빠졌다가 2번째 이후 답 중 하나에서 확인된 필수 요소 수 / 처음 답에서 빠진 필수 요소 수 |
| 따져 보기 논술 · 주장·근거·반론을 모두 쓴 처음 답 | 세 코드가 처음 답에 모두 확인된 시도 수 / 세 코드를 가진 따져 보기 논술 시도 수 |
| 들어가면 좋은 생각 | 시도의 답 중 하나에서 확인된 들어가면 좋은 생각 수 / 그 요소 수 |
| 생각 요소 · {요소 이름} (표준 코드별) | 처음 답에 그 요소가 확인된 시도 수 / 그 요소가 있는 시도 수 |

### 결정

1. **시범 판정 포함**: 사람 검증(P11) 전이라 지금 판정은 모두 `trial`이다. 빼면 지표가 하나도 나오지 않아 포함하고, 시범 판정이 섞인 지표는 `formula` 끝에 "(시범 판정 포함)"을 붙인다(FN-JDG-03 "AI 채점(시범)" 표시)
2. **제외**: 처리 중·실패(판정 없음)와 `HELD` 판정은 분자·분모에서 뺀다. 처음 답이 제외되면 그 시도는 처음 답·보완·논증·표준 요소 지표에 들어가지 않는다(기준이 없음). 들어가면 좋은 생각은 다른 판정 답으로 센다
3. **정답 요소 제외**: `ANSWER_KEY`·`FINAL_ANSWER`는 생각 요소가 아니라 정답 여부라(1.5) 모든 요소 지표에서 뺀다. 고르기·순서·분류만 한 기간에는 요소 지표가 없다
4. **보완은 뒤 답 중 하나**: 보완 답의 판정은 그 답 글만 본다(learning 체크리스트와 같은 이유). 그래서 처음에 확인된 요소가 뒤 답에서 다시 빠져도 줄이지 않고, 처음에 빠진 요소가 뒤 답 중 하나에서 확인되면 센다
5. **비율**: P08처럼 그 지표에 기여한 시도가 5개 미만이면 `value`는 null·`INSUFFICIENT_SAMPLE`이고 개수·분자·분모만 둔다. `count`는 분자다(기존 METRIC과 같음)
6. **출처**: 생각 요소는 LLM만 판정하므로(규칙 판정은 정답 요소뿐) `sourceType = AI_OBSERVATION`
7. **고유 요소 `e*`**: 처음 답·보완 지표에는 넣고(그 미션 충족률), 표준 요소별 출현에는 넣지 않는다(1.5). 따져 보기 논술 지표는 세 표준 코드를 모두 가진 시도만 센다(#262 전 기준표 제외)
8. **판정이 없는 기간**: 판정이 없거나 모두 처리 중·실패·보류면 기존 METRIC 3개만 나온다. 기여한 시도가 없는 지표는 만들지 않는다
9. **관찰은 답을 낸 주에 한 번**: 지난주에 시작해 이번 주에 고친 시도는 처음 답이 지난주 리포트에 이미 들어갔다. 그래서 처음 답·논증·표준 요소 지표는 기간 안에 낸 처음 답만 센다. 보완은 기간 안의 뒤 답만 보고, 기간 전 뒤 답에서 이미 채운 요소는 분자·분모에서 뺀다. 들어가면 좋은 생각도 기간 전에 확인된 것은 뺀다. 기존 기록 지표·전후 변화(P08 포함 기준)는 그대로다

### 이슈와 다른 점

- 이슈 결정 5 "규칙 판정만이면 `RULE`" → 항상 `AI_OBSERVATION`. 정답 요소를 빼면 남는 생각 요소는 LLM만 판정하고, 기록 API에는 판정 방식(`method`)이 없으며, 요소 `sourceType`은 충족된 요소에만 있어 출처를 요소에서 고를 수 없음
- 이슈 "들어가면 좋은 생각: 마지막 답에서 확인된 수" → 시도의 판정 답 중 하나에서 확인된 수. 보완 답은 그 답 글만 판정해 앞 답에서 확인된 생각이 마지막 답에서 다시 빠질 수 있음(결정 4와 같은 이유)
- 이슈 "따져 보기 논술 답 수" → 세 표준 코드를 모두 가진 따져 보기 논술 시도 수(#262 전 기준표가 분모를 키우지 않게)
- 이슈에 없던 배포 순서(learning 먼저)를 넣음
- 이슈 확인 필요(report 담당의 시범 판정 포함·라벨 문구, 프론트 담당의 `MetricCards` 배치)는 이 PR에서 제안대로 구현하고 리뷰에서 확정한다. 리포트 상세는 지표를 항목마다 나열하는 문서형이라 화면 수정은 하지 않음

### 범위 밖

판정 정정의 요소 지표 반영(정정은 `judgment_correction`에 결과만 남기고 요소 충족은 바꾸지 않음, #244 FN-SUP-03), 같은 유형·학년군 미션끼리 기간 비교(FN-RPT-05), 요소 기반 추천(FBF-38)·생각 조각(FN-DSH-13), web 요소 고르기(#356, 관리자 code 검사는 #353에서 구현), 실제 LLM으로 학생부터 리포트까지의 E2E(지금 E2E의 llm-stub는 항상 모든 요소를 찾음).

### 검증

- learning: 전체 테스트 290개 통과(Testcontainers). `SharedResponsesJsonTest`는 의도한 변경으로 기대 JSON에 `code`·`goodThought`를 넣음
- 로컬 실연(이 브랜치로 learning·report 재빌드, 실제 ai-service·OpenAI 판정): 초5 데모 미션 5개를 core 경로로 풀어(되묻기 답 3건) 리포트를 생성. 지표가 손 계산 기대값과 같음(처음 답 8/11, 보완 3/3, 논증 1/1, 들어가면 좋은 생각 4/4), LLM 서술이 새 지표를 인용하고 숫자·인용·금지어 대조 통과, 기록에 물어보기 응답 대조 통과. 답 글은 직접 지은 합성 문장
- 주별 합계 불변식(개인 검증, 저장소 밖 스크립트): 무작위 합성 기록 300명분(여러 주에 걸친 시도, 처리 중·실패·보류 섞임)을 4주로 나눠 계산해, 주별 분자·분모 합이 전체 기록에서 직접 센 값과 같음(처음 답·보완·들어가면 좋은 생각·표준 요소 14종). 기간 구분을 뺀 이전 동작으로는 같은 검사가 실패함(처음 답 중복)
- report: `ruff check`·`ruff format --check`, 전체 `pytest`. 새 테스트 `test_element_metrics.py`(제외 규칙·5개 미만·보완·논증·들어가면 좋은 생각·표준 요소·숫자 대조 허용·기간 경계)와 `test_learning_client.py` 판정 파싱 4건. 기록은 모두 합성

## 20. core 일일 리포트 일정·작업·알림·조회 (#390)

2026-11-06 결정 P24(FN-RPT-14·15, FN-SUP-08)의 core 몫. 일일 리포트를 새 테이블·메시지가 아니라 기간 종류(`period_type`)로 일반화해 주간의 작업·Outbox·복구·관리자 재처리·알림·다운로드 경로를 그대로 쓴다([서비스 기획 방향 5장](service-direction.md#5-설계-판단)). report-worker의 일일 생성·`weekly_report.period_type`은 #391 몫이라 다루지 않았다.

### 구현

| 영역 | 내용 |
|---|---|
| DB | V29 `report_job.period_type` NULL 허용 추가 → V30 기존 행 `WEEKLY` 채움, NOT NULL·`ck_report_job_period_type`·`ck_report_job_daily_period`(일일은 `period_from = period_to`), V2 `uq_report_job_scheduled_week (student_id, period_from)`를 `uq_report_job_scheduled_period (student_id, period_type, period_from) WHERE trigger='SCHEDULE'`로, 목록 인덱스를 `(student_id, period_type, period_from)`으로 교체. 알림 CHECK에 `DAILY_REPORT_COMPLETED`·`DAILY_REPORT_FAILED`. 기본값 없음(검증 스크립트 규칙) |
| 도메인 | `ReportPeriodType(DAILY·WEEKLY)`, `ReportPeriod(from, to, type)`(주간 월~일, 일일 하루 검사), `ReportPeriod.previousDay`(KST 전날, 토·일 포함), `ReportJob.periodType`·`period` |
| 일정 | `DailyReportScheduler` 매일 00:00 KST(대상일 자정, 21장), ShedLock `core-daily-reports`(주간 `core-weekly-reports`와 따로라 월요일에 둘 다 돈다). 대상·동의·자녀별 실패 격리는 주간과 같은 `ReportScheduleService.generate(at, type)`. 기록 없는 날도 작업을 만든다 |
| 잠금·횟수 | advisory lock 키·정기 작업 조회·진행 중 검사·학부모 재생성 1회 모두 `(학생, period_type, period_from)` 단위. 월요일 일일·주간 작업이 서로 막지 않는다 |
| 메시지 | `report.generate`에 선택 필드 `periodType`. 일일만 `"DAILY"`를 넣고 주간은 필드를 생략(=WEEKLY). 일일 `narrativeEnabled`는 항상 false이고 상품 권한을 조회하지 않는다 |
| 알림 | `ReportJobFinished.periodType`으로 일일 완료·실패를 `DAILY_REPORT_COMPLETED`·`DAILY_REPORT_FAILED`("일일 리포트가 완성되었습니다." 등)로 만든다. 수신 설정은 유형별 독립이라 PUT 1~8개 |
| 조회 | `GET /children/{childId}/reports?periodType`(생략 시 전체). core는 필터를 report에 전달하고 항목의 `periodType`(생략 = WEEKLY)이 필터와 다르거나 기간 모양이 종류와 맞지 않으면 502 `REPORT_CONTRACT_INVALID`. 목록·상세 응답에 항상 `periodType`을 채운다. 상세·다운로드는 작업의 종류와 report 응답의 종류를 대조한다 |
| 재생성·재처리 | 학부모 재생성·SERVICE_OPS 관리자 재생성·관리자 실패 작업 재처리 모두 원작업의 `period`(종류 포함)를 그대로 쓴다. 응답 `ReportJobAccepted`에 `periodType` |
| 원문 가림 | 보호자 공개(#206)가 꺼지면 일일 `problems[]`도 판정·요소 라벨만 남기고 되묻기·최종 답·돌아보기·인용을 비운다 |

### 결정

1. **주간 명령은 `periodType`을 생략**: 현재 report-worker 수신 DTO가 `extra="forbid"`라 주간 명령에 새 필드를 넣으면 #391 배포 전 주간 생성까지 DLQ로 간다. 계약상 생략 = WEEKLY라 주간은 이전 모양을 유지하고 일일에만 넣는다. report(#391)가 배포되기 전에 이 PR이 배포되면 일일 명령만 실패하고(주간은 영향 없음), 남은 일일 작업은 기존 종료 유실 복구(#132)의 대조 대상이 된다
2. **일일은 상품 권한을 조회하지 않음**: 서술이 없으므로 `ReportPeriodType.narrative = false`로 두고 생성·상세·다운로드에서 상품 조회를 건너뛴다. 결제 장애가 일일 생성·열람을 막지 않고, 일일 열람은 프리미엄 사용(환불 판정 `reportViewed`)으로 기록하지 않는다
3. **무료 사용자의 일일 상세(확인 필요)**: 이슈·P24대로 무료도 전체(문제별 되묻기·보완 답변·인용 포함)를 준다. P13 "무료는 수치만"과 겹치는 열린 결정이라 판단을 `ReportEntitlementService.dailyDetailEnabled` 한 곳에 모았다. 지금은 항상 true이며, false로 바꾸면 `ReportQueryService`가 일일 `problems[]`를 원문 가림과 같은 범위로 줄인다
4. **복구·lifecycle 계약은 그대로**: `report.started|completed|failed`와 `/internal/report-jobs/{jobId}/reconcile`은 jobId로 작업을 찾으므로 기간 종류를 넣지 않았다(report의 reconcile 요청 DTO도 `extra="forbid"`). core는 응답 기간을 작업의 종류로 검사한다
5. **목록 필터는 report에 맡김**: core가 항목을 걸러내면 report의 페이지 봉투가 어긋나므로 필터를 그대로 보내고 결과만 대조한다. #391 전 report는 `periodType` 쿼리를 무시해 `?periodType=DAILY`가 주간 항목을 돌려주므로 502가 된다(필터 없는 목록은 정상)

### report(#391)와 맞출 계약

- `report.generate`의 `periodType` 생략·`WEEKLY`를 같게 처리, `DAILY`면 `periodFrom = periodTo`
- 목록·상세 항목에 `periodType`(생략하면 core가 WEEKLY로 본다), `?periodType` 필터
- 일일 상세는 `ReportDetail`의 필수 필드(`metrics`·`quotes`·`narrative: null`·`eveningQuestion: null` 등)를 그대로 두고 `problems[]`를 더한다. `problems[]` 항목 모양은 web(#394) `DailyProblem`과 OpenAPI `DailyReportProblem`을 따른다
- 재생성 판 잠금·UK를 `(student_id, period_type, period_from)` 단위로

### 검증

검증 결과는 PR 본문에 적는다. 로컬은 JDK 21 임시 컨테이너(Testcontainers)와 일회용 PostgreSQL 컨테이너로 CI와 같은 명령을 실행했다.

- core: `./gradlew clean test bootJar`. 새 `DailyReportScheduleTest`(월요일 일일·주간 동시 생성, 재실행 0건, 일일은 상품 조회 없음, 토·일 대상일, 종류별 재생성 1회·진행 중 검사, 일일 알림 유형·독립 수신 거부, DB CHECK·UK), `ReportHttpTest` 일일 목록 필터·상세·원문 가림·다운로드·재생성, `ReportMessagingTest` 실제 RabbitMQ로 일일·주간 명령, `ReportScheduleLockTest` 일일 잠금 독립, `ReportPeriodTest` KST 전날·일일 cron
- 계약: 루트 `python -O -m unittest discover -s scripts/tests`(report.generate `periodType` 스키마 검사 추가, 계약 지문 테스트에 #390 승인 변경 정규화), `validate_report_contracts.py`(실제 일일 명령·일일 상세 산출물 추가), `validate_notification_contracts.py`
- DB: `scripts/check_db_migrations.py`(적용·재실행·report 왕복, ERD 대조). 일일 CHECK·NOT NULL·정기 UK 음수 사례를 `verify_db_schema.py`에 추가
- 범위 밖: report와 붙인 월요일 일일·주간 실제 생성·완료 알림(#391 머지 후), web 화면 확인(#394 머지됨, mock 기준 동기화만 확인)

## 21. 리포트 생성 시각 자정 변경 (#400)

2026-11-09 결정([서비스 기획 방향 7장](service-direction.md#7-2026-11-09-생성-시각-변경), 설계 PR #399): 다음 날·월요일 아침 생성은 학부모가 그날·그 주 기록을 바로 볼 수 없어 대상 기간이 끝나는 자정에 만든다. 주 경계 월~일·대상 기간 규칙·알림 즉시 발송은 그대로이고 실행 시각만 바꿨다.

### 구현

| 항목 | 이전 | 이후 |
|---|---|---|
| 주간 `WeeklyReportScheduler` | `0 0 7 * * MON` | `0 0 0 * * MON`(일요일 자정) |
| 일일 `DailyReportScheduler` | `0 0 7 * * *` | `0 0 0 * * *`(대상일 자정) |
| 서비스에 넘기는 실행 시각 | `clock.instant()` | `clock.instant() + EARLY_RUN_GRACE`(1분) |

ShedLock 이름(`core-weekly-reports`·`core-daily-reports`)·`lockAtMostFor`(30분)·`lockAtLeastFor`(1분), `ReportPeriod.previousDay/previousWeek`, 월요일 주간·일일 동시 실행은 그대로다.

### 결정

1. **조기 실행 여유 1분**: 아침 실행은 시각이 몇 초 앞뒤로 흔들려도 같은 KST 날짜였지만 00:00은 기간 경계 바로 위다. 스케줄러가 몇 ms라도 일찍 깨면(23:59:59.9) `clock.instant()`의 KST 날짜가 전날이 되어 일일은 이틀 전, 주간은 2주 전을 고른다. 기간 함수는 "실행 시각의 KST 날짜 기준 전날·직전 주" 의미를 유지하고, 스케줄러만 1분을 더해 넘긴다. 늦은 실행은 같은 KST 날짜 안이면 대상이 같다
2. **API·스키마 변경 없음**: 공개·내부 API, `report.generate` 메시지, DB는 바뀌지 않는다. `api-spec.md`·`class-diagram.md`의 "자정 변경은 구현 예정" 표기와 계약 문서 시각만 정리했다
3. **화면 문구는 다루지 않음**: web 학부모 화면 안내는 #401. `docs/outputs/user-flow`·`docs/screen-design` 산출물의 생성 시각 표기도 이 PR 범위 밖이다

### 검증

- core: `./gradlew test bootJar` 통과(525개, 실패 0, 로컬 JDK 21 + Testcontainers). `ReportPeriodTest` 주간·일일 cron 00:00, 월요일 00:00 실행이 조기(-100ms)·정각·지연(+5초, +29분)이어도 일일 10-25·주간 10-19~10-25를 고르는 경계 테스트, `ReportScheduleLockTest` 스케줄러가 여유를 더한 시각으로 호출, `DailyReportScheduleTest` 00:00 실행 시각
- 계약·스크립트: 루트 `python -O -m unittest discover -s scripts/tests` 175개 통과
- `git grep -nE "0 0 7|07:00"`: core·계약·`docs/report`·`docs/design`에 현재 시각으로 남은 07:00 없음(21장 표의 이전 값·서비스 기획 방향 7장 변경 전 서술은 이력)
