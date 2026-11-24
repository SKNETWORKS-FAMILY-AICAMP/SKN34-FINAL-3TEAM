import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { BookOpen, CalendarDays, Film, Layers, Play, RotateCw } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router'
import { adminRetentionApi as api } from '../../data/admin/retentionApi.ts'
import { useAdminMutation, useAdminQuery } from '../../data/admin/queries.ts'
import { ApiError } from '../../data/apiClient.ts'
import { thinkingLabels, inputLabels } from '../../domain/classroom.ts'
import { THEME_GRADE_LABELS } from '../../domain/admin/retention.ts'
import { THEME_SCENES, failureStageLabels, regenButtonLabels, regenConfirmText, regenKindsOf, regenTargetLabel,
  sceneLabels, themeDraftActions, themeDraftLabels } from '../../domain/admin/themeDrafts.ts'
import type { RegenKind, RegenTarget, ThemeDraft, ThemeSceneName } from '../../domain/admin/themeDrafts.ts'
import { versionName } from '../../domain/admin/sceneVersions.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import { Panel } from './AdminUi.tsx'
import { busyProps } from './busyButton.ts'
import { reviewWeeks } from './adminFormatting.ts'
import { ThemeDraftList } from './ThemeDraftList.tsx'
import { ThemeSceneReview } from './ThemeSceneReview.tsx'
import { useAdoptedTheme, useStoryboardScenes } from '../../data/admin/themeReviewQueries.ts'
import { ThemeStoryboard } from './ThemeStoryboard.tsx'
import { ThemeWeekMissions, ThemeAdoptedFooter } from './ThemeWeekMissions.tsx'
import { ThemeWeekPlayback } from './ThemeWeekPlayback.tsx'
import type { ScenePairs, SceneSettings, SceneView } from './ThemeSceneReview.tsx'
import './theme-workspace.css'
import './theme-storyboard.css'

const POLL_MS = 5000
const days = THEME_SCENES.filter(s => s !== 'INTRO' && s !== 'OUTRO')
type Change = (values: Record<string, string | null>, replace?: boolean) => void

export function ThemeDraftManager() {
  const [params, setParams] = useSearchParams()
  const [requestedId, setRequestedId] = useState('')
  const selected = params.get('draftId') || ''
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
  function choose(id: string) {change({draftId:id, scene:null, view:null, generationId:null, request:null}, params.get('request') === '1')}
  function leave(archive = false) {
    setRequestedId('')
    change({ draftId:null, scene:null, view:null, generationId:null,
      ...(archive ? { stage:'discarded',status:null,comparisonPending:null,grade:null,week:null,weekStart:null,source:null,page:null } : {}) })
  }
  if (selected) return <ThemeDraftDetail key={selected} draftId={selected} params={params} change={change} leave={leave}
    choose={choose} requestedNotice={selected === requestedId ? '생성 요청을 접수했습니다. 처리 상태를 확인해 주세요.' : ''}/>
  return <ThemeDraftList params={params} change={change} onRequested={draft => {
    setRequestedId(draft.draftId)
    choose(draft.draftId)
  }}/>
}

