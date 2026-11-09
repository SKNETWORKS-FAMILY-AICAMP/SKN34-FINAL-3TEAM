import test from 'node:test'
import assert from 'node:assert/strict'
import { setTimeout as pause } from 'node:timers/promises'
import { Window } from 'happy-dom'
import type { QueryClient as Client } from '@tanstack/react-query'
import type { StudentLook } from '../src/domain/studentLook.ts'
import type { Attempt, Child } from '../src/domain/classroom.ts'

// 실제 React root·effect·TanStack Query를 실행한다. 훅 함수를 모조 함수로 대체하지 않는다.
const dom = new Window({ url: 'http://localhost/' })
for (const key of ['window', 'document', 'navigator', 'HTMLElement', 'Node', 'Event', 'CustomEvent', 'sessionStorage'])
  Object.defineProperty(globalThis, key, { value: key === 'window' ? dom : dom[key as keyof Window], configurable: true })
Object.defineProperty(globalThis, 'IS_REACT_ACT_ENVIRONMENT', { value: true, configurable: true })
const { createElement, act } = await import('react')
const { createRoot } = await import('react-dom/client')
const { QueryClient, QueryClientProvider } = await import('@tanstack/react-query')
const { useParentQuery, useParentMutation, useParentDashboard } = await import('../src/data/parent/queries.ts')
const { useAdminQuery, useAdminMutation } = await import('../src/data/admin/queries.ts')
const device = await import('../src/data/studentDevice/queries.ts')
const { useStudentLook, useSaveLook } = await import('../src/data/studentLook/queries.ts')
const classroom = await import('../src/data/classroom/useClassroom.ts')
const { useSupportResults } = await import('../src/data/support/queries.ts')
const payment = await import('../src/data/payment/queries.ts')
const { useNotificationStream, reconnectDelay } = await import('../src/data/notifications.ts')
const { queryClient } = await import('../src/data/queryClient.ts')
const { setAccessToken } = await import('../src/data/apiClient.ts')

test.after(async () => { queryClient.clear(); await dom.happyDOM.close() })
test.afterEach(() => setAccessToken(null))

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false, gcTime: Infinity } } })
}
async function mount<T>(t: test.TestContext, hook: () => T, cache: Client = client()) {
  let result: T
  const container = dom.document.createElement('div')
  dom.document.body.append(container)
  const root = createRoot(container as unknown as HTMLElement)
  function Probe() { result = hook(); return null }
  const render = () => root.render(createElement(QueryClientProvider, { client: cache }, createElement(Probe)))
  await act(async () => render())
  t.after(async () => { await act(async () => root.unmount()); cache.clear(); container.remove() })
  return { get: () => result!, cache, render: () => act(async () => render()) }
}
async function until(check: () => boolean, timeoutMs = 1000) {
  for (let i = 0; i < timeoutMs / 10; i++) {
    await act(async () => { await pause(10) })
    if (check()) return
  }
  assert.fail('React query did not reach the expected state')
}
function mockFetch(t: test.TestContext, handle: (url: string, init: RequestInit) => Response | Promise<Response>) {
  setAccessToken('synthetic-parent', 'PARENT')
  t.mock.method(globalThis, 'fetch', (url: string | URL | Request, init: RequestInit = {}) => handle(String(url), init))
}
const child: Child = { id: 'child-a', nickname: '가상 학생', grade: 3, birthYear: 2017 }
const period = { from: '2026-10-19', to: '2026-10-25' }

test('Node import는 Vite env 없이 성공하고 개발·QR 경로를 켜지 않는다', () => {
  assert.equal(classroom.isDemo, false)
  assert.equal(device.qrDemoEnabled, false)
})

