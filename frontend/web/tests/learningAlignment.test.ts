import test from 'node:test'
import assert from 'node:assert/strict'
import { saveReflection, saveSelfAssessment } from '../src/data/classroom/learningApi.ts'
import { missionWritePayload, adminApi } from '../src/data/admin/api.ts'
import { missingMissionFields, missingFieldLabel, validAnswerKey } from '../src/domain/admin/operations.ts'
import type { AdminMission } from '../src/domain/admin/operations.ts'
import type { Attempt } from '../src/domain/classroom.ts'
Object.defineProperty(globalThis, 'location', { value: new URL('http://localhost/'), configurable: true })
const { setupServer } = await import('msw/node')
const { studentHandlers } = await import('../src/mocks/handlers/student.ts')
const { adminHandlers } = await import('../src/mocks/handlers/admin.ts')
const { fixtureStore } = await import('../src/mocks/fixtures/student.ts')
const { missions } = await import('../src/mocks/fixtures/admin/operations.ts')
const server = setupServer(...adminHandlers, ...studentHandlers)
server.listen({ onUnhandledRequest: 'error' }); test.after(() => server.close())
let token = ''
async function call(path: string, method = 'GET', data?: unknown) {
  const response = await fetch('http://localhost/api/v1' + path, { method,
    headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
    ...(data === undefined ? {} : { body: JSON.stringify(data) }),
  })
  return { status: response.status, data: await response.json() }
}
async function login(email: string) {
  const result = await call('/auth/login', 'POST', { email, password: 'demo-only' })
  assert.equal(result.status, 200); token = result.data.accessToken
}
const full = () => {
  const m = structuredClone(missions[0]); m.reviews = [{ missionVersion: m.currentVersion,
    rubricVersion: m.currentRubricVersion!, result: 'APPROVED', comment: '검토', createdAt: new Date().toISOString() }]
  return m
}

test('돌아보기는 세 난이도를 코드로 전송하며 자기 평가 일부 저장·응답 null/false를 유지한다', async (t) => {
  const requests: { url: string; body: unknown }[] = []
  const response = [{ elementId: 'final', label: '최종 답', selfChecked: false, aiChecked: true, quote: null },
    { elementId: 'step', label: '풀이', selfChecked: null, aiChecked: false, quote: null }]
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    requests.push({ url: String(url), body: JSON.parse(String(init.body)) })
    return Response.json(String(url).endsWith('self-assessment') ? response : {})
  })
  for (const difficulty of ['쉬웠어', '보통', '어려웠어'] as const) await saveReflection('a/id', { difficulty, text: '' })
  assert.deepEqual(requests.map((r) => r.body), ['EASY', 'NORMAL', 'HARD'].map((difficulty) => ({ difficulty, text: '' })))
  assert.ok(requests[0].url.endsWith('/attempts/a%2Fid/reflection'))
  assert.deepEqual(await saveSelfAssessment('a/id', [{ elementId: 'final', checked: false }]), response)
  assert.deepEqual(requests[3].body, { checks: [{ elementId: 'final', checked: false }] })
})

