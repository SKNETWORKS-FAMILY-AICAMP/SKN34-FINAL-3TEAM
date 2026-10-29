# 주간 리포트 (#42·#50~#55)

통합 원본: issue-42-weekly-reports, report-generation-foundation, report-metrics, report-narrative, report-rendering, report-query, report-deletion, report-deletion-schema, report-learning-integration, report-required-inputs, report-service-handoff, report-epic-readiness

계약은 [API 명세](../design/api-spec.md) 3.4·4.1.1·4.2.1·4.4·5.5, 메시지는 [report-messages](../../contracts/events/report-messages.md).

## 1. core 주간 리포트 (#42)

- 매주 월요일 07:00 Asia/Seoul, 직전 월~일 `LocalDate`, 집계 경계 `[월 00:00 KST, 다음 월 00:00 KST)`. 기록 없는 자녀도 대상
- ShedLock(Spring/JDBC, 기존 `shedlock` 테이블, `usingDbTime`) + SCHEDULE 부분 UK로 재실행 중복 방지, 자녀·기간별 advisory transaction lock으로 정기·재생성 직렬화. 자녀별 실패는 격리하고 실행 끝에 전파
- 작업 저장과 `OutboxWriter.append`는 같은 트랜잭션, HTTP는 밖. 기존 core `OutboxRelay`는 `@Transactional` 안에서 브로커 발행·confirm을 기다리는 제약이 있음(공통 기반, 미변경)
- 재생성: 부모는 자녀·주 계열 REGENERATE 1회(재생성 결과로 다시 요청해도 우회 불가), SERVICE_OPS 관리자는 ADMIN_RETRY 무제한. revision은 report가 배정
- 상품 권한: narrativeEnabled를 제공할 상품·구독 계약이 없어(사용자 확인) `ReportEntitlementService`가 503. 연결 전에는 정기·재생성이 job·Outbox를 만들지 못하고 실패가 노출됨(테스트에서만 대역)
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
- 이용 권한은 core가 `X-Report-Narrative-Enabled`로 전달(없으면 false). 생성 당시 유료였다는 이유로 유료 파일을 서명하지 않음. core는 아직 이 헤더를 설정하지 않음

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
| 상품 권한 | core·상품 | `ReportEntitlementService` 실제 판정, 조회 시 `X-Report-Narrative-Enabled` 전달 |
| 서술 API | ai | `/internal/report-narratives`(api-spec 4.2.1) 구현 |
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

당시 미연결이던 기본 worker와 core 별명 공급은 후속 #56에서 연결했다. #64 실제 AI API·core 상품 권한 헤더 전달·운영 AWS·전체 서비스 E2E는 별도 연동 검증 범위다. 현재 core `ReportClient`는 상품 권한 헤더를 공급하지 않아 report가 무료 기본값을 적용한다. #56의 직접 메시지 발행·report 내부 API 검증을 사용자 대상 전체 흐름 검증으로 해석하지 않는다.

결과는 저장소 밖 `C:/Users/playdata2/Desktop/final/tmp/`의 `report-integration-20261029-final.xml`, `report-integration-pdf-20261029/`, `report-learning-20261029-final/`에 보관했다. 테스트 자원은 정리했다. 문서와 검증 스크립트 수정은 로컬 테스트 브랜치에만 남기며 원격 push·PR·병합은 수행하지 않았다.
