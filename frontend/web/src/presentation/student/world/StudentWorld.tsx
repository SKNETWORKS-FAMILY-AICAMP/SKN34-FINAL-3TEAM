import type { ReactNode } from 'react'
import { BookOpen, LogOut, Map as MapIcon, Shapes } from 'lucide-react'
import { useStudentLook } from '../../../data/studentLook/queries.ts'
import { DEFAULT_LOOK, THEMES } from '../../../domain/studentLook.ts'
import type { Theme } from '../../../domain/studentLook.ts'
import type { Child } from '../../../domain/classroom.ts'
import { ThemeBackdrop } from './ThemeArt.tsx'
import { LookContext, themeVars } from './lookContext.ts'
import './student-world.css'

export type StudentPage = 'home' | 'missions' | 'journal'

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
 * 학생 화면 틀 (테마 캔버스). 고른 테마가 바탕과 이름을, 고른 캐릭터가 말풍선 안내를 맡는다.
 * focus(미션 작성 중)에는 메뉴를 숨겨 한 가지 일에만 집중하게 한다.
 */
export function StudentWorld({
  child,
  page,
  focus = false,
  onNavigate,
  onLeave,
  children,
}: {
  child: Child
  page: StudentPage | null
  focus?: boolean
  onNavigate: (page: StudentPage) => void
  onLeave: () => void
  children: ReactNode
}) {
  const query = useStudentLook(child.id)
  const look = query.data ?? DEFAULT_LOOK
  const t = THEMES[look.theme]
  const nav: { id: StudentPage; label: string; icon: typeof MapIcon }[] = [
    { id: 'home', label: '생각 지도', icon: MapIcon },
    { id: 'missions', label: '미션 고르기', icon: Shapes },
    { id: 'journal', label: '내 공책', icon: BookOpen },
  ]
  return (
    <LookContext.Provider value={{ t, companion: look.companion }}>
      <ThemeFrame t={t}>
        {!focus && (
          <header className="st-top">
            <div className="st-brand">
              <span className="st-wordmark">사고뭉치</span>
              <span className="st-sub">
                {child.nickname}의 {t.title} · 초등 {child.grade}학년
              </span>
            </div>
            <nav aria-label="학생 메뉴" className="st-nav">
              {nav.map((n) => (
                <button
                  type="button"
                  key={n.id}
                  aria-current={page === n.id ? 'page' : undefined}
                  onClick={() => onNavigate(n.id)}
                >
                  <span className="st-tile">
                    <n.icon aria-hidden="true" />
                  </span>
                  {n.label}
                </button>
              ))}
              <button type="button" className="st-leave" aria-label="학부모 로그인으로" onClick={onLeave}>
                <span className="st-tile">
                  <LogOut aria-hidden="true" />
                </span>
                학부모 로그인
              </button>
            </nav>
          </header>
        )}
        <div className={focus ? 'st-stage st-stage-focus' : 'st-stage'}>{children}</div>
      </ThemeFrame>
    </LookContext.Provider>
  )
}
