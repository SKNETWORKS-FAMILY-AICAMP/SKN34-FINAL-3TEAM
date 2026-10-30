import test from 'node:test'
import assert from 'node:assert/strict'
import { getResponse } from 'msw'
import { paymentHandlers } from '../src/mocks/handlers/payments.ts'
import { studentHandlers } from '../src/mocks/handlers/student.ts'
import { mockAccounts, mockAccountChildren, mockConsentHistory, setWorkspaceScenario } from '../src/mocks/fixtures/accounts.ts'
import { billingConfirmation, duplicateSubscription, refundLabels, nextBillingMonth } from '../src/domain/payment.ts'
import { paymentApi } from '../src/data/payment/api.ts'
import { setAccessToken } from '../src/data/apiClient.ts'
import type { ConsentHistory } from '../src/domain/parent.ts'
const handlers = [...paymentHandlers, ...studentHandlers]
let token = ''
async function call(path: string, body?: unknown, method = body ? 'POST' : 'GET', key = crypto.randomUUID()) {
  const request = new Request('http://localhost/api/v1' + path, { method, headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json', 'Idempotency-Key': key }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
  const r = await getResponse(handlers, request, { baseUrl: 'http://localhost' })
  assert.ok(r, path)
  return { status: r.status, data: await r.json() }
}
async function login() {
  const email = 'pay-' + crypto.randomUUID() + '@example.test', childId = crypto.randomUUID()
  mockAccounts.add(email); mockAccountChildren.set(email, [{ id: childId, nickname: '가상 자녀', grade: 3, birthYear: 2017, plan: 'FREE' }])
  const r = await call('/auth/login', { email, password: 'demo-only' }); assert.equal(r.status, 200); token = r.data.accessToken
  setWorkspaceScenario('normal')
  return { childId, email }
}
async function buy(childId: string) {
  const products = (await call('/products')).data.items
  const product = products.find((p: { price: number }) => p.price > 0)
  const r = await call('/orders', { childId, productId: product.id }); assert.equal(r.status, 201)
  return r.data
}
test('MSW 실서버 모양: 모의 승인 확인 중 → 조회 복구 → 구독·빌링·해지 철회·환불', async () => {
  const { childId } = await login(), order = await buy(childId)
  setWorkspaceScenario('payment-confirming')
  const key = crypto.randomUUID(), body = { orderId: order.orderId, amount: order.amount, paymentKey: 'mock-payment-' + order.orderId }
  const first = await call('/payments/confirm', body, 'POST', key)
  assert.equal(first.status, 202); assert.equal(first.data.status, 'CONFIRMING')
  assert.equal((await call('/payments/' + order.orderId)).data.status, 'CONFIRMING')
  setWorkspaceScenario('normal')
  const paid = (await call('/payments/' + order.orderId)).data
  assert.equal(paid.status, 'APPROVED'); assert.equal(paid.entitlementStatus, 'APPLIED')
  assert.deepEqual(Object.keys(paid).sort(), ['paymentId','orderId','childId','amount','status','entitlementStatus','approvedAt','failureCode','subscription','refundRequests'].sort())
  assert.equal(paid.subscription.autoRenew, false); assert.equal(paid.subscription.nextBillingDate, null)
  assert.equal((await call('/payments')).data.items.length, 1)
  assert.equal(duplicateSubscription((await call('/subscriptions')).data.items, childId), true)
  assert.equal((await call('/orders', { childId, productId: order.productId })).status, 409)
  const id = paid.subscription.subscriptionId, setup = (await call('/subscriptions/' + id + '/billing-key')).data
  const registered = await call('/subscriptions/' + id + '/billing-key', { customerKey: setup.customerKey, authKey: 'mock-billing-' + id })
  assert.equal(registered.data.billingRegistered, true); assert.equal(registered.data.autoRenew, true)
  assert.equal((await call('/subscriptions/' + id + '/auto-renewal', undefined, 'DELETE')).data.autoRenew, false)
  assert.equal((await call('/subscriptions/' + id + '/auto-renewal', undefined, 'PUT')).data.autoRenew, true)
  const refund = await call('/payments/' + paid.paymentId + '/refund-requests', { reason: '테스트 전액 환불' })
  assert.equal(refund.status, 201); assert.equal(refund.data.status, 'REQUESTED')
  assert.equal('cancelKey' in refund.data, false)
  assert.equal((await call('/payments/' + order.orderId)).data.status, 'REFUND_REVIEW')
  assert.equal((await call('/subscriptions/' + id + '/billing-key')).status, 409)
  assert.equal((await call('/subscriptions/' + id + '/auto-renewal', undefined, 'DELETE')).status, 200)
  await login()
  assert.equal((await call('/payments/' + order.orderId)).status, 404)
  assert.equal((await call('/payments/' + paid.paymentId + '/refund-requests', { reason: '다른 보호자 요청' })).status, 404)
})
test('모의 거래: 금액·빌링 고객·멱등 내용 위조 거부, 실패와 검토 중 구분', async () => {
  const { childId } = await login(), order = await buy(childId)
  assert.equal((await call('/payments/confirm', { orderId: order.orderId, amount: 1, paymentKey: 'mock-payment-' + order.orderId })).status, 422)
  const paid = (await call('/payments/confirm', { orderId: order.orderId, amount: order.amount, paymentKey: 'mock-payment-' + order.orderId })).data
  const id = paid.subscription.subscriptionId
  assert.equal((await call('/subscriptions/' + id + '/billing-key', { authKey: 'mock-billing-' + id, customerKey: 'another-customer' })).status, 422)
  setWorkspaceScenario('payment-refund-failed')
  const refund = (await call('/payments/' + paid.paymentId + '/refund-requests', { reason: '모의 PG 처리 실패' })).data
  assert.equal(refund.status, 'FAILED'); assert.notEqual(refundLabels.FAILED, refundLabels.REQUESTED)
  setWorkspaceScenario('payment-renewal-failed')
  const failed = (await call('/subscriptions')).data.items[0]
  assert.equal(failed.status, 'RENEWAL_FAILED'); assert.equal(failed.renewalRetryCount, 1); assert.ok(failed.graceUntil)
  setWorkspaceScenario('query-fail'); assert.equal((await call('/payments')).status, 503); setWorkspaceScenario('normal')
})
test('필수 동의 철회 뒤 거래 조회·갱신 해지는 유지하고 새 구매는 차단', async () => {
  const { childId, email } = await login(), order = await buy(childId)
  const paid = (await call('/payments/confirm', { orderId: order.orderId, amount: order.amount, paymentKey: 'mock-payment-' + order.orderId })).data
  mockConsentHistory.set(email, [{ document: { kind: 'TERMS' }, agreed: false, status: 'WITHDRAWN' } as ConsentHistory])
  assert.equal((await call('/payments')).status, 200)
  assert.equal((await call('/subscriptions/' + paid.subscription.subscriptionId + '/auto-renewal', undefined, 'DELETE')).status, 200)
  assert.equal((await call('/orders', { childId, productId: order.productId })).status, 403)
  mockConsentHistory.delete(email)
})
test('빌링 콜백 고객 범위·만료·중복 값을 검사', () => {
  const pending = { subscriptionId: crypto.randomUUID(), customerKey: 'synthetic-customer', idempotencyKey: crypto.randomUUID(), createdAt: Date.now() }
  assert.deepEqual(billingConfirmation('?customerKey=synthetic-customer&authKey=synthetic-auth', pending), { customerKey: pending.customerKey, authKey: 'synthetic-auth' })
  for (const q of ['?customerKey=other&authKey=x','?customerKey=synthetic-customer&authKey=x&authKey=y','?customerKey=synthetic-customer']) assert.throws(() => billingConfirmation(q, pending))
  assert.throws(() => billingConfirmation('?customerKey=synthetic-customer&authKey=x', { ...pending, createdAt: Date.now() - 600001 }))
})
test('구독·빌링·환불 API는 core 경로·본문·안정적인 UUID 멱등 키를 사용', async t => {
  const calls: { url: string; init: RequestInit }[] = []; setAccessToken('synthetic-token','PARENT')
  t.mock.method(globalThis,'fetch',async (url: string, init: RequestInit) => { calls.push({ url: String(url), init }); return Response.json({}) })
  const key = crypto.randomUUID()
  await paymentApi.billingSetup('subscription')
  await paymentApi.registerBilling('subscription',{ customerKey:'synthetic-customer',authKey:'synthetic-auth' },key)
  await paymentApi.autoRenew('subscription',false); await paymentApi.autoRenew('subscription',true)
  await paymentApi.refund('payment','환불 사유',key); await paymentApi.history(2)
  assert.equal(calls[1].url,'/api/v1/subscriptions/subscription/billing-key')
  assert.equal(new Headers(calls[1].init.headers).get('Idempotency-Key'),key)
  assert.equal(calls[2].init.method,'DELETE'); assert.equal(calls[3].init.method,'PUT')
  assert.deepEqual(JSON.parse(String(calls[4].init.body)),{reason:'환불 사유'})
  assert.equal(calls[5].url,'/api/v1/payments?page=2&size=20')
  setAccessToken(null)
})

test('월 이용 기간은 KST 기준 같은 날·말일로 계산하며 30일로 고정하지 않음', () => {
  assert.equal(nextBillingMonth('2026-10-30'), '2026-11-30')
  assert.equal(nextBillingMonth('2026-01-31'), '2026-02-28')
  assert.equal(nextBillingMonth('2028-01-31'), '2028-02-29')
})
