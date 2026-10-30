export interface PaymentProduct {
  id: string; code: string; name: string; price: number; billingCycle: string
  childLimit: number; active: boolean; features: Record<string, unknown>; limits: Record<string, unknown>
}
export interface PaymentOrder {
  orderId: string; amount: number; orderName: string; childId: string; productId: string
}
export interface PendingCheckout extends PaymentOrder {
  confirmKey: string; createdAt: number
}
export interface PaymentState {
  paymentId: string | null; orderId: string; childId: string; amount: number
  status: string; entitlementStatus: string | null; approvedAt: string | null; failureCode: string | null
}
export const checkoutStorageKey = 'sagomungchi:checkout:v1'
export function validPending(value: unknown): value is PendingCheckout {
  if (!value || typeof value !== 'object') return false
  const v = value as PendingCheckout
  return typeof v.orderId === 'string' && /^[A-Za-z0-9_-]{6,64}$/.test(v.orderId)
    && Number.isSafeInteger(v.amount) && v.amount > 0 && typeof v.childId === 'string'
    && typeof v.orderName === 'string' && typeof v.productId === 'string'
    && typeof v.confirmKey === 'string' && /^[0-9a-f-]{36}$/i.test(v.confirmKey)
    && Number.isFinite(v.createdAt) && Date.now() - v.createdAt < 3_600_000 && v.createdAt <= Date.now()
}
export function readCheckout(): PendingCheckout | null {
  try { const v: unknown = JSON.parse(sessionStorage.getItem(checkoutStorageKey) ?? 'null'); return validPending(v) ? v : null }
  catch { return null }
}
export function checkoutConfirmation(search: string, pending: PendingCheckout | null) {
  const q = new URLSearchParams(search)
  if (!pending || !validPending(pending) || q.getAll('orderId').length !== 1 || q.getAll('amount').length !== 1
      || q.getAll('paymentKey').length !== 1 || q.get('orderId') !== pending.orderId
      || !/^\d+$/.test(q.get('amount') ?? '') || Number(q.get('amount')) !== pending.amount
      || !q.get('paymentKey') || q.get('paymentKey')!.length > 200)
    throw new Error('주문 정보가 일치하지 않습니다. 결제 내역에서 상태를 먼저 확인해 주세요.')
  return { orderId: pending.orderId, amount: pending.amount, paymentKey: q.get('paymentKey')! }
}
export function paymentComplete(state: PaymentState) {
  return state.status === 'APPROVED' && state.entitlementStatus === 'APPLIED'
}
export function paymentStateLabel(state: PaymentState) {
  if (paymentComplete(state)) return '결제와 이용권 적용이 완료되었습니다.'
  if (state.status === 'APPROVED') return '결제는 승인됐습니다. 이용권 적용을 확인하고 있습니다.'
  if (['PENDING', 'CONFIRMING'].includes(state.status)) return '결제 결과를 확인하고 있습니다. 다시 결제하지 마세요.'
  return ({ FAILED: '결제가 승인되지 않았습니다.', CANCELED: '취소된 결제입니다.', REFUNDED: '환불된 결제입니다.', REFUND_REVIEW: '환불 요청을 확인하고 있습니다.' } as Record<string, string>)[state.status] ?? '결제 상태를 확인해 주세요.'
}

export interface PaymentSubscription {
  subscriptionId: string; childId: string; product: PaymentProduct | null; status: string
  periodStart: string; periodEnd: string; nextBillingDate: string | null; autoRenew: boolean
  graceUntil: string | null; renewalRetryCount: number; billingRegistered: boolean
}
export interface PaymentRefund {
  id: string; paymentId: string; requestedBy: string; amount: number; reason: string; status: string
  decidedBy: string | null; rejectReason: string | null; pgStatus: string | null; decidedAt: string | null
  createdAt: string; usageVerifiedAt: string | null
}
export interface PaymentRecord extends PaymentState {
  subscription: PaymentSubscription | null; refundRequests: PaymentRefund[]
}
export interface PendingBilling {
  subscriptionId: string; customerKey: string; idempotencyKey: string; createdAt: number
}
export const billingStorageKey = 'sagomungchi:billing:v1'
export function readBilling(): PendingBilling | null {
  try {
    const p = JSON.parse(sessionStorage.getItem(billingStorageKey) ?? 'null') as PendingBilling | null
    return p && typeof p.subscriptionId === 'string' && typeof p.customerKey === 'string'
      && typeof p.idempotencyKey === 'string' && /^[0-9a-f-]{36}$/i.test(p.idempotencyKey)
      && Number.isFinite(p.createdAt) && p.createdAt <= Date.now() && Date.now() - p.createdAt < 600000 ? p : null
  } catch { return null }
}
export function billingConfirmation(search: string, p: PendingBilling | null) {
  const q = new URLSearchParams(search)
  if (!p || Date.now() - p.createdAt >= 600000 || q.getAll('customerKey').length !== 1
    || q.get('customerKey') !== p.customerKey || q.getAll('authKey').length !== 1
    || !q.get('authKey') || q.get('authKey')!.length > 300) throw new Error('결제수단 인증 정보를 확인하지 못했습니다. 구독 화면에서 다시 등록해 주세요.')
  return { authKey: q.get('authKey')!, customerKey: p.customerKey }
}
export const subscriptionLabels: Record<string, string> = { ACTIVE: '이용 중', RENEWAL_FAILED: '갱신 실패 · 유예 중', CANCELED: '이용 종료', EXPIRED: '기간 만료' }
export const refundLabels: Record<string, string> = { REQUESTED: '환불 검토 중', APPROVED: '취소 처리 확인 중', REJECTED: '환불 반려', COMPLETED: '환불 완료', FAILED: '환불 처리 실패' }
export function duplicateSubscription(items: PaymentSubscription[], childId: string) {
  return items.some(s => s.childId === childId && ['ACTIVE', 'RENEWAL_FAILED'].includes(s.status))
}
