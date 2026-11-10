import { useEffect, useRef, useState } from 'react'
import type { Child, Period } from '../../domain/classroom.ts'
import type { Scope, StreamState, MessageResult } from '../../domain/parent.ts'
import { analysisResultLabel } from '../../domain/parent.ts'
import { parentApi } from '../../data/parent/api.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'

interface Turn {
  question: string
  result?: MessageResult
}

/**
 * 리포트 상세의 "이 리포트로 AI에게 질문하기" (P25, API 명세 2.4). 분석 대화 API를 그대로 쓴다.
 * - 일일 리포트(reportId): 서버가 그 리포트의 자녀·대상일·판으로 대화를 고정한다. 다른 날 질문은 새 대화로 안내된다.
 * - 주간 리포트: 리포트 기간으로 대화를 만든다.
 * 프리미엄 전용이고 분석 대화 하루 한도를 함께 쓴다. 자녀·리포트가 바뀌면 부모가 key를 바꿔 새로 만든다.
 */
export function ReportChat({
  child,
  scope,
  reportId,
  onAnalysis,
}: {
  child: Child
  scope: Scope
  reportId?: string
  onAnalysis: (p: Period) => void
}) {
  const [question, setQuestion] = useState(''),
    [turns, setTurns] = useState<Turn[]>([]),
    [state, setState] = useState<StreamState>({ phase: 'IDLE', temporary: '' }),
    [error, setError] = useState<unknown>(null),
    conversation = useRef<string | null>(null),
    controller = useRef<AbortController | null>(null),
    active = useRef(true)
  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
      controller.current?.abort()
    }
  }, [])

  async function ask(text: string, selectedScope: Scope = scope) {
    if (!text.trim()) return
    controller.current?.abort()
    const abort = new AbortController()
    controller.current = abort
    setError(null)
    setState({ phase: 'RUNNING', temporary: '' })
    setTurns((t) => [...t, { question: text }])
    try {
      if (!conversation.current) {
        const c = reportId ? await parentApi.createForReport(child.id, reportId) : await parentApi.create(selectedScope)
        if (!active.current || abort.signal.aborted) return
        conversation.current = c.conversationId
      }
      let last: StreamState = { phase: 'RUNNING', temporary: '' }
      await parentApi.message(
        conversation.current,
        text,
        selectedScope,
        (s) => {
          last = s
          if (active.current && !abort.signal.aborted) setState(s)
        },
        abort.signal,
      )
      if (!active.current || abort.signal.aborted) return
      setQuestion('')
      if (last.result) {
        const result = last.result
        setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, result } : turn)))
      }
    } catch (e) {
      if (!active.current || abort.signal.aborted) return
      setError(e)
      setState({ phase: 'FAILED', temporary: '' })
    }
  }

  if (child.plan === 'FREE')
    return (
      <p className="ws-card">
        이 리포트로 AI에게 질문하기는 프리미엄 기능입니다. 무료 플랜에서도 리포트 내용은 그대로 확인할 수 있습니다.
      </p>
    )
  const pending = state.phase === 'RUNNING'
  const fixedDay = reportId && scope.from === scope.to ? scope.from : null
  return (
    <section className="ws-card ws-report-chat" aria-label="이 리포트로 AI에게 질문하기">
      <h2>이 리포트로 AI에게 질문하기</h2>
      <p>AI 챗봇에 이 리포트의 자녀와 기간을 연결해 질문합니다. 같은 대화 기능과 하루 이용 한도를 사용합니다.</p>
      <p>
        {fixedDay
          ? `${fixedDay} 하루 리포트와 그날 학습 기록으로만 답합니다. 다른 날은 그날 리포트에서 새로 물어봐 주세요.`
          : `${scope.from} ~ ${scope.to} 기록으로 답합니다.`}{' '}
        숫자와 아이 글 인용은 기록과 맞춰 본 답만 보여 줍니다.
      </p>
      {turns.map((turn, i) => (
        <article className="ws-card" key={i}>
          <h3>보호자의 질문</h3>
          <p>{turn.question}</p>
          {turn.result ? <ReportChatAnswer result={turn.result} /> : null}
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
          {fixedDay ? (
            <p>이 대화는 {fixedDay} 리포트로 고정되어 있습니다. 다른 날은 리포트 목록에서 그날 리포트를 열어 물어봐 주세요.</p>
          ) : (
            state.clarification.options.map((option, i) => (
              <button
                className="cj-secondary"
                key={i}
                disabled={option.scope.childId !== child.id}
                onClick={() => {
                  const last = turns[turns.length - 1]
                  if (last) void ask(last.question, option.scope)
                }}
              >
                {option.label}
              </button>
            ))
          )}
        </section>
      )}
      <ErrorNotice error={error} />
      <form
        className="ws-form"
        onSubmit={(e) => {
          e.preventDefault()
          void ask(question)
        }}
      >
        <label>
          리포트에 대한 질문
          <textarea
            aria-label="리포트에 대한 질문"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              // Enter는 보내기, Shift+Enter는 줄바꿈. 한글 조합 중 Enter는 글자 확정이라 보내지 않음
              if (e.key !== 'Enter' || e.shiftKey || e.nativeEvent.isComposing) return
              e.preventDefault()
              if (!pending) void ask(question)
            }}
            placeholder={
              fixedDay
                ? '이날 되묻기 뒤에 어떤 말이 더해졌나요? (Enter 보내기 · Shift+Enter 줄바꿈)'
                : '이번 주에 되묻기 뒤 어떤 말이 더해졌나요? (Enter 보내기 · Shift+Enter 줄바꿈)'
            }
            maxLength={1000}
            required
          />
        </label>
        <div className="ws-actions">
          <button className="cj-primary" disabled={pending}>
            질문하기
          </button>
          {!fixedDay && (
            <button
              type="button"
              className="cj-secondary"
              onClick={() => onAnalysis({ from: scope.from, to: scope.to })}
            >
              AI 챗봇에서 이어 보기
            </button>
          )}
        </div>
      </form>
    </section>
  )
}

function ReportChatAnswer({ result }: { result: MessageResult }) {
  const v = result.verification
  if (!v?.numbersMatched || !v.quotesMatched || v.contentAllowed === false)
    return <p>확정 답변 없음 · 결과 검증이 필요합니다.</p>
  return (
    <>
      <p>{result.answer}</p>
      {(result.fallback || result.notice) && <p className="ws-tag">{analysisResultLabel(result)}</p>}
      <small>
        출처 {result.source} · 조회 기록 {result.recordCount}건
      </small>
    </>
  )
}
