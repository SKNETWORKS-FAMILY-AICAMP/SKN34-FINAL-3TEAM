import type { AnswerContent } from './classroom.ts'

export interface MemoTarget {
  id: string
  label: string
  limit: number
}

export function memoTargets(answer: AnswerContent): MemoTarget[] {
  switch (answer.inputType) {
    case 'NARRATIVE':
      return [{ id: 'text', label: '내 생각과 까닭', limit: 2400 }]
    case 'SOLUTION_STEPS':
      return [
        { id: 'finalAnswer', label: '최종 답', limit: 120 },
        ...answer.steps.map((_, i) => ({ id: `step:${i}`, label: `풀이 ${i + 1}`, limit: 2400 })),
      ]
    case 'ESSAY':
      return [
        { id: 'claim', label: '내 주장', limit: 2400 },
        { id: 'reason:0', label: '첫 번째 까닭', limit: 2400 },
        { id: 'reason:1', label: '두 번째 까닭', limit: 2400 },
        { id: 'rebuttal', label: '다른 의견에 답하기', limit: 2400 },
      ]
    default:
      return []
  }
}

// 자동 요약/대필 없이, 학생이 고른 단 한 칸에만 원문을 복사합니다.
export function appendMemo(answer: AnswerContent, memo: string, targetId: string): AnswerContent {
  const target = memoTargets(answer).find((t) => t.id === targetId)
  if (!target) throw new Error('이 답변 칸에는 글 메모를 옮길 수 없습니다.')
  if (!memo.trim()) throw new Error('옮길 내용을 글 메모에 먼저 적어 주세요.')
  const result = structuredClone(answer)
  const append = (existing: string) => {
    const next = existing ? `${existing}\n${memo}` : memo
    if (next.length > target.limit)
      throw new Error(`${target.label}은 ${target.limit}자까지 적을 수 있습니다. 메모나 답변을 줄여 주세요. 기존 내용은 그대로 두었습니다.`)
    return next
  }
  if (targetId === 'text') result.text = append(result.text)
  else if (targetId === 'finalAnswer') result.finalAnswer = append(result.finalAnswer)
  else if (targetId.startsWith('step:')) {
    const i = Number(targetId.split(':')[1])
    result.steps[i] = append(result.steps[i])
  } else if (targetId.startsWith('reason:')) {
    const i = Number(targetId.split(':')[1]) as 0 | 1
    result.essay.reasons[i] = append(result.essay.reasons[i])
  } else if (targetId === 'claim' || targetId === 'rebuttal') {
    result.essay[targetId] = append(result.essay[targetId])
  }
  return result
}