test('parent·admin 쿼리는 같은 키에서도 분리되고 disabled 쿼리는 호출하지 않는다', async t => {
  let disabledCalls = 0
  const h = await mount(t, () => ({
    parent: useParentQuery(['same'], async () => 'parent'),
    admin: useAdminQuery(['same'], async () => 'admin'),
    disabled: useParentQuery(['off'], async () => { disabledCalls++; return 'bad' }, false),
  }))
  await until(() => h.get().parent.isSuccess && h.get().admin.isSuccess)
  assert.equal(h.get().parent.data, 'parent')
  assert.equal(h.get().admin.data, 'admin')
  assert.equal(disabledCalls, 0)
  assert.equal(h.cache.getQueryData(['parent', 'same']), 'parent')
  assert.equal(h.cache.getQueryData(['admin', 'same']), 'admin')
})

test('조회 실패는 재시도하거나 빈 성공 데이터로 바꾸지 않는다', async t => {
  let calls = 0
  const h = await mount(t, () => useAdminQuery(['failure'], async () => { calls++; throw new Error('unavailable') }))
  await until(() => h.get().isError)
  assert.match(String(h.get().error), /unavailable/)
  assert.equal(h.get().data, undefined)
  assert.equal(calls, 1)
})

test('학부모 처리 중 쿼리는 재조회하고 완료 응답 뒤 자동 재조회를 멈춘다', async t => {
  let calls = 0
  const h = await mount(t, () => useParentQuery(['polling'], async () => {
    calls++; return { status: calls === 1 ? 'RUNNING' : 'COMPLETED' }
  }, true, true))
  await until(() => h.get().data?.status === 'COMPLETED', 2500)
  await act(async () => { await pause(1350) })
  assert.equal(calls, 2)
})

test('세션 복원은 동시 요청을 합치고 명시적 fresh 요청에서만 다시 조회한다', async t => {
  let calls = 0
  mockFetch(t, url => {
    assert.equal(url, '/api/v1/me'); calls++
    return Response.json({ role: 'PARENT', startPath: '/parent/journal' })
  })
  const first = classroom.restoreSession(true)
  assert.equal(classroom.restoreSession(), first)
  const result = await first
  assert.equal(result.role, 'PARENT')
  assert.equal(calls, 1)
  await classroom.restoreSession(true)
  assert.equal(calls, 2)
})

test('학부모 mutation 성공은 parent·children만 무효화하고 실패는 성공 무효화를 하지 않는다', async t => {
  const cache = client()
  for (const key of [['parent', 'records'], ['children'], ['admin', 'jobs']]) cache.setQueryData(key, [])
  const h = await mount(t, () => useParentMutation(async (fail: boolean) => {
    if (fail) throw new Error('save failed')
    return 'saved'
  }), cache)
  await act(async () => { await assert.rejects(h.get().mutateAsync(true), /save failed/) })
  assert.equal(cache.getQueryState(['parent', 'records'])?.isInvalidated, false)
  await act(async () => { assert.equal(await h.get().mutateAsync(false), 'saved') })
  assert.equal(cache.getQueryState(['parent', 'records'])?.isInvalidated, true)
  assert.equal(cache.getQueryState(['children'])?.isInvalidated, true)
  assert.equal(cache.getQueryState(['admin', 'jobs'])?.isInvalidated, false)
})

test('관리자 mutation은 관리자 캐시만 무효화한다', async t => {
  const cache = client()
  cache.setQueryData(['admin', 'missions'], []); cache.setQueryData(['parent', 'records'], [])
  const h = await mount(t, () => useAdminMutation(async (value: string) => value), cache)
  await act(async () => { await h.get().mutateAsync('saved') })
  assert.equal(cache.getQueryState(['admin', 'missions'])?.isInvalidated, true)
  assert.equal(cache.getQueryState(['parent', 'records'])?.isInvalidated, false)
})

