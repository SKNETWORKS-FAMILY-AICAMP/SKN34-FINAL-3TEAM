import { ArrowUp, MessageSquare, SquarePen, Search } from 'lucide-react'
import { useLayoutEffect, useRef, useState } from 'react'
import { ReportProblem } from '../service/ReportProblem.tsx'
import type { Child } from '../../domain/classroom.ts'
import type { Scope, StreamState, ConversationMessage, Conversation, Evidence } from '../../domain/parent.ts'
import { parentApi } from '../../data/parent/api.ts'
import { useConversationRequests, useParentQuery } from '../../data/parent/queries.ts'
import { knownEntitlement, useChildEntitlement } from '../../data/payment/queries.ts'
import { ApiError } from '../../data/apiClient.ts'
import { QueryFeedback, EvidenceItems } from '../common/Workspace.tsx'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import type { ReportContext } from './ParentInsights.tsx'
import type { ReportAnswer } from '../../domain/reportHighlight.ts'
export function ParentConversation({
  child,
  scope,
  onScope,
  report,
  onClearReport,
  onAnswer,
}: {
  child: Child
  scope: Scope
  onScope: (scope: Scope) => void
  report?: ReportContext
  onClearReport?: () => void
  onAnswer?: (answer: ReportAnswer | null, reveal?: boolean) => void
}) {
  const requests = useConversationRequests(),
    list = useParentQuery(['conversations', child.id], (signal) =>
      parentApi.conversations(child.id, signal),
      !report,
    ),
    [id, setId] = useState<string | null>(null),
    detail = useParentQuery(
      ['conversation', child.id, id],
      (signal) => parentApi.conversation(id!, signal),
      !!id,
    )
  const [historySearch, setHistorySearch] = useState('')
  const [question, setQuestion] = useState(''),
    [state, setState] = useState<StreamState>({ phase: 'IDLE', temporary: '' }),
    [error, setError] = useState<unknown>(null),
    [proof, setProof] = useState<{ conversationId: string; messageId: string } | null>(null),
    conversationRef = useRef<Conversation | null>(null),
    [lastQuestion, setLastQuestion] = useState('')
  const thread = useRef<HTMLDivElement>(null)
  const followThread = useRef(true)
  // 이용권은 entitlement로만 판단한다(#602). 조회 전·실패면 막지 않고 서버 응답을 따른다.
  const entitlement = knownEntitlement(useChildEntitlement(child.id)),
    conversationOff = entitlement?.conversationEnabled === false
  // 대화 생성·SSE·취소·캐시 갱신은 data 훅이 맡는다(#606).
  async function ask(selectedScope?: Scope, retry?: ConversationMessage, example?: string) {
    const confirmedScope =
      selectedScope ??
      state.result?.scope ??
      (detail.data ? { ...detail.data.period, childId: child.id } : scope)
    const text = example ?? retry?.question ?? (state.phase === 'CLARIFICATION' && !question.trim() ? lastQuestion : question)
    if (!text.trim() || conversationOff) return
    setError(null)
    onAnswer?.(null)
    setLastQuestion(text)
    followThread.current = true
    setState({ phase: 'RUNNING', temporary: '' })
    try {
      const done = await requests.ask({
        conversationId: id, target: target(confirmedScope), text, scope: confirmedScope, retryId: retry?.messageId,
        onCreated: (c) => { conversationRef.current = c; setId(c.conversationId) },
        onState: setState,
      })
      if (!done) return
      const { conversationId, result } = done
      if (result && report) {
        const context = detail.data?.conversationId === conversationId ? detail.data : conversationRef.current
        onAnswer?.({ conversationId, message: { ...result, question: text, status: 'COMPLETED' }, reportId: context?.reportId, reportRevision: context?.reportRevision })
      }
      setQuestion('')
    } catch (e) {
      setError(e)
      setState((previous) => ({ ...previous, phase: 'FAILED', temporary: '', result: undefined }))
    }
  }
  /** 일일 리포트에서 시작한 대화는 그 리포트에 고정한다. */
  function target(confirmedScope: Scope) {
    return { childId: child.id, scope: confirmedScope, dailyReportId: report?.periodType === 'DAILY' ? report.reportId : undefined }
  }
  function open(conversationId: string) {
    followThread.current = true
    requests.abort()
    onAnswer?.(null); conversationRef.current = null
    setId(conversationId)
    setState({ phase: 'IDLE', temporary: '' })
    setError(null)
  }
  const messages = detail.data?.childId === child.id && !detail.error ? detail.data.messages : [],
    pending = state.phase === 'RUNNING'
  const lastMessage = messages.at(-1)
  useLayoutEffect(() => {
    if (followThread.current && thread.current) thread.current.scrollTop = thread.current.scrollHeight
  }, [id, pending, lastMessage, state.phase])
  return (
    <>
      <div className="pc-layout">
        <aside className="ws-card">
          <h3>{report ? '질문에 연결한 리포트' : '이전 대화'}</h3>
          {report && <div role="note"><p>{report.periodType === 'DAILY' ? '일일 리포트' : '주간 리포트'}</p>
            {report.periodType === 'DAILY' && <p>대화 시작 시 최신 리포트 판과 해당 날짜로 연결됩니다.</p>}
            <button className="cj-secondary" onClick={onClearReport}>전체 기록으로 질문하기</button></div>}
          {!report && <QueryFeedback query={list} />}
          {!report && <label className="pc-history-search"><Search size={16} aria-hidden="true" /><input aria-label="이전 대화 검색" placeholder="대화 찾기" value={historySearch} onChange={e => setHistorySearch(e.target.value)} /></label>}
          <div className="pc-history-list">
          {!report && list.data &&
            !list.error &&
            list.data.items.filter(c => `${c.title} ${c.period.from} ${c.period.to}`.toLocaleLowerCase().includes(historySearch.trim().toLocaleLowerCase())).map((c) => (
              <button
                className="cj-secondary"
                key={c.conversationId}
                aria-current={id === c.conversationId ? 'true' : undefined}
                onClick={() => open(c.conversationId)}
              >
                <span title={c.title}>{c.title || '학습 기록 질문'}</span><small>{c.period.from} ~ {c.period.to}</small>
              </button>
            ))}
          </div>
          <button
            className="cj-secondary pc-new-chat"
            onClick={() => {
              requests.abort()
              onAnswer?.(null); conversationRef.current = null
              setId(null)
              setState({ phase: 'IDLE', temporary: '' })
              setError(null)
            }}
          >
            <SquarePen size={16} aria-hidden="true" /> 새 대화
          </button>
        </aside>
        <section className="ws-stack pc-conversation-panel">
          <div className="pc-thread" ref={thread} aria-label="대화 내용" tabIndex={0} onScroll={event => {
            const { scrollHeight, scrollTop, clientHeight } = event.currentTarget
            followThread.current = scrollHeight - scrollTop - clientHeight < 48
          }}>
          {!id && !pending && state.phase === 'IDLE' && <div className="pc-welcome"><MessageSquare size={30} strokeWidth={1.5} aria-hidden="true" /><h3>{child.nickname}의 기록에서<br />어떤 점이 궁금하세요?</h3><p>학습 내용과 달라진 생각을 물어보세요.</p></div>}
          {id && <QueryFeedback query={detail} />}
          {messages.map((m) => (
            <article className="ws-card pc-message" key={m.messageId}>
              <div className="pc-user-message"><p>{m.question}</p></div>
              {m.status === 'FAILED' ? (
                <>
                  <p role="alert">답변을 만들지 못했어요.</p>
                  {m.retryable && (
                    <button
                      className="cj-secondary"
                      disabled={pending}
                      onClick={() => {
                        void ask(m.scope ?? scope, m)
                      }}
                    >
                      다시 시도
                    </button>
                  )}
                </>
              ) : m.status === 'COMPLETED' &&
                m.answer &&
                m.verification?.numbersMatched &&
                m.verification.quotesMatched && m.verification.contentAllowed !== false ? (
                <>
                  <div className="pc-assistant-message"><h3><MessageSquare size={17} aria-hidden="true" />기록을 바탕으로 한 답변</h3><p>{m.answer}</p></div>
                  {m.correctionNotice && (
                    <p role="note">이 답변에 쓰인 판정 중 일부가 정정되었습니다.</p>
                  )}
                  <footer className="pc-answer-footer">
                    <span className="pc-answer-context">
                      {m.scope && <span>{m.scope.from}{m.scope.from !== m.scope.to && ' ~ ' + m.scope.to}</span>}
                      {Number.isFinite(m.recordCount) && <span>조회 기록 {m.recordCount}건</span>}
                    </span>
                    <div className="pc-answer-actions">
                      {m.scope?.changed && <button type="button" onClick={() => onScope(m.scope!)}>
                        이 기간으로 변경
                      </button>}
                      {!!m.evidence?.length && <button type="button" onClick={() => {
                        if (id) setProof({ conversationId: id, messageId: m.messageId })
                      }}>답변 근거 보기</button>}
                      <ReportProblem targetType="ANALYSIS" targetId={m.messageId} />
                    </div>
                  </footer>
                </>
              ) : (
                <p>
                  {m.status === 'RUNNING'
                    ? '처리 중'
                    : '확정 답변 없음 · 범위 확인 또는 결과 검증이 필요합니다.'}
                </p>
              )}
            </article>
          ))}
          {pending && (
            <div className="pc-progress" role="status">
              <span aria-hidden="true" />
              답변을 준비하고 있어요
            </div>
          )}
          {state.phase === 'CLARIFICATION' && state.clarification && (
            <section className="ws-card">
              <h3>{state.clarification.question}</h3>
              {state.clarification.options.map((option, i) => (
                <button
                  className="cj-secondary"
                  key={i}
                  onClick={() => {
                    if (option.scope.childId !== child.id || report?.periodType === 'DAILY' && (option.scope.from !== scope.from || option.scope.to !== scope.to)) {
                      requests.abort()
                      onScope(option.scope)
                    } else {
                      void ask(option.scope)
                    }
                  }}
                >
                  {option.label}
                </button>
              ))}
            </section>
          )}
          <ErrorNotice
            error={error}
            retry={
              error instanceof ApiError && state.messageId
                ? () => {
                    const m = messages.find((m) => m.messageId === state.messageId)
                    if (m) void ask(m.scope ?? scope, m)
                  }
                : undefined
            }
          />
          {conversationOff && (
            <p className="ws-card">
              {entitlement?.refundPending
                ? '환불 검토 중에는 분석 대화를 이용할 수 없습니다. 대시보드와 수치 리포트는 확인할 수 있습니다.'
                : '이 자녀의 무료 플랜에는 분석 대화가 포함되지 않습니다. 대시보드와 수치 리포트는 확인할 수 있습니다.'}
            </p>
          )}
          </div>
          {!conversationOff && <>
            {!id && !pending && state.phase === 'IDLE' && <ExampleQuestions
              childId={child.id}
              onPick={text => {
                setQuestion(text)
                void ask(undefined, undefined, text)
              }}
            />}
          <form
            className="ws-card ws-form pc-composer"
            onSubmit={(e) => {
              e.preventDefault()
              void ask()
            }}
          >
            <textarea
              aria-label="기록에 대한 질문"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="질문을 입력해 주세요"
              rows={1}
              maxLength={1000}
              required
            />
            <button className="cj-primary" type="submit" aria-label="질문 보내기" disabled={pending || !question.trim()}>
              <ArrowUp size={20} aria-hidden="true" />
            </button>
          </form>
          </>}
        </section>
      </div>
      {proof && (
        <Modal title="답변 근거" scrollIndicator onClose={() => setProof(null)}>
          <EvidenceQuery
            queryKey={['message-evidence', child.id, proof.conversationId, proof.messageId]}
            load={(signal) =>
              parentApi.messageEvidence(proof.conversationId, proof.messageId, signal)
            }
          />
        </Modal>
      )}
    </>
  )
}
/** 예시 질문 (FN-AGT-12, 선택). 기록이 없어 답할 수 없는 질문은 보내지 않고 가능 범위를 안내한다. */
function ExampleQuestions({ childId, onPick }: { childId: string; onPick: (question: string) => void }) {
  const examples = useParentQuery(['analysis-examples', childId], (signal) => parentApi.examples(childId, signal))
  if (examples.isPending || examples.error || !examples.data.length) return null
  return (
    <div className="ws-examples" role="group" aria-label="예시 질문">
      <div className="ws-actions">
        {examples.data.map((e) => (
          <button
            key={e.question}
            type="button"
            className="cj-secondary"
            disabled={!e.available}
            title={e.available ? undefined : '이 질문에 필요한 학습 기록이 아직 없습니다.'}
            onClick={() => onPick(e.question)}
          >
            {e.question}
          </button>
        ))}
      </div>
    </div>
  )
}
export function EvidenceQuery({
  queryKey,
  load,
}: {
  queryKey: unknown[]
  load: (signal: AbortSignal) => Promise<{ items: Evidence[] }>
}) {
  const q = useParentQuery(queryKey, load)
  return (
    <>
      <QueryFeedback query={q} />
      {q.error instanceof ApiError && q.error.problem.status === 410 && (
        <p>이용 불가 · 삭제된 근거입니다. 다른 기록으로 대체하지 않습니다.</p>
      )}
      {q.data && !q.error && <EvidenceItems items={q.data.items} />}
    </>
  )
}
