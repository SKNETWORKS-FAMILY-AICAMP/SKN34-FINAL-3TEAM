import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { useFetchWeeklyTheme } from '../../../data/retention/queries.ts'
import type { Attempt } from '../../../domain/classroom.ts'
import { DAY_LABELS, endingDue, pickStage } from '../../../domain/retention.ts'
import type { WeeklyTheme } from '../../../domain/retention.ts'
import { Companion } from './Companion.tsx'
import { useLook } from './lookContext.ts'

/**
 * 미션 완료 화면(설계 캔버스 SC-02-012 돌아보기의 '미션 완료!', user-flow 3.2 REF → 단서 모음·정답 고르기, 사용자 결정 2026-11-19 #807).
 * 돌아보기를 저장하면 문제 화면 위에 띄운다. 테마 문제는 주간 테마를 다시 받아 엔딩이 됐으면 이야기의 끝으로(onEnding), 아니면
 * 처음 마친 요일의 단서를 보여 주고 단서 모음(금요일은 정답 고르기)으로 잇는다. 단서는 그 문제를 학습 완료한 뒤에만 채워진다(#484).
 * 다시 풀기(THEME_REVIEW)와 더 풀어 보기(EXTRA)는 단서 칸 없이. 포인트 숫자는 넣지 않는다(미션마다 처음 한 번 +10이라 다시 풀기는
 * 0이고, 포인트 내역에 어느 미션 것인지 없어 실제로 쌓인 값을 화면이 알 수 없음).
 */
export function MissionDone({ attempt, childId, onEnding }: { attempt: Attempt; childId: string | undefined; onEnding: () => void }) {
  const navigate = useNavigate()
  const { companion, worn } = useLook()
  const fetchTheme = useFetchWeeklyTheme(childId)
  const isTheme = !!attempt.themeScene
  // undefined: 받는 중(테마 문제만), null: 테마 없음·실패
  const [theme, setTheme] = useState<WeeklyTheme | null | undefined>(undefined)
  const head = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    if (!isTheme) return
    let live = true
    fetchTheme().then(
      (t) => {
        if (!live) return
        if (t && endingDue(t)) onEnding()
        else setTheme(t ?? null)
      },
      () => { if (live) setTheme(null) },
    )
    return () => { live = false }
  }, [isTheme]) // eslint-disable-line react-hooks/exhaustive-deps
  const waiting = isTheme && theme === undefined
  useEffect(() => { if (!waiting) head.current?.focus() }, [waiting])
  if (waiting) return <div className="sw-done-dim" role="status"><p className="sw-done-wait">정리하고 있어요.</p></div>

  const day = theme?.days.find((d) => d.missionId === attempt.mission.id) ?? null
  const friday = day?.day === 'FRI'
  const clue = day && day.clue && attempt.context !== 'THEME_REVIEW' ? day.clue : null
  const toPick = friday && !!theme && pickStage(theme) === 'READY'
  // 금요일 문제의 친구 생각은 이야기의 끝을 본 뒤에 열린다(정답 고르기 화면 안내와 같음)
  const community = !(friday && theme?.ending !== 'ENDED')
  return (
    <div className="sw-done-dim">
      <section className="sw-done-card" role="dialog" aria-modal="true" aria-labelledby="sw-done-title">
        <span className="sw-done-face" aria-hidden="true"><Companion kind={companion} size={130} worn={worn} decorative /></span>
        <h2 id="sw-done-title" ref={head} tabIndex={-1}>미션 완료!</h2>
        <span className="sw-done-badge">미션 학습 완료</span>
        <p className="sw-done-note">이번 답은 내 공책에 남았어요.</p>
        {clue && day && (
          <div className="sw-done-clue">
            <strong>{friday ? '마지막 단서가 열렸어요!' : `${DAY_LABELS[day.day]}요일 단서가 열렸어요!`}</strong>
            <p>{clue}</p>
            <button type="button" className="sw-done-go" onClick={() => navigate(toPick ? '/student/theme/pick' : '/student/theme/clues')}>
              {toPick ? '정답 고르러 가기' : '단서 모음 보기'}<span aria-hidden="true"> →</span>
            </button>
          </div>
        )}
        <div className="sw-done-actions">
          <button type="button" className="sw-done-sub" onClick={() => navigate('/student/journal')}>내 공책 보기</button>
          {community && (
            <button type="button" className="sw-done-sub" onClick={() => navigate(`/student/community?mission=${encodeURIComponent(attempt.mission.id)}`)}>
              같은 미션 친구 생각 보기
            </button>
          )}
          <button type="button" className="sw-done-home" onClick={() => navigate('/student/home')}>홈으로</button>
        </div>
      </section>
    </div>
  )
}
