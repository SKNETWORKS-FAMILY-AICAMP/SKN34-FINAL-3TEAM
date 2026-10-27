import { useEffect, useState } from 'react'
import { useSearchParams, useLocation, useNavigate } from 'react-router'
import { useSession } from '../auth/sessionContext.ts'
import { parentApi } from '../../data/parent/api.ts'
import { useParentQuery, useParentDashboard } from '../../data/parent/queries.ts'
import { useAuthentication, displayPeriods } from '../../data/classroom/useClassroom.ts'
import type { Child, Period } from '../../domain/classroom.ts'
import type { Scope } from '../../domain/parent.ts'
import { thinkingLabels } from '../../domain/classroom.ts'
import { validPeriod } from '../../domain/parent.ts'
import { Workspace, QueryFeedback, MetricCards } from '../common/Workspace.tsx'
import { QueryStateNotice } from '../common/QueryStateNotice.tsx'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import { ChildRegistration, ProfileSettings } from './AccountForms.tsx'
import { ParentConversation } from './ParentConversation.tsx'
import { ParentReports } from './ParentReports.tsx'
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
    ]
  return (
    <Workspace
      title="학부모 기록 공간"
      nav={nav}
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
              disabled={auth.enter.isPending}
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
      <PeriodFilter
        key={`${scope.from}:${scope.to}`}
        period={scope}
        onApply={({ from, to }) => {
          const next = new URLSearchParams(params)
          next.set('from', from)
          next.set('to', to)
          setParams(next)
        }}
      />
      <span>
        선택 범위 · {child?.nickname ?? '자녀 미선택'} · {scope.from} ~ {scope.to}
      </span>
      {children.data && !children.error && !children.data.items.length ? (
        <section className="ws-card">
          <h1>먼저 자녀를 등록해 주세요.</h1>
          <p>연결된 자녀가 없어 아직 기록을 조회하지 않습니다.</p>
          <ChildRegistration onCreated={(c) => select(c)} />
        </section>
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
            <ProfileSettings child={child} />
          ) : (
            <Dashboard child={child} scope={scope} />
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
function Dashboard({ child, scope }: { child: Child; scope: Scope }) {
  const q = useParentDashboard(scope),
    [record, setRecord] = useState<string | null>(null)
  return (
    <>
      <h1>{child.nickname}의 기록을 함께 살펴보세요.</h1>
      <p>건수에서 답변으로, 답변에서 질문으로 이어집니다.</p>
      <QueryFeedback query={q.summary} />
      {q.summary.data && !q.summary.error && (
        <>
          <p>
            실제 조회 기간 · {q.summary.data.period.from} ~ {q.summary.data.period.to}
          </p>
          <p>{q.summary.data.inclusionRule}</p>
          <QueryStateNotice state={q.summary.data.state} />
          {q.summary.data.state === 'NO_RECORD' && (
            <p>
              아직 집계할 기록이 없습니다. 상단의 ‘이 자녀로 학습 시작’에서 첫 활동을 시작해 보세요.
            </p>
          )}
          <MetricCards metrics={q.summary.data.metrics} />
        </>
      )}
      <section className="ws-card">
        <h2>다섯 가지 생각 활동</h2>
        <QueryFeedback query={q.thinking} />
        {q.thinking.data && !q.thinking.error && (
          <div className="ws-metrics">
            {q.thinking.data.items.map((t) => (
              <div key={t.type}>
                <h3>{thinkingLabels[t.type]}</h3>
                <p>
                  {t.state === 'NO_RECORD'
                    ? '미관찰 · 아직 확인된 기록 없음'
                    : `${t.missions.length}개 미션에서 관찰`}
                </p>
                {t.missions.map((m) => (
                  <button
                    key={m.attemptId}
                    className="cj-secondary"
                    onClick={() => setRecord(m.attemptId)}
                  >
                    {m.title}
                  </button>
                ))}
              </div>
            ))}
          </div>
        )}
      </section>
      <section className="ws-card">
        <h2>학습 기록</h2>
        <QueryFeedback query={q.records} />
        {q.records.data && !q.records.error && (
          <div className="ws-stack">
            <p>
              실제 목록 기간 · {q.records.data.period.from} ~ {q.records.data.period.to}
            </p>
            {!q.records.data.items.length && (
              <p>아직 기록이 없습니다. 첫 학습 후 답변이 여기에 연결됩니다.</p>
            )}
            {q.records.data.items.map((a) => (
              <article className="ws-card" key={a.attemptId}>
                <h3>{a.mission.title}</h3>
                <p>
                  {a.status === 'COMPLETED' ? '완료' : '진행 중'} · {a.answers.length}개 답변
                </p>
                <button className="cj-secondary" onClick={() => setRecord(a.attemptId)}>
                  답변·되묻기·돌아보기 보기
                </button>
              </article>
            ))}
          </div>
        )}
      </section>
      {record && (
        <Modal title="학습 기록 원문" onClose={() => setRecord(null)}>
          <RecordDetail childId={child.id} id={record} />
        </Modal>
      )}
    </>
  )
}
export function RecordDetail({ childId, id }: { childId: string; id: string }) {
  const q = useParentQuery(['record', childId, id], (signal) =>
    parentApi.record(childId, id, signal),
  )
  return (
    <>
      <QueryFeedback query={q} />
      {q.data && !q.error && (
        <>
          <h3>{q.data.mission.title}</h3>
          {q.data.answers.map((a) => (
            <section key={a.answerId}>
              <h4>
                {a.version === 1 ? '최초 답변' : `보완 답변 ${a.version - 1}`} · {a.submittedAt}
              </h4>
              <blockquote>{a.text}</blockquote>
              {a.feedback.followup && <p>되묻기 · {a.feedback.followup.question}</p>}
            </section>
          ))}
          <p>생각 열기 이용: {q.data.helped ? '이용함' : '이용 안 함'}</p>
          <h4>돌아보기</h4>
          <p>
            {q.data.reflection
              ? `${q.data.reflection.difficulty} · ${q.data.reflection.text || '달라진 점 미작성'}`
              : '미작성'}
          </p>
        </>
      )}
    </>
  )
}
