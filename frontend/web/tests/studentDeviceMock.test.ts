import test from 'node:test'
import assert from 'node:assert/strict'

// MSW 핸들러는 상대 경로('/api/v1/...')로 등록되어 있어 Node에서는 기준 주소가 필요하다.
Object.defineProperty(globalThis, 'location', { value: new URL('http://localhost/'), configurable: true })
const { setupServer } = await import('msw/node')
const { studentDeviceHandlers } = await import('../src/mocks/handlers/studentDevice.ts')
const { parentHandlers } = await import('../src/mocks/handlers/parent.ts')
const { studentHandlers } = await import('../src/mocks/handlers/student.ts')
const { deviceState, setDeviceScenario } = await import('../src/mocks/fixtures/studentDevice.ts')

const server = setupServer(...studentDeviceHandlers, ...parentHandlers, ...studentHandlers)
server.listen({ onUnhandledRequest: 'error' })
test.after(() => server.close())

const base = 'http://localhost/api/v1'
let parentToken = ''
async function call(path: string, init: RequestInit & { token?: string } = {}) {
  const headers = new Headers(init.headers)
  if (init.body) headers.set('Content-Type', 'application/json')
  if (init.token) headers.set('Authorization', `Bearer ${init.token}`)
  const res = await fetch(base + path, { ...init, headers })
  const text = await res.text()
  return { status: res.status, body: text ? JSON.parse(text) : null }
}
async function parentLogin() {
  const r = await call('/auth/login', { method: 'POST', body: JSON.stringify({ email: 'parent@example.test', password: 'demo-only' }) })
  parentToken = r.body.accessToken
  return parentToken
}
async function reauth(childId: string) {
  const started = await call('/me/reauth', { method: 'POST', body: JSON.stringify({ purpose: 'PIN_CHANGE', childId }), token: parentToken })
  const r = await call('/me/reauth', { method: 'POST', body: JSON.stringify({ challengeId: started.body.challengeId }), token: parentToken })
  return r.body.reauthToken as string
}
async function setPin(childId: string, pin: string) {
  return call(`/children/${childId}/pin`, {
    method: 'PUT',
    body: JSON.stringify({ pin }),
    token: parentToken,
    headers: { 'X-Reauth-Token': await reauth(childId) },
  })
}
async function pair(childIds: string[]) {
  return (await call('/student-devices/pairings', { method: 'POST', body: JSON.stringify({ childIds }), token: parentToken })).body
}
const login = (childId: string, pin: string) =>
  call('/auth/student/login', { method: 'POST', body: JSON.stringify({ childId, pin }) })

test('미등록 기기: 프로필·PIN 로그인 모두 STUDENT_DEVICE_INVALID', async () => {
  deviceState.currentDeviceId = null
  assert.equal((await call('/auth/student/profiles')).body.code, 'STUDENT_DEVICE_INVALID')
  const r = await login('demo-seoyun', '4831')
  assert.equal(r.status, 401)
  assert.equal(r.body.code, 'STUDENT_DEVICE_INVALID')
})

test('PIN 설정은 재확인 필요, 반복·연속 PIN 거부, 자녀 목록에 상태 표시', async () => {
  await parentLogin()
  const noReauth = await call('/children/demo-seoyun/pin', { method: 'PUT', body: JSON.stringify({ pin: '4831' }), token: parentToken })
  assert.equal(noReauth.body.code, 'REAUTH_REQUIRED')
  assert.equal((await setPin('demo-seoyun', '1234')).status, 422)
  assert.equal((await setPin('demo-seoyun', '4831')).status, 204)
  const children = (await call('/children', { token: parentToken })).body.items
  const seoyun = children.find((c: { childId: string }) => c.childId === 'demo-seoyun')
  assert.equal(seoyun.pinSet, true)
  assert.equal(seoyun.pinLocked, false)
  assert.equal('pin' in seoyun || 'hash' in seoyun, false)
})

