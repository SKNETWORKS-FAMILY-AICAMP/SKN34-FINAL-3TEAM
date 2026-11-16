import { useEffect, useMemo, useRef } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { useStudentLook } from '../../../data/studentLook/queries.ts'
import { useLookItems } from '../../../data/retention/queries.ts'
import { wornAssets } from '../../../domain/retention.ts'
import { DEFAULT_LOOK, THEMES } from '../../../domain/studentLook.ts'
import type { Theme } from '../../../domain/studentLook.ts'
import type { Child } from '../../../domain/classroom.ts'
import { gradeLabel } from '../../../domain/grade.ts'
import { ThemeBackdrop } from './ThemeArt.tsx'
import { LookContext, themeVars } from './lookContext.ts'
import './student-world.css'
import './pages.css'

export type StudentPage =
  | 'home' | 'room' | 'album' | 'missions' | 'journal' | 'activities' | 'community' | 'points' | 'settings'
  | 'customize' | 'friends' | 'help' | 'support' | 'notices' | 'notifications'
  | 'theme'

/** 메뉴에 없는 화면이 어느 메뉴 아래인지(#648 시안 Nav active): 앨범·꾸미기·뭉치 친구들은 내 방, 포인트·도움말은 설정, 미션 고르기·주간 테마 화면(단서·정답·이야기·되돌아보기)은 홈 */
const NAV_PARENT: Partial<Record<StudentPage, StudentPage>> = {
  album: 'room', customize: 'room', friends: 'room',
  points: 'settings', help: 'settings', support: 'settings', notices: 'settings', notifications: 'settings',
  missions: 'home', theme: 'home',
}

/** 테마 바탕만 그리는 틀 (로그인 전 PIN 화면처럼 학생 설정을 아직 모를 때 기본 테마). */
export function ThemeFrame({ t = THEMES.lake, children }: { t?: Theme; children: ReactNode }) {
  return (
    <div className="st-world" data-theme={t.id} style={themeVars(t)}>
      <ThemeBackdrop t={t} />
      {children}
    </div>
  )
}

/**
 * 학생 화면 틀(#648): 밝은 테마 틀 + 흰 종이 + 메뉴 6개. 고른 테마는 틀 색과 홈 우리 집 그림을, 고른 캐릭터는 말풍선 안내를 맡는다.
 * focus(미션 작성 중)에는 메뉴를 숨겨 한 가지 일에만 집중하게 한다.
 */
export function StudentWorld({
  child,
  page,
  focus = false,
  onNavigate,
  children,
}: {
  child: Child
  page: StudentPage | null
  focus?: boolean
  onNavigate: (page: StudentPage) => void
  children: ReactNode
}) {
  const query = useStudentLook(child.id)
  const look = query.data ?? DEFAULT_LOOK
  const t = THEMES[look.theme]
  const items = useLookItems(child.id)
  // 착용 그림 키(#455). 목록 실패·키 없음은 기본 모습
  // 화면이 바뀌면 맨 위부터(앞 화면에서 내려간 스크롤이 남아 새 화면 머리가 잘려 보이지 않게, 2026-11-15)
  const stage = useRef<HTMLDivElement>(null)
  useEffect(() => {
    stage.current?.scrollTo?.(0, 0)
    window.scrollTo?.(0, 0)
  }, [page, focus])
  const worn = useMemo(() => wornAssets(look.equipped, items.error ? undefined : items.data), [look.equipped, items.data, items.error])
  // 메뉴 6개(#589·#648). 미션 고르기는 메뉴에서 빼고 프리미엄일 때 홈 "더 풀어 보기"로 들어간다.
  // 공개 설정·내 포인트·로그아웃은 설정 한 곳에서(#583). 학생 화면에 '학부모 로그인' 문구를 두지 않는다
  const nav: { id: StudentPage; label: string }[] = [
    { id: 'home', label: '홈' },
    { id: 'room', label: '내 방' },
    { id: 'journal', label: '내 공책' },
    { id: 'activities', label: '생각 활동' },
    { id: 'community', label: '친구 생각' },
    { id: 'settings', label: '설정' },
  ]
  return (
    <LookContext.Provider value={{ t, companion: look.companion, worn }}>
      <ThemeFrame t={t}>
        <div className="st-shell">
        {!focus && (
          <header className="st-top">
            <div className="st-brand">
              <Link className="st-wordmark" to="/student/home">사고뭉치</Link>
              <span className="st-sub">
                {child.nickname} · {gradeLabel(child.grade)}
              </span>
              {/* 도움말은 펼치면 아래로 뜨는 작은 메뉴(옆 글을 밀지 않음), 고르면 닫힘(사용자 의견 2026-11-16) */}
              <details className="st-support-menu">
                <summary>도움말</summary>
                <span className="st-support-pop">
                  <Link to="/student/help" onClick={(e) => { const d = e.currentTarget.closest('details'); if (d) d.open = false }}>이용 도움말</Link>
                  <Link to="/student/support" onClick={(e) => { const d = e.currentTarget.closest('details'); if (d) d.open = false }}>문의·오류 신고</Link>
                </span>
              </details>
            </div>
            <nav aria-label="학생 메뉴" className="st-nav">
              {nav.map((n) => (
                <button
                  type="button"
                  key={n.id}
                  aria-current={page && (page === n.id || NAV_PARENT[page] === n.id) ? 'page' : undefined}
                  onClick={() => onNavigate(n.id)}
                >
                  {n.label}
                </button>
              ))}
            </nav>
          </header>
        )}
        <div ref={stage} className={focus ? 'st-stage st-stage-focus' : 'st-stage'}>{children}</div>
        </div>
      </ThemeFrame>
    </LookContext.Provider>
  )
}
