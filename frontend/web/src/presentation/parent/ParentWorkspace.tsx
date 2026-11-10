import { useEffect, useState } from 'react'
import { useSearchParams, useLocation, useNavigate } from 'react-router'
import { useSession } from '../auth/sessionContext.ts'
import { parentApi } from '../../data/parent/api.ts'
import { sharingApi } from '../../data/classroom/sharingApi.ts'
import { useParentQuery } from '../../data/parent/queries.ts'
import { useAuthentication, displayPeriods } from '../../data/classroom/useClassroom.ts'
import type { Child, Period } from '../../domain/classroom.ts'
import { gradeLabel } from '../../domain/grade.ts'
import type { Scope } from '../../domain/parent.ts'
import { validPeriod } from '../../domain/parent.ts'
import { Workspace, QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import { ChildRegistration } from './AccountForms.tsx'
import { ParentConversation } from './ParentConversation.tsx'
import { ChildParticipation } from './ChildParticipation.tsx'
import { ParentReports } from './ParentReports.tsx'
import { StudentDevices } from './StudentDevices.tsx'
import { ParentDashboard } from './ParentDashboard.tsx'
import { ParentSettings } from './ParentSettings.tsx'
import { ParentPayments } from './ParentPayments.tsx'
import { EntitlementSummary } from './EntitlementSummary.tsx'
import { ParentSharingNotice } from './ParentSharingNotice.tsx'

export function ParentWorkspace() {
  const [params, setParams] = useSearchParams(), location = useLocation(), navigate = useNavigate()
  const { session, setSession, setSelected } = useSession(), auth = useAuthentication()
  const consentReady = session?.nextAction !== 'CONSENT_REQUIRED'
  const children = useParentQuery(['children'], signal => parentApi.children(signal), consentReady)
  const [registration, setRegistration] = useState(false)
  const childId = params.get('childId') ?? ''
  const scope: Scope = { childId, from: params.get('from') ?? displayPeriods.recentPeriod.from, to: params.get('to') ?? displayPeriods.recentPeriod.to }
  const child = consentReady ? children.data?.items.find(c => c.id === childId) : undefined
  const page = location.pathname.split('/')[2] ?? 'journal'
  const hasPeriod = page === 'journal' || page === 'analysis'
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
    { path: '/parent/journal', label: '학습 현황' }, { path: '/parent/report', label: '리포트' },
    { path: '/parent/analysis', label: 'AI 챗봇' }, { path: '/parent/settings', label: '계정·자녀 설정' },
    { path: '/parent/devices', label: '기기·PIN' }, { path: '/parent/billing', label: '이용권·결제' },
  ]
  return <Workspace title="학부모 공간" nav={nav} variant="parent"
    aside={child && <div className="ws-plan"><span>현재 이용권</span><strong>{child.nickname}</strong><EntitlementSummary childId={child.id} /></div>}
    actions={consentReady ? <>
      <label>자녀 선택<select aria-label="자녀 선택" value={childId} onChange={e => { const c = children.data?.items.find(c => c.id === e.target.value); if (c) select(c) }}>
        {!child && <option value={childId}>{childId ? '연결 여부 확인 필요' : '자녀를 선택해 주세요'}</option>}
        {children.data?.items.map(c => <option value={c.id} key={c.id}>{c.nickname} · {gradeLabel(c.grade)}</option>)}
      </select></label>
      <button className="cj-secondary" onClick={() => setRegistration(true)}>자녀 등록</button>
      {child && <button className="cj-primary" disabled={auth.enter.isPending || child.guardianConsentRequired} onClick={() => void auth.enter.mutateAsync(child).then(s => { setSession(s); navigate('/student/home') }).catch(() => {})}>이 자녀로 학습 시작</button>}
    </> : undefined}>
    {consentReady && <QueryFeedback query={children} />}<ErrorNotice error={auth.enter.error} />
    {child?.guardianConsentRequired && <p role="alert">자녀 이용을 위해 법정대리인 동의가 필요합니다. 계정·자녀 설정의 공개·동의에서 확인해 주세요.</p>}
    {hasPeriod && child && <details className="parent-scope"><summary>조회 기간 · {scope.from} ~ {scope.to}</summary><PeriodFilter key={`${scope.from}:${scope.to}`} period={scope} onApply={({ from, to }) => {
      const next = new URLSearchParams(params); next.set('from', from); next.set('to', to); setParams(next)
    }} /></details>}
    {hasPeriod && child && !validPeriod(scope) && <p role="alert">조회 기간이 올바르지 않습니다. 시작일과 종료일을 다시 선택해 주세요.</p>}
    {page === 'settings' ? <ParentSettings key={child?.id ?? 'account'} child={child} />
      : page === 'billing' ? <ParentPayments key={child?.id ?? 'all'} child={child} />
      : page === 'devices' && children.data && !children.error ? <StudentDevices items={children.data.items} />
      : children.data && !children.error && !children.data.items.length ? <section className="ws-card"><h1>자녀를 등록하고 시작하세요</h1><p>등록한 자녀의 학습 현황과 리포트를 확인할 수 있습니다.</p><ChildRegistration onCreated={select} /></section>
      : childId && !child && children.data && !children.error ? <section className="ws-card"><h1>자녀 연결 확인</h1><p role="alert">연결되지 않은 자녀의 기록은 표시하지 않습니다.</p></section>
      : child && (!hasPeriod || validPeriod(scope)) && !children.error ? <div className="parent-content" key={`${child.id}:${hasPeriod ? scope.from + ':' + scope.to : page}`}>
        {page === 'journal' && <ParentSharingNotice studentId={child.id} />}
        {page === 'analysis' ? <ParentConversation child={child} scope={scope} canReadOriginals={canReadOriginals} onScope={s => { const c = children.data?.items.find(c => c.id === s.childId); if (c) select(c, s) }} />
          : page === 'report' ? <ParentReports child={child} onAnalysis={p => navigate(`/parent/analysis?${new URLSearchParams({ childId: child.id, ...p })}`)} />
          : <><ParentDashboard child={child} scope={scope} canReadOriginals={canReadOriginals} sharingPending={sharing.isPending} /><ChildParticipation child={child} canReadOriginals={canReadOriginals} /></>}
      </div> : null}
    {registration && <Modal title="자녀 프로필 등록" onClose={() => setRegistration(false)}><ChildRegistration onCreated={c => { select(c); setRegistration(false) }} /></Modal>}
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
