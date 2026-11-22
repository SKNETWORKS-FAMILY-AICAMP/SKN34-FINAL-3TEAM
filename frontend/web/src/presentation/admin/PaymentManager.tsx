import { useRef, useState } from 'react'
import { ArrowDownLeft, ArrowUpRight, ListFilter, ReceiptText, RefreshCw, Search } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { adminServiceApi as api } from '../../data/admin/serviceApi.ts'
import { useAdminMutation, useAdminQuery } from '../../data/admin/queries.ts'
import { hasPermission } from '../../domain/admin/operations.ts'
import type { Permission } from '../../domain/admin/operations.ts'
import type { RefundRequest } from '../../domain/admin/service.ts'
import { refundStatusLabel } from '../../domain/admin/service.ts'
import type { Period } from '../../domain/classroom.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import { Badge, Empty, Inspector, Panel } from './AdminUi.tsx'
import { date, number } from './adminFormatting.ts'
const stateLabel:Record<string,string>={APPROVED:'결제 완료',CONFIRMING:'결제 확인 중',REFUND_REVIEW:'환불 검토',REFUNDED:'환불 완료',FAILED:'실패',CANCELED:'취소'}
export function PaymentManager({ period, permissions }: { period: Period; permissions: Permission[] }) {
  const [params, setParams] = useSearchParams(), raw = params.get('tab'), tab = ['payments', 'reconciliation'].includes(raw ?? '') ? raw! : 'refunds'
  const canView = hasPermission(permissions, 'PAYMENT_VIEW'), canApprove = hasPermission(permissions, 'PAYMENT_REFUND')
  const [page, setPage] = useState(0), [selected, setSelected] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const status = params.get('status') ?? ''
  function setStatus(value: string) {
    const next=new URLSearchParams(params)
    if(value) next.set('status',value); else next.delete('status')
    setParams(next); setPage(0); setSelected(null)
  }
  const payments = useAdminQuery(['payments', period, page], s => api.payments(period, page, s), canView && tab === 'payments')
  const refunds = useAdminQuery(['refunds', page,status], s => api.refunds(page, s,status), canView && tab === 'refunds')
  const reconciliation = useAdminQuery(['reconciliation', period, page], s => api.reconciliation(period, page, s), canView && tab === 'reconciliation')
  const allRows = refunds.error ? [] : refunds.data?.items ?? [], chosen = allRows.find(r => r.id === selected)
  const rows = allRows.filter(r => `${r.id} ${r.paymentId}`.toLowerCase().includes(search.trim().toLowerCase()))
  const active = tab === 'refunds' ? refunds : tab === 'payments' ? payments : reconciliation
  function changeTab(value: string) {
    setPage(0); setSelected(null); setSearch('')
    const next = new URLSearchParams(params); next.set('tab', value); next.delete('status'); setParams(next)
  }
  if (!canView) return <Panel title="결제 조회 권한 필요"><p role="alert">PAYMENT_VIEW 권한이 있어야 거래와 환불 요청을 볼 수 있습니다. 환불 처리에는 PAYMENT_REFUND 권한이 별도로 필요합니다.</p></Panel>
  return <div className="ad-payment-workbench">
    <div className="ad-view-tabs" aria-label="결제 업무">
      <button aria-pressed={tab === 'refunds'} onClick={() => changeTab('refunds')}><ArrowDownLeft size={17} aria-hidden="true" />환불 요청</button>
      <button aria-pressed={tab === 'payments'} onClick={() => changeTab('payments')}><ReceiptText size={17} aria-hidden="true" />거래 내역</button>
      <button aria-pressed={tab === 'reconciliation'} onClick={() => changeTab('reconciliation')}><ListFilter size={17} aria-hidden="true" />PG 대조</button>
    </div>
    <section className="ad-data-surface" aria-label={tab === 'refunds' ? '환불 요청 목록' : tab === 'payments' ? '거래 내역 목록' : 'PG 대조 목록'}>
      <div className="ad-data-toolbar">
        <div><h2>{tab === 'refunds' ? '환불 요청' : tab === 'payments' ? '거래 내역' : '내부 기록·PG 상태 대조'}</h2><p>{tab === 'refunds' ? '상태는 접수일 전체에 적용 · 번호는 현재 페이지에서 검색' : '선택한 조회 기간'}</p></div>
        <button aria-label="상태 새로고침" disabled={active.isFetching} onClick={() => void active.refetch()}><RefreshCw size={15} aria-hidden="true" />새로고침</button>
      </div>
      {tab === 'refunds' && <div className="ad-list-filters">
        <label className="ad-inline-search"><Search size={16} aria-hidden="true" /><input aria-label="현재 페이지 환불 검색" placeholder="요청·결제 번호 검색" value={search} onChange={e => setSearch(e.target.value)} /></label>
        <label>상태<select aria-label="환불 상태 필터" value={status} onChange={e => setStatus(e.target.value)}><option value="">전체 상태</option>{Object.entries(refundStatusLabel).map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label>
        {(search || status) && <button className="ad-link-button" onClick={() => {setSearch(''); setStatus('')}}>필터 초기화</button>}
      </div>}
      <QueryFeedback query={active} />
      {tab === 'refunds' ? <>
        <div className="ad-table-wrap"><table className="ad-table"><thead><tr><th>환불 요청</th><th>처리 상태</th><th className="num">환불 금액</th><th>접수 시각</th><th>검토</th></tr></thead><tbody>{rows.map(r => <tr key={r.id} className={r.id === selected ? 'is-selected' : ''}>
          <td><strong className="ad-record-id" title={r.id}>{r.id}</strong><small className="ad-record-id" title={r.paymentId}>{r.paymentId}</small></td>
          <td><Badge active={r.status === 'COMPLETED'} tone={r.status === 'FAILED' ? 'danger' : undefined}>{refundStatusLabel[r.status] ?? r.status}</Badge></td>
          <td className="num"><strong className="ad-money">{number(r.amount)}<small>원</small></strong></td><td>{date(r.createdAt)}</td>
          <td><button className="ad-link-button" aria-label={`${r.id} 환불 선택`} onClick={() => setSelected(r.id)}>검토<ArrowUpRight size={14} aria-hidden="true" /></button></td>
        </tr>)}</tbody></table></div>{refunds.data && !rows.length && !refunds.error && <Empty>조건에 맞는 환불 요청이 없습니다.</Empty>}
      </> : tab === 'payments' ? <>
        <div className="ad-table-wrap"><table className="ad-table"><thead><tr><th>주문·자녀 번호</th><th className="num">결제 금액</th><th>결제 상태</th><th>이용 권한</th><th>승인 시각</th></tr></thead><tbody>{!payments.error && payments.data?.items.map(r => <tr key={r.orderId}><td><strong className="ad-record-id" title={r.orderId}>{r.orderId}</strong><small className="ad-record-id" title={r.childId}>{r.childId}</small></td><td className="num"><strong className="ad-money">{number(r.amount)}<small>원</small></strong></td><td><Badge active={r.status === 'APPROVED'} tone={r.status === 'FAILED' ? 'danger' : undefined}>{stateLabel[r.status] ?? r.status}</Badge></td><td>{r.entitlementStatus ?? '미확인'}</td><td>{date(r.approvedAt)}</td></tr>)}</tbody></table></div>{payments.data && !payments.data.items.length && !payments.error && <Empty />}
      </> : <>
        <div className="ad-table-wrap"><table className="ad-table"><thead><tr><th>주문번호</th><th>내부 기록</th><th>PG 기록</th><th>대조 결과</th><th>조회 출처</th></tr></thead><tbody>{!reconciliation.error && reconciliation.data?.items.map(r => <tr key={r.orderId}><td className="ad-record-id" title={r.orderId}>{r.orderId}</td><td>{r.localStatus ?? '미확인'}</td><td>{r.pgStatus ?? '미확인'}</td><td><Badge active={r.result === 'MATCH'} tone={r.result === 'MISMATCH' ? 'danger' : undefined}>{{MATCH:'일치',MISMATCH:'불일치',UNKNOWN:'확인 불가',MISSING_PG:'PG 기록 없음',NO_PG_ATTEMPT:'PG 요청 없음'}[r.result] ?? r.result}</Badge></td><td>{r.source}</td></tr>)}</tbody></table></div>{reconciliation.data && !reconciliation.data.items.length && !reconciliation.error && <Empty />}<p className="ad-note">대조 요청은 서버의 PG 조회를 실행합니다. 조회 실패를 일치나 빈 결과로 바꾸지 않습니다.</p>
      </>}
      <div className="ad-list-footer"><span>{page + 1}페이지 · 최대 20건</span><div><button disabled={!page || active.isFetching} onClick={() => {setPage(p => p-1); setSelected(null)}}>이전 페이지</button><button disabled={active.isFetching || !!active.error || (active.data?.items.length ?? 0) < 20} onClick={() => {setPage(p => p+1); setSelected(null)}}>다음 페이지</button></div></div>
    </section>
    {chosen && tab === 'refunds' && <Inspector title="환불 검토" onClose={() => setSelected(null)}><div className="ad-inspector-lead"><span>{refundStatusLabel[chosen.status] ?? chosen.status}</span><strong>{number(chosen.amount)}<small>원</small></strong><p className="ad-record-id">{chosen.id}</p></div><RefundReview key={`${chosen.id}:${chosen.status}`} request={chosen} canApprove={canApprove} /></Inspector>}
  </div>
}
function RefundReview({request,canApprove}:{request:RefundRequest;canApprove:boolean}) {
 const [checks,setChecks]=useState([false,false,false]),[reason,setReason]=useState(''),[confirm,setConfirm]=useState<'approve'|'reject'|null>(null),[message,setMessage]=useState('')
 const receipt=useRef<string|null>(null)
 const mutation=useAdminMutation((action:'approve'|'reject')=>action==='approve'?api.approve(request.id,receipt.current??(receipt.current=crypto.randomUUID())):api.reject(request.id,reason.trim()))
 const pending=request.status==='APPROVED',decidable=['REQUESTED','FAILED'].includes(request.status)
 return <Panel title="환불 조건 확인"><dl className="ad-facts"><dt>결제 번호</dt><dd>{request.paymentId}</dd><dt>금액</dt><dd>{number(request.amount)}원 · 전액</dd><dt>요청 사유</dt><dd>{request.reason}</dd><dt>상태</dt><dd>{refundStatusLabel[request.status]??request.status}</dd><dt>사용 이력 확인 시각</dt><dd>{date(request.usageVerifiedAt)}</dd><dt>PG 상태</dt><dd>{request.pgStatus??'미확인'}</dd></dl>
 <p className="ad-note">결제 7일 이내·프리미엄 미사용 여부와 금액은 서버가 승인 시 다시 검증합니다. 이 화면은 별도의 적격 여부를 추정하지 않습니다.</p>
 {decidable&&<><div className="ad-checklist">{['대상 결제를 확인했습니다.','금액과 환불 정책을 확인했습니다.','원문 열람 없이 요청 사유와 처리 영향을 확인했습니다.'].map((label,i)=><label key={label}><input type="checkbox" checked={checks[i]} onChange={e=>setChecks(checks.map((v,n)=>n===i?e.target.checked:v))}/>{label}</label>)}</div><label className="ws-form">반려 사유 (반려 시 필수)<textarea aria-label="환불 반려 사유" maxLength={200} value={reason} onChange={e=>setReason(e.target.value)}/></label><div className="ws-actions"><button className="ad-danger" disabled={!canApprove||!reason.trim()||mutation.isPending} onClick={()=>setConfirm('reject')}>반려</button><button className="cj-primary" disabled={!canApprove||request.status!=='REQUESTED'||!request.usageVerifiedAt||!checks.every(Boolean)||mutation.isPending} onClick={()=>setConfirm('approve')}>환불 승인 요청</button></div>
 {confirm&&<div className="ad-note"><p>{number(request.amount)}원 전액 환불 요청을 {confirm==='approve'?'승인':'반려'}하시겠습니까?</p><button className={confirm==='reject'?'ad-danger':undefined} disabled={mutation.isPending} onClick={()=>void mutation.mutateAsync(confirm).then(r=>{setConfirm(null);setMessage(r.status==='COMPLETED'?'PG 취소 확인 후 환불을 완료했습니다.':r.status==='APPROVED'?'승인되었습니다. PG 취소 확인 중이며 아직 완료되지 않았습니다.':'반려 결과를 저장했습니다.')}).catch(()=>{})}>처리 확정</button><button disabled={mutation.isPending} onClick={()=>setConfirm(null)}>취소</button></div>}</>}
 {!canApprove&&<p className="ad-note">조회 전용입니다. 환불 승인·반려에는 PAYMENT_REFUND 권한이 필요합니다.</p>}
 {pending&&<p role="status">승인 후 PG 취소 확인 중입니다. 완료로 표시하지 않습니다. 상태 새로고침으로 확인해 주세요.</p>}
 {request.status==='COMPLETED'&&<p>PG 취소 확인 완료</p>}{request.rejectReason&&<p>반려 사유 · {request.rejectReason}</p>}
 <p role="status">{message}</p><ErrorNotice error={mutation.error}/></Panel>
}
