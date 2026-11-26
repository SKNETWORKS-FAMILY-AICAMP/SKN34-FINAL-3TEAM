import './parent-management.css'
import { CalendarDays, ChevronDown } from 'lucide-react'
import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Link, Navigate, useSearchParams, useLocation } from 'react-router'
import { useSession } from '../auth/sessionContext.ts'
import { parentApi } from '../../data/parent/api.ts'
import { useParentQuery } from '../../data/parent/queries.ts'
import { displayPeriods } from '../../data/classroom/useClassroom.ts'
import type { Child, Period } from '../../domain/classroom.ts'
import { gradeLabel } from '../../domain/grade.ts'
import type { Scope } from '../../domain/parent.ts'
import { validPeriod } from '../../domain/parent.ts'
import { Workspace, QueryFeedback } from '../common/Workspace.tsx'
import { ParentInsights } from './ParentInsights.tsx'
import { DateFilter } from './ActivityExplorer.tsx'
import { Modal } from '../shared/ClassroomParts.tsx'
import { StudentDevices } from './StudentDevices.tsx'
import { ParentDashboard } from './ParentDashboard.tsx'
import { ParentSettings } from './ParentSettings.tsx'
import { ParentPayments } from './ParentPayments.tsx'
import { parentNavigation } from './parentNavigation.tsx'
import { ParentGuideGate } from './ParentGuide.tsx'

const ServiceContent = lazy(() => import('../service/ServiceCenter.tsx').then(m => ({ default: m.ServiceContent })))
const SupportResults = lazy(() => import('../support/SupportResults.tsx').then(m => ({ default: m.SupportResults })))

export function ParentWorkspace() {
  const [params, setParams] = useSearchParams(), location = useLocation()
  const periodFilter = useRef<HTMLDetailsElement>(null)
  const { session, setSelected } = useSession()
  const consentReady = session?.nextAction !== 'CONSENT_REQUIRED'
  const children = useParentQuery(['children'], signal => parentApi.children(signal), consentReady)
  const childId = params.get('childId') ?? ''
  const scope: Scope = { childId, from: params.get('from') ?? displayPeriods.recentPeriod.from, to: params.get('to') ?? displayPeriods.recentPeriod.to }
  const child = consentReady ? children.data?.items.find(c => c.id === childId) : undefined
  const page = location.pathname.split('/')[2] ?? 'journal'
  const hasPeriod = ['journal', 'analysis', 'report'].includes(page)
  function select(c: Child, p: Period = scope) {
    const next = new URLSearchParams(params)
    next.set('childId', c.id); next.set('from', p.from); next.set('to', p.to); next.delete('reportId'); next.delete('revision')
    setParams(next); setSelected(c.id); localStorage.setItem('sagomungchi:last-child', c.id)
  }
  useEffect(() => {
    if (!consentReady || !children.data || params.get('childId')) return
    const last = localStorage.getItem('sagomungchi:last-child')
    const c = children.data.items.find(c => c.id === last) ?? children.data.items[0]
    if (c) {
      const next = new URLSearchParams(params)
      next.set('childId', c.id); next.set('from', scope.from); next.set('to', scope.to)
      setParams(next, { replace: true })
    }
  }, [consentReady, children.data, params, setParams, scope.from, scope.to])
  // 리포트·AI 챗봇은 사이드바 한 칸(/parent/report)이고, 화면 안 '리포트 | AI 챗봇' 전환은 view=chat으로 구분한다.
  if (page === 'analysis' || page === 'chat') {
    const next = new URLSearchParams(params); next.set('view', 'chat')
    return <Navigate to={'/parent/report?' + next} replace />
  }
  const insightsMode = params.get('view') === 'chat' ? 'chat' : 'report'
  return <Workspace title="학부모 공간" nav={parentNavigation} variant="parent" fullScreen={page === 'report' && insightsMode === 'chat'} actions={consentReady && <ChildPicker items={children.data?.items ?? []} selectedId={child?.id} loading={children.isPending} failed={!!children.error} disabled={page === 'billing' && params.get('checkout') === '1'} onSelect={c => select(c)} />}>
    {consentReady && <QueryFeedback query={children} />}
    {/* 첫 사용 안내(#1037): 동의·자녀 등록(READY)을 마친 뒤 학습 현황에서만 */}
    {page === 'journal' && (session?.nextAction ?? 'READY') === 'READY' && <ParentGuideGate />}
    {child?.guardianConsentRequired && <p role="alert">자녀 이용을 위해 법정대리인 동의가 필요합니다. 계정·자녀 설정의 공개·동의에서 확인해 주세요.</p>}
    {hasPeriod && child && (page !== 'report' || !validPeriod(scope)) && <details ref={periodFilter} className="parent-scope"><summary>조회 기간 · {scope.from} ~ {scope.to}</summary><PeriodFilter key={`${scope.from}:${scope.to}`} period={scope} onApply={({ from, to }) => {
      const next = new URLSearchParams(params); next.set('from', from); next.set('to', to); setParams(next)
    }} /></details>}
    {hasPeriod && child && !validPeriod(scope) && <p role="alert">조회 기간이 올바르지 않습니다. 시작일과 종료일을 다시 선택해 주세요.</p>}
    {['help', 'support', 'notices', 'notifications'].includes(page) ? <Suspense fallback={<p role="status">불러오고 있습니다.</p>}>{location.pathname.endsWith('/support/results') ? <SupportResults /> : <ServiceContent page={page as 'help' | 'support' | 'notices' | 'notifications'} />}</Suspense>
      : page === 'settings' ? <ParentSettings key={child?.id ?? 'account'} child={child} childItems={consentReady ? children.data?.items : undefined} onCreated={select} />
      : page === 'billing' ? <ParentPayments key={child?.id ?? 'all'} child={child} />
      : page === 'devices' && children.data && !children.error ? <StudentDevices items={children.data.items} selectedChildId={child?.id} />
      : children.data && !children.error && !children.data.items.length ? <section className="ws-card"><h1>자녀를 등록하고 시작하세요</h1><p>등록한 자녀의 학습 현황과 리포트를 확인할 수 있습니다.</p><Link className="cj-primary" to="/parent/settings?section=profile">계정·자녀 설정에서 자녀 등록</Link></section>
      : childId && !child && children.data && !children.error ? <section className="ws-card"><h1>자녀 연결 확인</h1><p role="alert">연결되지 않은 자녀의 기록은 표시하지 않습니다.</p></section>
      : child && (!hasPeriod || validPeriod(scope)) && !children.error ? <div className="parent-content" key={`${child.id}:${page === 'report' ? 'insights' : hasPeriod ? scope.from + ':' + scope.to : page}`}>
        {page === 'report' ? <ParentInsights key={`${insightsMode}:${scope.from}:${scope.to}:${params.get('askReportId') ?? ''}`} mode={insightsMode} child={child} scope={scope}
          periodControl={<ChatPeriodPicker period={scope} onApply={({ from, to }) => {
            const next = new URLSearchParams(params); next.set('from', from); next.set('to', to); setParams(next)
          }} />}
          onScope={s => { const c = children.data?.items.find(c => c.id === s.childId); if (c) select(c, s) }} />
          : <ParentDashboard child={child} scope={scope} onChangePeriod={() => {
            if (periodFilter.current) {
              periodFilter.current.open = true
              periodFilter.current.querySelector('input')?.focus()
            }
          }} />}
      </div> : null}
  </Workspace>
}
function ChatPeriodPicker({ period, onApply }: { period: Period; onApply: (period: Period) => void }) {
  const [open, setOpen] = useState(false)
  return <div className="chat-period-picker">
    <button type="button" className="chat-period-control" aria-label={`질문 기간 변경 · ${period.from} ~ ${period.to}`}
      aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}>
      <CalendarDays size={17} aria-hidden="true" />
      <span>{period.from} ~ {period.to}</span>
      <ChevronDown size={14} aria-hidden="true" />
    </button>
    {open && <Modal title="질문 기간 선택" onClose={() => setOpen(false)}>
      <DateFilter initial={period} embedded week onCancel={() => setOpen(false)} onApply={value => {
        setOpen(false)
        onApply(value)
      }} />
    </Modal>}
  </div>
}

