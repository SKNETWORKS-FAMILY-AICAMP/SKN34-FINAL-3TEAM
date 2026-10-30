import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { useSession } from './auth/sessionContext.ts'
import './student/pinpad.css'
import { roleStart } from '../domain/navigation.ts'
import { StudentWorld } from './student/world/StudentWorld.tsx'
import type { StudentPage } from './student/world/StudentWorld.tsx'
import { ThinkingMap } from './student/world/ThinkingMap.tsx'
import { StudentMissions } from './student/world/StudentMissions.tsx'
import { isThinkingType } from '../domain/studentLook.ts'
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  Lightbulb,
  LogOut,
  MessagesSquare,
  NotebookPen,
  Play,
  Shapes,
} from 'lucide-react'
import {
  useAuthentication,
  useChildren,
  useLearningActions,
  useMissions,
  useMission,
  useRecords,
  usePublicRecord,
  displayPeriods,
  isDemo,
  setDemoScenario,
  useMockInvalidation,
} from '../data/classroom/useClassroom.ts'
import { inputLabels, shortRange, thinkingLabels } from '../domain/classroom.ts'
import type { Child, DemoScenario, Period, PublicAttempt } from '../domain/classroom.ts'
import { ActivityPaper, Brand, ErrorNotice, Modal } from './shared/ClassroomParts.tsx'
import { StudentWorkPage } from './student/StudentWorkPage.tsx'
import { ParentAnalysis, ParentReport } from './parent/ParentFeatures.tsx'
import './classroom.css'
import { QueryStateNotice } from './common/QueryStateNotice.tsx'

