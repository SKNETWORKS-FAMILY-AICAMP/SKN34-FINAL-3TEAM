import { http } from 'msw/http'
import { ApiError } from '../../data/apiClient.ts'
import { normalizePairingCode, pinProblem } from '../../domain/studentDevice.ts'
import { fixtureStore as store } from '../fixtures/student.ts'
import { mockAccountChildren, mockIdentity, mockConsentRequired, mockGuardianConsentRequired } from '../fixtures/accounts.ts'
import {
  DEVICE_TTL_MS,
  MAX_PIN_FAILURES,
  PAIRING_TTL_MS,
  currentDevice,
  deviceState,
  hashPin,
  newPairingCode,
  persistDeviceState,
} from '../fixtures/studentDevice.ts'
import { respond, startDeviceStudentSession } from './student.ts'
import { fail, page, parentChild, parentGuard, requireReauth, mockChildConsentMetadata } from './parent.ts'

// 학생 기기 등록·PIN 로그인 목 (API 명세 2.1, 3.11). 실제 서버 계약과 같은 경로·오류 코드를 쓴다.
const save = async <T,>(action: () => Promise<T>, status = 200) =>
  respond(async () => {
    try {
      return await action()
    } finally {
      persistDeviceState()
    }
  }, status)

const deviceInvalid = (): never =>
  fail('STUDENT_DEVICE_INVALID', '이 기기는 학습용으로 등록되어 있지 않아요.', 401)

function pinStatus(childId: string) {
  const p = deviceState.pins[childId]
  return { pinSet: !!p, pinLocked: !!p?.locked }
}

