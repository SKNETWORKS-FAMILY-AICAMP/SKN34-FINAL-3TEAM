import { useState } from 'react'
import type { ReactNode } from 'react'
import { useSearchParams } from 'react-router'
import type { Child, Period } from '../../domain/classroom.ts'
import type { Scope } from '../../domain/parent.ts'
import { ParentReports } from './ParentReports.tsx'
import { ParentConversation } from './ParentConversation.tsx'

export interface ReportContext {
  reportId: string
  revision: number
  period: Period
  periodType: 'DAILY' | 'WEEKLY'
}

export function ParentInsights({ child, scope, canReadOriginals, onScope, periodControl, sharingPending = false }: {
  child: Child; scope: Scope; canReadOriginals: boolean; onScope: (scope: Scope) => void
  periodControl?: ReactNode; sharingPending?: boolean
}) {
  const [params, setParams] = useSearchParams()
  const [report, setReport] = useState<ReportContext | null>(null)
  const view = params.get('view') === 'chat' ? 'chat' : 'reports'
  const setView = (nextView: string) => {
    const next = new URLSearchParams(params); next.set('view', nextView); setParams(next)
  }
  const chatScope = report ? { childId: child.id, ...report.period } : scope
  return <section className="parent-insights">
    <header className="parent-page-head"><h1>리포트·AI 챗봇</h1><p>학습 결과를 확인하고, 같은 곳에서 궁금한 점을 이어서 물어보세요.</p></header>
    <nav className="parent-tabs" aria-label="리포트·챗봇 보기">
      <button aria-pressed={view === 'reports'} onClick={() => setView('reports')}>리포트 보기</button>
      <button aria-pressed={view === 'chat'} onClick={() => setView('chat')}>AI에게 질문하기</button>
    </nav>
    <div hidden={view !== 'reports'}>
      <ParentReports child={child} onAskReport={value => { setReport(value); setView('chat') }} />
    </div>
    <div hidden={view !== 'chat'}>
      {!report && periodControl}
      {sharingPending ? <p role="status">공개 설정을 확인하고 있습니다.</p> :
      <ParentConversation key={`${child.id}:${report ? report.reportId + ':' + report.revision : scope.from + ':' + scope.to}`}
        child={child} scope={chatScope} canReadOriginals={canReadOriginals} report={report ?? undefined}
        onClearReport={() => setReport(null)} onScope={next => { setReport(null); onScope(next) }} />}
    </div>
  </section>
}
