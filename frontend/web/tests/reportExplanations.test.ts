import test from 'node:test'
import assert from 'node:assert/strict'
import { makeWeekly, makeDaily } from '../src/mocks/fixtures/parent.ts'
import type { Child } from '../src/domain/classroom.ts'
import { setMockSubscription } from '../src/mocks/fixtures/payments.ts'
import { explanationBlocks, explanationSections, personalizeExplanation } from '../src/domain/reportExplanation.ts'
import { generatedReportDetails, reports } from '../src/mocks/fixtures/parent.ts'
import { seedStructuredReportDemo, structuredReportChild, structuredReportPeriod } from '../src/mocks/fixtures/structuredReportDemo.ts'
import { fixtureStore } from '../src/mocks/fixtures/student.ts'

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

test('상세 설명: 구조화된 본문은 세 구역으로 표시하고 없는 보완점은 만들지 않는다', () => {
  const content: { analysis: string; improvement_points: string | null; next_steps: string[] } = { analysis: '도서관이 필요한 까닭을 설명했어요.', improvement_points: null,
    next_steps: ['도서관에서 해 보고 싶은 일을 물어보세요.', '이유에 경험을 한 문장 덧붙여 보세요.'] }
  const sections = explanationSections(JSON.stringify(content))
  assert.deepEqual(sections.map(section => section.title), ['상세 분석', '개선 방안'])
  assert.deepEqual(explanationBlocks(sections[1].body), [{ kind: 'list', ordered: false, items: content.next_steps }])
  content.improvement_points = '이유를 더 구체적으로 풀어 볼 수 있어요.'
  assert.deepEqual(explanationSections(JSON.stringify(content)).map(section => section.title), ['상세 분석', '보완할 지점', '개선 방안'])
})

test('상세 설명: 저장된 소제목·문단·목록을 구분하며 제목 없는 원문을 임의로 요약하지 않는다', () => {
  const sections = explanationSections('## 상세 분석\n첫 관찰이에요.\n\n두 번째 관찰이에요.\n\n[보완할 지점]\n근거를 풀어 볼 수 있어요.\n개선 방안:\n1. 질문해 보세요.\n2. 한 문장을 써 보세요.')
  assert.deepEqual(sections.map(section => section.title), ['상세 분석', '보완할 지점', '개선 방안'])
  assert.equal(explanationBlocks(sections[0].body).length, 2)
  assert.deepEqual(explanationBlocks(sections[2].body), [{ kind: 'list', ordered: true, items: ['질문해 보세요.', '한 문장을 써 보세요.'] }])
  const original = '첫 관찰이에요.\n\n원문에 있는 개선 방안: 이 표현은 제목이 아니에요.'
  assert.deepEqual(explanationSections(original), [{ title: '상세 분석', body: original }])
  assert.deepEqual(explanationSections('잘한 점: 이유를 썼어요.\n함께 이야기해 볼 점: 경험을 연결해 보세요.'), [
    { title: '잘한 점', body: '이유를 썼어요.' }, { title: '함께 이야기해 볼 점', body: '경험을 연결해 보세요.' },
  ])
})

test('상세 설명: 형식이 다른 JSON은 내용을 버리지 않고 원문으로 보존한다', () => {
  const original = JSON.stringify({ analysis: '관찰', extra: '사라지면 안 되는 내용' })
  assert.deepEqual(explanationSections(original), [{ title: '상세 분석', body: original }])
})

test('Gemma 시연: 결과 누락·원문 변경에는 합성 설명으로 대체하지 않고 재집계에는 같은 결과를 쓴다', () => {
  const before = fixtureStore.snapshot()
  try {
    assert.equal(seedStructuredReportDemo().explanations?.state, 'NOT_INCLUDED')
    const attempt = fixtureStore.snapshot().attempts.find(row => row.studentId === structuredReportChild.id)!
    const answer = attempt.answers.at(-1)!
    const text = JSON.stringify({ analysis: '검증용 모델 응답', improvement_points: null, next_steps: ['검증용 제안'] })
    seedStructuredReportDemo({ model: 'test-only-model', promptVersion: 'test-only-prompt', items: [
      { attemptId: attempt.attemptId, answerVersion: answer.version, sourceText: answer.text, text },
    ] })
    const regenerated = makeWeekly(structuredReportChild, structuredReportPeriod, 2)
    assert.equal(regenerated.themeSummary, null)
    assert.equal(regenerated.explanations?.items.length, 1)
    assert.equal(regenerated.explanations?.items[0].text, text)
    const changed = fixtureStore.snapshot()
    changed.attempts.find(row => row.attemptId === attempt.attemptId)!.answers.at(-1)!.text += ' 원문 수정'
    fixtureStore.restoreSnapshot(changed)
    assert.equal(makeWeekly(structuredReportChild, structuredReportPeriod).explanations?.state, 'NOT_INCLUDED')
  } finally {
    fixtureStore.restoreSnapshot(before)
    for (const id of generatedReportDetails.keys()) if (id.startsWith('structured-report-demo-')) generatedReportDetails.delete(id)
    reports.delete(`${structuredReportChild.id}-${structuredReportPeriod.from}`)
  }
})

test('젬마 본문에 학생 이름과 받침에 맞는 조사를 쓰고 인용은 유지한다', () => {
  const text = '자녀는 근거를 썼고 자녀의 글에 “자녀가 쓴 원문”이 남아 있어요.'
  assert.equal(personalizeExplanation(text, '하늘'), '하늘은 근거를 썼고 하늘의 글에 “자녀가 쓴 원문”이 남아 있어요.')
  assert.equal(personalizeExplanation(text, '바다'), '바다는 근거를 썼고 바다의 글에 “자녀가 쓴 원문”이 남아 있어요.')
  assert.equal(personalizeExplanation('자녀는 다음 예를 들었어요.', ' '), '자녀는 다음 예를 들었어요.')
})
