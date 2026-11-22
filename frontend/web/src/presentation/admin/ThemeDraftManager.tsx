import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { adminRetentionApi as api } from '../../data/admin/retentionApi.ts'
import { useAdminMutation, useAdminQuery } from '../../data/admin/queries.ts'
import { ApiError } from '../../data/apiClient.ts'
import { calendarPeriods, thinkingLabels, inputLabels } from '../../domain/classroom.ts'
import { THEME_GRADE_LABELS } from '../../domain/admin/retention.ts'
import type { ThemeGrade } from '../../domain/admin/retention.ts'
import { THEME_SCENES, failureStageLabels, regenButtonLabels, regenConfirmText, regenKindsOf, regenTargetLabel,
  sceneLabels, themeDraftActions, themeDraftLabels, themeDraftSourceLabels } from '../../domain/admin/themeDrafts.ts'
import type { RegenKind, RegenTarget, ThemeSceneName } from '../../domain/admin/themeDrafts.ts'
import type { SceneHistory } from '../../domain/admin/sceneVersions.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import { Badge, DraftWorkflow, Empty, Panel } from './AdminUi.tsx'
import { date as when } from './adminFormatting.ts'
import { ThemeRequest } from './ThemeRequest.tsx'
import { ThemeSceneReview } from './ThemeSceneReview.tsx'
import type { SceneView } from './ThemeSceneReview.tsx'
import './theme-workspace.css'

const POLL_MS = 5000
const PAGE_SIZE = 20
const days = THEME_SCENES.filter(s => s !== 'INTRO' && s !== 'OUTRO')
function weekOf(value: string | null) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return ''
  const day = new Date(value + 'T00:00:00Z')
  if (Number.isNaN(day.getTime()) || day.toISOString().slice(0, 10) !== value) return ''
  return calendarPeriods(day).thisWeek.from
}
type Change = (values: Record<string, string | null>, replace?: boolean) => void

