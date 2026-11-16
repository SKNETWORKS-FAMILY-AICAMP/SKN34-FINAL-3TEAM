import { useWeeklyTheme } from '../../../data/retention/queries.ts'
import type { Child } from '../../../domain/classroom.ts'
import { clueCount, pickStage, remainingCandidates, ruledOutOn } from '../../../domain/retention.ts'
import type { WeeklyTheme } from '../../../domain/retention.ts'
import { QueryStateNotice } from '../../common/QueryStateNotice.tsx'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import { BuddyBubble, CandidateFacts, ClueFacts } from './themeWeekParts.tsx'
import { clueEffect, dayName, josa, latestClueDay, list } from './themeWeek.ts'
import './theme-week.css'

/** 말풍선(규칙 기반, AI 호출 없음): 가장 최근 단서가 뺀 후보와 남은 후보, 금요일까지 모았으면 정답 고르기 권유 */
function buddyLine(theme: WeeklyTheme) {
  if (theme.ending === 'ENDED')
    return theme.answer ? `정답은 ${josa.was(theme.answer)}! 단서를 다시 보며 이야기를 떠올려 봐.` : '이번 주 이야기가 끝났어! 단서를 다시 볼 수 있어.'
  const last = latestClueDay(theme)
  if (!last) return '문제를 하나 풀 때마다 단서가 하나씩 생겨. 오늘 문제부터 풀어 볼까?'
  const day = theme.days.find((d) => d.day === last)!
  const left = remainingCandidates(theme)
  const { fresh } = clueEffect(theme, day)
  let line = fresh.length && theme.candidates.length
    ? `${dayName(last)} 단서로 ${josa.subject(list(fresh))} 빠졌어! 남은 후보는 ${josa.is(list(left))}.`
    : '이 단서로는 빠진 후보가 없어. 그래도 정답을 고를 때 도움이 될 거야.'
  if (pickStage(theme) === 'READY') line += ' 이제 정답을 골라 볼까?'
  return line
}

/**
 * 단서 모음(#589·#487 시안 Clues, #647 단서 근거). 후보 카드(빠진 후보에 "빠짐" 도장)와 요일별 단서 카드.
 * 단서·빠지는 후보·근거는 그날 문제를 학습 완료한 요일만 응답에 오므로 받은 것만 그린다. 숫자 점수·순위는 없다.
 */
export function ThemeClues({ child, onHome, onPick }: { child: Child; onHome: () => void; onPick: () => void }) {
  const query = useWeeklyTheme(child.id)
  const theme = query.error ? null : (query.data ?? null)
  if (query.isPending) return <main className="st-paper st-sheet tw-page"><QueryStateNotice state="PROCESSING" /></main>
  if (!theme)
    return (
      <main className="st-paper st-sheet tw-page">
        <ErrorNotice error={query.error} retry={() => void query.refetch()} />
        {!query.error && <p className="st-empty">이번 주 테마를 준비하고 있어요. 테마가 열리면 여기에 단서가 모여요.</p>}
        <button type="button" className="tw-go tw-go-plain" onClick={onHome}>홈으로</button>
      </main>
    )
  const last = latestClueDay(theme)
  const left = remainingCandidates(theme)
  const stage = pickStage(theme)
  return (
    <main className="st-paper st-sheet tw-page tw-clues">
      <header className="tw-head">
        <div>
          <p className="tw-kicker">{theme.title}{last ? ` · ${dayName(last)} 단서까지` : ''}</p>
          <h1 className="st-title-mix">단서 <span>모음</span></h1>
          {theme.bigQuestion && <p className="tw-question">{theme.bigQuestion}</p>}
        </div>
        <span className="tw-badge">
          모은 단서 {clueCount(theme)}장{theme.candidates.length > 0 && ` · 남은 후보 ${left.length}개`}
        </span>
      </header>

      {theme.candidates.length > 0 && (
        <section aria-labelledby="tw-cand-h" className="tw-section">
          <h2 id="tw-cand-h">후보</h2>
          <ul className="tw-cands">
            {theme.candidates.map((c) => {
              const out = ruledOutOn(theme, c)
              const answer = theme.ending === 'ENDED' && theme.answer === c
              return (
                <li key={c} data-out={out ? true : undefined} data-answer={answer || undefined}>
                  <strong>{c}</strong>
                  <span className="tw-cand-note">{answer ? '정답이었어요' : out ? `${dayName(out)} 단서로 빠졌어요` : '아직 남아 있어요'}</span>
                  <CandidateFacts theme={theme} candidate={c} />
                  {out && (
                    <span className="tw-stamp" data-new={out === last || undefined} aria-hidden="true">
                      빠짐
                    </span>
                  )}
                </li>
              )
            })}
          </ul>
        </section>
      )}

      <section aria-labelledby="tw-clue-h" className="tw-section">
        <h2 id="tw-clue-h">요일별 단서</h2>
        <ol className="tw-clue-cards">
          {theme.days.map((d) => {
            const got = !!d.clue
            const ended = theme.ending === 'ENDED' && !!theme.features?.length
            const isNew = got && d.day === last && theme.ending !== 'ENDED'
            const { fresh, again } = clueEffect(theme, d)
            return (
              <li key={d.day} data-state={!got ? 'locked' : isNew ? 'new' : 'got'}>
                <span className="tw-clue-top">
                  <span className="tw-day">{dayName(d.day).slice(0, 1)}</span>
                  {!got ? (ended ? '못 얻은 단서' : '아직 못 얻었어요') : isNew ? '새 단서!' : ''}
                </span>
                {/* 엔딩 뒤에는 "마치면 열려요" 대신 위 후보 카드에 공개된 것을 알림(#715 1번과 같은 화면) */}
                <p className="tw-clue-text">{got ? d.clue : ended ? '정답이 나와서 이 날 특징은 위 후보 카드에 ‘엔딩 뒤 공개’로 보여요.' : `${dayName(d.day)} 문제를 마치면 열려요.`}</p>
                {got && <ClueFacts day={d} />}
                {got && theme.candidates.length > 0 && (
                  <span className="tw-effect" data-fresh={fresh.length > 0 || undefined}>
                    {fresh.length
                      ? `빠진 후보: ${list(fresh)}${again.length ? ` (${josa.topic(list(again))} 이미 빠졌어요)` : ''}`
                      : again.length
                        ? `${josa.topic(list(again))} 이미 빠졌어요`
                        : '빠진 후보 없음 · 정답 고를 때 힌트'}
                  </span>
                )}
              </li>
            )
          })}
        </ol>
      </section>

      <div className="tw-bottom">
        <BuddyBubble text={buddyLine(theme)} />
        <div className="tw-actions">
          {stage === 'READY' && (
            <button type="button" className="tw-go" onClick={onPick}>
              정답 고르러 가기 →
            </button>
          )}
          <button type="button" className="tw-go tw-go-plain" onClick={onHome}>
            홈으로
          </button>
        </div>
      </div>
    </main>
  )
}