function PeriodFilter({ period, onApply }: { period: Period; onApply: (p: Period) => void }) {
  const [from, setFrom] = useState(period.from),
    [to, setTo] = useState(period.to),
    [error, setError] = useState('')
  const startInvalid = !validPeriod({ from, to: from })
  return (
    <>
      <form
        className="ws-toolbar"
        onSubmit={(e) => {
          e.preventDefault()
          if (!validPeriod({ from, to })) {
            setError(startInvalid ? '시작일을 입력해 주세요.' : !to ? '종료일을 입력해 주세요.' : '종료일은 시작일과 같거나 이후여야 합니다.')
            e.currentTarget.querySelector<HTMLInputElement>(startInvalid ? '[name="from"]' : '[name="to"]')?.focus()
            return
          }
          setError('')
          onApply({ from, to })
        }}
      >
        <label>
          조회 시작일
          <input
            aria-label="조회 시작일" name="from" aria-invalid={!!error && startInvalid} aria-describedby={error ? 'period-error' : undefined}
            type="date"
            value={from}
            onChange={(e) => { setError(''); setFrom(e.target.value) }}
          />
        </label>
        <label>
          조회 종료일
          <input
            aria-label="조회 종료일" name="to" aria-invalid={!!error && !startInvalid} aria-describedby={error ? 'period-error' : undefined}
            type="date"
            value={to}
            onChange={(e) => { setError(''); setTo(e.target.value) }}
          />
        </label>
        <button className="cj-secondary">기간 적용</button>
      </form>
      {error && <p id="period-error" role="alert">{error}</p>}
    </>
  )
}

/** Header selection stays shared across all parent categories; payment checkout locks its target. */
function ChildPicker({items,selectedId,onSelect,loading,failed,disabled}: {items:Child[];selectedId?:string;onSelect:(c:Child)=>void;loading:boolean;failed:boolean;disabled:boolean}) {
  return <div className="parent-header-child-picker">
    <select aria-label="현재 자녀 선택" value={selectedId ?? ''} disabled={disabled || loading || failed || !items.length} title={disabled ? '결제 중인 자녀는 변경할 수 없습니다.' : '자녀 선택'} onChange={e=>{const child=items.find(c=>c.id===e.target.value);if(child)onSelect(child)}}>
      {!selectedId && <option value="" disabled>{loading ? '자녀 확인 중' : failed ? '자녀 조회 실패' : items.length ? '자녀 선택' : '등록된 자녀 없음'}</option>}
      {items.map(c=><option key={c.id} value={c.id}>{c.nickname} · {gradeLabel(c.grade)}</option>)}
    </select><ChevronDown size={16} aria-hidden="true"/>
  </div>
}
