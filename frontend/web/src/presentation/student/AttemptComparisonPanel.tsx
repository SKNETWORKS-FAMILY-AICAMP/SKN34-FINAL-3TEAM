import { useQuery } from '@tanstack/react-query'
import type { Attempt } from '../../domain/classroom.ts'
import { comparisonAnswerText, comparisonLabels } from '../../domain/learning.ts'
import { getAttemptComparison } from '../../data/classroom/learningApi.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import './learning-settings.css'

const judgmentLabels = { CORRECT: '확인했어요', PARTIAL: '생각을 더 보탰어요', RETHINK: '다시 살펴봐요', HELD: '판정 보류' }
export function AttemptComparisonPanel({ attempt }: { attempt: Attempt }) {
  const query = useQuery({ queryKey: ['attempt-comparison', attempt.attemptId], enabled: !!attempt.finishedAt,
    retry: false, queryFn: ({ signal }) => getAttemptComparison(attempt.attemptId, signal) })
  if (!attempt.finishedAt) return null
  const value = query.error ? undefined : query.data
  return <section className="st-comparison" aria-label="이전 답과 이번 답 비교">
    <h3>이전 답과 나란히 볼까요?</h3>
    {query.isPending && <p role="status">이전에 마무리한 같은 미션을 찾고 있어요.</p>}
    <ErrorNotice error={query.error} retry={() => void query.refetch()} />
    {value?.state === 'NO_PREVIOUS' && <p>이 미션에서 처음 마무리한 답이에요. 다음에 다시 풀면 이번 답과 나란히 볼 수 있어요.</p>}
    {value?.previous && <>
      <p>같은 미션에서 바로 전에 마무리한 답과 비교합니다. 이전 답은 그대로 남아 있어요.</p>
      <div className="st-comparison-pair">{[value.previous, value.current].map((snapshot, index) => <article key={snapshot.attemptId}>
        <h4>{index === 0 ? '이전 답' : '이번 답'}</h4>
        <p>{snapshot.mission.question}</p>
        <p className="st-comparison-meta">{new Date(snapshot.finishedAt).toLocaleDateString('ko-KR', { timeZone: 'Asia/Seoul' })} 마무리 · {snapshot.judgment ? judgmentLabels[snapshot.judgment] : '판정 없음'}</p>
        {snapshot.answers.map(answer => <div key={answer.answerId}><small>답변 {answer.version}</small><blockquote>{comparisonAnswerText(answer, snapshot.mission)}</blockquote></div>)}
      </article>)}</div>
      {value.state === 'CRITERIA_CHANGED' ? <p role="status">문제나 확인 기준이 바뀌었어요. 두 답을 읽어 보되, 확인 항목의 개수로 비교하지 않습니다.</p>
        : <ul className="st-comparison-elements">{value.elements.map(element => <li key={element.elementId}>
          <strong>{element.label}</strong><span>{comparisonLabels[element.change]}</span>
        </li>)}</ul>}
    </>}
  </section>
}
