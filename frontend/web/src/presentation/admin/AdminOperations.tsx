import { useRef, useState } from 'react'
import { ArrowUpRight, BookOpen, CalendarDays, CheckCheck, FilePenLine, NotebookPen, RotateCcw, Search, Server } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'
import { WorkloadCards, ThemeWorkQueue } from './AdminReviewHome.tsx'
import './review-home.css'
import { adminApi } from '../../data/admin/api.ts'
import { useAdminQuery, useAdminMutation } from '../../data/admin/queries.ts'
import type { Audit, Permission } from '../../domain/admin/operations.ts'
import { auditTargetLabels, callTypeLabels, hasPermission, jobLabels, jobTypeLabels, jobRetryMessage, labelOf, missionLabels } from '../../domain/admin/operations.ts'
import type { Period } from '../../domain/classroom.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { Badge, Empty, Inspector } from './AdminUi.tsx'
import { auditActionLabel, date, modelScopeLabel, number, queueHeading } from './adminFormatting.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
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
  if (page === 'audit') return <AuditLog key={period.from + period.to} period={period} />
  if (page === 'usage') return <Usage period={period} />
  return <Overview period={period} permissions={permissions} />
}
function Overview({ period, permissions }: { period: Period; permissions: Permission[] }) {
  const q = useAdminQuery(['overview', period], (signal) => adminApi.overview(period, signal))
  return (
    <>
      <WorkloadCards period={period} permissions={permissions}/>
      {hasPermission(permissions, 'CONTENT') && <ThemeWorkQueue/>}
      <QueryFeedback query={q} />
      {q.data && !q.error && (
        <>
          <div className="ad-overview-intro"><p>
            실제 집계 기간 · {q.data.period.from} ~ {q.data.period.to}
          </p><details><summary>집계 기준</summary><p>{q.data.inclusionRule}</p><p>{q.data.learning.inclusionRule}</p></details></div>
          <div className="ad-overview-top"><section className="ad-learning-summary" aria-label="학습 현황"><h2>학습 현황</h2><div className="ws-metrics">
            <article className="ws-card">
              <div className="ad-metric-heading"><h3>학습 시도</h3><span className="ad-metric-icon"><NotebookPen size={20} aria-hidden="true" /></span></div>
              <strong className="ws-number">{q.data.learning.attempts}건</strong>
            </article>
            <article className="ws-card ad-completed-card">
              <div className="ad-metric-heading"><h3>학습 완료</h3><span className="ad-metric-icon"><CheckCheck size={20} aria-hidden="true" /></span></div>
              <strong className="ws-number">{q.data.learning.completedAttempts}건</strong>
            </article>
          </div></section><section className="ad-shortcuts" aria-label="업무 바로가기"><h2>바로가기</h2>
            {hasPermission(permissions, 'CONTENT') && <>
              <Link to="/admin/mission-drafts"><FilePenLine size={19} aria-hidden="true" /><span><strong>미션 초안 만들기</strong></span><ArrowUpRight size={16} aria-hidden="true" /></Link>
              <Link to="/admin/themes"><CalendarDays size={19} aria-hidden="true" /><span><strong>주간 테마 관리</strong></span><ArrowUpRight size={16} aria-hidden="true" /></Link>
            </>}
            {hasPermission(permissions, 'SERVICE_OPS') && <Link to={`/admin/jobs?${new URLSearchParams({ ...period, status: 'FAILED' })}`}><RotateCcw size={19} aria-hidden="true" /><span><strong>실패한 작업 확인</strong></span><ArrowUpRight size={16} aria-hidden="true" /></Link>}
            {!hasPermission(permissions, 'CONTENT') && !hasPermission(permissions, 'SERVICE_OPS') && <Link to={`/admin/audit?${new URLSearchParams({ ...period })}`}><BookOpen size={19} aria-hidden="true" /><span><strong>감사 이력 확인</strong></span><ArrowUpRight size={16} aria-hidden="true" /></Link>}
          </section></div>
          {hasPermission(permissions, 'SERVICE_OPS') && (
            <>
              <div className="ad-section-title"><h3>처리 현황</h3></div>
              <div className="ad-table-wrap ad-job-matrix"><table className="ad-table">
                <thead><tr><th scope="col">작업</th>{Object.entries(jobLabels).map(([status, label]) => <th scope="col" key={status}>{label}</th>)}</tr></thead>
                <tbody>{Object.entries(jobTypeLabels).map(([type, label]) => {
                  const counts = q.data.jobCounts.filter(c => c.type === type)
                  if (!counts.length) return null
                  return <tr key={type}><th scope="row">{label}</th>{Object.entries(jobLabels).map(([status, statusLabel]) => {
                    const count = counts.find(c => c.status === status)
                    return <td key={status}>{count ? <Link className={status === 'FAILED' && count.count > 0 ? 'ad-job-alert' : ''}
                      to={`/admin/jobs?${new URLSearchParams({ ...period, type, status })}`}>
                      <span className="ad-sr">{label} · {statusLabel} </span>{count.count}건<ArrowUpRight size={13} aria-hidden="true" />
                    </Link> : <span aria-label="집계 없음">—</span>}</td>
                  })}</tr>
                })}</tbody>
              </table></div>
            </>
          )}
        </>
      )}
      {hasPermission(permissions, 'CONTENT') && <MissionPublication />}
    </>
  )
}
function MissionPublication() {
  const q = useAdminQuery(['missions', 'overview'], async signal => {
    // counts는 페이지·필터와 무관한 전체 네 상태의 집계다. 미션 본문은 한 건만 요청한다.
    const { counts } = await adminApi.missions({ page: '0', size: '1' }, signal)
    if (!Array.isArray(counts) || counts.length !== Object.keys(missionLabels).length ||
      new Set(counts.map(c => c?.status)).size !== counts.length ||
      counts.some(c => !c || !Object.hasOwn(missionLabels, c.status) || !Number.isSafeInteger(c.count) || c.count < 0)) {
      throw new Error('미션 공개 현황의 집계를 확인하지 못했습니다.')
    }
    return counts
  })
  return <section className="ad-mission-publication" aria-labelledby="mission-publication-title">
    <h2 id="mission-publication-title">미션 공개 현황</h2>
    <p>전체 미션 · 현재 상태</p>
    <QueryFeedback query={q} />
    {q.data && !q.error && <div className="ws-metrics">
      {Object.entries(missionLabels).map(([status, label]) => <Link className="ws-card" key={status}
        to={`/admin/missions?${new URLSearchParams({ status })}`}>
        <h3>{label}</h3><strong className="ws-number">{q.data.find(c => c.status === status)!.count}개</strong>
      </Link>)}
    </div>}
  </section>
}
function Jobs() {
  const [params, setParams] = useSearchParams(),
    type = params.get('type') ?? '',
    status = params.get('status') ?? '',
    page = Math.max(0, Number.parseInt(params.get('page') ?? '0', 10) || 0),
    [id, setId] = useState<string | null>(null),
    period =
      params.get('from') && params.get('to')
        ? { from: params.get('from')!, to: params.get('to')! }
        : undefined,
    q = useAdminQuery(['jobs', type, status, period, page], (signal) =>
      adminApi.jobs(type, status, signal, period, page),
    )
  function filter(key: string, value: string) {
    const next = new URLSearchParams(params)
    next.set(key, value)
    if (key !== 'page') next.delete('page')
    setParams(next)
  }
  return <section className="ad-data-surface">
    <div className="ad-data-toolbar"><div><h2>작업 목록</h2></div><button disabled={q.isFetching} onClick={() => void q.refetch()}><RotateCcw size={15} aria-hidden="true" />새로고침</button></div>
    <div className="ad-list-filters"><label>작업 유형<select aria-label="작업 유형" value={type} onChange={e => filter('type', e.target.value)}><option value="">전체</option>{Object.entries(jobTypeLabels).map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label><label>작업 상태<select aria-label="작업 상태" value={status} onChange={e => filter('status',e.target.value)}><option value="">전체</option>{Object.entries(jobLabels).map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label></div>
    <QueryFeedback query={q} />
    {q.data && !q.error && <><div className="ad-table-wrap"><table className="ad-table"><thead><tr><th>작업</th><th>상태</th><th>재처리</th><th>실패 사유</th><th>확인</th></tr></thead><tbody>{q.data.items.map(j => <tr key={j.jobId}><td><strong>{jobTypeLabels[j.type]}</strong><small className="ad-record-id" title={j.jobId}>{j.jobId}</small></td><td><Badge active={j.status === 'COMPLETED'} tone={j.status === 'FAILED' ? 'danger' : undefined}>{jobLabels[j.status]}</Badge></td><td>{j.retryCount}회</td><td className="ad-cell-note">{j.failureReason ?? '—'}</td><td><button onClick={() => setId(j.jobId)}>작업 상세</button></td></tr>)}</tbody></table></div>{!q.data.items.length && <Empty>조건에 맞는 작업이 없습니다.</Empty>}</>}
    {q.data && !q.error && q.data.totalElements > q.data.size && <nav aria-label="작업 목록 페이지" className="ad-list-footer">
      <button disabled={page === 0} onClick={() => filter('page', String(page - 1))}>이전</button>
      <span>{page + 1} / {Math.ceil(q.data.totalElements / q.data.size)}</span>
      <button disabled={(page + 1) * q.data.size >= q.data.totalElements} onClick={() => filter('page', String(page + 1))}>다음</button>
    </nav>}
    {id && <Inspector title="작업 상세·재처리" onClose={() => setId(null)}><JobDetail key={id} id={id} /></Inspector>}
  </section>
}

function JobDetail({ id }: { id: string }) {
  const [selectedId, setSelectedId] = useState(id)
  const q = useAdminQuery(['job', selectedId], (signal) => adminApi.job(selectedId, signal)),
    key = useRef<string | null>(null),
    // 멱등 키는 실패 후 다시 시도할 때 재사용하고, 성공·원래 작업 복귀 때만 버린다. 훅 인자에서 ref를 읽지 않도록 변수로 넘긴다.
    retry = useAdminMutation((idempotencyKey: string) => adminApi.retry(selectedId, idempotencyKey)),
    [notice, setNotice] = useState('')
  function run() {
    key.current ??= crypto.randomUUID()
    void retry
      .mutateAsync(key.current)
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
          <div className="ad-job-summary"><h3>{jobTypeLabels[q.data.type]}</h3><Badge active={q.data.status === 'COMPLETED'} tone={q.data.status === 'FAILED' ? 'danger' : undefined}>{jobLabels[q.data.status]}</Badge></div>
          <dl className="ad-facts"><dt>작업 번호</dt><dd>{selectedId}</dd><dt>실패 사유</dt><dd>{q.data.failureReason ?? '실패 원인 없음'}</dd></dl>
          {q.data.status === 'FAILED' && !q.data.retryable && (
            <p>재처리 연결 대기 · {q.data.retryUnavailableReason}</p>
          )}
          <section className="ad-job-history"><h4>처리 이력</h4><ol className="ad-job-timeline">{q.data.executions.map(e => <li key={e.executionId}><strong>{e.attemptNo}회</strong><div><Badge active={e.status === 'COMPLETED'} tone={e.status === 'FAILED' ? 'danger' : undefined}>{jobLabels[e.status]}</Badge><time dateTime={e.startedAt}>{date(e.startedAt)}</time><code>{e.errorCode ?? '오류 없음'}</code></div></li>)}</ol>{!q.data.executions.length && <p className="ad-cell-note">아직 처리 이력이 없습니다.</p>}</section>
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
  const q = useAdminQuery(['queues'], signal => adminApi.queues(signal))
  const totalLabels = { WORK: '대기 또는 처리 중', RETRY: '재시도 대기', DLQ: '실패 보관' }
  return <><QueryFeedback query={q} />{q.data && !q.error && <div className="ad-queue-grid">
    {q.data.items.map(c => {
      const unavailable = ['down', 'stopped', 'crashed'].includes(c.state)
      const attention = unavailable ? '대기열 상태 확인'
        : c.kind === 'DLQ' && c.messages > 0 ? '실패 원인 확인'
        : c.kind === 'WORK' && c.messages > 0 && c.consumers === 0 ? '처리 연결 없음' : null
      return <article className={`ad-queue-card${c.kind === 'DLQ' ? ' is-dlq' : ''}`} key={c.name}>
        <header>
          <span className="ad-queue-icon"><Server size={21} aria-hidden="true" /></span>
          <h2>{queueHeading(c)}</h2>
          {attention && <Badge tone="danger">{attention}</Badge>}
        </header>
        <div className="ad-queue-volume"><strong>{number(c.messages)}건</strong><span>{totalLabels[c.kind]}</span></div>
        {c.kind === 'WORK' && <dl className="ad-queue-breakdown">
          <div><dt>처리 대기</dt><dd>{number(c.messagesReady)}건</dd></div>
          <div><dt>처리 중</dt><dd>{number(c.messagesUnacknowledged)}건</dd></div>
        </dl>}
        {c.kind === 'DLQ' && <p className="ad-queue-note">자동 처리에서 제외된 작업입니다.</p>}
        <details className="ad-queue-technical">
          <summary>기술 정보</summary>
          <dl>
            <div><dt>큐 이름</dt><dd><code>{c.name}</code></dd></div>
            <div><dt>시스템 상태</dt><dd><code>{c.state}</code></dd></div>
            <div><dt>처리 구독 수</dt><dd>{number(c.consumers)}</dd></div>
            {c.kind !== 'WORK' && <>
              <div><dt>대기 메시지</dt><dd>{number(c.messagesReady)}</dd></div>
              <div><dt>처리 중 메시지</dt><dd>{number(c.messagesUnacknowledged)}</dd></div>
            </>}
          </dl>
        </details>
      </article>
    })}{!q.data.items.length && <Empty>조회된 작업 대기열이 없습니다.</Empty>}
  </div>}</>
}
function AuditLog({ period }: { period: Period }) {
  const [target, setTarget] = useState(''), [result, setResult] = useState(''), [search, setSearch] = useState('')
  const [page,setPage] = useState(0)
  const q = useAdminQuery(['audit', period, target, page], signal => adminApi.audits(period, target, signal, page))
  const term = search.trim().toLowerCase()
  const rows = (q.error ? [] : q.data?.items ?? []).map(a => ({
    ...a,
    actionLabel: auditActionLabel(a.action),
    targetLabel: a.targetType === 'JOB' ? '작업' : labelOf(auditTargetLabels, a.targetType),
  })).filter(a => (!result || a.result === result) &&
    [a.actionLabel, a.action, a.targetLabel, a.targetType, a.targetId, a.actorUserId].join(' ').toLowerCase().includes(term))
  return <section className="ad-data-surface ad-audit-ledger">
    <div className="ad-data-toolbar"><div><h2>활동 기록</h2></div></div>
    <div className="ad-list-filters"><label className="ad-inline-search"><Search size={16} aria-hidden="true" /><input aria-label="조회된 감사 이력 검색" placeholder="작업·대상·처리자 검색" value={search} onChange={e => setSearch(e.target.value)} /></label><label>대상 유형<select aria-label="감사 대상 유형" value={target} onChange={e => { setTarget(e.target.value); setPage(0) }}><option value="">전체</option>{Object.entries(auditTargetLabels).map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label></div>
    <div className="ad-result-tabs" aria-label="감사 결과 필터">{[['','전체 결과'],['SUCCESS','성공'],['FAILURE','실패']].map(([v,l]) => <button key={v} aria-pressed={result === v} onClick={() => setResult(v)}>{l}</button>)}<span>조회된 이력 내 검색</span></div>
    <QueryFeedback query={q} />
    {q.data && !q.error && <><div className="ad-table-wrap"><table className="ad-table"><thead><tr><th>시각</th><th>작업</th><th>대상</th><th>처리자 ID</th><th>결과</th></tr></thead><tbody>{rows.map(a => <tr key={a.id}>
      <td className="ad-time-cell"><time dateTime={a.createdAt}>{date(a.createdAt)}</time></td>
      <td>
        <strong className="ad-audit-action" title={a.action}>{a.actionLabel}</strong>
        {a.actionLabel === '기타 작업' && <small className="ad-record-id">{a.action}</small>}
        {a.targetType === 'MODEL_VERSION' ? <AuditModelDetail detail={a.detail} /> :
          <details className="ad-audit-detail"><summary>활동 상세</summary><dl>
            <div><dt>기록 번호</dt><dd>{a.id}</dd></div><div><dt>작업 코드</dt><dd>{a.action}</dd></div>
            <div><dt>대상 번호</dt><dd>{a.targetId ?? '기록 없음'}</dd></div>
          </dl></details>}
      </td>
      <td>{a.targetLabel}<small className="ad-record-id" title={a.targetId ?? undefined}>{a.targetId ?? '—'}</small></td><td><span className="ad-record-id" title={a.actorUserId}>{a.actorUserId}</span></td><td><Badge tone={a.result === 'SUCCESS' ? 'success' : 'danger'}>{a.result === 'SUCCESS' ? '성공' : '실패'}</Badge></td>
    </tr>)}</tbody></table></div>{!rows.length && <Empty>{search || result ? '검색 조건에 맞는 이력이 없습니다.' : '조회 기간의 조치 이력이 없습니다.'}</Empty>}<div className="ad-list-footer"><span>현재 페이지 {rows.length}건 표시</span>{q.data.totalElements > q.data.size && <>
      <button disabled={page===0} onClick={()=>setPage(page-1)}>이전</button><span>{page+1} / {Math.ceil(q.data.totalElements/q.data.size)}</span>
      <button disabled={(page+1)*q.data.size>=q.data.totalElements} onClick={()=>setPage(page+1)}>다음</button></>}{(search || result) && <button onClick={() => {setSearch(''); setResult('')}}>검색 초기화</button>}</div></>}
  </section>
}
const auditModelFields = {
  name: '모델 이름', version: '버전', scopes: '적용 범위', reason: '변경 사유',
  reanalysisPlanned: '재분석 계획 (실행 아님)', previousVersionId: '이전 버전 ID',
}
function AuditModelDetail({ detail }: { detail: Audit['detail'] }) {
  return <details className="ad-audit-detail">
    <summary>모델 버전 조치 상세</summary>
    {detail ? <dl>{Object.entries(auditModelFields).map(([key, label]) => {
      const raw = detail[key]
      let value = raw == null ? '기록 없음' : String(raw)
      if (typeof raw === 'boolean') value = raw ? '있음' : '없음'
      if (key === 'scopes' && Array.isArray(raw)) value = raw.map(scope => modelScopeLabel(String(scope))).join(', ') || '없음'
      if (key === 'name' && raw === 'judge') value = '판정'
      return <div key={key}><dt>{label}</dt><dd title={value !== String(raw) && raw != null && typeof raw !== 'boolean' ? String(raw) : undefined}>{value}</dd></div>
    })}</dl> : <p>이 기록에는 조회 가능한 상세 정보가 없습니다.</p>}
  </details>
}
function Usage({ period }: { period: Period }) {
  const [type, setType] = useState(''), q = useAdminQuery(['usage', period, type], signal => adminApi.usage(period, type, signal))
  return <section className="ad-data-surface">
    <div className="ad-data-toolbar"><div><h2>호출별 사용량</h2><p>확인하지 못한 비용은 미측정으로 표시합니다.</p></div><label>호출 종류<select aria-label="호출 종류" value={type} onChange={e => setType(e.target.value)}><option value="">전체</option>{Object.entries(callTypeLabels).map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label></div>
    <QueryFeedback query={q} />
    {q.data && !q.error && <><div className="ad-table-wrap"><table className="ad-table"><thead><tr><th>호출 종류</th><th className="num">호출 / 실패</th><th className="num">평균 지연</th><th className="num">입력 / 출력 토큰</th><th className="num">비용 (USD)</th></tr></thead><tbody>{q.data.items.map(u => <tr key={u.callType}><td><strong>{labelOf(callTypeLabels,u.callType)}</strong></td><td className="num">{number(u.calls)} / <span className={u.failures ? 'ad-text-danger' : ''}>{number(u.failures)}</span></td><td className="num">{u.calls ? `${number(u.latencyMs)}ms` : '미측정'}</td><td className="num">{u.inputTokens == null ? '미측정' : number(u.inputTokens)} / {u.outputTokens == null ? '미측정' : number(u.outputTokens)}</td><td className="num"><strong>{u.costUsd ?? '미측정'}</strong><small>비용 미산정 {number(u.unpricedCalls)}건{u.externallyBilledCalls > 0 && ` · 별도 청구 ${number(u.externallyBilledCalls)}건`}</small></td></tr>)}</tbody></table></div>{!q.data.items.length && <Empty>이 기간에 기록된 AI 호출이 없습니다.</Empty>}<div className="ad-list-footer"><span>실제 조회 기간 {q.data.period.from} ~ {q.data.period.to}</span></div></>}
  </section>
}
