import { pinDemoChild, temporaryStudentPin } from '../src/mocks/fixtures/studentPinDemo.ts'
// Vite 개발 서버에서만 사용하는 공유 기기 목업. 실제 core-service/API를 대체하지 않는다.
import { randomBytes, randomInt, randomUUID, scryptSync, timingSafeEqual } from 'node:crypto'
import type { Child } from '../src/domain/classroom.ts'
import { normalizePairingCode, pinProblem } from '../src/domain/studentDevice.ts'

const PREFIX = '/__demo/device'
const COOKIE = 'sagomungchi_demo_device'
const PAIRING_TTL = 10 * 60_000
const DEVICE_TTL = 90 * 24 * 60 * 60_000
type Pin = { salt: string; hash: Buffer; failures: number }
type Owner = { children: Child[]; pins: Map<string, Pin> }
type Device = {
  deviceId: string; credential: string; owner: Owner; childIds: string[]; label: string
  createdAt: string; expiresAt: string; lastUsedAt: string | null; revoked: boolean
}
class DemoError extends Error {
  status: number
  code: string
  remainingAttempts?: number
  constructor(status: number, code: string, title: string, remainingAttempts?: number) {
    super(title)
    this.status = status
    this.code = code
    this.remainingAttempts = remainingAttempts
  }
}
function fail(status: number, code: string, title: string): never { throw new DemoError(status, code, title) }
const json = (body: unknown, status = 200, extra: Record<string, string> = {}) =>
  new Response(status === 204 ? null : JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', ...extra },
  })
const page = (items: unknown[]) => ({ items, page: 0, size: 20, totalElements: items.length })
function childrenFrom(value: unknown): Child[] {
  if (!Array.isArray(value) || value.length > 3) fail(422, 'VALIDATION_FAILED', '시연 자녀는 최대 3명입니다.')
  const seen = new Set<string>()
  return value.map((c: Child) => {
    if (!c || typeof c.id !== 'string' || !c.id || c.id.length > 100 || seen.has(c.id) ||
        typeof c.nickname !== 'string' || !c.nickname.trim() || c.nickname.length > 30 ||
        !Number.isInteger(c.grade) || c.grade < 3 || c.grade > 6)
      fail(422, 'VALIDATION_FAILED', '가상 자녀 정보를 확인해 주세요.')
    seen.add(c.id)
    return { id: c.id, nickname: c.nickname, grade: c.grade, birthYear: Number(c.birthYear) || 0,
      plan: c.plan === 'PREMIUM' ? 'PREMIUM' : 'FREE' }
  })
}

