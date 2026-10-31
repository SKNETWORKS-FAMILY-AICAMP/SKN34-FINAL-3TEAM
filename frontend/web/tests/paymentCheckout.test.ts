import test from 'node:test'
import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { checkoutConfirmation, paymentComplete, paymentStateLabel } from '../src/domain/payment.ts'
import type { PendingCheckout, PaymentState } from '../src/domain/payment.ts'
import { createPaymentSandbox, testProduct } from '../scripts/payment-test-server.ts'
import { paymentApi } from '../src/data/payment/api.ts'
import { setAccessToken } from '../src/data/apiClient.ts'

const pending: PendingCheckout = { orderId: 'test-order-123456', amount: 14900, childId: 'child-a', productId: 'premium', orderName: '프리미엄', confirmKey: randomUUID(), createdAt: Date.now() }
test('실서버 어댑터는 core 주문·승인 계약과 동일 멱등 키를 사용하고 비밀 키를 전송하지 않음', async (t) => {
  const calls: { url: string; body: unknown; headers: Headers }[] = []
  setAccessToken('synthetic-parent-token', 'PARENT')
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    calls.push({ url: String(url), body: init.body ? JSON.parse(String(init.body)) : null, headers: new Headers(init.headers) })
    return Response.json({})
  })
  const orderKey = randomUUID(), confirmKey = randomUUID()
  await paymentApi.order('child-a', 'premium', orderKey)
  const body = { orderId: pending.orderId, amount: pending.amount, paymentKey: 'synthetic-payment-token' }
  await paymentApi.confirm(body, confirmKey)
  await paymentApi.confirm(body, confirmKey)
  await paymentApi.state(pending.orderId)
  assert.equal(calls[0].url, '/api/v1/orders')
  assert.deepEqual(calls[0].body, { childId: 'child-a', productId: 'premium' })
  assert.equal(calls[0].headers.get('Idempotency-Key'), orderKey)
  for (const call of calls.slice(1, 3)) { assert.equal(call.url, '/api/v1/payments/confirm'); assert.equal(call.headers.get('Idempotency-Key'), confirmKey); assert.deepEqual(call.body, body) }
  assert.equal(calls[3].url, '/api/v1/payments/' + pending.orderId)
  for (const call of calls) assert.equal(call.headers.get('Authorization'), 'Bearer synthetic-parent-token')
  setAccessToken(null)
})
test('리다이렉트의 주문·금액·키 검증: 변조·중복·만료를 거절', () => {
  assert.deepEqual(checkoutConfirmation('?orderId=test-order-123456&amount=14900&paymentKey=test-token', pending), { orderId: pending.orderId, amount: 14900, paymentKey: 'test-token' })
  for (const q of ['?orderId=other-order&amount=14900&paymentKey=x', '?orderId=test-order-123456&amount=1&paymentKey=x', '?orderId=test-order-123456&amount=14900&amount=1&paymentKey=x', '?orderId=test-order-123456&amount=14900']) assert.throws(() => checkoutConfirmation(q, pending))
  assert.throws(() => checkoutConfirmation('?orderId=test-order-123456&amount=14900&paymentKey=x', { ...pending, createdAt: Date.now() - 3_600_001 }))
})
test('서버 승인과 이용권 적용을 모두 확인한 경우만 완료', () => {
  const s: PaymentState = { paymentId: null, orderId: pending.orderId, amount: pending.amount, childId: pending.childId, status: 'CONFIRMING', entitlementStatus: null, approvedAt: null, failureCode: null }
  assert.equal(paymentComplete(s), false)
  assert.equal(paymentComplete({ ...s, status: 'APPROVED', entitlementStatus: 'RECOVERY_REQUIRED' }), false)
  assert.equal(paymentComplete({ ...s, status: 'APPROVED', entitlementStatus: 'SANDBOX_ONLY' }), false)
  assert.equal(paymentComplete({ ...s, status: 'APPROVED', entitlementStatus: 'APPLIED' }), true)
  assert.match(paymentStateLabel(s), /다시 결제하지/)
})
const request = (path: string, body?: unknown, key = randomUUID()) => new Request('http://127.0.0.1:5250/__payment-test' + path, {
  method: body ? 'POST' : 'GET', headers: { Origin: 'http://127.0.0.1:5250', 'X-Requested-With': 'XMLHttpRequest', 'Idempotency-Key': key, 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}),
})
test('샌드박스: 서버 금액 고정, 중복 주문·타인 조회·금액 변조·CSRF 차단', async () => {
  let calls = 0
  const handle = createPaymentSandbox('test_gsk_synthetic', (async () => { calls++; return Response.json({}) }) as typeof fetch)
  const key = randomUUID(), body = { childId: 'child-a', productId: testProduct.id, amount: 1 }
  const order = await (await handle(request('/orders', body, key), 'owner-a')).json()
  const again = await (await handle(request('/orders', body, key), 'owner-a')).json()
  assert.equal(order.amount, 14900); assert.equal(order.orderId, again.orderId)
  assert.equal((await handle(request('/payments/' + order.orderId), 'owner-b')).status, 404)
  assert.equal((await handle(request('/payments/confirm', { orderId: order.orderId, amount: 1, paymentKey: 'synthetic' }), 'owner-a')).status, 422)
  const csrf = request('/orders', body); csrf.headers.set('Origin', 'https://attacker.invalid')
  assert.equal((await handle(csrf, 'owner-a')).status, 403)
  assert.equal(calls, 0)
  assert.throws(() => createPaymentSandbox('live_gsk_synthetic'))
})
test('샌드박스: 승인 중복 억제, 실제 PG 응답 대조, 앱 이용권 미적용', async () => {
  let calls = 0
  const handle = createPaymentSandbox('test_gsk_synthetic', (async (_url, init) => {
    calls++; const b = JSON.parse(String(init?.body)); await new Promise(r => setTimeout(r, 10))
    return Response.json({ orderId: b.orderId, totalAmount: b.amount, currency: 'KRW', paymentKey: b.paymentKey, status: 'DONE' })
  }) as typeof fetch)
  const order = await (await handle(request('/orders', { childId: 'child-a', productId: testProduct.id }), 'a')).json()
  const body = { orderId: order.orderId, amount: order.amount, paymentKey: 'synthetic-token' }
  const results = await Promise.all([handle(request('/payments/confirm', body), 'a'), handle(request('/payments/confirm', body), 'a')])
  for (const r of results) { const s = await r.json(); assert.equal(s.status, 'APPROVED'); assert.equal(s.entitlementStatus, 'SANDBOX_ONLY') }
  assert.equal(calls, 1)
  await handle(request('/payments/confirm', body), 'a'); assert.equal(calls, 1)
  assert.equal((await handle(request('/payments/confirm', { ...body, paymentKey: 'another' }), 'a')).status, 409)
})
test('타임아웃 후 새 결제 없이 조회로 복구, 다른 주문의 PG 응답을 승인으로 취급하지 않음', async () => {
  let orderId = '', first = true
  const handle = createPaymentSandbox('test_gsk_synthetic', (async () => {
    if (first) { first = false; throw new Error('timeout') }
    return Response.json({ orderId, totalAmount: 14900, paymentKey: 'token', status: 'DONE', currency: 'KRW' })
  }) as typeof fetch)
  const order = await (await handle(request('/orders', { childId: 'child-a', productId: testProduct.id }), 'a')).json()
  const r = await handle(request('/payments/confirm', { orderId: order.orderId, amount: order.amount, paymentKey: 'token' }), 'a')
  assert.equal(r.status, 202)
  assert.equal((await (await handle(request('/payments/' + order.orderId), 'a')).json()).status, 'CONFIRMING')
  orderId = order.orderId
  assert.equal((await (await handle(request('/payments/' + order.orderId), 'a')).json()).status, 'APPROVED')
})
