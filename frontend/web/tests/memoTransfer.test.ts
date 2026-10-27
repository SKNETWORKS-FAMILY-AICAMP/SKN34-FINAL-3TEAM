import test from 'node:test'
import assert from 'node:assert/strict'
import { blankAnswer } from '../src/domain/classroom.ts'
import { appendMemo, memoTargets } from '../src/domain/memoTransfer.ts'

for (const type of ['NARRATIVE', 'SOLUTION_STEPS', 'ESSAY'] as const) {
  test(`${type} 메모는 선택한 한 칸에만 덧붙이고 원본은 보존`, () => {
    const answer = blankAnswer(type)
    answer.text = '기존 생각'
    answer.finalAnswer = '6'
    answer.steps = ['첫 풀이', '둘째 풀이']
    answer.essay = { claim: '주장', reasons: ['첫 까닭', '둘째 까닭'], rebuttal: '다른 의견' }
    answer.dictatedByGuardian = true
    const before = structuredClone(answer)
    for (const t of memoTargets(answer)) {
      const result = appendMemo(answer, '덧붙일 메모', t.id)
      assert.deepEqual(answer, before)
      assert.equal(result.dictatedByGuardian, true)
      const serialized = JSON.stringify(result)
      assert.equal(serialized.split('덧붙일 메모').length - 1, 1)
      assert.equal('memo' in result, false)
      const read = (v: typeof answer) => t.id === 'text' ? v.text : t.id === 'finalAnswer' ? v.finalAnswer
        : t.id.startsWith('step:') ? v.steps[Number(t.id.split(':')[1])]
        : t.id.startsWith('reason:') ? v.essay.reasons[Number(t.id.split(':')[1]) as 0 | 1]
        : v.essay[t.id as 'claim' | 'rebuttal']
      assert.equal(read(result), `${read(answer)}\n덧붙일 메모`)
    }
  })
}
test('빈 메모·잘못된 대상·초과 길이는 잘라 넣지 않고 거부', () => {
  const a = blankAnswer('SOLUTION_STEPS')
  a.finalAnswer = '기존 답'
  assert.throws(() => appendMemo(a, ' ', 'finalAnswer'), /먼저 적어/)
  assert.throws(() => appendMemo(a, 'a'.repeat(120), 'finalAnswer'), /120자/)
  assert.equal(a.finalAnswer, '기존 답')
  assert.throws(() => appendMemo(a, '메모', 'step:999'), /옮길 수 없습니다/)
  const empty = blankAnswer('SOLUTION_STEPS')
  assert.equal(appendMemo(empty, 'a'.repeat(120), 'finalAnswer').finalAnswer.length, 120)
})
for (const type of ['CHOICE', 'ORDERING', 'CLASSIFICATION'] as const) {
  test(`${type} 글 메모를 선택 답으로 자동 변환하지 않음`, () => {
    const a = blankAnswer(type)
    assert.deepEqual(memoTargets(a), [])
    assert.throws(() => appendMemo(a, '메모', 'text'), /옮길 수 없습니다/)
  })
}
