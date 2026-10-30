import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import type { Child } from '../../domain/classroom.ts'
import type { PaymentRecord, PaymentSubscription } from '../../domain/payment.ts'
import { billingStorageKey, paymentStateLabel, refundLabels, subscriptionLabels } from '../../domain/payment.ts'
import { billingClientKey, mockPaymentMode, paymentApi, paymentTestMode } from '../../data/payment/api.ts'
import { loadToss } from '../../data/payment/toss.ts'
import { useParentMutation, useParentQuery } from '../../data/parent/queries.ts'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import { QueryFeedback } from '../common/Workspace.tsx'

const won = (n: number) => n.toLocaleString('ko-KR') + '원'
function date(value: string | null) { return value ? value.slice(0, 10) : '예정 없음' }
export function SubscriptionCard({ value: s, refundPending = false }: { value: PaymentSubscription; refundPending?: boolean }) {
  const navigate = useNavigate()
  const [agree, setAgree] = useState(false), [change, setChange] = useState<boolean | null>(null)
  const register = useParentMutation(async () => {
    const setup = await paymentApi.billingSetup(s.subscriptionId)
    const pending = { ...setup, idempotencyKey: crypto.randomUUID(), createdAt: Date.now() }
    sessionStorage.setItem(billingStorageKey, JSON.stringify(pending))
    if (mockPaymentMode) { navigate('/payment/billing/success?' + new URLSearchParams({ customerKey: setup.customerKey, authKey: 'mock-billing-' + setup.subscriptionId })); return }
    if (!/^test_ck_/.test(billingClientKey)) throw new Error('자동결제 상점의 테스트 클라이언트 키를 설정해 주세요.')
    await loadToss()
    await window.TossPayments!(billingClientKey).payment({ customerKey: setup.customerKey }).requestBillingAuth({ method: 'CARD', successUrl: location.origin + '/payment/billing/success', failUrl: location.origin + '/payment/billing/fail' })
  })
  const renewal = useParentMutation((enabled: boolean) => paymentApi.autoRenew(s.subscriptionId, enabled))
  const active = ['ACTIVE', 'RENEWAL_FAILED'].includes(s.status)
  return <article className="payment-panel"><h3>{s.product?.name ?? '이용권'} · {subscriptionLabels[s.status] ?? s.status}</h3>
    <dl><div><dt>이용 기간</dt><dd>{date(s.periodStart)} ~ {date(s.periodEnd)} 09:00 KST</dd></div><div><dt>자동 갱신</dt><dd>{s.autoRenew ? '사용 중' : '사용 안 함'}</dd></div><div><dt>다음 결제</dt><dd>{date(s.nextBillingDate)}{s.nextBillingDate ? ' 09:00 KST' : ''}</dd></div><div><dt>갱신 금액</dt><dd>{s.product ? won(s.product.price) : '확인 필요'}</dd></div><div><dt>결제수단</dt><dd>{s.billingRegistered ? '등록됨' : '미등록'}</dd></div></dl>
    {s.status === 'RENEWAL_FAILED' && <p role="status">갱신 결제에 실패했습니다. 재청구 {s.renewalRetryCount}회 / 최대 3회. 유예 종료 {date(s.graceUntil)}. 다음 재시도 {date(s.nextBillingDate)}{s.autoRenew ? ' 09:00 KST' : ' · 자동 갱신 중단'}. 유예 중 이용은 유지되며, 모두 실패하면 해지됩니다.</p>}
    {active && <><label className="payment-agreement"><input type="checkbox" checked={agree} onChange={e => setAgree(e.target.checked)} />결제수단을 등록하면 표시된 금액으로 매월 자동 갱신되는 데 동의합니다.</label>
      <button disabled={refundPending || !agree || register.isPending || !mockPaymentMode && !/^test_ck_/.test(billingClientKey)} onClick={() => void register.mutateAsync(undefined).catch(() => {})}>{s.billingRegistered ? '결제수단 변경' : '자동결제 수단 등록'}</button>
      {!mockPaymentMode && !billingClientKey && <p>자동결제 설정을 준비하고 있습니다. 일반 결제 키와 별도의 빌링 키가 필요합니다.</p>}
      <div className="payment-actions">{s.autoRenew ? <button disabled={renewal.isPending} onClick={() => setChange(false)}>자동 갱신 해지</button> : s.status === 'ACTIVE' && s.billingRegistered && !refundPending && <button disabled={renewal.isPending} onClick={() => setChange(true)}>자동 갱신 해지 철회</button>}</div>
      {!s.autoRenew && <p>새로운 자동 청구는 하지 않습니다. 이미 결제한 이용 기간은 유지됩니다.</p>}</>}
    {refundPending && <p>환불 검토 중에는 결제수단 등록·변경과 자동 갱신 해지 철회가 제한됩니다.</p>}
    <ErrorNotice error={register.error ?? renewal.error} />
    {change !== null && <Modal title={change ? '자동 갱신 해지 철회' : '자동 갱신 해지'} onClose={() => setChange(null)}><p>{change ? `${date(s.periodEnd)}부터 매월 자동 청구를 다시 시작합니다.` : `${date(s.periodEnd)} 09:00 KST까지 이용할 수 있으며 다음 자동 청구를 중단합니다. 이미 결제된 금액은 환불되지 않습니다.`}</p><button disabled={renewal.isPending} onClick={() => void renewal.mutateAsync(change).then(() => setChange(null)).catch(() => {})}>{renewal.isPending ? '처리 중…' : '내용 확인 후 적용'}</button><ErrorNotice error={renewal.error} /></Modal>}
  </article>
}
function RefundForm({ payment, onClose }: { payment: PaymentRecord; onClose: () => void }) {
  const [reason, setReason] = useState(''), [agree, setAgree] = useState(false), [key, setKey] = useState(() => crypto.randomUUID())
  const request = useParentMutation(() => paymentApi.refund(payment.paymentId!, reason.trim(), key))
  return <Modal title="전액 환불 요청" onClose={onClose}><p>결제 후 7일 이내이며 프리미엄 기능을 사용하지 않은 경우 전액 환불을 요청할 수 있습니다. 서버에서 사용 내역과 조건을 확인합니다.</p><p>요청 금액 {won(payment.amount)} · 환불이 완료되면 구독이 즉시 종료됩니다. 검토 중에는 새로운 프리미엄 사용이 제한됩니다.</p><label>환불 사유<textarea maxLength={200} value={reason} onChange={e => { setReason(e.target.value); setKey(crypto.randomUUID()) }} /></label><label className="payment-agreement"><input type="checkbox" checked={agree} onChange={e => setAgree(e.target.checked)} />전액 환불 조건과 처리 중 이용 제한을 확인했습니다.</label><button disabled={!reason.trim() || !agree || request.isPending} onClick={() => void request.mutateAsync(undefined).then(onClose).catch(() => {})}>{request.isPending ? '요청 중…' : '전액 환불 요청'}</button><ErrorNotice error={request.error} /></Modal>
}
export function PaymentManagement({ child }: { child?: Child }) {
  const [page, setPage] = useState(0), [refund, setRefund] = useState<PaymentRecord | null>(null)
  const subscriptions = useParentQuery(['subscriptions'], signal => paymentApi.subscriptions(signal), !paymentTestMode)
  const history = useParentQuery(['payment-history', page], signal => paymentApi.history(page, signal), !paymentTestMode)
  const [checking, setChecking] = useState(''), [checkError, setCheckError] = useState<unknown>(null)
  const refresh = useParentMutation((orderId: string) => paymentApi.state(orderId))
  if (paymentTestMode) return <p>이 모드는 토스 단건 결제 검증용입니다. 구독·환불 시연은 일반 MSW 모드에서 확인할 수 있습니다.</p>
  const own = subscriptions.data?.items.filter(s => !child || s.childId === child.id) ?? []
  const rows = history.data?.items.filter(p => !child || p.childId === child.id) ?? []
  return <div className="payment-management">
    <section aria-label="현재 구독"><h2>현재 구독</h2><QueryFeedback query={subscriptions} />{subscriptions.data && !own.length && <p>이 자녀의 구독이 없습니다. 무료 이용 조건은 위의 상품 정보를 확인해 주세요.</p>}{own.map(s => <SubscriptionCard key={s.subscriptionId} value={s} refundPending={history.data?.items.some(p => p.childId === s.childId && p.refundRequests.some(r => ['REQUESTED','APPROVED'].includes(r.status)))} />)}</section>
    <section aria-label="결제 및 환불 내역"><h2>결제·취소·환불 내역</h2><p>현재 선택한 자녀의 거래입니다. 다른 자녀의 내역은 상단 자녀 선택을 바꿔 확인해 주세요.</p><QueryFeedback query={history} /><ErrorNotice error={checkError} />
      {history.data && !rows.length && <p>이 페이지에 해당 자녀의 결제 내역이 없습니다.</p>}
      <div className="payment-history">{rows.map(p => <article key={p.orderId} className="payment-panel"><div className="payment-history-heading"><h3>{p.subscription?.product?.name ?? '이용권 결제'}</h3><strong>{won(p.amount)}</strong></div><p>{paymentStateLabel(p)}</p><small>대상 자녀 {child?.nickname ?? p.childId} · 승인일 {date(p.approvedAt)} · 주문번호 {p.orderId}</small>
        {p.refundRequests.map(r => <div key={r.id} className="payment-refund-status"><strong>{refundLabels[r.status] ?? r.status}</strong><p>{r.rejectReason ?? (r.status === 'APPROVED' ? 'PG 취소 결과를 확인하고 있습니다. 환불 완료 상태와 다릅니다.' : r.status === 'FAILED' ? '환불 처리가 실패했습니다. 문의를 통해 처리 상태를 확인해 주세요.' : r.status === 'REQUESTED' ? '사용 내역과 환불 조건을 검토하고 있습니다.' : r.status === 'COMPLETED' ? '전액 환불이 완료되었습니다.' : '환불 처리 내역입니다.')}</p></div>)}
        <div className="payment-actions"><button disabled={refresh.isPending && checking === p.orderId} onClick={() => { setChecking(p.orderId); setCheckError(null); void refresh.mutateAsync(p.orderId).catch(setCheckError) }}>최신 거래 상태 확인</button>{p.status === 'APPROVED' && p.paymentId && !p.refundRequests.some(r => ['REQUESTED', 'APPROVED', 'COMPLETED'].includes(r.status)) && <button onClick={() => setRefund(p)}>환불 요청</button>}</div>
        {p.refundRequests.some(r => r.status === 'FAILED') && <Link to="/parent/support">결제 문의하기</Link>}
      </article>)}</div>
      <nav className="payment-actions" aria-label="거래 내역 페이지"><button disabled={page === 0 || history.isFetching} onClick={() => setPage(p => p - 1)}>이전 거래</button><span>{page + 1}페이지</span><button disabled={history.isFetching || !history.data || history.data.items.length < 20} onClick={() => setPage(p => p + 1)}>다음 거래</button></nav>
    </section>
    {refund && <RefundForm key={refund.orderId} payment={refund} onClose={() => setRefund(null)} />}
  </div>
}
