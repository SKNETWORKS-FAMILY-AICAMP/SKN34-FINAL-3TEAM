# #152 / #47 관리자 재처리 이벤트 예시

모든 ID·문장은 합성 예시다. JSON 전체가 실제 v1 봉투/본문 스키마로 검증된다.

| 파일 | 생산자 → 소비자 | 설명 |
|---|---|---|
| 01-original-failed.json | report → core | 원래 실패 작업 A(2222…) |
| 02-retry-request.json | core → report | A를 다시 실행할 새 작업 B(3333…), ADMIN_RETRY |
| 03-retry-started.json | report → core | B 시작, reportId 6666… 배정 |
| 04-retry-completed.json | report → core | B 성공, 시작과 같은 reportId |
| 05-another-retry-request.json | core → report | 별도로 명시한 새 재처리 C(4444…) |
| 06-another-retry-started.json | report → core | C 시작, reportId 7777… 배정 |
| 07-another-retry-failed.json | report → core | C 재실패, 원문 없는 failureReason |

core가 관리할 연결은 `A → B`, `A → C`다. report 메시지에 originalJobId를 추가하지 않는다. 원작업 연결·저장 방식은 core #47에서 구현한다.

- 요청: exchange `cmd.direct`, routing key `report.generate`, queue `report.report.generate`.
- 결과: exchange `events.topic`, routing key `report.started|completed|failed`, queue `core.report.events`.
- 관리자 요청 재전송은 02와 같은 jobId·업무 본문을 사용한다. 전송 재시도에는 원래 봉투 id도 유지한다. 봉투 id만 새로 생겨도 같은 jobId이면 실행 횟수는 늘어나지 않는다.
- 새로 재처리할 때는 05처럼 새 jobId를 만든다. 각 실행은 started와 completed 또는 failed 중 하나만 갖는다.
- core가 현재 권한·학생 상태를 확인해 narrativeEnabled를 설정한다. 무료면 false를 사용한다. 예시 true는 합성 프리미엄 요청이며 권한 증거를 대신하지 않는다.
- 늦게 도착한 01을 B의 실패로 해석하면 안 된다. core는 각 이벤트의 data.jobId로만 연결하고, 봉투 id 중복·종료 상태 이후 이벤트를 기존 방어 정책으로 무시한다.
- reportId는 report가 배정한다. jobId·reportId는 서로 다르며 revision은 core가 추정하거나 요청에 넣지 않는다.
