import { BookOpen, ChevronDown, ChevronRight, Lock, TextSearch, NotebookPen, GitCompareArrows, ChartNoAxesColumnIncreasing } from 'lucide-react'
import type { ReactNode } from 'react'
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { ReportExplanations, reportExplanationItems } from './ReportExplanations.tsx'
import { DailyReportSummary } from './DailyReportSummary.tsx'
import { dailyReportGroups, type DailyActivitySelection } from '../../domain/dailyReportNavigation.ts'
import type { Child, Metric } from '../../domain/classroom.ts'
import { scheduledDayLine, answerTimeLine, difficultyText, type DailyProblem, type WeeklyReport, type ReportItem, type ReportPeriodType, type ThemeSummary } from '../../domain/parent.ts'
import { reportPeriodType } from '../../domain/parent.ts'
import type { ReportContext, ReportHighlight, ReportTargets } from '../../domain/reportHighlight.ts'
import { emptyReportTargets, reportTargets } from '../../domain/reportHighlight.ts'
import { parentApi } from '../../data/parent/api.ts'
import { useParentQuery, useParentMutation } from '../../data/parent/queries.ts'
import { ParentMemoryBooks } from './ParentMemoryBooks.tsx'
import { knownEntitlement, useChildEntitlement } from '../../data/payment/queries.ts'
import { thinkingLabels } from '../../domain/classroom.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { QueryStateNotice } from '../common/QueryStateNotice.tsx'
import { Modal } from '../shared/ClassroomParts.tsx'
import { EvidenceQuery } from './ParentConversation.tsx'
import { ReportDialogNavigation } from './ReportDialogNavigation.tsx'
import { useReportDialogHistory } from './useReportDialogHistory.ts'
import { WeeklyReportOverview } from './WeeklyReportOverview.tsx'
import { WeeklyReportDialog } from './WeeklyReportDialog.tsx'
import { weeklyActivities, weeklyCategories, type WeeklyReportView } from '../../domain/weeklyReportNavigation.ts'
import './report-reader.css'

// Preview is local-only. No example records or mock handlers enter the production bundle.
const ReportExamplePreview = import.meta.env.DEV ? lazy(() => import('./ReportExamplePreview.tsx')) : null

