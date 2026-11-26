import { Link } from 'react-router'
import { useMyPoints } from '../../../data/retention/queries.ts'
import type { Child } from '../../../domain/classroom.ts'
import { StudentSharingPage } from '../StudentSharingPage.tsx'
import './room.css'

/**
 * 학생 설정(/student/settings, #583). 공개 설정(학부모 안내·친구 공개)·내 포인트·로그아웃을 한 곳에 모은다.
 * #648 시안 Settings: PC 한 화면에 카드 3개(포인트 카드는 노랑). 포인트 내역·꾸미기 해금은 "내 포인트 보기"(/student/points)에서.
 * 학생 화면에는 '학부모 로그인' 문구를 두지 않는다: 로그아웃하면 로그인 화면으로 가고,
 * 학부모 복귀는 그 화면의 "학부모 화면으로 돌아가기"(보호자 비밀번호, FN-ACC-05)가 맡는다.
 */
export function StudentSettings({ child, onPoints, onLogout, leaving }: {
  child: Child
  onPoints: () => void
  onLogout: () => void
  leaving: boolean
}) {
  const points = useMyPoints(child.id)
  const balance = points.error ? undefined : points.data?.balance
  return (
    <main className="st-paper st-sheet st-settings-page">
      <header className="st-page-head">
        <div>
          <h1 className="st-title-mix">설정</h1>
          <p>내 답 공개, 포인트, 로그아웃을 여기서 해요.</p>
        </div>
        {/* 도움말·문의 링크는 제목 줄 오른쪽(1440×900 한 화면, 검증 2026-11-15) */}
        <p className="st-set-links">
          <Link to="/student/help">이용 도움말</Link>
          <Link to="/student/support">문의·오류 신고</Link>
        </p>
      </header>
      <div className="st-set-grid">
        <div className="st-set-card st-set-sharing">
          <StudentSharingPage child={child} embedded />
        </div>
        <section className="st-set-card st-set-points" aria-labelledby="points-card-h">
          <h2 id="points-card-h">내 포인트</h2>
          <strong className="st-set-balance" aria-live="polite">
            {balance !== undefined ? balance.toLocaleString('ko-KR') : points.isPending ? '…' : '?'}
          </strong>
          {points.error ? <p className="st-meta">포인트를 확인하지 못했어요.</p> : null}
          <button type="button" className="st-pill-link" onClick={onPoints}>내 포인트 보기 <span aria-hidden="true">→</span></button>
        </section>
        <section className="st-set-card" aria-labelledby="logout-h">
          <h2 id="logout-h">로그아웃</h2>
          <p>공부를 마쳤으면 로그아웃해요. 처음 화면으로 돌아가요.</p>
          <button type="button" className="st-dark-button" disabled={leaving} onClick={onLogout}>
            {leaving ? '로그아웃하고 있어요' : '로그아웃'}
          </button>
        </section>
      </div>
    </main>
  )
}
