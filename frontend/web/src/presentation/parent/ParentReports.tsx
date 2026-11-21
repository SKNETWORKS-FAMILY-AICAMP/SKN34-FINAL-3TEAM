import { DateFilter } from './ActivityExplorer.tsx'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { ArrowLeft, ArrowUpRight, Files } from 'lucide-react'
import { ReportProblem } from '../service/ReportProblem.tsx'
import { ReportExplanations } from './ReportExplanations.tsx'
import type { Child, Metric } from '../../domain/classroom.ts'
import { scheduledDayLine, answerTimeLine, difficultyText, type DailyProblem, type WeeklyReport, type ReportPeriodType, type ThemeSummary } from '../../domain/parent.ts'
import { reportPeriodType } from '../../domain/parent.ts'
import type { ReportContext, ReportHighlight, ReportTargets } from '../../domain/reportHighlight.ts'
import { emptyReportTargets, reportTargets } from '../../domain/reportHighlight.ts'
import { parentApi } from '../../data/parent/api.ts'
import { useParentQuery, useParentMutation } from '../../data/parent/queries.ts'
import { knownEntitlement, useChildEntitlement } from '../../data/payment/queries.ts'
import { thinkingLabels } from '../../domain/classroom.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { QueryStateNotice } from '../common/QueryStateNotice.tsx'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import { EvidenceQuery } from './ParentConversation.tsx'

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
  const [opened, setOpened] = useState(false)
  const [dismissedReveal, setDismissedReveal] = useState(0)
  const [dates,setDates] = useState<Partial<Record<ReportPeriodType,{from:string;to:string}>>>({})
  const [today] = useState(()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul'}).format(new Date()))
  const [calendar,setCalendar] = useState<ReportPeriodType|null>(null)
  const [pages, setPages] = useState({ WEEKLY: 0, DAILY: 0 })
  const [status, setStatus] = useState(''),
    [kind, setKind] = useState<ReportPeriodType | ''>(''),
    [revision, setRevision] = useState<number | undefined>(),
    list = useParentQuery(['reports', child.id, status, kind], (signal) =>
      parentApi.reports(child.id, status, signal, kind || undefined), true,
    )
  const matches = (item: {period:{from:string;to:string}}, type:ReportPeriodType) => !dates[type] || (item.period.from <= dates[type]!.to && item.period.to >= dates[type]!.from)
  const revealRequested = !!highlight && revealToken > dismissedReveal
  const selected = revealRequested ? highlight : undefined
  // Deep links can open only reports returned for the currently selected child.
  const requestedId = params.get('reportId')
  const linkedId = list.data?.items.find(item => item.reportId === requestedId && item.childId === child.id)?.reportId
  const activeId = linkedId ?? (revealRequested ? highlight?.reportId : undefined)
  const activeRevision = selected && selected.reportId === activeId ? selected.revision : revision
  const showModal = opened || !!linkedId || revealRequested
  const close = () => {
    setOpened(false); setDismissedReveal(revealToken); onReportChange?.(); setRevision(undefined)
    const next = new URLSearchParams(params); next.delete('reportId'); setParams(next, {replace:true})
  }
  return (
    <>
      <div className="parent-report-entry">
        <div><h2>학습 리포트</h2><p>하루의 학습과 한 주의 변화를 모아 볼 수 있어요.</p></div>
        <button className="parent-report-launcher" onClick={() => setOpened(true)}><Files size={24} aria-hidden="true" /><span><strong>리포트 자세히 보기</strong><small>일일·주간 리포트</small></span><ArrowUpRight size={20} aria-hidden="true" /></button>
      </div>
      {showModal && <Modal title={`${child.nickname}의 학습 리포트`} onClose={close}>
      <div className="report-explorer" data-detail={!!activeId}>
      {!activeId && <>
      <header className="parent-page-head"><h2>리포트</h2>
      <p>
        하루·한 주의 학습을 자동으로 정리한 결과입니다. 궁금한 점은 AI 챗봇에서 질문할 수 있습니다.
      </p>
      <p>일일 리포트는 매일 자정에 그날 기록으로, 주간 리포트는 일요일 자정에 한 주 기록으로 만들어집니다.</p></header>
      <div className="parent-report-filters"><label>
        리포트 종류{' '}
        <select aria-label="리포트 종류" value={kind} onChange={(e) => setKind(e.target.value as ReportPeriodType | '')}>
          <option value="">전체</option>
          <option value="DAILY">일일</option>
          <option value="WEEKLY">주간</option>
        </select>
      </label>{' '}
      <label>
        생성 상태{' '}
        <select aria-label="리포트 상태" value={status} onChange={(e) => { setStatus(e.target.value); setPages({ WEEKLY: 0, DAILY: 0 }) }}>
          <option value="">전체</option>
          {[
            ['RUNNING', '생성 중'],
            ['COMPLETED', '완료'],
            ['FAILED', '생성 실패'],
          ].map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
      </label>
      </div>
      <div className="parent-insights-report-body" tabIndex={0} role="region" aria-label="리포트 목록">
      <QueryFeedback query={list} />
      {list.data && !list.error && (
        <div className="parent-report-groups">
          {!list.data.items.length && <p>아직 생성된 리포트가 없습니다.</p>}
          {(['WEEKLY', 'DAILY'] as const).filter(type => !kind || type === kind).map(type => <section className="parent-report-group" key={type} aria-labelledby={`report-group-${type}`}>
            <h2 id={`report-group-${type}`}>{type === 'WEEKLY' ? '주간 리포트' : '일일 리포트'}</h2>
            <div className="report-date-controls"><button type="button" aria-expanded={calendar===type} onClick={()=>setCalendar(calendar===type ? null : type)}>{type==='WEEKLY' ? '주간 날짜 선택' : '일일 날짜 선택'}</button><span>{dates[type] ? `${dates[type]!.from} ~ ${dates[type]!.to}` : '전체 날짜'}</span>{dates[type] && <button type="button" onClick={()=>{setDates(d=>({...d,[type]:undefined}));setPages(p=>({...p,[type]:0}))}}>초기화</button>}</div>
            {calendar===type && <DateFilter embedded week={type==='WEEKLY'} initial={dates[type] ?? list.data.items.find(x=>reportPeriodType(x)===type)?.period ?? {from:today,to:today}} onCancel={()=>setCalendar(null)} onApply={value=>{setDates(d=>({...d,[type]:value}));setPages(p=>({...p,[type]:0}));setCalendar(null)}}/>}
            <div className="parent-report-grid">
          {list.data.items.filter(item => reportPeriodType(item) === type && matches(item,type)).slice(pages[type] * 6, (pages[type] + 1) * 6).map((r) => (
            <article className="ws-card" key={r.reportId}>

              <h3>{reportPeriodType(r) === 'DAILY' ? r.period.from : `${r.period.from} ~ ${r.period.to}`}</h3>
              <p>
                {r.status === 'COMPLETED'
                  ? '생성 완료'
                  : r.status === 'FAILED'
                    ? '생성 실패'
                    : '생성 중'}
              </p>
              <QueryStateNotice state={r.state} />
              <button
                className="cj-secondary"
                onClick={() => {
                  onReportChange?.()
                  setRevision(undefined)
                  const next = new URLSearchParams(params); next.set('reportId', r.reportId); setParams(next)
                  setOpened(true)
                }}
              >
                자세히 보기
              </button>
            </article>
          ))}
            </div>
            {list.data.items.filter(item => reportPeriodType(item) === type && matches(item,type)).length > 6 && <nav className="report-list-pages" aria-label={`${type === 'WEEKLY' ? '주간' : '일일'} 리포트 페이지`}>
              <button disabled={pages[type] === 0} onClick={() => setPages(p => ({...p, [type]: p[type] - 1}))}>이전</button>
              <span>{pages[type] + 1} / {Math.ceil(list.data.items.filter(item => reportPeriodType(item) === type && matches(item,type)).length / 6)}</span>
              <button disabled={(pages[type] + 1) * 6 >= list.data.items.filter(item => reportPeriodType(item) === type && matches(item,type)).length} onClick={() => setPages(p => ({...p, [type]: p[type] + 1}))}>다음</button>
            </nav>}
            {!list.data.items.some(item => reportPeriodType(item) === type && matches(item,type)) && <p>{type === 'WEEKLY' ? '주간' : '일일'} 리포트가 없습니다.</p>}
          </section>)}
        </div>
      )}
      </div>
      </>}
      {activeId && <div className="parent-report-detail-nav"><button className="parent-report-back" aria-label="리포트 목록으로 돌아가기" onClick={() => {
        onReportChange?.(); setDismissedReveal(revealToken); setOpened(true); setRevision(undefined)
        const next = new URLSearchParams(params); next.delete('reportId'); setParams(next)

      }}><ArrowLeft size={20} aria-hidden="true" />리포트 목록</button></div>}
      {activeId && (
        <div className="parent-insights-report-body" tabIndex={0} role="region" aria-label="리포트 내용">
        <ReportDetail
          key={activeId}
          child={child}
          id={activeId}
          revision={activeRevision}
          compact={false} highlight={highlight} revealToken={revealToken}
          onRevision={value => { setRevision(value); onReportChange?.() }}
          onAskReport={value => { close(); onAskReport(value) }}
        />
        </div>
      )}
      </div></Modal>}
    </>
  )
}
function ReportDetail({
  child,
  id,
  revision,
  onRevision,
  onAskReport, compact = false, highlight, revealToken = 0,
}: {
  child: Child
  compact?: boolean
  highlight?: ReportHighlight | null
  revealToken?: number
  id: string
  revision: number | undefined
  onRevision: (v: number | undefined) => void
  onAskReport: (report: ReportContext) => void
}) {
  const q = useParentQuery(
      ['report', child.id, id, revision ?? 'latest'],
      (signal) => parentApi.report(id, child.id, revision, signal),
      true,
      true,
    ),
    regenerate = useParentMutation(() => parentApi.regenerate(id)),
    // 이용권은 entitlement로만 판단한다(#602). 조회 전·실패면 서버가 내려준 리포트 내용을 그대로 쓴다.
    entitlement = knownEntitlement(useChildEntitlement(child.id)),
    conversationOff = entitlement?.conversationEnabled === false,
    download = useParentMutation((format: 'pdf' | 'md') => parentApi.download(id, format)),
    [proof, setProof] = useState<string | null>(null),
    [notice, setNotice] = useState('')
  const r = q.error ? undefined : q.data,
    ready = r?.status === 'COMPLETED',
    daily = !!r && reportPeriodType(r) === 'DAILY'
  const panel = useRef<HTMLElement>(null), lastReveal = useRef(0)
  const targets = useMemo(() => r ? reportTargets(r, highlight) : emptyReportTargets(), [r, highlight])
  const [selection, setSelection] = useState({ tab: 'summary', message: '' })
  const message = highlight?.messageId ?? ''
  const tab = message && selection.message !== message ? (targets.metrics.length ? 'summary' : 'records') : selection.tab
  const matched = Object.values(targets).reduce((total, values) => total + values.length, 0)
  useEffect(() => {
    if (!highlight || !ready || !matched) return
    const first = Array.from(panel.current?.querySelectorAll<HTMLElement>('[data-answer-highlight="true"]') ?? []).find(element => !element.closest('[hidden]'))
    if (!first) return
    const pane = compact ? panel.current?.closest<HTMLElement>('.parent-insights-report-body') : null
    const behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
    if (pane && window.matchMedia('(min-width:1101px)').matches) {
      pane.scrollTo({ top: pane.scrollTop + first.getBoundingClientRect().top - pane.getBoundingClientRect().top - 16, behavior })
    } else if (revealToken > lastReveal.current) first.scrollIntoView({ block: 'center', behavior })
    // 팝업의 초기 초점 설정이 끝난 뒤 선택한 근거로 이동한다.
    const frame = revealToken > lastReveal.current
      ? requestAnimationFrame(() => { if (first.isConnected) first.focus({ preventScroll: true }) })
      : undefined
    lastReveal.current = revealToken
    return () => { if (frame !== undefined) cancelAnimationFrame(frame) }
  }, [highlight, ready, matched, targets, revealToken, compact, tab])
  async function file(format: 'pdf' | 'md') {
    try {
      const data = await download.mutateAsync(format)
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
  return (
    <section className="ws-card report-detail" ref={panel}>
      <header className="report-document-header"><div><h2>{daily ? '일일 리포트' : '주간 리포트'}</h2>{r && <p>{r.period.from} ~ {r.period.to} · {r.revision}판</p>}</div><div className="report-header-actions">
      <ReportProblem targetType="REPORT" targetId={id}/>
      {!compact && r && ready && r.parentSharingEnabled !== false && (
        <div className="parent-report-question">
          {conversationOff && <p>AI 질문은 프리미엄 기능입니다.</p>}
          <button className="cj-primary" disabled={conversationOff} onClick={() => onAskReport({ reportId: r.reportId, revision: r.revision, period: r.period, periodType: daily ? 'DAILY' : 'WEEKLY' })}>이 리포트로 질문하기</button>
        </div>
      )}
      </div></header><QueryFeedback query={q} />
      {highlight && r && <><p>선택한 질문 · {highlight.question}</p><p role="status" className="report-highlight-summary">{matched
        ? `선택한 답변과 연결된 ${matched}개 항목을 초록 테두리로 표시했습니다.`
        : '이 답변과 직접 연결된 항목이 현재 리포트 판에는 없습니다.'}</p></>}
      {r && (
        <>
          {r.correctionNotice && (
            <p role="note">이 리포트에 쓰인 판정 중 일부가 리포트를 만든 뒤 정정되었습니다. 리포트 내용은 만들어진 때 그대로입니다.</p>
          )}
          {!compact && <label className="report-version-control">
            리포트 판{' '}
            <select
              aria-label="리포트 판"
              value={revision ?? 'latest'}
              onChange={(e) =>
                onRevision(e.target.value === 'latest' ? undefined : Number(e.target.value))
              }
            >
              <option value="latest">최신판</option>
              {r.revisions.map((v) => (
                <option key={v.revision} value={v.revision}>
                  {v.revision}판
                </option>
              ))}
            </select>
          </label>}
          {!ready ? (
            <p role="status">
              {r.status === 'FAILED'
                ? '리포트 생성에 실패했습니다. 기록 없음과는 다릅니다.'
                : '리포트를 생성하고 있습니다. 완료 전 내용을 표시하지 않습니다.'}
            </p>
          ) : (
            <>
              <nav className="report-sections" aria-label="리포트 상세 항목">
                {([['summary','요약'],['records','활동 기록'],['explanation','설명과 근거'],['files','파일·관리']] as const).filter(([key]) => !compact || key !== 'files').map(([key,label]) => <button key={key} type="button" aria-pressed={tab === key} onClick={() => setSelection({tab:key,message})}>{label}</button>)}
              </nav>
              <div className="report-section" hidden={tab !== 'summary'}><h3 className="report-chapter-title">학습 요약</h3>
              <details className="report-inclusion"><summary>집계 기준</summary><p>{r.inclusionRule}</p></details>
              <QueryStateNotice state={r.state} />
              {!daily && (r.narrative ? (
                <section className="report-data-group report-narrative-panel"><h4>한 주의 기록</h4>
                  <div className="report-narrative-text">{r.narrative.text}</div>
                  <details className="report-source"><summary>요약 출처</summary><p>{r.narrative.source}</p></details>
                </section>
              ) : (
                <p>{r.parentSharingEnabled === false ? '아이의 답변 원문이 비공개여서 서술과 인용을 표시하지 않습니다. 학습 수치는 아래에서 확인할 수 있습니다.' : '수치 리포트입니다. 이 자녀의 플랜에는 서술 요약이 포함되지 않습니다.'}</p>
              ))}
              <section className="report-data-group report-stat-panel"><h4>학습 수치</h4><ReportMetricCounts metrics={r.metrics} highlighted={targets.metrics} /></section>
              </div>
              <div className="report-section" hidden={tab !== 'explanation'}><h3 className="report-chapter-title">설명과 근거</h3>
              <ReportExplanations report={r} narrativeEnabled={entitlement?.narrativeEnabled} />
              <MetricEvidence metrics={r.metrics} disabled={r.parentSharingEnabled===false} onProof={setProof}/>

              </div>
              <div className="report-section" hidden={tab !== 'records'}>
              {daily && <DailyProblems completedDate={r.period.from} highlighted={targets.problems} problems={r.problems ?? []} canReadOriginals={r.parentSharingEnabled !== false} onProof={setProof} />}
              {!daily && r.parentSharingEnabled === false && <p>아이의 답변 원문이 비공개입니다. 요약에서 학습 수치를 확인할 수 있습니다.</p>}
              {!daily && r.themeSummary && <details className="report-theme-disclosure"><summary>이번 주 테마 보기</summary><ThemeSummaryView summary={r.themeSummary} /></details>}
              {!daily && entitlement?.narrativeEnabled !== false && r.parentSharingEnabled !== false && (
                <>
                  <WeeklyActivityRecords report={r} targets={targets} onProof={setProof} />
                  {r.eveningQuestion && (
                    <section className="report-data-group">
                      <h3>이번 주 저녁 질문</h3>
                      <p>{r.eveningQuestion}</p>
                    </section>
                  )}
                </>
              )}
              </div>
              {!compact && tab === 'files' && <p>{r.parentSharingEnabled === false ? '원문 비공개 중에는 기존 파일을 제공하지 않습니다. 위 학습 수치는 계속 확인할 수 있습니다.' : '다운로드는 서버가 제공하는 최신판 파일입니다.'}</p>}

            </>
          )}
          {!compact && tab === 'files' && <div className="parent-report-regenerate"><div className="parent-report-toolbar">{ready && <>                <button
                  className="cj-secondary"
                  disabled={download.isPending || r.parentSharingEnabled === false}
                  onClick={() => {
                    void file('pdf')
                  }}
                >
                  PDF 다운로드
                </button>
                <button
                  className="cj-secondary"
                  disabled={download.isPending || r.parentSharingEnabled === false}
                  onClick={() => {
                    void file('md')
                  }}
                >
                  Markdown 다운로드
                </button>
              </>}<button
            className="cj-secondary"
            disabled={regenerate.isPending || r.status === 'RUNNING' || r.status === 'QUEUED'}
            onClick={() => {
              void regenerate
                .mutateAsync(undefined)
                .then(() => {
                  onRevision(undefined)
                  setNotice('새 판 생성을 요청했습니다. 기존 판은 유지됩니다.')
                })
                .catch(() => {})
            }}
          >
            새 판으로 재생성
          </button></div>
          <p>학부모 재생성은 리포트당 한 번입니다. 이전 판은 유지됩니다.</p></div>}
        </>
      )}
      {r && ready && r.parentSharingEnabled === false && <p role="note">원문 비공개 중에는 원문 근거·AI 질문·파일 다운로드를 이용할 수 없습니다. 위 학습 수치는 계속 확인할 수 있습니다.</p>}
      {notice && <p role="status">{notice}</p>}
      <ErrorNotice error={regenerate.error} />
      <ErrorNotice error={download.error} />
      {proof && r && (
        <Modal title="리포트 항목 근거" onClose={() => setProof(null)}>
          <EvidenceQuery
            queryKey={['report-evidence', child.id, id, proof]}
            load={(signal) => parentApi.reportEvidence(id, proof, signal)}
          />
        </Modal>
      )}
    </section>
  )
}

const judgmentLabels: Record<NonNullable<DailyProblem['judgment']>, string> = {
  CORRECT: '맞게 썼어요',
  PARTIAL: '일부 확인',
  RETHINK: '다시 생각해 보기',
  HELD: '판정 보류',
}
const contextLabels: Record<NonNullable<DailyProblem['context']>, string> = {
  THEME_DAY: '주간 테마 오늘 문제',
  THEME_REVIEW: '되돌아보기 다시 풀기',
  EXTRA: '추가 문제',
}

/** 일일 리포트(P24): 그날 문제별 기록만 보여 준다. 서술·저녁 질문은 없다. */
function DailyProblems({ completedDate, problems, onProof, canReadOriginals, highlighted }: { completedDate: string; problems: DailyProblem[]; canReadOriginals: boolean; onProof: (itemId: string) => void; highlighted: number[] }) {
  if (!problems.length) return <p>이날은 기록이 없습니다.</p>
  return (
    <>
      <h3>그날 푼 문제</h3>
      {problems.map((p, i) => (
        <details className="report-answer-comparison report-highlight-target" open={highlighted.includes(i) || undefined} data-answer-highlight={highlighted.includes(i) ? 'true' : undefined} tabIndex={-1} key={`${p.missionId}-${p.attemptId ?? i}`}>
          <summary>{p.title}</summary>
          {scheduledDayLine(p, completedDate) && <p>{scheduledDayLine(p, completedDate)}</p>}
          <HighlightLabel active={highlighted.includes(i)} />

          <p>
            {p.context ? `${contextLabels[p.context]} · ` : ''}
            {p.judgment ? `판정 ${judgmentLabels[p.judgment]}` : '판정 없음'}
          </p>
          {/* P28: 생각·작성 시간은 원문이 아니라 원문 비공개여도 보인다. 시간 없는 답은 줄을 생략 */}
          {(p.answerTimes ?? []).map((t) => (
            <p key={t.version}>{answerTimeLine(t)}</p>
          ))}
          {p.followups.map((f, j) => (
            <div className="report-followup" key={j}>
              <div className="report-followup-question"><span className="report-step-label">되묻기 {j + 1}</span><p>{f.question}</p></div>
              <div className="report-student-response"><span className="report-response-label">아이의 답변</span>
                <blockquote data-empty={!canReadOriginals || !f.answer || undefined}>{canReadOriginals ? f.answer ?? '보완 답변 없음' : '아이가 답변 원문을 비공개로 두었어요.'}</blockquote>
              </div>
            </div>
          ))}
          {p.finalAnswer && (
            <section className="report-final-answer">
              <h4>마지막 답</h4>
              <blockquote>{p.finalAnswer}</blockquote>
            </section>
          )}
          {p.elements.length > 0 && (
            <p>
              확인된 생각 요소 · {p.elements.filter((e) => e.satisfied).map((e) => e.label).join(', ') || '없음'}
            </p>
          )}
          <section className="report-reflection-note">
            <h4>돌아보기</h4>
            {p.reflection?.written && p.reflection.difficulty && <span className="report-difficulty">{difficultyText(p.reflection.difficulty)}</span>}
            <p>{p.reflection?.written ? p.reflection.text || '작성함' : '쓰지 않음'}</p>
          </section>
          {p.attemptId && canReadOriginals && (
            <button className="cj-secondary" onClick={() => onProof(p.attemptId!)}>
              원문 근거
            </button>
          )}
        </details>
      ))}
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
            {summary.title} · {summary.completed ? '완주' : '진행'}
          </p>
          <ul>
            {summary.days.map((d) => (
              <li key={d.day}>
                {({ MON: '월', TUE: '화', WED: '수', THU: '목', FRI: '금' } as Record<string, string>)[d.day] ?? d.day} ·{' '}
                {d.title ?? '문제'} · {d.completed ? '마침' : '마치지 않음'}
              </li>
            ))}
          </ul>
          {summary.reviewRetries.length > 0 && <p>주말 다시 풀기 {summary.reviewRetries.length}개</p>}
        </>
      )}
    </>
  )
}

function ReportMetricCounts({metrics, highlighted}: {metrics: Metric[]; highlighted: number[]}) {
  const [page,setPage] = useState({index:0,highlight:''})
  const highlight=highlighted.join(',')
  const pages=Math.max(1,Math.ceil(metrics.length/6))
  const current=Math.min(pages-1,highlight && page.highlight!==highlight ? Math.floor(highlighted[0]/6) : page.index)
  return <><dl className="report-count-list">{metrics.slice(current*6,current*6+6).map((m,offset)=>{const i=current*6+offset;return <div key={i} className="report-highlight-target" data-answer-highlight={highlighted.includes(i) ? 'true' : undefined} tabIndex={-1}><dt><HighlightLabel active={highlighted.includes(i)}/>{m.label === '도움 없이 시작한 비율' ? '도움 없이 시작한 활동' : m.label}</dt><dd><span>전체 {m.denominator.toLocaleString()}건 중</span> <strong>{m.numerator.toLocaleString()}건</strong>{m.state === 'NO_RECORD' && <small>기록 없음</small>}</dd></div>})}</dl>{pages>1 && <nav className="report-metric-pages" aria-label="학습 수치 페이지"><span>전체 {metrics.length}항목</span><button type="button" disabled={current===0} onClick={()=>setPage({index:current-1,highlight})}>이전</button><span>{current+1} / {pages}</span><button type="button" disabled={current===pages-1} onClick={()=>setPage({index:current+1,highlight})}>다음</button></nav>}</>

}

function WeeklyActivityRecords({report:r, targets, onProof}: {report:WeeklyReport; targets:ReportTargets; onProof:(id:string)=>void}) {
  const activities = useMemo(() => {
    const ids = [...new Set([...r.changes.map(x=>x.attemptId), ...r.reflections.map(x=>x.attemptId), ...r.quotes.filter(x=>x.verified).map(x=>x.attemptId)])]
    return ids.map((id,index) => {
      const thinking = r.thinkingTypes.find(t=>t.missions.some(m=>m.attemptId===id))
      return {id,title:thinking?.missions.find(m=>m.attemptId===id)?.title ?? r.explanations?.items.find(x=>x.attemptId===id)?.missionTitle ?? `활동 ${index+1}`,type:thinking?.type}
    })
  },[r])
  const highlightedId = r.changes[targets.changes[0]]?.attemptId ?? r.reflections[targets.reflections[0]]?.attemptId ?? r.quotes[targets.quotes[0]]?.attemptId
  const [selection,setSelection] = useState({id:'',highlightedId:undefined as string|undefined})
  const id = highlightedId && selection.highlightedId !== highlightedId ? highlightedId : activities.some(a=>a.id===selection.id) ? selection.id : activities[0]?.id
  const activity = activities.find(a=>a.id===id)
  const category=activity?.type ?? 'OTHER'
  const visibleActivities=activities.filter(a=>(a.type ?? 'OTHER')===category)
  const changes = r.changes.map((value,index)=>({value,index})).filter(x=>x.value.attemptId===id)
  const reflections = r.reflections.map((value,index)=>({value,index})).filter(x=>x.value.attemptId===id)
  const quotes = r.quotes.map((value,index)=>({value,index})).filter(x=>x.value.attemptId===id && x.value.verified)
  return <section className="report-data-group weekly-activity-records"><h3>활동별 기록</h3>
    {!activities.length ? <p>이 리포트에 포함된 답변·돌아보기 기록이 없습니다.</p> : <>
      <label className="weekly-activity-picker">생각 활동 유형<select aria-label="주간 리포트 유형 선택" value={category} onChange={e=>setSelection({id:activities.find(a=>(a.type ?? 'OTHER')===e.target.value)!.id,highlightedId})}>{[...new Set(activities.map(a=>a.type ?? 'OTHER'))].map(type=><option key={type} value={type}>{thinkingLabels[type as keyof typeof thinkingLabels] ?? '기타 활동'}</option>)}</select></label>
      <label className="weekly-activity-picker">활동 선택<select aria-label="주간 리포트 활동 선택" value={id} onChange={e=>setSelection({id:e.target.value,highlightedId})}>{visibleActivities.map((a,i)=><option key={a.id} value={a.id}>{i+1}. {a.title}{a.type ? ` · ${thinkingLabels[a.type]}` : ''}</option>)}</select></label>
      <header className="weekly-activity-heading"><h4>{activity?.title}</h4><span>{activity?.type && thinkingLabels[activity.type]} · {visibleActivities.findIndex(a=>a.id===id)+1} / {visibleActivities.length}</span></header>
      {changes.map(({value:c,index:i})=><details className="report-answer-comparison report-highlight-target" open={targets.changes.includes(i) || undefined} data-answer-highlight={targets.changes.includes(i) ? 'true' : undefined} tabIndex={-1} key={c.attemptId}><summary>처음 답변과 보완 답변</summary><HighlightLabel active={targets.changes.includes(i)}/>{c.followup && <p>되묻기 · {c.followup}</p>}<div className="ws-grid report-change-pair"><div><h4>처음 답변</h4><blockquote>{c.first.text ?? '원문 없음'}</blockquote></div><div><h4>보완 답변</h4><blockquote>{c.revised.text ?? '원문 없음'}</blockquote></div></div><p>글자 수 {c.counts.chars.join(' → ')} · 문장 수 {c.counts.sentences.join(' → ')}</p><details><summary>변화 집계 상세</summary><p>까닭 연결어 수 {c.counts.reasonConnectives.join(' → ')}</p><small>실제로 센 글의 변화이며 사고력 향상으로 단정하지 않습니다.</small></details><button className="cj-secondary" onClick={()=>onProof(c.itemId ?? c.attemptId)}>전후 변화 근거</button></details>)}
      <div className="weekly-activity-pair"><section><h4>돌아보기</h4>{!reflections.length && <p className="weekly-record-empty">이 활동의 돌아보기가 리포트에 포함되지 않았습니다.</p>}{reflections.map(({value:f,index:i})=><div className="report-highlight-target" key={i} data-answer-highlight={targets.reflections.includes(i) ? 'true' : undefined} tabIndex={-1}><HighlightLabel active={targets.reflections.includes(i)}/>{f.written ? <><span className="weekly-reflection-difficulty">{difficultyText(f.difficulty) || '난이도 미응답'}</span><p>{f.text || '달라진 점 미작성'}</p></> : <p>돌아보기 미작성</p>}</div>)}</section>
      <section><h4>아이의 말</h4>{!quotes.length && <p className="weekly-record-empty">이 활동의 확인된 인용이 리포트에 포함되지 않았습니다.</p>}{quotes.map(({value:v,index:i})=><blockquote className="report-highlight-target" key={`${v.answerId}-${i}`} data-answer-highlight={targets.quotes.includes(i) ? 'true' : undefined} tabIndex={-1}><HighlightLabel active={targets.quotes.includes(i)}/>{v.text}</blockquote>)}</section></div>
    </>}
    <details className="weekly-thinking-summary" open={targets.thinking.length ? true : undefined}><summary>생각 유형별 활동 전체 보기</summary>{r.thinkingTypes.map((t,i)=><p className="report-highlight-target" data-answer-highlight={targets.thinking.includes(i) ? 'true' : undefined} tabIndex={-1} key={t.type}><HighlightLabel active={targets.thinking.includes(i)}/>{thinkingLabels[t.type]} · {t.state==='NO_RECORD' ? '미관찰 · 확인된 기록 없음' : t.summary ?? `${t.missions.length}개 미션`}</p>)}</details>
  </section>
}

function HighlightLabel({ active }: { active: boolean }) {
  return active ? <span className="report-highlight-label">선택한 답변의 근거</span> : null
}

function MetricEvidence({metrics,disabled,onProof}:{metrics:(Metric & {itemId?:string})[];disabled:boolean;onProof:(id:string)=>void}) {
 const [index,setIndex]=useState(0)
 const current=Math.min(index,Math.max(0,metrics.length-1))
 return <section className="report-evidence-selector"><h4>학습 수치의 근거</h4>{metrics.length ? <div><label>항목<select aria-label="근거 항목 선택" value={current} onChange={e=>setIndex(Number(e.target.value))}>{metrics.map((m,i)=><option key={i} value={i}>{m.label}</option>)}</select></label><button className="cj-secondary" disabled={disabled} onClick={()=>onProof(metrics[current].itemId ?? `metric-${current}`)}>근거 보기</button></div> : <p>확인할 학습 수치가 없습니다.</p>}</section>
}