export function ParentReports({
  child,
  onAskReport, highlight, revealToken = 0, onReportChange,
}: {
  child: Child
  highlight?: ReportHighlight | null
  revealToken?: number
  onReportChange?: () => void
  onAskReport: (report: ReportContext) => void
}) {
  const [params, setParams] = useSearchParams()
  const [exampleOpen, setExampleOpen] = useState(false)
  const [dismissedReveal, setDismissedReveal] = useState(0)
  const [today] = useState(() => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul' }).format(new Date()))
  const reports = useParentQuery(['reports', child.id, 'COMPLETED', ''], signal => parentApi.reports(child.id, 'COMPLETED', signal))
  const items = reports.error ? [] : (reports.data?.items ?? [])
    .filter(item => item.childId === child.id && item.status === 'COMPLETED')
    .sort((a, b) => b.period.to.localeCompare(a.period.to))
  const selected = highlight?.childId === child.id && revealToken > dismissedReveal ? highlight : undefined
  const linked = items.find(item => item.reportId === params.get('reportId'))
  const weekly = items.filter(item => reportPeriodType(item) === 'WEEKLY' && item.period.from <= today)
  const active = linked ?? items.find(item => item.reportId === selected?.reportId)
    ?? weekly.find(item => item.period.to >= today) ?? weekly[0] ?? items[0]
  const revision = Number(params.get('revision'))
  const activeRevision = selected && selected.reportId === active?.reportId ? selected.revision
    : linked && Number.isSafeInteger(revision) && revision > 0 ? revision : active?.revision

  function chooseReport(reportId: string) {
    const next = new URLSearchParams(params)
    next.set('reportId', reportId)
    next.delete('revision')
    if (next.get('view') === 'reports') next.delete('view')
    setDismissedReveal(revealToken)
    onReportChange?.()
    setParams(next)
  }

  return <>
    <div className="parent-report-entry"><h2>{child.nickname}의 학습 리포트</h2>
      {ReportExamplePreview && <button type="button" className="cj-secondary" aria-haspopup="dialog" onClick={() => setExampleOpen(true)}>주간 리포트 예시 보기</button>}
    </div>
    {exampleOpen && ReportExamplePreview && <Modal title="주간 리포트 예시" onClose={() => setExampleOpen(false)} scrollIndicator>
      <Suspense fallback={<p role="status">리포트 예시를 불러오고 있어요.</p>}><ReportExamplePreview /></Suspense>
    </Modal>}
    <QueryFeedback query={reports} />
    {active ? (
      <div className="report-explorer parent-report-inline" aria-label="리포트 내용" role="region">
        <ReportDetail
          key={active.reportId}
          child={child}
          id={active.reportId}
          revision={activeRevision}
          highlight={selected?.reportId === active.reportId ? selected : undefined}
          revealToken={revealToken}
          onAskReport={onAskReport}
          periodPicker={<ReportPeriodPicker items={items} selected={active} onSelect={chooseReport} />}
        />
      </div>
    ) : reports.data && !reports.error && <p>아직 볼 수 있는 리포트가 없습니다.</p>}
    <ParentMemoryBooks child={child} />
  </>
}

function narrativeParagraphs(text: string) {
  const paragraphs = text.trim().split(/\n\s*\n/)
  if (paragraphs.length > 1) return paragraphs
  const sentences = Array.from(new Intl.Segmenter('ko', { granularity: 'sentence' }).segment(text), item => item.segment)
  if (sentences.length <= 3) return paragraphs
  return Array.from({ length: Math.floor(sentences.length / 2) }, (_, index) => {
    const start = index * 2
    const end = index === Math.floor(sentences.length / 2) - 1 ? sentences.length : start + 2
    return sentences.slice(start, end).join('').trim()
  })
}

function periodLabel(report: ReportItem) {
  return reportPeriodType(report) === 'DAILY' ? report.period.from : `${report.period.from} ~ ${report.period.to}`
}

function ReportPeriodPicker({ items, selected, onSelect }: {
  items: ReportItem[]
  selected: ReportItem
  onSelect: (id: string) => void
}) {
  const reportType = reportPeriodType(selected)
  const [kind, setKind] = useState<ReportPeriodType>(reportType)
  const picker = useRef<HTMLDetailsElement>(null)
  const trigger = useRef<HTMLElement>(null)
  const choices = items.filter(item => reportPeriodType(item) === kind)
  useEffect(() => {
    function dismiss(event: PointerEvent) {
      if (picker.current?.open && event.target instanceof Node && !picker.current.contains(event.target)) {
        picker.current.open = false
      }
    }
    document.addEventListener('pointerdown', dismiss)
    return () => document.removeEventListener('pointerdown', dismiss)
  }, [])
  return <div className="report-period-heading">
    <details className="report-period-picker" ref={picker} onKeyDown={event => {
      if (event.key !== 'Escape' || !picker.current?.open) return
      event.stopPropagation()
      picker.current.open = false
      trigger.current?.focus()
    }}>
      <summary ref={trigger} onClick={() => {
        if (!picker.current?.open) setKind(reportType)
      }}>
        <h2>
          {reportType === 'DAILY' ? '일일 리포트' : '주간 리포트'}
          <ChevronDown size={18} aria-hidden="true" />
        </h2>
      </summary>
      <div className="report-period-popover" aria-label="리포트 기간 선택">
        <div className="report-period-types" role="group" aria-label="리포트 종류">
          {(['WEEKLY', 'DAILY'] as const).map(type => (
            <button key={type} type="button" aria-pressed={kind === type} onClick={() => setKind(type)}>
              {type === 'WEEKLY' ? '주간' : '일일'}
            </button>
          ))}
        </div>
        {choices.length ? <ul className="report-period-dates" aria-label="리포트 일자">
          {choices.map(item => <li key={item.reportId}>
            <button type="button" aria-current={item.reportId === selected.reportId ? 'date' : undefined}
              onClick={() => {
                if (picker.current) picker.current.open = false
                trigger.current?.focus()
                if (item.reportId !== selected.reportId) onSelect(item.reportId)
              }}>{periodLabel(item)}</button>
          </li>)}
        </ul> : <p>볼 수 있는 {kind === 'WEEKLY' ? '주간' : '일일'} 리포트가 없습니다.</p>}
      </div>
    </details>
    <p>{periodLabel(selected)}</p>
  </div>
}

function ReportDetail({
  child,
  id,
  revision,
  onAskReport, highlight, revealToken = 0, periodPicker,
}: {
  child: Child
  highlight?: ReportHighlight | null
  revealToken?: number
  id: string
  revision: number | undefined
  periodPicker: ReactNode
  onAskReport: (report: ReportContext) => void
}) {
  const q = useParentQuery(
      ['report', child.id, id, revision ?? 'latest'],
      (signal) => parentApi.report(id, child.id, revision, signal),
      true,
      true,
    ),
    // 이용권은 entitlement로만 판단한다(#602). 조회 전·실패면 서버가 내려준 리포트 내용을 그대로 쓴다.
    entitlement = knownEntitlement(useChildEntitlement(child.id)),
    conversationOff = entitlement?.conversationEnabled === false,
    download = useParentMutation(() => parentApi.download(id, 'pdf')),
    [proof, setProof] = useState<string | null>(null),
    [notice, setNotice] = useState('')
  const r = q.error ? undefined : q.data,
    ready = r?.status === 'COMPLETED',
    daily = !!r && reportPeriodType(r) === 'DAILY'
  const panel = useRef<HTMLElement>(null), lastReveal = useRef(0)
  const targets = useMemo(() => r ? reportTargets(r, highlight) : emptyReportTargets(), [r, highlight])
  const additionalDailyMetrics = r?.metrics.map((metric, index) => ({ metric, index })).filter(({ metric }) => metric.label !== '완료한 활동') ?? []
  const additionalDailyHighlights = additionalDailyMetrics.flatMap((entry, index) => targets.metrics.includes(entry.index) ? [index] : [])
  const [recordSelection, setRecordSelection] = useState<(DailyActivitySelection & { revision: number; reportId: string }) | null>(null)
  const [weeklyChoice, setWeeklyChoice] = useState<WeeklyReportView | null>(null)
  const [dismissedWeeklyHighlight, setDismissedWeeklyHighlight] = useState(0)
  const highlightedAttempt = r?.changes[targets.changes[0]]?.attemptId ?? r?.reflections[targets.reflections[0]]?.attemptId ?? r?.quotes[targets.quotes[0]]?.attemptId
  const highlightedCategory = r && (highlightedAttempt ? weeklyCategories(r).find(item => item.ids.includes(highlightedAttempt))?.key
    : targets.metrics.length ? 'metrics' : r.thinkingTypes[targets.thinking[0]]?.type)
  const weeklySelection = weeklyChoice ?? (!daily && ready && highlight && revealToken > dismissedWeeklyHighlight && highlightedCategory
    ? { category: highlightedCategory, attemptId: highlightedAttempt ?? null } : null)
  function setWeeklySelection(value: WeeklyReportView | null) {
    setDismissedWeeklyHighlight(revealToken)
    setWeeklyChoice(value)
  }
  function openActivities(selection: DailyActivitySelection) {
    if (!r) return
    setRecordSelection({ ...selection, revision: r.revision, reportId: r.reportId })
  }
  const matched = Object.values(targets).reduce((total, values) => total + values.length, 0)
  useEffect(() => {
    if (!highlight || !ready || !matched) return
    const first = Array.from(panel.current?.querySelectorAll<HTMLElement>('[data-answer-highlight="true"]') ?? []).find(element => !element.closest('[hidden]'))
    if (!first) return
    const behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
    if (revealToken > lastReveal.current) first.scrollIntoView({ block: 'center', behavior })
    // 리포트를 렌더링한 뒤 질문에 연결된 근거로 초점을 이동한다.
    const frame = revealToken > lastReveal.current
      ? requestAnimationFrame(() => { if (first.isConnected) first.focus({ preventScroll: true }) })
      : undefined
    lastReveal.current = revealToken
    return () => { if (frame !== undefined) cancelAnimationFrame(frame) }
  }, [highlight, ready, matched, targets, revealToken, weeklySelection?.category, weeklySelection?.attemptId])
  async function downloadReport() {
    setNotice('')
    try {
      const data = await download.mutateAsync(undefined)
      const url = new URL(data.url, location.href)
      if (!['http:', 'https:'].includes(url.protocol))
        throw new Error('허용되지 않은 다운로드 주소입니다.')
      if (Date.parse(data.expiresAt) <= Date.now())
        throw new Error('다운로드 주소가 만료되었습니다.')
      window.location.assign(url.href)
    } catch (e) {
      setNotice(e instanceof Error ? e.message : '파일을 받지 못했습니다.')
    }
  }
  const proofDialog = proof && r ? (
    <Modal title="리포트 항목 내용" scrollIndicator onClose={() => setProof(null)}>
      <EvidenceQuery reportLayout queryKey={['report-evidence', child.id, id, proof]}
        load={(signal) => parentApi.reportEvidence(id, proof, signal)} />
    </Modal>
  ) : null
  return (
    <section className="ws-card report-detail" data-period-type={daily ? 'DAILY' : 'WEEKLY'} ref={panel}>
      <header className="report-toolbar">
        {periodPicker}
        <div className="report-toolbar-actions">
          {ready && <button className="cj-secondary" onClick={() => daily ? openActivities({ indices: [] }) : setWeeklySelection({ category: null, attemptId: null })}>
            리포트 전체 보기
          </button>}
          {r && ready && (
            <button className="cj-secondary" disabled={conversationOff}
              title={conversationOff ? 'AI 질문은 프리미엄 기능입니다.' : undefined}
              onClick={() => onAskReport({ reportId: r.reportId, revision: r.revision, period: r.period, periodType: daily ? 'DAILY' : 'WEEKLY' })}>
              이 리포트로 질문하기
            </button>
          )}
          {r && ready && (
            <button className="cj-primary" disabled={download.isPending}
              onClick={() => void downloadReport()}>
              {download.isPending ? '다운로드 준비 중' : '리포트 다운로드'}
            </button>
          )}
        </div>
      </header>
      <QueryFeedback query={q} />
      {highlight && r && <><p>선택한 질문 · {highlight.question}</p><p role="status" className="report-highlight-summary">{matched
        ? `선택한 답변과 연결된 ${matched}개 항목을 초록 테두리로 표시했습니다.`
        : '이 답변과 직접 연결된 항목을 리포트에서 찾지 못했습니다.'}</p></>}
      {r && (
        <>
          {r.correctionNotice && (
            <p role="note">이 리포트에 쓰인 판정 중 일부가 리포트를 만든 뒤 정정되었습니다. 리포트 내용은 만들어진 때 그대로입니다.</p>
          )}
          {!ready ? <p>이 기간에 볼 수 있는 리포트가 없습니다.</p> : (
            <div className="report-body">
              <QueryStateNotice state={r.state} />
              {daily ? <section className="daily-report-overview" aria-label="일일 학습 요약">
                <DailyReportSummary report={r} highlighted={targets.metrics.some(index => r.metrics[index]?.label === '완료한 활동')} onOpenActivities={openActivities} />
                {additionalDailyMetrics.length > 0 && <details className="report-inclusion" open={additionalDailyHighlights.length > 0 || undefined}><summary>추가 학습 수치</summary>
                  <ReportMetricCounts metrics={additionalDailyMetrics.map(entry => entry.metric)} highlighted={additionalDailyHighlights} onProof={setProof} />
                </details>}
                <details className="report-inclusion"><summary>집계 기준</summary><p>{r.inclusionRule}</p><p>판정과 생각 요소는 그날 답변의 기록이며, 아이의 능력 점수가 아니에요.</p></details>
              </section> : <div className="weekly-report-overview">
                {!daily && (r.narrative ? (
                  <section className="report-data-group report-narrative-panel">
                    <h3>한 주의 기록</h3>
                    <div className="report-narrative-text">
                      <p>{narrativeParagraphs(r.narrative.text)[0]}</p>
                    </div>
                    <button className="cj-secondary" onClick={() => setWeeklySelection({ category: 'narrative', attemptId: null })}>한 주의 기록 읽기</button>
                  </section>
                ) : entitlement?.narrativeEnabled === false ? (
                  <PremiumPreview childId={child.id} />
                ) : (
                  null
                ))}
                <WeeklyReportOverview report={r} highlighted={targets.metrics} thinkingHighlights={targets.thinking} onProof={setProof}
                  onCategory={category => setWeeklySelection({ category, attemptId: null })}
                  theme={r.themeSummary ? <><ThemeSummaryView summary={r.themeSummary} /><button className="cj-secondary" onClick={() => setWeeklySelection({ category: 'theme', attemptId: null })}>테마 기록 보기</button></> : undefined} />
                <nav className="weekly-record-links" aria-label="주간 기록 바로가기">
                  {weeklyCategories(r).filter(item => item.kind === 'record').map(item => {
                    const Icon = item.key === 'explanations' ? TextSearch : item.key === 'reflections' ? NotebookPen : GitCompareArrows
                    return <button key={item.key} aria-label={`${item.label} ${item.ids.length}개`} disabled={!item.ids.length} onClick={() => setWeeklySelection({ category: item.key, attemptId: null })}><Icon className="weekly-record-icon" size={21} aria-hidden="true" /><span className="weekly-record-name">{item.label}</span><span className="weekly-record-count"><strong>{item.ids.length}</strong>개</span><ChevronRight size={18} aria-hidden="true" /></button>
                  })}
                  <button onClick={() => setWeeklySelection({ category: 'metrics', attemptId: null })}><ChartNoAxesColumnIncreasing className="weekly-record-icon" size={21} aria-hidden="true" /><span className="weekly-record-name">학습 수치 전체 보기</span><span className="weekly-record-count"><strong>{r.metrics.length}</strong>항목</span><ChevronRight size={18} aria-hidden="true" /></button>
                  {r.eveningQuestion && !r.narrative && <button onClick={() => setWeeklySelection({ category: 'narrative', attemptId: null })}>이번 주 저녁 질문<ChevronRight size={16} aria-hidden="true" /></button>}
                </nav>
                {entitlement?.narrativeEnabled !== false && !reportExplanationItems(r).length &&
                  <ReportExplanations report={r} studentName={child.nickname} narrativeEnabled={entitlement?.narrativeEnabled} />}
              </div>}
            </div>
          )}
        </>
      )}
      {notice && <p role="status">{notice}</p>}
      {r && daily && ready && recordSelection?.reportId === r.reportId && recordSelection.revision === r.revision ? (
        <DailyProblemsDialog key={`${r.reportId}-${r.revision}`} report={r} selection={recordSelection} highlighted={targets.problems}
          onProof={setProof} onClose={() => { setRecordSelection(null); setProof(null) }}>
          {proofDialog}
        </DailyProblemsDialog>
      ) : r && !daily && ready && weeklySelection ? <WeeklyReportDialog key={`${r.reportId}-${r.revision}-${weeklySelection.category}-${weeklySelection.attemptId}`} report={r} initial={weeklySelection} onClose={() => { setWeeklySelection(null); setProof(null) }}
        renderActivity={attemptId => <WeeklyActivityRecords report={r} selectedId={attemptId} studentName={child.nickname} targets={targets} onProof={setProof} narrativeEnabled={entitlement?.narrativeEnabled} />}
        metrics={<section className="report-stat-panel"><ReportMetricCounts metrics={r.metrics} highlighted={targets.metrics} onProof={setProof} /><details className="report-inclusion"><summary>집계 기준</summary><p>{r.inclusionRule}</p></details></section>}
        theme={r.themeSummary ? <ThemeSummaryView summary={r.themeSummary} /> : undefined}>
        {proofDialog}
      </WeeklyReportDialog> : proofDialog}
    </section>
  )
}

/**
 * 무료 주간 리포트의 프리미엄 칸 미리보기(P13, #998). 제목과 한 줄 설명만 보이고 내용은 요청하지 않는다.
 * 누르면 이용권·결제 화면의 비교표(`#plan-compare`)로 간다.
 */
function PremiumPreview({ childId }: { childId: string }) {
  const to = `/parent/billing?${new URLSearchParams({ childId })}#plan-compare`
  return (
    <section className="report-data-group report-premium-preview" aria-labelledby="report-premium-preview-title">
      <h3 id="report-premium-preview-title">프리미엄에서 더 볼 수 있어요</h3>
      <ul>
        <li><Link to={to}><Lock size={18} aria-hidden="true" /><span><strong>한 주의 기록</strong><span>한 주 동안의 활동을 글로 정리해 드려요.</span></span><em>프리미엄</em></Link></li>
        <li><Link to={to}><Lock size={18} aria-hidden="true" /><span><strong>이번 주 저녁 질문</strong><span>아이와 저녁에 함께 나눌 질문을 드려요.</span></span><em>프리미엄</em></Link></li>
      </ul>
      <Link className="cj-secondary" to={to}>무료와 프리미엄 비교 보기</Link>
    </section>
  )
}

const judgmentLabels: Record<NonNullable<DailyProblem['judgment']>, string> = {
  CORRECT: '맞게 썼어요',
  PARTIAL: '일부 확인',
  RETHINK: '다시 생각해 보기',
  HELD: '판정 보류',
}

/** 일일 리포트(P24): 테마(또는 추가 문제) → 문제 목록 → 상세 기록. */
type DailyDialogView = { groupKey: string | null; problemIndex: number | null; filtered: boolean }

function DailyProblemsDialog({ report, selection, highlighted, onProof, onClose, children }: {
  report: WeeklyReport; selection: DailyActivitySelection; highlighted: number[]
  onProof: (itemId: string) => void; onClose: () => void; children: ReactNode
}) {
  const groups = dailyReportGroups(report)
  const selectedIndices = [...new Set(selection.indices)].filter(index => report.problems?.[index])
  const initialIndex = selectedIndices[0] ?? null
  const initialGroup = groups.find(g => initialIndex !== null && g.indices.includes(initialIndex))
  const initialRoot: DailyDialogView = { groupKey: null, problemIndex: null, filtered: !selection.direct && selectedIndices.length > 0 }
  // Direct problem links retain their parent path so the back arrow reaches the theme list.
  const history = useReportDialogHistory<DailyDialogView>(initialGroup ? [initialRoot,
    { ...initialRoot, groupKey: initialGroup.key },
    { ...initialRoot, groupKey: initialGroup.key, problemIndex: initialIndex },
  ] : [initialRoot], (a, b) => a.groupKey === b.groupKey && a.problemIndex === b.problemIndex && a.filtered === b.filtered)
  const { filtered, groupKey, problemIndex } = history.current
  const group = groups.find(g => problemIndex !== null ? g.indices.includes(problemIndex) : g.key === groupKey)
  const visibleIndices = (indices: number[]) => filtered ? indices.filter(i => selectedIndices.includes(i)) : indices
  const visibleGroups = groups.filter(g => g.story || visibleIndices(g.indices).length > 0)
  const problem = problemIndex === null ? undefined : report.problems?.[problemIndex]
  const selectedPosition = problemIndex === null ? -1 : selectedIndices.indexOf(problemIndex)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      heading.current?.focus({ preventScroll: true })
      heading.current?.scrollIntoView({ block: 'nearest' })
    })
    return () => cancelAnimationFrame(frame)
  }, [group?.key, problemIndex, filtered])
  function root(clearFilter = false) {
    history.navigate({ groupKey: null, problemIndex: null, filtered: clearFilter ? false : filtered })
  }
  return <Modal title="일일 리포트 전체 보기" scrollIndicator onClose={onClose}>
    <div className="report-body daily-problems-dialog">
      <div className="report-dialog-topline"><ReportDialogNavigation {...history} /><p className="daily-problems-date">{report.period.from} · {report.problems?.length ?? 0}개 활동</p></div>
      <nav className="daily-report-path" aria-label="문제 탐색 경로">
        <button onClick={() => root()} aria-current={!group ? 'page' : undefined}>전체 리포트</button>
        {group && <><ChevronRight size={14} aria-hidden="true" /><button aria-current={!problem ? 'page' : undefined}
          onClick={() => history.navigate({ groupKey: group.key, problemIndex: null, filtered })}>{group.label}</button></>}
        {problem && <><ChevronRight size={14} aria-hidden="true" /><span aria-current="page">상세 기록</span></>}
      </nav>
      {filtered && <div className="daily-report-filter"><span>{selection.label ?? '선택한 활동'} · {selectedIndices.length}개 활동</span><button onClick={() => root(true)}>전체 문제 보기</button></div>}
      {filtered && problem && selectedPosition >= 0 && selectedIndices.length > 1 && <nav className="daily-matching-activities" aria-label="선택한 조건의 활동 이동">
        <button type="button" className="cj-secondary" disabled={selectedPosition === 0}
          onClick={() => history.navigate({ ...history.current, problemIndex: selectedIndices[selectedPosition - 1] })}>이전 활동</button>
        <span>{selectedPosition + 1} / {selectedIndices.length}</span>
        <button type="button" className="cj-secondary" disabled={selectedPosition === selectedIndices.length - 1}
          onClick={() => history.navigate({ ...history.current, problemIndex: selectedIndices[selectedPosition + 1] })}>다음 활동</button>
      </nav>}
      <header className="report-reader-heading">
        <BookOpen size={26} aria-hidden="true" />
        <h3 className="daily-navigation-heading" tabIndex={-1} ref={heading}>{problem ? problem.title : group ? group.label : '테마와 추가 문제'}</h3>
      </header>
        {!group ? <>
            <ul className="daily-navigation-list daily-story-list" aria-label="테마별 문제 수">{visibleGroups.map(g => <li key={g.key}>
              <button className="daily-navigation-row" data-daily-group={g.key} data-daily-story={g.story || undefined}
                disabled={visibleIndices(g.indices).length === 0} onClick={() => history.navigate({ groupKey: g.key, problemIndex: null, filtered })}>
                <strong>{g.label}</strong><span className="daily-navigation-count">{visibleIndices(g.indices).length}개{filtered && ` / 전체 ${g.indices.length}개`}</span><ChevronRight size={16} aria-hidden="true" />
              </button>
            </li>)}</ul>
          {!report.problems?.length && <p>이날은 기록이 없습니다.</p>}
          {visibleGroups.some(g => g.key === 'unclassified') && <p className="daily-unclassified-note">이야기 테마를 확인할 수 없는 문제는 ‘테마 미분류 기록’에서 볼 수 있어요.</p>}
        </> : problem && problemIndex !== null ? <DailyProblems completedDate={report.period.from} problems={[problem]} indices={[problemIndex]}
          highlighted={highlighted} onProof={onProof} /> : <>
          <p className="daily-navigation-help">{visibleIndices(group.indices).length}개 문제</p>
          <ul className="daily-navigation-list">{visibleIndices(group.indices).map(index => {
            const p = report.problems![index]
            return <li key={index}><button className="daily-navigation-row" data-daily-problem-link={index} onClick={() => history.navigate({ groupKey: group.key, problemIndex: index, filtered })}>
              <strong>{p.title}</strong><span>{p.judgment ? judgmentLabels[p.judgment] : '판정 없음'}</span><ChevronRight size={16} aria-hidden="true" />
            </button></li>
          })}</ul>
        </>}
      {children}
    </div>
  </Modal>
}

