import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { PaymentState, PaymentSubscription } from '../../domain/payment.ts'
import { paymentApi } from './api.ts'

const stateKey = (orderId: string) => ['parent', 'payment-result', orderId]

/**
 * 결제 결과 재조회 간격. 승인 대기(PENDING·CONFIRMING)나 이용권 복구 필요(APPROVED+RECOVERY_REQUIRED)일 때만
 * 3초마다 묻는다. 첫 응답 뒤 최대 10회, 조회 오류가 나면 멈춘다.
 */
export function paymentPollDelay(state: PaymentState | undefined, updates: number, failed: boolean): number | false {
  if (!state || failed || updates > 10) return false
  const waiting = ['PENDING', 'CONFIRMING'].includes(state.status)
    || state.status === 'APPROVED' && state.entitlementStatus === 'RECOVERY_REQUIRED'
  return waiting ? 3000 : false
}

/** 결제 결과 화면의 주문 상태. 승인 응답을 받은 경우 그 값으로 시작해 같은 상태를 바로 다시 묻지 않는다. */
export function usePaymentResult(orderId: string, enabled: boolean) {
  return useQuery({
    queryKey: stateKey(orderId),
    queryFn: ({ signal }) => paymentApi.state(orderId, signal),
    enabled: enabled && !!orderId,
    retry: false,
    // 승인 응답으로 채운 값은 바로 다시 묻지 않고, 화면을 떠나면 버려 다음 진입에서 새로 조회한다.
    staleTime: Infinity,
    gcTime: 0,
    refetchInterval: q => paymentPollDelay(q.state.data, q.state.dataUpdateCount, q.state.status === 'error'),
    refetchIntervalInBackground: true,
  })
}

// StrictMode의 effect 두 번 실행이 같은 요청을 공유하도록 모듈 단위로 보관한다. 새로고침 뒤에는 저장된 같은 멱등 키로 다시 보낸다.
const confirmations = new Map<string, Promise<PaymentState>>()
const registrations = new Map<string, Promise<PaymentSubscription>>()
function shared<T>(requests: Map<string, Promise<T>>, key: string, start: () => Promise<T>) {
  let promise = requests.get(key)
  if (!promise) { promise = start(); requests.set(key, promise) }
  return promise
}

export function usePaymentConfirmation() {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: ({ body, key }: { body: { orderId: string; amount: number; paymentKey: string }; key: string }) =>
      shared(confirmations, body.orderId, () => paymentApi.confirm(body, key)),
    onSuccess: (state, { body }) => cache.setQueryData(stateKey(body.orderId), state),
  })
}

export function useBillingRegistration() {
  return useMutation({
    mutationFn: ({ subscriptionId, body, key }: { subscriptionId: string; body: { authKey: string; customerKey: string }; key: string }) =>
      shared(registrations, key, () => paymentApi.registerBilling(subscriptionId, body, key)),
  })
}

/** 결제수단 인증 없이 결과 화면에 들어온 경우 본인 구독 목록에서 해당 구독을 찾는다. */
export function useOwnSubscription(subscriptionId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['parent', 'subscription-result', subscriptionId],
    enabled,
    retry: false,
    queryFn: async ({ signal }) => {
      const found = (await paymentApi.subscriptions(signal)).items.find(s => s.subscriptionId === subscriptionId)
      if (!found) throw new Error('본인의 구독을 확인하지 못했습니다.')
      return found
    },
  })
}
