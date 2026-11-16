import { http } from 'msw/http'
import { guard, respond as respondBase } from './student.ts'
import { parentGuard, parentChild, fail } from './parent.ts'
import { fixtureStore } from '../fixtures/student.ts'
import { mockIdentity, mockAccountChildren, workspaceScenario } from '../fixtures/accounts.ts'
import { addMockSubscription, existingPaymentAccount, freeProduct as free, mockDay as day, mockEntitlement, paymentAccount, persistPaymentFixture as persist, premiumProduct as premium } from '../fixtures/payments.ts'
import type { PaymentAccount as Account } from '../fixtures/payments.ts'
import type { PaymentRecord, PaymentRefund } from '../../domain/payment.ts'

async function respond(action: () => Promise<unknown>, status = 200) {
  return respondBase(async () => { try { return await action() } finally { persist() } }, status)
}
function parentRead(request: Request) { guard(request); if (fixtureStore.snapshot().session?.role !== 'PARENT') return fail('FORBIDDEN', '학부모 본인의 결제만 확인할 수 있습니다.', 403) }
function account(request: Request): Account {
  parentRead(request)
  if (workspaceScenario === 'query-fail') return fail('PAYMENT_STORAGE_UNAVAILABLE', '거래 정보를 불러오지 못했습니다.', 503)
  return paymentAccount()
}
// 이관 목업도 기존 결제 fixture를 읽는다. 결제 명의·구독 상태를 이전하거나 바꾸지 않는다.
export function requireMockTransferPaymentReady(sender: string, childId: string) {
  if (workspaceScenario === 'query-fail') fail('PAYMENT_STORAGE_UNAVAILABLE', '거래 정보를 불러오지 못했습니다.', 503)
  const data = existingPaymentAccount(sender) ?? (sender === mockIdentity.email || mockAccountChildren.has(sender) ? paymentAccount(sender) : undefined)
  const subscriptions = data?.subscriptions ?? []
  const payments = data?.payments ?? []
  const unresolved = (p: PaymentRecord) => p.refundRequests.some(r => ['REQUESTED', 'APPROVED', 'FAILED'].includes(r.status))
  if (subscriptions.some(s => s.status === 'RENEWAL_FAILED' || (s.status === 'ACTIVE' && (s.autoRenew || s.periodEnd > day(0))) || (s.status === 'CANCELED' && s.periodEnd > day(0))) || payments.some(unresolved))
    fail('WITHDRAWAL_BLOCKED', '발신자의 구독·환불을 먼저 정리해 주세요.', 409)
  if (subscriptions.some(s => s.childId === childId && ['ACTIVE', 'RENEWAL_FAILED'].includes(s.status)) ||
    payments.some(p => p.childId === childId && (p.status === 'CONFIRMING' || unresolved(p))))
    fail('TRANSFER_PAYMENT_BLOCKED', '자녀의 결제·구독 처리가 끝난 뒤 이관해 주세요.', 409)
}
async function keyed<T>(request: Request, action: (body: Record<string, unknown>) => Promise<T>): Promise<T> {
  const a = account(request), key = request.headers.get('Idempotency-Key') ?? ''
  if (!/^[0-9a-f-]{36}$/i.test(key)) return fail('IDEMPOTENCY_KEY_REQUIRED', '같은 요청 식별자가 필요합니다.')
  const raw = await request.text(), cacheKey = request.method + ':' + new URL(request.url).pathname + ':' + key, cached = a.keys.get(cacheKey)
  if (cached) { if (cached.body !== raw) return fail('IDEMPOTENCY_CONFLICT', '같은 요청의 내용이 달라졌습니다.', 409); return structuredClone(cached.result) as T }
  const result = await action(JSON.parse(raw)); a.keys.set(cacheKey, { body: raw, result: structuredClone(result) }); return result
}
function approve(a: Account, p: PaymentRecord) {
  if (p.status === 'APPROVED') return p
  const s = addMockSubscription(a, p.childId)
  p.status = 'APPROVED'; p.entitlementStatus = 'APPLIED'; p.approvedAt = new Date().toISOString(); p.subscription = s; return p
}
export const paymentHandlers = [
  http.get('/api/v1/children/:childId/entitlement', ({ request, params }) => respond(async () => {
    const childId = String(params.childId)
    await parentChild(request, childId)
    account(request)
    return mockEntitlement(childId)
  })),
  http.get('/api/v1/products', () => respond(async () => ({ items: [free, premium] }))),
  http.get('/api/v1/subscriptions', ({ request }) => respond(async () => ({ items: account(request).subscriptions.map(s => workspaceScenario === 'payment-renewal-failed' && s.status === 'ACTIVE' ? { ...s, status: 'RENEWAL_FAILED', renewalRetryCount: 1, graceUntil: new Date(Date.now() + 2 * 86400000).toISOString(), nextBillingDate: s.autoRenew ? day(1) : null } : s) }))),
  http.get('/api/v1/payments', ({ request }) => respond(async () => {
    const a = account(request), q = new URL(request.url).searchParams, page = Number(q.get('page') ?? 0), size = Number(q.get('size') ?? 20)
    if (!Number.isInteger(page) || page < 0 || !Number.isInteger(size) || size < 1 || size > 100) return fail('INVALID_PAGE', '페이지를 확인해 주세요.')
    return { items: a.payments.slice(page * size, (page + 1) * size) }
  })),
  http.post('/api/v1/orders', ({ request }) => respond(async () => {
    parentGuard(request)
    return keyed(request, async b => {
      const a = account(request); await parentChild(request, String(b.childId))
      if (b.productId !== premium.id) return fail('PRODUCT_NOT_PURCHASABLE', '구매 가능한 상품을 선택해 주세요.', 409)
      if (a.subscriptions.some(s => s.childId === b.childId && ['ACTIVE', 'RENEWAL_FAILED'].includes(s.status)) || a.payments.some(p => p.childId === b.childId && p.status === 'CONFIRMING')) return fail('SUBSCRIPTION_DUPLICATE', '이 자녀는 이미 이용 중이거나 결제 확인 중입니다.', 409)
      const order = { orderId: 'mock-' + crypto.randomUUID(), amount: premium.price, orderName: premium.name, childId: String(b.childId), productId: premium.id }; a.orders.set(order.orderId, order); return order
    })
  }, 201)),
  http.post('/api/v1/payments/confirm', ({ request }) => respond(async () => {
    parentGuard(request)
    return keyed(request, async b => {
      const a = account(request), order = a.orders.get(String(b.orderId)); if (!order) return fail('NOT_FOUND', '본인의 주문을 찾지 못했습니다.', 404)
      await parentChild(request, order.childId)
      if (b.amount !== order.amount) return fail('PAYMENT_AMOUNT_MISMATCH', '서버 주문 금액과 다릅니다.', 422)
      if (b.paymentKey !== 'mock-payment-' + order.orderId) return fail('PAYMENT_KEY_MISMATCH', '모의 결제 키가 올바르지 않습니다.', 409)
      const old = a.payments.find(p => p.orderId === order.orderId); if (old) return old
      const p: PaymentRecord = { paymentId: crypto.randomUUID(), orderId: order.orderId, childId: order.childId, amount: order.amount, status: 'CONFIRMING', entitlementStatus: null, approvedAt: null, failureCode: null, subscription: null, refundRequests: [] }; a.payments.unshift(p)
      return workspaceScenario === 'payment-confirming' ? p : approve(a, p)
    })
  }, workspaceScenario === 'payment-confirming' ? 202 : 200)),
  http.get('/api/v1/payments/:orderId', ({ request, params }) => respond(async () => {
    const a = account(request), p = a.payments.find(p => p.orderId === params.orderId)
    if (p) return p.status === 'CONFIRMING' && workspaceScenario !== 'payment-confirming' ? approve(a, p) : p
    const o = a.orders.get(String(params.orderId)); if (!o) return fail('NOT_FOUND', '본인의 주문을 찾지 못했습니다.', 404)
    return { paymentId: null, orderId: o.orderId, childId: o.childId, amount: o.amount, status: 'PENDING', entitlementStatus: null, approvedAt: null, failureCode: null, subscription: null, refundRequests: [] }
  })),
  http.get('/api/v1/subscriptions/:id/billing-key', ({ request, params }) => respond(async () => {
    parentGuard(request); const s = account(request).subscriptions.find(s => s.subscriptionId === params.id)
    if (!s) return fail('NOT_FOUND', '본인의 구독을 찾지 못했습니다.', 404)
    await parentChild(request, s.childId)
    if (account(request).payments.some(p => p.childId === s.childId && p.refundRequests.some(r => ['REQUESTED','APPROVED'].includes(r.status)))) return fail('SUBSCRIPTION_NOT_ACTIVE', '환불 검토 중에는 결제수단을 변경할 수 없습니다.', 409)
    if (!['ACTIVE', 'RENEWAL_FAILED'].includes(s.status)) return fail('SUBSCRIPTION_NOT_ACTIVE', '이용 중인 구독에서 등록해 주세요.', 409)
    return { subscriptionId: s.subscriptionId, customerKey: 'mock-customer-' + s.subscriptionId }
  })),
  http.post('/api/v1/subscriptions/:id/billing-key', ({ request, params }) => respond(async () => {
    parentGuard(request)
    return keyed(request, async b => {
      const s = account(request).subscriptions.find(s => s.subscriptionId === params.id); if (!s) return fail('NOT_FOUND', '본인의 구독이 아닙니다.', 404)
      await parentChild(request, s.childId)
    if (account(request).payments.some(p => p.childId === s.childId && p.refundRequests.some(r => ['REQUESTED','APPROVED'].includes(r.status)))) return fail('SUBSCRIPTION_NOT_ACTIVE', '환불 검토 중에는 결제수단을 변경할 수 없습니다.', 409)
      if (b.customerKey !== 'mock-customer-' + s.subscriptionId || b.authKey !== 'mock-billing-' + s.subscriptionId) return fail('BILLING_AUTH_MISMATCH', '인증 정보를 확인해 주세요.', 422)
      if (!['ACTIVE', 'RENEWAL_FAILED'].includes(s.status)) return fail('SUBSCRIPTION_NOT_ACTIVE', '현재 등록할 수 없는 구독입니다.', 409)
      s.billingRegistered = true; s.autoRenew = true; s.nextBillingDate = s.status === 'RENEWAL_FAILED' ? day(1) : s.periodEnd; return s
    })
  })),
  ...(['PUT', 'DELETE'] as const).map(method => http[method === 'PUT' ? 'put' : 'delete']('/api/v1/subscriptions/:id/auto-renewal', ({ request, params }) => respond(async () => {
    if (method === 'PUT') parentGuard(request)
    const s = account(request).subscriptions.find(s => s.subscriptionId === params.id); if (!s) return fail('NOT_FOUND', '본인의 구독이 아닙니다.', 404)
    if (method === 'PUT' && account(request).payments.some(p => p.childId === s.childId && p.refundRequests.some(r => ['REQUESTED','APPROVED'].includes(r.status)))) return fail('SUBSCRIPTION_NOT_ACTIVE', '환불 검토 중에는 갱신을 재개할 수 없습니다.', 409)
    if (method === 'PUT') { await parentChild(request, s.childId); if (s.status !== 'ACTIVE' || !s.billingRegistered || day(0) >= s.periodEnd) return fail('SUBSCRIPTION_NOT_ACTIVE', '현재 자동 갱신을 재개할 수 없습니다.', 409) }
    s.autoRenew = method === 'PUT'; s.nextBillingDate = s.autoRenew ? s.periodEnd : null; return s
  }))),
  http.post('/api/v1/payments/:id/refund-requests', ({ request, params }) => respond(async () => keyed(request, async b => {
    const p = account(request).payments.find(p => p.paymentId === params.id); if (!p) return fail('NOT_FOUND', '본인의 결제가 아닙니다.', 404)
    const existing = p.refundRequests.find(r => ['REQUESTED', 'APPROVED'].includes(r.status)); if (existing) return existing
    if (typeof b.reason !== 'string' || !b.reason.trim() || b.reason.length > 200) return fail('VALIDATION_FAILED', '환불 사유를 200자 이내로 입력해 주세요.', 422)
    if (p.status !== 'APPROVED' || !p.approvedAt || Date.now() - Date.parse(p.approvedAt) > 7 * 86400000) return fail('REFUND_NOT_ALLOWED', '환불 조건을 확인해 주세요.', 409)
    const r: PaymentRefund = { id: crypto.randomUUID(), paymentId: p.paymentId!, requestedBy: '74000000-0000-4000-8000-000000000002', amount: p.amount, reason: b.reason, status: workspaceScenario === 'payment-refund-failed' ? 'FAILED' : 'REQUESTED', decidedBy: null, rejectReason: null, pgStatus: null, decidedAt: null, createdAt: new Date().toISOString(), usageVerifiedAt: null }; p.refundRequests.push(r); if (r.status === 'REQUESTED') p.status = 'REFUND_REVIEW'; return r
  }), 201)),
]
