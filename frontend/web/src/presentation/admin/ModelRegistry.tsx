import { useId, useState } from 'react'
import { adminApi } from '../../data/admin/api.ts'
import { useAdminQuery, useAdminMutation } from '../../data/admin/queries.ts'
import type { ModelVersion } from '../../domain/admin/operations.ts'
import { actionBlockers, EVIDENCE_LABELS, KNOWN_MODEL_SCOPES } from '../../domain/admin/modelRegistration.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import { ModelRegistrationPanel } from './ModelRegistrationPanel.tsx'
import '../service/service.css'
import './modelRegistry.css'

function VersionCard({ version: v }: { version: ModelVersion }) {
  const id = useId()
  const [scopes, setScopes] = useState<string[]>([]), [reason, setReason] = useState('')
  const [approved, setApproved] = useState(false), [reanalysis, setReanalysis] = useState(false)
  const [confirm, setConfirm] = useState(false), [notice, setNotice] = useState('')
  const action = v.status === 'INACTIVE' ? 'rollback' : 'activate'
  const mutation = useAdminMutation(() => adminApi.modelAction(v.id, action, reason.trim(), scopes, reanalysis))
  const record = v.evalResult
  const allowed = (action === 'activate' ? record?.evidence.evaluatedScopes : record?.approval?.scopes) ?? []
  const blockers = v.status === 'ACTIVE' ? ['현재 활성 버전입니다. 다른 버전을 승인하거나 이전 승인 버전으로 되돌릴 수 있습니다.']
    : actionBlockers(v, action, scopes, reason, approved, mutation.isPending)
  const verb = action === 'activate' ? '활성화' : '이 버전으로 되돌리기'
  return <article className="ws-card model-version" aria-label={`${v.name} ${v.version}`}>
    <h2>{v.name} · {v.version}</h2><p>{v.kind} · {v.status} · 승인자 {v.approvedBy ?? '미승인'}</p>
    {v.status === 'ACTIVE' && <p role="status">core 활성화 완료, 로딩은 scoring에서 확인</p>}
    {record ? <>
      <dl className="model-evidence">{Object.entries(EVIDENCE_LABELS).map(([key, label]) => <div key={key}>
        <dt>{label}</dt><dd>{record.evidence[key as keyof typeof EVIDENCE_LABELS]}</dd>
      </div>)}</dl>
      <p>평가 범위: {record.evidence.evaluatedScopes.join(', ')}</p>
      <p>현재 범위: {record.activeScopes.join(', ') || '없음'} · 변경 순번 {record.revision}</p>
      {record.approval && <p>승인 범위: {record.approval.scopes.join(', ')} · {record.approval.reason}</p>}
      <Limitations items={record.evidence.limitations} />
      {record.evidence.evaluatedScopes.filter(s => !(v.status === 'ACTIVE' ? record.activeScopes : scopes).includes(s)).map(s => <p key={s}>{s} · 평가했지만 적용하지 않음</p>)}
    </> : <p>평가 근거가 없는 이전 기록입니다. 활성화할 수 없습니다.</p>}
    <details className="model-stages"><summary>운영 단계와 확인 방법</summary>
      <ol><li>등록: {v.status === 'REGISTERED' ? '등록 완료, 승인 전' : '등록 완료'}</li>
        <li>사전 검사: 이 화면에서 확인할 수 없습니다. 산출물·해시·범위 호환성을 별도로 확인하세요.</li>
        <li>승인·활성화: {v.status === 'ACTIVE' ? 'core 활성화 완료, 로딩은 scoring에서 확인' : v.status === 'INACTIVE' ? '현재 비활성' : '사람 승인 대기'}</li>
        <li>로딩 확인: scoring의 각 replica에서 <code>/internal/versions</code>의 이름·버전·active와 readiness 응답 200을 확인하세요.</li>
        <li>추론 확인: 해당 범위의 합성 입력으로 추론하고 적용 버전과 결과를 확인하세요. <code>scripts/verify_scoring_m2.py</code>를 참고하세요.</li></ol>
    </details>
    {v.status !== 'ACTIVE' && <fieldset className="ws-form" disabled={mutation.isPending}>
      <legend>{action === 'activate' ? '활성화할 범위 선택' : '원 승인 범위에서 복귀할 범위 선택'}</legend>
      {allowed.map(scope => <label className="ws-check" key={scope}><input type="checkbox" checked={scopes.includes(scope)} onChange={e => setScopes(s => e.target.checked ? [...s, scope] : s.filter(x => x !== scope))} />
        <span>{scope}{!KNOWN_MODEL_SCOPES.includes(scope) && ' · 알려진 목록 밖 범위 (경고)'}</span></label>)}
      <label>변경 사유<input aria-label="모델 변경 사유" value={reason} onChange={e => setReason(e.target.value)} /></label>
      {action === 'activate' && <label className="ws-check"><input type="checkbox" checked={approved} onChange={e => setApproved(e.target.checked)} />평가 근거와 선택 범위를 확인하고 활성화를 승인합니다.</label>}
      <label className="ws-check"><input type="checkbox" checked={reanalysis} onChange={e => setReanalysis(e.target.checked)} />재분석을 계획합니다 (작업 실행 아님).</label>
    </fieldset>}
    <button disabled={!!blockers.length} aria-describedby={`${id}-reasons`} onClick={() => setConfirm(true)}>{verb}</button>
    <ul id={`${id}-reasons`}>{blockers.map(message => <li key={message}>{message}</li>)}</ul>
    <ErrorNotice error={mutation.error} /><p role="status">{notice}</p>
    {confirm && <Modal title={`${v.name} ${v.version} ${verb} 확인`} onClose={() => { if (!mutation.isPending) setConfirm(false) }}>
      <p>평가셋: {record?.evidence.datasetId} · {record?.evidence.datasetVersion}</p>
      <p>비교 보고서: {record?.evidence.comparisonReport}</p><p>사람 검토: {record?.evidence.humanReview}</p>
      <Limitations items={record?.evidence.limitations} />
      <p>적용 범위: {scopes.join(', ')}</p><p>변경 사유: {reason}</p><p>재분석 계획: {reanalysis ? '있음 (작업 실행 아님)' : '없음'}</p>
      <p>승인자는 로그인한 계정으로 기록됩니다. 기존 결과는 유지됩니다.</p><ErrorNotice error={mutation.error} />
      <div className="ws-actions"><button disabled={mutation.isPending} onClick={() => setConfirm(false)}>취소</button>
        <button className="cj-primary" disabled={!!blockers.length} onClick={() => void mutation.mutateAsync(undefined).then(() => { setConfirm(false); setScopes([]); setApproved(false); setReason(''); setNotice('서버에서 버전 변경을 확인했습니다. 기존 결과는 유지됩니다.') }).catch(() => {})}>확인 후 {verb}</button></div>
    </Modal>}
  </article>
}
export function Limitations({ items }: { items?: string[] }) {
  return <div><strong>한계·주의</strong>{items?.length ? <ul>{items.map((item, i) => <li key={i}>{item}</li>)}</ul> : <p>기록된 한계·주의 없음</p>}</div>
}
export function ModelRegistry() {
  const q = useAdminQuery(['models'], signal => adminApi.allModels(signal))
  return <div className="svc-page model-registry"><h1>모델·프롬프트 버전</h1>
    <p>평가 근거와 적용 범위를 확인하고 사람이 승인합니다. 등록 후 사전 검사·활성화·로딩·추론을 각각 확인합니다.</p>
    <QueryFeedback query={q} />
    <ModelRegistrationPanel existing={q.data?.items ?? []} listReady={!!q.data && !q.error && !q.isFetching} />
    <section aria-label="등록된 버전" className="ws-stack"><h2>등록된 버전</h2>
      {q.data && !q.error && !q.data.items.length && <p>등록된 버전이 없습니다.</p>}
      {!q.error && q.data?.items.map(v => <VersionCard key={`${v.id}:${v.status}`} version={v} />)}
    </section></div>
}
