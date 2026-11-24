import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { CalendarDays } from 'lucide-react'
import { themePlannerApi, type PlannerDraft, type PlannerTheme, type PlanChange, type WeekSlot } from '../../data/admin/themePlannerApi.ts'
import { useAdminMutation, useAdminQuery } from '../../data/admin/queries.ts'
import { THEME_GRADE_LABELS, THEME_STATUS_LABELS, publishProblems, type ThemeGrade } from '../../domain/admin/retention.ts'
import { ApiError } from '../../data/apiClient.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { Modal, ErrorNotice } from '../shared/ClassroomParts.tsx'
import { Badge, Panel } from './AdminUi.tsx'
import './weeklyPlanner.css'
import { busyProps } from './busyButton.ts'

function offset(date: string, days: number) {
  const stamp = new Date(date + 'T00:00:00Z')
  stamp.setUTCDate(stamp.getUTCDate() + days)
  return stamp.toISOString().slice(0, 10)
}
function thisMonday() {
  const today = new Date(Date.now() + 9 * 3600_000)
  return offset(today.toISOString().slice(0,10), -((today.getUTCDay()+6)%7))
}
function isMonday(value: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && new Date(value+'T00:00:00Z').getUTCDay() === 1
}
type Decision =
  | {kind:'plan'; request:PlanChange; draft:PlannerDraft; other:PlannerDraft | undefined}
  | {kind:'publish'; theme:PlannerTheme; slot:WeekSlot; grade:ThemeGrade}
type Choosing = {draft:PlannerDraft; destination:string} | {week:string; candidateId:string}

