import { useEffect, useRef, useState } from 'react'
import { PaymentManagement } from './PaymentManagement.tsx'
import { Link, useNavigate } from 'react-router'
import { useSession } from '../auth/sessionContext.ts'
import type { Child } from '../../domain/classroom.ts'
import { checkoutConfirmation, checkoutStorageKey, paymentComplete, paymentStateLabel, readCheckout, duplicateSubscription } from '../../domain/payment.ts'
import type { PendingCheckout, PaymentState } from '../../domain/payment.ts'
import { paymentApi, paymentClientKey, paymentTestMode, mockPaymentMode } from '../../data/payment/api.ts'
import { loadToss } from '../../data/payment/toss.ts'
import type { TossWidget } from '../../data/payment/toss.ts'
import { useParentQuery } from '../../data/parent/queries.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import './payment.css'

const won = (n: number) => n.toLocaleString('ko-KR') + '원'
export function ParentPayments({ child }: { child?: Child }) {
  const navigate = useNavigate()
  const products = useParentQuery(['products'], signal => paymentApi.products(signal))
  const subscriptions = useParentQuery(['subscriptions'], signal => paymentApi.subscriptions(signal), !paymentTestMode)
  const duplicate = child && duplicateSubscription(subscriptions.data?.items ?? [], child.id)
  const [selection, setSelection] = useState('')
  const product = products.data?.items.find(p => p.id === selection && p.active && p.price > 0)
  const [order, setOrder] = useState<PendingCheckout | null>(() => { const p = readCheckout(); return p?.childId === child?.id ? p : null })
  const [busy, setBusy] = useState(false), [ready, setReady] = useState(false), [error, setError] = useState<unknown>(null)
  const checkoutState = useParentQuery(['checkout-state', order?.orderId], signal => paymentApi.state(order!.orderId, signal), !!order)
  const state = checkoutState.data ?? null
  const widget = useRef<TossWidget | null>(null), createKey = useRef(crypto.randomUUID())
  useEffect(() => {
    if (!order) return
    let active = true
    const resources: { destroy(): void | Promise<void> }[] = []
    void (async () => {
      if (!mockPaymentMode && !/^test_gck_/.test(paymentClientKey)) throw new Error('테스트 결제용 클라이언트 키를 설정해 주세요.')
      // A returning checkout must be reconciled before another payment window can open.
      const previous = await paymentApi.state(order.orderId)
      if (!active) return
      if (previous.status !== 'PENDING') return
      if (mockPaymentMode) { setReady(true); return }
      await loadToss()
      if (!active) return
      const w = window.TossPayments!(paymentClientKey).widgets({ customerKey: 'checkout-' + order.orderId })
      await w.setAmount({ currency: 'KRW', value: order.amount })
      if (!active) return
      const methods = await w.renderPaymentMethods({ selector: '#toss-payment-methods', variantKey: 'DEFAULT' })
      if (!active) { await methods.destroy(); return }; resources.push(methods)
      const agreement = await w.renderAgreement({ selector: '#toss-payment-agreement', variantKey: 'AGREEMENT' })
      if (!active) { await agreement.destroy(); return }; resources.push(agreement)
      widget.current = w; setReady(true)
    })().catch(e => { if (active) setError(e) })
    return () => { active = false; widget.current = null; for (const r of resources) { try { void Promise.resolve(r.destroy()).catch(() => {}) } catch { /* Already removed by the SDK. */ } } }
  }, [order])
  async function prepare() {
    if (!product || !child || duplicate || busy) return
    setBusy(true); setError(null)
    try {
      const created = await paymentApi.order(child.id, product.id, createKey.current)
      const pending = { ...created, confirmKey: crypto.randomUUID(), createdAt: Date.now() }
      sessionStorage.setItem(checkoutStorageKey, JSON.stringify(pending))
      setOrder(pending)
    } catch (e) { setError(e) } finally { setBusy(false) }
  }
  async function pay() {
    if (!order || !ready || busy || !mockPaymentMode && !widget.current) return
    setBusy(true); setError(null)
    try {
      if (mockPaymentMode) { navigate('/payment/success?' + new URLSearchParams({ orderId: order.orderId, amount: String(order.amount), paymentKey: 'mock-payment-' + order.orderId })); return }
      await widget.current!.requestPayment({ orderId: order.orderId, orderName: order.orderName,
        successUrl: location.origin + '/payment/success', failUrl: location.origin + '/payment/fail' })
    } catch (e) { setError(e) } finally { setBusy(false) }
  }
  return <section className="payment-page" data-ui>
    <header><h1>이용권·결제</h1><p>{child ? child.nickname + '님의 학습에 사용할 이용권을 선택해 주세요.' : '신규 구매는 연결된 자녀를 선택해 주세요. 기존 구독과 본인 거래는 아래에서 확인할 수 있습니다.'}</p></header>
    {paymentTestMode && <p className="payment-test-note">결제 연동 테스트 · 실제 청구 없이 토스 인증과 승인을 확인합니다. 테스트 주문은 서버 메모리에만 보관되며 학습 이용권에는 적용되지 않습니다.</p>}
    {mockPaymentMode && <p className="payment-test-note">모의 결제 시연 · 외부 PG를 호출하지 않고 가상 승인·구독·환불을 확인합니다.</p>}
    {duplicate && <p role="status">이 자녀는 이미 이용 중인 구독이 있습니다. 아래에서 결제수단과 자동 갱신을 관리해 주세요.</p>}
    <QueryFeedback query={products} /><ErrorNotice error={error} />
    <div className="payment-columns">
      <section className="payment-panel"><h2>{order ? '결제수단' : '이용권 선택'}</h2>
        {!order && products.data?.items.filter(p => p.active && p.price === 0).map(p => <div className="payment-free" key={p.id}><h3>{p.name} · {won(p.price)}</h3><p>정기 청구 없음 · 대상 자녀 {p.childLimit}명{typeof p.limits.dailyMissions === 'number' ? ` · 하루 미션 ${p.limits.dailyMissions}개` : ''}{p.limits.reportNarrative === false ? ' · 수치 리포트 제공' : ''}</p></div>)}
        {!order ? <><div className="payment-products">{products.data?.items.filter(p => p.active && p.price > 0 && p.billingCycle === 'MONTHLY').map(p => <label key={p.id} className="payment-option"><input type="radio" name="product" value={p.id} checked={selection === p.id} onChange={() => { setSelection(p.id); createKey.current = crypto.randomUUID() }} /><span>{p.name}<small>자녀 {p.childLimit}명 · {p.billingCycle === 'MONTHLY' ? '1개월 · 자동결제 등록 시 매월 청구' : p.billingCycle}</small><small>{typeof p.limits.dailyFeedback === 'number' ? `하루 피드백 ${p.limits.dailyFeedback}회 · ` : ''}{typeof p.limits.dailyConversations === 'number' ? `분석 대화 ${p.limits.dailyConversations}회 · ` : ''}{typeof p.limits.reportNarrative === 'boolean' ? p.limits.reportNarrative ? '전체 리포트' : '수치 리포트' : ''}</small></span><strong>{won(p.price)}</strong></label>)}</div>
          {products.data && !products.data.items.some(p => p.active && p.price > 0 && p.billingCycle === 'MONTHLY') && <p>현재 구매 가능한 이용권이 없습니다.</p>}
          <button className="payment-primary" disabled={!child || !product || duplicate || busy || !paymentTestMode && (subscriptions.isPending || !!subscriptions.error) || !mockPaymentMode && !/^test_gck_/.test(paymentClientKey)} onClick={() => void prepare()}>{busy ? '주문을 준비하고 있습니다…' : '결제수단 선택'}</button>
          {!mockPaymentMode && !paymentClientKey && <p>결제 설정을 확인하고 있습니다. 관리자에게 문의해 주세요.</p>}</>
          : <><QueryFeedback query={checkoutState} /><div id="toss-payment-methods" /><div id="toss-payment-agreement" />
            {!ready && state?.status === 'PENDING' && !error && <p role="status">토스 결제수단을 불러오고 있습니다.</p>}
            {state && state.status !== 'PENDING' ? <><p role="status">{paymentTestMode && state.status === 'APPROVED' ? '테스트 결제 승인이 완료되었습니다. 학습 이용권은 변경되지 않습니다.' : paymentStateLabel(state)}</p><Link to={'/payment/success?orderId=' + encodeURIComponent(order.orderId)}>결제 결과 확인</Link></>
              : <button className="payment-primary" disabled={!ready || busy} onClick={() => void pay()}>{busy ? '결제창으로 이동 중…' : won(order.amount) + ' 결제하기'}</button>}
          </>}
      </section>
      <aside className="payment-panel payment-summary"><h2>주문 확인</h2><dl><div><dt>이용할 자녀</dt><dd>{child?.nickname ?? '자녀 선택 필요'}</dd></div><div><dt>이용권</dt><dd>{order?.orderName ?? product?.name ?? '선택해 주세요'}</dd></div><div><dt>결제 금액</dt><dd className="payment-amount">{order ? won(order.amount) : product ? won(product.price) : '—'}</dd></div></dl><p>이번 결제는 1개월 이용권 구매입니다. 자동결제 등록은 포함하지 않습니다.</p><p>결제창에서 인증을 마친 뒤 서버 승인이 완료되면 결과를 안내해 드립니다.</p>{order && <small className="payment-order-id">주문번호 {order.orderId}</small>}</aside>
    </div>
    <PaymentManagement key={child?.id ?? 'all'} child={child} />
  </section>
}

