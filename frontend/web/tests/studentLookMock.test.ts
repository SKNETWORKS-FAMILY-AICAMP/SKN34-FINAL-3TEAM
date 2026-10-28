import test from 'node:test'
import assert from 'node:assert/strict'

// MSW 핸들러는 상대 경로로 등록되어 있어 Node에서는 기준 주소가 필요하다.
Object.defineProperty(globalThis, 'location', { value: new URL('http://localhost/'), configurable: true })
const { setupServer } = await import('msw/node')
const { studentHandlers } = await import('../src/mocks/handlers/student.ts')

const server = setupServer(...studentHandlers)
server.listen({ onUnhandledRequest: 'error' })
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

test('꾸미기 설정: 학생만 읽고 바꾸며, 목록 밖 값은 422', async () => {
  const parent = (
    await call('/auth/login', { method: 'POST', body: JSON.stringify({ email: 'parent@example.test', password: 'demo-only' }) })
  ).body.accessToken
  assert.equal((await call('/students/me/preferences', { token: parent })).status, 403)

  const childId = (await call('/children', { token: parent })).body.items[0].childId
  const student = (
    await call('/auth/student-sessions', { method: 'POST', body: JSON.stringify({ childId }), token: parent })
  ).body.accessToken

  const first = await call('/students/me/preferences', { token: student })
  assert.deepEqual(first.body, { theme: 'lake', companion: 'mungchi', updatedAt: null })

  const bad = await call('/students/me/preferences', {
    method: 'PUT',
    body: JSON.stringify({ theme: 'mars', companion: 'tori' }),
    token: student,
  })
  assert.equal(bad.status, 422)

  const saved = await call('/students/me/preferences', {
    method: 'PUT',
    body: JSON.stringify({ theme: 'space', companion: 'kongi' }),
    token: student,
  })
  assert.equal(saved.status, 200)
  assert.equal(saved.body.theme, 'space')
  assert.ok(saved.body.updatedAt)
  assert.equal((await call('/students/me/preferences', { token: student })).body.companion, 'kongi')
})
