import { useState } from 'react'
import { BookOpen, ArrowUpRight, ChevronDown, CheckCheck, Footprints, MessageSquarePlus } from 'lucide-react'
import './parent-overview.css'
import { ActivityExplorer } from './ActivityExplorer.tsx'
import { ChildParticipation } from './ChildParticipation.tsx'
import { ThinkingIcon } from './ThinkingIcon.tsx'
import { Link, useLocation, useNavigate } from 'react-router'
import { parentApi } from '../../data/parent/api.ts'
import { useParentDashboard, useParentQuery } from '../../data/parent/queries.ts'
import type { Child, Metric } from '../../domain/classroom.ts'
import { thinkingLabels } from '../../domain/classroom.ts'
import { gradeLabel } from '../../domain/grade.ts'
import type { Scope } from '../../domain/parent.ts'
import { metricText, reportPeriodType } from '../../domain/parent.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { Modal } from '../shared/ClassroomParts.tsx'
import { EntitlementSummary } from './EntitlementSummary.tsx'

const stateText = {
  OK: null,
  NO_RECORD: '기록 없음',
  INSUFFICIENT_SAMPLE: '표본 부족',
  PROCESSING: '처리 중',
  FAILED: '조회 실패',
} as const

/**
 * 학부모 대시보드 (FN-DSH-06~10, 학부모 대시보드 시안).
 * 숫자는 서버 Metric 그대로 쓰고, 표본이 적으면 비율을 만들지 않는다. 기록 없는 유형은 '미관찰'로 둔다.
 */
