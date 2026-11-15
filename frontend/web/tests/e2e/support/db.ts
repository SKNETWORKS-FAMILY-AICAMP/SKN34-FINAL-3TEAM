import { execFileSync } from 'node:child_process'

const container = process.env.E2E_POSTGRES_CONTAINER ?? 'sagomungchi-e2e-postgres-1'

function psql(database: string, sql: string) {
  return execFileSync('docker', ['exec', '-i', container, 'sh', '-c', `psql -v ON_ERROR_STOP=1 -qAt -U "$POSTGRES_USER" -d ${database}`],
    { input: sql, encoding: 'utf8' }).trim()
}

/**
 * 리포트 cron(일일 00:00 전날, 주간 월요일 00:00 지난주)을 기다릴 수 없어 이번 기간 생성 명령을 core outbox에 직접 넣는다.
 * 일일은 오늘 하루, 주간은 이번 주 월~일. ReportGenerateWriter·OutboxWriter와 같은 형식(주간은 periodType 생략)이라
 * OutboxRelay → report-worker → 완료 이벤트까지 실제 경로를 탄다.
 * narrative는 ReportJobService가 계산하는 값(주간 && 이용권 reportNarrative)을 호출하는 쪽이 맞춰 넘긴다.
 */
export function queueReport(nickname: string, { periodType = 'WEEKLY', narrative = false }: { periodType?: 'DAILY' | 'WEEKLY'; narrative?: boolean } = {}) {
  const name = nickname.replaceAll("'", "''")
  const daily = periodType === 'DAILY'
  return psql('core_db', `
WITH target AS (
  SELECT s.id AS student, gen_random_uuid() AS job, gen_random_uuid() AS event,
         ${daily ? `(now() AT TIME ZONE 'Asia/Seoul')::date` : `date_trunc('week', now() AT TIME ZONE 'Asia/Seoul')::date`} AS from_date
  FROM student s WHERE s.nickname = '${name}'
), period AS (
  SELECT *, from_date + ${daily ? 0 : 6} AS to_date FROM target
), job AS (
  INSERT INTO report_job (id, student_id, period_type, period_from, period_to, trigger, requested_by, status, report_id, failure_reason, retry_count, trace_id, created_at)
  SELECT job, student, '${periodType}', from_date, to_date, 'SCHEDULE', NULL, 'QUEUED', NULL, NULL, 0, NULL, now() FROM period
  RETURNING id
)
INSERT INTO outbox_event (id, event_type, routing_key, subject, payload, created_at, failure_count, manual_retry_count)
SELECT event, 'report.generate', 'report.generate', student::text, jsonb_build_object(
  'id', event::text, 'specversion', '1.0', 'type', 'report.generate', 'source', 'core-service', 'time', now(),
  'subject', student::text, 'dataschema', 'report.generate.v1',
  'data', jsonb_build_object('jobId', job::text, 'studentId', student::text, 'periodFrom', from_date::text,
    'periodTo', to_date::text, 'trigger', 'SCHEDULE', 'narrativeEnabled', ${narrative})${daily ? ` || jsonb_build_object('periodType', 'DAILY')` : ''}), now(), 0, 0
FROM period WHERE EXISTS (SELECT 1 FROM job)
RETURNING (payload->'data'->>'periodFrom') || ' ' || (payload->'data'->>'periodTo');`)
}

/** 이번 주 주간 리포트(무료 수치 리포트). 학습 여정·보호자 이전 확인용 */
export const queueWeeklyReport = (nickname: string) => queueReport(nickname)