function DailyProblems({ completedDate, problems, onProof, highlighted, indices }: { completedDate: string; problems: DailyProblem[]; onProof: (itemId: string) => void; highlighted: number[]; indices: number[] }) {
  if (!problems.length) return <p>이날은 기록이 없습니다.</p>
  return (
    <>
      {problems.map((p, offset) => {
        const i = indices[offset]
        return (
        <article className="report-answer-comparison report-reader-layout report-highlight-target" data-daily-problem-index={i} data-answer-highlight={highlighted.includes(i) ? 'true' : undefined} tabIndex={-1} key={`${p.missionId}-${p.attemptId ?? i}`}>
          <div className="report-reader-document">
          {scheduledDayLine(p, completedDate) && <p>{scheduledDayLine(p, completedDate)}</p>}
          <HighlightLabel active={highlighted.includes(i)} />
          <section className="report-final-answer">
            <h4>마지막 답</h4>
            {p.finalAnswer ? <blockquote>{p.finalAnswer}</blockquote>
              : <p className="report-reader-empty">리포트에 마지막 답변이 포함되지 않았어요.</p>}
          </section>
          {p.followups.length > 0 && <section className="report-reader-followups"><h4>되묻기와 답변</h4>{p.followups.map((f, j) => (
            <div className="report-followup" key={j}>
              <div className="report-followup-question"><span className="report-step-label">되묻기 {j + 1}</span><p>{f.question}</p></div>
              <div className="report-student-response"><span className="report-response-label">아이의 답변</span>
                <blockquote data-empty={!f.answer || undefined}>{f.answer ?? '보완 답변 없음'}</blockquote>
              </div>
            </div>
          ))}</section>}
          {!p.itemId && <p className="report-reader-empty">이 문제에는 연결된 원문 근거가 없습니다.</p>}
          {p.itemId && <button className="cj-secondary" onClick={() => onProof(p.itemId!)}>내용</button>}
          </div>
          <aside className="report-reader-feedback" aria-label="판정과 돌아보기">
          <section className="report-reader-panel">
            <h4>판정 결과</h4>
            <p className="report-reader-verdict" data-judgment={p.judgment ?? 'UNKNOWN'}>{p.judgment ? judgmentLabels[p.judgment] : '판정 없음'}</p>
          </section>
          <section className="report-reader-panel">
            <h4>확인된 생각 요소</h4>
            {p.elements.some(e => e.satisfied) ? <ul className="report-reader-elements">{p.elements.filter(e => e.satisfied).map((e, index) => <li key={`${e.label}-${index}`}>{e.label}</li>)}</ul> : <p className="report-reader-empty">확인된 요소 없음</p>}
          </section>
          <section className="report-reflection-note report-reader-panel">
            <h4>돌아보기</h4>
            {p.reflection?.written && difficultyText(p.reflection.difficulty) && <span className="report-difficulty" data-difficulty={difficultyText(p.reflection.difficulty)}>{difficultyText(p.reflection.difficulty)}</span>}
            <p>{p.reflection?.written ? p.reflection.text || '작성함' : '쓰지 않음'}</p>
          </section>
          {/* P28: 기록된 생각·작성 시간만 보여 준다. */}
          {!!p.answerTimes?.length && <section className="report-reader-panel"><h4>풀이 기록</h4>{p.answerTimes.map(t => <p key={t.version}>{answerTimeLine(t)}</p>)}</section>}
          </aside>
        </article>
      )})}
      <small>판정 결과는 그날 기록이며 능력 점수가 아닙니다.</small>
    </>
  )
}