test('대시보드는 같은 자녀·기간으로 세 쿼리를 보내며 자녀 변경 시 결과를 섞지 않는다', async t => {
  const calls: string[] = []
  mockFetch(t, (url, init) => {
    calls.push(url); assert.ok(init.signal instanceof AbortSignal)
    const id = /\/children\/([^/]+)/.exec(url)![1]
    return Response.json({ childId: id, items: [], period, state: 'NO_RECORD', page: 0, size: 20, totalElements: 0 })
  })
  let scope = { childId: child.id, ...period }
  const h = await mount(t, () => useParentDashboard(scope))
  await until(() => h.get().summary.isSuccess && h.get().thinking.isSuccess && h.get().records.isSuccess)
  scope = { ...scope, childId: 'child-b' }; await h.render()
  await until(() => h.get().summary.data?.childId === 'child-b')
  assert.equal(calls.length, 6)
  assert.ok(calls.every(url => url.includes('from=2026-10-19') && url.includes('to=2026-10-25')))
  assert.equal(h.get().records.data?.childId, 'child-b')
})

test('기기 등록 성공 안내는 프로필 무효화 전에 실행하고 등록값을 그대로 전송한다', async t => {
  const cache = client(); cache.setQueryData(['student-device', 'profiles'], [])
  const order: string[] = []
  cache.getQueryCache().subscribe(() => {
    if (cache.getQueryState(['student-device', 'profiles'])?.isInvalidated) order.push('invalidate')
  })
  mockFetch(t, (url, init) => {
    assert.equal(url, '/api/v1/auth/student/devices')
    assert.deepEqual(JSON.parse(String(init.body)), { pairingCode: 'ABCD2345', label: '태블릿' })
    return Response.json({ deviceId: 'device-a', children: [] })
  })
  const h = await mount(t, () => device.useDeviceRegistration(() => order.push('registered')), cache)
  await act(async () => { await h.get().mutateAsync({ code: 'ABCD2345', label: '태블릿' }) })
  assert.equal(order[0], 'registered')
  assert.ok(order.includes('invalidate'))
})

test('PIN 실패는 프로필 잠금 상태를 다시 읽되 보호자 데이터를 지우지 않는다', async t => {
  const cache = client(); cache.setQueryData(['student-device', 'profiles'], [])
  cache.setQueryData(['parent', 'records'], ['preserved'])
  mockFetch(t, () => Response.json({ code: 'PIN_INVALID', status: 403, title: 'PIN 오류' }, { status: 403 }))
  const h = await mount(t, device.usePinLogin, cache)
  await act(async () => { await assert.rejects(h.get().mutateAsync({ childId: child.id, pin: '1111' })) })
  assert.equal(cache.getQueryState(['student-device', 'profiles'])?.isInvalidated, true)
  assert.deepEqual(cache.getQueryData(['parent', 'records']), ['preserved'])
})

test('기기 관리의 페어링·PIN·해제 요청과 성공 후 캐시 갱신', async t => {
  const cache = client(); cache.setQueryData(['parent', 'student-devices'], []); cache.setQueryData(['children'], [])
  const calls: { url: string; method?: string; body: unknown; proof: string | null }[] = []
  mockFetch(t, (url, init) => {
    calls.push({ url, method: init.method, body: init.body ? JSON.parse(String(init.body)) : null,
      proof: new Headers(init.headers).get('X-Reauth-Token') })
    return init.method === 'DELETE' || init.method === 'PUT' ? new Response(null, { status: 204 }) : Response.json({ pairingCode: 'ABCD2345' })
  })
  const h = await mount(t, device.useDeviceAdmin, cache)
  await act(async () => { await h.get().pairing.mutateAsync([child.id]) })
  assert.equal(cache.getQueryState(['children'])?.isInvalidated, false)
  await act(async () => { await h.get().setPin.mutateAsync({ childId: child.id, pin: '4831', reauthToken: 'synthetic-proof' }) })
  await act(async () => { await h.get().revoke.mutateAsync('device-a') })
  assert.deepEqual(calls.map(c => c.method), ['POST', 'PUT', 'DELETE'])
  assert.deepEqual(calls[0].body, { childIds: [child.id] })
  assert.equal(calls[1].proof, 'synthetic-proof')
  assert.equal(cache.getQueryState(['children'])?.isInvalidated, true)
})

