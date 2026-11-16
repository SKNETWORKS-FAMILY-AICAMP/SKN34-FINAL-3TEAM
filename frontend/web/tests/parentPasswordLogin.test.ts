import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { setupServer } from 'msw/node'
import { parentHandlers } from '../src/mocks/handlers/parent.ts'
import { studentHandlers } from '../src/mocks/handlers/student.ts'
import { serviceHandlers } from '../src/mocks/handlers/service.ts'
import { mockConsentHistory, passwordParentKey } from '../src/mocks/fixtures/accounts.ts'
import { createApiGateway } from '../src/data/classroom/apiGateway.ts'
import { setAccessToken } from '../src/data/apiClient.ts'
import { signupProblem } from '../src/domain/parentAccount.ts'

// #415 학부모 ID·비밀번호 가입·로그인·비밀번호 재확인: MSW가 core와 같은 계약인지 확인한다.
Object.defineProperty(globalThis, 'location', { value: new URL('http://localhost/'), configurable: true })
const server = setupServer(...parentHandlers, ...serviceHandlers, ...studentHandlers)
let token = '', serial = 0
async function call(path: string, method = 'GET', body?: unknown, grant?: string) {
  const response = await fetch('http://localhost/api/v1' + path, { method,
    headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json', ...(grant ? { 'X-Reauth-Token': grant } : {}) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
  return { status: response.status, data: response.status === 204 ? null : await response.json() }
}
const newId = () => `Parent${Date.now() % 100000}${++serial}`
before(() => server.listen({ onUnhandledFrame: 'error' }))
after(() => server.close())

test('가입은 ID를 소문자로 저장하고 동의 화면으로 시작하며 /me는 PASSWORD 방식과 loginId를 준다', async () => {
  const id = newId()
  for (const [body, code] of [
    [{ loginId: 'ab', password: 'password-415', name: '보호자' }, 'VALIDATION_FAILED'],
    [{ loginId: 'me@example.com', password: 'password-415', name: '보호자' }, 'VALIDATION_FAILED'],
    [{ loginId: id, password: 'short', name: '보호자' }, 'VALIDATION_FAILED'],
    [{ loginId: id, password: 'password-415', name: ' ' }, 'VALIDATION_FAILED'],
  ] as const) {
    const r = await call('/auth/parent/signup', 'POST', body)
    assert.equal(r.status, 400); assert.equal(r.data.code, code)
  }
  const signup = await call('/auth/parent/signup', 'POST', { loginId: id, password: 'password-415', name: '보호자' })
  assert.equal(signup.status, 200)
  assert.equal(signup.data.role, 'PARENT')
  assert.equal(signup.data.nextAction, 'CONSENT_REQUIRED')
  token = signup.data.accessToken
  const me = await call('/me')
  assert.equal(me.data.authMethod, 'PASSWORD')
  assert.equal(me.data.loginId, id.toLowerCase())
  assert.equal(me.data.email, null)
  const taken = await call('/auth/parent/signup', 'POST', { loginId: id.toUpperCase(), password: 'password-415', name: '보호자' })
  assert.equal(taken.status, 409); assert.equal(taken.data.code, 'LOGIN_ID_TAKEN')
})

test('로그인 실패는 같은 401이고 5회째부터 잠기며, 이메일 시연 로그인은 GOOGLE 방식이다', async () => {
  const id = newId()
  assert.equal((await call('/auth/parent/signup', 'POST', { loginId: id, password: 'password-415', name: '보호자' })).status, 200)
  const unknown = await call('/auth/parent/login', 'POST', { loginId: 'nobody415', password: 'password-415' })
  assert.equal(unknown.status, 401); assert.equal(unknown.data.code, 'INVALID_CREDENTIALS')
  const ok = await call('/auth/parent/login', 'POST', { loginId: id.toUpperCase(), password: 'password-415' })
  assert.equal(ok.status, 200)
  for (let i = 0; i < 4; i++) assert.equal((await call('/auth/parent/login', 'POST', { loginId: id, password: 'wrong-pass' })).status, 401)
  const locked = await call('/auth/parent/login', 'POST', { loginId: id, password: 'wrong-pass' })
  assert.equal(locked.status, 423); assert.equal(locked.data.code, 'LOGIN_LOCKED')
  assert.equal((await call('/auth/parent/login', 'POST', { loginId: id, password: 'password-415' })).status, 423)
  const google = await call('/auth/login', 'POST', { email: 'parent@example.test', password: 'demo-only' })
  token = google.data.accessToken
  assert.equal((await call('/me')).data.authMethod, 'GOOGLE')
  const mismatch = await call('/me/reauth/password', 'POST', { purpose: 'WITHDRAWAL', password: 'password-415' })
  assert.equal(mismatch.status, 409); assert.equal(mismatch.data.code, 'REAUTH_METHOD_MISMATCH')
})

test('비밀번호 재확인은 목적 규칙을 검사하고 1회 토큰으로 보호자 비밀번호를 정한다', async () => {
  const id = newId()
  const signup = await call('/auth/parent/signup', 'POST', { loginId: id, password: 'password-415', name: '보호자' })
  token = signup.data.accessToken
  mockConsentHistory.delete(passwordParentKey(id.toLowerCase()))
  assert.equal((await call('/me/reauth/password', 'POST', { purpose: 'PIN_CHANGE', password: 'password-415' })).data.code, 'VALIDATION_FAILED')
  const wrong = await call('/me/reauth/password', 'POST', { purpose: 'GUARDIAN_PASSWORD', password: 'wrong-pass' })
  assert.equal(wrong.status, 403); assert.equal(wrong.data.code, 'REAUTH_PASSWORD_INVALID')
  const proof = await call('/me/reauth/password', 'POST', { purpose: 'GUARDIAN_PASSWORD', password: 'password-415' })
  assert.equal(proof.status, 200); assert.equal(typeof proof.data.reauthToken, 'string')
  const saved = await call('/me/guardian-password', 'PUT', { password: '2580' }, proof.data.reauthToken)
  assert.equal(saved.status, 200); assert.equal(saved.data.set, true)
  assert.equal((await call('/me/guardian-password', 'PUT', { password: '2580' }, proof.data.reauthToken)).status, 403)
})

test('세션 복원은 /me의 authMethod를 담고, 가입 입력 검사는 core 규칙과 같다', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url: string) => {
    if (url.endsWith('/auth/refresh')) return Response.json({ accessToken: 'parent-access', role: 'PARENT' })
    return Response.json({ role: 'PARENT', permissions: [], authMethod: 'PASSWORD', loginId: 'parent415', email: null, nextAction: 'READY', startPath: '/parent/journal' })
  })
  setAccessToken(null)
  assert.equal((await createApiGateway().restore()).authMethod, 'PASSWORD')
  setAccessToken(null)
  assert.equal(signupProblem('ab', 'password-415', 'password-415', '보호자'), '아이디는 영문과 숫자 4~30자로 입력해 주세요.')
  assert.equal(signupProblem('me@example', 'password-415', 'password-415', '보호자'), '아이디는 영문과 숫자 4~30자로 입력해 주세요.')
  assert.equal(signupProblem('parent415', 'short', 'short', '보호자'), '비밀번호는 8~128자로 입력해 주세요.')
  assert.equal(signupProblem('parent415', 'password-415', 'password-416', '보호자'), '두 번 입력한 비밀번호가 다릅니다.')
  assert.equal(signupProblem('Parent415', 'password-415', 'password-415', '보호자'), null)
})