// Share the in-flight request across React StrictMode effects; use the same stored idempotency key after reload.
const confirmations = new Map<string, Promise<PaymentState>>()
export function PaymentResult({ failed = false }: { failed?: boolean }) {
  const { ready: authReady, session } = useSession()
  const [callback] = useState(() => location.search), [pending] = useState(readCheckout)
  const [state, setState] = useState<PaymentState | null>(null), [error, setError] = useState<unknown>(null), [busy, setBusy] = useState(!failed)
  const id = new URLSearchParams(callback).get('orderId') ?? pending?.orderId ?? ''
  async function refresh() {
    if (!id) return
    setBusy(true); setError(null)
    try { setState(await paymentApi.state(id)) } catch (e) { setError(e) } finally { setBusy(false) }
  }
  useEffect(() => {
    // Keep paymentKey out of subsequent navigation, copied URLs and referrers.
    history.replaceState(history.state, '', location.pathname + (id ? '?orderId=' + encodeURIComponent(id) : ''))
    if (failed || !authReady || session?.role !== 'PARENT') return
    let active = true
    void (async () => {
      const q = new URLSearchParams(callback)
      if (!q.has('paymentKey')) {
        if (!id) throw new Error('확인할 주문이 없습니다.')
        return paymentApi.state(id)
      }
      const body = checkoutConfirmation(callback, pending)
      const key = body.orderId
      let promise = confirmations.get(key)
      if (!promise) { promise = paymentApi.confirm(body, pending!.confirmKey); confirmations.set(key, promise) }
      return promise
    })().then(r => { if (active) setState(r) }).catch(e => { if (active) setError(e) }).finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [callback, pending, id, failed, authReady, session?.role])
  const stateOrderId = state?.orderId, stateStatus = state?.status, entitlementStatus = state?.entitlementStatus
  useEffect(() => {
    if (!stateOrderId || !['PENDING', 'CONFIRMING'].includes(stateStatus ?? '') && !(stateStatus === 'APPROVED' && entitlementStatus === 'RECOVERY_REQUIRED')) return
    let active = true, tries = 0
    const timer = setInterval(() => {
      if (++tries > 10) { clearInterval(timer); return }
      void paymentApi.state(stateOrderId).then(r => { if (active) setState(r) }).catch(e => { if (active) setError(e); clearInterval(timer) })
    }, 3000)
    return () => { active = false; clearInterval(timer) }
  }, [stateOrderId, stateStatus, entitlementStatus])
  const complete = state && (paymentComplete(state) || paymentTestMode && state.status === 'APPROVED')
  return <main className="payment-result payment-page" data-ui><Link to="/parent/billing">사고뭉치 · 이용권·결제</Link><h1>{failed ? '결제를 완료하지 못했습니다' : complete ? mockPaymentMode ? '모의 결제가 완료되었습니다' : '결제가 완료되었습니다' : '결제 결과 확인'}</h1>
    {mockPaymentMode && <p className="payment-test-note">모의 승인 결과입니다. 실제 PG 승인·청구가 아닙니다.</p>}
    {authReady && session?.role !== 'PARENT' && <p>결제 정보를 확인하려면 학부모로 로그인해 주세요. <Link to="/login">로그인 화면</Link></p>}
    {failed ? <p>결제 인증이 취소되었거나 완료되지 않았습니다. 이 화면에서는 승인을 요청하지 않았습니다.</p> : busy && (!authReady || session?.role === 'PARENT') ? <p role="status">서버에서 결제 결과를 확인하고 있습니다…</p> : state && <p role="status">{paymentTestMode && state.status === 'APPROVED' ? '토스 테스트 승인이 완료되었습니다. 실제 청구와 학습 이용권 적용은 이루어지지 않습니다.' : paymentStateLabel(state)}</p>}
    <ErrorNotice error={error} />{state && <dl><div><dt>결제 금액</dt><dd>{won(state.amount)}</dd></div><div><dt>주문번호</dt><dd className="payment-order-id">{state.orderId}</dd></div></dl>}
    {!complete && id && <button className="payment-primary" disabled={busy} onClick={() => void refresh()}>결제 상태 다시 확인</button>}
    <p><Link to={'/parent/billing' + (pending ? '?childId=' + encodeURIComponent(pending.childId) : '')}>이용권 화면으로 돌아가기</Link></p>
  </main>
}
