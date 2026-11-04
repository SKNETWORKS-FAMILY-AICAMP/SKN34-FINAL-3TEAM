// #240 학생 생각 활동(FN-DSH-04)·분석 대화 예시 질문(FN-AGT-12): core 응답 모양 어댑터와 MSW 목업
import test from 'node:test'
import assert from 'node:assert/strict'

Object.defineProperty(globalThis, 'location', { value: new URL('http://localhost/'), configurable: true })
const { getThinkingActivities } = await import('../src/data/classroom/learningApi.ts')
const { parentApi } = await import('../src/data/parent/api.ts')
const { setAccessToken } = await import('../src/data/apiClient.ts')
const { setupServer } = await import('msw/node')
const { studentHandlers } = await import('../src/mocks/handlers/student.ts')
const { parentHandlers } = await import('../src/mocks/handlers/parent.ts')

const child = { id: 'child-1', nickname: '가상 학생', grade: 3, birthYear: 2017 }
const period = { from: '2026-10-20', to: '2026-10-26' }
const json = (data: unknown) => new Response(JSON.stringify(data), { headers: { 'Content-Type': 'application/json' } })

test('생각 활동은 기간을 보내고 돌아보기 코드를 표시값으로 바꾸며 숫자 필드를 만들지 않는다', async t => {
  setAccessToken('synthetic-student', 'STUDENT'); t.after(() => setAccessToken(null))
  let url = ''
  t.mock.method(globalThis, 'fetch', async (input: string) => {
    url = String(input)
    return json({ studentId: child.id, state: 'OK', period, items: [
      { attemptId: 'a-1', thinkingType: 'ANALYZE', missionTitle: '가상 미션', reflection: { difficulty: 'EASY', text: null } },
      { attemptId: 'a-2', thinkingType: 'REFLECT', missionTitle: '돌아보기 없는 미션', reflection: null },
    ] })
  })
  const result = await getThinkingActivities(child, period)
  assert.ok(url.endsWith('/students/me/thinking-activities?from=2026-10-20&to=2026-10-26'))
  assert.deepEqual(result.items, [
    { attemptId: 'a-1', thinkingType: 'ANALYZE', missionTitle: '가상 미션', reflection: { difficulty: '쉬웠어', text: '' } },
    { attemptId: 'a-2', thinkingType: 'REFLECT', missionTitle: '돌아보기 없는 미션', reflection: null },
  ])
})

test('생각 활동·예시 질문 응답 모양이 다르면 성공으로 표시하지 않는다', async t => {
  setAccessToken('synthetic-parent', 'PARENT'); t.after(() => setAccessToken(null))
  t.mock.method(globalThis, 'fetch', async (input: string) => String(input).includes('thinking-activities')
    ? json({ studentId: 'other-child', state: 'OK', period, items: [] })
    : json({ items: [{ question: '이번 주 학습 횟수는?' }] }))
  await assert.rejects(getThinkingActivities(child, period), (e: { problem: { status: number } }) => e.problem.status === 502)
  await assert.rejects(parentApi.examples(child.id), (e: { problem: { code: string } }) => e.problem.code === 'CONTRACT_NOT_READY')
})

test('목업: 학생만 생각 활동을 받고 학부모 예시 질문은 core와 같은 다섯 문구에 가능 여부를 붙인다', async () => {
  const server = setupServer(...parentHandlers, ...studentHandlers)
  server.listen({ onUnhandledFrame: 'error' })
  try {
    const call = async (path: string, token?: string, init: RequestInit = {}) => {
      const headers = new Headers(init.headers)
      if (init.body) headers.set('Content-Type', 'application/json')
      if (token) headers.set('Authorization', `Bearer ${token}`)
      const res = await fetch('http://localhost/api/v1' + path, { ...init, headers })
      return { status: res.status, body: await res.json() }
    }
    const parent = (await call('/auth/login', undefined, { method: 'POST', body: JSON.stringify({ email: 'parent@example.test', password: 'demo-only' }) })).body.accessToken
    const childId = (await call('/children', parent)).body.items[0].childId
    assert.equal((await call('/students/me/thinking-activities', parent)).status, 403)
    const examples = await call(`/agent/example-questions?childId=${childId}`, parent)
    assert.equal(examples.status, 200)
    assert.deepEqual(examples.body.items.map((i: { question: string }) => i.question),
      ['이번 주 학습 횟수는?', '어떤 생각 활동을 했어?', '아이가 쓴 생각을 보여줘', '되묻기 전후 무엇이 달라졌어?', '돌아보기에 뭐라고 썼어?'])
    assert.ok(examples.body.items.every((i: { available: unknown }) => typeof i.available === 'boolean'))
    const student = (await call('/auth/student-sessions', parent, { method: 'POST', body: JSON.stringify({ childId }) })).body.accessToken
    const activities = await call('/students/me/thinking-activities?from=2000-01-01&to=2099-12-31', student)
    assert.equal(activities.status, 200)
    assert.equal(activities.body.studentId, childId)
    for (const item of activities.body.items) {
      assert.deepEqual(Object.keys(item).sort(), ['attemptId', 'missionTitle', 'reflection', 'thinkingType'])
      if (item.reflection) assert.ok(['EASY', 'NORMAL', 'HARD'].includes(item.reflection.difficulty))
    }
  } finally { server.close() }
})
