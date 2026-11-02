import { useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { adminApi } from '../../data/admin/api.ts'
import { useAdminQuery, useAdminMutation } from '../../data/admin/queries.ts'
import type { Permission } from '../../domain/admin/operations.ts'
import { hasPermission, jobLabels, jobRetryMessage } from '../../domain/admin/operations.ts'
import type { Period } from '../../domain/classroom.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
export function AdminOperations({
  page,
  period,
  permissions,
}: {
  page: string
  period: Period
  permissions: Permission[]
}) {
  if (page === 'jobs') return <Jobs />
  if (page === 'queues') return <Queues />
  if (page === 'audit') return <AuditLog period={period} />
  if (page === 'usage') return <Usage period={period} />
  return <Overview period={period} permissions={permissions} />
}
function Overview({ period, permissions }: { period: Period; permissions: Permission[] }) {
  const q = useAdminQuery(['overview', period], (signal) => adminApi.overview(period, signal))
  return (
    <>
      <h2>운영 현황</h2>
      <QueryFeedback query={q} />
      {q.data && !q.error && (
        <>
          <p>
            실제 집계 기간 · {q.data.period.from} ~ {q.data.period.to}
          </p>
          <p>{q.data.inclusionRule}</p>
          <p>{q.data.learning.inclusionRule}</p>
          <div className="ws-metrics">
            <article className="ws-card">
              <h3>학습 시도</h3>
              <strong className="ws-number">{q.data.learning.attempts}건</strong>
            </article>
            <article className="ws-card">
              <h3>학습 완료</h3>
              <strong className="ws-number">{q.data.learning.completedAttempts}건</strong>
            </article>
          </div>
          {hasPermission(permissions, 'SERVICE_OPS') && (
            <>
              <h3>처리 현황</h3>
              <div className="ws-metrics">
                {q.data.jobCounts.map((c) => (
                  <Link
                    className="ws-card"
                    key={c.type + c.status}
                    to={`/admin/jobs?${new URLSearchParams({ ...period, type: c.type, status: c.status })}`}
                  >
                    {c.type} · {jobLabels[c.status]} <strong>{c.count}건</strong>
                  </Link>
                ))}
              </div>
            </>
          )}
          {hasPermission(permissions, 'CONTENT') && (
            <>
              <h3>미션 공개 현황</h3>
              <p>미션 공개 현황은 관리자 미션 공급자 연결 후 조회할 수 있습니다.</p>
            </>
          )}
        </>
      )}
    </>
  )
}
function Jobs() {
  const [params, setParams] = useSearchParams(),
    type = params.get('type') ?? '',
    status = params.get('status') ?? '',
    [id, setId] = useState<string | null>(null),
    period =
      params.get('from') && params.get('to')
        ? { from: params.get('from')!, to: params.get('to')! }
        : undefined,
    q = useAdminQuery(['jobs', type, status, period], (signal) =>
      adminApi.jobs(type, status, signal, period),
    )
  function filter(key: string, value: string) {
    const next = new URLSearchParams(params)
    next.set(key, value)
    setParams(next)
  }
  return (
    <>
      <h2>작업 목록</h2>
      <div className="ws-toolbar">
        <label>
          작업 유형
          <select
            aria-label="작업 유형"
            value={type}
            onChange={(e) => filter('type', e.target.value)}
          >
            <option value="">전체</option>
            {['REPORT', 'CONVERSATION', 'NOTIFICATION'].map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label>
          작업 상태
          <select
            aria-label="작업 상태"
            value={status}
            onChange={(e) => filter('status', e.target.value)}
          >
            <option value="">전체</option>
            {Object.entries(jobLabels).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
      </div>
      <QueryFeedback query={q} />
      {q.data && !q.error && (
        <div className="ws-stack">
          {!q.data.items.length && <p>조건에 맞는 작업이 없습니다.</p>}
          {q.data.items.map((j) => (
            <article className="ws-card" key={j.jobId}>
              <h3>
                {j.type} · {j.jobId}
              </h3>
              <p>
                {jobLabels[j.status]} · 재처리 {j.retryCount}회
              </p>
              <p>{j.failureReason}</p>
              <button className="cj-secondary" onClick={() => setId(j.jobId)}>
                작업 상세
              </button>
            </article>
          ))}
        </div>
      )}
      {id && (
        <Modal title="작업 상세·재처리" onClose={() => setId(null)}>
          <JobDetail key={id} id={id} />
        </Modal>
      )}
    </>
  )
}
function JobDetail({ id }: { id: string }) {
  const [selectedId, setSelectedId] = useState(id)
  const q = useAdminQuery(['job', selectedId], (signal) => adminApi.job(selectedId, signal)),
    key = useRef<string | null>(null),
    retry = useAdminMutation(() => {
      key.current ??= crypto.randomUUID()
      return adminApi.retry(selectedId, key.current)
    }),
    [notice, setNotice] = useState('')
  function run() {
    void retry
      .mutateAsync(undefined)
      .then((j) => {
        key.current = null
        setSelectedId(j.jobId)
        setNotice(jobRetryMessage(j.status))
      })
      .catch(() => {})
  }
  return (
    <>
      <QueryFeedback query={q} />
      {q.data && !q.error && (
        <>
          <h3>
            {q.data.type} · {jobLabels[q.data.status]}
          </h3>
          <p>{q.data.failureReason ?? '실패 원인 없음'}</p>
          {q.data.status === 'FAILED' && !q.data.retryable && (
            <p>재처리 연결 대기 · {q.data.retryUnavailableReason}</p>
          )}
          <h4>처리 이력</h4>
          {q.data.executions.map((e) => (
            <p key={e.executionId}>
              {e.attemptNo}회 · {jobLabels[e.status]} · {e.errorCode ?? '오류 없음'} ·{' '}
              {e.startedAt}
            </p>
          ))}
          {q.data.retryable && (
            <button className="cj-primary" disabled={retry.isPending} onClick={run}>
              작업 재처리
            </button>
          )}
        </>
      )}
      <button disabled={q.isFetching} onClick={() => {
        void q.refetch().then(({ data, error }) => {
          if (data && !error) setNotice(jobRetryMessage(data.status))
        })
      }}>작업 상태 새로고침</button>
      {selectedId !== id && <button onClick={() => {
        key.current = null
        setSelectedId(id)
        setNotice('')
      }}>원래 작업 보기</button>}
      <p role="status">{notice}</p>
      <ErrorNotice error={retry.error} retry={run} />
    </>
  )
}
function Queues() {
  const q = useAdminQuery(['queues'], (signal) => adminApi.queues(signal))
  return (
    <>
      <h2>큐·DLQ</h2>
      <QueryFeedback query={q} />
      {q.data && !q.error && (
        <div className="ws-metrics">
          {q.data.items.map((c) => (
            <article className="ws-card" key={c.name}>
              <h3>{c.name}</h3>
              <p>
                {c.kind} · 전체 {c.messages} · 대기 {c.messagesReady} · 처리 중 {c.messagesUnacknowledged} · 소비자 {c.consumers} · {c.state}
              </p>
            </article>
          ))}
        </div>
      )}
    </>
  )
}
function AuditLog({ period }: { period: Period }) {
  const [target, setTarget] = useState(''),
    q = useAdminQuery(['audit', period, target], (signal) =>
      adminApi.audits(period, target, signal),
    )
  return (
    <>
      <h2>감사 이력</h2>
      <label>
        대상 유형
        <select
          aria-label="감사 대상 유형"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
        >
          <option value="">전체</option>
          {['CONVERSATION', 'REPORT', 'NOTIFICATION', 'MISSION', 'MODEL_VERSION', 'ERROR_REPORT', 'ACCOUNT_MANAGEMENT'].map((v) => (
            <option key={v}>{v}</option>
          ))}
        </select>
      </label>
      <QueryFeedback query={q} />
      {q.data && !q.error && (
        <div className="ws-stack">
          {!q.data.items.length && <p>조회 기간의 조치 이력이 없습니다.</p>}
          {q.data.items.map((a) => (
            <article className="ws-card" key={a.id}>
              <h3>
                {a.action} · {a.result === 'SUCCESS' ? '성공' : '실패'}
              </h3>
              <p>
                {a.actorUserId} · {a.targetType} / {a.targetId} · {a.createdAt}
              </p>
            </article>
          ))}
        </div>
      )}
    </>
  )
}
function Usage({ period }: { period: Period }) {
  const [type, setType] = useState(''),
    q = useAdminQuery(['usage', period, type], (signal) => adminApi.usage(period, type, signal))
  return (
    <>
      <h2>AI 사용량</h2>
      <p>
        조회 기간의 호출·평균 지연·토큰 합계를 확인합니다. 확인하지 못한 비용은 0 대신 ‘미측정’으로 표시합니다.
      </p>
      <label>
        호출 종류
        <select aria-label="호출 종류" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">전체</option>
          {['JUDGMENT', 'FOLLOWUP', 'ANALYSIS', 'REPORT_NARRATIVE', 'M2', 'M1'].map((v) => (
            <option key={v}>{v}</option>
          ))}
        </select>
      </label>
      <QueryFeedback query={q} />
      {q.data && !q.error && (
        <>
          <p>
            실제 조회 기간 {q.data.period.from} ~ {q.data.period.to}
          </p>
          {!q.data.items.length && <p>이 기간에 기록된 AI 호출이 없습니다.</p>}
          <div className="ws-metrics">
            {q.data.items.map((u) => (
              <article className="ws-card" key={u.callType}>
                <h3>{u.callType}</h3>
                <p>
                  호출 {u.calls} · 실패 {u.failures} · 지연{' '}
                  {u.calls ? `${u.latencyMs}ms` : '미측정'}
                </p>
                <p>
                  입력 토큰 {u.inputTokens ?? '미측정'} · 출력 토큰 {u.outputTokens ?? '미측정'} ·
                  비용 {u.costUsd ?? '미측정'} · 비용 미산정 {u.unpricedCalls}건
                </p>
              </article>
            ))}
          </div>
        </>
      )}
    </>
  )
}