export function ParentDashboard({ child, scope, onChangePeriod }: { child: Child; scope: Scope; onChangePeriod: () => void }) {
  const { search } = useLocation()
  const scopeKey = `${scope.childId}:${scope.from}:${scope.to}`
  const [selection, setSelection] = useState({ key: scopeKey, page: 0, record: null as string | null })
  const current = selection.key === scopeKey ? selection : { key: scopeKey, page: 0, record: null }
  const q = useParentDashboard(scope, current.page)
  const [panel, setPanel] = useState<'thinking' | 'participation' | null>(null)
  const [typeFilter, setTypeFilter] = useState('')
  const [detailScope, setDetailScope] = useState(scope)
  const openPanel = (tab: 'thinking' | 'participation', type = '') => { setRecord(null); setPanel(tab); setTypeFilter(type); setDetailScope(scope) }
  const record = current.record
  const setRecord = (id: string | null) => setSelection({ ...current, record: id })
  const summary = q.summary.data && !q.summary.error ? q.summary.data : null
  const thinking = q.thinking.data && !q.thinking.error ? q.thinking.data.items : null
  const total = summary && ['OK', 'INSUFFICIENT_SAMPLE'].includes(summary.state) ? summary.metrics[0]?.count : undefined
  const revised = summary?.metrics.find(m => m.label === '생각을 덧붙인 활동' || m.label === '되묻기 후 생각을 더한 활동')
  let activitySummary = '답변을 제출한 활동'
  if (total !== undefined && total > 0) {
    activitySummary = `이 기간에 활동 ${total}개에 답했어요.`
    if (revised && Number.isInteger(revised.numerator) && revised.numerator >= 0 && revised.numerator <= total) {
      activitySummary += ` 그중 ${revised.numerator}개에서 생각을 덧붙였어요.`
    }
  }
  const seen = thinking && !['FAILED', 'PROCESSING'].includes(q.thinking.data!.state) &&
    thinking.every((t) => !['FAILED', 'PROCESSING'].includes(t.state))
    ? thinking.filter((t) => t.state === 'OK' || t.state === 'INSUFFICIENT_SAMPLE').length : undefined
  return (
    <div className="pd pd-overview">
      <header className="pd-head">
        <h1>{child.nickname}의 학습 현황</h1>
        <p className="pd-sub">
          {gradeLabel(child.grade)}
          {summary && ` · ${summary.period.from.replaceAll('-', '.')} — ${summary.period.to.replaceAll('-', '.')} (KST)`}
        </p>
      </header>

      <QueryFeedback query={q.summary} />
      {summary && summary.state !== 'OK' && (
        <div className="pd-status" role="status" data-query-state={summary.state}>
          <span className="pd-chip pd-chip-warn">{stateText[summary.state]}</span>
          <span>
            {summary.state === 'NO_RECORD'
              ? '선택한 기간에 답변을 제출한 활동이 없습니다.'
              : summary.state === 'INSUFFICIENT_SAMPLE'
                ? `이 기간 집계 대상 활동이 ${summary.metrics[0]?.count ?? '확인되지 않음'}건입니다. 비율은 5건 이상일 때부터 보여 드립니다.`
                : summary.state === 'FAILED' ? '학습 기록 조회에 실패했습니다. 다시 시도해 주세요.'
                : summary.state === 'PROCESSING' ? '학습 기록을 처리 중입니다.'
                : '기간 내 기록을 집계했습니다.'}
          </span>
          {summary.state === 'NO_RECORD' && <div className="pd-empty-actions">
            <button type="button" className="cj-secondary" onClick={onChangePeriod}>조회 기간 바꾸기</button>
            <Link to={'/parent/devices' + search}>첫 학습 준비 · {child.nickname}의 기기·PIN 설정</Link>
          </div>}
          {summary.state === 'FAILED' && <button type="button" className="cj-secondary" disabled={q.summary.isFetching} onClick={() => void q.summary.refetch()}>다시 시도</button>}
        </div>
      )}

      <div className="pd-overview-top">
        <section className="pd-portfolio" aria-label="학습 요약">
          <h2>이번 기간의 학습</h2>
          <div className="pd-overview-focus">
            <div className="pd-focus-value"><strong>{summary && !['FAILED', 'PROCESSING'].includes(summary.state) ? summary.metrics[0]?.count ?? '—' : '—'}</strong><span>건</span><span className="pd-focus-coverage">{seen ?? '—'} / 5가지 생각 활동</span></div>
            <p>{activitySummary}</p>
            <div className="pd-activity-chart" aria-label="생각 유형별 관찰 기록 수">
              {Object.entries(thinkingLabels).map(([type, label]) => {
                const item = thinking?.find(t => t.type === type)
                const ready = item && ['OK', 'INSUFFICIENT_SAMPLE', 'NO_RECORD'].includes(item.state)
                const count = ready ? item.missions.length : null
                const max = Math.max(1, ...(thinking ?? []).map(t => t.missions.length))
                return <div key={type} data-thinking={type}><span>{count ?? '—'}</span><div className="pd-chart-track"><i style={{ height: `${count === null ? 0 : count / max * 100}%` }} /></div><small><ThinkingIcon type={type} />{label}</small></div>
              })}
            </div>
          </div>
        </section>
        <section aria-label="기간 요약" className="pd-metric-group">
          <h2>학습 과정</h2>
          <div className="pd-kpis">{summary?.metrics.slice(1).map((m, index) => <Kpi key={m.label} m={m} index={index} />)}</div>
        </section>
      </div>

      <div className="pd-split">
        <section aria-labelledby="types-h" className="pd-card pd-types">
          <div className="pd-card-head">
            <h2 id="types-h">다섯 가지 생각 활동</h2>
          </div>
          <QueryFeedback query={q.thinking} />
          {thinking && (
            <ul>
              {thinking.map((t) => (
                <li key={t.type} data-thinking={t.type}>
                  <span className="pd-type">
                    <span className="pd-type-icon"><ThinkingIcon type={t.type} /></span>
                    {thinkingLabels[t.type]}
                  </span>
                  <div className="pd-recent-missions" role="group" aria-label={`${thinkingLabels[t.type]} 최근 활동`}>
                    {t.missions.slice(0, 5).map(m =>
                      <button key={m.attemptId} type="button" title={m.title} onClick={() => setRecord(m.attemptId)}>{m.title}</button>)}
                  </div>
                  <div className="pd-type-actions">
                    {(t.state === 'OK' || t.state === 'INSUFFICIENT_SAMPLE') && t.missions.length > 0
                      ? <button type="button" className="pd-type-records" aria-label={`${thinkingLabels[t.type]} 기록 ${t.missions.length}건 보기`}
                          aria-haspopup="dialog" onClick={() => openPanel('thinking', t.type)}>
                          기록 {t.missions.length}건 보기 <ArrowUpRight size={14} aria-hidden="true" />
                        </button>
                      : <span className="pd-chip">{t.state === 'NO_RECORD' || t.state === 'OK' ? '미관찰' : stateText[t.state]}</span>}
                  </div>

                </li>
              ))}
            </ul>
          )}
          <p className="pd-observation-note">활동에 남은 기록이며, 사고력 수준을 진단하지 않습니다.</p>
        </section>
        <ReportCard child={child} />
      </div>

      <nav className="pd-detail-launchers" aria-label="학습 상세 기록">
        <button type="button" onClick={() => openPanel('thinking')}>생각 활동 전체 보기 <ArrowUpRight size={17} /></button>
        <button type="button" onClick={() => openPanel('participation')}>참여 기록 <ArrowUpRight size={17} /></button>
      </nav>
      {panel && <Modal title={`${child.nickname}의 학습 기록`} onClose={() => { setPanel(null); setRecord(null) }}>
        <div className="pd-record-explorer">
          <nav className="pd-explorer-nav" aria-label="상세 기록 메뉴">
            <span className="pd-explorer-brand"><BookOpen size={24} /> 학습 기록</span>
            {([['thinking', '생각 활동'], ['participation', '참여 기록']] as const).map(([tab, label]) =>
              <button key={tab} type="button" aria-current={panel === tab ? 'page' : undefined} onClick={() => { setPanel(tab); setRecord(null) }}>{label}<ArrowUpRight size={16} /></button>)}
            <small>{gradeLabel(child.grade)} · {child.nickname}</small>
          </nav>
          <div className="pd-explorer-content">
            {panel === 'participation' && <div className="pd-explorer-period">참여 기록 · 전체 기간</div>}
            {record && <><button className="pd-explorer-back" type="button" onClick={() => setRecord(null)}>← 목록으로</button><RecordDetail scope={detailScope} id={record} /></>}
            <div hidden={!!record}>
              {panel === 'thinking' && <ActivityExplorer scope={scope} initialType={typeFilter} onOpen={(id, period) => { setDetailScope(period); setRecord(id) }} />}
              {panel === 'participation' && <ChildParticipation child={child} />}
            </div>
          </div>
        </div>
      </Modal>}
      {!panel && record && (
        <Modal title="학습 기록 원문" onClose={() => setRecord(null)}>
          <RecordDetail scope={scope} id={record} />
        </Modal>
      )}
    </div>
  )
}

