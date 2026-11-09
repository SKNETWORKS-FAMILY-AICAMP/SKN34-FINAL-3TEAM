import { execFileSync } from 'node:child_process'

const container = process.env.E2E_POSTGRES_CONTAINER ?? 'sagomungchi-e2e-postgres-1'

function psql(database: string, sql: string) {
  return execFileSync('docker', ['exec', '-i', container, 'sh', '-c', `psql -v ON_ERROR_STOP=1 -qAt -U "$POSTGRES_USER" -d ${database}`],
    { input: sql, encoding: 'utf8' }).trim()
}

/**
 * 주간 리포트 cron(월요일 00:00 = 일요일 자정, 지난주 기간)을 기다릴 수 없어 이번 주 기간 생성 명령을 core outbox에 직접 넣는다.
 * ReportGenerateWriter·OutboxWriter와 같은 형식이라 OutboxRelay → report-worker → 완료 이벤트까지 실제 경로를 탄다.
 */
export function queueWeeklyReport(nickname: string) {
  const name = nickname.replaceAll("'", "''")
  return psql('core_db', `
WITH target AS (
  SELECT s.id AS student, gen_random_uuid() AS job, gen_random_uuid() AS event,
         date_trunc('week', now() AT TIME ZONE 'Asia/Seoul')::date AS mon
  FROM student s WHERE s.nickname = '${name}'
), job AS (
  INSERT INTO report_job (id, student_id, period_from, period_to, trigger, requested_by, status, report_id, failure_reason, retry_count, trace_id, created_at)
  SELECT job, student, mon, mon + 6, 'SCHEDULE', NULL, 'QUEUED', NULL, NULL, 0, NULL, now() FROM target
  RETURNING id
)
INSERT INTO outbox_event (id, event_type, routing_key, subject, payload, created_at, failure_count, manual_retry_count)
SELECT event, 'report.generate', 'report.generate', student::text, jsonb_build_object(
  'id', event::text, 'specversion', '1.0', 'type', 'report.generate', 'source', 'core-service', 'time', now(),
  'subject', student::text, 'dataschema', 'report.generate.v1',
  'data', jsonb_build_object('jobId', job::text, 'studentId', student::text, 'periodFrom', mon::text,
    'periodTo', (mon + 6)::text, 'trigger', 'SCHEDULE', 'narrativeEnabled', false)), now(), 0, 0
FROM target WHERE EXISTS (SELECT 1 FROM job)
RETURNING (payload->'data'->>'periodFrom') || ' ' || (payload->'data'->>'periodTo');`)
}