test('기기·프로필 쿼리는 실제 API를 사용하고 Node에서 QR 시연 주소는 조회하지 않는다', async t => {
  const calls: string[] = []
  mockFetch(t, url => { calls.push(url); return Response.json({ items: [] }) })
  const h = await mount(t, () => ({ profiles: device.useDeviceProfiles(), devices: device.useStudentDevices(), origins: device.usePairingOrigins() }))
  await until(() => h.get().profiles.isSuccess && h.get().devices.isSuccess)
  assert.deepEqual(calls.sort(), ['/api/v1/auth/student/profiles', '/api/v1/student-devices'])
  assert.equal(h.get().origins.fetchStatus, 'idle')
})

test('시연 기기 준비 실패는 프로필을 성공 처리하지 않는다', async t => {
  const cache = client(); cache.setQueryData(['student-device', 'profiles'], [])
  mockFetch(t, () => Response.json({ status: 503, code: 'DEMO_UNAVAILABLE' }, { status: 503 }))
  const h = await mount(t, device.useDemoStudentEntry, cache)
  await act(async () => { await assert.rejects(h.get().mutateAsync(undefined)) })
  assert.equal(cache.getQueryState(['student-device', 'profiles'])?.isInvalidated, false)
})

test('꾸미기 조회는 자녀가 없으면 중단하고 API의 설정을 자녀별로 캐시한다', async t => {
  let calls = 0; let id: string | undefined
  const saved: StudentLook = { theme: 'forest', companion: 'tori', updatedAt: null }
  mockFetch(t, url => { calls++; assert.equal(url, '/api/v1/students/me/preferences'); return Response.json(saved) })
  const h = await mount(t, () => useStudentLook(id))
  assert.equal(calls, 0)
  id = child.id; await h.render(); await until(() => h.get().isSuccess)
  assert.deepEqual(h.get().data, saved)
  assert.deepEqual(h.cache.getQueryData(['student-look', child.id]), saved)
})

test('꾸미기 저장 실패는 낙관적 변경을 취소하고 다른 자녀 캐시는 유지한다', async t => {
  const cache = client()
  const before: StudentLook = { theme: 'lake', companion: 'mungchi', updatedAt: null }
  cache.setQueryData(['student-look', child.id], before); cache.setQueryData(['student-look', 'child-b'], before)
  let release!: (value: Response) => void
  mockFetch(t, () => new Promise<Response>(resolve => { release = resolve }))
  const h = await mount(t, () => useSaveLook(child.id), cache)
  let pending!: Promise<StudentLook>
  await act(async () => { pending = h.get().mutateAsync({ theme: 'forest', companion: 'tori' }); void pending.catch(() => {}); await pause(0) })
  assert.equal(cache.getQueryData<StudentLook>(['student-look', child.id])?.theme, 'forest')
  assert.deepEqual(cache.getQueryData(['student-look', 'child-b']), before)
  await act(async () => { release(Response.json({ status: 503, code: 'SAVE_FAILED' }, { status: 503 })); await assert.rejects(pending) })
  assert.deepEqual(cache.getQueryData(['student-look', child.id]), before)
})

test('최초 꾸미기 저장 실패는 가짜 설정을 지우고 성공 응답의 설정·저장 시각을 유지한다', async t => {
  let fail = true
  const saved: StudentLook = { theme: 'sea', companion: 'kongi', updatedAt: '2026-11-01T12:00:00Z' }
  mockFetch(t, (_url, init) => {
    assert.equal(init.method, 'PUT')
    return fail ? Response.json({ status: 503 }, { status: 503 }) : Response.json(saved)
  })
  const h = await mount(t, () => useSaveLook(child.id))
  await act(async () => { await assert.rejects(h.get().mutateAsync({ theme: 'sea', companion: 'kongi' })) })
  assert.equal(h.cache.getQueryData(['student-look', child.id]), undefined)
  fail = false
  await act(async () => { await h.get().mutateAsync({ theme: 'sea', companion: 'kongi' }) })
  assert.deepEqual(h.cache.getQueryData(['student-look', child.id]), saved)
})

