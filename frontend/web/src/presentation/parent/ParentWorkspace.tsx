import { lazy, Suspense, useEffect, useState } from 'react'
import { Link, Navigate, useSearchParams, useLocation } from 'react-router'
import { useSession } from '../auth/sessionContext.ts'
import { parentApi } from '../../data/parent/api.ts'
import { sharingApi } from '../../data/classroom/sharingApi.ts'
import { useParentQuery } from '../../data/parent/queries.ts'
import { displayPeriods } from '../../data/classroom/useClassroom.ts'
import type { Child, Period } from '../../domain/classroom.ts'
import { gradeLabel } from '../../domain/grade.ts'
import type { Scope } from '../../domain/parent.ts'
import { validPeriod } from '../../domain/parent.ts'
import { Workspace, QueryFeedback } from '../common/Workspace.tsx'
import { ParentInsights } from './ParentInsights.tsx'
import { ChildParticipation } from './ChildParticipation.tsx'
import { StudentDevices } from './StudentDevices.tsx'
import { ParentDashboard } from './ParentDashboard.tsx'
import { ParentSettings } from './ParentSettings.tsx'
import { ParentPayments } from './ParentPayments.tsx'
import { ParentSharingNotice } from './ParentSharingNotice.tsx'

const ServiceContent = lazy(() => import('../service/ServiceCenter.tsx').then(m => ({ default: m.ServiceContent })))
const SupportResults = lazy(() => import('../support/SupportResults.tsx').then(m => ({ default: m.SupportResults })))

