import { useEffect, useRef } from 'react'
import { Coins, Eye, LogOut, Settings } from 'lucide-react'
import type { Child } from '../../../domain/classroom.ts'
import { StudentSharingPage } from '../StudentSharingPage.tsx'
import { StudentPoints } from './StudentPoints.tsx'
import './room.css'

export type SettingsPart = 'sharing' | 'points' | 'logout'

/**
 * 학생 설정(/student/settings, #583). 공개 설정·내 포인트·로그아웃을 한 곳에 모은다.
 * 학생 화면에는 '학부모 로그인' 문구를 두지 않는다: 로그아웃하면 로그인 화면으로 가고,
 * 학부모 복귀는 그 화면의 "학부모 화면으로 돌아가기"(보호자 비밀번호, FN-ACC-05)가 맡는다.
 * 옛 /student/points 주소는 focus='points'로 들어와 포인트 부분을 보여 준다.
 */
export function StudentSettings({ child, focus, onLogout, leaving }: {
  child: Child
  focus?: SettingsPart
  onLogout: () => void
  leaving: boolean
}) {
  const parts = useRef<Record<SettingsPart, HTMLElement | null>>({ sharing: null, points: null, logout: null })
  const go = (part: SettingsPart) => {
    const el = parts.current[part]
    el?.scrollIntoView({ block: 'start' })
    el?.querySelector<HTMLElement>('h2')?.focus({ preventScroll: true })
  }
  useEffect(() => { if (focus && focus !== 'sharing') go(focus) }, [focus])
  return (
    <main className="st-paper st-sheet st-settings-page">
      <div className="st-sheet-head">
        <h1><Settings aria-hidden="true" /> 설정</h1>
        <p>내 답 공개, 포인트, 로그아웃을 여기서 해요.</p>
      </div>
      <nav className="st-settings-nav" aria-label="설정 바로가기">
        <button type="button" className="st-button" onClick={() => go('sharing')}><Eye aria-hidden="true" /> 공개 설정 보기</button>
        <button type="button" className="st-button" onClick={() => go('points')}><Coins aria-hidden="true" /> 내 포인트 보기</button>
        <button type="button" className="st-button" onClick={() => go('logout')}><LogOut aria-hidden="true" /> 로그아웃 보기</button>
      </nav>
      <div ref={(el) => { parts.current.sharing = el }} className="st-settings-block">
        <StudentSharingPage child={child} embedded />
      </div>
      <div ref={(el) => { parts.current.points = el }} className="st-settings-block">
        <StudentPoints child={child} embedded />
      </div>
      <section ref={(el) => { parts.current.logout = el }} className="st-settings-block st-settings-part" aria-labelledby="logout-h">
        <h2 id="logout-h" tabIndex={-1}><LogOut aria-hidden="true" /> 로그아웃</h2>
        <p>공부를 마쳤으면 로그아웃해요. 처음 화면으로 돌아가요.</p>
        <button type="button" className="st-button st-primary" disabled={leaving} onClick={onLogout}>
          {leaving ? '로그아웃하고 있어요' : '로그아웃'}
        </button>
      </section>
    </main>
  )
}
