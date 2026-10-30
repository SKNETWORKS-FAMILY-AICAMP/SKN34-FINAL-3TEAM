import { http } from 'msw/http'
import { guard, respond } from './student.ts'
import { parentGuard, parentChild, fail } from './parent.ts'
import { fixtureStore } from '../fixtures/student.ts'
import { mockIdentity, workspaceScenario } from '../fixtures/accounts.ts'
import { setMockChildPlan } from '../fixtures/childPlan.ts'
import type { PaymentProduct, PaymentRecord, PaymentRefund, PaymentSubscription, PaymentOrder } from '../../domain/payment.ts'

const premium: PaymentProduct = { id: '74000000-0000-4000-8000-000000000001', code: 'PREMIUM', name: '프리미엄', price: 14900, billingCycle: 'MONTHLY', childLimit: 1, active: true, features: { feedback: true, conversations: true, fullReport: true }, limits: { dailyFeedback: 50, dailyConversations: 30, reportNarrative: true } }
const free: PaymentProduct = { ...premium, id: '74000000-0000-4000-8000-000000000000', code: 'FREE', name: '무료', price: 0, billingCycle: 'NONE', features: { feedback: true, conversations: false, fullReport: false }, limits: { dailyMissions: 3, dailyConversations: 0, reportNarrative: false } }
type Account = { subscriptions: PaymentSubscription[]; payments: PaymentRecord[]; orders: Map<string, PaymentOrder>; keys: Map<string, { body: string; result: unknown }> }
const accounts = new Map<string, Account>()
const day = (offset: number) => new Date(Date.now() + offset * 86400000).toISOString().slice(0, 10)
function parentRead(request: Request) { guard(request); if (fixtureStore.snapshot().session?.role !== 'PARENT') fail('FORBIDDEN', '학부모 본인의 결제만 확인할 수 있습니다.', 403) }
function account(request: Request): Account {
  parentRead(request)
  if (workspaceScenario === 'query-fail') fail('PAYMENT_STORAGE_UNAVAILABLE', '거래 정보를 불러오지 못했습니다.', 503)
  let a = accounts.get(mockIdentity.email)
  if (!a) {
    a = { subscriptions: [], payments: [], orders: new Map(), keys: new Map() }
    for (const c of fixtureStore.snapshot().children ?? []) if (c.plan === 'PREMIUM') {
      const s: PaymentSubscription = { subscriptionId: crypto.randomUUID(), childId: c.id, product: structuredClone(premium), status: 'ACTIVE', periodStart: day(-2), periodEnd: day(28), nextBillingDate: day(28), autoRenew: true, graceUntil: null, renewalRetryCount: 0, billingRegistered: true }
      a.subscriptions.push(s)
      a.payments.push({ paymentId: crypto.randomUUID(), orderId: 'mock-' + crypto.randomUUID(), childId: c.id, amount: premium.price, status: 'APPROVED', entitlementStatus: 'APPLIED', approvedAt: new Date(Date.now() - 2 * 86400000).toISOString(), failureCode: null, subscription: s, refundRequests: [] })
    }
    accounts.set(mockIdentity.email, a)
  }
  return a
}
async function keyed<T>(request: Request, action: (body: Record<string, unknown>) => Promise<T>): Promise<T> {
  const a = account(request), key = request.headers.get('Idempotency-Key') ?? ''
  if (!/^[0-9a-f-]{36}$/i.test(key)) fail('IDEMPOTENCY_KEY_REQUIRED', '같은 요청 식별자가 필요합니다.')
  const raw = await request.text(), cacheKey = request.method + ':' + new URL(request.url).pathname + ':' + key, cached = a.keys.get(cacheKey)
  if (cached) { if (cached.body !== raw) fail('IDEMPOTENCY_CONFLICT', '같은 요청의 내용이 달라졌습니다.', 409); return structuredClone(cached.result) as T }
  const result = await action(JSON.parse(raw)); a.keys.set(cacheKey, { body: raw, result: structuredClone(result) }); return result
}
function approve(a: Account, p: PaymentRecord) {
  if (p.status === 'APPROVED') return p
  const s: PaymentSubscription = { subscriptionId: crypto.randomUUID(), childId: p.childId, product: structuredClone(premium), status: 'ACTIVE', periodStart: day(0), periodEnd: day(30), nextBillingDate: null, autoRenew: false, graceUntil: null, renewalRetryCount: 0, billingRegistered: false }
  a.subscriptions.push(s); p.status = 'APPROVED'; p.entitlementStatus = 'APPLIED'; p.approvedAt = new Date().toISOString(); p.subscription = s
  setMockChildPlan({ childId: p.childId, plan: 'PREMIUM' }); return p
}
export const paymentHandlers = [
  http.get('/api/v1/products', () => respond(async () => ({ items: [free, premium] }))),
  http.get('/api/v1/subscriptions', ({ request }) => respond(async () => ({ items: account(request).subscriptions.map(s => workspaceScenario === 'payment-renewal-failed' && s.status === 'ACTIVE' ? { ...s, status: 'RENEWAL_FAILED', renewalRetryCount: 1, graceUntil: new Date(Date.now() + 2 * 86400000).toISOString(), nextBillingDate: s.autoRenew ? day(1) : null } : s) }))),
  http.get('/api/v1/payments', ({ request }) => respond(async () => {
    const a = account(request), q = new URL(request.url).searchParams, page = Number(q.get('page') ?? 0), size = Number(q.get('size') ?? 20)
    if (!Number.isInteger(page) || page < 0 || !Number.isInteger(size) || size < 1 || size > 100) fail('INVALID_PAGE', '페이지를 확인해 주세요.')
    return { items: a.payments.slice(page * size, (page + 1) * size) }
  })),
  http.post('/api/v1/orders', ({ request }) => respond(async () => {
    parentGuard(request)
    return keyed(request, async b => {
      const a = account(request); await parentChild(request, String(b.childId))
      if (b.productId !== premium.id) fail('PRODUCT_NOT_PURCHASABLE', '구매 가능한 상품을 선택해 주세요.', 409)
      if (a.subscriptions.some(s => s.childId === b.childId && ['ACTIVE', 'RENEWAL_FAILED'].includes(s.status)) || a.payments.some(p => p.childId === b.childId && p.status === 'CONFIRMING')) fail('SUBSCRIPTION_DUPLICATE', '이 자녀는 이미 이용 중이거나 결제 확인 중입니다.', 409)
      const order = { orderId: 'mock-' + crypto.randomUUID(), amount: premium.price, orderName: premium.name, childId: String(b.childId), productId: premium.id }; a.orders.set(order.orderId, order); return order
    })
  }, 201)),
  http.post('/api/v1/payments/confirm', ({ request }) => respond(async () => {
    parentGuard(request)
    return keyed(request, async b => {
      const a = account(request), order = a.orders.get(String(b.orderId)); if (!order) fail('NOT_FOUND', '본인의 주문을 찾지 못했습니다.', 404)
      await parentChild(request, order.childId)
      if (b.amount !== order.amount) fail('PAYMENT_AMOUNT_MISMATCH', '서버 주문 금액과 다릅니다.', 422)
      if (b.paymentKey !== 'mock-payment-' + order.orderId) fail('PAYMENT_KEY_MISMATCH', '모의 결제 키가 올바르지 않습니다.', 409)
      const old = a.payments.find(p => p.orderId === order.orderId); if (old) return old
      const p: PaymentRecord = { paymentId: crypto.randomUUID(), orderId: order.orderId, childId: order.childId, amount: order.amount, status: 'CONFIRMING', entitlementStatus: null, approvedAt: null, failureCode: null, subscription: null, refundRequests: [] }; a.payments.unshift(p)
      return workspaceScenario === 'payment-confirming' ? p : approve(a, p)
    })
  }, workspaceScenario === 'payment-confirming' ? 202 : 200)),
  http.get('/api/v1/payments/:orderId', ({ request, params }) => respond(async () => {
    const a = account(request), p = a.payments.find(p => p.orderId === params.orderId)
    if (p) return p.status === 'CONFIRMING' && workspaceScenario !== 'payment-confirming' ? approve(a, p) : p
    const o = a.orders.get(String(params.orderId)); if (!o) fail('NOT_FOUND', '본인의 주문을 찾지 못했습니다.', 404)
    return { paymentId: null, orderId: o.orderId, childId: o.childId, amount: o.amount, status: 'PENDING', entitlementStatus: null, approvedAt: null, failureCode: null, subscription: null, refundRequests: [] }
  })),
  http.get('/api/v1/subscriptions/:id/billing-key', ({ request, params }) => respond(async () => {
    parentGuard(request); const s = account(request).subscriptions.find(s => s.subscriptionId === params.id)
    if (!s) fail('NOT_FOUND', '본인의 구독을 찾지 못했습니다.', 404)
    await parentChild(request, s.childId)
    if (!['ACTIVE', 'RENEWAL_FAILED'].includes(s.status)) fail('SUBSCRIPTION_NOT_ACTIVE', '이용 중인 구독에서 등록해 주세요.', 409)
    return { subscriptionId: s.subscriptionId, customerKey: 'mock-customer-' + s.subscriptionId }
  })),
  http.post('/api/v1/subscriptions/:id/billing-key', ({ request, params }) => respond(async () => {
    parentGuard(request)
    return keyed(request, async b => {
      const s = account(request).subscriptions.find(s => s.subscriptionId === params.id); if (!s) fail('NOT_FOUND', '본인의 구독이 아닙니다.', 404)
      await parentChild(request, s.childId)
      if (b.customerKey !== 'mock-customer-' + s.subscriptionId || b.authKey !== 'mock-billing-' + s.subscriptionId) fail('BILLING_AUTH_MISMATCH', '인증 정보를 확인해 주세요.', 422)
      if (!['ACTIVE', 'RENEWAL_FAILED'].includes(s.status)) fail('SUBSCRIPTION_NOT_ACTIVE', '현재 등록할 수 없는 구독입니다.', 409)
      s.billingRegistered = true; s.autoRenew = true; s.nextBillingDate = s.status === 'RENEWAL_FAILED' ? day(1) : s.periodEnd; return s
    })
  })),
  ...(['PUT', 'DELETE'] as const).map(method => http[method === 'PUT' ? 'put' : 'delete']('/api/v1/subscriptions/:id/auto-renewal', ({ request, params }) => respond(async () => {
    if (method === 'PUT') parentGuard(request)
    const s = account(request).subscriptions.find(s => s.subscriptionId === params.id); if (!s) fail('NOT_FOUND', '본인의 구독이 아닙니다.', 404)
    if (method === 'PUT') { await parentChild(request, s.childId); if (s.status !== 'ACTIVE' || !s.billingRegistered || day(0) >= s.periodEnd) fail('SUBSCRIPTION_NOT_ACTIVE', '현재 자동 갱신을 재개할 수 없습니다.', 409) }
    s.autoRenew = method === 'PUT'; s.nextBillingDate = s.autoRenew ? s.periodEnd : null; return s
  }))),
  http.post('/api/v1/payments/:id/refund-requests', ({ request, params }) => respond(async () => keyed(request, async b => {
    const p = account(request).payments.find(p => p.paymentId === params.id); if (!p) fail('NOT_FOUND', '본인의 결제가 아닙니다.', 404)
    const existing = p.refundRequests.find(r => ['REQUESTED', 'APPROVED'].includes(r.status)); if (existing) return existing
    if (typeof b.reason !== 'string' || !b.reason.trim() || b.reason.length > 200) fail('VALIDATION_FAILED', '환불 사유를 200자 이내로 입력해 주세요.', 422)
    if (p.status !== 'APPROVED' || !p.approvedAt || Date.now() - Date.parse(p.approvedAt) > 7 * 86400000) fail('REFUND_NOT_ALLOWED', '환불 조건을 확인해 주세요.', 409)
    const r: PaymentRefund = { id: crypto.randomUUID(), paymentId: p.paymentId!, requestedBy: mockIdentity.userId, amount: p.amount, reason: b.reason, status: workspaceScenario === 'payment-refund-failed' ? 'FAILED' : 'REQUESTED', decidedBy: null, rejectReason: null, pgStatus: null, decidedAt: null, createdAt: new Date().toISOString(), usageVerifiedAt: null }; p.refundRequests.push(r); if (r.status === 'REQUESTED') p.status = 'REFUND_REVIEW'; return r
  }), 201)),
]
