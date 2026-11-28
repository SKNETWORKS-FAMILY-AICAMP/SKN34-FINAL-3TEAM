import test from 'node:test'
import assert from 'node:assert/strict'
import { STUDENT_START_BLOCKED, startBlockedMessage } from '../src/domain/studentStart.ts'

// #1093 추가 문제 시작이 막혔을 때 아이에게 보일 말: 한도(429)·프리미엄(403)만 아이 말로 바꾸고, 이용권·결제·KST 같은 말은 넣지 않는다
const NO_ADULT_WORDS = /결제|구매|이용권|프리미엄|KST|시도/

test('한도·프리미엄 막힘은 아이 말로 바꾼다', () => {
  assert.equal(startBlockedMessage({ problem: { code: 'USAGE_LIMIT_REACHED', status: 429 } }), STUDENT_START_BLOCKED.USAGE_LIMIT_REACHED)
  assert.equal(startBlockedMessage({ problem: { code: 'PREMIUM_REQUIRED', status: 403 } }), STUDENT_START_BLOCKED.PREMIUM_REQUIRED)
  for (const text of Object.values(STUDENT_START_BLOCKED)) assert.doesNotMatch(text, NO_ADULT_WORDS)
})

test('그 밖의 오류는 바꾸지 않는다(공통 오류 상자가 보인다)', () => {
  for (const error of [null, undefined, new Error('x'), { problem: { code: 'THEME_DAY_CLOSED' } }, { problem: {} }])
    assert.equal(startBlockedMessage(error), null)
})