export const studentDeviceHandlers = [
  // 학부모 자녀 목록: 기존 응답에 PIN 상태만 더한다 (API 명세 2.1 개정)
  http.get('/api/v1/children', ({ request }) =>
    respond(async () => {
      parentGuard(request)
      return page((await store.children()).map((c) => ({ ...mockChildConsentMetadata(c), childId: c.id, ...pinStatus(c.id) })))
    }),
  ),

  http.put('/api/v1/children/:childId/pin', ({ request, params }) =>
    save(async () => {
      const c = await parentChild(request, String(params.childId))
      requireReauth(request)
      const { pin } = (await request.json()) as { pin: string }
      const problem = pinProblem(String(pin ?? ''))
      if (problem)
        throw new ApiError({
          status: 422,
          code: 'VALIDATION_FAILED',
          title: problem,
          errors: [{ field: 'pin', reason: problem }],
        })
      deviceState.pins[c.id] = { hash: await hashPin(c.id, pin), failed: 0, locked: false }
      return undefined
    }, 204),
  ),

  http.post('/api/v1/student-devices/pairings', ({ request }) =>
    save(async () => {
      parentGuard(request)
      const { childIds } = (await request.json()) as { childIds: string[] }
      if (!Array.isArray(childIds) || !childIds.length)
        fail('VALIDATION_FAILED', '등록할 자녀를 한 명 이상 골라 주세요.')
      const children = []
      for (const id of new Set(childIds)) children.push(await parentChild(request, id))
      const pairingCode = newPairingCode(),
        expiresAt = Date.now() + PAIRING_TTL_MS
      deviceState.pairings[pairingCode] = { owner: mockIdentity.email, children, expiresAt }
      return { pairingCode, expiresAt: new Date(expiresAt).toISOString() }
    }),
  ),

  http.get('/api/v1/student-devices', ({ request }) =>
    respond(async () => {
      parentGuard(request)
      const owned = deviceState.devices.filter((d) => d.owner === mockIdentity.email && !d.revokedAt)
      const names = new Map((await store.children()).map((c) => [c.id, c.nickname]))
      return page(
        owned.map((d) => ({
          deviceId: d.deviceId,
          label: d.label,
          children: d.childIds.map((childId) => ({ childId, nickname: names.get(childId) ?? '연결 해제된 자녀' })),
          createdAt: d.createdAt,
          lastUsedAt: d.lastUsedAt,
          expiresAt: d.expiresAt,
        })),
      )
    }),
  ),

  http.delete('/api/v1/student-devices/:deviceId', ({ request, params }) =>
    save(async () => {
      parentGuard(request)
      const d = deviceState.devices.find(
        (d) => d.deviceId === String(params.deviceId) && d.owner === mockIdentity.email && !d.revokedAt,
      )
      if (!d) fail('NOT_FOUND', '등록된 기기를 찾을 수 없습니다.', 404)
      d!.revokedAt = new Date().toISOString()
      return undefined
    }, 204),
  ),

  // ── 자녀 기기 (기기 쿠키 대신 개발용 currentDeviceId) ──
  http.post('/api/v1/auth/student/devices', ({ request }) =>
    save(async () => {
      const data = (await request.json()) as { pairingCode: string; label: string }
      const code = normalizePairingCode(String(data.pairingCode ?? ''))
      const pairing = deviceState.pairings[code]
      delete deviceState.pairings[code] // 1회용: 성공·실패 관계없이 조회한 코드는 버린다
      if (!pairing || pairing.expiresAt <= Date.now())
        fail('PAIRING_CODE_INVALID', '코드가 맞지 않거나 시간이 지났어요. 보호자에게 새 코드를 받아 주세요.')
      const now = Date.now()
      const device = {
        deviceId: crypto.randomUUID(),
        label: String(data.label ?? '').trim().slice(0, 30) || '이름 없는 기기',
        owner: pairing!.owner,
        childIds: pairing!.children.map((c) => c.id),
        createdAt: new Date(now).toISOString(),
        lastUsedAt: null,
        expiresAt: new Date(now + DEVICE_TTL_MS).toISOString(),
        revokedAt: null,
      }
      deviceState.devices.push(device)
      deviceState.currentDeviceId = device.deviceId
      return {
        deviceId: device.deviceId,
        children: pairing!.children.map((c) => ({ childId: c.id, nickname: c.nickname })),
      }
    }, 201),
  ),

  http.get('/api/v1/auth/student/profiles', () =>
    respond(async () => {
      const d = currentDevice() ?? deviceInvalid()
      const owned = mockAccountChildren.get(d.owner) ?? []
      return page(
        d.childIds
          .map((id) => owned.find((c) => c.id === id))
          .filter((c) => !!c)
          .map((c) => ({ childId: c.id, nickname: c.nickname, pinSet: !!deviceState.pins[c.id], locked: !!deviceState.pins[c.id]?.locked })),
      )
    }),
  ),

  http.post('/api/v1/auth/student/login', ({ request }) =>
    save(async () => {
      // 검사 순서: 기기 → 기기에 등록된 자녀 → 소유 학부모 연결 → PIN 설정 → 잠금 → PIN 일치 (API 명세 3.11)
      const d = currentDevice() ?? deviceInvalid()
      const { childId, pin } = (await request.json()) as { childId: string; pin: string }
      if (!d.childIds.includes(childId)) deviceInvalid()
      const owned = mockAccountChildren.get(d.owner) ?? []
      const child = owned.find((c) => c.id === childId)
      if (!child || mockConsentRequired(d.owner) || mockGuardianConsentRequired(childId, d.owner))
        fail('CHILD_NOT_LINKED', '보호자 연결·동의를 확인해 주세요.', 403)
      const p = deviceState.pins[childId]
      if (!p) fail('STUDENT_PIN_NOT_SET', '아직 PIN이 없어요. 보호자와 함께 시작해 주세요.', 409)
      if (p!.locked) fail('STUDENT_PIN_LOCKED', 'PIN이 잠겼어요. 보호자에게 다시 정해 달라고 해 주세요.', 423)
      if (p!.hash !== (await hashPin(childId, String(pin ?? '')))) {
        p!.failed += 1
        if (p!.failed >= MAX_PIN_FAILURES) {
          p!.locked = true
          fail('STUDENT_PIN_LOCKED', 'PIN이 잠겼어요. 보호자에게 다시 정해 달라고 해 주세요.', 423)
        }
        throw new ApiError({
          status: 401,
          code: 'STUDENT_PIN_INVALID',
          title: 'PIN이 맞지 않아요.',
          remainingAttempts: MAX_PIN_FAILURES - p!.failed,
        })
      }
      p!.failed = 0
      d.lastUsedAt = new Date().toISOString()
      const accessToken = startDeviceStudentSession(child!, owned)
      return {
        accessToken,
        role: 'STUDENT',
        child: { childId: child!.id, nickname: child!.nickname, grade: child!.grade, plan: child!.plan },
      }
    }),
  ),
]
