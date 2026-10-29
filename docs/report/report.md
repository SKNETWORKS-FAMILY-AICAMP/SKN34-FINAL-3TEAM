# 주간 리포트 (#42·#50~#55)

통합 원본: issue-42-weekly-reports, report-generation-foundation, report-metrics, report-narrative, report-rendering, report-query, report-deletion, report-deletion-schema, report-learning-integration, report-required-inputs, report-service-handoff, report-epic-readiness

계약은 [API 명세](../design/api-spec.md) 3.4·4.1.1·4.2.1·4.4·5.5, 메시지는 [report-messages](../../contracts/events/report-messages.md).

#152 관리자 실패 작업 재처리는 새 jobId·ADMIN_RETRY와 기존 생성/revision을 재사용한다. 원작업 연결·관리자 접수는 core #47, report 실행·중복 방어·기존 판 보존은 [#152 검토](issue-152-report-admin-retry.md)를 따른다. 기존 #50의 종료 작업 단순 재전달 종료 정책은 유지한다.

## 1. core 주간 리포트 (#42)

- 매주 월요일 07:00 Asia/Seoul, 직전 월~일 `LocalDate`, 집계 경계 `[월 00:00 KST, 다음 월 00:00 KST)`. 기록 없는 자녀도 대상
- ShedLock(Spring/JDBC, 기존 `shedlock` 테이블, `usingDbTime`) + SCHEDULE 부분 UK로 재실행 중복 방지, 자녀·기간별 advisory transaction lock으로 정기·재생성 직렬화. 자녀별 실패는 격리하고 실행 끝에 전파
- 작업 저장과 `OutboxWriter.append`는 같은 트랜잭션, HTTP는 밖. 기존 core `OutboxRelay`는 `@Transactional` 안에서 브로커 발행·confirm을 기다리는 제약이 있음(공통 기반, 미변경)
- 재생성: 부모는 자녀·주 계열 REGENERATE 1회(재생성 결과로 다시 요청해도 우회 불가), SERVICE_OPS 관리자는 ADMIN_RETRY 무제한. revision은 report가 배정
- 상품 권한: #48에서 `ReportEntitlementService → ProductEntitlementService`를 연결했다. 생성 시 실제 상품·구독의 narrativeEnabled를 사용하며 설정·판정 오류는 job·Outbox 생성 전에 전파한다. 조회 연결은 11장(#129)을 따른다.
- lifecycle 이벤트 data는 `jobId·studentId·reportId`(failed는 `failureReason`). core는 식별자 대조 후 `processed_event`·조건부 전이·`job_execution`을 원자 저장. 종료 후 늦은 started·상반된 종료 이벤트는 무시. 종료 전이가 반영될 때만 `ReportJobFinished` 발행(알림 연결점)
- 조회: Controller → `ReportQueryService` → `ReportClient`. reportId의 자녀는 core `report_job`으로 식별, 연결·동의 확인 후 scope를 그 자녀로 제한. 상세 응답의 자녀·기간·UUID 대조 후 실제 반환 판 ID로 `report_view` 저장(목록·다운로드는 열람 아님). 다운로드는 pdf·md만

## 2. 생성 기반 (#50)

- report-worker가 `report.generate`를 받아 작업 상태·결과 이벤트를 중복 없이 저장·발행. 공유 v1 스키마를 재사용(`report.generate` data는 `jobId·studentId·periodFrom·periodTo·trigger·narrativeEnabled` 6개, 요청 시각은 봉투 `time`)
- `narrativeEnabled`는 필수 boolean. 누락·잘못된 형식은 DLQ
- `app/messaging/contracts.py`는 엄격한 수신 DTO, `app/generation/codec.py`가 payload를 내부 모델로 변환. `requested_at`은 봉투 time을 보존(삭제 장벽에서 사용)
- Outbox는 처리 중인 앞 100개 후보를 건너뛰어 다른 행을 선점, 발행은 최대 15초. 브로커 대기 동안 트랜잭션·행 잠금은 없지만 session lock용 연결 1개 사용(연결 풀과 worker 동시 실행 수를 함께 관리)
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
- 무료·NO_RECORD는 AI 생략. 알려진 닉네임은 본문에서 가리고 이름·학생 식별 필드는 요청에 넣지 않음. 닉네임 공급 경로는 미연결(공유 메시지에 임의로 추가하지 않음)

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
- 이용 권한은 core가 `X-Report-Narrative-Enabled`로 전달(없으면 false). 생성 당시 유료였다는 이유로 유료 파일을 서명하지 않음. core의 상세·파일 요청에서 설정하며 반환 직전 권한 재확인도 수행한다(11장)

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

