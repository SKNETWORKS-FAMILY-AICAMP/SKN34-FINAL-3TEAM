import test from 'node:test'
import assert from 'node:assert/strict'
import {
  formatPairingCode,
  loginState,
  normalizePairingCode,
  pinProblem,
  remaining,
  validPairingCode,
} from '../src/domain/studentDevice.ts'
import { studentDeviceApi } from '../src/data/studentDevice/api.ts'
import { ApiError, withAuth, setAccessToken } from '../src/data/apiClient.ts'

test('PIN 규칙: 숫자 4~6자리, 같은 숫자 반복·연속 숫자 거부', () => {
  for (const ok of ['4831', '90210', '135792', '1357'])
    assert.equal(pinProblem(ok), null, ok)
  for (const bad of ['123', '1234567', '12a4', '', '1111', '000000', '1234', '4321', '56789', '987654'])
    assert.notEqual(pinProblem(bad), null, bad)
})

test('페어링 코드 정리·검사·표시와 남은 시간', () => {
  assert.equal(normalizePairingCode(' ab3d-ef9h '), 'AB3DEF9H')
  assert.equal(validPairingCode('AB3DEF9H'), true)
  assert.equal(validPairingCode('AB3DEF9'), false)
  assert.equal(validPairingCode('AB3DEF9!'), false)
  assert.equal(formatPairingCode('AB3DEF9H'), 'AB3D EF9H')
  const now = Date.parse('2026-10-27T10:00:00Z')
  assert.equal(remaining('2026-10-27T10:10:00Z', now), '10:00')
  assert.equal(remaining('2026-10-27T10:00:05.200Z', now), '0:06')
  assert.equal(remaining('2026-10-27T10:00:00Z', now), null)
})

test('오류 코드를 아이가 읽을 상태로 바꾼다', () => {
  assert.deepEqual(loginState('STUDENT_PIN_INVALID', 2), { kind: 'wrong-pin', remainingAttempts: 2 })
  assert.deepEqual(loginState('STUDENT_PIN_INVALID'), { kind: 'wrong-pin', remainingAttempts: null })
  assert.equal(loginState('STUDENT_PIN_LOCKED').kind, 'locked')
  assert.equal(loginState('STUDENT_PIN_NOT_SET').kind, 'pin-not-set')
  assert.equal(loginState('STUDENT_DEVICE_INVALID').kind, 'invalid-device')
  assert.equal(loginState('CHILD_NOT_LINKED').kind, 'not-linked')
  assert.equal(loginState('REQUEST_FAILED', undefined, '').kind, 'other')
})

test('PIN 로그인 어댑터: STUDENT 토큰을 메모리에 두고 DEVICE 진입으로 표시, refresh 쿠키 없음', async (t) => {
  setAccessToken(null)
  const seen: { path: string; init: RequestInit }[] = []
  t.mock.method(globalThis, 'fetch', async (path: string, init: RequestInit) => {
    seen.push({ path, init })
    return new Response(
      JSON.stringify({
        accessToken: 'student-token',
        role: 'STUDENT',
        child: { childId: 'c1', nickname: '별빛', grade: 3 },
      }),
      { headers: { 'Content-Type': 'application/json' } },
    )
  })
  const session = await studentDeviceApi.login('c1', '4831')
  assert.equal(session.role, 'STUDENT')
  assert.equal(session.entry, 'DEVICE')
  assert.equal(session.child?.id, 'c1')
  assert.equal(seen[0].path, '/api/v1/auth/student/login')
  assert.deepEqual(JSON.parse(String(seen[0].init.body)), { childId: 'c1', pin: '4831' })
  assert.equal(withAuth().get('Authorization'), 'Bearer student-token')
  setAccessToken(null)
})

test('PIN 로그인 어댑터: 다른 자녀 응답은 계약 오류로 거부하고 토큰을 저장하지 않음', async (t) => {
  setAccessToken(null)
  t.mock.method(globalThis, 'fetch', async () =>
    new Response(
      JSON.stringify({ accessToken: 'x', role: 'STUDENT', child: { childId: 'other', nickname: '다른', grade: 4 } }),
      { headers: { 'Content-Type': 'application/json' } },
    ),
  )
  await assert.rejects(studentDeviceApi.login('c1', '4831'), (e) => e instanceof ApiError && e.problem.code === 'CONTRACT_NOT_READY')
  assert.equal(withAuth().get('Authorization'), null)
})

test('PIN 설정은 X-Reauth-Token과 PUT으로 보낸다', async (t) => {
  const seen: RequestInit[] = []
  t.mock.method(globalThis, 'fetch', async (_p: string, init: RequestInit) => {
    seen.push(init)
    return new Response(null, { status: 204 })
  })
  await studentDeviceApi.setPin('c1', '4831', 'reauth-1')
  assert.equal(seen[0].method, 'PUT')
  assert.equal(new Headers(seen[0].headers).get('X-Reauth-Token'), 'reauth-1')
})
