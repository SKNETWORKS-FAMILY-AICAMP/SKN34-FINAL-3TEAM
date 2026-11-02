import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { serviceApi } from '../../data/serviceApi.ts'
import { setAccessToken } from '../../data/apiClient.ts'
import { useSession } from '../auth/sessionContext.ts'
import { useParentMutation } from '../../data/parent/queries.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import { GoogleRecheck } from './AccountLifecycle.tsx'
let receipt: { statusToken:string;withdrawalRequestId:string;status:string } | null = null
export function Withdrawal() {
  const navigate=useNavigate()
  const [token,setToken]=useState(''),[confirmed,setConfirmed]=useState(false)
  const precheck=useParentMutation(serviceApi.precheck),withdraw=useMutation({mutationFn:()=>serviceApi.withdraw(token)})
  return <section className="svc-page ws-card ws-form"><h2>회원 탈퇴</h2><p>요청 즉시 로그인과 자녀 이용이 중단됩니다. 자녀 삭제와 거래 기록 보관은 별도로 처리되며 요청을 되돌릴 수 없습니다.</p>
    <button disabled={precheck.isPending} onClick={()=>void precheck.mutateAsync(undefined).catch(()=>{})}>구독·환불 상태 먼저 확인</button>
    {precheck.data&&<><p>진행 중 구독 {precheck.data.activeSubscriptions}건 · 미처리 환불 {precheck.data.unresolvedRefunds}건 · 거래 기록 {precheck.data.retainedTransactionsYears}년 보관</p>{!precheck.data.canWithdraw?<p role="alert">구독과 환불을 먼저 정리해 주세요.</p>:<><GoogleRecheck purpose="WITHDRAWAL" onProof={setToken}/><label className="ws-check"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>계정과 자녀 정보에 미치는 영향을 확인했습니다.</label><button disabled={!confirmed||!token||withdraw.isPending} onClick={()=>void withdraw.mutateAsync(undefined).then(r=>{receipt=r;setAccessToken(null);navigate('/withdrawal-status',{replace:true})}).catch(()=>{})}>탈퇴 요청 확정</button></>}</>}
    <ErrorNotice error={precheck.error??withdraw.error}/>
  </section>
}
export function WithdrawalReceipt() {
  const cache=useQueryClient(),{setSession}=useSession()
  useEffect(()=>{setSession(null);cache.clear()},[cache,setSession])
  const [result,setResult]=useState(receipt),query=useParentMutation(()=>serviceApi.withdrawal(receipt!.statusToken))
  return <main id="class-journal" style={{maxWidth:760,margin:'40px auto',padding:24}}><div className="svc-page"><h1>탈퇴 처리 상태</h1>{result?<><p>요청 번호 {result.withdrawalRequestId}</p><p role="status">{result.status==='COMPLETED'?'탈퇴 처리 완료':'탈퇴 요청 접수 · 자녀 정보 삭제 처리 중'}</p><button disabled={query.isPending} onClick={()=>void query.mutateAsync(undefined).then(r=>setResult({...receipt!,...r})).catch(()=>{})}>처리 상태 확인</button><p>조회 영수증은 이 화면의 메모리에만 보관합니다. 새로고침하면 사라집니다.</p><ErrorNotice error={query.error}/></>:<p>이 화면에 보관된 조회 영수증이 없습니다. 탈퇴 상태를 확인하려면 운영자에게 요청 번호를 알려 주세요.</p>}<Link to="/login">로그인 안내로</Link></div></main>
}
