# 이슈 #50 리포트 생성 기반 — #42 계약 연결 전

> 현재 상태(2026-10-28): 사용자 지시에 따라 기존 이슈별 브랜치 `feature/report-generation`에서 진행한다. develop `78bbdc1`을 충돌 없이 병합하여 #42 공유 스키마를 확보했다. 아래 스키마 미확보 설명은 이전 검증 이력이며, 지금 남은 작업은 production codec·worker 연결과 공유 규격 기반 검증이다. #51~#55 변경은 이 브랜치에 포함하지 않았다.

## 범위와 현재 상태

[#50](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/50)의 DB 처리·생성 상태 전이·Outbox 발행 기반을 구현한다. develop `e3bb6ab`에서 시작했으며 최종 정리 기준은 #36 인증 구현이 병합된 `ecd6ecf`다. 두 기준 사이에 report 코드·마이그레이션·이벤트 계약 변경은 없다. 작업 브랜치는 `feature/report-generation`이다.

공통 메시지 스키마는 [#42](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/42)에서 작성하는 것을 재사용한다. 기준 develop에는 `report.*` 스키마가 없으므로 이번 변경에는 별도 스키마나 임시 운영용 메시지 변환기를 추가하지 않았다. **이 변경만으로 #50 완료를 선언하거나 이슈를 종료하지 않는다.**

## 구현 내용

| 위치 (`backend/report-service/`) | 역할 |
|---|---|
| `app/generation/models.py` | 내부 명령·리포트 상태·생성 결과. 외부 JSON 필드 계약과 구분 |
| `app/generation/ports.py` | `ReportGenerator`와 `ReportEventCodec` 연결 지점 |
| `app/generation/repository.py` | 기존 `weekly_report` 조회·생성·조건부 종료, 재생성 revision 할당 |
| `app/generation/service.py` | 시작/종료 상태와 Outbox를 같은 트랜잭션에 저장, 비동기 생성 실행 |
| `app/generation/locking.py` | 작업별 PostgreSQL 세션 advisory lock으로 동시 실행 방지 |
| `app/generation/consumer.py` | 기존 `EventConsumer`에 전달할 핸들러. 학생 subject 대조, SYSTEM 컨텍스트 지정·복구 |
| `app/outbox/repository.py`·`relay.py` | 미발행 행 `FOR UPDATE SKIP LOCKED`, confirm 이후 발행 시각 기록 |
| `app/messaging/publisher.py` | 기존 AMQP 연결로 `events.topic` 발행. persistent·mandatory·publisher confirm 적용 |
| `app/database.py`·`security.py` | 기존 트랜잭션/컨텍스트 기반에 DB 스레드 실행·컨텍스트 복구 함수 추가 |

새 마이그레이션·ERD 변경·의존성 추가는 없다. SQLAlchemy Table은 기존 스키마를 조회하는 정의이며 `create_all`·reflection·앱 기동 마이그레이션을 실행하지 않는다.

### 처리 흐름

1. 계약 변환기가 메시지를 내부 `GenerateReport`로 변환한다. 핸들러는 봉투의 학생 subject와 명령의 학생이 같은지 확인한 뒤 `SYSTEM` 컨텍스트를 지정한다.
2. `job_id`별 세션 advisory lock을 획득한다. 다른 소비자가 같은 작업을 처리 중이면 예외를 전달해 기존 `EventConsumer`의 지연 재시도를 사용한다.
3. 짧은 트랜잭션에서 최초 작업은 `RUNNING`과 `report.started`를 함께 저장한다. 종료된 작업은 즉시 반환한다. 기존 `RUNNING`은 같은 행을 재사용하며 started 이벤트를 다시 저장하지 않는다.
4. 생성기를 호출한다. 이 호출 동안 DB 트랜잭션은 열어 두지 않는다. 작업 잠금용 연결 하나는 유지하므로 worker 동시 실행 수와 DB 연결 풀 크기를 함께 관리해야 한다.
5. 성공 시 `COMPLETED`와 `report.completed`, 생성기 예외 시 `FAILED`와 `report.failed`를 각각 같은 트랜잭션에 저장한다. 예외 원문에는 민감한 값이 포함될 수 있어 `failure_reason`에는 `GENERATION_FAILED`만 기록한다.
6. DB 저장/메시지 변환 실패는 롤백 후 호출자에게 전달한다. 종료 저장 실패 시 `RUNNING`이 남아 재전달로 복구한다. 취소도 FAILED로 바꾸지 않으며 DB 스레드 정리 후 잠금을 반환한다.
7. 핸들러 반환 뒤 ACK·실패 재시도는 기존 `EventConsumer`가 담당한다. 핸들러는 종료·예외·취소 시 이전 사용자 컨텍스트를 복구한다.

동일 학생·시작일의 revision은 트랜잭션 advisory lock 아래 `MAX(revision) + 1`로 할당한다. 서로 다른 재생성 job이 동시에 들어와도 기존 판을 덮지 않는다. `job_id`가 다른 학생/기간으로 재사용되면 기존 행을 수정하지 않고 거부한다.

### Outbox 발행

- 상태 변경과 같은 Session에 전체 EventEnvelope를 JSONB로 저장한다. Repository는 commit하지 않는다.
- 릴레이의 DB Session·트랜잭션은 한 DB 스레드에서 사용하고, AMQP 발행은 해당 연결의 이벤트 루프에서 실행한다. 행 잠금은 제한 시간 내 confirm을 기다리는 동안만 유지한다.
- 연결 단절·반송(unroutable)·NACK·시간 초과·DB 반영 실패 시 `published_at`은 남기지 않는다. 다음 호출에서 다시 시도할 수 있다.
- confirm 직후 DB 반영 전에 중단되면 같은 이벤트가 재발행될 수 있다. 저장된 이벤트 ID·본문은 그대로 유지하며 core의 멱등 소비와 결합하는 at-least-once 방식이다.
- exchange·큐 선언은 운영의 `definitions.json`이 담당한다. 서비스 발행기는 기존 exchange를 확인해 사용한다.

## #42 연결 후 남은 작업

| #50 항목 | 현재 검증 범위 | 남은 연결 |
|---|---|---|
| `EventConsumer.consume` worker 시작 | 핸들러 구성, 내부 생성 서비스 | #42 codec과 생성기를 조립해 `worker.py`에 소비 시작·종료 처리 연결 |
| SYSTEM 사용자 컨텍스트 | subject 대조·범위 지정·trace 전달·복구 | 실제 요청 JSON의 학생 필드와 계약 검증 |
| 시작·종료·재전달·재생성 | 실제 PostgreSQL에서 검증 | 실제 메시지로 같은 흐름 재검증 |
| Outbox 저장·발행 | 롤백·중복·confirm·반송·재발행 검증 | worker의 릴레이 실행 주기·종료 처리 연결 |
| 공통 이벤트 스키마 | #42 담당, 이번 변경에서 생성하지 않음 | `report.generate/started/completed/failed` 스키마를 재사용 |
| 스키마 계약 테스트 | 미완료 | 실제 #42 스키마와 입력/출력 페이로드 대조 |

`tests/report_helpers.py`의 FakeCodec·EmptyGenerator는 합성 테스트 전용이다. `testOnlyReportId`는 팀 메시지 필드가 아니다. 계산·서술·파일 생성은 #51~#53에서 채운다. 운영 worker에는 임시 생성기를 연결하지 않았으며, 빈 결과로 실제 작업을 완료 처리하지 않는다.

#42 규격을 받은 뒤 필요한 필드·버전·실패 사유 형식을 대조하고 변환기를 구현한다. 공개 API 계약 변경이 필요하면 API 명세와 이 보고서를 함께 갱신한다. #50 종료는 worker 연결과 계약 테스트까지 통과한 뒤 판단한다.

## 검증

2026-10-27 로컬 서비스 `.venv`와 일회용 PostgreSQL 17.11·RabbitMQ 4.3.7 컨테이너를 사용한다. 실제 학생 답안·AI Hub 자료 없이 합성 데이터만 사용한다.

- `uv run --frozen ruff check .`
- `uv run --frozen ruff format --check .`
- `uv run --frozen pytest`
- `docker build -t sagomungchi/report-service:issue50-local .`

위 검증은 모두 통과했다. pytest **40개 통과·실패/생략 0개(26.22초)**이며, 기존 Starlette TestClient 사용 중단 안내 경고 1개가 남았다. 실제 PostgreSQL 마이그레이션 적용 후 테스트했고, 실제 RabbitMQ의 정상 confirm과 라우팅 실패 후 재발행도 포함한다. 서비스 이미지 빌드도 성공했다.

주요 검증: 동일 job 중복·동시 전달, 초기/완료 Outbox 저장 실패 시 롤백, 기존 RUNNING 재개, 다른 학생으로 job 재사용 거부, 동시 revision 할당, 취소 후 복구, SYSTEM 범위·trace 전파, 릴레이 동시 실행, confirm 후 DB 실패 시 동일 ID 재발행, 실제 브로커의 라우팅 실패 후 재발행.

실제 core와의 메시지 계약·worker 전체 연동은 위 테스트 결과에 포함하지 않는다.
