import test from 'node:test'
import assert from 'node:assert/strict'
import {
  createDemoGateway,
  demoMissions,
  DraftConflictError,
} from '../src/data/classroom/demoGateway.ts'
import {
  blankAnswer,
  calendarPeriods,
  canAddAnswer,
  canFinish,
  inPeriod,
  previousWeek,
  recentPeriod,
  validateAnswer,
} from '../src/domain/classroom.ts'
import type { Child } from '../src/domain/classroom.ts'

async function setup(index = 0) {
  const api = createDemoGateway()
  await api.login('parent@example.test', 'demo')
  const child = (await api.children())[index]
  await api.enterStudent(child)
  return { api, child }
}
test('최초 답과 추가 답 2회 보존, 마무리 잠금, 돌아보기 후에만 완료', async () => {
  const { api, child } = await setup()
  let a = await api.start(demoMissions(child.grade)[2], child)
  await assert.rejects(api.finish(a.attemptId))
  for (let i = 0; i < 3; i++) {
    const answer = { ...blankAnswer(a.mission.inputType), text: `내 생각 ${i}` }
    a = await api.submit(
      a.attemptId,
      answer,
      `key-${i}`,
      a.answers.at(-1)?.feedback.followup?.followupId,
    )
    assert.equal(a.answers.length, i + 1)
    await api.feedback(a.attemptId, a.answers.at(-1)!.answerId, () => {})
    a = await api.attempt(a.attemptId)
    assert.equal(canFinish(a), true) // DONE + HELD도 마무리 가능
  }
  assert.equal(canAddAnswer(a), false)
  assert.equal(a.answers[0].text, '내 생각 0')
  a = await api.finish(a.attemptId)
  assert.ok(a.finishedAt)
  assert.equal(a.status, 'IN_PROGRESS')
  await assert.rejects(
    api.submit(a.attemptId, { ...blankAnswer('NARRATIVE'), text: '수정' }, 'fourth'),
  )
  await assert.rejects(api.reflect(a.attemptId, { difficulty: '' as never, text: '' }))
  a = await api.reflect(a.attemptId, { difficulty: '보통', text: '' })
  assert.equal(a.status, 'COMPLETED')
})
test('AI 실패해도 답변 저장 유지, 피드백 재시도/멱등 제출은 답변 추가 없음', async () => {
  const { api, child } = await setup()
  api.setScenario('ai-fail')
  const a = await api.start(demoMissions(child.grade)[2], child)
  const content = { ...blankAnswer('NARRATIVE'), text: '보존해야 하는 답변' }
  const saved = await api.submit(a.attemptId, content, 'stable-key')
  await assert.rejects(api.feedback(a.attemptId, saved.answers[0].answerId, () => {}))
  assert.equal((await api.attempt(a.attemptId)).answers[0].feedback.status, 'FAILED')
  assert.equal((await api.submit(a.attemptId, content, 'stable-key')).answers.length, 1)
  assert.equal(
    (await api.feedback(a.attemptId, saved.answers[0].answerId, () => {})).status,
    'DONE',
  )
  assert.equal((await api.attempt(a.attemptId)).answers.length, 1)
})
test('초안 실패 입력 보존 / 버전 충돌 / 메모는 학부모·리포트·분석에서 제외', async () => {
  const { api, child } = await setup()
  const a = await api.start(demoMissions(child.grade)[2], child)
  const draft = {
    answer: { ...blankAnswer('NARRATIVE'), text: '제출 원문' },
    memo: '비밀 메모 SECRET',
    version: '0',
  }
  api.setScenario('draft-fail')
  await assert.rejects(api.saveDraft(a.attemptId, draft))
  assert.equal(draft.memo, '비밀 메모 SECRET')
  const saved = await api.saveDraft(a.attemptId, draft)
  await assert.rejects(api.saveDraft(a.attemptId, draft), DraftConflictError)
  assert.equal((await api.attempt(a.attemptId)).draft?.version, saved.version)
  const submitted = await api.submit(a.attemptId, draft.answer, 'memo-key')
  await api.feedback(a.attemptId, submitted.answers[0].answerId, () => {})
  await api.logout()
  await api.login('parent@example.test', 'demo')
  const records = await api.records(child, 'PARENT', recentPeriod)
  assert.equal('draft' in records.find((r) => r.attemptId === a.attemptId)!, false)
  assert.equal(JSON.stringify(await api.record(child, a.attemptId)).includes('SECRET'), false)
  assert.equal(JSON.stringify(await api.report(child, previousWeek)).includes('SECRET'), false)
  assert.equal(
    JSON.stringify(await api.analyze(child, recentPeriod, '원문')).includes('SECRET'),
    false,
  )
})
test('고르기 정답은 추가 질문 없이 마무리, 학생 자녀 범위 검증', async () => {
  const { api, child } = await setup()
  const a = await api.start(demoMissions(child.grade)[1], child)
  const saved = await api.submit(
    a.attemptId,
    { ...blankAnswer('CHOICE'), choiceIds: ['leaf'] },
    'choice',
  )
  const f = await api.feedback(a.attemptId, saved.answers[0].answerId, () => {})
  assert.deepEqual(f.nextActions, ['FINISH'])
  assert.equal(f.followup, undefined)
  await assert.rejects(api.records({ ...child, id: 'another' }, 'STUDENT', recentPeriod))
})
test('학부모 자녀별 기록, 무료 분석 잠금, 빈 주 완료와 소표본, 이전 판 보존', async () => {
  const api = createDemoGateway()
  await api.login('parent@example.test', 'demo')
  const [premium, free] = await api.children()
  assert.equal((await api.records(free, 'PARENT', recentPeriod)).length, 1)
  const empty = await api.report(premium, { from: '2026-10-12', to: '2026-10-18' })
  assert.equal(empty.status, 'COMPLETED')
  assert.equal(empty.state, 'NO_RECORD')
  const r = await api.report(premium, previousWeek)
  assert.equal(r.state, 'INSUFFICIENT_SAMPLE')
  assert.equal(
    r.metrics.every((m) => m.value === null),
    true,
  )
  assert.equal((await api.regenerate(r)).revision, 2)
  assert.equal((await api.report(premium, previousWeek, 1)).revision, 1)
  await assert.rejects(api.regenerate(r))
  await assert.rejects(api.analyze(free, recentPeriod, '원문'))
  await assert.rejects(api.record(free, r.records[0].attemptId))
  await assert.rejects(api.records({ id: 'other-parent-child' } as Child, 'PARENT', recentPeriod))
})
test('학년별 입력 방식과 KST 기간 경계', () => {
  assert.equal(
    validateAnswer(blankAnswer('ESSAY'), { ...demoMissions(3)[2], inputType: 'ESSAY' })?.includes(
      '5~6',
    ),
    true,
  )
  assert.equal(demoMissions(5)[2].inputType, 'ESSAY')
  assert.equal(inPeriod('2026-10-19T15:10:00Z', recentPeriod), true)
  assert.equal(inPeriod('2026-10-26T15:00:00Z', recentPeriod), false)
})
test('실제 조회 기간은 고정 시연 날짜가 아니라 KST 기준으로 계산', () => {
  const p = calendarPeriods(new Date('2026-11-01T15:10:00Z')) // 한국 월요일
  assert.deepEqual(p.recentPeriod, { from: '2026-10-27', to: '2026-11-02' })
  assert.deepEqual(p.previousWeek, { from: '2026-10-26', to: '2026-11-01' })
})