test('페어링 코드 1회용 → 기기 등록 → 프로필 → 5회 실패 잠금 → 재설정으로 해제', async () => {
  await parentLogin()
  const { pairingCode, expiresAt } = await pair(['demo-seoyun', 'demo-doyun'])
  assert.match(pairingCode, /^[A-Z0-9]{8}$/)
  assert.ok(Date.parse(expiresAt) - Date.now() <= 10 * 60 * 1000)
  const reg = await call('/auth/student/devices', { method: 'POST', body: JSON.stringify({ pairingCode, label: '거실 컴퓨터' }) })
  assert.equal(reg.status, 201)
  assert.equal(reg.body.children.length, 2)
  const reuse = await call('/auth/student/devices', { method: 'POST', body: JSON.stringify({ pairingCode, label: '다른 기기' }) })
  assert.equal(reuse.body.code, 'PAIRING_CODE_INVALID')

  const profiles = (await call('/auth/student/profiles')).body.items
  assert.deepEqual(profiles.map((p: { childId: string }) => p.childId), ['demo-seoyun', 'demo-doyun'])
  assert.equal((await login('demo-doyun', '4831')).body.code, 'STUDENT_PIN_NOT_SET')

  for (let i = 1; i <= 4; i++) {
    const r = await login('demo-seoyun', '9999')
    assert.equal(r.body.code, 'STUDENT_PIN_INVALID')
    assert.equal(r.body.remainingAttempts, 5 - i)
  }
  const fifth = await login('demo-seoyun', '9999')
  assert.equal(fifth.status, 423)
  assert.equal((await login('demo-seoyun', '4831')).body.code, 'STUDENT_PIN_LOCKED', '잠긴 뒤에는 맞는 PIN도 거부')

  await parentLogin()
  assert.equal((await call('/children', { token: parentToken })).body.items[0].pinLocked, true)
  assert.equal((await setPin('demo-seoyun', '4831')).status, 204)
  const ok = await login('demo-seoyun', '4831')
  assert.equal(ok.status, 200)
  assert.equal(ok.body.role, 'STUDENT')
  assert.equal(ok.body.child.childId, 'demo-seoyun')
  // 학생 토큰으로 학생 홈은 열리고, refresh는 발급하지 않는다
  assert.equal((await call('/students/me/home', { token: ok.body.accessToken })).status, 200)
  assert.equal((await call('/auth/refresh', { method: 'POST' })).status, 401)
})

test('해제·만료 기기는 PIN이 맞아도 거부, 기기 목록에서 해제 반영', async () => {
  await parentLogin()
  const { pairingCode } = await pair(['demo-seoyun'])
  await call('/auth/student/devices', { method: 'POST', body: JSON.stringify({ pairingCode, label: '태블릿' }) })
  assert.equal((await login('demo-seoyun', '4831')).status, 200)

  await parentLogin()
  const list = (await call('/student-devices', { token: parentToken })).body.items
  const tablet = list.find((d: { label: string }) => d.label === '태블릿')
  assert.ok(tablet.lastUsedAt)
  assert.equal((await call(`/student-devices/${tablet.deviceId}`, { method: 'DELETE', token: parentToken })).status, 204)
  assert.equal((await login('demo-seoyun', '4831')).body.code, 'STUDENT_DEVICE_INVALID')
  assert.equal((await call('/student-devices', { token: parentToken })).body.items.some((d: { deviceId: string }) => d.deviceId === tablet.deviceId), false)

  const again = await pair(['demo-seoyun'])
  await call('/auth/student/devices', { method: 'POST', body: JSON.stringify({ pairingCode: again.pairingCode, label: '새 태블릿' }) })
  setDeviceScenario('device-expired')
  assert.equal((await login('demo-seoyun', '4831')).body.code, 'STUDENT_DEVICE_INVALID')
})

test('명시적 가상 학생 준비 후 5090 로그인: 오입력은 거절하고 학생 토큰만 발급', async () => {
  const prepared = await call('/auth/student/demo-device', { method: 'POST' })
  assert.equal(prepared.status, 201)
  const profiles = (await call('/auth/student/profiles')).body.items
  assert.equal(profiles[0].childId, 'demo-pin-student')
  assert.equal((await login('demo-pin-student', '1234')).body.code, 'STUDENT_PIN_INVALID')
  const entered = await login('demo-pin-student', '5090')
  assert.equal(entered.status, 200)
  assert.equal(entered.body.role, 'STUDENT')
  assert.equal((await call('/children', { token: entered.body.accessToken })).status, 403)
})