## 9. 남은 연결

| 항목 | 담당 | 내용 |
|---|---|---|
| 상품 권한 | core·상품 | #48 실제 판정 연결, #129 조회 헤더·최종 권한 확인(11장) |
| 표시 이름 | core | AI 전송 전 이름 가림·파일 제목용 닉네임 내부 조회 경로 |
| 생성기 조립 | report | worker 기본 생성기를 계산 → 서술 → 렌더링으로 연결 |
| 삭제 전체 | learning·core | learning `student.deleted` 소비·완료 보고, 삭제 학생의 queued job 정리·늦은 이벤트 무시 |
| 운영 | 인프라 | 운영 S3·IAM/IRSA·공개 endpoint, Chromium `/tmp` writable volume, guard 표식 보존·SIGTERM 유예·DLQ 복구 |

## 10. 로컬 #56 작업과 이전 통합 검증 기록

develop `f9df2d3` 기준 #56에서 기본 worker와 실제 core 별명 API를 연결했다. 최신 완료 조건 대조와 재현 방법은 [worker 통합 검증](report-worker-integration.md)을 따른다. 아래 결과는 **c608f52 기준 과거 실행 결과**다.

## 2026-10-29 develop 통합 재검증

목적은 #52 AI 서술 검증 → #53 파일 생성·저장 → #54 조회·다운로드 → #55 삭제의 누적 회귀와 문서 정합성 확인이다. 기준은 #52 PR #109, #53 PR #116, #54 PR #117, #55 PR #118이 병합된 develop `c608f52`이며, 로컬 `test/report-integration`에서 실행했다.

| 검사 | 이번 결과 |
|---|---|
| 잠금 파일 기준 의존성 동기화, Ruff check/format | 통과, 78개 파일 포맷 일치 |
| report 전체 pytest | **239 passed**, 196.38초, 실패·생략 없음. 기존 Starlette/httpx 폐기 예정 경고 1개 |
| 공통 계약·스키마 검사 | 일반 및 `python -O` 실행 각각 **58개 통과** |
| 일회용 DB 마이그레이션 | 세 DB ERD 대조, 제약 음성 사례 60개, CHECK 값 집합 67개, 인덱스 23개 통과. 반복 no-op 및 report downgrade/upgrade 통과, 23.9초 |
| 운영 Docker 이미지 | `local/report-integration:20261029` 빌드 통과 |
| 운영 이미지 렌더링 | UID 10001, read-only root, network none, `/tmp` tmpfs. HTML·MD·PDF 생성. 한글 PDF 191,409바이트·2쪽, 한글 텍스트·None 미출력 확인. 이번에는 PNG 시각 검사는 수행하지 않음 |
| 실제 learning → report | 최신 JDK 21 bootJar 사용, **8개 항목 통과**. 여섯 입력 방식 집계·OpenAPI·근거 원문·403·무료/유료 상세·3종 파일·101건 페이지·삭제 표식 |
| 문서/작업 상태 | 대상 14문서·57개 로컬 링크 확인. 충돌 표식 및 `git diff --check` 이상 없음 |

실제 DB·RabbitMQ·MinIO 테스트와 AI/core HTTP 대역 검사는 구분한다. #52 API 장애 FAILED 및 대조 실패 TEMPLATE 정책, #53 파일/실패 처리, #54 권한·revision·nullable 응답, #55 중복·실패 재시도·다른 학생 보존은 전체 pytest에 포함된다. 실제 learning 연동의 삭제 표식 검사는 삭제 이벤트 소비자 전체 E2E가 아니다.

### 발견한 문제와 수정

