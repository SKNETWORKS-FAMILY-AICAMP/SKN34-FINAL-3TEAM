import { Link } from 'react-router'
import { analysisResultLabel } from '../../domain/parent.ts'
import { useEffect, useRef, useState } from 'react'
import { ReportProblem } from '../service/ReportProblem.tsx'
import { useQueryClient } from '@tanstack/react-query'
import type { Child } from '../../domain/classroom.ts'
import type { Scope, StreamState, ConversationMessage, Evidence } from '../../domain/parent.ts'
import { parentApi } from '../../data/parent/api.ts'
import { useParentQuery } from '../../data/parent/queries.ts'
import { ApiError } from '../../data/apiClient.ts'
import { QueryFeedback, MetricCards, EvidenceItems } from '../common/Workspace.tsx'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import { ReportTemplateEditor } from './ReportTemplateEditor.tsx'
export function ParentConversation({
  child,
  scope,
  onScope,
  canReadOriginals = false,
}: {
  canReadOriginals?: boolean
  child: Child
  scope: Scope
  onScope: (scope: Scope) => void
}) {
  const cache = useQueryClient(),
    list = useParentQuery(['conversations', child.id], (signal) =>
      parentApi.conversations(child.id, signal),
      canReadOriginals,
    ),
    [id, setId] = useState<string | null>(null),
    detail = useParentQuery(
      ['conversation', child.id, id],
      (signal) => parentApi.conversation(id!, signal),
      !!id && canReadOriginals,
    )
  const [question, setQuestion] = useState(''),
    [state, setState] = useState<StreamState>({ phase: 'IDLE', temporary: '' }),
    [error, setError] = useState<unknown>(null),
    [proof, setProof] = useState<{ conversationId: string; messageId: string } | null>(null),
    controller = useRef<AbortController | null>(null),
    active = useRef(true),
    [lastQuestion, setLastQuestion] = useState(''),
    [startingTemplate, setStartingTemplate] = useState(false),
    [templateOpen, setTemplateOpen] = useState(false)
  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
      controller.current?.abort()
    }
  }, [])
  useEffect(() => {
    if (!canReadOriginals) controller.current?.abort()
  }, [canReadOriginals])
  async function ask(selectedScope?: Scope, retry?: ConversationMessage, example?: string) {
    const confirmedScope =
      selectedScope ??
      state.result?.scope ??
      (detail.data ? { ...detail.data.period, childId: child.id } : scope)
    const text = example ?? retry?.question ?? (state.phase === 'CLARIFICATION' && !question.trim() ? lastQuestion : question)
    if (!text.trim() || child.plan === 'FREE' || !canReadOriginals) return
    controller.current?.abort()
    const abort = new AbortController()
    controller.current = abort
    setError(null)
    setLastQuestion(text)
    setState({ phase: 'RUNNING', temporary: '' })
    try {
      let conversationId = id
      if (!conversationId) {
        const c = await parentApi.create(confirmedScope)
        if (!active.current || abort.signal.aborted) return
        conversationId = c.conversationId
        setId(conversationId)
      }
      await parentApi.message(
        conversationId,
        text,
        confirmedScope,
        (s) => {
          if (active.current && !abort.signal.aborted) setState(s)
        },
        abort.signal,
        retry?.messageId,
      )
      if (!active.current || abort.signal.aborted) return
      setQuestion('')
      void cache.invalidateQueries({ queryKey: ['parent', 'conversation'] })
      void cache.invalidateQueries({ queryKey: ['parent', 'conversations'] })
    } catch (e) {
      if (!active.current || abort.signal.aborted) return
      setError(e)
      setState((previous) => ({ ...previous, phase: 'FAILED', temporary: '', result: undefined }))
      void cache.invalidateQueries({ queryKey: ['parent', 'conversation'] })
    }
  }
  function open(conversationId: string) {
    controller.current?.abort()
    setId(conversationId)
    setState({ phase: 'IDLE', temporary: '' })
    setError(null)
  }
  async function startTemplate() {
    if (startingTemplate || child.plan === 'FREE' || !canReadOriginals) return
    const abort = new AbortController()
    controller.current?.abort(); controller.current = abort
    setStartingTemplate(true); setError(null)
    try {
      const conversation = await parentApi.create(scope)
      if (!active.current || abort.signal.aborted) return
      setId(conversation.conversationId)
      void cache.invalidateQueries({ queryKey: ['parent', 'conversations'] })
    } catch (e) {
      if (active.current && !abort.signal.aborted) setError(e)
    } finally { if (active.current) setStartingTemplate(false) }
  }
  const messages = detail.data?.childId === child.id && !detail.error ? detail.data.messages : [],
    pending = state.phase === 'RUNNING'
  if (!canReadOriginals) return <section className="ws-stack"><header><h1>AI 챗봇</h1><p>학습 기록을 바탕으로 궁금한 점을 질문하는 대화입니다.</p></header><div className="parent-private-records" role="note"><h2>답변 원문이 비공개여서 기록 분석 질문은 잠시 쉬어요</h2><p>학습 현황과 리포트의 수치는 계속 볼 수 있습니다. 원문을 분석하는 대화는 아이가 공개한 뒤 이용할 수 있습니다.</p><div className="ws-actions"><Link to={`/parent/journal?childId=${encodeURIComponent(child.id)}`} className="cj-secondary">학습 현황 보기</Link><Link to={`/parent/report?childId=${encodeURIComponent(child.id)}`} className="cj-secondary">리포트 보기</Link></div></div></section>
  return (
    <>
      <header className="parent-page-head">
      <h1>AI 챗봇</h1>
      <p>학습 기록에 대해 궁금한 점을 질문하고 답변의 근거를 확인하세요. 리포트는 정해진 주기로 자동 생성됩니다.</p>
      <p>
        {child.nickname} · 선택 기간 {scope.from} ~ {scope.to}
      </p>
      </header>
      <div className="pc-layout">
        <aside className="ws-card">
          <h2>이전 대화</h2>
          <QueryFeedback query={list} />
          {list.data &&
            !list.error &&
            list.data.items.map((c) => (
              <button
                className="cj-secondary"
                key={c.conversationId}
                onClick={() => open(c.conversationId)}
              >
                {c.period.from} ~ {c.period.to}
              </button>
            ))}
          <button
            className="cj-secondary"
            onClick={() => {
              controller.current?.abort()
              setId(null)
              setState({ phase: 'IDLE', temporary: '' })
              setError(null)
            }}
          >
            새 대화
          </button>
        </aside>
        <section className="ws-stack">
          {id && <QueryFeedback query={detail} />}
          {messages.map((m) => (
            <article className="ws-card" key={m.messageId}>
              <h3>보호자의 질문</h3>
              <p>{m.question}</p>
              {m.status === 'FAILED' ? (
                <>
                  <p role="alert">처리 실패 · {m.failureCode}. 임시 문장은 보관하지 않습니다.</p>
                  {m.retryable && (
                    <button
                      className="cj-secondary"
                      disabled={!canReadOriginals || pending}
                      onClick={() => {
                        void ask(m.scope ?? scope, m)
                      }}
                    >
                      실패 메시지 재시도
                    </button>
                  )}
                </>
              ) : m.status === 'COMPLETED' &&
                m.answer &&
                m.verification?.numbersMatched &&
                m.verification.quotesMatched && m.verification.contentAllowed !== false ? (
                <>
                  <p>{m.answer}</p>
                  <ReportProblem targetType="ANALYSIS" targetId={m.messageId}/>
                  {m.scope && (
                    <p>
                      이 답변의 실제 범위 · {m.scope.from} ~ {m.scope.to}
                      {m.scope.changed && <strong> · 범위가 변경되었습니다.</strong>}
                    </p>
                  )}
                  {m.scope?.changed && (
                    <button className="cj-secondary" onClick={() => onScope(m.scope!)}>
                      이 범위를 화면 전체에 적용
                    </button>
                  )}
                  {(m.fallback || m.notice) && (
                    <p className="ws-tag">
                      {analysisResultLabel(m)}
                    </p>
                  )}
                  {m.metrics && <MetricCards metrics={m.metrics} />}
                  <p>
                    출처 {m.source} · 조회 기록 {m.recordCount}건
                  </p>
                  <button
                    className="cj-secondary"
                    onClick={() => setProof({ conversationId: id!, messageId: m.messageId })}
                  >
                    답변 근거 보기
                  </button>
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
            <div className="ws-chat-temp" role="status">
              <strong>{state.message ?? '기록을 살펴보고 있습니다.'}</strong>
              {state.temporary && <p>{state.temporary}</p>}
              <small>임시 출력 · 숫자·인용 대조 전</small>
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
                    if (option.scope.childId !== child.id) {
                      controller.current?.abort()
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
          {child.plan === 'FREE' && (
            <p className="ws-card">
              이 자녀의 무료 플랜에는 분석 대화가 포함되지 않습니다. 대시보드와 수치 리포트는 확인할
              수 있습니다.
            </p>
          )}
          {child.plan !== 'FREE' && (
          <form
            className="ws-card ws-form"
            onSubmit={(e) => {
              e.preventDefault()
              void ask()
            }}
          >
            <label>
              기록에 대한 질문
              <textarea
                aria-label="기록에 대한 질문"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="되묻기 전후에 어떤 말이 더해졌나요?"
                maxLength={1000}
                required
              />
            </label>
            <button className="cj-primary" disabled={!canReadOriginals || pending || startingTemplate}>
              질문 보내기
            </button>
            <ExampleQuestions
              childId={child.id}
              disabled={!canReadOriginals || pending || startingTemplate}
              onPick={(text) => {
                // 현재 자녀·기간(대화 범위)을 그대로 두고 질문만 채워 보낸다.
                setQuestion(text)
                void ask(undefined, undefined, text)
              }}
            />
            <small>
              다른 화면으로 이동하면 답변 생성을 중단합니다. 저장된 대화는 이전 대화에서 다시 볼 수 있습니다.
            </small>
          </form>
          )}
          {child.plan !== 'FREE' && <details className="pc-template" onToggle={event => setTemplateOpen(event.currentTarget.open)}>
            <summary>리포트 표시 설정 변경</summary>
            {templateOpen && (id
              ? <ReportTemplateEditor key={id} conversationId={id} />
              : <button className="cj-secondary" disabled={pending || startingTemplate} onClick={() => { void startTemplate() }}>리포트 설정 대화 시작</button>)}
          </details>}
        </section>
      </div>
      {proof && (
        <Modal title="분석 답변의 근거" onClose={() => setProof(null)}>
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
function ExampleQuestions({ childId, disabled, onPick }: { childId: string; disabled: boolean; onPick: (question: string) => void }) {
  const examples = useParentQuery(['analysis-examples', childId], (signal) => parentApi.examples(childId, signal))
  if (examples.isPending || examples.error || !examples.data.length) return null
  const unavailable = examples.data.some((e) => !e.available)
  return (
    <div className="ws-examples" role="group" aria-label="예시 질문">
      <small>예시 질문</small>
      <div className="ws-actions">
        {examples.data.map((e) => (
          <button
            key={e.question}
            type="button"
            className="cj-secondary"
            disabled={disabled || !e.available}
            onClick={() => onPick(e.question)}
          >
            {e.question}
          </button>
        ))}
      </div>
      {unavailable && (
        <small>
          흐리게 표시한 질문은 이 자녀의 학습 기록이 아직 없어 답할 수 없습니다. 기록이 생긴 뒤 다시 선택해 주세요.
        </small>
      )}
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
