import test from 'node:test'
import assert from 'node:assert/strict'
import { apiFetch, setAccessToken, withAuth, refreshAccessToken, withAuthLock } from '../src/data/apiClient.ts'
import { createApiGateway } from '../src/data/classroom/apiGateway.ts'

const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), {
  status, headers: { 'Content-Type': 'application/json' },
})

test('OAuth completion restores access through shared refresh and follows server onboarding contract', async (t) => {
  const paths: string[] = []
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    paths.push(url)
    assert.equal(new Headers(init.headers).get('X-Requested-With'), 'XMLHttpRequest')
    if (url.endsWith('/auth/refresh')) return json({ accessToken: 'new-access', role: 'PARENT' })
    assert.equal(new Headers(init.headers).get('Authorization'), 'Bearer new-access')
    return json({ role: 'PARENT', permissions: [], nextAction: 'CONSENT_REQUIRED', startPath: '/parent/onboarding' })
  })
  const session = await createApiGateway().restore()
  assert.equal(session.startPath, '/parent/onboarding')
  assert.equal(session.nextAction, 'CONSENT_REQUIRED')
  assert.deepEqual(paths, ['/api/v1/auth/refresh', '/api/v1/me'])
  setAccessToken(null)
})

test('student access is kept only in memory and expiry never refreshes parent credentials', async (t) => {
  let refreshes = 0
  setAccessToken('student-access', 'STUDENT')
  t.mock.method(globalThis, 'fetch', async (url: string) => {
    if (url.endsWith('/auth/refresh')) { refreshes++; return json({ accessToken: 'parent-access' }) }
    return json({ code: 'TOKEN_EXPIRED', status: 401, title: '만료' }, 401)
  })
  await assert.rejects(apiFetch('/students/me/home'), (e: { problem: { code: string } }) => e.problem.code === 'STUDENT_REAUTH_REQUIRED')
  await assert.rejects(refreshAccessToken())
  assert.equal(refreshes, 0)
  assert.equal(withAuth().has('Authorization'), false)
  setAccessToken(null)
})

test('student in-memory session restore uses me without refresh', async (t) => {
  const paths: string[] = []
  setAccessToken('student-access', 'STUDENT')
  t.mock.method(globalThis, 'fetch', async (url: string) => {
    paths.push(url)
    return json({ role: 'STUDENT', child: { id: 'child', nickname: '별명', grade: 3, birthYear: 2017 }, nextAction: 'READY', startPath: '/student/home' })
  })
  assert.equal((await createApiGateway().restore()).role, 'STUDENT')
  assert.deepEqual(paths, ['/api/v1/me'])
  setAccessToken(null)
})

test('Web Locks serialize operations across cookie refresh callers', async (t) => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'navigator')
  let pending = Promise.resolve()
  let locks = 0
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { locks: {
    request: (name: string, action: () => Promise<unknown>) => {
      assert.equal(name, 'sagomungchi-auth'); locks++
      const result = pending.then(action); pending = result.then(() => undefined, () => undefined)
      return result
    },
  } } })
  t.after(() => { if (descriptor) Object.defineProperty(globalThis, 'navigator', descriptor); else Reflect.deleteProperty(globalThis, 'navigator') })
  const order: string[] = []
  await Promise.all([
    withAuthLock(async () => { order.push('a-start'); await new Promise((r) => setTimeout(r, 10)); order.push('a-end') }),
    withAuthLock(async () => { order.push('b') }),
  ])
  assert.deepEqual(order, ['a-start', 'a-end', 'b'])
  assert.equal(locks, 2)
})

test('authentication store failure is not disguised as expired login', async (t) => {
  setAccessToken('existing-access')
  t.mock.method(globalThis, 'fetch', async () => json({ code: 'AUTH_UNAVAILABLE', status: 503, title: '인증 저장소 장애' }, 503))
  await assert.rejects(refreshAccessToken(), (e: { problem: { code: string } }) => e.problem.code === 'AUTH_UNAVAILABLE')
  assert.equal(withAuth().get('Authorization'), 'Bearer existing-access')
  setAccessToken(null)
})

test('SESSION_CHANGED does not blindly retry the previous privileged write', async (t) => {
  let count = 0
  t.mock.method(globalThis, 'fetch', async () => { count++; return json({ code: 'SESSION_CHANGED', status: 401, title: '변경' }, 401) })
  await assert.rejects(apiFetch('/children', { method: 'POST', body: '{}' }))
  assert.equal(count, 1)
})
