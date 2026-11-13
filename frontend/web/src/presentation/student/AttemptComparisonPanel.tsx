import type { Attempt } from '../../domain/classroom.ts'
import { comparisonAnswerText, comparisonLabels } from '../../domain/learning.ts'
import { useAttemptComparison } from '../../data/classroom/useClassroom.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import './learning-settings.css'

const judgmentLabels = { CORRECT: '확인했어요', PARTIAL: '생각을 더 보탰어요', RETHINK: '다시 살펴봐요', HELD: '판정 보류' }
export function AttemptComparisonPanel({ attempt }: { attempt: Attempt }) {
  const query = useAttemptComparison(attempt)
  if (!attempt.finishedAt) return null
  const value = query.error ? undefined : query.data
  return <section className="st-comparison" aria-label="이전 답과 이번 답 비교">
    <h3>이전 답과 나란히 볼까요?</h3>
    {query.isPending && <p role="status">이전에 마무리한 같은 미션을 찾고 있어요.</p>}
    <ErrorNotice error={query.error} retry={() => void query.refetch()} />
    {value?.state === 'NO_PREVIOUS' && <p>처음 끝낸 답이에요. 다시 풀면 나란히 볼 수 있어요.</p>}
    {value?.previous && <>
      <p>바로 전에 쓴 답과 나란히 보여 줄게요.</p>
      <div className="st-comparison-pair">{[value.previous, value.current].map((snapshot, index) => <article key={snapshot.attemptId}>
        <h4>{index === 0 ? '이전 답' : '이번 답'}</h4>
        <p>{snapshot.mission.question}</p>
        <p className="st-comparison-meta">{new Date(snapshot.finishedAt).toLocaleDateString('ko-KR', { timeZone: 'Asia/Seoul' })} 마무리 · {snapshot.judgment ? judgmentLabels[snapshot.judgment] : '판정 없음'}</p>
        {snapshot.answers.map(answer => <div key={answer.answerId}><small>답변 {answer.version}</small><blockquote>{comparisonAnswerText(answer, snapshot.mission)}</blockquote></div>)}
      </article>)}</div>
      {value.state === 'CRITERIA_CHANGED' ? <p role="status">문제가 조금 바뀌었어요. 두 답을 읽고 달라진 점을 찾아보세요.</p>
        : <ul className="st-comparison-elements">{value.elements.map(element => <li key={element.elementId}>
          <strong>{element.label}</strong><span>{comparisonLabels[element.change]}</span>
        </li>)}</ul>}
    </>}
  </section>
}