test('학생 훅은 자녀 없는 조회를 막고 학년 변경을 별도 미션 키로 조회한다', async t => {
  const calls: string[] = []
  mockFetch(t, url => { calls.push(url); return Response.json({ items: [] }) })
  let selected: Child | undefined
  const h = await mount(t, () => ({ children: classroom.useChildren(false), missions: classroom.useMissions(selected) }))
  assert.equal(calls.length, 0)
  selected = child; await h.render(); await until(() => h.get().missions.isSuccess)
  selected = { ...child, grade: 4 }; await h.render(); await until(() => h.get().missions.isSuccess)
  assert.deepEqual(calls, ['/api/v1/missions', '/api/v1/missions'])
})

test('시도 시작은 상세 캐시를 갱신하고 학습 홈·기록·미션을 새로 읽게 한다', async t => {
  const attempt: Attempt = { attemptId: 'attempt-a', studentId: child.id, status: 'IN_PROGRESS', answers: [], helped: false,
    mission: { id: 'mission-a', title: '가상 미션', subject: '국어', grade: 3, inputType: 'NARRATIVE', thinkingType: 'ANALYZE', question: '어떻게 생각하나요?', hint: '장면을 보세요.', scene: 'korean' } }
  const cache = client()
  for (const key of [['student-home', child.id], ['missions', child.id, 3], ['records', 'STUDENT', child.id]]) cache.setQueryData(key, [])
  mockFetch(t, (url, init) => {
    assert.equal(url, '/api/v1/missions/mission-a/attempts'); assert.equal(init.method, 'POST')
    return Response.json(attempt)
  })
  const h = await mount(t, classroom.useLearningActions, cache)
  await act(async () => { await h.get().start.mutateAsync({ child, mission: attempt.mission }) })
  assert.deepEqual(cache.getQueryData(['attempt', attempt.attemptId]), { ...attempt, reflection: undefined })
  assert.equal(cache.getQueryState(['student-home', child.id])?.isInvalidated, true)
  assert.equal(cache.getQueryState(['missions', child.id, 3])?.isInvalidated, true)
})

test('신고·문의 결과는 목록 두 개를 받고 선택한 건만 상세 조회한다', async t => {
  const calls: string[] = []
  mockFetch(t, url => {
    calls.push(url)
    return url.endsWith('/error-reports/report-a')
      ? Response.json({ reportId: 'report-a', status: 'RESOLVED', comment: '확인 요청', reviewReason: '판정을 다시 확인했습니다.' })
      : Response.json({ items: [] })
  })
  let reportId: string | null = null
  const h = await mount(t, () => useSupportResults('session-a', reportId, null))
  await until(() => h.get().reports.isSuccess && h.get().inquiries.isSuccess)
  assert.equal(h.get().detail.fetchStatus, 'idle')
  reportId = 'report-a'; await h.render(); await until(() => h.get().detail.isSuccess)
  assert.deepEqual(calls.sort(), ['/api/v1/error-reports', '/api/v1/error-reports/report-a', '/api/v1/inquiries'])
  assert.equal((h.get().detail.data as { reviewReason: string }).reviewReason, '판정을 다시 확인했습니다.')
})

test('결제 결과 재조회는 승인 대기·이용권 복구만 3초 간격 최대 10회, 오류 뒤에는 멈춘다', () => {
  const state = (status: string, entitlementStatus: string | null = null) =>
    ({ paymentId: null, orderId: 'order-a', childId: child.id, amount: 9900, status, entitlementStatus, approvedAt: null, failureCode: null })
  assert.equal(payment.paymentPollDelay(state('PENDING'), 1, false), 3000)
  assert.equal(payment.paymentPollDelay(state('CONFIRMING'), 10, false), 3000)
  assert.equal(payment.paymentPollDelay(state('APPROVED', 'RECOVERY_REQUIRED'), 1, false), 3000)
  assert.equal(payment.paymentPollDelay(state('PENDING'), 11, false), false)
  assert.equal(payment.paymentPollDelay(state('PENDING'), 1, true), false)
  assert.equal(payment.paymentPollDelay(state('APPROVED', 'APPLIED'), 1, false), false)
  assert.equal(payment.paymentPollDelay(state('FAILED'), 1, false), false)
  assert.equal(payment.paymentPollDelay(undefined, 0, false), false)
})

