import test from 'node:test'
import assert from 'node:assert/strict'

// MSW 핸들러는 상대 경로로 등록되어 있어 Node에서는 기준 주소가 필요하다.
Object.defineProperty(globalThis, 'location', { value: new URL('http://localhost/'), configurable: true })
const { setupServer } = await import('msw/node')
const { onboardingHandlers } = await import('../src/mocks/handlers/onboarding.ts')
const { parentHandlers } = await import('../src/mocks/handlers/parent.ts')
const { studentHandlers } = await import('../src/mocks/handlers/student.ts')
const { ONBOARDING_DONE_AT, setMockOnboarding, studentOnboardingKey } = await import('../src/mocks/fixtures/onboarding.ts')

const server = setupServer(...onboardingHandlers, ...parentHandlers, ...studentHandlers)
server.listen({ onUnhandledFrame: 'error' })
test.after(() => server.close())

const base = 'http://localhost/api/v1'
async function call(path: string, init: RequestInit & { token?: string } = {}) {
  const headers = new Headers(init.headers)
  if (init.body) headers.set('Content-Type', 'application/json')
  if (init.token) headers.set('Authorization', `Bearer ${init.token}`)
  const res = await fetch(base + path, { ...init, headers })
  const text = await res.text()
  return { status: res.status, body: text ? JSON.parse(text) : null }
}
const parentLogin = async (): Promise<string> =>
  (await call('/auth/login', { method: 'POST', body: JSON.stringify({ email: 'parent@example.test', password: 'demo-only' }) })).body.accessToken
async function studentLogin(index: number) {
  const parent = await parentLogin()
  const childId: string = (await call('/children', { token: parent })).body.items[index].childId
  const token: string = (await call('/auth/student-sessions', { method: 'POST', body: JSON.stringify({ childId }), token: parent })).body.accessToken
  return { childId, token }
}

test('학부모: 미완료 null → PUT 기록 → 다시 PUT해도 처음 시각 유지, 학생 경로는 403', async () => {
  const parent = await parentLogin()
  assert.deepEqual((await call('/me/onboarding', { token: parent })).body, { completedAt: null })
  const first = await call('/me/onboarding', { method: 'PUT', token: parent })
  assert.equal(first.status, 200)
  assert.equal(typeof first.body.completedAt, 'string')
  assert.deepEqual((await call('/me/onboarding', { method: 'PUT', token: parent })).body, first.body)
  assert.deepEqual((await call('/me/onboarding', { token: parent })).body, first.body)
  assert.equal((await call('/students/me/onboarding', { token: parent })).status, 403)
  assert.equal((await call('/students/me/onboarding', { method: 'PUT', token: parent })).status, 403)
})

test('학생: 자녀별 기록·처음 시각 유지, 학부모 경로는 403', async () => {
  const first = await studentLogin(0)
  assert.deepEqual((await call('/students/me/onboarding', { token: first.token })).body, { completedAt: null })
  const saved = (await call('/students/me/onboarding', { method: 'PUT', token: first.token })).body
  assert.equal(typeof saved.completedAt, 'string')
  assert.deepEqual((await call('/students/me/onboarding', { method: 'PUT', token: first.token })).body, saved)
  assert.equal((await call('/me/onboarding', { token: first.token })).status, 403)
  assert.equal((await call('/me/onboarding', { method: 'PUT', token: first.token })).status, 403)

  const sibling = await studentLogin(1)
  assert.notEqual(sibling.childId, first.childId)
  assert.deepEqual((await call('/students/me/onboarding', { token: sibling.token })).body, { completedAt: null })
})

test('완료 상태 fixture: 정한 시각을 그대로 주고 PUT도 바꾸지 않는다', async () => {
  const { childId, token } = await studentLogin(0)
  setMockOnboarding(studentOnboardingKey(childId), ONBOARDING_DONE_AT)
  assert.deepEqual((await call('/students/me/onboarding', { token })).body, { completedAt: ONBOARDING_DONE_AT })
  assert.deepEqual((await call('/students/me/onboarding', { method: 'PUT', token })).body, { completedAt: ONBOARDING_DONE_AT })
  setMockOnboarding(studentOnboardingKey(childId), null)
  assert.deepEqual((await call('/students/me/onboarding', { token })).body, { completedAt: null })
})
