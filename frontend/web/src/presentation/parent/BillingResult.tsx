import { useSession } from '../auth/sessionContext.ts'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { billingConfirmation } from '../../domain/payment.ts'
import { mockPaymentMode } from '../../data/payment/api.ts'
import { readBilling } from '../../data/payment/checkoutStorage.ts'
import { useBillingRegistration, useOwnSubscription } from '../../data/payment/queries.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import './payment.css'
export function BillingResult({ failed = false }: { failed?: boolean }) {
  const { ready: authReady, session } = useSession()
  const [search] = useState(() => location.search), [pending] = useState(readBilling)
  const id = new URLSearchParams(search).get('subscriptionId') ?? pending?.subscriptionId ?? ''
  const callback = new URLSearchParams(search).has('authKey')
  const [request] = useState(() => {
    if (!callback) return null
    try { return { body: billingConfirmation(search, pending) } } catch (error) { return { error } }
  })
  const parent = !failed && authReady && session?.role === 'PARENT'
  const register = useBillingRegistration(), { mutate } = register
  const existing = useOwnSubscription(id, parent && !callback)
  useEffect(() => {
    history.replaceState(history.state, '', location.pathname + (id ? '?subscriptionId=' + encodeURIComponent(id) : ''))
  }, [id])
  useEffect(() => {
    if (parent && request?.body) mutate({ subscriptionId: pending!.subscriptionId, body: request.body, key: pending!.idempotencyKey })
  }, [parent, request, pending, mutate])
  const value = callback ? register.data : existing.data
  const error = parent ? request?.error ?? register.error ?? existing.error : null
  const busy = !failed && (!authReady || parent && !error && !value)
  return <main className="payment-result payment-page"><Link to="/parent/billing">사고뭉치 · 이용권·결제</Link><h1>{failed ? '결제수단 인증을 완료하지 못했습니다' : value?.billingRegistered ? '결제수단 등록 확인' : '결제수단 등록 결과'}</h1>{mockPaymentMode && <p className="payment-test-note">모의 빌링 등록 결과입니다. 실제 PG 발급·청구는 하지 않습니다.</p>}{authReady && session?.role !== 'PARENT' && <p>학부모 로그인이 필요합니다. <Link to="/login">로그인 화면</Link></p>}{busy && (!authReady || session?.role === 'PARENT') && <p role="status">인증 결과를 서버에 확인하고 있습니다…</p>}{failed && <p>등록을 취소했거나 인증을 마치지 못했습니다. 기존 결제수단과 갱신 설정은 결과 조회로 확인해 주세요.</p>}<ErrorNotice error={error} />{value && <><p role="status">{value.billingRegistered ? '결제수단이 등록되어 있습니다.' : '결제수단 등록을 확인하지 못했습니다.'} 자동 갱신 {value.autoRenew ? '사용 중' : '사용 안 함'}.</p><p>다음 결제 예정일 {value.nextBillingDate ?? '없음'}</p></>}<p><Link to="/parent/billing">구독 화면으로 돌아가기</Link></p></main>
}