/** 주간 리포트의 테마 요약(FN-RPT-17). */
function ThemeSummaryView({ summary }: { summary: ThemeSummary }) {
  return (
    <>
      <h3>이번 주 테마</h3>
      {summary.state === 'NO_RECORD' || !summary.title ? (
        <p>이번 주에는 주간 테마에 참여한 기록이 없습니다.</p>
      ) : (
        <>
          <p>
            {summary.title} · {(summary.finished ?? summary.completed) ? '완주' : '진행'}
          </p>
          <ul className="weekly-theme-days">
            {summary.days.map((d) => (
              <li key={d.day} data-completed={d.completedInWeek ?? d.completed}>
                <span>{({ MON: '월', TUE: '화', WED: '수', THU: '목', FRI: '금' } as Record<string, string>)[d.day] ?? d.day}</span>
                <span>{d.title ?? '문제'}</span><span>{d.completed ? '마침' : d.completedInWeek ? '나중에 마침' : '마치지 않음'}</span>
              </li>
            ))}
          </ul>
          {summary.reviewRetries.length > 0 && <p>주말 다시 풀기 {summary.reviewRetries.length}개</p>}
        </>
      )}
    </>
  )
}

function ReportMetricCounts({ metrics, highlighted, onProof }: {
  metrics: (Metric & { itemId?: string })[]
  highlighted: number[]
  onProof: (id: string) => void
}) {
  const [page, setPage] = useState({ index: 0, highlight: '' })
  const highlight = highlighted.join(',')
  const pages = Math.max(1, Math.ceil(metrics.length / 6))
  const current = Math.min(pages - 1, highlight && page.highlight !== highlight ? Math.floor(highlighted[0] / 6) : page.index)
  if (!metrics.length) return <p>확인할 학습 수치가 없습니다.</p>
  return <>
    <dl className="report-count-list">{metrics.slice(current * 6, (current + 1) * 6).map((metric, offset) => {
      const index = current * 6 + offset
      const label = metric.label === '도움 없이 시작한 비율' ? '도움 없이 시작한 활동' : metric.label
      const active = highlighted.includes(index)
      return <div key={index} className="report-highlight-target" data-answer-highlight={active ? 'true' : undefined} tabIndex={-1}>
        <dt><HighlightLabel active={active}/>{label}</dt>
        <dd>
          <span>전체 {metric.denominator.toLocaleString()}건 중</span>{' '}
          <strong>{metric.numerator.toLocaleString()}건</strong>
          {metric.state === 'NO_RECORD' && <small>기록 없음</small>}
          <button type="button" className="report-metric-proof" aria-label={`${label} 내용 보기`}
            onClick={() => onProof(metric.itemId ?? `metric-${index}`)}>내용</button>
        </dd>
      </div>
    })}</dl>
    {pages > 1 && <nav className="report-metric-pages" aria-label="학습 수치 페이지">
      <span>전체 {metrics.length}항목</span>
      <button disabled={current === 0} onClick={() => setPage({ index: current - 1, highlight })}>이전</button>
      <span>{current + 1} / {pages}</span>
      <button disabled={current === pages - 1} onClick={() => setPage({ index: current + 1, highlight })}>다음</button>
    </nav>}
  </>
}