test('입력 방식별 정답 객체와 모든 문항 기준표, 풀이 최종 답 외 요소 조건을 검사한다', () => {
  const m = full(), v = m.versions[0], r = m.rubrics[0]
  assert.deepEqual(missingMissionFields(m), [])
  r.elements = []; assert.ok(missingMissionFields(m).includes('rubric.elements'))
  r.elements = [{ code: 'FINAL_ANSWER', label: '최종 답', description: '', points: 1, commonErrors: [], goodThought: true, judgeVerified: false }]
  v.inputType = 'SOLUTION_STEPS'; r.answerKey = { finalAnswer: '30' }
  assert.ok(missingMissionFields(m).includes('rubric.elements'))
  r.elements.push({ ...r.elements[0], code: 'STEPS', label: '풀이' })
  assert.deepEqual(missingMissionFields(m), [])
  assert.equal(validAnswerKey(v, { finalAnswer: '30m²' }), false)
  v.inputType = 'CHOICE'; v.choices = [{ id: 'c1', label: '하나' }, { id: 'c2', label: '둘' }]
  assert.ok(missingMissionFields(m).includes('rubric.elements'))
  r.elements = r.elements.filter((e) => e.code !== 'FINAL_ANSWER'); r.answerKey = { choiceIds: ['c2'] }
  assert.deepEqual(missingMissionFields(m), [])
  v.inputType = 'ORDERING'; assert.equal(validAnswerKey(v, r.answerKey), false)
  assert.equal(validAnswerKey(v, { choiceIds: ['c2', 'c1'] }), true)
  assert.equal(validAnswerKey(v, { choiceIds: ['c1', 'c1'] }), false)
  v.inputType = 'CLASSIFICATION'; v.categories = [{ id: 'g1', label: '식물' }]
  assert.equal(validAnswerKey(v, { assignments: [{ choiceId: 'c1', categoryId: 'g1' }, { choiceId: 'c2', categoryId: 'g1' }] }), true)
  assert.equal(validAnswerKey(v, { assignments: [{ choiceId: 'c1', categoryId: 'missing' }] }), false)
  r.elements[0].points = 0; assert.ok(missingMissionFields(m).includes('rubric.elements.points'))
  assert.equal(missingFieldLabel('rubric.elements[0].points'), '요소 이름·양의 배점')
  assert.ok(missingFieldLabel('unknown.code').includes('unknown.code'))
})

test('미션 쓰기에는 scene/응답 버전 대신 URI·단위·입력 틀을 보내고 게시·중단은 {}로 보낸다', async (t) => {
  const v = { ...full().versions[0], demoOnly: true, inputType: 'SOLUTION_STEPS' as const,
    answerUnit: ' m² ', inputTemplate: ['구하는 값', '식'], scene: 'math' }
  const wire = missionWritePayload(v)
  assert.equal('scene' in wire, false); assert.equal('version' in wire, false); assert.equal('createdAt' in wire, false)
  assert.equal(wire.answerUnit, 'm²'); assert.deepEqual(wire.inputTemplate, ['구하는 값', '식'])
  const requests: RequestInit[] = []
  t.mock.method(globalThis, 'fetch', async (_url: string, init: RequestInit) => { requests.push(init); return Response.json({}) })
  await adminApi.action('m', 'publish'); await adminApi.action('m', 'unpublish')
  assert.deepEqual(requests.map((r) => JSON.parse(String(r.body))), [{}, {}])
  for (const answerKey of [{ choiceIds: ['c2'] }, { choiceIds: ['i2', 'i3', 'i1'] },
    { assignments: [{ choiceId: 'c1', categoryId: 'g1' }] }, { finalAnswer: '30' }]) {
    await adminApi.rubric('m', { ...full().rubrics[0], answerKey })
    const body = JSON.parse(String(requests.at(-1)!.body))
    assert.deepEqual(body.answerKey, answerKey); assert.equal('version' in body, false)
  }

})