export function ParentWorkspace() {
  const [params, setParams] = useSearchParams(), location = useLocation()
  const { session, setSelected } = useSession()
  const consentReady = session?.nextAction !== 'CONSENT_REQUIRED'
  const children = useParentQuery(['children'], signal => parentApi.children(signal), consentReady)
  const childId = params.get('childId') ?? ''
  const scope: Scope = { childId, from: params.get('from') ?? displayPeriods.recentPeriod.from, to: params.get('to') ?? displayPeriods.recentPeriod.to }
  const child = consentReady ? children.data?.items.find(c => c.id === childId) : undefined
  const page = location.pathname.split('/')[2] ?? 'journal'
  const hasPeriod = ['journal', 'analysis', 'report'].includes(page)
  const sharing = useParentQuery(['sharing-preferences', childId], signal => sharingApi.get(childId, 'PARENT', signal), !!child && hasPeriod)
  const canReadOriginals = sharing.data?.parentSharingEnabled === true && !sharing.error
  function select(c: Child, p: Period = scope) {
    const next = new URLSearchParams(params)
    next.set('childId', c.id); next.set('from', p.from); next.set('to', p.to)
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
  const nav = [
    { path: '/parent/journal', label: '학습 현황' }, { path: '/parent/report', label: '리포트·AI 챗봇' }, { path: '/parent/settings', label: '계정·자녀 설정' },
    { path: '/parent/devices', label: '기기·PIN' }, { path: '/parent/billing', label: '이용권·결제' },
  ]
  if (page === 'analysis') {
    const next = new URLSearchParams(params); next.set('view', 'chat')
    return <Navigate to={'/parent/report?' + next} replace />
  }
  return <Workspace title="학부모 공간" nav={nav} variant="parent"
    actions={consentReady && page !== 'devices' && params.get('checkout') !== '1' ? <>
      <label>자녀 선택<select aria-label="자녀 선택" value={childId} onChange={e => { const c = children.data?.items.find(c => c.id === e.target.value); if (c) select(c) }}>
        {!child && <option value={childId}>{childId ? '연결 여부 확인 필요' : '자녀를 선택해 주세요'}</option>}
        {children.data?.items.map(c => <option value={c.id} key={c.id}>{c.nickname} · {gradeLabel(c.grade)}</option>)}
      </select></label>
    </> : undefined}>
    {consentReady && <QueryFeedback query={children} />}
    {child?.guardianConsentRequired && <p role="alert">자녀 이용을 위해 법정대리인 동의가 필요합니다. 계정·자녀 설정의 공개·동의에서 확인해 주세요.</p>}
    {hasPeriod && child && (page !== 'report' || !validPeriod(scope)) && <details className="parent-scope"><summary>조회 기간 · {scope.from} ~ {scope.to}</summary><PeriodFilter key={`${scope.from}:${scope.to}`} period={scope} onApply={({ from, to }) => {
      const next = new URLSearchParams(params); next.set('from', from); next.set('to', to); setParams(next)
    }} /></details>}
    {hasPeriod && child && !validPeriod(scope) && <p role="alert">조회 기간이 올바르지 않습니다. 시작일과 종료일을 다시 선택해 주세요.</p>}
    {['help', 'support', 'notices', 'notifications'].includes(page) ? <Suspense fallback={<p role="status">불러오고 있습니다.</p>}>{location.pathname.endsWith('/support/results') ? <SupportResults /> : <ServiceContent page={page as 'help' | 'support' | 'notices' | 'notifications'} />}</Suspense>
      : page === 'settings' ? <ParentSettings key={child?.id ?? 'account'} child={child} childCount={consentReady ? children.data?.items.length : undefined} onCreated={select} />
      : page === 'billing' ? <ParentPayments key={child?.id ?? 'all'} child={child} />
      : page === 'devices' && children.data && !children.error ? <StudentDevices items={children.data.items} />
      : children.data && !children.error && !children.data.items.length ? <section className="ws-card"><h1>자녀를 등록하고 시작하세요</h1><p>등록한 자녀의 학습 현황과 리포트를 확인할 수 있습니다.</p><Link className="cj-primary" to="/parent/settings?section=profile">계정·자녀 설정에서 자녀 등록</Link></section>
      : childId && !child && children.data && !children.error ? <section className="ws-card"><h1>자녀 연결 확인</h1><p role="alert">연결되지 않은 자녀의 기록은 표시하지 않습니다.</p></section>
      : child && (!hasPeriod || validPeriod(scope)) && !children.error ? <div className="parent-content" key={`${child.id}:${page === 'report' ? 'insights' : hasPeriod ? scope.from + ':' + scope.to : page}`}>
        {page === 'journal' && <ParentSharingNotice studentId={child.id} />}
        {page === 'report' ? <ParentInsights key={`${scope.from}:${scope.to}:${canReadOriginals}:${sharing.isPending}`} child={child} scope={scope} canReadOriginals={canReadOriginals} sharingPending={sharing.isPending}
          periodControl={<details className="parent-scope"><summary>질문할 기간 · {scope.from} ~ {scope.to}</summary><PeriodFilter key={`${scope.from}:${scope.to}`} period={scope} onApply={({ from, to }) => {
            const next = new URLSearchParams(params); next.set('from', from); next.set('to', to); setParams(next)
          }} /></details>}
          onScope={s => { const c = children.data?.items.find(c => c.id === s.childId); if (c) select(c, s) }} />
          : <><ParentDashboard child={child} scope={scope} canReadOriginals={canReadOriginals} sharingPending={sharing.isPending} /><ChildParticipation child={child} canReadOriginals={canReadOriginals} /></>}
      </div> : null}
  </Workspace>
}
function PeriodFilter({ period, onApply }: { period: Period; onApply: (p: Period) => void }) {
  const [from, setFrom] = useState(period.from),
    [to, setTo] = useState(period.to),
    [error, setError] = useState('')
  return (
    <>
      <form
        className="ws-toolbar"
        onSubmit={(e) => {
          e.preventDefault()
          if (!validPeriod({ from, to })) {
            setError('시작일과 종료일을 확인해 주세요.')
            return
          }
          setError('')
          onApply({ from, to })
        }}
      >
        <label>
          조회 시작일
          <input
            aria-label="조회 시작일"
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </label>
        <label>
          조회 종료일
          <input
            aria-label="조회 종료일"
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </label>
        <button className="cj-secondary">기간 적용</button>
      </form>
      {error && <p role="alert">{error}</p>}
    </>
  )
}
