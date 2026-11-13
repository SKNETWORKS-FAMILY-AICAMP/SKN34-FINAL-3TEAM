import test from 'node:test'
import assert from 'node:assert/strict'
import { makeWeekly, makeDaily } from '../src/mocks/fixtures/parent.ts'
import { privateReport } from '../src/mocks/fixtures/sharing.ts'
import type { Child } from '../src/domain/classroom.ts'
import { setMockSubscription } from '../src/mocks/fixtures/payments.ts'

const child: Child = { id: 'explanation-synthetic-child', nickname: '검증 학생', grade: 5, birthYear: 2015 }
setMockSubscription(child.id, 'PREMIUM')
const period = { from: '2026-11-02', to: '2026-11-08' }

test('#481 목업: 대상 없는 주간은 NO_TARGET, 무료·일일은 null이며 기존 설명 필드는 null이다', () => {
  const report = makeWeekly(child, period)
  assert.deepEqual(report.explanations, { state: 'NO_TARGET', items: [] })
  assert.equal(report.narrative?.modelExplanation, null)
  assert.equal(makeWeekly({ ...child, id: 'explanation-free-child' }, period).explanations, null)
  assert.equal(makeDaily(child, period.from).explanations, null)
})

test('#481 목업: 비공개 응답은 저장된 설명·인용을 제거하고 수치는 유지한다', () => {
  const original = { ...makeWeekly(child, period), explanations: { state: 'INCLUDED' as const, items: [{ attemptId: 'a', answerId: 'b', answerVersion: 1,
    missionTitle: '합성 미션', thinkingType: 'ANALYZE' as const, quote: '목업 비공개 원문', text: '목업 비공개 설명' }] } }
  const hidden = privateReport(original)
  assert.deepEqual(hidden.explanations, { state: 'NO_TARGET', items: [] })
  assert.equal(JSON.stringify(hidden).includes('목업 비공개'), false)
  assert.deepEqual(hidden.metrics, original.metrics)
  assert.equal(original.explanations.items.length, 1)
})
