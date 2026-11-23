import { CalendarDays, Clapperboard, CreditCard, Flag, MessagesSquare, RotateCcw } from 'lucide-react'
import { Link } from 'react-router'
import { adminApi } from '../../data/admin/api.ts'
import { useAdminQuery } from '../../data/admin/queries.ts'
import { adminRetentionApi as themes } from '../../data/admin/retentionApi.ts'
import type { Period } from '../../domain/classroom.ts'
import type { Permission } from '../../domain/admin/operations.ts'
import { THEME_GRADE_LABELS } from '../../domain/admin/retention.ts'
import { QueryFeedback } from '../common/Workspace.tsx'

export function WorkloadCards({ period, permissions }: { period: Period; permissions: Permission[] }) {
  const cards = [
    { key:'pendingInquiries', permission:'SERVICE_OPS', label:'답변 대기 문의', to:'/admin/support?tab=inquiries&status=RECEIVED', icon:MessagesSquare },
    { key:'receivedReports', permission:'SERVICE_OPS', label:'신규 오류 신고', to:'/admin/errors?status=RECEIVED', icon:Flag },
    { key:'failedJobs', permission:'SERVICE_OPS', label:'재처리할 실패 작업', to:'/admin/jobs?'+new URLSearchParams({...period,status:'FAILED'}), icon:RotateCcw },
    { key:'pendingRefunds', permission:'PAYMENT_VIEW', label:'환불 승인 대기', to:'/admin/payments?tab=refunds&status=REQUESTED', icon:CreditCard },
  ] as const
  const visible=cards.filter(c=>permissions.includes(c.permission))
  const q=useAdminQuery(['workload',period,permissions], async signal=>{
    const counts=await adminApi.workload(period,signal)
    for(const card of visible) {
      const n=counts[card.key]
      if(typeof n!=='number' || !Number.isSafeInteger(n) || n<0) throw new Error('운영 대기 건수를 확인하지 못했습니다.')
    }
    return counts
  },visible.length>0)
  if(!visible.length) return null
  return <section className="ad-workload" aria-label="운영 대기 현황">
    <h2>운영 대기 현황</h2>
    <p>문의·신고·환불은 전체 접수 건, 실패 작업은 선택한 기간에 생성된 건입니다.</p>
    <QueryFeedback query={q}/>
    {q.data && !q.error && <div className="ad-workload-cards">{visible.map(({key,label,to,icon:Icon})=>
      <Link key={key} to={to}><span className={'ad-task-icon '+key}><Icon size={20}/></span>
        <span>{label}<strong>{q.data[key]}건</strong></span></Link>)}</div>}
  </section>
}

export function ThemeWorkQueue() {
  const ready=useAdminQuery(['home','ready-drafts'],s=>themes.themeDrafts({status:'READY',hideDiscarded:'true',size:'1'},s))
  const compare=useAdminQuery(['home','compare-drafts'],s=>themes.themeDrafts({status:'READY',comparisonPending:'true',size:'1'},s))
  const review=useAdminQuery(['home','publish-queue'],s=>themes.themes({status:'REVIEW_REQUIRED'},s))
  const priority=compare.data?.items[0] ?? ready.data?.items[0]
  const detail=useAdminQuery(['theme-draft',priority?.draftId],s=>themes.themeDraft(priority!.draftId,s),!!priority)
  const theme=detail.data
  const firstImage=theme?.scenes.find(scene=>scene.scene==='INTRO')?.imageUrl
  const queues=[
    {label:'검사 통과 초안',to:'/admin/theme-drafts?status=READY',count:ready.data?.totalElements,q:ready},
    {label:'재생성 장면 비교 대기',to:'/admin/theme-drafts?status=READY&comparisonPending=true',count:compare.data?.totalElements,q:compare},
    {label:'게시 검토 대기',to:'/admin/themes?status=REVIEW_REQUIRED',count:review.data?.totalElements,q:review},
  ]
  return <section className="ad-theme-work" aria-label="테마 검수·게시">
    <div className="ad-priority-theme">
      {firstImage && <img src={firstImage} alt=""/>}
      <div><span><Clapperboard size={16}/> 우선 검수 테마</span>
        {priority && <QueryFeedback query={detail}/>}
        {theme ? <><h2>{theme.draft?.theme?.title || theme.input.topic || '테마 초안'}</h2>
          <p>{theme.grade && THEME_GRADE_LABELS[theme.grade]} · {theme.weekStart} 생성 기준 주</p>
          <Link to={'/admin/theme-drafts?draftId='+encodeURIComponent(theme.draftId)}>테마 검수 열기</Link></>
        : !priority && !ready.isPending && !compare.isPending && <p>{ready.error || compare.error ? '검수 후보를 불러오지 못했습니다.' : '검수할 초안이 없습니다.'}</p>}
      </div>
    </div>
    <div className="ad-theme-work-list"><h2><CalendarDays size={18}/> 테마 검수·게시 대기</h2>
      {queues.map(({label,to,count,q})=><Link to={to} key={to}><span>{label}</span><strong>{q.error?'조회 실패':q.isPending?'조회 중':typeof count==='number'?count+'건':'집계 미제공'}</strong></Link>)}
      <Link className="ad-request-theme" to="/admin/theme-drafts?request=1">테마 추가 생성 요청</Link>
    </div>
  </section>
}
