import test from 'node:test'
import assert from 'node:assert/strict'
import { createApiGateway } from '../src/data/classroom/apiGateway.ts'
import { parentSessionLocked, refreshAccessToken, setAccessToken, unlockParentSession, withAuth } from '../src/data/apiClient.ts'
import { unlockProblem } from '../src/domain/studentDevice.ts'
import type { Child } from '../src/domain/classroom.ts'

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const child = { id: 'child-1', nickname: '하늘', grade: 4, birthYear: 2016 } as Child

function stubSessionStorage(t: test.TestContext) {
  const values = new Map<string, string>()
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'sessionStorage')
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  } })
  t.after(() => {
    setAccessToken('reset', 'PARENT'); setAccessToken(null)
    if (descriptor) Object.defineProperty(globalThis, 'sessionStorage', descriptor); else Reflect.deleteProperty(globalThis, 'sessionStorage')
  })
}

test('동석 진입은 학부모 세션 잠금을 탭에 표시하고, 잠긴 refresh는 표시를 유지한다', async (t) => {
  stubSessionStorage(t)
  setAccessToken('parent', 'PARENT')
  t.mock.method(globalThis, 'fetch', async (url: string) => url === '/api/v1/auth/student-sessions'
    ? json(200, { role: 'STUDENT', accessToken: 'student' })
    : json(401, { status: 401, code: 'PARENT_SESSION_LOCKED', title: 'locked' }))
  await createApiGateway().enterStudent(child)
  assert.equal(parentSessionLocked(), true)
  setAccessToken(null)
  await assert.rejects(refreshAccessToken())
  assert.equal(parentSessionLocked(), true)
})

test('보호자 비밀번호 복귀: 틀리면 남은 횟수를 그대로 주고, 맞으면 학부모 access로 바꾸고 잠금 표시를 지운다', async (t) => {
  stubSessionStorage(t)
  setAccessToken('student', 'STUDENT')
  sessionStorage.setItem('sagomungchi:parent-session-locked', 'true')
  const bodies: unknown[] = []
  let answer: Response = json(401, { status: 401, code: 'GUARDIAN_PASSWORD_INVALID', title: 'wrong', remainingAttempts: 4 })
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    assert.equal(url, '/api/v1/auth/parent-unlock')
    assert.equal(init.credentials, 'same-origin')
    assert.equal(new Headers(init.headers).get('X-Requested-With'), 'XMLHttpRequest')
    // 잠긴 학부모 세션은 refresh 쿠키로 식별한다. 학생 access를 보내지 않는다.
    assert.equal(new Headers(init.headers).get('Authorization'), null)
    bodies.push(JSON.parse(String(init.body)))
    return answer
  })
  await assert.rejects(unlockParentSession('1111'), (e: { problem: { code: string; remainingAttempts?: number } }) =>
    e.problem.code === 'GUARDIAN_PASSWORD_INVALID' && e.problem.remainingAttempts === 4)
  assert.equal(parentSessionLocked(), true)
  assert.equal(withAuth().get('Authorization'), 'Bearer student')
  answer = json(200, { accessToken: 'parent-again', role: 'PARENT' })
  await unlockParentSession('2580')
  assert.deepEqual(bodies, [{ password: '1111' }, { password: '2580' }])
  assert.equal(withAuth().get('Authorization'), 'Bearer parent-again')
  assert.equal(parentSessionLocked(), false)
})

test('잠김·미설정이면 비밀번호 입력을 닫고 Google 로그인만 남긴다', async (t) => {
  stubSessionStorage(t)
  let code = ''
  t.mock.method(globalThis, 'fetch', async () => json(code.endsWith('LOCKED') ? 423 : 409, { status: 423, code, title: code }))
  for (code of ['GUARDIAN_PASSWORD_LOCKED', 'GUARDIAN_PASSWORD_NOT_SET']) {
    sessionStorage.setItem('sagomungchi:parent-session-locked', 'true')
    await assert.rejects(unlockParentSession('2580'))
    assert.equal(parentSessionLocked(), false)
  }
  assert.match(unlockProblem('GUARDIAN_PASSWORD_INVALID', 2), /남은 기회는 2번/)
  assert.match(unlockProblem('GUARDIAN_PASSWORD_LOCKED'), /다시 로그인/)
})

test('목업: 보호자 비밀번호는 재인증 후 정하고, 동석 진입 뒤 refresh는 막히며 비밀번호로만 돌아온다', async () => {
  Object.defineProperty(globalThis, 'location', { value: new URL('http://localhost/'), configurable: true })
  const { setupServer } = await import('msw/node')
  const { parentHandlers } = await import('../src/mocks/handlers/parent.ts')
  const { studentHandlers } = await import('../src/mocks/handlers/student.ts')
  const server = setupServer(...parentHandlers, ...studentHandlers)
  server.listen({ onUnhandledFrame: 'error' })
  try {
    let token = ''
    const call = async (path: string, method = 'GET', body?: unknown, headers: Record<string, string> = {}) => {
      const r = await fetch('http://localhost/api/v1' + path, { method, headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json', ...headers },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
      return { status: r.status, data: r.status === 204 ? null : await r.json() }
    }
    token = (await call('/auth/login', 'POST', { email: 'parent@example.test', password: 'demo-only' })).data.accessToken
    assert.deepEqual((await call('/me/guardian-password')).data, { set: false, locked: false, updatedAt: null })
    const challenge = (await call('/me/reauth', 'POST', { purpose: 'GUARDIAN_PASSWORD' })).data.challengeId
    const grant = (await call('/me/reauth', 'POST', { challengeId: challenge })).data.reauthToken
    assert.equal((await call('/me/guardian-password', 'PUT', { password: '1234' }, { 'X-Reauth-Token': grant })).status, 422)
    assert.equal((await call('/me/guardian-password', 'PUT', { password: '2580' }, { 'X-Reauth-Token': grant })).data.set, true)
    const kid = (await call('/children')).data.items[0]
    token = (await call('/auth/student-sessions', 'POST', { childId: kid.id })).data.accessToken
    const refresh = await call('/auth/refresh', 'POST')
    assert.equal(refresh.status, 401); assert.equal(refresh.data.code, 'PARENT_SESSION_LOCKED')
    const wrong = await call('/auth/parent-unlock', 'POST', { password: '1111' })
    assert.equal(wrong.status, 401); assert.equal(wrong.data.remainingAttempts, 4)
    const back = await call('/auth/parent-unlock', 'POST', { password: '2580' })
    assert.equal(back.status, 200); assert.equal(back.data.role, 'PARENT')
    assert.equal((await call('/auth/refresh', 'POST')).status, 200)
    // core와 같이 잠기지 않은 세션의 parent-unlock은 비밀번호 확인 없이 refresh처럼 200이다 (#310).
    const unlocked = await call('/auth/parent-unlock', 'POST', { password: '1111' })
    assert.equal(unlocked.status, 200); assert.equal(unlocked.data.role, 'PARENT')
  } finally { server.close() }
})
