import type { Child } from '../../domain/classroom.ts'

/**
 * 개발 전용 학생 기기 상태 (#59).
 * 실제 서버는 기기 자격증명을 httpOnly 쿠키로 주지만 MSW는 그 쿠키를 만들 수 없으므로,
 * "이 브라우저에 등록된 기기"를 sessionStorage의 currentDeviceId로 대신한다. 운영 번들에는 포함되지 않는다.
 * PIN은 원문 대신 SHA-256 해시로만 보관한다(NFR-SEC-08 모사).
 */
export interface MockPin {
  hash: string
  failed: number
  locked: boolean
}
export interface MockDevice {
  deviceId: string
  label: string
  owner: string
  childIds: string[]
  createdAt: string
  lastUsedAt: string | null
  expiresAt: string
  revokedAt: string | null
}
export interface MockPairing {
  owner: string
  children: Child[]
  expiresAt: number
}
interface DeviceState {
  pins: Record<string, MockPin>
  devices: MockDevice[]
  currentDeviceId: string | null
  pairings: Record<string, MockPairing>
}

export const MAX_PIN_FAILURES = 5
export const PAIRING_TTL_MS = 10 * 60 * 1000
export const DEVICE_TTL_MS = 90 * 24 * 60 * 60 * 1000

const storageKey = 'sagomungchi:msw-device:v1'
export const deviceState: DeviceState = load()

function load(): DeviceState {
  const blank: DeviceState = { pins: {}, devices: [], currentDeviceId: null, pairings: {} }
  if (typeof sessionStorage === 'undefined') return blank
  try {
    const raw = sessionStorage.getItem(storageKey)
    if (!raw) return blank
    const data = JSON.parse(raw) as Partial<DeviceState>
    if (!data.pins || !Array.isArray(data.devices)) return blank
    return { ...blank, ...data }
  } catch {
    return blank
  }
}
export function persistDeviceState() {
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.setItem(storageKey, JSON.stringify(deviceState))
  } catch {
    /* 저장소 차단 시 새로고침 복원만 제한됩니다. */
  }
}

export async function hashPin(childId: string, pin: string) {
  const bytes = new TextEncoder().encode(`${childId}:${pin}`)
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789' // 헷갈리는 0·O·1·I 제외
export function newPairingCode() {
  const values = crypto.getRandomValues(new Uint32Array(8))
  return [...values].map((v) => alphabet[v % alphabet.length]).join('')
}

/** 이 브라우저(자녀 기기)의 유효한 기기. 미등록·해제·만료면 null. */
export function currentDevice(now = Date.now()) {
  const d = deviceState.devices.find((d) => d.deviceId === deviceState.currentDeviceId)
  if (!d || d.revokedAt || Date.parse(d.expiresAt) <= now) return null
  return d
}

/** 상태 선택기 시나리오. 이 브라우저에 등록된 기기를 기준으로 상태를 바꾼다. */
export type DeviceScenario =
  | 'normal'
  | 'device-revoked'
  | 'device-expired'
  | 'pin-locked'
  | 'pin-not-set'
  | 'device-reset'
export function setDeviceScenario(value: DeviceScenario) {
  const d = deviceState.devices.find((d) => d.deviceId === deviceState.currentDeviceId)
  const now = Date.now()
  if (value === 'device-reset') deviceState.currentDeviceId = null
  else if (d && value === 'device-revoked') d.revokedAt = new Date(now).toISOString()
  else if (d && value === 'device-expired') d.expiresAt = new Date(now - 60_000).toISOString()
  else if (d && value === 'pin-locked')
    for (const id of d.childIds)
      if (deviceState.pins[id]) deviceState.pins[id] = { ...deviceState.pins[id], failed: MAX_PIN_FAILURES, locked: true }
  if (d && value === 'pin-not-set') for (const id of d.childIds) delete deviceState.pins[id]
  persistDeviceState()
}
