import test from 'node:test'
import assert from 'node:assert/strict'
import { assertVerifiedAnalysis, analysisResultLabel, reduceAnalysis } from '../src/domain/parent.ts'
import type { MessageResult } from '../src/domain/parent.ts'
const final = { numbersMatched: true, quotesMatched: true, contentAllowed: true }
const result: MessageResult = { messageId: 'm', answer: '최종 확인 문장', scope: { childId: 's', from: '2026-10-20', to: '2026-10-26' }, metrics: [], evidence: [], recordCount: 0, source: 'LLM', verification: final }
test('최종 검증과 초안 실패를 구분하고 임시 delta를 교체한다', () => {
  const value: MessageResult = { ...result, source: 'TEMPLATE', fallback: { reason: 'VERIFICATION_FAILED', draftVerification: { ...final, numbersMatched: false } } }
  const state = reduceAnalysis({ phase: 'RUNNING', temporary: '검증 전 초안' }, { event: 'result', data: value })
  assert.equal(state.temporary, '')
  assert.equal(state.result?.answer, value.answer)
  assert.equal(state.result?.fallback?.draftVerification?.numbersMatched, false)
  assert.match(analysisResultLabel(value), /초안 대조 실패/)
})
test('정상 안내와 AI 장애는 서로 다른 출처 설명을 사용한다', () => {
  const notice: MessageResult = { ...result, source: 'TEMPLATE', notice: { reason: 'NO_RECORD' } }
  assert.doesNotThrow(() => assertVerifiedAnalysis(notice))
  assert.equal(analysisResultLabel(notice), '기록 없음 안내')
  assert.match(analysisResultLabel({ source: 'TEMPLATE', fallback: { reason: 'AI_UNAVAILABLE', draftVerification: null } }), /AI 응답 불가/)
})
test('최종 미검증과 모순된 출처는 거부한다', () => {
  assert.throws(() => assertVerifiedAnalysis({ ...result, verification: { ...final, contentAllowed: false } }))
  assert.throws(() => assertVerifiedAnalysis({ ...result, source: 'TEMPLATE' }))
  assert.throws(() => assertVerifiedAnalysis({ ...result, notice: { reason: 'NO_RECORD' } }))
  assert.throws(() => assertVerifiedAnalysis({ ...result, source: 'TEMPLATE', fallback: { reason: 'VERIFICATION_FAILED', draftVerification: final } }))
  assert.throws(() => assertVerifiedAnalysis({ ...result, source: 'TEMPLATE', notice: { reason: 'NO_RECORD' }, fallback: { reason: 'AI_UNAVAILABLE', draftVerification: null } }))
})