export function ThemeDraftManager() {
  const [params, setParams] = useSearchParams()
  const [notice, setNotice] = useState('')
  const selected = params.get('draftId') || ''
  const grade = Object.hasOwn(THEME_GRADE_LABELS, params.get('grade') ?? '') ? params.get('grade') as ThemeGrade : ''
  const weekStart = weekOf(params.get('weekStart'))
  const source = params.get('source') || '', status = params.get('status') || ''
  const comparisonPending = params.get('comparisonPending') === 'true'
  const page = Math.max(0, Number(params.get('page')) || 0)
  const list = useAdminQuery(['theme-drafts', grade, weekStart, source, status, comparisonPending, page], signal =>
    api.themeDrafts({ grade, weekStart, source, status, hideDiscarded: status ? '' : 'true',
      comparisonPending: comparisonPending ? 'true' : '', page: String(page), size: String(PAGE_SIZE) }, signal),
    !selected, data => data?.items.some(d => d.status === 'GENERATING') ? POLL_MS : false)
  function change(values: Record<string, string | null>, replace = false) {
    setParams(previous => {
      const next = new URLSearchParams(previous)
      for (const [k, value] of Object.entries(values)) {
        if (value) next.set(k, value)
        else next.delete(k)
      }
      return next
    }, { replace })
  }
  function choose(id: string) {change({draftId:id, scene:null, view:null, generationId:null, request:null})}
  function leave(archive = false) {
    setNotice('')
    change({ draftId:null, scene:null, view:null, generationId:null, ...(archive ? {status:'DISCARDED', comparisonPending:null, page:null} : {}) })
  }
  if (selected) return <ThemeDraftDetail key={selected} draftId={selected} params={params} change={change} leave={leave}
    choose={choose} requestedNotice={notice}/>
  const rows = list.error ? [] : list.data?.items ?? []
  const hasNext = list.data?.totalElements == null ? rows.length >= PAGE_SIZE : (page + 1) * PAGE_SIZE < list.data.totalElements
  return <div className="ad-theme-drafts tw-desk">
    <DraftWorkflow>검사에 통과한 초안을 채택하면 미션 5개와 테마가 작성 중으로 만들어집니다. 미션 검토와 주간 게시를 마치면 학생에게 제공됩니다.</DraftWorkflow>
    <ThemeRequest initialGrade={grade || 'G3'} initialWeek={weekStart} expanded={params.get('request') === '1'}
      onRequested={draft => {setNotice('생성 요청을 접수했습니다. 처리 상태를 확인해 주세요.');choose(draft.draftId)}}/>
    <Panel title={status === 'DISCARDED' ? '버림 이력' : '테마 초안 목록'} action={<div className="ws-actions">
      <button onClick={() => change({ status:status === 'DISCARDED' ? null : 'DISCARDED', comparisonPending:null, page:null })}>{status === 'DISCARDED' ? '검수 목록' : '버림 이력'}</button>
      <button onClick={() => void list.refetch()}>목록 다시 확인</button></div>}>
      <div className="ad-toolbar tw-filters">
        <label>학년<select aria-label="테마 초안 학년" value={grade} onChange={e => change({grade:e.target.value,page:null})}><option value="">전체</option>{Object.entries(THEME_GRADE_LABELS).map(([v,l]) => <option value={v} key={v}>{l}</option>)}</select></label>
        <label>생성 기준 주<input type="date" aria-label="테마 초안 생성 기준 주" value={weekStart} onChange={e => change({weekStart:weekOf(e.target.value),page:null})}/></label>
        <label>상태<select aria-label="테마 초안 상태" value={status} onChange={e => change({status:e.target.value,page:null,comparisonPending:null})}><option value="">전체 검수 상태</option>{Object.entries(themeDraftLabels).map(([v,l]) => <option value={v} key={v}>{l}</option>)}</select></label>
        <label>출처<select aria-label="테마 초안 출처" value={source} onChange={e => change({source:e.target.value,page:null})}><option value="">전체</option>{Object.entries(themeDraftSourceLabels).map(([v,l]) => <option value={v} key={v}>{l}</option>)}</select></label>
        <label className="tw-check"><input type="checkbox" checked={comparisonPending} onChange={e => change({comparisonPending:e.target.checked ? 'true' : null, status:e.target.checked ? 'READY' : status, page:null})}/>영상 비교 대기</label>
      </div>
      <QueryFeedback query={list}/>
      {!!rows.length && <div className="ad-table-wrap"><table className="ad-table"><thead><tr><th>테마</th><th>학년</th><th>생성 기준 주</th><th>출처</th><th>상태</th><th>검수</th></tr></thead><tbody>
        {rows.map(d => <tr key={d.draftId}><td><strong>{d.draft?.theme?.title || d.input.topic || '주간 테마 초안'}</strong><small>{when(d.createdAt)}</small></td>
          <td>{d.grade ? THEME_GRADE_LABELS[d.grade] : '—'}</td><td>{d.weekStart ?? '—'}</td><td>{d.source ? themeDraftSourceLabels[d.source] : '—'}{d.input.regenerate ? ' · 부분' : ''}</td>
          <td><Badge active={d.status === 'READY'}>{themeDraftLabels[d.status]}</Badge></td><td><button aria-label={(d.weekStart ?? d.draftId)+' '+(d.grade ? THEME_GRADE_LABELS[d.grade] : '')+' 초안 열기'} onClick={() => {setNotice('');choose(d.draftId)}}>열기</button></td></tr>)}
      </tbody></table></div>}
      {list.data && !list.error && !rows.length && <Empty>조건에 맞는 테마 초안이 없습니다.</Empty>}
      {list.data && !list.error && <nav className="ws-actions" aria-label="테마 초안 목록 페이지"><button disabled={!page || list.isFetching} onClick={() => change({page:String(page - 1)})}>이전 페이지</button>
        <span>{page+1}쪽{list.data.totalElements != null && ' · 전체 '+list.data.totalElements+'건'}</span><button disabled={!hasNext || list.isFetching} onClick={() => change({page:String(page+1)})}>다음 페이지</button></nav>}
    </Panel>
  </div>
}

