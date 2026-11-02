import { useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useSession } from '../auth/sessionContext.ts'
import { hasPermission } from '../../domain/admin/operations.ts'
import type { Permission } from '../../domain/admin/operations.ts'
import { isDemo, useAuthentication } from '../../data/classroom/useClassroom.ts'
import { calendarPeriods } from '../../domain/classroom.ts'
import { validPeriod } from '../../domain/parent.ts'
import { Brand, ErrorNotice } from '../shared/ClassroomParts.tsx'
import { AdminOperations } from './AdminOperations.tsx'
import { MissionManager } from './MissionManager.tsx'
import { ErrorManager } from './ModelManager.tsx'
import { ModelRegistry } from './ModelRegistry.tsx'
import { SupportManager } from './SupportManager.tsx'
import { PaymentManager } from './PaymentManager.tsx'
import '../classroom.css'
import '../common/workspace.css'
import './admin.css'

const permissionLabel: Record<Permission, string> = { CONTENT: '콘텐츠', SERVICE_OPS: '서비스 운영', PAYMENT_VIEW: '결제 조회', PAYMENT_REFUND: '환불 승인' }
const titles: Record<string, string> = { home: '운영 요약', jobs: '작업 목록', queues: '큐·DLQ 현황', errors: '신고 검토', support: '문의 답변과 공지 관리', models: '버전 관리', usage: 'AI 호출량·비용', audit: '운영 조치·열람 이력', missions: '미션 목록', payments: '거래와 환불 요청' }
export function AdminWorkspace() {
  const { session, setSession, setExpired } = useSession(), location = useLocation(), navigate = useNavigate()
  const [params, setParams] = useSearchParams(), cache = useQueryClient(), auth = useAuthentication()
  const [menuOpen, setMenuOpen] = useState(false), [scenario, setScenario] = useState('normal')
  const [defaultPeriod] = useState(() => calendarPeriods().recentPeriod)
  const permissions = session?.permissions ?? [], can = (p: Permission) => hasPermission(permissions, p)
  const page = location.pathname.split('/')[2] || 'home'
  const period = { from: params.get('from') ?? defaultPeriod.from, to: params.get('to') ?? defaultPeriod.to }
  const nav = [
    { group: '공통', path: 'home', label: '운영 현황', visible: true },
    { group: '공통', path: 'audit', label: '감사 이력', visible: true },
    ...[['jobs', '작업 재처리'], ['queues', '큐·DLQ'], ['errors', '오류 신고'], ['support', '문의·공지'], ['models', '모델·프롬프트'], ['usage', 'AI 사용량']].map(([path, label]) => ({ group: '서비스 운영', path, label, visible: can('SERVICE_OPS') })),
    { group: '콘텐츠', path: 'missions', label: '미션 관리', visible: can('CONTENT') },
    { group: '결제', path: 'payments', label: '결제·환불', visible: can('PAYMENT_VIEW') || can('PAYMENT_REFUND') },
  ].filter((n) => n.visible)
  const allowed = nav.some((n) => n.path === page) || page === 'queues' && can('SERVICE_OPS')
  const title = page === 'missions' && params.get('missionId') ? '미션 작성·검토' : titles[page] ?? '화면을 찾을 수 없습니다'
  async function leave() {
    try { await auth.logout.mutateAsync() } finally {
      setSession(null); setExpired(false); cache.clear(); navigate('/admin/login', { replace: true })
    }
  }
  return <div id="class-journal"><div className="admin-shell">
    <a className="ad-skip" href="#admin-main">본문으로 이동</a>
    <header className="ad-topbar"><Link to="/admin/home" className="ad-brand" aria-label="사고뭉치 관리자 홈"><Brand /><span className="ad-brand-context">운영 관리</span></Link>
      <div className="ad-account"><span>승인 권한 · {permissions.map((p) => permissionLabel[p]).join(' · ') || '없음'}</span>
        <button onClick={() => void leave().catch(() => {})}>로그아웃</button>
        <button className="ad-menu-toggle" aria-expanded={menuOpen} aria-controls="admin-navigation" onClick={() => setMenuOpen(!menuOpen)}>메뉴</button>
      </div></header>
    <aside className={`ad-sidebar${menuOpen ? ' is-open' : ''}`} id="admin-navigation"><nav aria-label="관리자 메뉴">
      {nav.map((n, i) => <div key={n.path}>
        {(i === 0 || nav[i - 1].group !== n.group) && <p className="ad-nav-group">{n.group}</p>}
        <Link to={`/admin/${n.path}?${new URLSearchParams({ ...period })}`} aria-current={page === n.path ? 'page' : undefined} onClick={() => setMenuOpen(false)}>{n.label}</Link>
      </div>)}
    </nav><p className="ad-sidebar-note">사고뭉치 관리자<br />업무별 승인 권한으로 이용합니다.</p></aside>
    <main id="admin-main" className="ad-main">
      {isDemo && <div className="ad-demo"><span>개발 목업 · 가상 운영 데이터</span><label>상태 시연 <select aria-label="상태 시연" value={scenario} onChange={(e) => {
        setScenario(e.target.value); window.dispatchEvent(new CustomEvent('sagomungchi:workspace-scenario', { detail: e.target.value })); void cache.invalidateQueries({ queryKey: ['admin'] })
      }}>{[['normal', '정상'], ['empty', '기록 없음'], ['query-fail', '조회 실패'], ['retry-fail', '재처리 실패'], ['publish-missing', '게시 누락'], ['forbidden', '권한 거부']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label></div>}
      <div className="ad-page-heading"><div><p className="ad-breadcrumb">관리자 / {nav.find((n) => n.path === page)?.label ?? title}</p><h1>{title}</h1></div>
        {['home', 'jobs', 'audit', 'usage', 'payments'].includes(page) && <PeriodPicker key={`${period.from}:${period.to}`} period={period} onApply={(p) => { const next = new URLSearchParams(params); next.set('from', p.from); next.set('to', p.to); setParams(next) }} />}
      </div>
      {!allowed ? <section className="ad-panel"><h2>접근 권한 확인</h2><p role="alert">FORBIDDEN · 필요한 관리자 권한이 없습니다.</p><Link to="/admin/home">운영 현황으로 돌아가기</Link></section>
        : !validPeriod(period) ? <p role="alert">집계 기간을 확인해 주세요.</p>
        : page === 'missions' ? <MissionManager />
        : page === 'models' ? <ModelRegistry />
        : page === 'errors' ? <ErrorManager />
        : page === 'support' ? <SupportManager />
        : page === 'payments' ? <PaymentManager period={period} permissions={permissions} />
        : <AdminOperations page={page} period={period} permissions={permissions} />}
      <ErrorNotice error={auth.logout.error} />
      <footer className="ad-footer">콘텐츠·결제 권한으로 학생 답변 원문을 열람할 수 없습니다. 운영 조치는 감사 이력에 기록됩니다.</footer>
    </main>
  </div></div>
}
function PeriodPicker({ period, onApply }: { period: { from: string; to: string }; onApply: (p: { from: string; to: string }) => void }) {
  const [from, setFrom] = useState(period.from), [to, setTo] = useState(period.to), [error, setError] = useState('')
  return <form className="ad-period" onSubmit={(e) => { e.preventDefault(); if (!validPeriod({ from, to })) { setError('집계 기간을 확인해 주세요.'); return }; setError(''); onApply({ from, to }) }}>
    <label><span className="ad-sr">집계 시작일</span><input aria-label="집계 시작일" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label><span>—</span>
    <label><span className="ad-sr">집계 종료일</span><input aria-label="집계 종료일" type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label><button>기간 적용</button>
    {error && <p role="alert">{error}</p>}
  </form>
}
