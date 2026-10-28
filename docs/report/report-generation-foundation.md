# 이슈 #50 리포트 생성 메시지·worker·Outbox

## 목적과 현재 범위

core가 발행한 `report.generate`를 report-worker가 받아 작업 상태와 결과 이벤트를 중복 없이 저장·발행하는 기반이다. 기존 이슈 브랜치 `feature/report-generation`에 develop `1208ead`를 충돌 없이 병합하고 [기존 PR #101](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/pull/101)을 갱신한다. #42가 제공한 공유 v1 스키마를 재사용하며 새 이벤트 필드·DB migration은 추가하지 않았다.

#50은 생성 기반 범위다. 계산·서술·렌더링은 #51~#53에서 조립한다. 테스트에서는 이슈가 허용한 빈 생성기로 성공 경로를 확인한다. 이 브랜치의 기본 CLI는 생성 큐를 실제 구독하지만 계산 파이프라인이 미연결이면 `GENERATOR_NOT_CONFIGURED`로 FAILED를 기록한다. 기록을 조회하지 않고 NO_RECORD/COMPLETED로 꾸미지 않는다. 후속 단계는 `run(generator=...)`에 실제 생성기를 연결한다.

## 해야 할 일·완료 조건 대조

아래 11개는 이슈 본문의 순서다. 테스트 경로는 `backend/report-service/tests/` 기준이며, 모두 아래 전체 테스트 실행에서 통과했다.

| 구분 | 요구사항 | 구현·검증 근거 | 판정 |
|---|---|---|---|
| 할 일 1 | worker에서 생성 큐 소비 시작 | `app/worker.py`가 기존 `EventConsumer.consume`으로 `report.report.generate`를 구독. `test_worker_broker.py`에서 실제 RabbitMQ 명령 소비·릴레이·종료 확인 | 충족 |
| 할 일 2 | subject 학생의 SYSTEM 컨텍스트 | `GenerationConsumer`가 학생 scope·traceparent를 바인딩하고 복구. `test_system_context_is_bound_and_restored` 및 실제 브로커 테스트에서 확인 | 충족 |
| 할 일 3 | 신규·종료·RUNNING job 분기 | 최초 RUNNING+started, 종료 상태는 추가 생성 없이 ACK, RUNNING은 같은 report ID 재사용. `test_repeated_job_creates_one_report_and_one_of_each_event`, `test_shared_codec_pipeline_is_idempotent_and_unconfigured_is_not_success`, `test_terminal_rollback_leaves_running_and_redelivery_reuses_it` | 충족 |
| 할 일 4 | revision 증가·기존 판 보존 | 기존 UK와 학생·주별 advisory transaction lock 사용. `test_concurrent_regenerations_allocate_distinct_revisions`에서 서로 다른 job의 revision 1·2 및 두 행 보존 확인 | 충족 |
| 할 일 5 | 성공·실패 상태와 결과 이벤트 | `GenerationService._finish`의 같은 트랜잭션에서 상태·Outbox 저장. `test_generation.py`와 `test_worker_broker.py`에서 COMPLETED/FAILED, reportId, 안전한 failure_reason 확인 | 충족 |
| 할 일 6 | confirm 후 published_at | `OutboxRelay`·`EventPublisher` 사용. `test_confirm_precedes_published_timestamp`, `test_real_broker_confirm_and_unroutable_retry`, `test_mark_failure_replays_same_event_identity`에서 confirm·반송·DB 기록 실패 후 재전송 확인 | 충족 |
| 할 일 7 | 이벤트 계약 스키마 | D7 댓글 지시에 따라 #42가 추가한 `report.generate/started/completed/failed.v1.schema.json`을 재사용. `test_report_codec.py`·`test_worker_broker.py`가 실제 파일로 payload·봉투 검증 | 충족 |
| 완료 1 | 같은 메시지 두 번, 리포트 한 행·이벤트 중복 없음 | 실제 DB/브로커에서 생성 1회·행 1개, started 1개와 completed 또는 failed 1개. 종료 상태 재전달의 ACK도 검사 | 충족 |
| 완료 2 | 상태와 Outbox 동시 롤백 | `test_start_and_outbox_roll_back_together` 및 `test_terminal_rollback_leaves_running_and_redelivery_reuses_it`의 성공·실패 양쪽 경로에서 DB 쓰기 후 오류를 주입하고 동시 롤백·재실행 확인 | 충족 |
| 완료 3 | 스키마 계약 테스트 | 공유 JSON Schema, 필수 필드 6개 누락·잘못된 생산자/학생/기간·boolean 거부, `narrativeEnabled` true/false 전달 검증 | 충족 |
| 완료 4 | Ruff check·format·pytest | `uv run --locked ruff check .`, `uv run --locked ruff format --check .`, `uv run --locked pytest -q` 전체 통과 | 충족 |

“이벤트 1회”는 수명주기 이벤트 종류별 1회다. 정상 처리에는 started와 completed가 각각 한 번 필요하다. confirm 이후 DB 기록 전 장애에서는 같은 ID로 재발행할 수 있는 at-least-once 전송이며, 네트워크 전체의 exactly-once를 보장한다는 뜻은 아니다.

## 댓글 D7 및 확인 필요 항목

[#50 댓글](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/50#issuecomment-6459420848)의 중복 스키마 방지 지시를 반영했다. 작성 주체는 선행 구현한 #42이며 #50은 공유 v1 파일을 그대로 사용한다. `report.generate` 데이터 필드는 확정된 `jobId`, `studentId`, `periodFrom`, `periodTo`, `trigger`, `narrativeEnabled` 6개만 사용한다. 추가 데이터 필드는 필요하지 않으며 요청 시각은 기존 봉투의 `time`에서 얻는다.

`narrativeEnabled`는 필수 boolean이다. 누락·문자열·숫자는 DLQ로 보내고 true/false 모두 생성기에 그대로 전달하는 것을 실제 브로커에서 확인했다. 무료 플랜의 AI 서술 생략 실행은 이 플래그를 받는 #52의 범위다.

`app/messaging/contracts.py`는 기존 봉투의 엄격한 수신 DTO다. 기존 `EventEnvelope`는 발행 시 ID/시각 기본값을 계속 제공한다. `app/generation/codec.py`가 #42의 payload를 내부 모델로 변환하며 공유 스키마를 복사하거나 변경하지 않는다. `requested_at`은 원래 봉투 time을 보존해 #55 삭제 장벽에서도 사용할 수 있도록 한다.

Outbox는 동시에 처리 중인 앞 100개 후보를 건너뛰며 다른 행을 선점할 수 있다. 각 발행은 최대 15초다. 브로커 대기 동안 DB 트랜잭션/행 잠금은 없지만 session lock용 DB 연결 하나는 사용한다. 연결 풀과 worker 동시 실행 수를 함께 관리한다. 기존 core OutboxRelay 구현은 이 변경의 대상이 아니다.

## 검증 — 2026-10-28

- 최신 develop 병합 후 Ruff check·format check(46개 파일), 공백 검사 통과. root 계약·스키마 unittest 54개 통과(3.605초).
- report pytest 전체 단일 실행 **75 passed**(40.78초). 실패 전이의 Outbox 롤백, 필수 데이터 필드 누락, 무료/유료 플래그를 포함해 보강한 검사를 모두 실행했다. 이 기록은 이전 64+2 분리 재실행 기록을 대체한다.
- 실제 PostgreSQL에서 상태/Outbox 롤백·동시 job·revision·취소 복구, 발행 중 idle-in-transaction 0개, confirm 후 DB 실패·같은 ID 재전송·릴레이 선점 해제를 검증했다.
- 실제 RabbitMQ에서 공유 JSON Schema에 맞춘 명령을 두 번 발행하고 생성 1회, started와 completed/failed 각 1개, job/report 식별자·schema·publisher confirm을 검증했다. 기존 transport 테스트의 반송 후 재전송 검사도 통과했다.
- 합성 데이터만 사용했다. 실 학생 기록·AI Hub·운영 자격 증명은 사용하지 않았다. core 애플리케이션 전체 실행과 실제 #27/#64 연동은 이 검사에 포함하지 않는다.
- `docker build -t sagomungchi/report-service:issue50-refresh-20261028 .` 통과. 읽기 전용 root·네트워크 없는 운영 이미지에서 worker import와 pytest/jsonschema 미포함도 확인했다. jsonschema는 dev 그룹에만 추가했다.

## 후속 경계

#50에서 요구한 빈 생성기 기반의 메시지·상태 전이·Outbox 완료 조건은 충족했다. #51~#53의 계산·AI 서술·파일 렌더링과 #55 삭제 처리는 이 PR의 범위에 포함하지 않는다. #27은 develop에 병합됐지만 실제 learning/AI 연동과 생성기 조립 검증은 해당 후속 브랜치에서 관리한다. 현재 develop의 core `ReportEntitlementService`는 상품 권한 미연결 시 503을 반환하므로 #50 검증을 실제 스케줄 전체 E2E 완료로 보고하지 않는다. 기존 실패 작업의 재생성은 core의 새 job 규칙을 따른다.
