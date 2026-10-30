import { ApiError, apiFetch, setAccessToken } from '../apiClient.ts'
import { json } from '../parent/api.ts'
import type { Child, Session } from '../../domain/classroom.ts'
import type { Pairing, StudentDevice, StudentProfile } from '../../domain/studentDevice.ts'

const contractError = (detail: string): never => {
  throw new ApiError({
    code: 'CONTRACT_NOT_READY',
    status: 502,
    title: '백엔드 응답 계약 확인이 필요합니다.',
    detail,
  })
}
const item = (id: string) => encodeURIComponent(id)

/**
 * 학생 기기·PIN API (API 명세 2.1, 3.11).
 * 기기 자격증명은 httpOnly 쿠키(path /api/v1/auth/student)라 화면 코드가 읽거나 저장하지 않는다.
 * `credentials: 'same-origin'`으로 브라우저가 알아서 보낸다.
 */
export const studentDeviceApi = {
  // #45: proof is bound to this session, PIN_CHANGE and exactly one child.
  startPinReauth: (childId: string) => apiFetch<{ challengeId: string; authorizationUrl: string; expiresAt: string }>(
    '/me/reauth', json({ purpose: 'PIN_CHANGE', childId })),
  finishPinReauth: (challengeId: string) => apiFetch<{ reauthToken: string; expiresAt: string }>(
    '/me/reauth', json({ challengeId })),
  // ── 학부모 ─────────────────────────────────────────
  createPairing: (childIds: string[]) =>
    apiFetch<Pairing>('/student-devices/pairings', json({ childIds })),
  devices: async (signal?: AbortSignal) => {
    const raw = await apiFetch<{ items?: StudentDevice[] } | StudentDevice[]>('/student-devices', {
      signal,
    })
    const items = Array.isArray(raw) ? raw : raw.items
    if (!Array.isArray(items)) return contractError('기기 목록의 items 필드가 없습니다.')
    return items
  },
  revoke: (deviceId: string) =>
    apiFetch<void>(`/student-devices/${item(deviceId)}`, { method: 'DELETE' }),
  setPin: (childId: string, pin: string, reauthToken: string) =>
    apiFetch<void>(`/children/${item(childId)}/pin`, {
      ...json({ pin }, 'PUT'),
      headers: { 'Content-Type': 'application/json', 'X-Reauth-Token': reauthToken },
    }),

  // ── 자녀 기기 ───────────────────────────────────────
  register: (pairingCode: string, label: string) =>
    apiFetch<{ deviceId: string; children: { childId: string; nickname: string }[] }>(
      '/auth/student/devices',
      json({ pairingCode, label }),
    ),
  profiles: async (signal?: AbortSignal) => {
    const raw = await apiFetch<{ items?: StudentProfile[] } | StudentProfile[]>(
      '/auth/student/profiles',
      { signal },
    )
    const items = Array.isArray(raw) ? raw : raw.items
    if (!Array.isArray(items)) return contractError('기기 프로필 목록을 받지 못했습니다.')
    return items
  },
  /** PIN 로그인. refresh token은 받지 않으므로 access 만료 시 PIN을 다시 입력한다. */
  async login(childId: string, pin: string): Promise<Session> {
    const raw = await apiFetch<{ accessToken?: unknown; role?: unknown; child?: Record<string, unknown> }>(
      '/auth/student/login',
      json({ childId, pin }),
    )
    if (raw.role !== 'STUDENT' || typeof raw.accessToken !== 'string')
      return contractError('학생 세션 role·accessToken이 필요합니다.')
    const c = raw.child ?? {}
    const grade = Number(c.grade)
    if (c.childId !== childId || typeof c.nickname !== 'string' || !(grade >= 3 && grade <= 6))
      return contractError('로그인한 자녀 정보가 요청과 다릅니다.')
    setAccessToken(raw.accessToken, 'STUDENT')
    const child: Child = {
      id: childId,
      nickname: c.nickname,
      grade,
      // PIN 로그인 응답(API 명세 3.11)에는 출생연도가 없다. 학생 화면은 쓰지 않으므로 0으로 둔다.
      birthYear: Number(c.birthYear ?? 0),
      plan: c.plan === 'PREMIUM' || c.plan === 'FREE' ? c.plan : undefined,
    }
    return { role: 'STUDENT', entry: 'DEVICE', child }
  },
}

/** DEV 시연 화면에서만 사용하는 기기 준비. 미사용 export는 운영 빌드에서 제거합니다. */
export async function prepareDemoStudentDevice() {
  const raw = await apiFetch<{ deviceId?: unknown }>('/auth/student/demo-device', { method: 'POST' })
  if (typeof raw?.deviceId !== 'string' || !raw.deviceId)
    return contractError('시연 기기 등록 결과의 deviceId가 필요합니다.')
  const { temporaryStudentPin } = await import('../../mocks/fixtures/studentPinDemo.ts')
  return { deviceId: raw.deviceId, pin: temporaryStudentPin }
}
