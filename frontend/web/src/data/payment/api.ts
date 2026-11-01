import { apiFetch, toApiError } from '../apiClient.ts'
import type { PaymentProduct, PaymentOrder, PaymentState, PaymentRecord, PaymentRefund, PaymentSubscription } from '../../domain/payment.ts'

export const paymentTestMode = Boolean(import.meta.env?.DEV && import.meta.env?.VITE_PAYMENT_TEST === 'true')
export const mockPaymentMode = Boolean(import.meta.env?.DEV && import.meta.env?.VITE_API_MOCK === 'true' && !paymentTestMode)
export const billingClientKey = import.meta.env?.VITE_TOSS_TEST_BILLING_CLIENT_KEY ?? ''
export const paymentClientKey = import.meta.env?.VITE_TOSSPAYMENTS_CLIENT_KEY ?? ''
async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!paymentTestMode) return apiFetch<T>(path, init)
  const r = await fetch('/__payment-test' + path, { ...init, credentials: 'same-origin', headers: {
    'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest', ...Object.fromEntries(new Headers(init.headers)),
  } })
  if (!r.ok) throw await toApiError(r)
  return r.json() as Promise<T>
}
const post = (body: unknown, key: string): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key }, body: JSON.stringify(body) })
export const paymentApi = {
  history: (page = 0, signal?: AbortSignal) => call<{ items: PaymentRecord[] }>(`/payments?page=${page}&size=20`, { signal }),
  subscriptions: (signal?: AbortSignal) => call<{ items: PaymentSubscription[] }>('/subscriptions', { signal }),
  billingSetup: (id: string) => call<{ subscriptionId: string; customerKey: string }>(`/subscriptions/${encodeURIComponent(id)}/billing-key`),
  registerBilling: (id: string, body: { authKey: string; customerKey: string }, key: string) => call<PaymentSubscription>(`/subscriptions/${encodeURIComponent(id)}/billing-key`, post(body, key)),
  autoRenew: (id: string, enabled: boolean) => call<PaymentSubscription>(`/subscriptions/${encodeURIComponent(id)}/auto-renewal`, { method: enabled ? 'PUT' : 'DELETE' }),
  refund: (id: string, reason: string, key: string) => call<PaymentRefund>(`/payments/${encodeURIComponent(id)}/refund-requests`, post({ reason }, key)),
  products: (signal?: AbortSignal) => call<{ items: PaymentProduct[] }>('/products', { signal }),
  order: (childId: string, productId: string, key: string) => call<PaymentOrder>('/orders', post({ childId, productId }, key)),
  confirm: (body: { orderId: string; amount: number; paymentKey: string }, key: string) => call<PaymentState>('/payments/confirm', post(body, key)),
  state: (orderId: string, signal?: AbortSignal) => call<PaymentState>('/payments/' + encodeURIComponent(orderId), { signal }),
}
