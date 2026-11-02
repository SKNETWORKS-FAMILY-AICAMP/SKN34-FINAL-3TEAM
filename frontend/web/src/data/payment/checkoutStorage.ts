import { validBilling, validPending } from '../../domain/payment.ts'
import type { PendingBilling, PendingCheckout } from '../../domain/payment.ts'

// 토스 결제창에서 돌아올 때 필요한 대기 정보. 탭이 닫히면 사라지도록 sessionStorage에만 둔다.
const checkoutKey = 'sagomungchi:checkout:v1', billingKey = 'sagomungchi:billing:v1'
function read<T>(key: string, valid: (value: unknown) => value is T): T | null {
  try { const v: unknown = JSON.parse(sessionStorage.getItem(key) ?? 'null'); return valid(v) ? v : null }
  catch { return null }
}
export const readCheckout = () => read(checkoutKey, validPending)
export const saveCheckout = (pending: PendingCheckout) => sessionStorage.setItem(checkoutKey, JSON.stringify(pending))
export const readBilling = () => read(billingKey, validBilling)
export const saveBilling = (pending: PendingBilling) => sessionStorage.setItem(billingKey, JSON.stringify(pending))