1. 이 컴퓨터의 Docker 시작이 오래된 `sailor-ingest.sock`·`engine.sock`으로 실패했다. 해당 런타임 폴더를 백업 후 재시작해 복구했다. 최초 실행의 **154 passed / 85 setup errors**는 환경 실패이며 최종 통과 수치에 합산하지 않는다. 이미지·볼륨·기존 저장소 `output/`은 삭제하지 않았다.
2. `state-diagram.md` 2.2와 `sequence-diagram.md` 10.1은 PROFILE만 학생 차단한다고 설명했으나, 실제 `ChildManagementService.confirm`은 두 scope 모두 차단한다. 현재 구현대로 설명을 정정했다. RECORDS 학습 재개 정책을 새로 정하거나 서비스 코드를 변경하지 않았다.
3. 실제 learning 연동 스크립트의 합성 분류 미션에 #79의 `categories`가 없어 제출이 422로 거부됐다. 미션에 g1/g2 그룹을 등록하도록 검증 데이터만 수정했고, 전체 8개 연동 검사를 재실행하여 통과했다. 제출 검증 규칙은 완화하지 않았다.

### 남은 외부 연동 및 보관

당시 미연결이던 기본 worker와 core 별명 공급은 후속 #56에서 연결했다. #64 실제 AI API·core 상품 권한 헤더 전달·운영 AWS·전체 서비스 E2E는 별도 연동 검증 범위다. 이 검증 당시 core `ReportClient`는 상품 권한 헤더를 공급하지 않아 report가 무료 기본값을 적용했다. 후속 #129 연결은 11장을 따른다. #56의 직접 메시지 발행·report 내부 API 검증을 사용자 대상 전체 흐름 검증으로 해석하지 않는다.

결과는 저장소 밖 `C:/Users/playdata2/Desktop/final/tmp/`의 `report-integration-20261029-final.xml`, `report-integration-pdf-20261029/`, `report-learning-20261029-final/`에 보관했다. 테스트 자원은 정리했다. 문서와 검증 스크립트 수정은 로컬 테스트 브랜치에만 남기며 원격 push·PR·병합은 수행하지 않았다.


## 11. 현재 이용권 연결 (#129)

### 설계와 범위

시작 시점 develop `c364ed4` 기준, #48에서 상품 판정과 생성 명령 연결은 이미 반영됐지만 조회 클라이언트는 이용권 헤더를 보내지 않아 report가 기본 false를 적용한다. 기존 공급자를 재사용하고 상세·파일 요청에 검증된 현재 권한을 전달한다. API 명세 5.8의 요청 시 선택 범위와 반환 직전 재확인 규칙을 따른다.

- core의 `ReportClient`, `ReportQueryService`, `ReportViewService` 및 관련 테스트가 변경 대상이다. 기존 payment 판정·report 공급자·DB·메시지 형식은 유지한다.
- 무료 상세의 AI 세 필드(서술·저녁 질문·생각 유형 summary)를 가리고, 무료 다운로드는 이미 생성된 free 파일을 사용한다. full URL은 최종 권한 상실 시 거부한다.
- 무료 응답을 요청한 뒤 권한이 생긴 경우 프리미엄 사용을 기록하지 않는다. 환불과 같은 parent 잠금, 학생·동의 검사, 응답 학생·기간·판본 검사를 보존한다.
- 데모 특례와 새로운 의존성은 추가하지 않는다. #132 작업 고착 정리는 별도 범위다.

### 검증 계획

실제 상품·구독 공급자의 무료·프리미엄·유예·만료·환불 상태, 설정 오류, 정기·재생성 job/Outbox를 검증한다. HTTP 경로는 위조 헤더 무시, 무료/전체 전달, 상세·다운로드 도중 권한 변경, 동일 판본 파일 선택, 프리미엄 사용 기록을 검사한다. 구현 완료 후 core 전체 테스트·계약 검사·실제 core/report 연결·diff 검사를 수행하고 실행 결과를 여기에 기록한다.


### develop 추가 반영

작업 도중 병합된 #114의 develop `26f3788`을 fast-forward로 반영했다. API 명세 끝의 #41 계약과 #129 계약을 모두 보존해 문서 추가 위치 충돌만 해결했으며 분석 대화·공통 코드·OpenAPI는 새 develop 그대로다. 최종 core 전체·계약 검증은 이 통합 상태에서 수행한다.


### #129 검증 범위와 결과

