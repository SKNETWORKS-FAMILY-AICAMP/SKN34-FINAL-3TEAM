export interface TossPayment {
  requestBillingAuth(options: { method: 'CARD'; successUrl: string; failUrl: string }): Promise<void>
}
export interface TossWidget {
  setAmount(amount: { currency: 'KRW'; value: number }): Promise<void>
  renderPaymentMethods(options: { selector: string; variantKey: string }): Promise<{ destroy(): void | Promise<void> }>
  renderAgreement(options: { selector: string; variantKey: string }): Promise<{ destroy(): void | Promise<void> }>
  requestPayment(options: { orderId: string; orderName: string; successUrl: string; failUrl: string }): Promise<void>
}
declare global {
  interface Window { TossPayments?: (key: string) => { widgets(options: { customerKey: string }): TossWidget; payment(options: { customerKey: string }): TossPayment } }
}
let sdk: Promise<void> | undefined
export function loadToss() {
  if (window.TossPayments) return Promise.resolve()
  return sdk ??= new Promise<void>((resolve, reject) => {
    const tag = document.createElement('script')
    tag.src = 'https://js.tosspayments.com/v2/standard'
    tag.async = true
    const timeout = setTimeout(() => fail(), 20000)
    const fail = () => { clearTimeout(timeout); tag.remove(); sdk = undefined; reject(new Error('결제창을 불러오지 못했습니다. 네트워크를 확인한 뒤 다시 시도해 주세요.')) }
    tag.onload = () => { clearTimeout(timeout); if (window.TossPayments) resolve(); else fail() }
    tag.onerror = fail
    document.head.append(tag)
  })
}
