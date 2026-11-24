import test from 'node:test'
import assert from 'node:assert/strict'
import { apiFetch, setAccessToken, withAuth, renewStudentSession } from '../src/data/apiClient.ts'
import { readStudentToken, studentClaims, studentTokenKey } from '../src/data/studentSession.ts'

const jwt = (sid = 'student-a', age = 61, remaining = 1739) => {
  const now = Math.floor(Date.now() / 1000)
  return `test.${btoa(JSON.stringify({ role: 'STUDENT', sid, iat: now - age, exp: now + remaining }))}.signature`
}
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
test.afterEach(() => setAccessToken(null))

test('only student credentials persist; reload reader rejects malformed/adult values and storage failure is nonfatal', () => {
  const values = new Map<string, string>()
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key),
  } })
  try {
    const token = jwt()
    setAccessToken(token, 'STUDENT')
    assert.equal(readStudentToken(), token)
    setAccessToken('parent', 'PARENT')
    assert.equal(values.has(studentTokenKey), false)
    values.set(studentTokenKey, 'garbage')
    assert.equal(readStudentToken(), null)
    assert.equal(studentClaims(`x.${btoa(JSON.stringify({ role: 'ADMIN', sid: 'a', iat: 1, exp: 999 }))}.x`), null)
    setAccessToken(token, 'STUDENT')
    setAccessToken(null)
    assert.equal(readStudentToken(), null)
    Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, get: () => { throw new Error('blocked') } })
    assert.doesNotThrow(() => setAccessToken(token, 'STUDENT'))
    assert.equal(readStudentToken(), null)
  } finally { Reflect.deleteProperty(globalThis, 'sessionStorage') }
})

test('renew is coalesced, throttled for 60 seconds, and does not touch adult refresh', async t => {
  setAccessToken(jwt(), 'STUDENT')
  let calls = 0
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    assert.equal(url, '/api/v1/auth/student/renew')
    assert.equal(new Headers(init.headers).get('X-Requested-With'), 'XMLHttpRequest')
    calls++
    await new Promise(resolve => setTimeout(resolve, 10))
    return json({ accessToken: jwt('student-a', 0, 1800), expiresIn: 1800 })
  })
  await Promise.all([renewStudentSession(), renewStudentSession(), renewStudentSession()])
  await renewStudentSession()
  assert.equal(calls, 1)
  setAccessToken('parent', 'PARENT')
  await renewStudentSession()
  assert.equal(calls, 1)
})

test('polling and successful API requests do not renew inactive student sessions', async t => {
  setAccessToken(jwt('polling'), 'STUDENT')
  const paths: string[] = []
  t.mock.method(globalThis, 'fetch', async (url: string) => { paths.push(url); return json({ ok: true }) })
  await apiFetch('/me')
  await apiFetch('/students/a/home')
  assert.deepEqual(paths, ['/api/v1/me', '/api/v1/students/a/home'])
})

test('401 clears credentials, network failure preserves them and is throttled', async t => {
  setAccessToken(jwt('expired'), 'STUDENT')
  t.mock.method(globalThis, 'fetch', async () => json({ code: 'TOKEN_EXPIRED' }, 401))
  await assert.rejects(renewStudentSession(), /학생 로그인/)
  assert.equal(withAuth().has('Authorization'), false)
  const token = jwt('network')
  setAccessToken(token, 'STUDENT')
  let calls = 0
  t.mock.method(globalThis, 'fetch', async () => { calls++; throw new TypeError('offline') })
  await assert.rejects(renewStudentSession())
  await renewStudentSession()
  assert.equal(calls, 1)
  assert.equal(withAuth().get('Authorization'), `Bearer ${token}`)
})

test('late renewal cannot restore a logged-out or switched session', async t => {
  let release!: (response: Response) => void
  t.mock.method(globalThis, 'fetch', () => new Promise<Response>(resolve => { release = resolve }))
  setAccessToken(jwt('old'), 'STUDENT')
  const pending = renewStudentSession()
  setAccessToken('admin', 'ADMIN')
  release(json({ accessToken: jwt('old', 0), expiresIn: 1800 }))
  await pending
  assert.equal(withAuth().get('Authorization'), 'Bearer admin')
})

test('an old in-flight API expiry uses the renewed token without logging out', async t => {
  const old = jwt('race')
  const fresh = jwt('race', 0, 1800)
  setAccessToken(old, 'STUDENT')
  let release!: (response: Response) => void
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    if (url.endsWith('/renew')) return json({ accessToken: fresh, expiresIn: 1800 })
    if (new Headers(init.headers).get('Authorization') === `Bearer ${fresh}`) return json({ ok: true })
    return new Promise<Response>(resolve => { release = resolve })
  })
  const pending = apiFetch('/me')
  await renewStudentSession()
  release(json({ code: 'TOKEN_EXPIRED' }, 401))
  assert.deepEqual(await pending, { ok: true })
  assert.equal(withAuth().get('Authorization'), `Bearer ${fresh}`)
})
