import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { parentApi } from '../../data/parent/api.ts'
import { useParentQuery } from '../../data/parent/queries.ts'
import { ApiError } from '../../data/apiClient.ts'
import { metricLabels, sectionLabels, toneLabels } from '../../domain/reportTemplate.ts'
import type { ReportTemplateProposal, ReportTemplateSettings } from '../../domain/reportTemplate.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'

function Settings({ value }: { value: ReportTemplateSettings }) {
  return <dl>
    <dt>섹션 순서</dt><dd>{value.sectionOrder.map((s) => sectionLabels[s]).join(' → ')}</dd>
    <dt>강조 지표</dt><dd>{value.highlightMetrics.map((m) => metricLabels[m]).join(', ') || '없음'}</dd>
    <dt>서술 톤</dt><dd>{toneLabels[value.tone]}</dd>
  </dl>
}

export function ReportTemplateEditor({ conversationId }: { conversationId: string }) {
  const cache = useQueryClient()
  const current = useParentQuery(['report-template', conversationId], (signal) => parentApi.reportTemplate(conversationId, signal))
  const [question, setQuestion] = useState('')
  const [proposal, setProposal] = useState<ReportTemplateProposal | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const [expired, setExpired] = useState(false)
  const request = useRef<AbortController | null>(null)
  useEffect(() => () => { request.current?.abort() }, [])
  useEffect(() => {
    if (!proposal?.proposalId) return
    const timer = window.setTimeout(() => setExpired(true), Math.max(0, Date.parse(proposal.expiresAt) - Date.now()))
    return () => window.clearTimeout(timer)
  }, [proposal])
  async function submit(confirm: boolean) {
    if (request.current || (!confirm && !question.trim()) || (confirm && (!proposal?.proposalId || expired))) return
    const abort = new AbortController()
    request.current = abort
    setBusy(true); setError(null); setSaved(false)
    try {
      if (confirm && proposal?.proposalId) {
        const result = await parentApi.confirmReportTemplate(conversationId, proposal.proposalId, abort.signal)
        if (abort.signal.aborted) return
        cache.setQueryData(['parent', 'report-template', conversationId], result)
        void cache.invalidateQueries({ queryKey: ['parent', 'report-template'] })
        setProposal(null); setQuestion(''); setSaved(true)
      } else {
        setProposal(null)
        const result = await parentApi.proposeReportTemplate(conversationId, question.trim(), abort.signal)
        if (abort.signal.aborted) return
        setExpired(!!result.proposalId && Date.parse(result.expiresAt) <= Date.now())
        setProposal(result)
      }
    } catch (e) {
      if (abort.signal.aborted) return
      setError(e)
      // A lost response could have committed. Fetch current state, never silently retry a write.
      if (confirm) { setProposal(null); void current.refetch() }
      if (e instanceof ApiError && [401, 403, 404, 429].includes(e.problem.status)) setProposal(null)
    } finally {
      if (!abort.signal.aborted) { request.current = null; setBusy(false) }
    }
  }
  return <section className="ws-card ws-stack" aria-label="리포트 표시 설정">
    <h2>리포트 표시 설정</h2>
    <p>원하는 순서, 강조할 수치, 설명 말투를 적어 주세요. 변경안을 확인한 뒤 저장합니다.</p>
    <p>연결된 모든 자녀의 다음 리포트 생성부터 적용됩니다. 기존 리포트는 바뀌지 않습니다.</p>
    <small>원문 공개 여부는 학생의 별도 설정을 따릅니다. 이 화면에서는 바꿀 수 없습니다.</small>
    <QueryFeedback query={current} />
    {current.data && !current.error && <div aria-label="현재 리포트 설정"><h3>현재 설정</h3><Settings value={current.data.settings} /></div>}
    <form className="ws-form" onSubmit={(e) => { e.preventDefault(); void submit(false) }}>
      <label>리포트 변경 요청<textarea aria-label="리포트 변경 요청" maxLength={1000} required value={question}
        disabled={busy} placeholder="돌아보기를 먼저 보여 주고, 간결하게 설명해 주세요."
        onChange={(e) => { setQuestion(e.target.value); setProposal(null); setSaved(false); setError(null) }} /></label>
      <button className="cj-secondary" disabled={busy || !question.trim() || !current.data || !!current.error}>변경안 확인하기</button>
      <small>변경안을 요청하면 분석 대화 사용 한도에 포함됩니다. 확인·저장에는 추가 차감이 없습니다.</small>
    </form>
    {busy && <p role="status">요청을 처리하고 있습니다.</p>}
    {proposal?.clarification && <p role="status">{proposal.clarification}</p>}
    {proposal?.proposalId && <div aria-label="리포트 설정 변경안">
      <h3>변경안</h3><Settings value={proposal.settings} />
      <p>{expired ? '변경안이 만료되었습니다. 다시 요청해 주세요.' : '아직 저장되지 않았습니다. 변경안을 확인해 주세요.'}</p>
      <button className="cj-primary" disabled={busy || expired} onClick={() => { void submit(true) }}>확인하고 저장</button>
      <button className="cj-secondary" disabled={busy} onClick={() => { setProposal(null); setError(null) }}>변경안 취소</button>
    </div>}
    {saved && <p role="status">저장했습니다. 다음 리포트 생성부터 적용됩니다.</p>}
    <ErrorNotice error={error} />
  </section>
}
