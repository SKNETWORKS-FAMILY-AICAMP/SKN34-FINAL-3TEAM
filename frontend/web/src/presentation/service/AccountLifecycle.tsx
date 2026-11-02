import { useEffect, useState } from 'react'
import type { Child } from '../../domain/classroom.ts'
import type { DeletionRequest, DeletionScope, ReauthPurpose } from '../../domain/service.ts'
import { serviceApi } from '../../data/serviceApi.ts'
import { useParentQuery, useParentMutation } from '../../data/parent/queries.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import { QueryFeedback } from '../common/Workspace.tsx'
import './service.css'

export function GoogleRecheck({ purpose, childId, scope, onProof }: { purpose: ReauthPurpose; childId?: string; scope?: DeletionScope; onProof: (token: string) => void }) {
  const [challenge,setChallenge]=useState(''),[proof,setProof]=useState<{ token:string; expiresAt:string }|null>(null),[notice,setNotice]=useState('')
  const start=useParentMutation(()=>serviceApi.startReauth({purpose,...(childId?{childId}:{}),...(scope?{scope}:{})}))
  const finish=useParentMutation(()=>serviceApi.finishReauth(challenge))
  useEffect(()=>{if(!proof)return;const timer=setTimeout(()=>{setProof(null);onProof('');setNotice('재확인 시간이 지났습니다. 다시 확인해 주세요.')},Math.max(0,Date.parse(proof.expiresAt)-Date.now()));return()=>clearTimeout(timer)},[proof,onProof])
  function begin() {
    const popup=window.open('about:blank','_blank')
    if(!popup){setNotice('팝업을 허용한 뒤 다시 시도해 주세요.');return}
    popup.opener=null;onProof('');setProof(null);setChallenge('')
    void start.mutateAsync(undefined).then(data=>{const url=new URL(data.authorizationUrl,location.origin);if(url.protocol!=='https:'&&url.origin!==location.origin)throw new Error('재확인 주소가 올바르지 않습니다.');popup.location.href=url.href;setChallenge(data.challengeId);setNotice('Google 확인을 마친 뒤 완료 확인을 눌러 주세요.')}).catch(()=>{popup.close();setNotice('본인 확인을 시작하지 못했습니다.')})
  }
  return <div className="ws-form"><button type="button" onClick={begin} disabled={start.isPending||finish.isPending}>Google 본인 확인</button>{challenge&&!proof&&<button type="button" disabled={finish.isPending} onClick={()=>void finish.mutateAsync(undefined).then(data=>{setProof({token:data.reauthToken,expiresAt:data.expiresAt});onProof(data.reauthToken);setNotice('재확인을 마쳤습니다. 선택한 작업만 한 번 실행할 수 있습니다.')}).catch(()=>{})}>완료 확인</button>}<p role="status">{notice}</p><ErrorNotice error={start.error??finish.error}/></div>
}
export function AccountLifecycle({ child }: { child: Child }) {
  const impact=useParentQuery(['deletion-impact',child.id],signal=>serviceApi.impact(child.id,signal))
  const [choice,setChoice]=useState<'UNLINK'|DeletionScope>('UNLINK'),[token,setToken]=useState(''),[confirmed,setConfirmed]=useState(false),[name,setName]=useState(''),[notice,setNotice]=useState('')
  const [result,setResult]=useState<DeletionRequest|null>(null)
  const action=useParentMutation(async()=>{if(choice==='UNLINK'){await serviceApi.unlink(child.id,token);return null}return serviceApi.deleteChild(child.id,choice,token)})
  const check=useParentMutation(()=>serviceApi.deletion(child.id,result!.deletionRequestId))
  return <div className="svc-page"><section className="ws-card ws-form"><h2>자녀 연결·기록 관리</h2><p>연결 해제와 기록 삭제는 다릅니다. 처리 중인 삭제는 전체 완료로 표시하지 않습니다.</p><QueryFeedback query={impact}/>{impact.data?.actions.map(a=><p key={a.scope}><strong>{a.scope}</strong> · {a.effect}</p>)}<p>거래 기록 보관 기간: {impact.data?.retainedTransactionsYears??'확인 중'}년</p>
    <label>요청할 작업<select value={choice} onChange={e=>{setChoice(e.target.value as typeof choice);setToken('');setConfirmed(false);setName('')}}><option value="UNLINK">보호자 연결 해제</option><option value="PROFILE">프로필과 학습 기록 삭제</option><option value="RECORDS">학습 기록 삭제 (프로필 유지)</option></select></label>
    <GoogleRecheck key={choice+child.id} purpose={choice==='UNLINK'?'CHILD_UNLINK':'CHILD_DELETE'} childId={child.id} scope={choice==='UNLINK'?undefined:choice} onProof={setToken}/>
    <label>확인할 자녀 별명<input value={name} onChange={e=>setName(e.target.value)}/></label><label className="ws-check"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>대상 자녀와 위의 처리 범위를 확인했습니다.</label>
    <button disabled={!impact.data||!token||!confirmed||name!==child.nickname||action.isPending} onClick={()=>void action.mutateAsync(undefined).then(r=>{setResult(r);setToken('');setConfirmed(false);setNotice(r?'삭제 요청을 접수했습니다. 서비스별 처리 상태를 확인해 주세요.':'연결 해제를 확인했습니다.')}).catch(()=>{})}>선택한 작업 요청</button><ErrorNotice error={action.error}/><p role="status">{notice}</p>
    {result&&<div><p>요청 {result.deletionRequestId} · {result.status}</p><p>완료한 서비스: {result.completedServices.join(', ')||'없음'}</p><button disabled={check.isPending} onClick={()=>void check.mutateAsync(undefined).then(setResult).catch(()=>{})}>삭제 처리 상태 확인</button><ErrorNotice error={check.error}/></div>}
  </section></div>
}