export function WeeklyThemePlanner({onOpen,onCreate}: {onOpen:(id:string)=>void;onCreate:()=>void}) {
  const [params,setParams] = useSearchParams()
  const rawGrade = params.get('grade') ?? 'G4'
  const grade = Object.hasOwn(THEME_GRADE_LABELS,rawGrade) ? rawGrade as ThemeGrade : 'G4'
  const from = params.get('weekStart') ?? ''
  const start = isMonday(from) ? from : thisMonday()
  const pendingOnly = params.get('status')==='REVIEW_REQUIRED'
  const page = Math.max(0,Number.parseInt(params.get('page')??'0',10)||0)
  const waiting = useAdminQuery(['weekly-themes','awaiting',page], signal=>themePlannerApi.awaiting(page,signal),pendingOnly)
  const board = useAdminQuery(['theme-planner',grade,start], signal=>themePlannerApi.get(grade,start,signal),!pendingOnly)
  const [choosing,setChoosing] = useState<Choosing | null>(null)
  const [decision,setDecision] = useState<Decision | null>(null)
  const [message,setMessage] = useState('')
  const change = useAdminMutation((action:Decision) => action.kind==='plan' ? themePlannerApi.apply(action.request).then(()=>undefined) : themePlannerApi.publish(action.theme,action.slot.planned?.draftId??null).then(()=>undefined))
  const candidates = board.data?.candidates ?? []
  const destinationLocked = choosing && 'draft' in choosing &&
    board.data?.weeks.some(slot => slot.weekStart === choosing.destination && slot.locked)
  const choosePeriod = (nextGrade:ThemeGrade, nextWeek:string) => {
    if (!isMonday(nextWeek)) return
    const next=new URLSearchParams(params)
    next.delete('status');next.delete('page')
    next.set('grade',nextGrade); next.set('weekStart',nextWeek); next.delete('themeId')
    setParams(next); setMessage('')
  }
  const askPlan = (draft:PlannerDraft,to:string|null) => {
    const other=candidates.find(d=>d.draftId!==draft.draftId && to!==null && d.plannedWeek===to)
    const request={grade,draftId:draft.draftId,expectedWeek:draft.plannedWeek,targetWeek:to,expectedTargetDraftId:other?.draftId??null}
    setChoosing(null);change.reset();setDecision({kind:'plan',draft,request,other})
  }
  const finish = async () => {
    if (!decision || change.isPending) return
    try {
      await change.mutateAsync(decision)
      setMessage(decision.kind==='publish' ? '게시를 확정했습니다.' : '주차 편성을 저장했습니다.')
      setDecision(null)
    } catch {
      await board.refetch()
    }
  }
  const close = () => { if (!change.isPending) { setDecision(null);change.reset() } }
  const problems=change.error instanceof ApiError ? publishProblems(change.error.problem) : []
  const waitingPage = (n:number) => { const next=new URLSearchParams(params);next.set('status','REVIEW_REQUIRED');next.set('page',String(n));setParams(next) }
  if(pendingOnly) return <Panel title="게시 검토 대기" action={<button onClick={()=>choosePeriod(grade,start)}>전체 편성 보기</button>}>
    <QueryFeedback query={waiting}/>
    {waiting.data && !waiting.error && <><p>{waiting.data.totalElements}건</p>
      <ul className="ad-plan-pool">{waiting.data.items.map(t=><li key={t.themeId}><div><strong>{t.title}</strong><small>{THEME_GRADE_LABELS[t.grade]} · {t.weekStart}</small></div>
        <button onClick={()=>choosePeriod(t.grade,t.weekStart)}>해당 주차에서 게시 검토</button></li>)}</ul>
      {waiting.data.totalElements===0 && <p>게시 검토를 기다리는 테마가 없습니다.</p>}
      <div className="ws-actions"><button disabled={page===0} onClick={()=>waitingPage(page-1)}>이전</button><button disabled={(page+1)*20>=waiting.data.totalElements} onClick={()=>waitingPage(page+1)}>다음</button></div></>}
  </Panel>
  return <div className="ad-week-planner">
    <Panel title="주간 편성·게시" action={<button type="button" onClick={onCreate}>새 테마</button>}>
      <div className="ad-toolbar ad-plan-toolbar">
        <label>학년<select aria-label="테마 학년" value={grade} onChange={e=>choosePeriod(e.target.value as ThemeGrade,start)}>
          {Object.entries(THEME_GRADE_LABELS).map(([key,text])=><option key={key} value={key}>{text}</option>)}</select></label>
        <label>첫 주 월요일<input aria-label="편성 시작 주" type="date" value={start} onChange={e=>choosePeriod(grade,e.target.value)} /></label>
        <div className="ws-actions"><button onClick={()=>choosePeriod(grade,offset(start,-28))}>이전 4주</button>
          <button onClick={()=>choosePeriod(grade,thisMonday())}>이번 주</button>
          <button onClick={()=>choosePeriod(grade,offset(start,28))}>다음 4주</button><button onClick={()=>waitingPage(0)}>게시 검토 대기</button></div>
      </div>
      <QueryFeedback query={board} />
      {board.data && !board.error && <div className="ad-plan-weeks">{board.data.weeks.map(slot=>{
        const published=slot.themes.find(t=>t.status==='PUBLISHED')
        const available = candidates.some(d=>d.plannedWeek!==slot.weekStart)
        return <section className="ad-plan-slot" key={slot.weekStart} aria-label={slot.weekStart+' 주차'}>
          <header><CalendarDays size={17} aria-hidden="true"/><h3>{slot.weekStart} 주</h3></header>
          {slot.locked && published ? <div className="ad-plan-theme"><Badge active>게시 중</Badge>
            <strong>{published.title}</strong><button onClick={()=>onOpen(published.themeId)}>게시 테마 관리</button></div> : <>
            {slot.themes.map(t=><div className="ad-plan-theme" key={t.themeId}><Badge>{THEME_STATUS_LABELS[t.status]}</Badge>
              <strong>{t.title}</strong><button onClick={()=>onOpen(t.themeId)}>테마 열기</button>
              {t.status==='REVIEW_REQUIRED' && <button className="cj-primary" onClick={()=>{change.reset();setDecision({kind:'publish',theme:t,slot,grade})}}>최종 게시</button>}</div>)}
            {slot.planned && <div className="ad-plan-theme"><Badge>편성 후보</Badge><strong>{slot.planned.title}</strong>
              <small>생성 기준 주 {slot.planned.generationWeek}</small>
              <Link to={'/admin/theme-drafts?draftId='+encodeURIComponent(slot.planned.draftId)}>초안 검수</Link>
              <button onClick={()=>setChoosing({draft:slot.planned!,destination:offset(slot.weekStart,7)})}>주차 변경·맞바꾸기</button>
              <button onClick={()=>askPlan(slot.planned!,null)}>편성 해제</button></div>}
            {!slot.themes.length && !slot.planned && <p>편성된 테마가 없습니다.</p>}
            {available && slot.weekStart>=thisMonday() && <button onClick={()=>setChoosing({week:slot.weekStart,candidateId:''})}>후보 선택</button>}
          </>}
        </section>
      })}</div>}
    </Panel>
    {board.data && !board.error && <Panel title="편성 후보" action={<Link to="/admin/theme-drafts">주간 테마 검수</Link>}>
      {candidates.length===0 ? <p>이 학년에 편성할 검수 완료 초안이 없습니다.</p> : <ul className="ad-plan-pool">{candidates.map(d=><li key={d.draftId}>
        <div><strong>{d.title}</strong><small>생성 기준 주 {d.generationWeek} · {d.plannedWeek ? '편성 주차 '+d.plannedWeek : '미편성'}</small></div>
        <Link to={'/admin/theme-drafts?draftId='+encodeURIComponent(d.draftId)}>초안 검수</Link>
        <button onClick={()=>setChoosing({draft:d,destination:d.plannedWeek?offset(d.plannedWeek,7):start})}>주차 선택</button>
      </li>)}</ul>}
    </Panel>}
    <p role="status">{message}</p>
    {choosing && <Modal title={'draft' in choosing?'편성할 주차 선택':'편성할 초안 선택'} onClose={()=>setChoosing(null)}>
      <form className="ws-form" onSubmit={e=>{
        e.preventDefault()
        if ('draft' in choosing) { if (isMonday(choosing.destination) && !destinationLocked) askPlan(choosing.draft,choosing.destination) }
        else { const draft=candidates.find(d=>d.draftId===choosing.candidateId); if(draft) askPlan(draft,choosing.week) }
      }}>
        {'draft' in choosing ? <><p>{THEME_GRADE_LABELS[grade]} · {choosing.draft.title}</p>
          <label>편성 주차 (월요일)<input type="date" required min={thisMonday()} value={choosing.destination} onChange={e=>setChoosing({...choosing,destination:e.target.value})}/></label>
          {choosing.destination && !isMonday(choosing.destination) && <p role="alert">월요일 날짜를 선택해 주세요.</p>}
          {destinationLocked && <p role="alert">이미 게시된 주차입니다. 다른 주를 선택해 주세요.</p>}</> :
          <><p>{THEME_GRADE_LABELS[grade]} · {choosing.week}</p><label>초안<select required value={choosing.candidateId} onChange={e=>setChoosing({...choosing,candidateId:e.target.value})}>
            <option value="">후보 선택</option>{candidates.filter(d=>d.plannedWeek!==choosing.week).map(d=><option key={d.draftId} value={d.draftId}>{d.title} · {d.plannedWeek??'미편성'}</option>)}</select></label></>}
        <div className="ws-actions"><button type="button" onClick={()=>setChoosing(null)}>취소</button><button className="cj-primary"
          disabled={'draft' in choosing ? !!destinationLocked||!isMonday(choosing.destination)||choosing.destination===choosing.draft.plannedWeek||choosing.destination<thisMonday() : !choosing.candidateId}>변경 내용 확인</button></div>
      </form></Modal>}
    {decision && <Modal title={decision.kind==='publish'?'이 주차의 게시를 확정할까요?':decision.other&&decision.request.expectedWeek?'두 주의 후보를 맞바꿀까요?':'주차 편성을 변경할까요?'} onClose={close}>
      {decision.kind==='publish' ? <><p><strong>{THEME_GRADE_LABELS[decision.grade]} · {decision.slot.weekStart} · {decision.theme.title}</strong></p>
        <p>이 버전의 테마와 요일별 미션을 학생에게 공개합니다. 이후 수정한 내용은 검토 후 재게시할 때 반영됩니다.</p>
        {decision.slot.planned && <p>편성 후보 ‘{decision.slot.planned.title}’는 미편성으로 돌아갑니다.</p>}</> :
        <><p><strong>{decision.draft.title}</strong> · {decision.request.expectedWeek??'미편성'} → {decision.request.targetWeek??'미편성'}</p>
        {decision.other && <p><strong>{decision.other.title}</strong> · {decision.other.plannedWeek} → {decision.request.expectedWeek??'미편성'}</p>}</>}
      {problems.length>0 && <ul role="alert">{problems.map(p=><li key={p}>{p}</li>)}</ul>}<ErrorNotice error={problems.length?null:change.error}/>
      <div className="ws-actions"><button {...busyProps(change.isPending)} onClick={close}>취소</button><button className="cj-primary" {...busyProps(change.isPending, change.isError)} onClick={()=>void finish()}>
        {decision.kind==='publish'?'최종 게시 확정':'편성 확정'}</button></div>
    </Modal>}
  </div>
}
