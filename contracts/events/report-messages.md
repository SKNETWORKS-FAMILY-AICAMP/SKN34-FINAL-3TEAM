# 리포트 v1 메시지 계약 (#42 / #50 / #152)

공통 `envelope.schema.json`을 재사용한다. `specversion=1.0`, `id`는 UUID 멱등키, `time`은 offset date-time, `subject`는 data.studentId UUID, `traceparent`는 선택이다. data 스키마만 각 v1 파일에 정의한다. `dataschema`는 파일 확장자를 뺀 `<type>.v1`이며 학생 이름·답변 원문을 넣지 않는다.

| type | source/생산자 | exchange → queue/소비자 | data |
|---|---|---|---|
| report.generate | core-service / #42 | cmd.direct → report.report.generate / #50 report-worker | jobId, studentId, periodFrom, periodTo, trigger, narrativeEnabled |
| report.started | report-service / #50 | events.topic → core.report.events / #42 | jobId, studentId, reportId |
| report.completed | report-service / #50 | events.topic → core.report.events / #42 | jobId, studentId, reportId |
| report.failed | report-service / #50 | events.topic → core.report.events / #42 | jobId, studentId, reportId, failureReason |

routing key=type. 큐의 정확한 이름과 retry/DLQ는 기존 definitions.json을 따른다. periodFrom/To는 대상 주의 KST 월/일 ISO date다. 자동 생성은 직전 주, 재처리는 원작업의 대상 주를 사용한다. report 조회 식별자는 reportId이며 jobId와 다르다. report는 jobId UK를 사용하고 재전달이면 같은 weekly_report를 재사용한다. 재생성은 새 jobId이며 report가 자녀/주 단위 잠금으로 revision을 증가시켜 새 행에 저장한다. core가 revision을 추정해 전달하지 않는다.

report.started는 weekly_report RUNNING 저장과 같은 트랜잭션의 Outbox에 저장한다. 완료/실패도 상태와 Outbox를 원자 저장한다. failureReason은 원문 없는 1~100자 대문자 오류 코드다. 모든 lifecycle 이벤트의 reportId는 시작 시 배정된 같은 UUID이며 core는 job/student/report 일치 여부를 대조한다. started 지연/유실 시 completed/failed가 QUEUED에서 바로 종료할 수 있다. 먼저 반영된 종료 상태는 이후 이벤트로 바꾸지 않는다. 같은 id의 재전달과 다른 id의 중복 전이 모두 1회만 반영한다.

narrativeEnabled는 core의 현재 상품 권한 조회로 결정한다. 무료=false / 프리미엄=true이며 권한 조회 실패 시 명령을 발행하지 않고 명시적으로 실패한다. report는 NO_RECORD에서 true여도 AI를 호출하지 않는다. #47 관리자 재처리 접수에도 같은 계산을 연결해야 한다.

이 문서는 #42 v1 계약이며, report-service의 소비·발행 codec·생성 파이프라인과 ai 서술 API가 develop에 구현되어 있다. 각 검증의 실제 서비스/대역 범위는 report 검증 보고서를 따른다.

## #152 관리자 실패 작업 재처리

- core는 새 jobId로 `trigger=ADMIN_RETRY`를 발행한다. 원래 실패 jobId와의 연결 및 관리자 요청 멱등·권한·현재 narrativeEnabled 계산은 core #47 소유다. 원작업 연결 필드·revision을 메시지에 추가하지 않는다.
- 같은 관리자 요청의 중복 전송은 **같은 새 jobId와 같은 업무 본문**을 유지한다. 봉투 id가 같거나 달라도 report의 jobId 업무 멱등은 동일하다. 실패한 기존 jobId 메시지만 다시 보내면 재실행하지 않는다(#50).
- 새 jobId마다 새 reportId와 다음 revision을 배정하고 이전 판을 보존한다. 시작·종료 결과는 항상 그 새 jobId와 reportId에 연결한다. 지연된 원작업 이벤트는 core가 원작업에만 적용하며, 종료 상태는 되돌리지 않는다.
- 요청·결과 [JSON 예시](../examples/report-admin-retry/)는 자동 계약 검사 대상이다. 같은 성공 재처리의 started/completed와, 별도 재처리 실패의 started/failed를 구분했다. 완료와 실패는 한 실행에서 동시에 발행하지 않는다.