function WeeklyActivityRecords({ report: r, targets, onProof, narrativeEnabled, studentName, selectedId }: {
  report: WeeklyReport
  studentName: string
  targets: ReportTargets
  onProof: (id: string) => void
  narrativeEnabled?: boolean
  selectedId: string
}) {
  const explanations = useMemo(() => reportExplanationItems(r), [r])
  const activities = weeklyActivities(r)
  const id = selectedId
  const activity = activities.find(item => item.id === id)
  const changes = r.changes.map((value,index)=>({value,index})).filter(x=>x.value.attemptId===id)
  const reflections = r.reflections.map((value,index)=>({value,index})).filter(x=>x.value.attemptId===id)
  const quotes = r.quotes.map((value,index)=>({value,index})).filter(x=>x.value.attemptId===id && x.value.verified)
  const hasExplanation = explanations.some(item => item.attemptId === id)
  const hasFullOriginal = explanations.some(item => item.attemptId === id && item.itemId)
  const visibleQuotes = hasFullOriginal ? quotes.filter(({ index }) => targets.quotes.includes(index)) : quotes
  const explanation = <ReportExplanations report={r} attemptId={id} narrativeEnabled={narrativeEnabled} studentName={studentName} />
  return <section className="report-data-group weekly-activity-records" aria-label="활동별 기록">
    <div className="weekly-activity-layout">
      {hasExplanation && explanation}
      {activity && <div className="weekly-activity-pair">
        {(!hasFullOriginal || visibleQuotes.length > 0) && <section><h4>[답변 인용]</h4>{!visibleQuotes.length && <p className="weekly-record-empty">이 활동의 확인된 인용이 리포트에 포함되지 않았습니다.</p>}{visibleQuotes.map(({value:v,index:i})=><blockquote className="report-highlight-target" key={`${v.answerId}-${i}`} data-answer-highlight={targets.quotes.includes(i) ? 'true' : undefined} tabIndex={-1}><HighlightLabel active={targets.quotes.includes(i)}/>{v.text}</blockquote>)}</section>}
        <section><h4>[돌아보기]</h4>{!reflections.length && <p className="weekly-record-empty">이 활동의 돌아보기가 리포트에 포함되지 않았습니다.</p>}{reflections.map(({value:f,index:i})=><div className="report-highlight-target" key={i} data-answer-highlight={targets.reflections.includes(i) ? 'true' : undefined} tabIndex={-1}><HighlightLabel active={targets.reflections.includes(i)}/>{f.written ? <><span className="weekly-reflection-difficulty report-difficulty" data-difficulty={difficultyText(f.difficulty)}>{difficultyText(f.difficulty) || '난이도 미응답'}</span><p>{f.text || '달라진 점 미작성'}</p></> : <p>돌아보기 미작성</p>}</div>)}</section>
      </div>}
      {changes.map(({value:c,index:i})=><details className="report-answer-comparison report-highlight-target" open={targets.changes.includes(i) || undefined} data-answer-highlight={targets.changes.includes(i) ? 'true' : undefined} tabIndex={-1} key={c.attemptId}><summary>처음 답변과 보완 답변</summary><HighlightLabel active={targets.changes.includes(i)}/>{c.followup && <p>되묻기 · {c.followup}</p>}<div className="ws-grid report-change-pair"><div><h4>처음 답변</h4><blockquote>{c.first.text ?? '원문 없음'}</blockquote></div><div><h4>보완 답변</h4><blockquote>{c.revised.text ?? '원문 없음'}</blockquote></div></div><p>글자 수 {c.counts.chars.join(' → ')} · 문장 수 {c.counts.sentences.join(' → ')}</p><details><summary>변화 집계 상세</summary><p>까닭 연결어 수 {c.counts.reasonConnectives.join(' → ')}</p><small>실제로 센 글의 변화이며 사고력 향상으로 단정하지 않습니다.</small></details><button className="cj-secondary" onClick={()=>onProof(c.itemId ?? c.attemptId)}>전후 변화 내용</button></details>)}
      {!hasExplanation && explanation}
    </div>
    <details className="weekly-thinking-summary" open={targets.thinking.length ? true : undefined}><summary>생각 유형별 활동 전체 보기</summary>{r.thinkingTypes.map((t,i)=><p className="report-highlight-target" data-answer-highlight={targets.thinking.includes(i) ? 'true' : undefined} tabIndex={-1} key={t.type}><HighlightLabel active={targets.thinking.includes(i)}/>{thinkingLabels[t.type]} · {t.state==='NO_RECORD' ? '미관찰 · 확인된 기록 없음' : t.summary ?? `${t.missions.length}개 미션`}</p>)}</details>
  </section>
}

function HighlightLabel({ active }: { active: boolean }) {
  return active ? <span className="report-highlight-label">선택한 답변의 근거</span> : null
}
