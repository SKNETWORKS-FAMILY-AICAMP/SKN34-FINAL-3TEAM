import { useEffect, useRef } from 'react'
import { useRecordReviewView, useWeeklyTheme } from '../../../data/retention/queries.ts'
import type { Child, Mission } from '../../../domain/classroom.ts'
import { studentThinkingLabels } from '../../../domain/classroom.ts'
import { POINT_RULES, themeClosed } from '../../../domain/retention.ts'
import type { AttemptContext } from '../../../domain/retention.ts'
import { QueryStateNotice } from '../../common/QueryStateNotice.tsx'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import { Companion } from './Companion.tsx'
import { useLook } from './lookContext.ts'
import { dayName, useThemeMissions } from './themeWeek.ts'
import './theme-week.css'

const REVIEW_POINTS = POINT_RULES.find((r) => r.type === 'REVIEW_VIEWED')!.amount

/**
 * 주말 되돌아보기(#487 시안 Review). 토요일·프리미엄 일요일: 안 푼 문제 "지금 풀기", 마무리한 문제 "다시 풀기"(열면 주 1회 기록).
 * 무료 일요일(테마 닫힘): "다음 테마는 월요일에 열려요" + 이번 주 기록·이야기의 끝 다시 보기. 아이 화면에 결제 안내는 넣지 않는다.
 */
export function ThemeReview({ child, onJournal, onEnding, onHome, onResume, onStartTheme }: {
  child: Child
  onJournal: () => void
  onEnding: () => void
  onHome: () => void
  onResume: (attemptId: string) => void
  onStartTheme: (mission: Mission, context: AttemptContext) => void
}) {
  const query = useWeeklyTheme(child.id)
  const record = useRecordReviewView(child.id)
  const { open, image } = useThemeMissions(child, onResume, onStartTheme)
  const { companion, worn } = useLook()
  const theme = query.error ? null : (query.data ?? null)
  const sent = useRef('')
  useEffect(() => {
    if (!theme?.review.open) return
    const key = `${child.id}:${theme.weekStart}`
    if (sent.current === key) return
    sent.current = key
    // 같은 주에는 한 번만 보낸다(서버도 주 1회 멱등).
    record.mutate()
  }, [child.id, theme?.review.open, theme?.weekStart, record])

  if (query.isPending) return <main className="st-paper st-sheet tw-page"><QueryStateNotice state="PROCESSING" /></main>
  if (!theme)
    return (
      <main className="st-paper st-sheet tw-page">
        <ErrorNotice error={query.error} retry={() => void query.refetch()} />
        <button type="button" className="tw-go tw-go-plain" onClick={onHome}>홈으로</button>
      </main>
    )
  const closed = themeClosed(theme)
  const endingSeen = theme.ending === 'ENDED' && theme.outroSeen
  const reviewOpen = theme.review.open
  if (!reviewOpen && !closed)
    return (
      <main className="st-paper st-sheet tw-page">
        <p className="st-empty">주말 되돌아보기는 토요일에 열려요.</p>
        <button type="button" className="tw-go tw-go-plain" onClick={onHome}>홈으로</button>
      </main>
    )
  return (
    <main className="st-paper st-sheet tw-page tw-review">
      <header className="tw-head">
        <div>
          {/* 토요일과 프리미엄 일요일은 응답이 같아 요일 대신 "주말"(무료 일요일만 닫힘) */}
          <p className="tw-kicker">이번 주 테마 · {reviewOpen ? '주말' : '일요일'}</p>
          <h1 className="st-title-mix">{reviewOpen ? <>주말 <span>되돌아보기</span></> : <>이번 주 테마는 <span>끝났어요</span></>}</h1>
          <p className="tw-lead">{reviewOpen ? '안 푼 문제는 지금 풀고, 마무리한 문제는 다시 풀어 볼 수 있어요.' : `「${theme.title}」 한 주를 함께 했어요.`}</p>
        </div>
        {reviewOpen && <span className="tw-badge tw-badge-yellow">되돌아보기 열면 +{REVIEW_POINTS} 포인트 (한 주에 한 번)</span>}
      </header>

      {reviewOpen ? (
        <>
          <section aria-label="이번 주 문제" className="tw-review-days">
            {theme.days.map((d) => {
              const done = d.attemptStatus === 'COMPLETED'
              const doing = d.attemptStatus === 'IN_PROGRESS'
              const src = image(d.missionId)
              return (
                <article key={d.day} data-done={done || undefined}>
                  {src ? <img src={src} alt="" /> : <span className="tw-row-art" aria-hidden="true" />}
                  <span className="tw-review-meta">{dayName(d.day)} · {studentThinkingLabels[d.thinkingType]}</span>
                  <strong>{d.title ?? '이번 주 문제'}</strong>
                  <span>{done ? '마무리했어요' : doing ? '푸는 중이에요' : '아직 안 풀었어요'}</span>
                  <button type="button" className={done ? 'tw-go tw-go-plain' : 'tw-go'}
                    onClick={() => open(d.missionId, done ? 'THEME_REVIEW' : 'THEME_DAY')}>
                    {done ? '다시 풀기' : doing ? '이어서 풀기' : '지금 풀기'}
                  </button>
                </article>
              )
            })}
          </section>
          <p className="tw-review-note">
            마무리한 문제는 다시 풀어 볼 수 있어요.
            {theme.answerPick && !theme.answerPick.correct && theme.ending !== 'ENDED' && ' 금요일 정답 고르기를 틀렸다면, 그 문제를 다시 풀어 마무리하면 맞든 틀리든 이야기의 끝을 볼 수 있어요.'}
          </p>
          <ErrorNotice error={record.error} />
        </>
      ) : (
        <section className="tw-closed">
          <span aria-hidden="true"><Companion kind={companion} worn={worn} size={150} decorative /></span>
          <div>
            <strong>다음 테마는 월요일에 열려요</strong>
            {/* 무료 일요일에는 이미 본 엔딩 다시 보기만(state-diagram 3.2.2) */}
            <p>일요일에는 문제를 풀 수 없어요. 이번 주에 쓴 기록{endingSeen ? '과 본 이야기의 끝은' : '은'} 다시 볼 수 있어요.</p>
            <div className="tw-actions">
              <button type="button" className="tw-go tw-go-plain" onClick={onJournal}>이번 주 기록 보기</button>
              {endingSeen && <button type="button" className="tw-go tw-go-yellow" onClick={onEnding}>이야기의 끝 다시 보기</button>}
            </div>
          </div>
        </section>
      )}
    </main>
  )
}
