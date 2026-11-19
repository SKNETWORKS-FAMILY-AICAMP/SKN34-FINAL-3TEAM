import test from 'node:test'
import assert from 'node:assert/strict'
import { blankAnswer } from '../src/domain/classroom.ts'
import { markInput, measureTiming, noTiming, startRound } from '../src/domain/answerTiming.ts'
import { createApiGateway } from '../src/data/classroom/apiGateway.ts'
import { storedTiming } from '../src/data/classroom/demoGateway.ts'

// 생각·작성 시간(P28, api-spec 3.1, #802): 표시 → 첫 입력 → 제출을 performance.now() 밀리초로 받아 정수 초로
const typed = (text: string) => ({ ...blankAnswer('NARRATIVE'), text })

test('생각 시간은 표시→첫 입력, 작성 시간은 첫 입력→제출이고 이후 입력은 첫 입력을 바꾸지 않는다', () => {
  let r = startRound('v0', 1_000, false)
  r = markInput(r, blankAnswer('NARRATIVE'), typed('나'), 96_000)
  r = markInput(r, typed('나'), typed('나는'), 120_000)
  assert.deepEqual(measureTiming(r, typed('나는'), 336_400), { thinkingSeconds: 95, writingSeconds: 240 })
})

test('보호자 받아쓰기 표시만 바꾸면 첫 입력이 아니고, 시작 문장처럼 글이 바뀌면 첫 입력', () => {
  const blank = blankAnswer('ESSAY')
  let r = startRound('f-1', 0, false)
  r = markInput(r, blank, { ...blank, dictatedByGuardian: true }, 5_000)
  assert.equal(r.firstInputAt, null)
  const starter = { ...blank, essay: { ...blank.essay, claim: '나는 ○○ 쪽이 좋다고 생각해요.' } }
  r = markInput(r, blank, starter, 7_000)
  assert.equal(r.firstInputAt, 7_000)
})

test('고르기 방식·보호자 받아쓰기·이어하기·첫 입력 없음은 두 칸 모두 null', () => {
  const r = markInput(startRound('v0', 0, false), blankAnswer('NARRATIVE'), typed('a'), 1_000)
  for (const type of ['CHOICE', 'ORDERING', 'CLASSIFICATION'] as const)
    assert.deepEqual(measureTiming(r, blankAnswer(type), 2_000), noTiming)
  assert.deepEqual(measureTiming(r, { ...typed('a'), dictatedByGuardian: true }, 2_000), noTiming)
  assert.deepEqual(measureTiming({ ...r, resumed: true }, typed('a'), 2_000), noTiming)
  assert.deepEqual(measureTiming(startRound('v0', 0, false), typed('a'), 2_000), noTiming)
  assert.deepEqual(measureTiming(null, typed('a'), 2_000), noTiming)
})

test('24시간 넘는 값은 둘 다 null(반쪽 값 없음)', () => {
  const r = markInput(startRound('v0', 0, false), blankAnswer('SOLUTION_STEPS'), { ...blankAnswer('SOLUTION_STEPS'), finalAnswer: '6' }, 1_000)
  assert.deepEqual(measureTiming(r, blankAnswer('SOLUTION_STEPS'), 1_000 + 86_401_000), noTiming)
  assert.deepEqual(measureTiming(r, blankAnswer('SOLUTION_STEPS'), 1_000 + 86_400_000), { thinkingSeconds: 1, writingSeconds: 86400 })
})

test('payload()는 timing을 받으면 두 칸을 싣고, 없으면 보내지 않는다', async (t) => {
  const bodies: Record<string, unknown>[] = []
  t.mock.method(globalThis, 'fetch', async (path: string, init: RequestInit) => {
    if (path.endsWith('/answers')) bodies.push(JSON.parse(String(init.body)))
    return new Response(JSON.stringify({ attemptId: 'a-1', answers: [], status: 'IN_PROGRESS', helped: false,
      mission: { id: 'm', title: 't', subject: '국어', grade: 3, thinkingType: 'REASONING', inputType: 'NARRATIVE', question: 'q', hint: 'h' } }),
    { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  const api = createApiGateway()
  await api.submit('a-1', typed('원문'), 'k-1', undefined, { thinkingSeconds: 95, writingSeconds: 240 }).catch(() => {})
  await api.submit('a-1', typed('원문'), 'k-2', 'f-1', noTiming).catch(() => {})
  await api.submit('a-1', typed('원문'), 'k-3').catch(() => {})
  assert.equal(bodies[0].thinkingSeconds, 95)
  assert.equal(bodies[0].writingSeconds, 240)
  assert.equal(bodies[1].followupId, 'f-1')
  assert.equal(bodies[1].thinkingSeconds, null)
  assert.equal(bodies[1].writingSeconds, null)
  assert.equal('thinkingSeconds' in bodies[2], false)
})

test('시연 저장소는 learning 규칙대로 글 입력 방식의 범위 안 쌍만 저장', () => {
  assert.deepEqual(storedTiming(typed('a'), { thinkingSeconds: 3, writingSeconds: 4 }), { thinkingSeconds: 3, writingSeconds: 4 })
  assert.deepEqual(storedTiming(blankAnswer('CHOICE'), { thinkingSeconds: 3, writingSeconds: 4 }), noTiming)
  assert.deepEqual(storedTiming(typed('a'), { thinkingSeconds: -1, writingSeconds: 4 }), noTiming)
  assert.deepEqual(storedTiming(typed('a'), { thinkingSeconds: 3, writingSeconds: null }), noTiming)
  assert.deepEqual(storedTiming(typed('a')), noTiming)
})
