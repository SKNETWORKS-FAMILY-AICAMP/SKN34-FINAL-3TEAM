import { useState } from 'react'
import { adminApi } from '../../data/admin/api.ts'
import { useAdminQuery, useAdminMutation } from '../../data/admin/queries.ts'
import type { EvaluationEvidence } from '../../domain/admin/operations.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import '../service/service.css'
const labels = { datasetId:'평가셋 ID',datasetVersion:'평가셋 버전',baselineVersion:'비교 기준 버전',comparisonReport:'비교 보고서',trainingEvaluationSeparation:'학습·평가 분리 근거',quoteAccuracy:'인용 정확성 근거',calculationAccuracy:'계산 정확성 근거',humanReview:'사람 검토 기록' } as const
export function ModelRegistry() {
  const q = useAdminQuery(['models'], signal => adminApi.models(signal))
  const [name,setName]=useState(''),[version,setVersion]=useState(''),[kind,setKind]=useState('PROMPT')
  const [refId,setRefId]=useState(''),[artifact,setArtifact]=useState('')
  const [evidence,setEvidence]=useState<Record<string,string>>({}),[scopeText,setScopeText]=useState(''),[reason,setReason]=useState('')
  const [approved,setApproved]=useState(false),[reanalysis,setReanalysis]=useState(false),[notice,setNotice]=useState('')
  const scopes=scopeText.split(/[\n,]/).map(s=>s.trim()).filter(Boolean)
  const validScopes=scopes.length>0 && new Set(scopes).size===scopes.length && scopes.every(s=>s.length<=200 && /^[a-z0-9][a-z0-9._:/-]*$/.test(s))
  const register=useAdminMutation(()=>adminApi.registerModel({kind,name,version,...(kind==='RUBRIC'?{refId}:{}),...(artifact?{artifactUri:artifact}:{}),evaluation:{...evidence,evaluatedScopes:scopes} as EvaluationEvidence}))
  const action=useAdminMutation(({id,action}:{id:string;action:'activate'|'rollback'})=>adminApi.modelAction(id,action,reason,scopes,reanalysis))
  return <div className="svc-page"><h1>모델·프롬프트 버전</h1><p>평가 근거와 적용 범위를 확인하고 사람이 승인합니다. 재분석 계획 표시는 기존 결과를 다시 계산하지 않습니다.</p><QueryFeedback query={q} />
    <section className="ws-card ws-form"><h2>적용 범위와 변경 사유</h2><label>범위 키 (쉼표 또는 줄바꿈)<textarea aria-label="적용 범위" value={scopeText} onChange={e=>setScopeText(e.target.value)} placeholder="judgment/grade-3/narrative"/></label><label>변경 사유<input aria-label="모델 변경 사유" value={reason} onChange={e=>setReason(e.target.value)} /></label><label className="ws-check"><input type="checkbox" checked={approved} onChange={e=>setApproved(e.target.checked)}/>평가 근거와 선택 범위를 확인하고 활성화를 승인합니다.</label><label className="ws-check"><input type="checkbox" checked={reanalysis} onChange={e=>setReanalysis(e.target.checked)}/>재분석을 계획합니다 (작업 실행 아님).</label></section>
    {q.data?.items.map(v=><article className="ws-card" key={v.id}><h2>{v.name} · {v.version}</h2><p>{v.kind} · {v.status} · 승인자 {v.approvedBy??'미승인'}</p>
      {v.evalResult ? <><dl>{Object.entries(labels).map(([key,label])=><div key={key}><dt>{label}</dt><dd>{v.evalResult!.evidence[key as keyof typeof labels]}</dd></div>)}</dl><p>평가 범위: {v.evalResult.evidence.evaluatedScopes.join(', ')}</p><p>현재 범위: {v.evalResult.activeScopes.join(', ')||'없음'} · 변경 순번 {v.evalResult.revision}</p>{v.evalResult.approval && <p>승인 범위: {v.evalResult.approval.scopes.join(', ')} · {v.evalResult.approval.reason}</p>}</> : <p>평가 근거가 없는 이전 기록입니다. 활성화할 수 없습니다.</p>}
      <div className="ws-actions">{(['activate','rollback'] as const).map(a=><button key={a} disabled={!v.evalResult || !validScopes || !reason.trim() || action.isPending || (a==='activate' ? v.status!=='REGISTERED'||!approved : v.status!=='INACTIVE'||!v.evalResult.approval)} onClick={()=>void action.mutateAsync({id:v.id,action:a}).then(()=>setNotice('서버에서 버전 변경을 확인했습니다. 기존 결과는 유지됩니다.')).catch(()=>{})}>{a==='activate'?'활성화':'이 버전으로 되돌리기'}</button>)}</div>
    </article>)}
    <ErrorNotice error={action.error}/><p role="status">{notice}</p>
    <form className="ws-card ws-form" onSubmit={e=>{e.preventDefault();void register.mutateAsync(undefined).then(()=>setNotice('평가 기록과 함께 새 버전을 등록했습니다.')).catch(()=>{})}}><h2>새 버전 등록</h2>
      <label>종류<select aria-label="버전 종류" value={kind} onChange={e=>setKind(e.target.value)}>{['RUBRIC','MODEL','PROMPT','GENERATION'].map(k=><option key={k}>{k}</option>)}</select></label>
      <label>이름<input aria-label="모델 이름" required value={name} onChange={e=>setName(e.target.value)}/></label><label>버전<input aria-label="모델 버전" required value={version} onChange={e=>setVersion(e.target.value)}/></label>
      {kind==='RUBRIC'&&<label>기준표 원본 UUID<input required value={refId} onChange={e=>setRefId(e.target.value)}/></label>}
      <label>아티팩트 주소 (선택)<input value={artifact} onChange={e=>setArtifact(e.target.value)}/></label>
      {Object.entries(labels).map(([key,label])=><label key={key}>{label}<input required aria-label={label} value={evidence[key]??''} onChange={e=>setEvidence(v=>({...v,[key]:e.target.value}))}/></label>)}
      <p>위의 적용 범위를 평가 범위로 등록합니다. 승인자는 로그인한 계정으로 기록되며 직접 입력하지 않습니다.</p><button disabled={!validScopes||register.isPending} className="cj-primary">버전 등록</button><ErrorNotice error={register.error}/>
    </form></div>
}
