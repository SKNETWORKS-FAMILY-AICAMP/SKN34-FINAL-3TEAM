import { useRef, useState } from 'react'
import { Activity, BookOpen, CalendarDays, ChevronRight, CreditCard, FilePenLine, History, LayoutDashboard, Layers, LogOut, Menu, MessagesSquare, Palette, RotateCcw, Search, ShieldCheck, SlidersHorizontal, TriangleAlert, Workflow, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
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
import { MissionDraftManager } from './MissionDraftManager.tsx'
import { ThemeDraftManager } from './ThemeDraftManager.tsx'
import { NotificationBell } from '../common/NotificationBell.tsx'
import { ErrorManager } from './ModelManager.tsx'
import { ModelRegistry } from './ModelRegistry.tsx'
import { SupportManager } from './SupportManager.tsx'
import { PaymentManager } from './PaymentManager.tsx'
import { LookItemManager, WeeklyThemeManager } from './RetentionManager.tsx'
import { PeriodPicker } from './PeriodPicker.tsx'
import '../classroom.css'
import '../common/workspace.css'
import './admin.css'
import './admin-design.css'
import './period-picker.css'

const permissionLabel: Record<Permission, string> = { CONTENT: '콘텐츠', SERVICE_OPS: '서비스 운영', PAYMENT_VIEW: '결제 조회', PAYMENT_REFUND: '환불 승인' }
const titles: Record<string, string> = { home: '운영 요약', jobs: '작업 목록', queues: '작업 대기열 현황', errors: '신고 검토', support: '문의 답변과 공지 관리', models: '모델·프롬프트 버전', usage: 'AI 호출량·비용', audit: '운영 조치·열람 이력', missions: '미션 목록', 'mission-drafts': '미션 초안 요청·검사', themes: '게시 관리', 'theme-drafts': '주간 테마 검수', looks: '꾸미기 아이템', payments: '거래와 환불 요청' }
const icons: Record<string, LucideIcon> = { home: LayoutDashboard, audit: History, jobs: RotateCcw, queues: Workflow, errors: TriangleAlert, support: MessagesSquare, models: Layers, usage: Activity, missions: BookOpen, 'mission-drafts': FilePenLine, themes: CalendarDays, 'theme-drafts': SlidersHorizontal, looks: Palette, payments: CreditCard }
export function AdminWorkspace() {
  const { session, setSession, setExpired } = useSession(), location = useLocation(), navigate = useNavigate()
  const [params, setParams] = useSearchParams(), cache = useQueryClient(), auth = useAuthentication()
  const [menuOpen, setMenuOpen] = useState(false), [scenario, setScenario] = useState('normal')
  const [menuSearch, setMenuSearch] = useState('')
  const menuButton = useRef<HTMLButtonElement>(null)
  const [defaultPeriod] = useState(() => calendarPeriods().recentPeriod)
  const permissions = session?.permissions ?? [], can = (p: Permission) => hasPermission(permissions, p)
  const page = location.pathname.split('/')[2] || 'home'
  const period = { from: params.get('from') ?? defaultPeriod.from, to: params.get('to') ?? defaultPeriod.to }
  const nav = [
    { group: '공통', path: 'home', label: '운영 현황', visible: true },
    { group: '공통', path: 'audit', label: '감사 이력', visible: true },
    { group: '콘텐츠', path: 'missions', label: '미션 관리', visible: can('CONTENT') },
    { group: '콘텐츠', path: 'mission-drafts', label: '미션 초안', visible: can('CONTENT') },
    { group: '콘텐츠', path: 'theme-drafts', label: '주간 테마 검수', visible: can('CONTENT') },
    { group: '콘텐츠', path: 'themes', label: '게시 관리', visible: can('CONTENT') },
    { group: '콘텐츠', path: 'looks', label: '꾸미기 아이템', visible: can('CONTENT') },
    ...[['jobs', '작업 재처리'], ['queues', '작업 대기열'], ['errors', '오류 신고'], ['support', '문의·공지'], ['models', '모델·프롬프트'], ['usage', 'AI 사용량']].map(([path, label]) => ({ group: '서비스 운영', path, label, visible: can('SERVICE_OPS') })),
    { group: '결제', path: 'payments', label: '결제·환불', visible: can('PAYMENT_VIEW') || can('PAYMENT_REFUND') },
  ].filter((n) => n.visible)
  const allowed = nav.some((n) => n.path === page) || page === 'queues' && can('SERVICE_OPS')
  const title = page === 'missions' && params.get('missionId') ? '미션 작성·검토' : titles[page] ?? '화면을 찾을 수 없습니다'
  const current = nav.find(n => n.path === page)
  const PageIcon = icons[page] ?? LayoutDashboard
  const menuAliases: Record<string,string> = { 'theme-drafts':'테마 초안 영상 비교', themes:'주간 테마 편성' }
  const filteredNav = nav.filter(n => `${n.label} ${n.group} ${menuAliases[n.path] ?? ''}`.includes(menuSearch.trim()))
  async function leave() {
    try { await auth.logout.mutateAsync() } finally {
      setSession(null); setExpired(false); cache.clear(); navigate('/admin/login', { replace: true })
    }
  }
  return <div id="class-journal"><div className="admin-shell" onKeyDown={e => {
    if (e.key === 'Escape' && menuOpen) { setMenuOpen(false); menuButton.current?.focus() }
  }}>
    <a className="ad-skip" href="#admin-main">본문으로 이동</a>
    <header className="ad-topbar">
      <div className="ad-location">
        <button ref={menuButton} className="ad-menu-toggle" aria-label={menuOpen ? '메뉴 닫기' : '메뉴'} aria-expanded={menuOpen} aria-controls="admin-navigation" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={20} /> : <Menu size={20} />}</button>
        <span>워크스페이스</span><ChevronRight size={14} aria-hidden="true" /><strong>{current?.label ?? title}</strong>
      </div>
      <div className="ad-account">{isDemo && <details className="ad-demo-tools"><summary>목업</summary><div className="ad-demo"><span>개발 목업 · 가상 운영 데이터</span><label>상태 시연 <select aria-label="상태 시연" value={scenario} onChange={(e) => {
        setScenario(e.target.value); window.dispatchEvent(new CustomEvent('sagomungchi:workspace-scenario', { detail: e.target.value })); void cache.invalidateQueries({ queryKey: ['admin'] })
      }}>{[['normal', '정상'], ['empty', '기록 없음'], ['query-fail', '조회 실패'], ['retry-fail', '재처리 실패'], ['publish-missing', '게시 누락'], ['forbidden', '권한 거부']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label></div></details>}<span className="ad-access"><ShieldCheck size={15} aria-hidden="true" />관리자</span>
        <NotificationBell />
        <button className="ad-logout" onClick={() => void leave().catch(() => {})}><LogOut size={15} aria-hidden="true" /><span>로그아웃</span></button>
      </div></header>
    {menuOpen && <button className="ad-nav-backdrop" aria-label="메뉴 바깥 닫기" onClick={() => { setMenuOpen(false); menuButton.current?.focus() }} />}
    <aside className={`ad-sidebar${menuOpen ? ' is-open' : ''}`} id="admin-navigation">
      <Link to="/admin/home" className="ad-brand" aria-label="사고뭉치 관리자 홈" onClick={() => setMenuOpen(false)}><Brand linked={false} /><span className="ad-brand-context">admin</span></Link>
      <label className="ad-nav-search"><Search size={16} aria-hidden="true" /><input aria-label="관리자 메뉴 찾기" placeholder="메뉴 찾기" value={menuSearch} onChange={e => setMenuSearch(e.target.value)} />{menuSearch && <button aria-label="메뉴 검색 지우기" onClick={() => setMenuSearch('')}><X size={14} /></button>}</label>
      <nav aria-label="관리자 메뉴">
      {filteredNav.map((n, i) => { const Icon = icons[n.path]; return <div key={n.path}>
        {(i === 0 || filteredNav[i - 1].group !== n.group) && <p className="ad-nav-group">{n.group}</p>}
        <Link to={`/admin/${n.path}?${new URLSearchParams({ ...period })}`} aria-current={page === n.path ? 'page' : undefined} onClick={() => setMenuOpen(false)}><Icon size={18} strokeWidth={1.7} aria-hidden="true" /><span>{n.label}</span></Link>
      </div> })}
      {!filteredNav.length && <p className="ad-nav-empty">일치하는 메뉴가 없습니다.</p>}
    </nav><div className="ad-sidebar-note"><span><ShieldCheck size={16} aria-hidden="true" />승인 권한</span><div>{permissions.length ? permissions.map(p => <span key={p}>{permissionLabel[p]}</span>) : '없음'}</div><details className="ad-permission-note"><summary>권한 안내</summary><p>콘텐츠·결제 권한으로 학생 답변 원문을 열람할 수 없습니다. 운영 조치는 감사 이력에 기록됩니다.</p></details></div></aside>
    <main id="admin-main" className="ad-main" data-page={page}>

      <div className="ad-page-heading"><div className="ad-page-title"><span className="ad-page-symbol"><PageIcon size={23} strokeWidth={1.7} aria-hidden="true" /></span><div><p>{current?.group === '공통' ? '워크스페이스' : current?.group}</p><h1>{title}</h1></div></div>
        {(['home', 'jobs', 'audit', 'usage'].includes(page) || page === 'payments' && ['payments', 'reconciliation'].includes(params.get('tab') ?? '')) && <PeriodPicker period={period} onApply={(p) => { const next = new URLSearchParams(params); next.set('from', p.from); next.set('to', p.to); setParams(next) }} />}
      </div>
      <div className="ad-page-content">
      {!allowed ? <section className="ad-panel"><h2>접근 권한 확인</h2><p role="alert">FORBIDDEN · 필요한 관리자 권한이 없습니다.</p><Link to="/admin/home">운영 현황으로 돌아가기</Link></section>
        : !validPeriod(period) ? <p role="alert">집계 기간을 확인해 주세요.</p>
        : page === 'missions' ? <MissionManager />
        : page === 'mission-drafts' ? <MissionDraftManager />
        : page === 'themes' ? <WeeklyThemeManager />
        : page === 'theme-drafts' ? <ThemeDraftManager />
        : page === 'looks' ? <LookItemManager />
        : page === 'models' ? <ModelRegistry />
        : page === 'errors' ? <ErrorManager />
        : page === 'support' ? <SupportManager />
        : page === 'payments' ? <PaymentManager period={period} permissions={permissions} />
        : <AdminOperations page={page} period={period} permissions={permissions} />}
      </div>
      <ErrorNotice error={auth.logout.error} />

    </main>
  </div></div>
}
