import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useMemoryExplanation, useMemorySearch } from '../../../data/memory/queries.ts'
import type { Child } from '../../../domain/classroom.ts'
import { MEMORY_EXAMPLES, MEMORY_QUERY_MAX, explanationAttempts, explanationSentences, memoryFailure, memoryQuery } from '../../../domain/memory.ts'
import type { MemoryCard } from '../../../domain/memory.ts'
import { weekLabel } from '../../../domain/retention.ts'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import { Companion } from './Companion.tsx'
import { useLook } from './lookContext.ts'
import './memory.css'

/**
 * 추억 앨범 위 "기억으로 찾기"(P27·FN-RET-12·13, api-spec 2.12, #567, 시안 Album).
 * 검색과 설명은 따로 둔다: 설명이 실패해도 찾은 카드는 그대로 남는다(대체 문장 없음, FN-RET-13).
 * 둘 다 하루 횟수(찾기 20·설명 10)를 쓰므로 누를 때만 부른다.
 */
export function MemorySearch({ child, onOpen }: {
  child: Child
  onOpen: (card: { themeId: string; weekStart: string }) => void
}) {
  const { companion, worn } = useLook()
  const search = useMemorySearch(child.id)
  const explain = useMemoryExplanation(child.id)
  const [text, setText] = useState('')
  const [asked, setAsked] = useState('')
  const [invalid, setInvalid] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const cardRefs = useRef(new Map<string, HTMLLIElement>())

  const run = (q: string) => {
    explain.reset()
    setAsked(q)
    search.mutate(q)
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const q = memoryQuery(text)
    setInvalid(!q)
    if (q) run(q)
  }
  const fillExample = (example: string) => {
    setText(example)
    setInvalid(false)
    input.current?.focus()
  }

  const result = search.isPending || search.error ? undefined : search.data
  const cards = result?.state === 'RESULTS' ? result.cards : []
  // 설명 요청에 보내는 시도(카드마다 맨 앞 문제)와 그 번호. 설명 글의 [n]이 이 번호를 가리킨다
  const sent = explanationAttempts(cards)
  const numberOf = (attemptId: string) => sent.indexOf(attemptId) + 1
  const cardOf = (attemptId: string) => cards.find((c) => c.missions.some((m) => m.attemptId === attemptId))
  const focusCard = (attemptId: string) => {
    const card = cardOf(attemptId)
    const el = card ? cardRefs.current.get(cardKey(card)) : undefined
    el?.scrollIntoView({ block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
    el?.focus()
  }
  const searchFailure = search.error ? memoryFailure(search.error) : null
  const explanation = explain.isPending || explain.error ? undefined : explain.data
  const explainFailure = explain.error ? memoryFailure(explain.error) : null
  const sentences = explanation ? explanationSentences(explanation) : []
  // 설명(또는 설명 실패 안내)이 오면 카드 아래 그 자리가 보이게 옮긴다(카드가 길면 화면 밖에 생김)
  const said = useRef<HTMLDivElement>(null)
  const settled = !!explanation || !!explain.error
  useEffect(() => {
    if (settled) said.current?.scrollIntoView({ block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
  }, [settled])

  return (
    <section className="st-memory" aria-labelledby="memory-find-h">
      <h2 id="memory-find-h">기억으로 찾기</h2>
      <form className="st-memory-form" role="search" onSubmit={submit} noValidate>
        <label htmlFor="memory-q" className="st-visually-hidden">찾고 싶은 기억</label>
        <input
          id="memory-q"
          ref={input}
          type="search"
          maxLength={MEMORY_QUERY_MAX}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={`예: ${MEMORY_EXAMPLES[0]}`}
          aria-invalid={invalid || undefined}
          aria-describedby={invalid ? 'memory-q-error' : 'memory-q-note'}
        />
        <button type="submit" className="st-memory-go" disabled={search.isPending}>{search.isPending ? '찾는 중…' : '찾기'}</button>
      </form>
      {invalid && <p id="memory-q-error" role="alert" className="st-memory-error">찾고 싶은 기억을 한 글자 이상 써 주세요.</p>}
      <div className="st-memory-examples">
        <span className="st-memory-ex-label" id="memory-ex-label">예시</span>
        <ul aria-labelledby="memory-ex-label">
          {MEMORY_EXAMPLES.map((ex) => (
            <li key={ex}>
              <button type="button" onClick={() => fillExample(ex)} aria-label={`예시 질문 넣기: ${ex}`}>{ex}</button>
            </li>
          ))}
        </ul>
      </div>
      <p id="memory-q-note" className="st-memory-note">찾기는 하루 20번, 설명은 하루 10번까지예요. 방금 끝낸 문제는 조금 뒤에 찾을 수 있어요. 질문과 설명은 저장하지 않아요.</p>

      <div className="st-memory-result" aria-live="polite">
        {search.isPending && <p role="status" className="st-memory-box">기억을 찾고 있어요.</p>}
        {searchFailure?.kind === 'LIMIT' && (
          <p role="status" className="st-memory-box" data-tone="soft">{searchFailure.detail ?? '오늘은 다 찾았어요. 내일 다시 찾아볼 수 있어요.'}</p>
        )}
        {searchFailure?.kind === 'UNAVAILABLE' && (
          <div role="status" className="st-memory-box" data-tone="warn">
            <p>지금은 찾기가 잠시 쉬고 있어요. 조금 뒤에 다시 찾거나 아래 앨범에서 직접 골라 볼까요?</p>
            <button type="button" className="st-pill-link" onClick={() => run(asked)}>다시 찾기</button>
          </div>
        )}
        {searchFailure?.kind === 'INVALID' && (
          <p role="status" className="st-memory-box" data-tone="warn">질문을 다시 확인해 주세요. 1~200자로 쓸 수 있어요.</p>
        )}
        {searchFailure?.kind === 'OTHER' && <ErrorNotice error={search.error} />}
        {result?.state === 'NO_RECORDS' && (
          <p role="status" className="st-memory-box">아직 기념 액자가 없어서 찾을 기억이 없어요. 한 주 테마 문제 다섯 개를 모두 마무리하면 찾을 수 있어요.</p>
        )}
        {result?.state === 'NO_RESULTS' && (
          <p role="status" className="st-memory-box">비슷한 기억을 찾지 못했어요. 다른 말로 바꾸거나 언제쯤이었는지(예: 지난달) 넣어 찾아봐요. 방금 끝낸 문제는 조금 뒤에 찾을 수 있어요.</p>
        )}
        {cards.length > 0 && (
          <div className="st-memory-found st-scroll">
            <div className="st-memory-found-head">
              <strong>「{asked}」와 가까운 주 {cards.length}개</strong>
              <button type="button" className="st-memory-explain" onClick={() => explain.mutate({ query: asked, attemptIds: sent })}
                disabled={explain.isPending || !!explanation}>
                {explain.isPending ? '뭉치가 생각하는 중…' : '뭉치에게 설명 듣기'}
              </button>
            </div>
            <ol className="st-memory-cards" aria-label="찾은 주">
              {cards.map((card) => (
                <li key={cardKey(card)} tabIndex={-1} ref={(el) => { if (el) cardRefs.current.set(cardKey(card), el); else cardRefs.current.delete(cardKey(card)) }}>
                  <span className="st-memory-frame" aria-hidden="true">
                    {card.imageUrl ? <img src={card.imageUrl} alt="" /> : <span className="st-memory-frame-empty" />}
                  </span>
                  <div className="st-memory-card-body">
                    <span className="st-memory-week">{weekLabel(card.weekStart)}</span>
                    <strong>{card.title || '이름 없는 테마'}</strong>
                    <ul aria-label={`${card.title || '이 주'}에서 찾은 문제`}>
                      {card.missions.slice(0, CARD_MISSIONS).map((m) => {
                        const no = numberOf(m.attemptId)
                        return (
                          <li key={m.attemptId}>
                            <span className="st-memory-no" aria-label={no ? `근거 ${no}` : undefined} aria-hidden={no ? undefined : true}>{no || '·'}</span>
                            <span><b>{m.title || '문제'}</b>{m.answerExcerpt && <span>내 답 일부 · {m.answerExcerpt}</span>}</span>
                          </li>
                        )
                      })}
                    </ul>
                    {card.missions.length > CARD_MISSIONS && (
                      <span className="st-memory-more">이 주에서 {card.missions.length - CARD_MISSIONS}문제 더 찾았어요</span>
                    )}
                    <button type="button" className="st-pill-link" onClick={() => onOpen(card)}>그때 기록 보기 →</button>
                  </div>
                </li>
              ))}
            </ol>
            <div ref={said} className="st-memory-said">
            {explain.isPending && <p role="status" className="st-memory-box">뭉치가 기록을 읽고 있어요.</p>}
            {explanation?.state === 'GENERATED' && (
              <div className="st-memory-say">
                <Companion kind={companion} worn={worn} size={64} decorative />
                <p>
                  {sentences.map((s, i) => (
                    <span key={i}>
                      {s.text}
                      {s.citations.map((c) => (
                        <button key={c.no} type="button" className="st-memory-cite" onClick={() => focusCard(c.attemptId)}
                          aria-label={`근거 ${c.no}: ${cardOf(c.attemptId)?.title || '찾은 주'} 카드로`}>[{c.no}]</button>
                      ))}
                      {i < sentences.length - 1 ? ' ' : ''}
                    </span>
                  ))}
                </p>
              </div>
            )}
            {explanation?.state === 'INSUFFICIENT' && (
              <p role="status" className="st-memory-box">이 기록만으로는 설명하기 어려워요. 카드를 눌러 그때 기록을 직접 볼까요?</p>
            )}
            {(explanation?.state === 'FAILED' || explainFailure?.kind === 'INVALID' || explainFailure?.kind === 'OTHER') && (
              <p role="status" className="st-memory-box" data-tone="warn">지금은 설명을 만들지 못했어요. 찾은 기록은 그대로 볼 수 있어요.</p>
            )}
            {explainFailure?.kind === 'UNAVAILABLE' && (
              <div role="status" className="st-memory-box" data-tone="warn">
                <p>지금은 설명을 만들지 못했어요. 찾은 기록은 그대로 볼 수 있어요.</p>
                <button type="button" className="st-pill-link" onClick={() => explain.mutate({ query: asked, attemptIds: sent })}>다시 듣기</button>
              </div>
            )}
            {explainFailure?.kind === 'LIMIT' && (
              <p role="status" className="st-memory-box" data-tone="soft">{explainFailure.detail ?? '오늘은 설명을 다 들었어요. 내일 다시 들을 수 있어요.'}</p>
            )}
            </div>
          </div>
        )}
      </div>
    </section>
  )
}

const cardKey = (c: MemoryCard) => `${c.themeId}@${c.weekStart}`
/** 카드에 보이는 문제 수(시안 Album은 1~2개). 맨 앞이 설명 근거로 보내는 문제라 늘 보인다. 나머지는 회차 상세에서 */
const CARD_MISSIONS = 2
