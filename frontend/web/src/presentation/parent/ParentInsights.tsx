import './parent-insights.css'
import { ArrowLeft, CalendarDays } from 'lucide-react'
import { useCallback, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import type { Child } from '../../domain/classroom.ts'
import type { Scope } from '../../domain/parent.ts'
import { samePeriod, verifiedReportAnswer } from '../../domain/reportHighlight.ts'
import type { ReportContext, ReportAnswer, ReportHighlight } from '../../domain/reportHighlight.ts'
import { useMessageEvidence } from '../../data/parent/queries.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
export type { ReportContext } from '../../domain/reportHighlight.ts'
import { ParentReports } from './ParentReports.tsx'
import { ParentConversation } from './ParentConversation.tsx'

/** 화면 안 '리포트 | AI 챗봇' 전환은 주소(view=chat)로 하므로, 챗봇으로 넘길 때 연결한 리포트도 주소에 싣는다. */
function reportFromParams(params: URLSearchParams): ReportContext | null {
  const reportId = params.get('askReportId'), revision = Number(params.get('askRevision'))
  const periodType = params.get('askType'), from = params.get('askFrom'), to = params.get('askTo')
  if (!reportId || !Number.isSafeInteger(revision) || revision < 1 || !from || !to || (periodType !== 'DAILY' && periodType !== 'WEEKLY')) return null
  return { reportId, revision, periodType, period: { from, to } }
}
const ASK_KEYS = ['askReportId', 'askRevision', 'askType', 'askFrom', 'askTo']

export function ParentInsights({ child, scope, canReadOriginals, onScope, periodControl, sharingPending = false, mode = 'report' }: {
  child: Child; scope: Scope; canReadOriginals: boolean; onScope: (scope: Scope) => void
  periodControl?: ReactNode; sharingPending?: boolean; mode?: 'report' | 'chat'
}) {
  const [params] = useSearchParams(), navigate = useNavigate()
  const [report, setReport] = useState<ReportContext | null>(() => mode === 'chat' ? reportFromParams(params) : null)
  const switchTo = useCallback((target: 'report' | 'chat') => {
    if (target === mode) return
    const next = new URLSearchParams(params)
    for (const key of [...ASK_KEYS, 'reportId', 'revision']) next.delete(key)
    if (target === 'chat') next.set('view', 'chat'); else next.delete('view')
    navigate('/parent/report?' + next)
  }, [mode, params, navigate])
  const askReport = useCallback((value: ReportContext) => {
    const next = new URLSearchParams(params)
    for (const key of ['reportId', 'revision']) next.delete(key)
    next.set('view', 'chat')
    next.set('askReportId', value.reportId); next.set('askRevision', String(value.revision)); next.set('askType', value.periodType)
    next.set('askFrom', value.period.from); next.set('askTo', value.period.to)
    navigate('/parent/report?' + next)
  }, [params, navigate])
  const leaveReport = useCallback(() => {
    const next = new URLSearchParams(params)
    for (const key of ASK_KEYS) next.delete(key)
    navigate('/parent/report?' + next, { replace: true })
  }, [params, navigate])
  const [highlight, setHighlight] = useState<ReportHighlight | null>(null)
  const [linkError, setLinkError] = useState<unknown>(null), [linkNotice, setLinkNotice] = useState('')
  const [revealToken, setRevealToken] = useState(0)
  // 근거 조회의 요청·취소는 data 훅이 맡는다(#606). 새로 고르거나 지우면 이전 조회를 버린다.
  const { busy: linking, load: loadEvidence, abort: abortEvidence } = useMessageEvidence()
  const selection = useRef<ReportAnswer | null>(null)
  const clearHighlight = useCallback(() => {
    abortEvidence(); selection.current = null
    setHighlight(null); setLinkError(null); setLinkNotice('')
  }, [abortEvidence])
  const onAnswer = useCallback((answer: ReportAnswer | null, reveal = false) => {
    clearHighlight()
    if (!answer || !canReadOriginals || !verifiedReportAnswer(answer.message, child.id)) return
    const message = answer.message
    let target: ReportContext | null = report
    if (answer.reportId) {
      if (report && report.reportId !== answer.reportId || !Number.isSafeInteger(answer.reportRevision) || answer.reportRevision! < 1 || message.scope!.from !== message.scope!.to) {
        setLinkNotice('리포트 연결 정보를 확인하지 못해 위치를 강조하지 않았습니다.'); return
      }
      target = { reportId: answer.reportId, revision: answer.reportRevision!, periodType: 'DAILY', period: message.scope! }
    } else if (report?.periodType === 'DAILY') {
      setLinkNotice('이 대화에 고정된 리포트 판을 확인하지 못해 위치를 강조하지 않았습니다.'); return
    }
    if (!target || !samePeriod(target.period, message.scope!)) {
      setLinkNotice('이 답변의 자녀·기간과 연결된 리포트를 선택해야 근거 위치를 볼 수 있습니다.'); return
    }
    selection.current = answer
    void loadEvidence(answer.conversationId, message.messageId, Array.isArray(message.evidence) && message.evidence.length > 0).then(result => {
      if (!result) return
      if (!Array.isArray(result.items)) throw new Error('답변의 현재 근거를 확인하지 못했습니다.')
      setHighlight({ ...target!, childId: child.id, messageId: message.messageId, question: message.question, metrics: message.metrics!, evidence: result.items })
      if (reveal) setRevealToken(value => value + 1)
    }).catch(error => { setHighlight(null); setLinkError(error) })
  }, [child.id, canReadOriginals, report, clearHighlight, loadEvidence])
  const chatScope = report ? { childId: child.id, ...report.period } : scope
  const dashboardParams = new URLSearchParams({ childId: child.id, from: scope.from, to: scope.to })
  return <section className={mode === 'chat' ? 'parent-insights parent-insights-unified parent-insights-fullscreen' : 'parent-insights parent-insights-unified'}>
    {mode === 'chat' ? <header className="parent-chat-header">
      <Link to={'/parent/journal?' + dashboardParams} aria-label="학부모 대시보드로 돌아가기">
        <ArrowLeft size={22} aria-hidden="true" />
      </Link>
      <h1>AI 챗봇</h1>
      {report ? <span className="chat-period-control">
        <CalendarDays size={17} aria-hidden="true" />
        <span>{chatScope.from} ~ {chatScope.to}</span>
      </span> : periodControl}
    </header> : <header className="parent-page-head">
      <h1 className="parent-insights-switch">
        <button type="button" aria-pressed onClick={() => switchTo('report')}>리포트</button>
        <span aria-hidden="true">|</span>
        <button type="button" aria-pressed={false} onClick={() => switchTo('chat')}>AI 챗봇</button>
      </h1>
    </header>}
    <div className="parent-insights-content">
    {mode === 'report' && <div className="parent-insights-report">
      <div className="parent-report-workspace">
      <ParentReports child={child} canReadOriginals={canReadOriginals} highlight={highlight} revealToken={revealToken} onReportChange={clearHighlight}
        onAskReport={value => { clearHighlight(); askReport(value) }} />
      </div>
    </div>}
    {mode === 'chat' && <div className="parent-insights-chat" id="parent-ai-conversation">
      {linking && <p role="status">답변의 근거 위치를 확인하고 있습니다.</p>}
      {linkNotice && <p role="status">{linkNotice}</p>}
      <ErrorNotice error={linkError} retry={() => onAnswer(selection.current, true)} />
      {sharingPending ? <p role="status">공개 설정을 확인하고 있습니다.</p> :
      <ParentConversation key={`${child.id}:${report ? report.reportId + ':' + report.revision : scope.from + ':' + scope.to}`}
        child={child} scope={chatScope} canReadOriginals={canReadOriginals} report={report ?? undefined}
        onAnswer={onAnswer}
        onClearReport={() => { clearHighlight(); setReport(null); leaveReport() }} onScope={next => { clearHighlight(); setReport(null); onScope(next) }} />}
    </div>}
    </div>
  </section>
}
