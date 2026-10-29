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
export function ParentConversation({
  child,
  scope,
  onScope,
}: {
  child: Child
  scope: Scope
  onScope: (scope: Scope) => void
}) {
  const cache = useQueryClient(),
    list = useParentQuery(['conversations', child.id], (signal) =>
      parentApi.conversations(child.id, signal),
    ),
    [id, setId] = useState<string | null>(null),
    detail = useParentQuery(
      ['conversation', child.id, id],
      (signal) => parentApi.conversation(id!, signal),
      !!id,
    )
  const [question, setQuestion] = useState(''),
    [state, setState] = useState<StreamState>({ phase: 'IDLE', temporary: '' }),
    [error, setError] = useState<unknown>(null),
    [proof, setProof] = useState<{ conversationId: string; messageId: string } | null>(null),
    controller = useRef<AbortController | null>(null),
    active = useRef(true),
    [lastQuestion, setLastQuestion] = useState('')
  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
      controller.current?.abort()
    }
  }, [])
  async function ask(selectedScope?: Scope, retry?: ConversationMessage) {
    const confirmedScope =
      selectedScope ??
      state.result?.scope ??
      (detail.data ? { ...detail.data.period, childId: child.id } : scope)
    const text = retry?.question ?? (state.phase === 'CLARIFICATION' ? lastQuestion : question)
    if (!text.trim() || child.plan === 'FREE') return
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
      void cache.invalidateQueries({ queryKey: ['parent', 'conversation'] })
    }
  }
  function open(conversationId: string) {
    controller.current?.abort()
    setId(conversationId)
    setState({ phase: 'IDLE', temporary: '' })
    setError(null)
  }
  const messages = detail.data?.childId === child.id && !detail.error ? detail.data.messages : [],
    pending = state.phase === 'RUNNING'
  return (
    <>
      <h1>기록에 물어보기</h1>
      <p>
        {child.nickname} · 선택 기간 {scope.from} ~ {scope.to}
      </p>
      <div className="ws-grid">
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
                {c.period.from} ~ {c.period.to} · {c.messages.length}개 질문
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
                      disabled={pending}
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
                m.verification.quotesMatched ? (
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
                  {m.fallback && (
                    <p className="ws-tag">
                      {m.fallback.reason} · 규칙 응답 모드(TEMPLATE). 대조 실패 사실을 안내합니다.
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
                    void ask(option.scope)
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
          {child.plan === 'FREE' ? (
            <p className="ws-card">
              이 자녀의 무료 플랜에는 분석 대화가 포함되지 않습니다. 대시보드와 수치 리포트는 확인할
              수 있습니다.
            </p>
          ) : (
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
                  maxLength={2000}
                  required
                />
              </label>
              <button className="cj-primary" disabled={pending || state.phase === 'CLARIFICATION'}>
                기록으로 답변 받기
              </button>
              <small>
                다른 화면으로 이동하면 스트림을 취소합니다. 임시 문장을 확정 답변으로 남기지
                않습니다.
              </small>
            </form>
          )}
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
