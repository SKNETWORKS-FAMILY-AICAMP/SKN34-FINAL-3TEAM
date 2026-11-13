import { nextBillingMonth } from '../../domain/payment.ts'
import type { ChildEntitlement, PaymentProduct, PaymentRecord, PaymentSubscription, PaymentOrder } from '../../domain/payment.ts'
import { mockAccountChildren, mockIdentity } from './accounts.ts'

// 목업 이용권의 유일한 출처. /children 응답에는 이용권을 넣지 않고(api-spec 3.7·5.3),
// entitlement·구독 목업과 목업 안 권한 검사(분석 대화·서술·추가 문제)가 모두 이 구독 상태만 읽는다.
export const premiumProduct: PaymentProduct = { id: '74000000-0000-4000-8000-000000000001', code: 'PREMIUM', name: '프리미엄', price: 14900, billingCycle: 'MONTHLY', childLimit: 1, active: true, features: { feedback: true, conversations: true, fullReport: true }, limits: { dailyFeedback: 50, dailyConversations: 30, reportNarrative: true } }
export const freeProduct: PaymentProduct = { ...premiumProduct, id: '74000000-0000-4000-8000-000000000000', code: 'FREE', name: '무료', price: 0, billingCycle: 'NONE', features: { feedback: true, conversations: false, fullReport: false }, limits: { dailyMissions: 3, dailyConversations: 0, reportNarrative: false } }
export type PaymentAccount = { subscriptions: PaymentSubscription[]; payments: PaymentRecord[]; orders: Map<string, PaymentOrder>; keys: Map<string, { body: string; result: unknown }> }
/** 처음부터 구독 중인 가상 자녀. 신규 등록 자녀는 구독이 없어 무료다. */
const seededPremium = ['demo-seoyun']
const accounts = new Map<string, PaymentAccount>()
const storageKey = 'sagomungchi:payment-fixture:v1'
// Only virtual development fixtures cross tabs; production uses the server as source of truth.
const fixtureChannel = typeof window !== 'undefined' && typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel(storageKey) : null
import.meta.hot?.dispose(() => fixtureChannel?.close())
export const mockDay = (offset: number) => new Date(Date.now() + offset * 86400000).toLocaleDateString('sv-SE', { timeZone: 'Asia/Seoul' })
export function persistPaymentFixture() {
  if (typeof sessionStorage === 'undefined') return
  const value = JSON.stringify([...accounts].map(([owner, a]) => [owner, { subscriptions: a.subscriptions, payments: a.payments, orders: [...a.orders] }]))
  if (sessionStorage.getItem(storageKey) === value) return
  sessionStorage.setItem(storageKey, value)
  fixtureChannel?.postMessage(value)
}
function restoreFixture(value: string) {
  try {
    const saved = JSON.parse(value)
    for (const [owner, data] of saved) {
      if (typeof owner !== 'string' || !owner.endsWith('@example.test') || !Array.isArray(data.subscriptions) || !Array.isArray(data.payments) || !Array.isArray(data.orders)) continue
      const a: PaymentAccount = { ...data, orders: new Map(data.orders), keys: accounts.get(owner)?.keys ?? new Map() }
      for (const p of a.payments) if (p.subscription) p.subscription = a.subscriptions.find(s => s.subscriptionId === p.subscription?.subscriptionId) ?? p.subscription
      accounts.set(owner, a)
    }
  } catch { /* Development fixture only. */ }
}
if (typeof sessionStorage !== 'undefined') restoreFixture(sessionStorage.getItem(storageKey) ?? '[]')
if (fixtureChannel) fixtureChannel.onmessage = event => {
  if (typeof event.data !== 'string' || sessionStorage.getItem(storageKey) === event.data) return
  restoreFixture(event.data)
  sessionStorage.setItem(storageKey, event.data)
  window.dispatchEvent(new Event('sagomungchi:payment-fixture-updated'))
}
function subscription(childId: string, start: string, billing: boolean): PaymentSubscription {
  return { subscriptionId: crypto.randomUUID(), childId, product: structuredClone(premiumProduct), status: 'ACTIVE', periodStart: start, periodEnd: nextBillingMonth(start), nextBillingDate: billing ? nextBillingMonth(start) : null, autoRenew: billing, graceUntil: null, renewalRetryCount: 0, billingRegistered: billing }
}
/** 보호자별 결제 상태. 처음 만들 때 그 보호자의 가상 자녀 중 시드 구독 대상을 2일 전 결제로 넣는다. */
export function paymentAccount(owner = mockIdentity.email): PaymentAccount {
  let a = accounts.get(owner)
  if (!a) {
    a = { subscriptions: [], payments: [], orders: new Map(), keys: new Map() }
    const owned = mockAccountChildren.get(owner)?.map(c => c.id) ?? (owner === 'parent@example.test' ? seededPremium : [])
    for (const childId of seededPremium.filter(id => owned.includes(id))) {
      const s = subscription(childId, mockDay(-2), true)
      a.subscriptions.push(s)
      a.payments.push({ paymentId: crypto.randomUUID(), orderId: 'mock-' + crypto.randomUUID(), childId, amount: premiumProduct.price, status: 'APPROVED', entitlementStatus: 'APPLIED', approvedAt: new Date(Date.now() - 2 * 86400000).toISOString(), failureCode: null, subscription: s, refundRequests: [] })
    }
    accounts.set(owner, a)
  }
  return a
}
export function existingPaymentAccount(owner: string) { return accounts.get(owner) }
export function addMockSubscription(a: PaymentAccount, childId: string) {
  const s = subscription(childId, mockDay(0), false)
  a.subscriptions.push(s)
  return s
}
/** 실제 entitlement 응답과 같은 모양. 이용 중 구독(유예 포함)이 없으면 무료 상품이다. */
export function mockEntitlement(childId: string, owner = mockIdentity.email): ChildEntitlement {
  const a = paymentAccount(owner)
  const sub = a.subscriptions.find(s => s.childId === childId &&
    ((s.status === 'ACTIVE' && s.periodEnd > mockDay(0)) || (s.status === 'RENEWAL_FAILED' && (s.graceUntil ?? '') > mockDay(0))))
  const product = sub?.product ?? freeProduct
  const refundPending = a.payments.some(p => p.childId === childId && p.status === 'REFUND_REVIEW')
  return { childId, product, subscriptionId: sub?.subscriptionId ?? null, status: sub?.status ?? 'FREE',
    autoRenew: sub?.autoRenew ?? false, periodEnd: sub?.periodEnd ?? null, graceUntil: sub?.graceUntil ?? null,
    refundPending, conversationEnabled: !refundPending && Number(product.limits.dailyConversations) > 0,
    narrativeEnabled: !refundPending && product.limits.reportNarrative === true }
}
/** 목업 권한 검사용: 지금 이 보호자의 구독으로 프리미엄 상품을 쓰는지. */
export const mockPremium = (childId: string) => mockEntitlement(childId, ownerOf(childId)).product.code === 'PREMIUM'
/** 학생 화면(기기 로그인 포함)에서도 그 자녀 보호자의 구독을 읽는다. */
function ownerOf(childId: string) {
  if (mockAccountChildren.get(mockIdentity.email)?.some(c => c.id === childId)) return mockIdentity.email
  for (const [owner, children] of mockAccountChildren) if (children.some(c => c.id === childId)) return owner
  return mockIdentity.email
}
/** 테스트 설정 전용: 구독을 붙이거나(PREMIUM) 이용 중 구독을 지운다(FREE). 결제 내역은 건드리지 않는다. */
export function setMockSubscription(childId: string, plan: 'FREE' | 'PREMIUM', owner = mockIdentity.email) {
  const a = paymentAccount(owner)
  a.subscriptions = a.subscriptions.filter(s => s.childId !== childId || !['ACTIVE', 'RENEWAL_FAILED'].includes(s.status))
  if (plan === 'PREMIUM') addMockSubscription(a, childId)
  persistPaymentFixture()
}