type Pending = { action:'adopt'|'discard'|'regenerate'; target?:RegenTarget; sourceId?:string; plannedWeek?:string|null }
function ThemeDraftDetail({ draftId, params, change, leave, choose, requestedNotice }: {
  draftId:string; params:URLSearchParams; change:Change; leave:(archive?:boolean)=>void; choose:(id:string)=>void; requestedNotice:string
}) {
  const navigate = useNavigate(), cache = useQueryClient()
  const heading = useRef<HTMLDivElement>(null), singleFocus = useRef(false)
  const [still,setStill] = useState(false), [confirm,setConfirm] = useState<Pending|null>(null)
  const [notice,setNotice] = useState(requestedNotice), actionLock = useRef(false)
  const [pairs,setPairs] = useState<ScenePairs>({})
  const [sceneSettings,setSceneSettings] = useState<Partial<Record<ThemeSceneName,SceneSettings>>>({})
  const [generated,setGenerated] = useState<{scene:ThemeSceneName; id:string} | null>(null)
  const requestedGeneration = useRef<{scene:ThemeSceneName; id:string} | null>(null)
  const scene = THEME_SCENES.find(s=>s===params.get('scene')?.toUpperCase()) ?? 'INTRO'
  const rawView = params.get('view')
  const [comparedScenes,setComparedScenes] = useState<Partial<Record<ThemeSceneName,boolean>>>(() =>
    rawView === 'compare' || rawView === 'single' ? { [scene]: rawView === 'compare' } : {})
  const requestedView: SceneView = rawView === 'compare' || rawView === 'week' || rawView === 'missions' || (rawView === 'mission' && days.some(d=>d===scene)) ? rawView : 'scene'
  const generationId = params.get('generationId') || ''
  const detail = useAdminQuery(['theme-draft',draftId], signal=>api.themeDraft(draftId,signal),true,data=>data?.status==='GENERATING'?POLL_MS:false)
  const d = detail.error ? undefined : detail.data
  const storyboard = useStoryboardScenes(d, (requestedView !== 'mission' && requestedView !== 'missions') || confirm?.action === 'adopt')
  const sceneView = (name: ThemeSceneName) => (comparedScenes[name] ?? storyboard.find(row => row.scene === name)?.comparisonPending) ? 'compare' : 'scene'
  const view: SceneView = !rawView ? sceneView(scene) : requestedView
  const activeShot = storyboard.find(row => row.scene === scene)!
  const sourceId = activeShot.selected?.versionId ?? draftId
  const needsSource = sourceId !== draftId && (view === 'scene' || view === 'compare') && !!d && themeDraftActions(d.status).regenerate && !d.weekLocked && d.status !== 'DISCARDED'
  const selectedSource = useAdminQuery(['theme-draft',sourceId], signal=>api.themeDraft(sourceId,signal), needsSource)
  const adopted = useAdoptedTheme(detail.data?.themeId ?? null)
  const work = useAdminQuery(['theme-draft',generationId], signal=>api.themeDraft(generationId,signal),!!generationId,data=>data?.status==='GENERATING'?POLL_MS:false)
  const handled = useRef('')
  useEffect(()=>{
    const completed = work.data
    if (!generationId || !completed || completed.status==='GENERATING' || handled.current===generationId) return
    handled.current=generationId
    if (requestedGeneration.current?.id === generationId) {
      if (completed.status === 'READY') setGenerated(requestedGeneration.current)
      requestedGeneration.current = null
    }
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
      if(result.themeId){
        const themeId = result.themeId
        cache.setQueryData<ThemeDraft>(['admin','theme-draft',draftId], previous => previous && { ...previous, status: 'ADOPTED', themeId })
        setNotice('초안을 채택했습니다. 요일별 미션을 검토하세요.')
        change({view:'missions',generationId:null})
        return
      }
      if(!result.draft)return
      if(p.action==='discard'){
        cache.setQueryData(['admin','theme-draft',draftId],result.draft)
        setNotice('초안을 버렸습니다. 버림 이력에서 다시 볼 수 있습니다.')
      }else if(p.target){
        const targetScene = THEME_SCENES.find(name => p.target?.endsWith(':' + name))
        if (targetScene) {
          requestedGeneration.current = {scene: targetScene, id: result.draft.draftId}
          setGenerated(null)
        }
        change({generationId:result.draft.draftId},true)
        setNotice(regenTargetLabel(p.target)+' 다시 만들기 요청을 접수했습니다.')
      }else choose(result.draft.draftId)
    }).catch((error:unknown)=>{
      if(error instanceof ApiError && error.problem.status===409){setConfirm(null);void detail.refetch()}
    }).finally(()=>{actionLock.current=false})
  }
  function route(s:ThemeSceneName, mode:SceneView) {
    singleFocus.current = mode === 'scene' && view === 'mission'
    if (mode === 'scene' || mode === 'compare') setComparedScenes(previous => ({...previous,[s]:mode === 'compare'}))
    change({scene:s,view:mode==='scene'?'single':mode})
  }
  const [missionOrigin,setMissionOrigin] = useState<SceneView>('missions')
  function open(s:ThemeSceneName, mode:SceneView) {
    if(mode==='mission')setMissionOrigin(view==='mission'?'missions':view)
    route(s,mode)
  }
  if(!d)return <Panel title="초안 상세" action={<button onClick={()=>leave()}>검수 목록으로</button>}>
    {notice && <p role="status">{notice}</p>}<QueryFeedback query={detail}/></Panel>
  const theme=d.draft?.theme, allowed=themeDraftActions(d.status), readOnly=d.weekLocked || d.status==='ADOPTED' || d.status==='DISCARDED'
  const mission=d.draft?.missions.find(m=>m.day===scene)
  const pendingChild=!!generationId && (!work.data || work.data.status==='GENERATING') && !work.error
  const sourceDraft = sourceId === draftId ? d : selectedSource.data
  const availableKinds = regenKindsOf(scene)
  const regenTargets = availableKinds.map(kind => (kind+':'+scene) as RegenTarget)
    .filter(target => sourceDraft?.regenerableTargets.includes(target))
  const context=(d.grade ? THEME_GRADE_LABELS[d.grade]+' · ' : '')+(d.weekStart ?? '생성 주 미확인')
  const pendingComparisons = storyboard.filter(row => row.comparisonPending)
  const checkingSelections = confirm?.action === 'adopt' && storyboard.some(row => row.loading || row.error)
  const actionText=confirm?.target?regenTargetLabel(confirm.target)+' 다시 만들기':confirm?.action==='discard'?'초안 버리기':confirm?.action==='adopt'?'채택':'새 초안 생성'
  const missionTab = view === 'missions' || view === 'mission'
  const adoptedStatus = !adopted.error && adopted.data?.theme.status
  const weeks = reviewWeeks(d.weekStart, d.plannedWeek, d.status === 'ADOPTED' ? adopted.data?.theme.weekStart ?? d.plannedWeek ?? d.weekStart : null)
  const statusLabel = d.status === 'DISCARDED' ? '버림' : adoptedStatus === 'PUBLISHED' ? '게시 완료'
    : d.weekLocked ? '주차 확정 · 읽기 전용' : adoptedStatus === 'REVIEW_REQUIRED' ? '테마 검토 요청'
    : d.status === 'ADOPTED' ? '초안 채택 완료' : d.status === 'READY' ? '검수 대기' : themeDraftLabels[d.status]
  const showRegen = d.status !== 'GENERATING'
  const regenReason = d.weekLocked ? '게시가 확정된 주차에서는 장면을 다시 생성할 수 없습니다.'
    : d.status === 'ADOPTED' ? '채택한 초안의 장면은 다시 생성할 수 없습니다.'
    : d.status === 'DISCARDED' ? '버린 초안에서는 새 초안만 생성할 수 있습니다.'
    : pendingChild ? '요청한 장면을 생성하고 있습니다.'
    : activeShot.error || (needsSource && selectedSource.isError) ? '선택본의 재생성 정보를 불러오지 못했습니다.'
    : activeShot.loading || (needsSource && selectedSource.isPending) ? '선택본의 재생성 정보를 확인하고 있습니다.'
    : d.status === 'READY' && activeShot.editable === false ? '검수가 종료된 장면입니다.'
    : !regenTargets.length ? '이 선택본에는 장면 재생성 자료가 없습니다. 초안 전체를 다시 생성할 수 있습니다.' : ''
  const regenActions = showRegen && (regenTargets.length && !readOnly ? regenTargets.map((target,index) =>
    <button type="button" key={target} className={index===0?'rv-primary':undefined} {...busyProps(act.isPending, !!confirm || !!regenReason)}
      aria-describedby={regenReason?'scene-regen-reason':undefined}
      onClick={()=>setConfirm({action:'regenerate',target,sourceId})}>
      {index===0 && <RotateCw size={14} aria-hidden="true" />}{regenButtonLabels[target.split(':')[0] as RegenKind]}
    </button>) : <button type="button" className="rv-primary" disabled aria-describedby="scene-regen-reason">
      <RotateCw size={14} aria-hidden="true"/>{regenButtonLabels[availableKinds[0]]}</button>)
  return <div className="tw-desk rv-detail" ref={heading}>
    <div className="rv-crumb"><button type="button" onClick={()=>d.weekLocked && adopted.data ? navigate('/admin/themes?' + new URLSearchParams({ grade: adopted.data.theme.grade, weekStart: adopted.data.theme.weekStart })) : leave(d.status === 'DISCARDED')}>{d.status === 'DISCARDED' ? '버림 이력' : d.weekLocked && adopted.data ? '주차별 편성·게시' : '검수함'}</button><span>/</span><span>{d.weekLocked ? '내용 보기' : '초안 검수'}</span></div>
    {notice && <p role="status">{notice}</p>}
    <header className="rv-page-head">
      <div className="rv-title-line"><h1>{theme?.title || d.input.topic || '초안 상세'}</h1>
        <span className="rv-status" data-status={d.status}>{statusLabel}</span>
        {allowed.regenerate && !d.weekLocked && view!=='week' &&
          <button type="button" className="rv-primary rv-regenerate-draft" {...busyProps(act.isPending, !!confirm || pendingChild)}
            onClick={()=>setConfirm({action:'regenerate'})}><RotateCw size={15} aria-hidden="true" />
            {d.status==='DISCARDED'?'이 초안으로 새 초안 생성':'초안 전체 다시 생성'}</button>}
      </div>
      <div className="rv-meta">{d.grade && <span>{d.grade.slice(1)}학년</span>}
        <span className="rv-week-group"><CalendarDays size={15} aria-hidden="true" />{weeks.length ? weeks.map(w=><span key={w.label}>{w.label} <time dateTime={w.date}>{w.range}</time></span>) : '생성 기준 주 미확인'}</span>
        <span>{d.source === 'ADMIN' ? '직접 요청' : d.source === 'AUTO' ? '자동 생성' : '출처 미확인'}</span>
      </div>
    </header>
      {d.status==='GENERATING' && <p role="status">생성 중입니다. 5초마다 다시 확인합니다.</p>}
      {d.status==='DISCARDED' && <p>버린 초안입니다. 보존된 장면과 요일 미션을 열어볼 수 있습니다.</p>}
      {d.input.regenerate && <p>{d.input.regenerate.targets.map(regenTargetLabel).join(', ')}만 다시 만듦 · <button className="ad-link-button" onClick={()=>choose(d.input.regenerate!.baseDraftId)}>원래 초안 열기</button></p>}
      {d.checkResults.some(v=>v.failures.length>0) && <div className="ad-note"><h3>검사 실패</h3>{d.checkResults.flatMap(r=>r.failures.map((f,i)=><p key={r.attempt+'-'+i}>{r.attempt}회차 · {failureStageLabels[f.stage]??f.stage}: {f.reasons.join(' / ')}</p>))}</div>}
      {d.draft?.warnings.map((w,i)=><p key={i} className="ad-note">{failureStageLabels[w.stage]??w.stage} · {w.reason}</p>)}
    {generationId && <div className="ad-note" aria-live="polite"><QueryFeedback query={work}/>
      {work.data && <span>부분 생성 · {themeDraftLabels[work.data.status]}{work.data.failureCode?' · '+work.data.failureCode:''}</span>}
      <button className="ad-link-button" onClick={()=>choose(generationId)}>요청한 초안 열기</button></div>}
    {d.draft ? <>
      {view !== 'week' && <div className="rv-tabbar"><div className="rv-tabs" role="group" aria-label="검수할 항목">
        <button aria-pressed={!missionTab} onClick={()=>route(scene,sceneView(scene))}><Film size={16} />주간 장면 <span>{THEME_SCENES.length}</span></button>
        <button aria-pressed={missionTab} onClick={()=>route(scene,'missions')}><BookOpen size={16} />요일별 미션 <span>{days.length}</span></button>
      </div><button className="rv-open-full" onClick={()=>route(scene,'week')}><Play size={15} />전체 이어보기</button></div>}
      {missionTab ? <ThemeWeekMissions draft={d} scene={scene} detailOpen={view==='mission'} onOpen={open} onPublished={setNotice} onClose={()=>route(scene,missionOrigin==='mission'?'missions':missionOrigin)} />
        : view === 'week' ? <ThemeWeekPlayback scenes={storyboard} still={still} onClose={()=>route(scene,sceneView(scene))} />
        : <div className="rv-workbench">
          <ThemeStoryboard scenes={storyboard} active={scene} onChoose={s=>change({scene:s,view:null})} />
          <div className="tw-stage" tabIndex={-1}><ThemeSceneReview draft={d} scene={scene} view={view} weeks={weeks} open={open} still={still}
            pairs={pairs} setPairs={setPairs} generated={generated}
            settings={sceneSettings[scene] ?? {}} updateSettings={patch => setSceneSettings(saved => ({
              ...saved, [scene]: { ...saved[scene], ...patch },
            }))}
            onComparedGeneration={id=>setGenerated(value=>value?.id===id ? null : value)} regenActions={regenActions}
            regenSourceId={sourceId} regenReason={showRegen ? regenReason : ''} />
            {mission && <section className="rv-mission-context"><div><small>{sceneLabels[scene]} 미션</small><h3>{mission.title}</h3><p>{mission.question}</p></div>
              <button aria-label="이 요일 미션 보기" onClick={()=>open(scene,'mission')}>미션 내용 보기</button></section>}
          </div>
        </div>}
    </> : d.status!=='GENERATING' && <p>생성 결과가 없습니다. 실패 사유를 확인해 주세요.</p>}
    {view !== 'week' && (d.status === 'ADOPTED' && d.themeId ? <ThemeAdoptedFooter draft={d} /> :
      <footer className="rv-decision"><div><Layers size={21} /><span><strong>{d.status==='DISCARDED'?'버림 이력':d.weekLocked?'주차 확정':'초안 검수 결정'}</strong>
        <small>{pendingChild?'장면 생성이 끝나면 채택하거나 버릴 수 있습니다.':d.adoptionWeekLocked && !d.weekLocked?'생성 기준 주의 게시가 확정됐습니다. 다른 주에 편성하면 채택할 수 있습니다.':d.status === 'DISCARDED'?'버린 초안의 장면과 미션을 열람할 수 있습니다.':d.draft?'장면 7개의 선택본과 미션 5개를 확정합니다.':context}</small></span></div>
        <div className="ws-actions">
          {allowed.discard && !d.weekLocked && <button {...busyProps(act.isPending, !!confirm || pendingChild)} onClick={()=>setConfirm({action:'discard',plannedWeek:d.plannedWeek})}>초안 버리기</button>}
          {allowed.adopt && !d.weekLocked && d.adoptionWeekLocked && d.grade && <button onClick={()=>navigate('/admin/themes?' + new URLSearchParams({grade:d.grade!,weekStart:d.plannedWeek || d.weekStart || ''}))}>편성 주차 선택</button>}
          {d.status==='DISCARDED' && <button onClick={()=>leave(true)}>버림 이력 보기</button>}
          {allowed.adopt && !d.weekLocked && !d.adoptionWeekLocked && <button className="rv-primary" {...busyProps(act.isPending, !!confirm || pendingChild)} onClick={()=>setConfirm({action:'adopt',plannedWeek:d.plannedWeek})}>{d.plannedWeek?'이 주차로 채택':'초안 채택'}</button>}
        </div>
      </footer>)}
    <details className="rv-settings"><summary>검수 설정과 생성 정보</summary>
      <label className="tw-check"><input type="checkbox" checked={still} onChange={e=>setStill(e.target.checked)}/>움직임 끄기 (정지 그림만)</label>
      <section className="tw-story" aria-label={sceneLabels[scene]+' 이야기'}>
        {scene==='INTRO'||scene==='OUTRO'?<p>{(scene==='INTRO'?theme?.intro:theme?.outro)||'이야기 없음'}</p>:<><h4>{mission?.title}</h4><p>{mission?.question}</p></>}
        {theme?.bigQuestion && <details><summary>큰 질문과 엔딩 정답</summary><p>{theme.bigQuestion}</p><p>후보 {theme.candidates.join(', ')} · 정답 {theme.answer}</p></details>}
      </section>
      <details><summary>생성 정보와 요청 조건</summary>
        <dl className="ad-draft-meta"><dt>생성 시도</dt><dd>{d.attempts} / {d.maxAttempts || '—'} {d.failureCode}</dd>
        <dt>주제</dt><dd>{d.input.topic??'자동'}</dd><dt>생성 버전</dt><dd>{[d.versions.prompt,d.versions.model].filter(Boolean).join(' · ')||'—'}</dd>
        <dt>초안 식별자</dt><dd>{draftId}</dd></dl>
        {d.input.missions.map((m,i)=><p key={i}>{m.thinkingType?thinkingLabels[m.thinkingType]:'유형 미확인'} · {m.inputType?inputLabels[m.inputType]:'입력 방식 미확인'} · {m.standardCodes.join(', ')}</p>)}
        <button {...busyProps(detail.isFetching)} onClick={()=>void detail.refetch()}>다시 확인</button>
      </details>
    </details>
    {confirm && <Modal title={actionText+' 확인'} onClose={()=>{if(!act.isPending)setConfirm(null)}}>
      <p><strong>{theme?.title || d.input.topic || '주간 테마 초안'}</strong> · {confirm.action==='adopt'
        ? [d.grade && THEME_GRADE_LABELS[d.grade], '적용 주 '+(confirm.plannedWeek ?? d.weekStart ?? '미확인')].filter(Boolean).join(' · ')
        : context}</p>
      <p>{confirm.target?regenConfirmText(confirm.target):confirm.action==='adopt'?'채택하면 이 학년과 적용 주가 고정됩니다. 선택한 장면과 미션 5개로 테마를 만들고, 학생 공개는 게시 관리에서 확정합니다.':
        confirm.action==='discard'?'버린 초안은 다시 채택할 수 없습니다. 장면과 미션은 버림 이력에서 볼 수 있습니다.':'같은 입력으로 별도의 새 초안을 요청합니다.'}</p>
      {confirm.action==='adopt' && <section className="rv-adopt-shots"><h3>장면별 채택할 선택본</h3>
        {pendingComparisons.length > 0 && <p className="ad-note"><strong>선택을 확정하지 않은 후보가 {pendingComparisons.length}개 장면에 있습니다.</strong><br />
          지금 채택하면 아래의 현재 선택본이 유지됩니다. 채택한 뒤에는 버전을 바꿀 수 없습니다.</p>}
        <ul>{storyboard.map(row=><li key={row.scene}><strong>{row.label}</strong><span>{row.selected ? versionName(row.selected) : row.status}</span>
          {row.comparisonPending && <><small>후보 선택 대기</small><button {...busyProps(act.isPending)} aria-label={row.label+' 후보 비교'} onClick={()=>{setConfirm(null);route(row.scene,'compare')}}>비교</button></>}
          {row.error && <button {...busyProps(act.isPending)} onClick={()=>void row.refetch()}>다시 확인</button>}</li>)}</ul></section>}
      {confirm.action==='discard' && confirm.plannedWeek && <p>{confirm.plannedWeek} 주차의 편성에서 이 후보가 해제됩니다.</p>}
      <div className="ws-actions"><button {...busyProps(act.isPending)} onClick={()=>setConfirm(null)}>취소</button>
        <button {...busyProps(act.isPending, checkingSelections)} className={confirm.action==='discard'?'ad-danger':'cj-primary'} onClick={()=>run(confirm)}>{confirm.target?'다시 만들기':confirm.action==='adopt'?(pendingComparisons.length?'현재 선택본으로 채택':'채택'):actionText}</button></div>
      <ErrorNotice error={act.error}/>
    </Modal>}
    {!confirm && <ErrorNotice error={act.error}/>}
    {act.error && (!(act.error instanceof ApiError)||act.error.problem.status>=500) && <p>처리됐을 수 있습니다. 다시 요청하기 전에 상태를 확인해 주세요.</p>}
  </div>
}