test('결제 승인은 같은 주문의 중복 요청을 합치고 승인 응답으로 결과를 채워 바로 다시 조회하지 않는다', async t => {
  const calls: string[] = []
  const approved = { paymentId: 'pay-a', orderId: 'order-dedupe', childId: child.id, amount: 9900, status: 'APPROVED',
    entitlementStatus: 'APPLIED', approvedAt: '2026-11-02T00:00:00Z', failureCode: null }
  mockFetch(t, (url, init) => {
    calls.push(`${init.method ?? 'GET'} ${url}`)
    assert.equal(new Headers(init.headers).get('Idempotency-Key'), 'confirm-key')
    return Response.json(approved)
  })
  let enabled = false
  const h = await mount(t, () => ({ confirm: payment.usePaymentConfirmation(), result: payment.usePaymentResult('order-dedupe', enabled) }))
  const body = { orderId: 'order-dedupe', amount: 9900, paymentKey: 'synthetic-key' }
  await act(async () => {
    const [a, b] = await Promise.all([h.get().confirm.mutateAsync({ body, key: 'confirm-key' }), h.get().confirm.mutateAsync({ body, key: 'confirm-key' })])
    assert.equal(a, b)
  })
  enabled = true; await h.render(); await act(async () => { await pause(30) })
  assert.deepEqual(calls, ['POST /api/v1/payments/confirm'])
  assert.deepEqual(h.get().result.data, approved)
})

test('알림 스트림은 역할이 있을 때만 연결하고 새 알림을 받으면 알림 캐시만 다시 읽게 한다', async t => {
  const calls: string[] = []
  const cache = client()
  cache.setQueryData(['parent', 'notifications', true, 0], { items: [] }); cache.setQueryData(['parent', 'records'], [])
  mockFetch(t, (url, init) => {
    calls.push(`${init.method} ${url}`)
    assert.equal(new Headers(init.headers).get('Accept'), 'text/event-stream')
    return new Response(': ping\n\nevent: notification\ndata: {"id":"n-1","type":"REPORT_COMPLETED"}\n\n', { headers: { 'Content-Type': 'text/event-stream' } })
  })
  let role: 'PARENT' | null = null
  const h = await mount(t, () => useNotificationStream(role), cache)
  await act(async () => { await pause(30) })
  assert.equal(calls.length, 0)
  role = 'PARENT'; await h.render()
  await until(() => cache.getQueryState(['parent', 'notifications', true, 0])?.isInvalidated === true)
  assert.equal(cache.getQueryState(['parent', 'records'])?.isInvalidated, false)
  assert.deepEqual(calls, ['GET /api/v1/notifications/stream'])
})

test('알림 스트림 권한 오류는 다시 연결하지 않고, 실패가 이어지면 재연결 간격을 30초까지 늘린다', async t => {
  assert.deepEqual([0, 1, 2, 5, 10].map(reconnectDelay), [1000, 2000, 4000, 30000, 30000])
  let calls = 0
  mockFetch(t, () => { calls++; return Response.json({ status: 403, code: 'FORBIDDEN', title: '권한 없음' }, { status: 403 }) })
  await mount(t, () => useNotificationStream('ADMIN'))
  await act(async () => { await pause(1200) })
  assert.equal(calls, 1)
})

