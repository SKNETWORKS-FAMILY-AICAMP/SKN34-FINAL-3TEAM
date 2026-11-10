import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useSearchParams } from 'react-router'
import type { Child } from '../../domain/classroom.ts'
import type { Scope } from '../../domain/parent.ts'
import { samePeriod, verifiedReportAnswer } from '../../domain/reportHighlight.ts'
import type { ReportContext, ReportAnswer, ReportHighlight } from '../../domain/reportHighlight.ts'
import { parentApi } from '../../data/parent/api.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
export type { ReportContext } from '../../domain/reportHighlight.ts'
import { ParentReports } from './ParentReports.tsx'
import { ParentConversation } from './ParentConversation.tsx'

export function ParentInsights({ child, scope, canReadOriginals, onScope, periodControl, sharingPending = false }: {
  child: Child; scope: Scope; canReadOriginals: boolean; onScope: (scope: Scope) => void
  periodControl?: ReactNode; sharingPending?: boolean
}) {
  const [params, setParams] = useSearchParams()
  const [report, setReport] = useState<ReportContext | null>(null)
  const [highlight, setHighlight] = useState<ReportHighlight | null>(null)
  const [selectedMessageId, setSelectedMessageId] = useState<string>()
  const [linking, setLinking] = useState(false), [linkError, setLinkError] = useState<unknown>(null), [linkNotice, setLinkNotice] = useState('')
  const [revealToken, setRevealToken] = useState(0)
  const request = useRef<AbortController | null>(null), selection = useRef<ReportAnswer | null>(null)
  const clearHighlight = useCallback(() => {
    request.current?.abort(); request.current = null; selection.current = null
    setHighlight(null); setSelectedMessageId(undefined); setLinking(false); setLinkError(null); setLinkNotice('')
  }, [])
  useEffect(() => () => { request.current?.abort() }, [])
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
    selection.current = answer; setSelectedMessageId(message.messageId)
    const controller = new AbortController(); request.current = controller; setLinking(true)
    const refs = Array.isArray(message.evidence) && message.evidence.length
      ? parentApi.messageEvidence(answer.conversationId, message.messageId, controller.signal) : Promise.resolve({ items: [] })
    void refs.then(result => {
      if (controller.signal.aborted) return
      if (!Array.isArray(result.items)) throw new Error('답변의 현재 근거를 확인하지 못했습니다.')
      setHighlight({ ...target!, childId: child.id, messageId: message.messageId, question: message.question, metrics: message.metrics!, evidence: result.items })
      if (reveal) setRevealToken(value => value + 1)
    }).catch(error => { if (!controller.signal.aborted) { setHighlight(null); setLinkError(error) } })
      .finally(() => { if (!controller.signal.aborted) setLinking(false) })
  }, [child.id, canReadOriginals, report, clearHighlight])
  const view = params.get('view') === 'chat' ? 'chat' : 'reports'
  const setView = (nextView: string) => {
    const next = new URLSearchParams(params); next.set('view', nextView); setParams(next)
  }
  const chatScope = report ? { childId: child.id, ...report.period } : scope
  const preview = view === 'chat' ? highlight ?? report ?? undefined : undefined
  return <section className={preview ? 'parent-insights is-linked' : 'parent-insights'}>
    <header className="parent-page-head"><h1>리포트·AI 챗봇</h1><p>학습 결과를 확인하고, 같은 곳에서 궁금한 점을 이어서 물어보세요.</p></header>
    <nav className="parent-tabs" aria-label="리포트·챗봇 보기">
      <button aria-pressed={view === 'reports'} onClick={() => setView('reports')}>리포트 보기</button>
      <button aria-pressed={view === 'chat'} onClick={() => setView('chat')}>AI에게 질문하기</button>
    </nav>
    <div className="parent-insights-content">
    <div className="parent-insights-report" data-report-preview={preview ? 'true' : undefined} hidden={view !== 'reports' && !preview}>
      {preview && <h2>질문에 연결한 리포트</h2>}
      <div className="parent-insights-report-body">
      <ParentReports child={child} preview={preview} highlight={highlight} revealToken={revealToken} onReportChange={clearHighlight}
        onAskReport={value => { clearHighlight(); setReport(value); setView('chat') }} />
      </div>
    </div>
    <div className="parent-insights-chat" hidden={view !== 'chat'}>
      {!report && periodControl}
      {linking && <p role="status">답변의 근거 위치를 확인하고 있습니다.</p>}
      {linkNotice && <p role="status">{linkNotice}</p>}
      <ErrorNotice error={linkError} retry={() => onAnswer(selection.current, true)} />
      {sharingPending ? <p role="status">공개 설정을 확인하고 있습니다.</p> :
      <ParentConversation key={`${child.id}:${report ? report.reportId + ':' + report.revision : scope.from + ':' + scope.to}`}
        child={child} scope={chatScope} canReadOriginals={canReadOriginals} report={report ?? undefined}
        onAnswer={onAnswer} selectedMessageId={selectedMessageId}
        onClearReport={() => { clearHighlight(); setReport(null) }} onScope={next => { clearHighlight(); setReport(null); onScope(next) }} />}
    </div>
    </div>
  </section>
}
