import test from 'node:test'
import assert from 'node:assert/strict'
import { createDeviceDemo } from '../scripts/device-demo.ts'

const child = { id: 'demo-child', nickname: '하린', grade: 3, birthYear: 2017, plan: 'FREE' }
function setup() {
  let time = Date.now()
  const demo = createDeviceDemo(() => time)
  const actor = () => {
    let cookie = '', token = ''
    return {
      setToken(value: string) { token = value },
      async call(path: string, method = 'GET', body?: unknown, extra?: Record<string, string>) {
        const headers = { 'X-Sagomungchi-Demo': '1', Origin: 'http://demo.test', Cookie: cookie,
          Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', ...extra }
        const response = await demo.handle(new Request('http://demo.test/__demo/device' + path, {
          method, headers, ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        }))
        const setCookie = response.headers.get('Set-Cookie')
        if (setCookie) cookie = setCookie.split(';')[0]
        return { status: response.status, data: response.status === 204 ? null : await response.json(), setCookie }
      },
    }
  }
  const parent = actor(), tablet = actor()
  const ready = async () => {
    const r = await parent.call('/owners', 'POST', { children: [child] })
    parent.setToken(r.data.ownerToken)
    await parent.call('/pins/demo-child', 'PUT', { pin: '4831' })
    return (await parent.call('/pairings', 'POST', { childIds: [child.id] })).data.pairingCode as string
  }
  return { parent, tablet, actor, ready, advance(ms: number) { time += ms } }
}

test('독립 기기 등록 → HttpOnly 기기 쿠키 → PIN 로그인 → 보호자 기기 목록', async () => {
  const { ready, parent, tablet } = setup()
  const code = await ready()
  assert.equal((await tablet.call('/profiles')).status, 401)
  const registered = await tablet.call('/register', 'POST', { pairingCode: code, label: '하린의 태블릿' })
  assert.equal(registered.status, 201)
  assert.match(registered.setCookie!, /HttpOnly; SameSite=Strict/)
  assert.ok(!JSON.stringify(registered.data).includes('credential'))
  assert.deepEqual((await tablet.call('/profiles')).data.items,
    [{ childId: child.id, nickname: '하린', pinSet: true, pinLocked: false }])
  assert.equal((await tablet.call('/login', 'POST', { childId: child.id, pin: '4831' })).status, 200)
  const list = (await parent.call('/devices')).data.items
  assert.equal(list[0].label, '하린의 태블릿')
  assert.ok(list[0].lastUsedAt)
  assert.ok(!JSON.stringify(list).includes('credential'))
})

test('동시에 같은 QR로 등록하면 한 기기만 성공하고 재사용을 거부', async () => {
  const { ready, tablet, actor } = setup()
  const code = await ready(), other = actor()
  const results = await Promise.all([tablet, other].map((a) => a.call('/register', 'POST', { pairingCode: code })))
  assert.deepEqual(results.map((r) => r.status).sort(), [201, 400])
  assert.equal((await actor().call('/register', 'POST', { pairingCode: code })).data.code, 'PAIRING_CODE_INVALID')
})

test('QR 10분 만료와 기기 90일 만료', async () => {
  const { ready, parent, tablet, advance } = setup()
  const old = await ready()
  advance(10 * 60_000)
  assert.equal((await tablet.call('/register', 'POST', { pairingCode: old })).data.code, 'PAIRING_CODE_INVALID')
  const code = (await parent.call('/pairings', 'POST', { childIds: [child.id] })).data.pairingCode
  await tablet.call('/register', 'POST', { pairingCode: code })
  advance(90 * 24 * 60 * 60_000)
  assert.equal((await tablet.call('/profiles')).data.code, 'STUDENT_DEVICE_INVALID')
})

test('PIN 5회 실패는 기기 간 공유되고 보호자의 재설정으로 풀림', async () => {
  const { ready, parent, tablet } = setup()
  await tablet.call('/register', 'POST', { pairingCode: await ready() })
  for (let i = 1; i < 5; i++) {
    const r = await tablet.call('/login', 'POST', { childId: child.id, pin: '9999' })
    assert.equal(r.status, 401)
    assert.equal(r.data.remainingAttempts, 5 - i)
  }
  assert.equal((await tablet.call('/login', 'POST', { childId: child.id, pin: '9999' })).status, 423)
  assert.equal((await tablet.call('/login', 'POST', { childId: child.id, pin: '4831' })).status, 423)
  const statuses = await parent.call('/children', 'PUT', { children: [child] })
  assert.equal(statuses.data.items[0].pinLocked, true)
  assert.equal((await tablet.call('/profiles')).data.items[0].pinLocked, true)
  await parent.call('/pins/demo-child', 'PUT', { pin: '90210' })
  assert.equal((await tablet.call('/login', 'POST', { childId: child.id, pin: '90210' })).status, 200)
})

test('다른 보호자의 기기 접근과 deviceId로 쿠키 위조를 거부, 보호자 해제 즉시 반영', async () => {
  const { ready, parent, tablet, actor } = setup()
  const r = await tablet.call('/register', 'POST', { pairingCode: await ready() })
  const other = actor(), owner = await other.call('/owners', 'POST', { children: [child] })
  other.setToken(owner.data.ownerToken)
  assert.deepEqual((await other.call('/devices')).data.items, [])
  assert.equal((await other.call('/devices/' + r.data.deviceId, 'DELETE')).status, 404)
  assert.equal((await other.call('/profiles', 'GET', undefined,
    { Cookie: `sagomungchi_demo_device=${r.data.deviceId}` })).status, 401)
  assert.equal((await parent.call('/devices/' + r.data.deviceId, 'DELETE')).status, 204)
  assert.equal((await tablet.call('/login', 'POST', { childId: child.id, pin: '4831' })).data.code, 'STUDENT_DEVICE_INVALID')
})

test('Origin·전용 헤더 검사 및 PIN 규칙과 자녀 범위 검사', async () => {
  const { parent, tablet, ready } = setup()
  await ready()
  assert.equal((await parent.call('/owners', 'POST', { children: [child] }, { Origin: 'http://evil.test' })).status, 403)
  assert.equal((await parent.call('/owners', 'POST', { children: [child] }, { 'X-Sagomungchi-Demo': '' })).status, 403)
  assert.equal((await parent.call('/pins/demo-child', 'PUT', { pin: '1234' })).status, 422)
  assert.equal((await parent.call('/pairings', 'POST', { childIds: ['other-child'] })).status, 403)
  assert.equal((await tablet.call('/devices')).status, 401)
})

test('자녀 연결 해제는 기존 기기 프로필과 PIN 로그인에도 반영', async () => {
  const { ready, parent, tablet } = setup()
  await tablet.call('/register', 'POST', { pairingCode: await ready() })
  await parent.call('/children', 'PUT', { children: [] })
  assert.deepEqual((await tablet.call('/profiles')).data.items, [])
  assert.equal((await tablet.call('/login', 'POST', { childId: child.id, pin: '4831' })).data.code, 'CHILD_NOT_LINKED')
})
