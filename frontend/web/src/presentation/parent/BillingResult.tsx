import { useSession } from '../auth/sessionContext.ts'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { billingConfirmation, readBilling } from '../../domain/payment.ts'
import type { PaymentSubscription } from '../../domain/payment.ts'
import { paymentApi, mockPaymentMode } from '../../data/payment/api.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import './payment.css'
const requests = new Map<string, Promise<PaymentSubscription>>()
export function BillingResult({ failed = false }: { failed?: boolean }) {
  const { ready: authReady, session } = useSession()
  const [search] = useState(() => location.search), [pending] = useState(readBilling)
  const id = new URLSearchParams(search).get('subscriptionId') ?? pending?.subscriptionId ?? ''
  const [value, setValue] = useState<PaymentSubscription | null>(null), [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(!failed)
  useEffect(() => {
    history.replaceState(history.state, '', location.pathname + (id ? '?subscriptionId=' + encodeURIComponent(id) : ''))
    if (failed || !authReady || session?.role !== 'PARENT') return
    let active = true
    void (async () => {
      if (!new URLSearchParams(search).has('authKey')) {
        const rows = await paymentApi.subscriptions(); const found = rows.items.find(s => s.subscriptionId === id)
        if (!found) throw new Error('본인의 구독을 확인하지 못했습니다.')
        return found
      }
      const body = billingConfirmation(search, pending)
      let promise = requests.get(pending!.idempotencyKey)
      if (!promise) { promise = paymentApi.registerBilling(pending!.subscriptionId, body, pending!.idempotencyKey); requests.set(pending!.idempotencyKey, promise) }
      return promise
    })().then(s => { if (active) setValue(s) }).catch(e => { if (active) setError(e) }).finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [search, pending, id, failed, authReady, session?.role])
  return <main className="payment-result payment-page"><Link to="/parent/billing">사고뭉치 · 이용권·결제</Link><h1>{failed ? '결제수단 인증을 완료하지 못했습니다' : value?.billingRegistered ? '결제수단 등록 확인' : '결제수단 등록 결과'}</h1>{mockPaymentMode && <p className="payment-test-note">모의 빌링 등록 결과입니다. 실제 PG 발급·청구는 하지 않습니다.</p>}{authReady && session?.role !== 'PARENT' && <p>학부모 로그인이 필요합니다. <Link to="/login">로그인 화면</Link></p>}{busy && (!authReady || session?.role === 'PARENT') && <p role="status">인증 결과를 서버에 확인하고 있습니다…</p>}{failed && <p>등록을 취소했거나 인증을 마치지 못했습니다. 기존 결제수단과 갱신 설정은 결과 조회로 확인해 주세요.</p>}<ErrorNotice error={error} />{value && <><p role="status">{value.billingRegistered ? '결제수단이 등록되어 있습니다.' : '결제수단 등록을 확인하지 못했습니다.'} 자동 갱신 {value.autoRenew ? '사용 중' : '사용 안 함'}.</p><p>다음 결제 예정일 {value.nextBillingDate ?? '없음'}</p></>}<p><Link to="/parent/billing">구독 화면으로 돌아가기</Link></p></main>
}
