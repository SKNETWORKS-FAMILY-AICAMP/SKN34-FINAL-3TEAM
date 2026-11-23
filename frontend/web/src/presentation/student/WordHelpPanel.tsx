import { useEffect, useRef, useState } from 'react'
import type { CompanionId } from '../../domain/studentLook.ts'
import { companionLabel } from '../../domain/studentLook.ts'
import type { WordHelp, WordSense } from '../../domain/learning.ts'
import { WORD_QUESTION_MAX } from '../../domain/learning.ts'
import { useAskWord } from '../../data/classroom/useClassroom.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import { SpeechBubble } from './world/SpeechBubble.tsx'

type Turn = { id: number; question: string; answer: WordHelp }
const KEEP = 5

function SenseSource({ sense, adapted = false }: { sense: WordSense; adapted?: boolean }) {
  const name = sense.attribution ?? sense.source
  return <small className="st-word-cite">
    출처: {sense.sourceUrl?.startsWith('https://')
      ? <a href={sense.sourceUrl} target="_blank" rel="noopener noreferrer">{name}</a>
      : name}
    {sense.license?.startsWith('https://') && <>
      {' · '}<a href={sense.license} target="_blank" rel="noopener noreferrer">
        {sense.license.includes('creativecommons.org') ? 'CC BY-SA 2.0 KR' : '공공누리 1유형'}
      </a>
      {adapted && ' · 쉬운 말로 바꿈'}
    </>}
  </small>
}

/**
 * 낱말 물어보기 (FN-LRN-21, #599). 동행 캐릭터가 국립국어원 사전 뜻을 쉬운 말로 알려 준다.
 * 묻고 답한 내용은 이 화면에만 두고 저장하지 않는다(최근 5개). 작성 중인 답·초안은 건드리지 않는다.
 */
export function WordHelpPanel({ attemptId, companion }: { attemptId: string; companion: CompanionId }) {
  const ask = useAskWord(attemptId)
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const serial = useRef(0)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => { input.current?.focus() }, [])
  const name = companionLabel(companion)
  function send() {
    const text = question.trim()
    if (!text || ask.isPending) return
    void ask.mutateAsync(text).then(answer => {
      setTurns(list => [...list, { id: ++serial.current, question: text, answer }].slice(-KEEP))
      setQuestion('')
    }).catch(() => {})
  }
  return <section id="student-word-help" className="st-word-help" aria-label="낱말 물어보기">
    <p className="st-meta">문제에서 모르는 낱말을 적어 봐. 사전에서 찾아 쉬운 말로 알려 줄게.</p>
    <ol className="st-word-turns" aria-live="polite">
      {turns.map(turn => <li key={turn.id}>
        <p className="st-word-me"><span className="st-visually-hidden">내 질문</span>{turn.question}</p>
        <SpeechBubble tail="left" className="sw-bubble st-word-answer">
          <span className="st-visually-hidden">{name}의 대답</span>
          {turn.answer.headword && turn.answer.state !== 'NOT_FOUND' && <strong>{turn.answer.headword}</strong>}
          <p>{turn.answer.text}</p>
          {turn.answer.example && <p className="st-word-example">예: {turn.answer.example}</p>}
          {turn.answer.state === 'DICTIONARY_ONLY'
            ? <ul className="st-word-source">{turn.answer.senses.map((sense, index) => <li key={index}>{sense.definition} <SenseSource sense={sense} /></li>)}</ul>
            : turn.answer.senses.length > 0 && <>
              <SenseSource sense={turn.answer.senses[0]} adapted />
              <details className="st-word-source">
                <summary>사전에 적힌 뜻 보기</summary>
                <p>{turn.answer.senses[0].definition}</p>
              </details>
            </>}
        </SpeechBubble>
      </li>)}
    </ol>
    {ask.isPending && <p role="status">사전을 찾고 있어요.</p>}
    <ErrorNotice error={ask.error} retry={send} />
    <form className="st-word-form" onSubmit={event => { event.preventDefault(); send() }}>
      <label>
        <span className="st-visually-hidden">물어볼 낱말</span>
        <input ref={input} value={question} maxLength={WORD_QUESTION_MAX} placeholder="예: 분수가 뭐야?" aria-label="물어볼 낱말"
          onChange={event => setQuestion(event.target.value)} />
      </label>
      <button type="submit" className="st-button st-primary" disabled={!question.trim() || ask.isPending}>물어보기</button>
    </form>
  </section>
}
