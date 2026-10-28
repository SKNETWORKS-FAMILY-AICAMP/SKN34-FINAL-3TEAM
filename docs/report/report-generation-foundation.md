# 이슈 #50 리포트 생성 메시지·worker·Outbox

## 목적과 현재 범위

core가 발행한 `report.generate`를 report-worker가 받아 작업 상태와 결과 이벤트를 중복 없이 저장·발행하는 기반이다. 기존 이슈 브랜치 `feature/report-generation`에서 develop `47e5ffe`를 반영했다. #42가 제공한 공유 v1 스키마를 재사용하며 새 이벤트 필드·DB migration은 추가하지 않았다.

#50은 생성 기반 범위다. 계산·서술·렌더링은 #51~#53에서 조립한다. 테스트에서는 이슈가 허용한 빈 생성기로 성공 경로를 확인한다. 이 브랜치의 기본 CLI는 생성 큐를 실제 구독하지만 계산 파이프라인이 미연결이면 `GENERATOR_NOT_CONFIGURED`로 FAILED를 기록한다. 기록을 조회하지 않고 NO_RECORD/COMPLETED로 꾸미지 않는다. 후속 단계는 `run(generator=...)`에 실제 생성기를 연결한다.

## 구현과 완료 조건

| 항목 | 구현 및 검사 |
|---|---|
| worker 시작·종료 | 기본 `ReportV1Codec`, `EventConsumer.consume(report.report.generate)`, Outbox 주기 실행. 큐/브로커 준비 전 재확인, 종료 시 소비 취소→진행 작업 대기→채널 정리 |
| 메시지 계약 | 필수 id/specversion/time을 수신 시 자동 생성하지 않음. source/type/dataschema, UUID, subject=data.studentId, 월~일 기간, trigger, 엄격한 boolean·허용 필드 검사. 형식 오류는 즉시 DLQ |
| 사용자 컨텍스트 | subject 학생만 SYSTEM scope로 바인딩하고 종료·예외 후 복구, traceparent 전달 |
| 작업 멱등·재실행 | job_id UK, 최초 RUNNING+started, 종료 상태 재전달은 무작업, RUNNING은 같은 행으로 재실행 |
| 재생성 | 학생·주별 advisory transaction lock으로 revision 증가, 기존 판 보존 |
| 종료 트랜잭션 | COMPLETED 또는 FAILED와 해당 Outbox를 같은 짧은 트랜잭션에 저장. 오류 원문은 저장·로그에 노출하지 않음 |
| Outbox 발행 | 이벤트별 session advisory lock으로 선점, AUTOCOMMIT 연결만 유지한 채 발행. AMQP confirm 후 별도 짧은 DB 트랜잭션으로 published_at 기록 |
| 장애 복구 | confirm 후 기록 실패·timeout·취소 시 같은 ID/payload로 재발행 가능. 소비 측 멱등성과 결합하는 at-least-once 방식 |

`app/messaging/contracts.py`는 기존 봉투의 엄격한 수신 DTO다. 기존 `EventEnvelope`는 발행 시 ID/시각 기본값을 계속 제공한다. `app/generation/codec.py`가 #42의 payload를 내부 모델로 변환하며 공유 스키마를 복사하거나 변경하지 않는다. `requested_at`은 원래 봉투 time을 보존해 #55 삭제 장벽에서도 사용할 수 있도록 한다.

Outbox는 동시에 처리 중인 앞 100개 후보를 건너뛰며 다른 행을 선점할 수 있다. 각 발행은 최대 15초다. 브로커 대기 동안 DB 트랜잭션/행 잠금은 없지만 session lock용 DB 연결 하나는 사용한다. 연결 풀과 worker 동시 실행 수를 함께 관리한다. 기존 core OutboxRelay 구현은 이 변경의 대상이 아니다.

## 검증 — 2026-10-28

- Ruff check·format check(46개 파일), 공백 검사 통과. root 계약·스키마 unittest 53개도 통과(2.397초).
- report pytest 첫 실행 64 passed / 2 failed (33.50초). 새 실제 브로커 테스트의 정리 코드가 quorum 큐에서 지원하지 않는 if-unused 옵션을 사용한 실패였다. 정상/실패 lifecycle 송수신 검증 이후의 정리 단계 오류였다.
- 테스트 전용 큐 삭제 옵션을 고친 뒤 해당 2개 모두 통과(16.83초). 따라서 66개 항목을 확인했으며 이를 단일 전체 실행 66 passed로 표현하지 않는다.
- 실제 PostgreSQL에서 상태/Outbox 롤백·동시 job·revision·취소 복구, 발행 중 idle-in-transaction 0개, confirm 후 DB 실패·같은 ID 재전송·릴레이 선점 해제를 검증했다.
- 실제 RabbitMQ에서 공유 JSON Schema에 맞춘 명령을 두 번 발행하고 생성 1회, started와 completed/failed 각 1개, job/report 식별자·schema·publisher confirm을 검증했다. 기존 transport 테스트의 반송 후 재전송 검사도 통과했다.
- 합성 데이터만 사용했다. 실 학생 기록·AI Hub·운영 자격 증명은 사용하지 않았다. core 애플리케이션 전체 실행과 실제 #27/#64 연동은 이 검사에 포함하지 않는다.
- `docker build -t sagomungchi/report-service:issue50-20261028 .` 통과. 읽기 전용 root·네트워크 없는 운영 이미지에서 worker import와 pytest/jsonschema 미포함도 확인했다. jsonschema는 dev 그룹에만 추가했다.

## 후속 경계

#50의 메시지 기반 검증과 전체 주간 리포트 생성 완료는 구분한다. #51의 실제 learning 응답은 #27, #52의 실제 AI는 #64, #53의 닉네임 공급은 core 연결이 필요하다. core 정기/재생성의 상품 권한 공급자도 아직 503을 반환하므로 실제 스케줄 E2E 완료라고 보고하지 않는다. 실제 생성기는 후속 이슈에서 연결하고 기존 실패 작업의 재생성은 core의 새 job 규칙을 따른다.