export function createDeviceDemo(now = Date.now) {
  const instanceId = randomUUID()
  const owners = new Map<string, Owner>()
  const devices = new Map<string, Device>()
  const pairings = new Map<string, { owner: Owner; childIds: string[]; expiresAt: number }>()
  const ownerFor = (request: Request) => {
    const token = request.headers.get('Authorization')?.replace(/^Bearer /, '') ?? ''
    return owners.get(token) ?? fail(401, 'DEMO_OWNER_INVALID', '시연 서버가 다시 시작되었습니다. 화면을 새로 열어 주세요.')
  }
  const deviceFor = (request: Request) => {
    const credential = request.headers.get('Cookie')?.split(';').map((p) => p.trim())
      .find((p) => p.startsWith(COOKIE + '='))?.slice(COOKIE.length + 1)
    const d = credential ? devices.get(credential) : undefined
    if (!d || d.revoked || Date.parse(d.expiresAt) <= now())
      return fail(401, 'STUDENT_DEVICE_INVALID', '이 기기는 학습용으로 등록되어 있지 않아요.')
    return d
  }
  const linked = (owner: Owner, id: string) => owner.children.find((c) => c.id === id)
    ?? fail(403, 'CHILD_NOT_LINKED', '보호자와 연결이 확인되지 않았어요.')
  const cookie = (request: Request, value: string, age = DEVICE_TTL / 1000) =>
    `${COOKIE}=${value}; Path=${PREFIX}; HttpOnly; SameSite=Strict; Max-Age=${age}${new URL(request.url).protocol === 'https:' ? '; Secure' : ''}`

  return {
    instanceId,
    async handle(request: Request): Promise<Response> {
      try {
        const url = new URL(request.url), path = url.pathname.slice(PREFIX.length)
        // 전용 헤더 + 동일 Origin. 외부 사이트에서 LAN 목업의 상태를 변경하지 못하게 한다.
        if (request.headers.get('X-Sagomungchi-Demo') !== '1' ||
            (request.headers.has('Origin') && request.headers.get('Origin') !== url.origin) ||
            (request.method !== 'GET' && request.headers.get('Origin') !== url.origin))
          fail(403, 'DEMO_ORIGIN_DENIED', '같은 시연 화면에서 다시 시도해 주세요.')
        if (path === '/instance' && request.method === 'GET') return json({ instanceId })
        const body = async () => await request.json() as Record<string, unknown>
        // 명시적인 개발 시연 버튼만 호출한다. QR 기기·보호자 소유권을 재사용하지 않는다.
        if (path === '/preview' && request.method === 'POST') {
          if (devices.size >= 1000) fail(429, 'DEMO_LIMIT', '시연 서버를 다시 시작해 주세요.')
          const child = { ...pinDemoChild }, salt = randomBytes(16).toString('hex')
          const owner: Owner = { children: [child], pins: new Map([[child.id, { salt, hash: scryptSync(temporaryStudentPin, salt, 32), failures: 0 }]]) }
          const d: Device = { deviceId: randomUUID(), credential: randomBytes(32).toString('hex'), owner,
            childIds: [child.id], label: '가상 학생 PIN 시연', createdAt: new Date(now()).toISOString(),
            expiresAt: new Date(now() + DEVICE_TTL).toISOString(), lastUsedAt: null, revoked: false }
          devices.set(d.credential, d)
          return json({ deviceId: d.deviceId }, 201, { 'Set-Cookie': cookie(request, d.credential) })
        }
        if (path === '/owners' && request.method === 'POST') {
          if (owners.size >= 100) fail(429, 'DEMO_LIMIT', '시연 서버를 다시 시작해 주세요.')
          const data = await body(), ownerToken = randomBytes(32).toString('hex')
          owners.set(ownerToken, { children: childrenFrom(data.children), pins: new Map() })
          return json({ ownerToken }, 201)
        }
        if (path === '/children' && request.method === 'PUT') {
          const owner = ownerFor(request)
          owner.children = childrenFrom((await body()).children)
          return json(page(owner.children.map((c) => ({ ...c, childId: c.id,
            pinSet: owner.pins.has(c.id), pinLocked: (owner.pins.get(c.id)?.failures ?? 0) >= 5 }))))
        }
        const pinId = /^\/pins\/([^/]+)$/.exec(path)?.[1]
        if (pinId && request.method === 'PUT') {
          const owner = ownerFor(request), child = linked(owner, decodeURIComponent(pinId))
          const pin = String((await body()).pin ?? ''), problem = pinProblem(pin)
          if (problem) fail(422, 'VALIDATION_FAILED', problem)
          const salt = randomBytes(16).toString('hex')
          owner.pins.set(child.id, { salt, hash: scryptSync(pin, salt, 32), failures: 0 })
          return json(null, 204)
        }
        if (path === '/pairings' && request.method === 'POST') {
          const owner = ownerFor(request), data = await body()
          if (!Array.isArray(data.childIds) || !data.childIds.length || data.childIds.length > 3 ||
              data.childIds.some((id) => typeof id !== 'string'))
            fail(422, 'VALIDATION_FAILED', '등록할 자녀를 한 명 이상 골라 주세요.')
          const childIds = [...new Set(data.childIds as string[])]
          childIds.forEach((id) => linked(owner, id))
          for (const [key, p] of pairings) if (p.expiresAt <= now()) pairings.delete(key)
          if (pairings.size >= 1000) fail(429, 'DEMO_LIMIT', '잠시 후 다시 시도해 주세요.')
          const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
          let pairingCode: string
          do { pairingCode = Array.from({ length: 8 }, () => alphabet[randomInt(alphabet.length)]).join('') }
          while (pairings.has(pairingCode))
          const expiresAt = now() + PAIRING_TTL
          pairings.set(pairingCode, { owner, childIds, expiresAt })
          return json({ pairingCode, expiresAt: new Date(expiresAt).toISOString() })
        }
        if (path === '/devices' && request.method === 'GET') {
          const owner = ownerFor(request)
          return json(page([...devices.values()].filter((d) => d.owner === owner && !d.revoked).map((d) => ({
            deviceId: d.deviceId, label: d.label, createdAt: d.createdAt, lastUsedAt: d.lastUsedAt,
            expiresAt: d.expiresAt, children: d.childIds.filter((id) => owner.children.some((c) => c.id === id))
              .map((id) => ({ childId: id, nickname: linked(owner, id).nickname })),
          }))))
        }
        const revokeId = /^\/devices\/([^/]+)$/.exec(path)?.[1]
        if (revokeId && request.method === 'DELETE') {
          const owner = ownerFor(request)
          const device = [...devices.values()].find((d) => d.deviceId === revokeId && d.owner === owner && !d.revoked)
          if (!device) fail(404, 'NOT_FOUND', '등록된 기기를 찾을 수 없습니다.')
          device.revoked = true
          return json(null, 204)
        }
        if (path === '/register' && request.method === 'POST') {
          const data = await body(), code = normalizePairingCode(String(data.pairingCode ?? ''))
          const pairing = pairings.get(code)
          // await 이전에 소비하므로 다른 브라우저의 동시 등록도 한 번만 성공한다.
          pairings.delete(code)
          if (!pairing || pairing.expiresAt <= now())
            fail(400, 'PAIRING_CODE_INVALID', '코드가 맞지 않거나 시간이 지났어요. 보호자에게 새 코드를 받아 주세요.')
          const children = pairing.childIds.map((id) => linked(pairing.owner, id))
          const d: Device = { deviceId: randomUUID(), credential: randomBytes(32).toString('hex'),
            owner: pairing.owner, childIds: pairing.childIds, label: String(data.label ?? '').trim().slice(0, 30) || '이름 없는 기기',
            createdAt: new Date(now()).toISOString(), expiresAt: new Date(now() + DEVICE_TTL).toISOString(),
            lastUsedAt: null, revoked: false }
          devices.set(d.credential, d)
          return json({ deviceId: d.deviceId, children: children.map((c) => ({ childId: c.id, nickname: c.nickname })) },
            201, { 'Set-Cookie': cookie(request, d.credential) })
        }
        if (path === '/profiles' && request.method === 'GET') {
          const d = deviceFor(request)
          return json(page(d.childIds.filter((id) => d.owner.children.some((c) => c.id === id)).map((id) => ({
            childId: id, nickname: linked(d.owner, id).nickname, pinSet: d.owner.pins.has(id),
            pinLocked: (d.owner.pins.get(id)?.failures ?? 0) >= 5,
          }))))
        }
        if (path === '/login' && request.method === 'POST') {
          const d = deviceFor(request), data = await body(), childId = String(data.childId ?? '')
          if (!d.childIds.includes(childId)) fail(401, 'STUDENT_DEVICE_INVALID', '이 기기에 등록된 자녀가 아니에요.')
          const child = linked(d.owner, childId), pin = d.owner.pins.get(childId)
          if (!pin) fail(409, 'STUDENT_PIN_NOT_SET', '아직 PIN이 없어요. 보호자와 함께 시작해 주세요.')
          if (pin.failures >= 5) fail(423, 'STUDENT_PIN_LOCKED', 'PIN이 잠겼어요. 보호자에게 다시 정해 달라고 해 주세요.')
          const input = String(data.pin ?? '')
          if (input.length > 6 || !timingSafeEqual(scryptSync(input, pin.salt, 32), pin.hash)) {
            pin.failures++
            if (pin.failures >= 5) fail(423, 'STUDENT_PIN_LOCKED', 'PIN이 잠겼어요. 보호자에게 다시 정해 달라고 해 주세요.')
            throw new DemoError(401, 'STUDENT_PIN_INVALID', 'PIN이 맞지 않아요.', 5 - pin.failures)
          }
          pin.failures = 0
          d.lastUsedAt = new Date(now()).toISOString()
          return json({ child, children: d.childIds.map((id) => linked(d.owner, id)) })
        }
        if (path === '/scenario' && request.method === 'POST') {
          const value = (await body()).value
          if (value === 'device-reset') return json(null, 204, { 'Set-Cookie': cookie(request, '', 0) })
          const d = deviceFor(request)
          if (value === 'device-revoked') d.revoked = true
          else if (value === 'device-expired') d.expiresAt = new Date(now() - 1).toISOString()
          else if (value === 'pin-not-set') d.childIds.forEach((id) => d.owner.pins.delete(id))
          else if (value === 'pin-locked') d.childIds.forEach((id) => {
            const pin = d.owner.pins.get(id)
            if (pin) pin.failures = 5
          })
          return json(null, 204)
        }
        return json({ code: 'DEMO_NOT_FOUND', title: '지원하지 않는 시연 요청입니다.' }, 404)
      } catch (error) {
        const e = error instanceof DemoError ? error : new DemoError(400, 'VALIDATION_FAILED', '요청 형식을 확인해 주세요.')
        return json({ status: e.status, code: e.code, title: e.message, remainingAttempts: e.remainingAttempts }, e.status,
          { 'Content-Type': 'application/problem+json' })
      }
    },
  }
}