test('공통 QueryClient는 같은 쿼리의 동시 HTTP를 합치고 명시적 clear 후 결과를 제거한다', async () => {
  let calls = 0
  const options = { queryKey: ['test-deduplicate'], queryFn: async () => { calls++; await pause(5); return 'server result' } }
  assert.deepEqual(await Promise.all([queryClient.fetchQuery(options), queryClient.fetchQuery(options)]), ['server result', 'server result'])
  assert.equal(calls, 1)
  queryClient.clear()
  assert.equal(queryClient.getQueryData(options.queryKey), undefined)
})


test('#389 해금 확정 응답은 선택 자녀의 모든 페이지 잔액·해금에만 반영한다', async t => {
  const { useUnlock } = await import('../src/data/retention/queries.ts')
  const cache = client()
  const points = { balance: 150, items: [], page: 0, size: 20, totalElements: 21 }
  const item = { itemKey: 'THEME:forest', name: '숲', slot: 'THEME', pricePoints: 100, unlocked: false, onSale: true, assetKey: null }
  cache.setQueryData(['points', child.id, 0], points)
  cache.setQueryData(['points', child.id, 1], { ...points, page: 1 })
  cache.setQueryData(['points', 'other-child', 0], points)
  cache.setQueryData(['look-items', child.id], [item])
  mockFetch(t, (_url, init) => {
    assert.equal(init.method, 'POST')
    assert.equal(init.body, undefined)
    assert.equal(new Headers(init.headers).get('Idempotency-Key'), '00000000-0000-4000-8000-000000000001')
    return Response.json({ itemKey: item.itemKey, unlocked: true, balance: 50 })
  })
  const h = await mount(t, () => useUnlock(child.id), cache)
  await act(async () => { await h.get().mutateAsync({ itemKey: item.itemKey, key: '00000000-0000-4000-8000-000000000001' }) })
  for (const page of [0, 1]) assert.equal(cache.getQueryData<typeof points>(['points', child.id, page])?.balance, 50)
  assert.equal(cache.getQueryData<typeof points>(['points', 'other-child', 0])?.balance, 150)
  assert.deepEqual(cache.getQueryData(['look-items', child.id]), [{ ...item, unlocked: true }])
})

test('#389 다른 항목의 해금 응답은 성공·잔액 변경으로 표시하지 않는다', async t => {
  const { useUnlock } = await import('../src/data/retention/queries.ts')
  const cache = client(), points = { balance: 150, items: [], page: 0, size: 20, totalElements: 0 }
  cache.setQueryData(['points', child.id, 0], points)
  mockFetch(t, () => Response.json({ itemKey: 'THEME:space', unlocked: true, balance: 50 }))
  const h = await mount(t, () => useUnlock(child.id), cache)
  await act(async () => { await assert.rejects(h.get().mutateAsync({ itemKey: 'THEME:forest', key: crypto.randomUUID() }), /확인하지 못/) })
  assert.deepEqual(cache.getQueryData(['points', child.id, 0]), points)
})

test('#433 친구 공개 설정은 창으로 돌아오면 다시 읽어 보호자 동의를 바로 반영한다', async t => {
  const { useCommunitySettings } = await import('../src/data/retention/queries.ts')
  const { focusManager } = await import('@tanstack/react-query')
  let consentGranted = false, calls = 0
  mockFetch(t, (url) => {
    assert.match(url, /\/students\/me\/community-settings$/)
    calls++
    return Response.json({ enabled: false, consentGranted, updatedAt: null })
  })
  t.after(() => focusManager.setFocused(undefined))
  // 앱 기본값이 바뀌어도(오래 신선·포커스 재조회 끔) 이 조회는 포커스마다 다시 읽어야 한다.
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 60_000, refetchOnWindowFocus: false } } })
  const h = await mount(t, () => useCommunitySettings(child.id), cache)
  await until(() => h.get().isSuccess)
  assert.equal(h.get().data?.consentGranted, false)
  consentGranted = true // 보호자가 다른 창에서 동의했다.
  await act(async () => { focusManager.setFocused(false) })
  await act(async () => { focusManager.setFocused(true) })
  await until(() => h.get().data?.consentGranted === true)
  assert.equal(calls, 2)
})