const { recentPeriod, previousWeek } = displayPeriods
type Page = 'home' | 'journal' | 'missions' | 'report' | 'analysis'
export function ClassroomApp() {
  const auth = useAuthentication(),
    { session, setSession, selected, setSelected, expired, setExpired, scenario, setScenario } =
      useSession(),
    navigate = useNavigate(),
    location = useLocation()
  useMockInvalidation()
  const page = (location.pathname.split('/')[2] ?? 'journal') as Page
  const work = location.pathname.startsWith('/student/attempts/')
    ? location.pathname.split('/')[3]
    : null
  const studentPage: StudentPage = (['home', 'missions'] as const).find((p) => p === page) ?? 'journal'
  const typeFilter = new URLSearchParams(location.search).get('type')
  const setPage = (page: Page) => navigate(`/${session?.role.toLowerCase() ?? 'parent'}/${page}`)
  const setWork = (id: string | null) =>
    navigate(id ? `/student/attempts/${encodeURIComponent(id)}` : '/student/journal')
  const [detail, setDetail] = useState<PublicAttempt | null>(null)
  const [period, setPeriod] = useState<Period>(recentPeriod),
    [analysisPeriod, setAnalysisPeriod] = useState<Period>(recentPeriod)
  const [instructions, setInstructions] = useState<import('../domain/classroom.ts').Mission | null>(
    null,
  )
  const [email, setEmail] = useState(isDemo ? 'parent@example.test' : ''),
    [password, setPassword] = useState(isDemo ? 'demo-only' : '')
  const [subject, setSubject] = useState('all'),
    [message, setMessage] = useState(''),
    [showPlan, setShowPlan] = useState(false)
  const [evidenceId, setEvidenceId] = useState<string | null>(null)
  const children = useChildren(session?.role === 'PARENT'),
    child =
      session?.role === 'STUDENT'
        ? session.child
        : (children.data?.find((c) => c.id === selected) ?? children.data?.[0])
  const missions = useMissions(session?.role === 'STUDENT' ? child : undefined)
  const records = useRecords(child, session?.role === 'STUDENT' ? 'STUDENT' : 'PARENT', period)
  const sourceRecord = usePublicRecord(session?.role === 'PARENT' ? child : undefined, evidenceId, period)
  const learning = useLearningActions()
  async function login() {
    try {
      const next = await auth.login.mutateAsync({ email, password })
      setSession(next)
      setPassword('')
      navigate(roleStart(next.role), { replace: true })
      setSelected('')
    } catch {
      setPassword('')
    }
  }
  // 학생 → 학부모 화면 전환은 학부모 로그인을 다시 거친다 (FN-ACC-05). 학생 세션으로 학부모 화면을 열지 않는다.
  async function leave() {
    try {
      await auth.logout.mutateAsync()
    } catch {
      /* 세션은 항상 정리, 시연 데이터로 대체하지 않는다. */
    } finally {
      setSession(null)
      setExpired(false)
      navigate('/login', { replace: true })
      setDetail(null)
      setPassword(isDemo ? 'demo-only' : '')
    }
  }
  async function enter(c: Child) {
    try {
      setSession(await auth.enter.mutateAsync(c))
      navigate('/student/home')
      setDetail(null)
    } catch {
      /* mutation 오류를 화면에 표시 */
    }
  }
  async function start(mission: import('../domain/classroom.ts').Mission) {
    if (!child) return
    try {
      const a = await learning.start.mutateAsync({ mission, child })
      setWork(a.attemptId)
      setInstructions(null)
    } catch {
      /* 시작 실패를 시작 전/빈 화면으로 숨기지 않는다. */
    }
  }
  const rows = records.data?.filter((a) => subject === 'all' || a.mission.subject === subject) ?? []
  const subjects = [
    ...new Set((missions.data ?? records.data?.map((a) => a.mission) ?? []).map((m) => m.subject)),
  ]
  const menu: { page: Page; label: string; icon: typeof NotebookPen }[] =
    session?.role === 'STUDENT'
      ? [
          { page: 'home', label: '학습 홈', icon: BookOpen },
          { page: 'journal', label: '내 공책', icon: NotebookPen },
          { page: 'missions', label: '미션', icon: Shapes },
        ]
      : [
          { page: 'journal', label: '아이의 공책', icon: NotebookPen },
          { page: 'report', label: '주간 리포트', icon: BookOpen },
          { page: 'analysis', label: '기록에 물어보기', icon: MessagesSquare },
        ]
  const switchChild = (id: string) => {
    setSelected(id)
    setDetail(null)
    setEvidenceId(null)
    setSubject('all')
    setAnalysisPeriod(recentPeriod)
    setMessage('')
  }
  const evidence = (id: string) => setEvidenceId(id)
  return (
    <div id="class-journal">
      <div className="ux-preview">
        <span>
          {isDemo
            ? 'MSW 목업 모드 · 실제 API 요청을 가로채는 가상 응답 · 운영 서버 호출 없음'
            : 'API 연결 모드 · core 공개 API만 호출 · 오류 시 예시 데이터 대체 없음'}
        </span>
        {isDemo && (
          <label>
            상태 시연
            <select
              aria-label="상태 시연"
              value={scenario}
              onChange={(e) => {
                const s = e.target.value as DemoScenario
                setScenario(s)
                setDemoScenario(s)
              }}
            >
              {[
                ['normal', '정상 흐름'],
                ['draft-fail', '초안 저장 실패'],
                ['draft-conflict', '초안 충돌'],
                ['submit-fail', '답변 저장 실패'],
                ['ai-fail', '피드백 처리 실패'],
                ['ai-fail-final', '피드백 처리 실패(다시 요청 불가)'],
                ['held', '판정 보류'],
                ['bank', '질문 은행'],
                ['report-fail', '리포트 생성 실패'],
                ['correct', '정답'],
                ['partial', '부분 정답'],
                ['rethink', '다시 생각'],
                ['running', 'RUNNING 응답 후 재조회'],
                ['finish-unmet', '마무리 조건 미충족'],
                ['home-empty', '홈 기록 없음'],
                ['home-processing', '홈 처리 중'],
                ['home-small', '홈 표본 부족'],
                ['home-fail', '홈 조회 실패'],
                ['input-fixtures', '6종 입력 시험 문항'],
                ['token-expired', '토큰 만료·갱신'],
                ['refresh-fail', '갱신 실패·재로그인'],
              ].map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        )}
        <small>develop 66f6052 기준 · PC 정식 / 태블릿 확장 시안</small>
      </div>
      <div className={session?.role === 'STUDENT' ? 'cj-app cj-app-student' : 'cj-app'}>
        {expired && session && (
          <Modal title="다시 로그인해 주세요." onClose={() => {}}>
            <p>
              인증 갱신에 실패하여 기록 조회·변경을 중단했습니다. 저장된 답변과 초안은 유지됩니다.
            </p>
            <p>아직 저장하지 못한 입력이 있다면 이 화면을 나가기 전에 별도로 보관해 주세요.</p>
            <button
              className="cj-primary"
              type="button"
              onClick={() => {
                void leave()
              }}
            >
              로그인 화면으로
            </button>
          </Modal>
        )}
        {!session ? (
          <main className="ux-login">
            <div className="ux-login-intro">
              <Brand />
              <h1>
                내 생각을 남기고,
                <br />
                공책에서 다시 만나요.
              </h1>
              <p>
                학생 별도 계정 없이, 보호자가 등록한 기기에서 PIN으로<br />
                들어오거나 학부모 로그인 후 자녀를 골라 시작합니다.
              </p>
              <button
                type="button"
                className="cj-secondary"
                onClick={() => navigate('/student/login')}
              >
                자녀 기기로 시작하기 (PIN)
              </button>
              <span className="cj-tag">초등 3~6학년</span>
              <p className="ux-help">
                {isDemo
                  ? '화면 시연용 계정입니다. 실제 이메일·아동 개인정보를 입력하지 마세요.'
                  : 'Google 계정으로 로그인하고 자녀를 등록해 주세요.'}
              </p>
            </div>
            {!isDemo ? (
              <section className="ux-login-form">
                <h2>학부모·관리자 로그인</h2>
                <a className="cj-primary" href="/api/v1/auth/google/authorize">Google 계정으로 계속하기</a>
                <nav className="ux-login-links" aria-label="로그인 도움 메뉴">
                  <Link to="/login-help">로그인 도움말</Link>
                  <Link to="/admin/login">관리자 로그인</Link>
                </nav>
                <p>처음 로그인하면 이용 동의와 자녀 등록을 진행합니다.</p>
                {new URLSearchParams(location.search).has('oauthError') &&
                  <p role="alert">{new URLSearchParams(location.search).get('oauthError') === 'CANCELLED'
                    ? 'Google 로그인을 취소했습니다.' : 'Google 로그인을 완료하지 못했습니다. 다시 시도해 주세요.'}</p>}
              </section>
            ) : <form
              className="ux-login-form"
              onSubmit={(e) => {
                e.preventDefault()
                void login()
              }}
            >
              <h2>학부모 로그인</h2>
              <label className="cj-field">
                이메일
                <input
                  aria-label="이메일"
                  type="email"
                  autoComplete={isDemo ? 'off' : 'username'}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </label>
              <label className="cj-field">
                비밀번호
                <input
                  aria-label="비밀번호"
                  type="password"
                  autoComplete={isDemo ? 'off' : 'current-password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </label>
              <button className="cj-primary" type="submit" disabled={auth.login.isPending}>
                {auth.login.isPending ? '확인 중' : isDemo ? '시연 계정으로 로그인' : '로그인'}
                <ArrowRight />
              </button>
              <ErrorNotice error={auth.login.error} />
              <nav className="ux-login-links" aria-label="로그인 도움 메뉴">
                  <Link to="/login-help">로그인 도움말</Link>
                  <Link to="/admin/login">관리자 로그인</Link>
                </nav>
              <button type="button" className="cj-secondary ux-login-signup" onClick={() => navigate('/signup')}>
                처음이신가요? 이용 등록
              </button>
              {isDemo && (
                <small className="ux-login-demo-note">
                  관리자 시연: admin / content / ops / payment / refund@example.test · 비밀번호
                  demo-only
                </small>
              )}
            </form>}
          </main>
        ) : session.role === 'ADMIN' ? (
          <main className="cj-sheet">
            <h1>관리자 운영 화면</h1>
            <p>
              현재 작업은 학생·학부모 UX 범위입니다. 운영 권한이나 학생 원문 접근을 임의로 부여하지
              않습니다.
            </p>
            <button
              className="cj-secondary"
              type="button"
              onClick={() => {
                void leave()
              }}
            >
              로그아웃
            </button>
          </main>
        ) : session.role === 'STUDENT' && child ? (
          <StudentWorld
            child={child}
            page={work ? null : studentPage}
            focus={!!work}
            onNavigate={(p) => {
              setPage(p)
              setDetail(null)
            }}
            onLeave={() => {
              void leave()
            }}
          >
            {work ? (
              <StudentWorkPage
                key={work}
                attemptId={work}
                onBack={() => {
                  setWork(null)
                  setPage('journal')
                }}
              />
            ) : studentPage === 'home' ? (
              <ThinkingMap
                child={child}
                onResume={setWork}
                onOpen={setInstructions}
                onType={(t) => navigate(`/student/missions?type=${t}`)}
                onJournal={() => setPage('journal')}
              />
            ) : studentPage === 'missions' ? (
              <StudentMissions
                child={child}
                type={isThinkingType(typeFilter) ? typeFilter : null}
                onType={(t) => navigate(t ? `/student/missions?type=${t}` : '/student/missions')}
                onOpen={setInstructions}
              />
            ) : detail ? (
              <main className="st-paper st-sheet">
                <RecordDetail record={detail} child={child} onClose={() => setDetail(null)} />
              </main>
            ) : (
              <main className="st-paper st-sheet">
                <div className="cj-feedbar">
                  <h1>
                    <NotebookPen />
                    나의 공책
                  </h1>
                  <div className="cj-filters">
                    <select
                      aria-label="과목 필터"
                      value={subject}
                      onChange={(e) => setSubject(e.target.value)}
                    >
                      <option value="all">모든 과목</option>
                      {subjects.map((s) => (
                        <option key={s}>{s}</option>
                      ))}
                    </select>
                    <select
                      aria-label="공책 기간"
                      value={period.from}
                      onChange={(e) =>
                        setPeriod(e.target.value === recentPeriod.from ? recentPeriod : previousWeek)
                      }
                    >
                      <option value={recentPeriod.from}>최근 7일 · {shortRange(recentPeriod)}</option>
                      <option value={previousWeek.from}>지난주 · {shortRange(previousWeek)}</option>
                    </select>
                  </div>
                </div>
                <div className="cj-feed">
                  {records.isPending && (
                    <QueryStateNotice state="PROCESSING">기록을 읽는 중입니다.</QueryStateNotice>
                  )}
                  <ErrorNotice
                    error={records.error}
                    retry={() => {
                      void records.refetch()
                    }}
                  />
                  {records.isSuccess && rows.length === 0 && (
                    <QueryStateNotice state="NO_RECORD">
                      이 기간·과목에 제출한 답변이 없습니다.
                      <button type="button" className="cj-primary" onClick={() => setPage('missions')}>
                        첫 미션 고르기
                      </button>
                    </QueryStateNotice>
                  )}
                  {rows.map((r) => (
                    <RecordCard
                      key={r.attemptId}
                      record={r}
                      child={child}
                      onDetail={() => setDetail(r)}
                      onContinue={() => setWork(r.attemptId)}
                    />
                  ))}
                </div>
              </main>
            )}
          </StudentWorld>
        ) : (
          <>
            <header className="cj-top">
              <div className="cj-top-left">
                <button
                  type="button"
                  className="cj-brand"
                  onClick={() => {
                    setPage('journal')
                    setDetail(null)
                  }}
                >
                  <Brand />
                </button>
                {session.role === 'PARENT' ? (
                  <select
                    className="ux-child-select"
                    aria-label="자녀 선택"
                    value={child?.id ?? ''}
                    onChange={(e) => switchChild(e.target.value)}
                  >
                    {children.data?.map((c) => (
                      <option value={c.id} key={c.id}>
                        {c.nickname} · 초{c.grade}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span className="cj-top-context">{child?.nickname}의 학습 공간</span>
                )}
              </div>
              <div className="cj-top-right">
                {menu.map((m) => (
                  <button
                    type="button"
                    key={m.page}
                    className="cj-plain"
                    aria-pressed={page === m.page && !detail}
                    onClick={() => {
                      setPage(m.page)
                      setDetail(null)
                    }}
                  >
                    <m.icon />
                    <span>{m.label}</span>
                  </button>
                ))}
                <button
                  type="button"
                  className="cj-plain"
                  aria-label={session.role === 'STUDENT' ? '학부모 로그인으로' : '로그아웃'}
                  onClick={() => {
                    void leave()
                  }}
                >
                  <LogOut />
                </button>
              </div>
            </header>
            <div className="cj-shell">
              <main className="cj-main">
                <ErrorNotice
                  error={children.error}
                  retry={() => {
                    void children.refetch()
                  }}
                />
                {children.isPending && session.role === 'PARENT' && (
                  <div role="status" className="cj-empty">
                    연결된 자녀를 확인하는 중입니다.
                  </div>
                )}
                {session.role === 'PARENT' && children.data?.length === 0 && (
                  <div className="cj-empty">
                    등록된 자녀가 없습니다. 자녀 등록은 별명·학년·출생연도·법정대리인 동의가
                    필요하며 최대 3명입니다.
                  </div>
                )}
                {message && (
                  <div className="ux-help" role="status">
                    {message}
                  </div>
                )}
                {child && detail ? (
                  <RecordDetail record={detail} child={child} onClose={() => setDetail(null)} />
                ) : child && page === 'report' && session.role === 'PARENT' ? (
                  <ParentReport
                    key={child.id}
                    child={child}
                    onEvidence={evidence}
                    onAnalysis={(p) => {
                      setAnalysisPeriod(p)
                      setPage('analysis')
                    }}
                  />
                ) : child && page === 'analysis' && session.role === 'PARENT' ? (
                  <ParentAnalysis
                    key={`${child.id}:${analysisPeriod.from}:${analysisPeriod.to}`}
                    child={child}
                    period={analysisPeriod}
                    onEvidence={evidence}
                  />
                ) : (
                  <>
                    <div className="cj-feedbar">
                      <h1>
                        {page === 'missions' ? <Shapes /> : <NotebookPen />}
                        {page === 'missions'
                          ? '미션'
                          : session.role === 'STUDENT'
                            ? '나의 공책'
                            : '아이의 공책'}
                      </h1>
                      <div className="cj-filters">
                        <select
                          aria-label="과목 필터"
                          value={subject}
                          onChange={(e) => setSubject(e.target.value)}
                        >
                          <option value="all">모든 과목</option>
                          {subjects.map((s) => (
                            <option key={s}>{s}</option>
                          ))}
                        </select>
                        {page !== 'missions' && (
                          <select
                            aria-label="공책 기간"
                            value={period.from}
                            onChange={(e) =>
                              setPeriod(
                                e.target.value === recentPeriod.from ? recentPeriod : previousWeek,
                              )
                            }
                          >
                            <option value={recentPeriod.from}>
                              최근 7일 · {shortRange(recentPeriod)}
                            </option>
                            <option value={previousWeek.from}>
                              지난주 · {shortRange(previousWeek)}
                            </option>
                          </select>
                        )}
                      </div>
                    </div>
                    <div className="cj-feed">
                      {session.role === 'PARENT' && child && (
                        <div className="ux-parent-entry">
                          <span>
                            <strong>{child.nickname}</strong> · 초등 {child.grade}학년 ·{' '}
                            {child.plan === 'FREE' ? '무료' : child.plan === 'PREMIUM' ? '프리미엄' : '이용권 확인 필요'}
                          </span>
                          <button
                            type="button"
                            className="cj-primary"
                            disabled={auth.enter.isPending}
                            onClick={() => {
                              void enter(child)
                            }}
                          >
                            <Play />이 자녀로 학습 시작
                          </button>
                          <ErrorNotice error={auth.enter.error} />
                        </div>
                      )}
                      {page === 'missions' ? (
                        <>
                          {missions.isPending && (
                            <div className="cj-empty" role="status">
                              공개 미션을 읽는 중입니다.
                            </div>
                          )}
                          <ErrorNotice
                            error={missions.error}
                            retry={() => {
                              void missions.refetch()
                            }}
                          />
                          {missions.data
                            ?.filter((m) => subject === 'all' || m.subject === subject)
                            .map((m) => (
                              <article className="cj-post cj-activity" key={m.id}>
                                <div className="cj-thumb">
                                  <ActivityPaper mission={m} />
                                </div>
                                <div>
                                  <span className="cj-badge">
                                    {m.subject} · {thinkingLabels[m.thinkingType]} ·{' '}
                                    {inputLabels[m.inputType]}
                                  </span>
                                  <h2>{m.title}</h2>
                                  <p className="ux-mission-position">
                                    활동 {m.position} / {m.total} ·{' '}
                                    {m.status === 'COMPLETED'
                                      ? '완료'
                                      : m.status === 'IN_PROGRESS'
                                        ? '진행 중'
                                        : '시작 전'}
                                  </p>
                                  <p>{m.question}</p>
                                  <button
                                    type="button"
                                    className="cj-primary"
                                    onClick={() => setInstructions(m)}
                                  >
                                    미션 열기 <ArrowRight />
                                  </button>
                                </div>
                              </article>
                            ))}
                        </>
                      ) : (
                        <>
                          {records.isPending && (
                            <QueryStateNotice state="PROCESSING">
                              기록을 읽는 중입니다.
                            </QueryStateNotice>
                          )}
                          <ErrorNotice
                            error={records.error}
                            retry={() => {
                              void records.refetch()
                            }}
                          />
                          {records.isSuccess && rows.length === 0 && (
                            <QueryStateNotice state="NO_RECORD">
                              이 기간·과목에 제출한 답변이 없습니다.
                              {session.role === 'STUDENT' && (
                                <button
                                  type="button"
                                  className="cj-primary"
                                  onClick={() => setPage('missions')}
                                >
                                  첫 미션 고르기
                                </button>
                              )}
                            </QueryStateNotice>
                          )}
                          {rows.map((r) => (
                            <RecordCard
                              key={r.attemptId}
                              record={r}
                              child={child!}
                              onDetail={() => setDetail(r)}
                              onContinue={
                                session.role === 'STUDENT' ? () => setWork(r.attemptId) : undefined
                              }
                            />
                          ))}
                        </>
                      )}
                    </div>
                  </>
                )}
              </main>
              <aside className="cj-rail">
                <div className="cj-rail-avatar">{child?.nickname[0] ?? '나'}</div>
                <div className="cj-rail-title">
                  <h2>{child?.nickname ?? '자녀'}의 공책</h2>
                  <p>
                    {child
                      ? `초등 ${child.grade}학년 · ${session.role === 'STUDENT' ? '학생' : '학부모'}`
                      : '자녀 선택'}
                  </p>
                </div>
                {session.role === 'STUDENT' && (
                  <button
                    type="button"
                    className="cj-add"
                    onClick={() => {
                      setPage('missions')
                      setDetail(null)
                    }}
                  >
                    <Shapes />
                    미션 고르기
                  </button>
                )}
                <nav className="cj-rail-nav" aria-label="교실 메뉴">
                  {menu.map((m) => (
                    <button
                      type="button"
                      key={m.page}
                      aria-current={page === m.page ? 'page' : undefined}
                      onClick={() => {
                        setPage(m.page)
                        setDetail(null)
                      }}
                    >
                      <m.icon />
                      {m.page === 'home'
                        ? '홈'
                        : m.page === 'analysis'
                          ? '물어보기'
                          : m.page === 'journal'
                            ? '공책'
                            : m.page === 'report'
                              ? '리포트'
                              : '미션'}
                    </button>
                  ))}
                </nav>
                <div className="cj-rail-label">다섯 가지 생각 활동</div>
                <div className="cj-subjects">
                  {Object.values(thinkingLabels).map((t, i) => (
                    <div className="cj-subject" key={t}>
                      <i>{i + 1}</i>
                      {t}
                    </div>
                  ))}
                </div>
                <p className="cj-rail-note">
                  {session.role === 'STUDENT'
                    ? '처음 답과 덧붙인 답은 따로 남아요. 생각 메모는 나만 볼 수 있어요.'
                    : '자녀를 바꾸면 기록·대화·리포트의 대상도 함께 바뀝니다.'}
                </p>
                {child && session.role === 'PARENT' && (
                  <button type="button" className="cj-plain" onClick={() => setShowPlan(true)}>
                    이용권 안내
                  </button>
                )}
              </aside>
            </div>
            <footer className="cj-app-foot">
              <span>
                {child?.nickname} · {period.from}~{period.to} · 관찰 기록이지 사고력 진단이
                아닙니다.
              </span>
              <span>초안·제출·피드백·완료 상태를 구분합니다.</span>
            </footer>
          </>
        )}
        {instructions && child && (
          <MissionInstructions
            id={instructions.id}
            child={child}
            onClose={() => setInstructions(null)}
            onStart={start}
            pending={learning.start.isPending}
            error={learning.start.error}
          />
        )}
        {evidenceId && child && session?.role === 'PARENT' && (
          <Modal title="인용한 학습 원문" onClose={() => setEvidenceId(null)}>
            {sourceRecord.isPending && <p role="status">이 자녀의 원문을 확인합니다.</p>}
            <ErrorNotice
              error={sourceRecord.error}
              retry={() => {
                void sourceRecord.refetch()
              }}
            />
            {sourceRecord.data && (
              <RecordDetail
                record={sourceRecord.data}
                child={child}
                onClose={() => setEvidenceId(null)}
              />
            )}
          </Modal>
        )}
        {showPlan && (
          <Modal title="이용권 안내 · 테스트 범위" onClose={() => setShowPlan(false)}>
            <p>무료: 자녀별 하루 미션 3개, 리포트 수치 제공.</p>
            <p>프리미엄: 자녀별 월 14,900원, 하루 피드백 50회·분석 대화 30회, 전체 리포트.</p>
            <p className="ux-help">
              현재 develop에는 상품·결제 공개 Controller가 아직 없습니다. 이 화면은 정책 안내이며
              결제를 요청하거나 카드 정보를 받지 않습니다. 결제 구현은 토스 테스트 환경만
              대상입니다.
            </p>
          </Modal>
        )}
      </div>
      <div className="cj-announcement" role="status">
        {isDemo
          ? '실제 아동 정보·음성·AI Hub 원본을 사용하지 않는 UX 검증용 예시입니다.'
          : '인증 토큰은 메모리에만 보관합니다. 내부 서비스에는 브라우저가 직접 연결하지 않습니다.'}
      </div>
    </div>
  )
}
function MissionInstructions({
  id,
  child,
  onClose,
  onStart,
  pending,
  error,
}: {
  id: string
  child: Child
  onClose: () => void
  onStart: (m: import('../domain/classroom.ts').Mission) => Promise<void>
  pending: boolean
  error: unknown
}) {
  const query = useMission(id, child),
    m = query.data
  return (
    <Modal title={m?.title ?? '미션 안내'} onClose={onClose}>
      {query.isPending && <p role="status">질문과 입력 틀을 확인하는 중입니다.</p>}
      <ErrorNotice
        error={query.error}
        retry={() => {
          void query.refetch()
        }}
      />
      {m && (
        <>
          <span className="cj-badge">
            초{m.grade} · {inputLabels[m.inputType]}
          </span>
          <ActivityPaper mission={m} />
          <p>{m.question}</p>
          <p className="ux-help">
            미션에서 정한 답변 틀을 사용해 주세요. 메모는 제출 답변과 별도입니다.
          </p>
          <ErrorNotice error={error} />
          <div className="cj-modal-actions">
            <button
              type="button"
              className="cj-primary"
              disabled={pending}
              onClick={() => {
                void onStart(m)
              }}
            >
              작성하기 · 진행 중이면 이어서
            </button>
          </div>
        </>
      )}
    </Modal>
  )
}
function RecordCard({
  record: r,
  child,
  onDetail,
  onContinue,
}: {
  record: PublicAttempt
  child: Child
  onDetail: () => void
  onContinue?: () => void
}) {
  const latest = r.answers.at(-1)
  return (
    <article className="cj-post">
      <header className="cj-post-head">
        <div className="cj-author">
          <span className="cj-avatar">{child.nickname[0]}</span>
          <span>
            {child.nickname}
            <small>
              {latest?.submittedAt.slice(0, 10)} ·{' '}
              {r.status === 'COMPLETED' ? '완료' : r.finishedAt ? '돌아보기 대기' : '진행 중'}
            </small>
          </span>
        </div>
        <button type="button" className="cj-plain" onClick={onDetail} aria-label="전체 과정 보기">
          <ArrowUpRight />
        </button>
      </header>
      <div className="cj-post-context">
        {r.mission.subject} · {r.mission.title}
      </div>
      <button
        type="button"
        className="cj-post-art"
        onClick={onDetail}
        aria-label="작업물 크게 보기"
      >
        <ActivityPaper mission={r.mission} text={latest?.text} />
      </button>
      <p className="cj-caption">{latest?.text}</p>
      <div className="cj-post-tags">
        <span className="cj-tag">{thinkingLabels[r.mission.thinkingType]}</span>
        <span>
          {r.reflection
            ? `돌아보기 · ${r.reflection.text || r.reflection.difficulty}`
            : '아직 돌아보기를 남기지 않았어요.'}
        </span>
      </div>
      <footer className="cj-post-actions">
        <button type="button" className="cj-plain" onClick={onDetail}>
          <MessagesSquare />
          처음 답·질문·추가 답
        </button>
        {onContinue && r.status === 'IN_PROGRESS' ? (
          <button type="button" className="cj-primary" onClick={onContinue}>
            이어서 하기
          </button>
        ) : (
          <span className="cj-badge">
            <Check />
            기록 보기
          </span>
        )}
      </footer>
      {latest?.feedback.followup && !r.finishedAt && (
        <div className="cj-comment">
          <span className="cj-avatar">?</span>
          <div>
            <strong>
              추가 질문 ·{' '}
              {isDemo
                ? '시연 예시'
                : latest.feedback.followup.source === 'BANK'
                  ? '질문 은행'
                  : 'AI'}
            </strong>
            <p>{latest.feedback.followup.question}</p>
          </div>
        </div>
      )}
    </article>
  )
}
function RecordDetail({
  record,
  child,
  onClose,
}: {
  record: PublicAttempt
  child: Child
  onClose: () => void
}) {
  return (
    <div className="cj-feed">
      <button type="button" className="cj-back" onClick={onClose}>
        <ArrowLeft />
        돌아가기
      </button>
      <article className="cj-sheet">
        <small>
          {child.nickname} · {record.mission.subject} · 학습 당시 초{record.mission.grade}
        </small>
        <h2>{record.mission.title}</h2>
        {record.answers.map((a) => (
          <section className="cj-version" key={a.answerId}>
            <small>
              답변 {a.version} · {a.submittedAt}
            </small>
            <p className="cj-quote">{a.text}</p>
            {a.feedback.followup && (
              <div className="ux-help">
                <Lightbulb />
                {a.feedback.followup.question}
              </div>
            )}
            <small>
              피드백 처리 {a.feedback.status}
              {a.feedback.judgment
                ? ` · ${a.feedback.judgment.result === 'HELD' ? '판정 보류' : '판정 결과 있음'}`
                : ''}
            </small>
          </section>
        ))}
        <h3>돌아보기</h3>
        <p>
          {record.reflection
            ? `${record.reflection.difficulty} · ${record.reflection.text || '별도 문장 없음'}`
            : '아직 작성하지 않았어요.'}
        </p>
        <small>생각 메모는 이 학습 원문 조회에 포함되지 않습니다.</small>
      </article>
    </div>
  )
}
