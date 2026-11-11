import test from 'node:test'
import assert from 'node:assert/strict'
import type { Metric } from '../src/domain/classroom.ts'
import type { ConversationMessage, WeeklyReport } from '../src/domain/parent.ts'
import { emptyReportTargets, reportTargets, verifiedReportAnswer } from '../src/domain/reportHighlight.ts'
import type { ReportHighlight } from '../src/domain/reportHighlight.ts'

const period = { from: '2026-11-09', to: '2026-11-15' }
const metric: Metric = { label: '학습한 활동', formula: '기간 내 답변 제출이 있는 시도 수', count: 6, numerator: 6, denominator: 6, value: null, period, sourceType: 'RECORD', state: 'OK' }
const message: ConversationMessage = { messageId: 'm1', question: '어떤 활동을 했나요?', answer: '기록을 확인했습니다.', status: 'COMPLETED', scope: { childId: 'child', ...period }, metrics: [metric], verification: { numbersMatched: true, quotesMatched: true, contentAllowed: true } }
function report(): WeeklyReport {
  return { reportId: 'r1', revision: 2, childId: 'child', period, periodType: 'WEEKLY', status: 'COMPLETED', state: 'OK', parentSharingEnabled: true,
    revisions: [{ revision: 2 }], inclusionRule: '검사용 기록', metrics: [metric], thinkingTypes: [], changes: [], reflections: [], quotes: [], narrative: null, verification: { numbersMatched: true, quotesMatched: true } }
}
function highlight(): ReportHighlight {
  return { reportId: 'r1', revision: 2, childId: 'child', period, periodType: 'WEEKLY', messageId: 'm1', question: message.question, metrics: [metric], evidence: [] }
}
test('완료·최종 검증·자녀·실제 기간이 확인된 답변만 연결한다', () => {
  assert.equal(verifiedReportAnswer(message, 'child'), true)
  for (const value of [
    { ...message, status: 'RUNNING' as const }, { ...message, answer: undefined }, { ...message, metrics: undefined },
    { ...message, verification: { numbersMatched: true, quotesMatched: true, contentAllowed: false } },
    { ...message, scope: { childId: 'other', ...period } }, { ...message, scope: { childId: 'child', from: '2026-02-30', to: period.to } },
  ]) assert.equal(verifiedReportAnswer(value, 'child'), false)
})
test('다른 판·자녀·기간·비공개·미검증 리포트는 강조하지 않는다', () => {
  for (const value of [
    { ...report(), revision: 1 }, { ...report(), reportId: 'other' }, { ...report(), childId: 'other' },
    { ...report(), period: { ...period, to: '2026-11-16' } }, { ...report(), parentSharingEnabled: false },
    { ...report(), parentSharingEnabled: undefined }, { ...report(), status: 'FAILED' as const },
    { ...report(), verification: { numbersMatched: false, quotesMatched: true } },
  ]) assert.deepEqual(reportTargets(value, highlight()), emptyReportTargets())
})
test('같은 수치라도 다른 계산식·기간·출처·분모의 항목은 연결하지 않는다', () => {
  const r = report()
  r.metrics.push(...[
    { ...metric, label: '다른 지표' }, { ...metric, formula: '다른 집계식' },
    { ...metric, period: { ...period, from: '2026-11-08' } }, { ...metric, sourceType: 'RULE' as const },
    { ...metric, denominator: 7 }, { ...metric, count: NaN }, { ...metric, value: Infinity },
  ])
  assert.deepEqual(reportTargets(r, highlight()).metrics, [0])
})
test('기존 집계 정의가 같은 learning·report 이름만 연결하고 완료 기준이 다른 지표는 제외한다', () => {
  const r = report(), h = highlight()
  r.metrics = [{ ...metric, label: '답변 제출 시도 수', formula: '집계 대상 시도 수' },
    { ...metric, label: '도움 없이 시작한 비율', formula: '최초 답변 전 도움 열람 없는 시도 수 / 집계 대상 시도 수', value: 1 },
    { ...metric, label: '완료한 시도 수', formula: '조회 종료일까지 완료한 집계 대상 시도 수' }]
  h.metrics.push({ ...metric, label: '도움 없이 시작한 활동', formula: '최초 답변 전 생각 열기를 열지 않은 시도 수 / 집계 대상 시도 수', value: 1 },
    { ...metric, label: '완료한 활동', formula: '돌아보기까지 마친 시도 수 / 집계 대상 시도 수', value: 1 })
  assert.deepEqual(reportTargets(r, h).metrics, [0, 1])
  h.metrics[1].value = 0.5
  assert.deepEqual(reportTargets(r, h).metrics, [0])
})
test('사용 가능한 답변 ID가 일치한 전후 답변·인용만 연결한다', () => {
  const r = report(), h = highlight()
  r.changes = [{ attemptId: 'a1', followup: null, first: { answerId: 'answer-1', text: '처음 생각' }, revised: { answerId: 'answer-2', text: '나중 생각' }, counts: { chars: [5, 5], sentences: [1, 1], reasonConnectives: [0, 0] } }]
  r.quotes = [{ attemptId: 'a1', answerId: 'answer-2', text: '나중 생각', verified: true }, { attemptId: 'a1', answerId: 'answer-1', text: '처음 생각', verified: true }]
  h.evidence = [{ attemptId: 'a1', answerId: 'answer-2', available: true, kind: 'ANSWER' }]
  assert.deepEqual(reportTargets(r, h).changes, [0]); assert.deepEqual(reportTargets(r, h).quotes, [0])
  for (const ref of [{ ...h.evidence[0], available: false }, { ...h.evidence[0], attemptId: 'other' }, { ...h.evidence[0], answerId: 'other' }, { ...h.evidence[0], kind: 'REFLECTION' as const }]) {
    assert.deepEqual(reportTargets(r, { ...h, evidence: [ref] }).changes, [])
    assert.deepEqual(reportTargets(r, { ...h, evidence: [ref] }).quotes, [])
  }
})
test('돌아보기는 같은 시도와 현재 확인된 원문이 모두 일치해야 연결한다', () => {
  const r = report(), h = highlight()
  r.reflections = [{ attemptId: 'a1', difficulty: 'EASY', written: true, text: '까닭을 더 썼다.' }]
  h.evidence = [{ attemptId: 'a1', answerId: null, kind: 'REFLECTION', available: true, quote: '까닭을 더 썼다.' }]
  assert.deepEqual(reportTargets(r, h).reflections, [0])
  assert.deepEqual(reportTargets(r, { ...h, evidence: [{ ...h.evidence[0], quote: '수정된 돌아보기' }] }).reflections, [])
})
test('일일 문제는 화면에 보이는 답변에 검증된 발췌 또는 현재 원문 전체가 있어야 연결한다', () => {
  const r = report(), h = highlight()
  r.periodType = h.periodType = 'DAILY'
  r.problems = [{ missionId: 'mission', attemptId: 'a1', title: '나무의 역할', context: 'EXTRA', judgment: null, finalAnswer: '그늘을 만든다.', followups: [], elements: [], reflection: null,
    quotes: [{ answerId: 'answer-1', text: '그늘', verified: true }] }]
  h.evidence = [{ attemptId: 'a1', answerId: 'answer-1', available: true }]
  assert.deepEqual(reportTargets(r, h).problems, [0])
  r.problems[0].quotes[0].text = '화면에 없는 이전 답변'
  assert.deepEqual(reportTargets(r, h).problems, [])
  h.evidence[0].quote = '그늘을 만든다.'
  assert.deepEqual(reportTargets(r, h).problems, [0])
  r.problems[0].reflection = { written: true, difficulty: 'EASY', text: '다시 생각했다.' }
  h.evidence = [{ attemptId: 'a1', answerId: null, kind: 'REFLECTION', available: true, quote: '다시 생각했다.' }]
  assert.deepEqual(reportTargets(r, h).problems, [0])
})
test('생각 유형은 알려진 계산식·기간·실제 미션 수가 일치해야 연결한다', () => {
  const r = report(), h = highlight()
  r.thinkingTypes = [{ type: 'ANALYZE', state: 'OK', missions: [{ attemptId: 'a1', title: '분석 활동' }] }]
  h.metrics = [{ ...metric, label: '분석하기 활동', formula: '분석하기 유형 시도 수', count: 1, numerator: 1, denominator: 1, value: null, state: 'INSUFFICIENT_SAMPLE' }]
  assert.deepEqual(reportTargets(r, h).thinking, [0])
  h.metrics[0].count = h.metrics[0].numerator = h.metrics[0].denominator = 2
  assert.deepEqual(reportTargets(r, h).thinking, [])
})