function Kpi({ m, index }: { m: Metric; index: number }) {
  const Icon = [CheckCheck, Footprints, MessageSquarePlus][index % 3]
  const ratio = m.value !== null
  return (
    <article className="pd-card pd-kpi">
      <div className="pd-kpi-heading"><h2>{m.label}</h2><Icon size={19} aria-hidden="true" /></div>
      <div className="pd-value" data-ratio={ratio || undefined}>
        {metricText(m) === '확인되지 않음' ? (
          <strong>확인되지 않음</strong>
        ) : ratio ? (
          <>
            <strong>{Math.round(m.value! * 100)}%</strong>
            <span>
              {m.numerator} / {m.denominator}건
            </span>
          </>
        ) : m.numerator !== m.denominator ? (
          <>
            <strong>{m.numerator}</strong>
            <span>/ {m.denominator}건</span>
          </>
        ) : (
          <>
            <strong>{m.count}</strong>
            <span>건</span>
          </>
        )}
      </div>
      <details className="pd-metric-definition"><summary>집계 기준 <ChevronDown size={14} aria-hidden="true" /></summary><p>{m.formula}</p></details>
    </article>
  )
}

function ReportCard({ child }: { child: Child }) {
  const navigate = useNavigate()
  const { search } = useLocation()
  const list = useParentQuery(['reports', child.id, 'COMPLETED', ''], (signal) => parentApi.reports(child.id, 'COMPLETED', signal))
  const latest = list.data && !list.error ? list.data.items.filter(report =>
    report.status === 'COMPLETED' && reportPeriodType(report) === 'WEEKLY' && report.childId === child.id)
    .sort((a, b) => b.period.to.localeCompare(a.period.to) || b.revision - a.revision)[0] : undefined
  const reportParams = new URLSearchParams(search)
  for (const key of ['reportId', 'revision', 'view']) reportParams.delete(key)
  if (latest) reportParams.set('reportId', latest.reportId)
  return (
    <section aria-labelledby="report-h" className="pd-card pd-report">
      <div className="pd-report-title"><BookOpen size={21} aria-hidden="true" /><h2 id="report-h">최근 주간 리포트</h2></div>
      <QueryFeedback query={list} />
      {list.data && !list.error && !latest && <p>아직 볼 수 있는 주간 리포트가 없습니다.</p>}
      {latest && <p className="pd-report-meta pd-num">{latest.period.from} ~ {latest.period.to}</p>}
      <EntitlementSummary childId={child.id} report />
      <div className="pd-actions">
        <button type="button" className="cj-primary" onClick={() => navigate('/parent/report?' + reportParams)}>
          리포트 보기
        </button>
        <button type="button" className="cj-secondary" onClick={() => navigate('/parent/analysis' + search)}>
          AI 챗봇으로 질문하기
        </button>
      </div>
    </section>
  )
}

