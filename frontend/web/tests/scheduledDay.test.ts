import test from 'node:test'
import assert from 'node:assert/strict'
import { scheduledDayLine } from '../src/domain/parent.ts'

test('예정 요일과 KST 완료일 구분, 이전 리포트와 추가 문제 표시 유지 (#845)', () => {
  for (const context of ['THEME_DAY', 'THEME_REVIEW'] as const) {
    assert.equal(scheduledDayLine({ context, scheduledDay: 'TUE' }, '2026-11-19'), '화요일 문제 · 목요일에 풀었어요')
    assert.equal(scheduledDayLine({ context, scheduledDay: 'FRI' }, '2026-11-22'), '금요일 문제 · 일요일에 풀었어요')
    assert.equal(scheduledDayLine({ context, scheduledDay: 'THU' }, '2026-11-19'), null)
    assert.equal(scheduledDayLine({ context }, '2026-11-19'), null)
    assert.equal(scheduledDayLine({ context, scheduledDay: null }, '2026-11-19'), null)
  }
  assert.equal(scheduledDayLine({ context: 'EXTRA', scheduledDay: 'TUE' }, '2026-11-19'), null)
})
