import { useEffect, useRef } from 'react'
import { CalendarDays } from 'lucide-react'
import { useRecordReviewView, useWeeklyTheme } from '../../../data/retention/queries.ts'
import type { Child, Mission } from '../../../domain/classroom.ts'
import { thinkingLabels } from '../../../domain/classroom.ts'
import { DAY_LABELS, dayStatusText, todayThemeDay } from '../../../domain/retention.ts'
import type { AttemptContext, WeeklyTheme } from '../../../domain/retention.ts'
import { thinkingHue } from '../../../domain/studentLook.ts'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import './retention.css'

/**
 * 이번 주 테마 (P23, API 명세 2.11). 월요일 도입 이야기, 월~금 하루 한 문제, 토·일 되돌아보기.
 * 테마를 받지 못하면(없음·실패) 아무것도 그리지 않아 기존 생각 지도 홈이 그대로 보인다.
 */
export function WeeklyThemeCard({
  child,
  missions,
  onStart,
  onResume,
}: {
  child: Child
  missions: Mission[]
  onStart: (mission: Mission, context: AttemptContext) => void
  onResume: (attemptId: string) => void
}) {
  const query = useWeeklyTheme(child.id)
  const theme = query.error ? null : query.data
  if (query.isPending || !theme) return null
  const byId = new Map(missions.map((m) => [m.id, m]))
  const open = (missionId: string, context: AttemptContext) => {
    const m = byId.get(missionId)
    if (!m) return
    if (m.status === 'IN_PROGRESS' && m.attemptId) onResume(m.attemptId)
    else onStart(m, context)
  }
  const today = todayThemeDay(theme)
  return (
    <section className="st-paper st-week" aria-labelledby="week-h">
      <p className="st-kicker">
        <CalendarDays aria-hidden="true" size={16} /> 이번 주 테마{theme.reused && ' · 지난 테마를 다시 만나요'}
      </p>
      <h2 id="week-h">{theme.title}</h2>
      {theme.intro && <p className="st-week-intro">{theme.intro}</p>}
      <ol className="st-week-days" aria-label="요일별 문제">
        {theme.days.map((d) => {
          const title = d.title ?? byId.get(d.missionId)?.title ?? '오늘의 문제'
          return (
            <li key={d.day} data-state={d.state} data-done={d.attemptStatus === 'COMPLETED' || undefined}>
              <span className="st-week-day" style={{ borderColor: thinkingHue[d.thinkingType] }}>
                {DAY_LABELS[d.day]}
              </span>
              <span className="st-week-title">
                <strong>{d.state === 'LOCKED' ? '아직 비밀이에요' : title}</strong>
                <small>
                  {thinkingLabels[d.thinkingType]} · {dayStatusText(d)}
                </small>
              </span>
              {d.state === 'OPEN' && d.attemptStatus !== 'COMPLETED' && (
                <button type="button" className="st-button st-primary" onClick={() => open(d.missionId, 'THEME_DAY')}>
                  {d.attemptStatus === 'IN_PROGRESS' ? '이어서 하기' : '오늘 문제 풀기'}
                </button>
              )}
              {d.state === 'CLOSED' && d.attemptStatus === 'IN_PROGRESS' && (
                <button type="button" className="st-button" onClick={() => open(d.missionId, 'THEME_DAY')}>
                  이어서 하기
                </button>
              )}
            </li>
          )
        })}
      </ol>
      {!today && !theme.review.open && (
        <p className="st-meta">오늘은 열린 문제가 없어요. 다음 요일에 새 문제가 열려요.</p>
      )}
      {theme.review.open && <WeekendReview child={child} theme={theme} byId={byId} onOpen={open} />}
      {theme.completed && <p className="st-week-done">이번 주 테마를 끝까지 해냈어요!</p>}
    </section>
  )
}

/** 토·일 되돌아보기: 마무리한 문제는 다시 풀기, 놓친 문제는 목록에만(풀 수 없음). 열면 한 번 기록한다. */
function WeekendReview({
  child,
  theme,
  byId,
  onOpen,
}: {
  child: Child
  theme: WeeklyTheme
  byId: Map<string, Mission>
  onOpen: (missionId: string, context: AttemptContext) => void
}) {
  const record = useRecordReviewView(child.id)
  const sent = useRef('')
  useEffect(() => {
    const key = `${child.id}:${theme.weekStart}`
    if (sent.current === key) return
    sent.current = key
    // 같은 주에는 한 번만 보낸다(서버도 주 1회 멱등). ref가 다시 그려도 중복 전송을 막는다.
    record.mutate()
  }, [child.id, theme.weekStart, record])
  return (
    <div className="st-review" aria-labelledby="review-h">
      <h3 id="review-h">주말 되돌아보기</h3>
      <p className="st-meta">이번 주에 마무리한 문제를 다시 풀어 볼 수 있어요. 다시 풀어도 무료 한도는 줄지 않아요.</p>
      <ul>
        {theme.review.missions.map((m) => (
          <li key={m.missionId} data-missed={m.missed || undefined}>
            <span>{m.title ?? byId.get(m.missionId)?.title ?? '이번 주 문제'}</span>
            {m.completed ? (
              <button type="button" className="st-button" onClick={() => onOpen(m.missionId, 'THEME_REVIEW')}>
                다시 풀기
              </button>
            ) : (
              <small>놓친 문제 · 다음 주에 새 문제가 기다려요</small>
            )}
          </li>
        ))}
      </ul>
      <ErrorNotice error={record.error} />
    </div>
  )
}
