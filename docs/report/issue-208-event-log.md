# #208 RabbitMQ 발행·소비 기록 PostgreSQL 보완

## 배경
- 10/29 멘토링에서 AI 처리와 플랫폼 간 요청·응답 이력 관리 여부를 검토하라는 의견이 나옴. 11/1 RabbitMQ 작업·이벤트 기록을 기존 PostgreSQL에 저장하기로 결정
- 운영 중 "이 메시지가 발행됐는지, 브로커를 거쳤는지, 누가 처리했는지"를 PostgreSQL에서 조회할 수 있어야 함

## 참고 레포와 비교
| 항목 | 참고 레포 (SKN34-4th-1Team) | 현재 저장소 |
|---|---|---|
| 발행 기록 위치 | 작업 테이블 행 자체가 outbox (`next_publish_at`·`last_published_at`·`queue_expires_at`) | 서비스별 공통 `outbox_event` 테이블 (core·report) |
| 재발행 | QUEUED 행을 `next_publish_at`마다 재발행, 만료 시 실패 처리 | core: 미발행 행을 매 주기 재시도. report: 1·5·15분 재시도 후 격리(#131). 작업 유실은 #132 job guard로 복구 |
| 소비 기록 | 작업 상태 전이 | `processed_event` 또는 상태 전이 조건 |
| 상태 없는 서비스 발행 | 해당 없음 | ai·scoring best-effort 발행, 기록 없음 |

참고 레포의 작업별 컬럼 방식은 작업 단위 재발행·만료에 맞춤. 현재 저장소는 이미 `outbox_event` + 작업 상태 + #131·#132 복구가 같은 역할을 하므로 작업 테이블에 컬럼을 추가하지 않음. 빠진 부분은 "통합 조회"와 "보존 정책"임.

## 메시지별 기록 현황
| 메시지 | 생산 → 소비 | 발행 기록 | 브로커 전달 (#208) | 소비 기록 |
|---|---|---|---|---|
| report.generate | core → report | core outbox_event | event_log | core report_job 상태, report weekly_report.job_id |
| report.started/completed/failed | report → core | report outbox_event (실패·격리 포함) | event_log | core processed_event |
| student.deleted | core → learning·report | core outbox_event | event_log | learning·report processed_event, core 완료 보고 행 |
| model.version.activated | core → ai·scoring 모든 Pod | core outbox_event | event_log | 기록 없음 (예외, 아래 참조) |
| llm.usage.recorded | ai·scoring → core | 없음 | event_log | core llm_usage(event_id) |

- 현재 메시지 5종은 모두 core가 생산하거나 소비함 (`definitions.json` 바인딩 기준)

## 결정
1. **core 감사 큐 + `event_log`**: 큐 `core.event.audit`(재시도 1·5·15분, DLQ 포함)을 업무 routing key마다 바인딩. `EventAuditConsumer`가 봉투의 id·type·source·subject·time과 수신 시각만 저장하고 payload·원문은 저장하지 않음. 같은 id는 `ON CONFLICT DO NOTHING`
2. **`#` 와일드카드를 쓰지 않음**: report 발행자는 `mandatory=True`로 unroutable 메시지를 실패로 보고 #131 재시도·격리를 적용함. `#`에 바인딩하면 잘못된 routing key도 감사 큐로 전달되어 성공으로 처리되므로 키별로 바인딩함. 업무 바인딩 키마다 감사 바인딩이 있는지는 `RabbitDefinitionsTest`가 검사함 (`model.version.activated`는 Pod별 임시 큐라 별도로 포함)
3. **ai·scoring DB 신설 안 함**: 상태 없는 서비스 원칙 유지. 브로커에 도달한 발행은 event_log에 남음. 브로커 미연결·발행 실패 건은 event_log에 없고 기존 서비스 로그(`이벤트 발행 실패`)로만 확인함
4. **model.version.activated 소비는 예외**: 모든 Pod가 각자 임시 큐로 받아 메모리 버전을 교체하며 DB가 없음. 기동·재연결 때 core snapshot을 다시 조회해 누락을 복구하고 적용 전에는 readiness가 false이므로 Pod별 적용 기록은 남기지 않음
5. **보존 90일**: 발행 완료 `outbox_event`, `processed_event`, `event_log`를 90일 뒤 1시간 주기로 삭제. 미발행·격리 outbox 행은 기간과 무관하게 유지. `llm_usage`·`job_execution`은 정리 대상이 아님
   - core: `EventRetentionCleanup` (`app.messaging.event-retention-days`, 기본 90)
   - learning: `ProcessedEventCleanupScheduler` → `ProcessedEventCleanupService` (`app.messaging.event-retention-days`, 기본 90, #278에서 scheduler·service 분리). 삭제 표식 `deleted_student`는 유지
   - report: worker cleanup 루프가 `deletion/service.py` `prune_event_records` 호출 (`EVENT_RETENTION_DAYS`, 기본 90, #278에서 service로 이동). `report_deletion_guard`는 유지
   - 조건부 DELETE라 레플리카가 동시에 실행해도 결과가 같아 ShedLock을 쓰지 않음 (기존 `IdempotencyCleanup`과 같은 방식)
6. **학생 식별자**: event_log.subject에 학생 UUID가 들어갈 수 있으나 payload·원문은 없음. 학생 삭제 시 즉시 지우지 않고 90일 보존 후 삭제함

## 남은 누락 구간 (후속 이슈 후보)
- core outbox 릴레이는 발행 실패 시 실패 횟수·오류 코드를 저장하지 않고 매 주기 재시도만 함. report(#131)의 `failure_count`·`last_error_code`·격리와 같은 기록이 없음
- ai·scoring 발행 실패 건은 PostgreSQL에 남지 않음 (위 결정 3)

## API·설정 변경
- 새 HTTP API·이벤트 스키마 없음
- 관리자 큐 현황(`GET /api/v1/admin/queues` 응답 items)이 고정 25개 → 30개 큐로 늘어남 (`core.event.audit`·재시도 3·DLQ). `docs/design/api-spec.md` 반영
- RabbitMQ `definitions.json`에 큐 5개·바인딩 8개 추가. 기존 환경은 definitions 재적용 필요

## 마이그레이션
- core `V20__event_log_and_retention.sql`: event_log 테이블, 정리용 인덱스
- learning `V8__processed_event_retention_index.sql`
- report Alembic `20261102_05` (down_revision `20261030_04`): 정리용 인덱스. 다운그레이드는 인덱스만 제거

## 운영 조회 예시 (core DB)
```sql
-- 특정 이벤트의 발행(core)·브로커 전달·core 소비
SELECT l.event_id, l.event_type, l.source, l.event_time, l.received_at,
       o.published_at, p.processed_at, u.occurred_at AS usage_occurred_at
FROM event_log l
LEFT JOIN outbox_event o ON o.id = l.event_id
LEFT JOIN processed_event p ON p.event_id = l.event_id
LEFT JOIN llm_usage u ON u.event_id = l.event_id
WHERE l.event_id = :event_id;

-- core가 발행했으나 감사 큐에 도달하지 않은 이벤트
SELECT o.id, o.event_type, o.published_at
FROM outbox_event o LEFT JOIN event_log l ON l.event_id = o.id
WHERE o.published_at IS NOT NULL AND l.event_id IS NULL;

-- 유형별 최근 24시간 전달 건수
SELECT event_type, count(*) FROM event_log
WHERE received_at > now() - interval '1 day' GROUP BY event_type;
```
report·learning이 처리했는지는 각 DB의 `processed_event`(student.deleted)와 core 완료 보고·report_job 상태로 확인함.