type Pending = { action:'adopt'|'discard'|'regenerate'; target?:RegenTarget; sourceId?:string; plannedWeek?:string|null }
function ThemeDraftDetail({ draftId, params, change, leave, choose, requestedNotice }: {
  draftId:string; params:URLSearchParams; change:Change; leave:(archive?:boolean)=>void; choose:(id:string)=>void; requestedNotice:string
}) {
  const navigate = useNavigate(), cache = useQueryClient()
  const heading = useRef<HTMLDivElement>(null), singleFocus = useRef(false)
  const [still,setStill] = useState(false), [confirm,setConfirm] = useState<Pending|null>(null)
  const [notice,setNotice] = useState(requestedNotice), actionLock = useRef(false)
  const scene = THEME_SCENES.find(s=>s===params.get('scene')?.toUpperCase()) ?? 'INTRO'
  const rawView = params.get('view')
  const view: SceneView = rawView === 'compare' || rawView === 'missions' || (rawView === 'mission' && days.some(d=>d===scene)) ? rawView : 'scene'
  const generationId = params.get('generationId') || ''
  const detail = useAdminQuery(['theme-draft',draftId], signal=>api.themeDraft(draftId,signal),true,data=>data?.status==='GENERATING'?POLL_MS:false)
  const work = useAdminQuery(['theme-draft',generationId], signal=>api.themeDraft(generationId,signal),!!generationId,data=>data?.status==='GENERATING'?POLL_MS:false)
  const handled = useRef('')
  useEffect(()=>{
    const generated = work.data
    if (!generationId || !generated || generated.status==='GENERATING' || handled.current===generationId) return
    handled.current=generationId
    void cache.invalidateQueries({queryKey:['admin','theme-scene-history',draftId]})
    void cache.invalidateQueries({queryKey:['admin','theme-draft',draftId]})
    void cache.invalidateQueries({queryKey:['admin','theme-drafts']})
  },[work.data,generationId,cache,draftId])
  useEffect(()=>{
    if(singleFocus.current && view==='scene'){
      singleFocus.current=false
      const target=heading.current?.querySelector<HTMLElement>('.tw-single video') ?? heading.current?.querySelector<HTMLElement>('.tw-stage')
      target?.focus()
    }
  },[view,scene])
  const act = useAdminMutation(async (p:Pending)=>{
    if(p.action==='adopt')return {themeId:(await api.adoptThemeDraft(draftId,p.plannedWeek)).themeId}
    return {draft:await api.themeDraftAction(p.sourceId??draftId,p.action,p.target?[p.target]:undefined,p.plannedWeek)}
  })
  function run(p:Pending) {
    if(actionLock.current)return
    actionLock.current=true;setNotice('')
    void act.mutateAsync(p).then(result=>{
      setConfirm(null)
      if(result.themeId){navigate('/admin/themes?themeId='+encodeURIComponent(result.themeId));return}
      if(!result.draft)return
      if(p.action==='discard'){
        cache.setQueryData(['admin','theme-draft',draftId],result.draft)
        setNotice('초안을 버렸습니다. 버림 이력에서 다시 볼 수 있습니다.')
      }else if(p.target){
        change({generationId:result.draft.draftId},true)
        setNotice(regenTargetLabel(p.target)+' 다시 만들기 요청을 접수했습니다.')
      }else choose(result.draft.draftId)
    }).catch((error:unknown)=>{
      if(error instanceof ApiError && error.problem.status===409){setConfirm(null);void detail.refetch()}
    }).finally(()=>{actionLock.current=false})
  }
  function route(s:ThemeSceneName, mode:SceneView) {
    singleFocus.current = mode === 'scene' && view === 'mission'
    change({scene:s,view:mode==='scene'?null:mode})
  }
  const d = detail.error ? undefined : detail.data
  const [missionOrigin,setMissionOrigin] = useState<SceneView>('missions')
  function open(s:ThemeSceneName, mode:SceneView) {
    if(mode==='mission')setMissionOrigin(view==='mission'?'missions':view)
    route(s,mode)
  }
  if(!d)return <Panel title="초안 상세" action={<button onClick={()=>leave()}>검수 목록으로</button>}><QueryFeedback query={detail}/></Panel>
  const theme=d.draft?.theme, allowed=themeDraftActions(d.status), readOnly=d.weekLocked || d.status==='ADOPTED' || d.status==='DISCARDED'
  const mission=d.draft?.missions.find(m=>m.day===scene), plan=theme?.days.find(p=>p.day===scene)
  const lines=d.draft?.dialogues.find(v=>v.day===scene)?.lines ?? []
  const pendingChild=!!generationId && (!work.data || work.data.status==='GENERATING') && !work.error
  const regenTargets=d.regenerableTargets.filter(t=>regenKindsOf(scene).some(k=>t===k+':'+scene))
  const context=(d.grade ? THEME_GRADE_LABELS[d.grade]+' · ' : '')+(d.weekStart ?? '생성 주 미확인')
  const blocked=act.isPending || !!confirm
  const actionText=confirm?.target?regenTargetLabel(confirm.target)+' 다시 만들기':confirm?.action==='discard'?'초안 버리기':confirm?.action==='adopt'?'채택':'새 초안 생성'
  return <div className="tw-desk" ref={heading}>
    <div className="tw-top"><button className="ad-link-button" onClick={()=>leave()}>← 검수 목록으로</button>
      {d.status==='DISCARDED' && <button onClick={()=>leave(true)}>버림 이력 보기</button>}</div>
    {notice && <p role="status">{notice}</p>}
    <Panel title={theme?.title?'초안 상세 · '+theme.title:'초안 상세'} action={<button disabled={detail.isFetching} onClick={()=>void detail.refetch()}>다시 확인</button>}>
      <div className="tw-meta"><Badge active={d.status==='READY'}>{themeDraftLabels[d.status]}</Badge><span>{context}</span>
        {d.plannedWeek && <span>편성 주 {d.plannedWeek}</span>}<span>{d.source?themeDraftSourceLabels[d.source]:'출처 미확인'}</span></div>
      {d.status==='GENERATING' && <p role="status">생성 중입니다. 5초마다 다시 확인합니다.</p>}
      {d.status==='ADOPTED' && d.themeId && <Link to={'/admin/themes?themeId='+encodeURIComponent(d.themeId)}>채택한 테마 보기</Link>}
      {d.status==='DISCARDED' && <p>버린 초안입니다. 보존된 장면과 요일 미션을 열어볼 수 있습니다.</p>}
      {d.input.regenerate && <p>{d.input.regenerate.targets.map(regenTargetLabel).join(', ')}만 다시 만듦 · <button className="ad-link-button" onClick={()=>choose(d.input.regenerate!.baseDraftId)}>원래 초안 열기</button></p>}
      {d.checkResults.some(v=>v.failures.length>0) && <div className="ad-note"><h3>검사 실패</h3>{d.checkResults.flatMap(r=>r.failures.map((f,i)=><p key={r.attempt+'-'+i}>{r.attempt}회차 · {failureStageLabels[f.stage]??f.stage}: {f.reasons.join(' / ')}</p>))}</div>}
      {d.draft?.warnings.map((w,i)=><p key={i} className="ad-note">{failureStageLabels[w.stage]??w.stage} · {w.reason}</p>)}
      <details><summary>생성 정보와 요청 조건</summary>
        <dl className="ad-draft-meta"><dt>생성 시도</dt><dd>{d.attempts} / {d.maxAttempts || '—'} {d.failureCode}</dd>
        <dt>주제</dt><dd>{d.input.topic??'자동'}</dd><dt>생성 버전</dt><dd>{[d.versions.prompt,d.versions.model].filter(Boolean).join(' · ')||'—'}</dd>
        <dt>초안 식별자</dt><dd>{draftId}</dd></dl>
        {d.input.missions.map((m,i)=><p key={i}>{m.thinkingType?thinkingLabels[m.thinkingType]:'유형 미확인'} · {m.inputType?inputLabels[m.inputType]:'입력 방식 미확인'} · {m.standardCodes.join(', ')}</p>)}
      </details>
    </Panel>
    {generationId && <div className="ad-note" aria-live="polite"><QueryFeedback query={work}/>
      {work.data && <span>부분 생성 · {themeDraftLabels[work.data.status]}{work.data.failureCode?' · '+work.data.failureCode:''}</span>}
      <button className="ad-link-button" onClick={()=>choose(generationId)}>요청한 초안 열기</button></div>}
    {d.draft ? <Panel title="주간 테마 검수">
      <div className="tw-switch"><button aria-pressed={view!=='missions'&&view!=='mission'} onClick={()=>route(scene,'scene')}>주간 장면</button>
        <button aria-pressed={view==='missions'||view==='mission'} onClick={()=>route(scene,'missions')}>요일별 미션</button></div>
      {(view==='missions'||view==='mission') && <ul className="tw-missions">{days.map(day=>{
        const item=d.draft!.missions.find(m=>m.day===day)
        return <li key={day}><span>{sceneLabels[day]}</span><strong>{item?.title || '생성된 미션 없음'}</strong><button onClick={()=>open(day,'mission')}>내용 보기</button></li>
      })}</ul>}
      <div hidden={view==='missions' || view==='mission'} className="tw-stage" tabIndex={-1}>
        <nav className="tw-scenes" aria-label="주간 장면">{THEME_SCENES.map(s=><button key={s} aria-current={s===scene?'step':undefined} onClick={()=>route(s,'scene')}>{sceneLabels[s]}</button>)}</nav>
        <label className="tw-check"><input type="checkbox" checked={still} onChange={e=>setStill(e.target.checked)}/>움직임 끄기 (정지 그림만)</label>
        <ThemeSceneReview draft={d} scene={scene} view={view} open={open} still={still}/>
        <section className="tw-story" aria-label={sceneLabels[scene]+' 이야기'}>
          {scene==='INTRO'||scene==='OUTRO'?<p>{(scene==='INTRO'?theme?.intro:theme?.outro)||'이야기 없음'}</p>:<><h4>{mission?.title||sceneLabels[scene]+' 문제'}</h4><p>{mission?.question}</p></>}
          {theme?.bigQuestion && <details><summary>큰 질문과 엔딩 정답</summary><p>{theme.bigQuestion}</p><p>후보 {theme.candidates.join(', ')} · 정답 {theme.answer}</p></details>}
        </section>
        {!readOnly && allowed.regenerate && <div className="ws-actions">{regenTargets.map(t=><button key={t} disabled={blocked||pendingChild}
          aria-label={sceneLabels[scene]+' '+regenButtonLabels[t.split(':')[0] as RegenKind]} onClick={()=>{
            const selected=cache.getQueryData<SceneHistory>(['admin','theme-scene-history',draftId,scene])?.selectedVersionId
            setConfirm({action:'regenerate',target:t,sourceId:selected??draftId})
          }}>{regenButtonLabels[t.split(':')[0] as RegenKind]}</button>)}</div>}
      </div>
    </Panel> : d.status!=='GENERATING' && <p>생성 결과가 없습니다. 실패 사유를 확인해 주세요.</p>}
    {view==='mission' && d.draft && <Modal title={mission?.title||sceneLabels[scene]+' 미션'} onClose={()=>route(scene,missionOrigin==='mission'?'missions':missionOrigin)}>
      <p>{sceneLabels[scene]} 미션{mission?.thinkingType?' · '+thinkingLabels[mission.thinkingType]:''}</p>
      <h3>학생에게 보일 질문</h3><p>{mission?.question||'생성된 질문이 없습니다.'}</p>{mission?.guide && <p>{mission.guide}</p>}
      {lines.length>0 && <><h3>문제 전 대화</h3><ul>{lines.map((l,i)=><li key={i}><b>{l.speaker}</b> {l.text}</li>)}</ul></>}
      {plan?.clue && <><h3>문제 마무리 뒤 단서</h3><p>{plan.clue}</p>{plan.rulesOut.length>0 && <p>빠지는 후보 · {plan.rulesOut.join(', ')}</p>}</>}
      <div className="ws-actions"><button onClick={()=>route(scene,'scene')}>{sceneLabels[scene]} 장면 보기</button>
        <button onClick={()=>route(scene,'compare')}>이 장면 비교 보기</button></div>
    </Modal>}
    <div className="tw-decisions"><div><strong>{d.status==='DISCARDED'?'버림 이력':d.weekLocked?'게시 확정':'초안 검수'}</strong>
      <p>{d.adoptionWeekLocked && !d.weekLocked?'생성 주의 게시가 확정됐습니다. 다른 주에 편성하면 채택할 수 있습니다.':d.plannedWeek?'채택하면 '+d.plannedWeek+' 주차의 테마가 만들어집니다.':context}</p></div>
      <div className="ws-actions">
        {allowed.adopt && !d.weekLocked && !d.adoptionWeekLocked && <button className="cj-primary" disabled={blocked||pendingChild} onClick={()=>setConfirm({action:'adopt',plannedWeek:d.plannedWeek ?? null})}>채택해서 테마 만들기</button>}
        {allowed.regenerate && !d.weekLocked && <button disabled={blocked||pendingChild} onClick={()=>setConfirm({action:'regenerate'})}>{d.status==='DISCARDED'?'이 초안으로 새 초안 생성':'다시 생성'}</button>}
        {allowed.discard && !d.weekLocked && <button className="ad-danger" disabled={blocked} onClick={()=>setConfirm({action:'discard',plannedWeek:d.plannedWeek})}>버리기</button>}
      </div></div>
    {confirm && <Modal title={actionText+' 확인'} onClose={()=>{if(!act.isPending)setConfirm(null)}}>
      <p><strong>{theme?.title || d.input.topic || '주간 테마 초안'}</strong> · {confirm.action==='adopt'
        ? [d.grade && THEME_GRADE_LABELS[d.grade], '적용 주 '+(confirm.plannedWeek ?? d.weekStart ?? '미확인')].filter(Boolean).join(' · ')
        : context}</p>
      <p>{confirm.target?regenConfirmText(confirm.target):confirm.action==='adopt'?'채택하면 이 학년과 적용 주가 고정됩니다. 선택한 장면과 미션 5개로 테마를 만들고, 학생 공개는 게시 관리에서 확정합니다.':
        confirm.action==='discard'?'버린 초안은 다시 채택할 수 없습니다. 장면과 미션은 버림 이력에서 볼 수 있습니다.':'같은 입력으로 별도의 새 초안을 요청합니다.'}</p>
      {confirm.action==='discard' && confirm.plannedWeek && <p>{confirm.plannedWeek} 주차의 편성에서 이 후보가 해제됩니다.</p>}
      <div className="ws-actions"><button disabled={act.isPending} onClick={()=>setConfirm(null)}>취소</button>
        <button disabled={act.isPending} className={confirm.action==='discard'?'ad-danger':'cj-primary'} onClick={()=>run(confirm)}>{confirm.target?'다시 만들기':confirm.action==='adopt'?'채택':actionText}</button></div>
      <ErrorNotice error={act.error}/>
    </Modal>}
    {!confirm && <ErrorNotice error={act.error}/>}
    {act.error && (!(act.error instanceof ApiError)||act.error.problem.status>=500) && <p>처리됐을 수 있습니다. 다시 요청하기 전에 상태를 확인해 주세요.</p>}
  </div>
}