/** 학습 기록 원문: 최초 답변·되묻기·보완 답변·생각 열기 이용·돌아보기 (FN-DSH-09). 메모는 없다. */
export function RecordDetail({ scope, id }: { scope: Scope; id: string }) {
  const q = useParentQuery(['record', scope, id], (signal) =>
    parentApi.record(scope.childId, id, signal, scope),
  )
  return (
    <>
      <QueryFeedback query={q} />
      {q.data && !q.error && ['FAILED', 'PROCESSING'].includes(q.data.state) && (
        <p role="status">{stateText[q.data.state]} · 다시 조회해 주세요.</p>
      )}
      {q.data && !q.error && !['FAILED', 'PROCESSING'].includes(q.data.state) && (
        <>
          <article className="pd-original">
            <header className="pd-original-heading"><h2>{q.data.mission.title}</h2><p>{q.data.period.from} — {q.data.period.to}</p></header>
            <div className="pd-original-answers">{q.data.answers.map(a => <section className="pd-original-answer" key={a.answerId}>
              <header><h3>{a.version === 1 ? '최초 답변' : `보완 답변 ${a.version - 1}`}</h3><time>{new Date(a.submittedAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', dateStyle: 'medium', timeStyle: 'short' })}</time></header>
              <blockquote>{a.text}</blockquote>
              {a.feedback.followup && <aside className="pd-original-followup"><strong>되묻기</strong><p>{a.feedback.followup.question}</p></aside>}
            </section>)}</div>
            <section className="pd-original-reflection"><header><h3>돌아보기</h3><span>생각 열기 {q.data.helped ? '이용함' : '이용 안 함'}</span></header>
              {q.data.reflection ? <><span className="pd-original-difficulty">{q.data.reflection.difficulty}</span><p>{q.data.reflection.text || '달라진 점을 작성하지 않았어요.'}</p></> : <p>아직 작성한 돌아보기가 없습니다.</p>}
            </section>
          </article>
        </>
      )}
    </>
  )
}
