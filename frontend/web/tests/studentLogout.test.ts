import test from 'node:test'
import assert from 'node:assert/strict'
import { createApiGateway } from '../src/data/classroom/apiGateway.ts'
import { setAccessToken, withAuth, parentLoginRequired, requireParentLogin, refreshAccessToken, watchAuthChange } from '../src/data/apiClient.ts'

function reset() { setAccessToken('reset', 'PARENT'); setAccessToken(null) }
const problem = (status: number, code: string) => new Response(JSON.stringify({ status, code, title: code }),
  { status, headers: { 'Content-Type': 'application/json' } })

test('학생 종료는 전용 API만 호출하고 보호자 쿠키 자동 복원을 차단한다', async (t) => {
  t.after(reset)
  setAccessToken('student-only', 'STUDENT')
  const paths: string[] = []
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    paths.push(url)
    assert.equal(new Headers(init.headers).get('Authorization'), 'Bearer student-only')
    return new Response(null, { status: 204 })
  })
  await createApiGateway().logout()
  assert.deepEqual(paths, ['/api/v1/auth/student/logout'])
  assert.equal(withAuth().has('Authorization'), false)
  assert.equal(parentLoginRequired(), true)
  await assert.rejects(refreshAccessToken(), (e: { problem: { code: string } }) => e.problem.code === 'PARENT_LOGIN_REQUIRED')
  assert.equal(paths.length, 1)
})

test('만료된 학생 종료는 보호자 refresh로 재시도하지 않고 503은 성공으로 숨기지 않는다', async (t) => {
  t.after(reset)
  let calls = 0
  let status = 503
  setAccessToken('student-only', 'STUDENT')
  t.mock.method(globalThis, 'fetch', async (url: string) => {
    assert.equal(url, '/api/v1/auth/student/logout'); calls++
    return problem(status, status === 503 ? 'AUTH_UNAVAILABLE' : 'TOKEN_EXPIRED')
  })
  await assert.rejects(createApiGateway().logout())
  assert.equal(withAuth().get('Authorization'), 'Bearer student-only')
  assert.equal(parentLoginRequired(), false)
  status = 401
  await createApiGateway().logout()
  assert.equal(parentLoginRequired(), true)
  assert.equal(calls, 2)
})

test('보호자 로그아웃은 기존 전체 로그아웃 경로를 유지한다', async (t) => {
  t.after(reset)
  setAccessToken('parent-only', 'PARENT')
  t.mock.method(globalThis, 'fetch', async (url: string) => {
    assert.equal(url, '/api/v1/auth/logout')
    return new Response(null, { status: 204 })
  })
  await createApiGateway().logout()
  assert.equal(parentLoginRequired(), false)
})

test('보호자 진입 표식은 탭에만 남고 다른 탭 로그인으로 학생 역할을 바꾸지 않는다', async (t) => {
  const names = ['window', 'sessionStorage', 'BroadcastChannel'] as const
  const descriptors = names.map((name) => Object.getOwnPropertyDescriptor(globalThis, name))
  const values = new Map<string, string>()
  const windowStub = Object.assign(new EventTarget(), { location: { pathname: '/login' } })
  const channels: EventTarget[] = []
  class Channel extends EventTarget { constructor() { super(); channels.push(this) } postMessage() { throw new Error('Student logout must not broadcast') } }
  Object.defineProperty(globalThis, 'window', { configurable: true, value: windowStub })
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  } })
  Object.defineProperty(globalThis, 'BroadcastChannel', { configurable: true, value: Channel })
  t.after(() => { reset(); names.forEach((name, i) => { if (descriptors[i]) Object.defineProperty(globalThis, name, descriptors[i]!); else Reflect.deleteProperty(globalThis, name) }) })
  let localEntries = 0, changed = 0
  windowStub.addEventListener('sagomungchi:parent-login-required', () => localEntries++)
  const stop = watchAuthChange(() => changed++)
  t.after(stop)
  windowStub.location.pathname = '/student/login'
  setAccessToken(null)
  channels[0].dispatchEvent(new MessageEvent('message', { data: 'PARENT' }))
  assert.equal(changed, 0)
  windowStub.location.pathname = '/login'
  setAccessToken('student', 'STUDENT')
  channels[0].dispatchEvent(new MessageEvent('message', { data: 'PARENT' }))
  assert.equal(withAuth().get('Authorization'), 'Bearer student')
  t.mock.method(globalThis, 'fetch', async () => new Response(null, { status: 204 }))
  await createApiGateway().logout()
  assert.equal(localEntries, 1)
  assert.deepEqual([...values], [['sagomungchi:parent-login-required', 'true']])
  channels[0].dispatchEvent(new MessageEvent('message', { data: 'PARENT' }))
  assert.equal(changed, 0)
  assert.equal(parentLoginRequired(), true)
  requireParentLogin() // PIN page's guardian button follows the same local transition.
  assert.equal(localEntries, 2)
  setAccessToken('oauth-parent', 'PARENT')
  assert.equal(parentLoginRequired(), false)
  assert.equal(values.size, 0)
})
