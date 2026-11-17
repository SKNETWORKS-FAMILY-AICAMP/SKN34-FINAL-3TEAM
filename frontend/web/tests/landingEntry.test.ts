import test from 'node:test'
import assert from 'node:assert/strict'
import { adultLoginPath, landingEntryHref, landingLoginEntry, loginPaths } from '../src/domain/navigation.ts'
import { hasAccessToken, isStudentSession, parentLoginRequired, prepareLoginEntry, refreshAccessToken, setAccessToken, withAuth } from '../src/data/apiClient.ts'

function reset() { setAccessToken('test-reset', 'PARENT'); setAccessToken(null) }
test.afterEach(reset)

test('공개 소개 진입 표시는 로그인 네 경로에만 적용하고 보호 화면에는 적용하지 않는다', () => {
  for (const path of loginPaths) {
    const url = new URL(landingEntryHref(path), 'https://example.test')
    assert.equal(landingLoginEntry(url.pathname, url.search), path)
    assert.equal(landingLoginEntry(path, ''), null)
    assert.equal(landingLoginEntry(path, '?entry=other'), null)
  }
  for (const path of ['/admin/home', '/parent/journal', '/student/home', '//other.example/login', '/oauth/complete'])
    assert.equal(landingLoginEntry(path, '?entry=landing'), null)
})

for (const previous of ['PARENT', 'STUDENT', 'ADMIN'] as const) {
  for (const path of loginPaths) test(`${previous} 사용 뒤 ${path} 선택: 이전 토큰·보호자 쿠키 자동 로그인 없이 인증부터 시작`, async t => {
    setAccessToken(`synthetic-${previous}`, previous)
    let calls = 0
    t.mock.method(globalThis, 'fetch', async () => { calls++; throw new Error('로그인 선택만으로 서버에 요청하면 안 됨') })
    prepareLoginEntry(path)
    assert.equal(hasAccessToken(), false)
    assert.equal(withAuth().has('Authorization'), false)
    assert.equal(isStudentSession(), path === '/student/login')
    assert.equal(parentLoginRequired(), true)
    await assert.rejects(refreshAccessToken(), (error: { problem: { code: string } }) =>
      error.problem.code === (path === '/student/login' ? 'STUDENT_REAUTH_REQUIRED' : 'PARENT_LOGIN_REQUIRED'))
    assert.equal(calls, 0)
  })
}

test('가입·관리자 진입은 보호자 복귀 표식이 있어도 /login으로 덮어쓰지 않는다', () => {
  assert.equal(adultLoginPath('/signup'), '/signup')
  assert.equal(adultLoginPath('/admin/login'), '/admin/login')
  assert.equal(adultLoginPath('/login'), '/login')
  assert.equal(adultLoginPath('/student/login'), '/login')
  assert.equal(adultLoginPath('/parent/settings'), '/login')
})

test('진입 화면을 바꾼 뒤 늦게 도착한 refresh 응답이 이전 역할을 복원하지 않는다', async t => {
  reset()
  let resolveResponse!: (response: Response) => void
  let started!: () => void
  const waiting = new Promise<void>(resolve => { started = resolve })
  t.mock.method(globalThis, 'fetch', () => {
    started()
    return new Promise<Response>(resolve => { resolveResponse = resolve })
  })
  const refreshing = refreshAccessToken()
  await waiting
  prepareLoginEntry('/admin/login')
  resolveResponse(new Response(JSON.stringify({ accessToken: 'stale-parent', role: 'PARENT' }), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  }))
  await assert.rejects(refreshing, (error: { problem: { code: string } }) => error.problem.code === 'SESSION_CHANGED')
  assert.equal(hasAccessToken(), false)
  assert.equal(parentLoginRequired(), true)
})

test('이후 실제 인증으로 받은 토큰만 사용하고 진입 표시는 해제한다', async t => {
  prepareLoginEntry('/student/login')
  prepareLoginEntry('/admin/login')
  setAccessToken('verified-admin-token', 'ADMIN')
  assert.equal(parentLoginRequired(), false)
  assert.equal(isStudentSession(), false)
  assert.equal(withAuth().get('Authorization'), 'Bearer verified-admin-token')
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ accessToken: 'renewed-admin-token', role: 'ADMIN' }), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  }))
  await refreshAccessToken()
  assert.equal(withAuth().get('Authorization'), 'Bearer renewed-admin-token')
})
