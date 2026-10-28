# 리포트 v1 메시지 계약 (#42 / #50)

공통 `envelope.schema.json`을 재사용한다. `specversion=1.0`, `id`는 UUID 멱등키, `time`은 offset date-time, `subject`는 data.studentId UUID, `traceparent`는 선택이다. data 스키마만 각 v1 파일에 정의한다. `dataschema`는 파일 확장자를 뺀 `<type>.v1`이며 학생 이름·답변 원문을 넣지 않는다.

| type | source/생산자 | exchange → queue/소비자 | data |
|---|---|---|---|
| report.generate | core-service / #42 | cmd.direct → report.report.generate / #50 report-worker | jobId, studentId, periodFrom, periodTo, trigger, narrativeEnabled |
| report.started | report-service / #50 | events.topic → core.report.events / #42 | jobId, studentId, reportId |
| report.completed | report-service / #50 | events.topic → core.report.events / #42 | jobId, studentId, reportId |
| report.failed | report-service / #50 | events.topic → core.report.events / #42 | jobId, studentId, reportId, failureReason |

routing key=type. 큐의 정확한 이름과 retry/DLQ는 기존 definitions.json을 따른다. periodFrom/To는 직전 KST 월/일의 ISO date다. report 조회 식별자는 reportId이며 jobId와 다르다. report는 jobId UK를 사용하고 재전달이면 같은 weekly_report를 재사용한다. 재생성은 새 jobId이며 report가 자녀/주 단위 잠금으로 revision을 증가시켜 새 행에 저장한다. core가 revision을 추정해 전달하지 않는다.

report.started는 weekly_report RUNNING 저장과 같은 트랜잭션의 Outbox에 저장한다. 완료/실패도 상태와 Outbox를 원자 저장한다. failureReason은 원문 없는 1~100자 대문자 오류 코드다. 모든 lifecycle 이벤트의 reportId는 시작 시 배정된 같은 UUID이며 core는 job/student/report 일치 여부를 대조한다. started 지연/유실 시 completed/failed가 QUEUED에서 바로 종료할 수 있다. 먼저 반영된 종료 상태는 이후 이벤트로 바꾸지 않는다. 같은 id의 재전달과 다른 id의 중복 전이 모두 1회만 반영한다.

narrativeEnabled는 승인된 상품 계약에서만 결정한다. 미연결 상태에서 core는 명령을 발행하지 않고 명시적으로 실패한다. 무료=false / 프리미엄=true의 실제 연결은 상품 담당 서비스 계약 확정 후 수행한다. report는 NO_RECORD에서 true여도 AI를 호출하지 않는다.

이 문서는 #42에서 먼저 제안·구현한 v1 계약이다. #50/#54 실제 공급자와 통합 시 필드·큐·응답을 대조해야 하며 합의나 실제 report-service 연동 완료를 뜻하지 않는다.
