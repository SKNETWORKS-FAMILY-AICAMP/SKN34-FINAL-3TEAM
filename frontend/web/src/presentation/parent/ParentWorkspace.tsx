import { useEffect, useState } from 'react'
import { useSearchParams, useLocation, useNavigate } from 'react-router'
import { useSession } from '../auth/sessionContext.ts'
import { parentApi } from '../../data/parent/api.ts'
import { useParentQuery } from '../../data/parent/queries.ts'
import { useAuthentication, displayPeriods } from '../../data/classroom/useClassroom.ts'
import type { Child, Period } from '../../domain/classroom.ts'
import type { Scope } from '../../domain/parent.ts'
import { validPeriod } from '../../domain/parent.ts'
import { Workspace, QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import { ChildRegistration, ProfileSettings } from './AccountForms.tsx'
import { ParentConversation } from './ParentConversation.tsx'
import { ConsentSettings } from './ConsentSettings.tsx'
import { ParentReports } from './ParentReports.tsx'
import { StudentDevices } from './StudentDevices.tsx'
import { ParentDashboard } from './ParentDashboard.tsx'
import { AccountLifecycle } from '../service/AccountLifecycle.tsx'
import { Withdrawal } from '../service/Withdrawal.tsx'
import { ParentPayments } from './ParentPayments.tsx'
export function ParentWorkspace() {
  const [params, setParams] = useSearchParams(),
    location = useLocation(),
    navigate = useNavigate(),
    { setSession, setSelected } = useSession(),
    auth = useAuthentication(),
    children = useParentQuery(['children'], (signal) => parentApi.children(signal)),
    [registration, setRegistration] = useState(false)
  const childId = params.get('childId') ?? '',
    scope: Scope = {
      childId,
      from: params.get('from') ?? displayPeriods.recentPeriod.from,
      to: params.get('to') ?? displayPeriods.recentPeriod.to,
    },
    child = children.data?.items.find((c) => c.id === childId)
  function select(c: Child, p: Period = scope) {
    const next = new URLSearchParams({ childId: c.id, from: p.from, to: p.to })
    setParams(next)
    setSelected(c.id)
    localStorage.setItem('sagomungchi:last-child', c.id)
  }
  useEffect(() => {
    if (!children.data || params.get('childId')) return
    const last = localStorage.getItem('sagomungchi:last-child'),
      c = children.data.items.find((c) => c.id === last) ?? children.data.items[0]
    if (c) setParams({ childId: c.id, from: scope.from, to: scope.to }, { replace: true })
  }, [children.data, params, setParams, scope.from, scope.to])
  const page = location.pathname.split('/')[2] ?? 'journal',
    nav = [
      { path: '/parent/journal', label: '대시보드·공책' },
      { path: '/parent/analysis', label: '기록에 물어보기' },
      { path: '/parent/report', label: '주간 리포트' },
      { path: '/parent/settings', label: '정보 관리' },
      { path: '/parent/devices', label: '자녀 기기·PIN' },
      { path: '/parent/billing', label: '이용권·결제' },
    ]
  return (
    <Workspace
      title="학부모 기록 공간"
      nav={nav}
      variant="parent"
      aside={
        child && (
          <div className="ws-plan">
            <span>이용권</span>
            <strong>
              {child.nickname} · {child.plan === 'FREE' ? '무료' : child.plan === 'PREMIUM' ? '프리미엄' : '이용권 확인 필요'}
            </strong>
            <small>
              {child.plan === 'FREE'
                ? '하루 미션 3개, 리포트 수치 제공'
                : child.plan === 'PREMIUM' ? '하루 피드백 50회·분석 대화 30회, 전체 리포트' : '이용권 정보를 확인하지 못했습니다.'}
            </small>
          </div>
        )
      }
      actions={
        <>
          <label>
            자녀 선택{' '}
            <select
              aria-label="자녀 선택"
              value={childId}
              onChange={(e) => {
                const c = children.data?.items.find((c) => c.id === e.target.value)
                if (c) select(c)
              }}
            >
              {!child && (
                <option value={childId}>
                  {childId ? '연결 여부 확인 필요' : '자녀를 선택해 주세요'}
                </option>
              )}
              {children.data?.items.map((c) => (
                <option value={c.id} key={c.id}>
                  {c.nickname} · 초{c.grade}
                </option>
              ))}
            </select>
          </label>
          <button className="cj-secondary" onClick={() => setRegistration(true)}>
            자녀 등록
          </button>
          {child && (
            <button
              className="cj-primary"
              disabled={auth.enter.isPending || child.guardianConsentRequired}
              onClick={() => {
                void auth.enter
                  .mutateAsync(child)
                  .then((s) => {
                    setSession(s)
                    navigate('/student/home')
                  })
                  .catch(() => {})
              }}
            >
              이 자녀로 학습 시작
            </button>
          )}
        </>
      }
    >
      <QueryFeedback query={children} />
      <ErrorNotice error={auth.enter.error} />
      {child?.recordState === 'UNAVAILABLE' && <p role="alert">기록 유무를 확인하지 못했습니다. 기록이 없는 상태와 다릅니다. 자녀 선택과 동석 진입은 사용할 수 있습니다.</p>}
      {child?.hasRecords === false && child.recordState === 'AVAILABLE' && <p>아직 학습 기록이 없습니다. 이 자녀로 첫 학습을 시작해 주세요.</p>}
      {child?.guardianConsentRequired && <p role="alert">법정대리인 동의가 필요합니다. 정보 관리에서 현재 문서에 동의해 주세요.</p>}
      {page === 'settings' && <ConsentSettings key={child?.id} child={child} />}
      {page !== 'billing' && <PeriodFilter
        key={`${scope.from}:${scope.to}`}
        period={scope}
        onApply={({ from, to }) => {
          const next = new URLSearchParams(params)
          next.set('from', from)
          next.set('to', to)
          setParams(next)
        }}
      />}
      {page !== 'billing' && <span className="ws-scope">
        선택 범위 · {child?.nickname ?? '자녀 미선택'} · {scope.from} ~ {scope.to}
      </span>}
      {page === 'billing' ? <ParentPayments key={child?.id ?? 'all'} child={child} /> : children.data && !children.error && !children.data.items.length ? (
        <section className="ws-card">
          <h1>먼저 자녀를 등록해 주세요.</h1>
          <p>연결된 자녀가 없어 아직 기록을 조회하지 않습니다.</p>
          <ChildRegistration onCreated={(c) => select(c)} />
        </section>
      ) : page === 'devices' && children.data && !children.error ? (
        <StudentDevices items={children.data.items} />
      ) : childId && !child && children.data && !children.error ? (
        <section className="ws-card">
          <h1>자녀 연결을 확인해 주세요.</h1>
          <p role="alert">CHILD_NOT_LINKED · 연결되지 않은 자녀의 기록은 표시하지 않습니다.</p>
        </section>
      ) : child && validPeriod(scope) && !children.error ? (
        <div key={`${scope.childId}:${scope.from}:${scope.to}`}>
          {page === 'analysis' ? (
            <ParentConversation
              child={child}
              scope={scope}
              onScope={(s) => {
                const c = children.data?.items.find((c) => c.id === s.childId)
                if (c) select(c, s)
              }}
            />
          ) : page === 'report' ? (
            <ParentReports
              child={child}
              scope={scope}
              onAnalysis={(p) =>
                navigate(`/parent/analysis?${new URLSearchParams({ childId: child.id, ...p })}`)
              }
            />
          ) : page === 'settings' ? (
            <><ProfileSettings child={child} /><AccountLifecycle key={child.id} child={child} /><Withdrawal /></>
          ) : (
            <ParentDashboard child={child} scope={scope} />
          )}
        </div>
      ) : null}
      {registration && (
        <Modal title="자녀 프로필 등록" onClose={() => setRegistration(false)}>
          <ChildRegistration
            onCreated={(c) => {
              select(c)
              setRegistration(false)
            }}
          />
        </Modal>
      )}
    </Workspace>
  )
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
