/** 학생 기기 등록·PIN 로그인 규칙 (P01 개정, API 명세 3.11, FN-ACC-05·14) */

export const PIN_MIN = 4
export const PIN_MAX = 6
export const PAIRING_CODE_LENGTH = 8

/** 기기에서 고를 수 있는 자녀 프로필. PIN 원문·실패 횟수는 받지 않는다. */
export interface StudentProfile {
  childId: string
  nickname: string
  pinSet: boolean
  locked: boolean
}

export interface StudentDevice {
  deviceId: string
  label: string
  children: { childId: string; nickname: string }[]
  createdAt: string
  lastUsedAt: string | null
  expiresAt: string
}

export interface Pairing {
  pairingCode: string
  expiresAt: string
}

/**
 * PIN 형식 검사. 서버도 같은 규칙으로 거부(422)하지만, 아이에게 보여 주기 전에 학부모 화면에서 먼저 막는다.
 * 숫자 4~6자리, 같은 숫자만 반복(1111), 1씩 오르거나 내리는 연속(1234, 4321) 거부.
 */
export function pinProblem(pin: string): string | null {
  if (!/^\d+$/.test(pin)) return '숫자만 입력해 주세요.'
  if (pin.length < PIN_MIN || pin.length > PIN_MAX) return `숫자 ${PIN_MIN}~${PIN_MAX}자리로 정해 주세요.`
  if (/^(\d)\1+$/.test(pin)) return '같은 숫자만 반복한 PIN은 쓸 수 없습니다.'
  const digits = [...pin].map(Number)
  const step = (d: number) => digits.every((v, i) => i === 0 || v - digits[i - 1] === d)
  if (step(1) || step(-1)) return '1234·4321처럼 이어지는 숫자는 쓸 수 없습니다.'
  return null
}

/** 페어링 코드 입력값 정리: 공백·하이픈 제거, 대문자. 8자리 영숫자만 유효. */
export function normalizePairingCode(raw: string): string {
  return raw.replace(/[\s-]/g, '').toUpperCase()
}
export const validPairingCode = (code: string) => /^[A-Z0-9]{8}$/.test(code)

/** 화면 표시용: 4자리씩 끊어 읽기 쉽게. */
export const formatPairingCode = (code: string) => code.replace(/^(.{4})(.{4})$/, '$1 $2')

/** 남은 시간 (만료 카운트다운). 0 이하면 null. */
export function remaining(expiresAt: string, now: number): string | null {
  const ms = Date.parse(expiresAt) - now
  if (!(ms > 0)) return null
  const total = Math.ceil(ms / 1000),
    m = Math.floor(total / 60),
    s = total % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

/** 학생 기기 화면이 보여 줄 상태. 서버 오류 코드를 아이가 읽을 문장으로 바꾼다. */
export type DeviceLoginState =
  | { kind: 'invalid-device' }
  | { kind: 'wrong-pin'; remainingAttempts: number | null }
  | { kind: 'locked' }
  | { kind: 'pin-not-set' }
  | { kind: 'not-linked' }
  | { kind: 'other'; message: string }

export function loginState(code: string, remainingAttempts?: number, message = ''): DeviceLoginState {
  if (code === 'STUDENT_DEVICE_INVALID') return { kind: 'invalid-device' }
  if (code === 'STUDENT_PIN_INVALID')
    return { kind: 'wrong-pin', remainingAttempts: Number.isInteger(remainingAttempts) ? remainingAttempts! : null }
  if (code === 'STUDENT_PIN_LOCKED') return { kind: 'locked' }
  if (code === 'STUDENT_PIN_NOT_SET') return { kind: 'pin-not-set' }
  if (code === 'CHILD_NOT_LINKED') return { kind: 'not-linked' }
  return { kind: 'other', message: message || '지금은 들어갈 수 없어요. 잠시 후 다시 해 볼까요?' }
}

/** 기기 목록의 상태 문구. 만료는 서버 값이 기준이고, 화면은 시각만 비교한다. */
export const deviceExpired = (d: Pick<StudentDevice, 'expiresAt'>, now: number) =>
  Date.parse(d.expiresAt) <= now
