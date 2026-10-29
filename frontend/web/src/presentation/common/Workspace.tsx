import { useState } from 'react'
function ServiceLinks({ role }: { role?: string }) {
  if (!role) return null
  const root = '/' + role.toLowerCase()
  return <nav aria-label="이용 지원" className="ws-actions" style={{ marginBottom: 20, flexWrap: 'wrap', gap: 16 }}>
    <Link to={root + '/help'}>도움말</Link><Link to={root + '/support'}>문의·오류 신고</Link><Link to={root + '/notices'}>공지</Link>
    {role !== 'STUDENT' && <Link to={root + '/notifications'}>알림</Link>}
    {role === 'PARENT' && <Link to="/parent/account">계정·자녀 관리</Link>}
    {isDemo && <Link to="/review">개발 점검표</Link>}
  </nav>
}
import type { ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useAuthentication, isDemo } from '../../data/classroom/useClassroom.ts'
import { useSession } from '../auth/sessionContext.ts'
import { Brand, ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import { QueryStateNotice } from './QueryStateNotice.tsx'
import type { Metric } from '../../domain/classroom.ts'
import type { Evidence } from '../../domain/parent.ts'
import { metricText } from '../../domain/parent.ts'
import '../classroom.css'
import './workspace.css'
import './workspace-parent.css'
export function Workspace({
  title,
  nav,
  children,
  actions,
  variant,
  aside,
}: {
  title: string
  nav: { path: string; label: string }[]
  children: ReactNode
  actions?: ReactNode
  /** parent: 왼쪽 메뉴 + 본문 배치(학부모 대시보드 시안). 관리자는 기존 위쪽 메뉴 배치. */
  variant?: 'parent'
  /** 왼쪽 메뉴 아래에 붙는 보조 정보(학부모: 이용권) */
  aside?: ReactNode
}) {
  const { session, setSession, expired, setExpired } = useSession(),
    auth = useAuthentication(),
    navigate = useNavigate(),
    location = useLocation(),
    cache = useQueryClient()
  const [scenario, setScenario] = useState('normal')
  async function leave() {
    try {
      await auth.logout.mutateAsync()
    } finally {
      setSession(null)
      setExpired(false)
      cache.clear()
      navigate('/login', { replace: true })
    }
  }
  const logout = session && (
    <button
      className="cj-secondary"
      onClick={() => {
        void leave().catch(() => {})
      }}
    >
      로그아웃
    </button>
  )
  const demo = isDemo && (
    <div className="ws-demo">
      <span>개발 목업 · 가상 데이터만 사용 · 실제 서버·AI 호출 없음</span>
      <label>
        상태 시연{' '}
        <select
          aria-label="상태 시연"
          value={scenario}
          onChange={(e) => {
            setScenario(e.target.value)
            window.dispatchEvent(
              new CustomEvent('sagomungchi:workspace-scenario', { detail: e.target.value }),
            )
            void cache.invalidateQueries({ queryKey: ['parent'] })
            void cache.invalidateQueries({ queryKey: ['admin'] })
          }}
        >
          {[
            ['normal', '정상'],
            ['no-children', '자녀 없음'],
            ['empty', '기록 없음'],
            ['small', '표본 부족'],
            ['query-fail', '조회 실패'],
            ['clarification', '대화 범위 확인'],
            ['verification-error', '대조 실패 오류'],
            ['verification-fallback', '대조 실패·규칙 응답'],
            ['analysis-fail', '대화 처리 실패'],
            ['analysis-slow', '대화 처리 지연'],
            ['scope-change', '응답 범위 변경'],
            ['report-running', '리포트 생성 중'],
            ['report-failed', '리포트 생성 실패'],
            ['deleted-evidence', '삭제된 근거'],
            ['gone-evidence', '근거 410'],
            ['unlinked', '연결 안 된 자녀'],
            ['retry-fail', '작업 재처리 실패'],
            ['publish-missing', '게시 필수 누락'],
            ['forbidden', '권한 거부 403'],
          ].map(([id, label]) => (
            <option key={id} value={id}>
              {label}
            </option>
          ))}
        </select>
      </label>
    </div>
  )
  const menu = (
    <nav className="ws-nav" aria-label={`${title} 메뉴`}>
      {nav.map((n) => (
        <Link
          key={n.path}
          to={n.path + location.search}
          aria-current={location.pathname === n.path ? 'page' : undefined}
        >
          {n.label}
        </Link>
      ))}
    </nav>
  )
  const footer = (
    <footer className="ws-footer">
      자체 제작 문항·가상 기록을 사용하는 시연입니다. 기록이 적다는 것이 능력 부족을 뜻하지는
      않습니다.
    </footer>
  )
  const expiredModal = expired && session && (
    <Modal title="다시 로그인해 주세요." onClose={() => {}}>
      <p>인증 갱신에 실패해 조회·변경을 중단했습니다. 저장된 기록은 유지됩니다.</p>
      <button
        className="cj-primary"
        onClick={() => {
          void leave().catch(() => {})
        }}
      >
        로그인 화면으로
      </button>
    </Modal>
  )
  if (variant === 'parent')
    return (
      <div id="class-journal">
        <div className="ws-shell ws-parent">
          <aside className="ws-side">
            <div className="ws-side-brand">
              <Brand />
              <span>{title}</span>
            </div>
            {menu}
            {aside}
          </aside>
          <div className="ws-body">
            {demo}
            <header className="ws-header">
              <div className="ws-header-actions">
                {actions}
                {logout}
              </div>
            </header>
            <main className="ws-main"><ServiceLinks role={session?.role} />{children}</main>
            {footer}
          </div>
          {expiredModal}
        </div>
      </div>
    )
  return (
    <div id="class-journal">
      <div className="ws-shell">
        <header className="ws-header">
          {session?.role !== 'STUDENT' && <Brand />}
          <span>{title}</span>
          <div className="ws-header-actions">
            {actions}
            {logout}
          </div>
        </header>
        {demo}
        {menu}
        <main className="ws-main"><ServiceLinks role={session?.role} />{children}</main>
        {footer}
        {expiredModal}
      </div>
    </div>
  )
}
export function QueryFeedback({
  query,
}: {
  query: { isPending: boolean; error: unknown; refetch: () => unknown }
}) {
  return (
    <>
      {query.isPending && <p role="status">불러오고 있습니다.</p>}
      <ErrorNotice
        error={query.error}
        retry={() => {
          void query.refetch()
        }}
      />
    </>
  )
}
export function MetricCards({ metrics }: { metrics: Metric[] }) {
  return (
    <div className="ws-metrics">
      {metrics.map((m, i) => (
        <article className="ws-card" key={i}>
          <h3>{m.label}</h3>
          <strong className="ws-number">{metricText(m)}</strong>
          <QueryStateNotice state={m.state} />
          <p>
            {m.period.from} ~ {m.period.to}
          </p>
          <details>
            <summary>계산 근거</summary>
            <p>
              분자 {m.numerator} · 분모 {m.denominator}
            </p>
            <p>{m.formula}</p>
            <p>출처: {m.sourceType}</p>
          </details>
        </article>
      ))}
    </div>
  )
}
export function EvidenceItems({ items }: { items: Evidence[] }) {
  return (
    <div className="ws-stack">
      {!items.length && <p>연결된 근거가 없습니다.</p>}
      {items.map((e, i) => (
        <article className="ws-card" key={i}>
          <strong>{e.missionTitle ?? '관련 미션'}</strong>
          <p>
            {e.kind === 'REFLECTION' ? '돌아보기' : `답변 ${e.answerVersion ?? '확인 전'}`} · {e.submittedAt ?? '시점 정보 없음'}
          </p>
          {e.available ? (
            <blockquote>{e.quote ?? '인용 정보 없음'}</blockquote>
          ) : (
            <p role="status">이용 불가 · 삭제된 근거입니다. 다른 기록으로 대체하지 않습니다.</p>
          )}
        </article>
      ))}
    </div>
  )
}