test('자기 평가는 마무리 뒤·완료 전에만, 부분 갱신과 최종 답 요소를 보존한다', async () => {
  await login('parent@example.test'); const child = (await call('/children')).data.items[0]
  const entered = await call('/auth/student-sessions', 'POST', { childId: child.childId ?? child.id }); token = entered.data.accessToken
  const snap = fixtureStore.snapshot(), selected = snap.session!.child!
  const a: Attempt = { attemptId: 'alignment-self', studentId: selected.id, mission: { id: 'math', title: '수학', subject: '수학',
    grade: 3, thinkingType: 'SOLVE', inputType: 'SOLUTION_STEPS', question: '계산', hint: '', scene: 'math' },
    status: 'IN_PROGRESS', answers: [], helped: false,
    checklist: [{ elementId: 'final', label: '최종 답', satisfied: true, quote: '30', sourceType: 'ANSWER_KEY' },
      { elementId: 'step', label: '풀이', satisfied: false, quote: null, sourceType: 'AI_OBSERVATION' }] }
  function restore() { const s = fixtureStore.snapshot(); fixtureStore.restoreSnapshot({ ...s, attempts: [...s.attempts.filter((v) => v.attemptId !== a.attemptId), a] }) }
  restore(); const path = '/attempts/' + a.attemptId
  assert.equal((await call(path + '/self-assessment', 'POST', { checks: [{ elementId: 'final', checked: true }] })).status, 409)
  a.finishedAt = new Date().toISOString(); a.reveal = '30'; restore()
  for (const checks of [[], [{ elementId: 'foreign', checked: true }], [{ elementId: 'final', checked: true }, { elementId: 'final', checked: false }]])
    assert.equal((await call(path + '/self-assessment', 'POST', { checks })).status, 400)
  let result = await call(path + '/self-assessment', 'POST', { checks: [{ elementId: 'final', checked: false }] })
  assert.equal(result.status, 200); assert.equal(result.data[0].selfChecked, false); assert.equal(result.data[1].selfChecked, null)
  result = await call(path + '/self-assessment', 'POST', { checks: [{ elementId: 'step', checked: true }] })
  assert.deepEqual(result.data.map((e: { selfChecked: unknown }) => e.selfChecked), [false, true])
  assert.equal((await call(path + '/reflection', 'POST', { difficulty: '쉬웠어', text: '' })).status, 400)
  assert.equal((await call(path + '/reflection', 'POST', { difficulty: 'NORMAL', text: '' })).status, 200)
  assert.equal((await call(path + '/self-assessment', 'POST', { checks: [{ elementId: 'final', checked: true }] })).status, 409)
})

test('공개 중 편집·기준표 갱신·검토에도 공개본을 유지하고 재게시 때만 학생 카탈로그를 바꾼다', async () => {
  await login('admin@example.test')
  const source = full(), version = source.versions[0]
  const created = await call('/admin/missions', 'POST', missionWritePayload({ ...version, demoOnly: true }))
  assert.equal(created.status, 201)
  const path = '/admin/missions/' + created.data.missionId
  let saved = await call(path + '/rubric', 'PUT', source.rubrics[0]); let m: AdminMission = saved.data
  const pair = () => ({ missionVersion: m.currentVersion, rubricVersion: m.currentRubricVersion })
  await call(path + '/review-request', 'POST', pair()); await call(path + '/review', 'POST', { ...pair(), result: 'APPROVED', comment: '확인' })
  m = (await call(path + '/publish', 'POST', {})).data
  assert.equal(m.status, 'PUBLISHED'); const published = m.publishedVersion
  saved = await call(path, 'PATCH', missionWritePayload({ ...version, title: '편집본 v2', demoOnly: true })); m = saved.data
  assert.equal(m.status, 'PUBLISHED'); assert.equal(m.publishedVersion, published); assert.equal(m.currentVersion, 2)
  assert.equal(fixtureStore.snapshot().catalog!.find((v) => v.id === m.missionId)!.title, version.title)
  m = (await call(path + '/rubric', 'PUT', source.rubrics[0])).data
  assert.equal(m.status, 'PUBLISHED'); assert.equal(m.publishedVersion, published)
  const failed = await call(path + '/publish', 'POST', {})
  assert.equal(failed.status, 422); assert.ok(failed.data.missingFields.includes('review'))
  assert.ok(failed.data.missingFields.every((f: string) => /^[a-zA-Z][a-zA-Z0-9.[\]]*$/.test(f)))
  m = (await call(path + '/review-request', 'POST', pair())).data; assert.equal(m.status, 'PUBLISHED')
  m = (await call(path + '/review', 'POST', { ...pair(), result: 'APPROVED', comment: '검토' })).data
  m = (await call(path + '/publish', 'POST', {})).data
  assert.equal(m.publishedVersion, 2); assert.equal(fixtureStore.snapshot().catalog!.find((v) => v.id === m.missionId)!.title, '편집본 v2')
  const list = await call('/admin/missions?status=PUBLISHED&page=0&size=1')
  assert.equal(list.data.size, 1); assert.ok(list.data.items.length <= 1)
  assert.equal(list.data.counts.reduce((sum: number, r: { count: number }) => sum + r.count, 0), missions.length)
})
