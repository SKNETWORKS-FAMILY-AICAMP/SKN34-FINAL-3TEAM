import test from 'node:test'
import assert from 'node:assert/strict'
import { ApiError } from '../src/data/apiClient.ts'
import { getAttemptComparison } from '../src/data/classroom/learningApi.ts'
import { comparisonAnswerText } from '../src/domain/learning.ts'
import type { AttemptComparison, ComparisonSnapshot } from '../src/domain/learning.ts'

const mission: ComparisonSnapshot['mission'] = { title: '합성 미션', question: '질문', inputType: 'CHOICE',
  choices: [{ id: 'c1', label: '이전 선택지' }], categories: [{ id: 'g1', label: '첫 그룹' }], answerUnit: 'm²' }
const snapshot = (id: string): ComparisonSnapshot => ({ attemptId: id, finishedAt: '2026-11-01T01:00:00Z',
  mission, judgment: 'PARTIAL', answers: [{ answerId: id + '-a1', version: 1, text: '합성 답', content: { text: '합성 답' } }], elements: [] })
const comparison = (): AttemptComparison => ({ attemptId: 'current', state: 'COMPARABLE',
  previous: snapshot('previous'), current: snapshot('current'), elements: [{ elementId: 'e1', label: '까닭',
    previousSatisfied: false, currentSatisfied: true, change: 'ADDED' }] })

test('비교 API는 이전 원문·판정 보류·문제 버전을 바꾸지 않고 no-store로 조회한다', async t => {
  const value = comparison()
  value.previous!.judgment = 'HELD'
  value.previous!.mission = { ...mission, question: '예전 질문' }
  let requested: RequestInit | undefined
  t.mock.method(globalThis, 'fetch', async (_url: string, init: RequestInit) => { requested = init; return Response.json(value) })
  assert.deepEqual(await getAttemptComparison('current'), value)
  assert.equal(requested?.cache, 'no-store')
})

test('비교 계약은 타 시도 응답·거짓 변화·잘못된 시각·이전 결과 누락을 거부한다', async t => {
  const wrongId = comparison(); wrongId.current.attemptId = 'other'
  const falseChange = comparison(); falseChange.elements[0].change = 'RETAINED'
  const badTime = comparison(); badTime.previous!.finishedAt = 'invalid'
  const missing = comparison(); missing.previous = null
  const changed = comparison(); changed.state = 'CRITERIA_CHANGED'
  for (const value of [wrongId, falseChange, badTime, missing, changed]) {
    t.mock.method(globalThis, 'fetch', async () => Response.json(value))
    await assert.rejects(() => getAttemptComparison('current'), (e: unknown) => e instanceof ApiError && e.problem.code === 'CONTRACT_NOT_READY')
  }
  const first = { ...comparison(), state: 'NO_PREVIOUS', previous: null, elements: [] }
  t.mock.method(globalThis, 'fetch', async () => Response.json(first))
  assert.equal((await getAttemptComparison('current')).state, 'NO_PREVIOUS')
})

test('선택·분류·풀이·논술 답변은 각각의 시도에 고정된 문항으로 표시한다', () => {
  const answer = (content: Record<string, unknown>) => ({ answerId: 'a', version: 1, text: null, content })
  assert.equal(comparisonAnswerText(answer({ choiceIds: ['c1'] }), mission), '이전 선택지')
  assert.equal(comparisonAnswerText(answer({ assignments: [{ choiceId: 'c1', categoryId: 'g1' }] }), mission), '이전 선택지: 첫 그룹')
  assert.equal(comparisonAnswerText(answer({ finalAnswer: '30', steps: ['3 × 10'] }), mission), '30m²\n3 × 10')
  assert.equal(comparisonAnswerText(answer({ essay: { claim: '주장', reasons: ['까닭'], rebuttal: '다른 생각' } }), mission), '주장\n까닭\n다른 생각')
  assert.equal(comparisonAnswerText(answer({ assignments: [null] }), mission), '')
})