- 공통 계약: `python -O -m unittest discover -s scripts/tests -q` — develop 추가 반영 후 76개 통과.
- report 소비자: `python -m pytest tests/test_report_query.py -q` — 31개 통과. 임시 PostgreSQL을 사용하며 기존 Starlette/httpx 폐기 예정 경고 1개가 있다.
- 실제 HTTP: 격리 PostgreSQL·RabbitMQ·Redis·MinIO와 실제 core/report 앱으로 5개 시나리오를 통과했다. 프리미엄 상세·full PDF/MD 다운로드, 무료 전환 후 AI 세 필드 제외·free PDF/MD 다운로드(위조 공개 헤더 포함), 무료 재생성 job/Outbox, 무료 상품 비활성 시 명시적 503, 무료 요청의 프리미엄 사용 미기록을 확인했다.
- 위 실제 HTTP 검증은 합성 계정·상품·구독·저장 리포트·파일 바이트를 사용했다. 실제 PG·Google·AI 호출, worker 생성·렌더링, 브라우저·운영 배포·성능 검증은 아니다. 다운로드 URL을 실제 MinIO에 요청해 free/full 객체 내용까지 대조했다. 이 연동 검증은 최초 기준의 #129 구현 JAR이며, 이후 develop 반영에서도 report production 변경 3개 파일은 동일하다.
- 환경 보완: 기존 가상환경에 pytest가 없어 전용 worktree에서 `uv sync --frozen`으로 준비했다. Windows JDK의 selector/socket 기동 오류를 피하려고 Docker JDK 21을 사용했다. 동시 검증 부하로 Redis 초기화가 2초를 넘겨, 실제 HTTP 검증 실행에만 Redis connect/command timeout을 10초로 설정했다. 저장소 기본값은 변경하지 않았다. 임시 연동 컨테이너·DB·파일은 검증 종료 시 제거했다.
- 최초 core 전체 실행은 294개 중 새 환불 경합 테스트 1개가 실패했다. 합성 결제의 APPLIED 상태·상품 snapshot·charge attempt 누락을 보완한 뒤 해당 클래스 9개 모두 통과했다. 제품의 환불 검사를 완화하지 않았다.
- 실제 core 테스트 산출물로 `validate_report_contracts.py`와 `validate_notification_contracts.py`를 실행해 report 명령·종료 이벤트·상세 응답 및 알림 HTTP 스키마를 대조했다.


### 최종 통합 검증 (develop `26f3788` + #129)

- Docker JDK 21: `bash gradlew test bootJar --no-daemon --max-workers=1 --no-watch-fs --console=plain`(검증 전용 Gradle/Test heap 512MiB·CPU 2 설정) — **323개 통과, 실패·오류·생략 0**, bootJar 성공. 새 분석 대화 경로와 #129 이용권 통합 9개를 포함한 전체 실행이다.
- report production 변경 3개 파일은 실제 HTTP 연동 당시 소스와 바이트 단위로 동일함을 대조했다. 서비스 경계·payment service 호출·내부 헤더 생성·parent 잠금 밖 HTTP 호출·공개 계약 보존을 최종 변경분에서 확인했다.
- `git diff --check` 통과, 미해결 충돌 없음. 원격 CI·운영 배포는 이 로컬 검증 결과에 포함하지 않는다.


### PR 준비: 최신 develop `2538d19` 반영

- #129 커밋 `2cf3bf9`을 유지하고 develop `2538d195c53c70a17af84aadea9a3ab1b348840a`를 일반 merge했다. 텍스트 충돌은 없었고 API 명세도 자동 병합됐다. squash·rebase·기존 이력 재작성은 수행하지 않았다.
- 전체 파일 대조에서 최신 develop 대비 차이는 원래 #129의 7개 파일뿐이다. API 명세는 최신 develop 원문에 #129의 기존 문구 변경을 적용한 결과와 정확히 일치하며, 나머지 구현·테스트 변경은 `2cf3bf9`과 동일하다. AI·learning·scoring의 새 파일과 이동은 develop 그대로 보존했다.
- 이번 병합 후 `python -O -m unittest discover -s scripts/tests -q` **76개 통과**, `git diff --check`·staged 공백 검사 통과, 미해결 충돌 없음. 이동된 ai 모듈의 이전 import·테스트 파일명 참조도 확인했다.
- core/report의 전체 소스·테스트·빌드 트리가 이전 검증본과 동일해 core 323개·bootJar, report 조회 31개, 실제 연결 5개 시나리오는 반복하지 않았다. 위 결과는 이전 실행 결과이며 이번 병합에서 새로 실행한 것으로 집계하지 않는다. 새 upstream 기능 전체의 학습·모델·삭제 E2E는 #129의 변경 검증 범위가 아니다.
- PR 대상과 저장소 기본 브랜치는 모두 develop이며, 전체 #129 완료 범위에 `Closes #129`를 사용한다. PR 생성은 사용자가 수행한다.
