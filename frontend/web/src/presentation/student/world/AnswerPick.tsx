import { useEffect, useRef, useState } from 'react'
import { useAnswerPick, useWeeklyTheme } from '../../../data/retention/queries.ts'
import type { Child, Mission } from '../../../domain/classroom.ts'
import { clueCount, pickStage, remainingCandidates, ruledOutOn, themeClosed } from '../../../domain/retention.ts'
import type { AnswerPickResult, AttemptContext, WeeklyTheme } from '../../../domain/retention.ts'
import { QueryStateNotice } from '../../common/QueryStateNotice.tsx'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import { Companion } from './Companion.tsx'
import { useLook } from './lookContext.ts'
import { CandidateFacts } from './themeWeekParts.tsx'
import { dayName, josa, useThemeMissions } from './themeWeek.ts'
import './theme-week.css'

const TILTS = ['-1.5deg', '1deg', '1.5deg', '-1deg']

/** 왼쪽 "이번 주 단서" 줄 목록(시안 AnswerPick): 그날 미션 그림·단서·빠진 후보(줄 긋기) 또는 "빠지는 후보 없음 · 힌트". */
function ClueRows({ theme, image }: { theme: WeeklyTheme; image: (missionId: string) => string | null }) {
  return (
    <ol className="tw-clue-rows">
      {theme.days.map((d) => {
        const src = image(d.missionId)
        return (
          <li key={d.day} data-locked={!d.clue || undefined}>
            {src ? <img src={src} alt="" /> : <span className="tw-row-art" aria-hidden="true" />}
            <div>
              <span className="tw-row-day">{dayName(d.day)} · {d.title ?? '이번 주 문제'}</span>
              <span className="tw-row-text">{d.clue ?? `${dayName(d.day)} 문제를 마치면 열려요.`}</span>
              {d.clue && (
                <span className="tw-row-outs">
                  {(d.rulesOut ?? []).map((c) => <s key={c}>{c} 빠짐</s>)}
                  {d.rulesOut?.length === 0 && <i>빠지는 후보 없음 · 힌트</i>}
                </span>
              )}
            </div>
          </li>
        )
      })}
    </ol>
  )
}

/**
 * 큰 질문 정답 고르기(#487·#590 시안 AnswerPick). 한 주에 한 번, 단서로 빠진 후보도 고를 수 있다.
 * 맞히면 그 자리에서 "이야기의 끝 보기", 틀리면 토요일(프리미엄 일요일)에 금요일 문제를 다시 풀어 마무리하면 엔딩(#484).
 * 단계 판정은 domain pickStage(금요일 문제 학습 완료부터, 사용자 결정 2026-11-12).
 */
export function AnswerPick({ child, onHome, onEnding, onJournal, onResume, onStartTheme }: {
  child: Child
  onHome: () => void
  onEnding: () => void
  onJournal: () => void
  onResume: (attemptId: string) => void
  onStartTheme: (mission: Mission, context: AttemptContext) => void
}) {
  const query = useWeeklyTheme(child.id)
  const pick = useAnswerPick(child.id)
  const { open, image } = useThemeMissions(child, onResume, onStartTheme)
  const { companion, worn } = useLook()
  const [sel, setSel] = useState('')
  const [tried, setTried] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const [result, setResult] = useState<(AnswerPickResult & { pick: string }) | null>(null)
  const confirmHead = useRef<HTMLHeadingElement>(null)
  const resultBox = useRef<HTMLDivElement>(null)
  useEffect(() => { if (confirm) confirmHead.current?.focus() }, [confirm])
  useEffect(() => { if (result) resultBox.current?.focus() }, [result])

  const theme = query.error ? null : (query.data ?? null)
  if (query.isPending) return <main className="st-paper st-sheet tw-page"><QueryStateNotice state="PROCESSING" /></main>
  if (!theme)
    return (
      <main className="st-paper st-sheet tw-page">
        <ErrorNotice error={query.error} retry={() => void query.refetch()} />
        <button type="button" className="tw-go tw-go-plain" onClick={onHome}>홈으로</button>
      </main>
    )
  const stage = pickStage(theme)
  const friday = theme.days.find((d) => d.day === 'FRI')
  const left = remainingCandidates(theme)
  const choosable = stage === 'READY' && !confirm && !result && !pick.isPending
  // 고른 뒤 결과: 방금 고른 결과가 있으면 그것, 다시 들어왔으면 응답의 answerPick(틀림)·엔딩
  const wrong = result ? !result.correct : stage === 'RETRY'
  const right = result ? result.correct : false
  const myPick = result?.pick ?? theme.answerPick?.pick ?? ''
  const commit = () => {
    setConfirm(false)
    pick.mutate(sel, { onSuccess: (r) => setResult({ ...r, pick: sel }) })
  }
  return (
    <main className="st-paper st-sheet tw-page tw-pick">
      <header className="tw-head">
        <div>
          <p className="tw-kicker">{theme.title}</p>
          <h1 className="st-title-mix">정답 <span>고르기</span></h1>
          {theme.bigQuestion && <p className="tw-question">{theme.bigQuestion}</p>}
        </div>
        <span className="tw-badge">
          모은 단서 {clueCount(theme)}장 · 남은 후보 {left.length}개
        </span>
      </header>

      <div className="tw-pick-body">
        <section aria-labelledby="tw-pick-clue-h" className="tw-section">
          <h2 id="tw-pick-clue-h">이번 주 <b>단서</b></h2>
          <ClueRows theme={theme} image={image} />
        </section>

        <section aria-labelledby="tw-pick-h" className="tw-section tw-pick-side">
          <h2 id="tw-pick-h"><b>후보</b> {theme.candidates.length}개</h2>
          {stage === 'NONE' && <p className="st-empty">이번 주 테마에는 정답 고르기가 없어요.</p>}
          {!wrong && !right && stage !== 'NONE' && stage !== 'ENDED' && (
            <div role="group" aria-label="후보" className="tw-pick-grid">
              {theme.candidates.map((c, i) => {
                const out = !!ruledOutOn(theme, c)
                return (
                  <button key={c} type="button" className="tw-pick-cand" aria-pressed={sel === c} disabled={!choosable}
                    data-out={out || undefined} style={{ rotate: TILTS[i % TILTS.length] }}
                    onClick={() => { setSel(c); setTried(false) }}>
                    <strong>{c}</strong>
                    <span className="tw-pill">{out ? '단서로 빠졌어요' : '남은 후보'}</span>
                    {/* 알아낸 것은 남은 후보만(빠진 후보는 "단서로 빠졌어요"로 충분, 한 화면에 담기게) */}
                    {!out && <CandidateFacts theme={theme} candidate={c} />}
                  </button>
                )
              })}
            </div>
          )}

          {stage === 'READY' && !confirm && !result && (
            <div className="tw-pick-decide">
              <p>단서로 빠진 후보도 고를 수는 있어요. 정답 고르기는 <b>한 주에 한 번</b>이라 고르면 바꿀 수 없어요.</p>
              {tried && !sel && <p role="alert" className="tw-warn">후보를 하나 골라 주세요.</p>}
              <button type="button" className="tw-go tw-go-big" disabled={pick.isPending}
                onClick={() => (sel ? setConfirm(true) : setTried(true))}>
                {pick.isPending ? '확인하는 중…' : '이걸로 정하기'}
              </button>
              <ErrorNotice error={pick.error} />
            </div>
          )}

          {confirm && (
            <div role="dialog" aria-modal="false" aria-labelledby="tw-cf-h" className="tw-confirm"
              onKeyDown={(e) => { if (e.key === 'Escape') setConfirm(false) }}>
              <h3 id="tw-cf-h" ref={confirmHead} tabIndex={-1}>「{sel}」{josa.to(sel).slice(sel.length)} 정할까요?</h3>
              <p>한 번 고르면 이번 주에는 바꿀 수 없어요.</p>
              <div className="tw-confirm-actions">
                <button type="button" className="tw-go tw-go-plain" onClick={() => setConfirm(false)}>다시 고를래요</button>
                <button type="button" className="tw-go" onClick={commit}>정했어요</button>
              </div>
            </div>
          )}

          {right && (
            <div role="status" ref={resultBox} tabIndex={-1} className="tw-result" data-tone="right">
              <span className="tw-result-face" aria-hidden="true"><Companion kind={companion} worn={worn} size={120} decorative /></span>
              <div>
                <strong>정답이에요!</strong>
                <p>{result?.answer ? `정답은 ${josa.was(result.answer)}. ` : ''}이제 이야기의 끝을 볼 수 있어.</p>
                <button type="button" className="tw-go tw-go-big" onClick={onEnding}>이야기의 끝 보기 →</button>
              </div>
            </div>
          )}

          {wrong && (
            <div role="status" ref={resultBox} tabIndex={-1} className="tw-result" data-tone="wrong">
              <div className="tw-result-row">
                <span className="tw-result-face" aria-hidden="true"><Companion kind={companion} worn={worn} size={100} decorative /></span>
                <div>
                  <strong>아쉬워, 정답이 아니야</strong>
                  {myPick && <span className="tw-pill">내가 고른 답 · {myPick}</span>}
                </div>
              </div>
              <p className="tw-result-lead">
                {theme.review.open
                  ? '오늘 금요일 문제를 다시 풀어 마무리하면, 맞든 틀리든 이야기의 끝을 볼 수 있어.'
                  : themeClosed(theme)
                    ? // 무료 일요일: 토요일이 지나 다시 풀 수 없다(#487 45행)
                      '이번 주 테마가 끝나서 다시 풀 수 없어. 다음 테마는 월요일에 열려!'
                    : '토요일에 금요일 문제를 다시 풀어 마무리하면, 맞든 틀리든 이야기의 끝을 볼 수 있어.'}
              </p>
              <p>금요일 문제의 친구 생각은 이야기의 끝을 본 뒤에 열려요.</p>
              {theme.review.open && friday ? (
                <button type="button" className="tw-go tw-go-big" onClick={() => open(friday.missionId, 'THEME_REVIEW')}>금요일 문제 다시 풀기 →</button>
              ) : (
                <button type="button" className="tw-go tw-go-plain" onClick={onHome}>홈으로</button>
              )}
            </div>
          )}

          {stage === 'LOCKED' && (
            <div role="status" className="tw-note-box" data-dashed>
              <strong>금요일 문제를 마치면 고를 수 있어요</strong>
              <p>금요일 문제를 풀고 돌아보기까지 저장하면 마지막 단서가 열리고, 그다음에 정답을 골라요.</p>
              {friday && friday.state === 'OPEN' ? (
                <button type="button" className="tw-go" onClick={() => open(friday.missionId, 'THEME_DAY')}>
                  {friday.attemptStatus === 'IN_PROGRESS' ? '금요일 문제 이어서 풀기 →' : '금요일 문제 풀기 →'}
                </button>
              ) : (
                <button type="button" className="tw-go tw-go-plain" onClick={onHome}>홈으로</button>
              )}
            </div>
          )}

          {stage === 'CLOSED' && (
            <div role="status" className="tw-note-box">
              <strong>일요일에는 정답을 고를 수 없어요</strong>
              <p>이번 주 단서와 기록은 다시 볼 수 있어요. 다음 테마는 월요일에 열려요.</p>
              <button type="button" className="tw-go tw-go-plain" onClick={onJournal}>이번 주 기록 보기</button>
            </div>
          )}

          {stage === 'ENDED' && !result && (
            <div role="status" className="tw-note-box">
              <strong>이번 주 이야기는 끝났어요</strong>
              <p>{theme.answer ? `정답은 ${josa.was(theme.answer)}요. ` : ''}끝 이야기는 언제든 다시 볼 수 있어요.</p>
              <button type="button" className="tw-go" onClick={onEnding}>이야기의 끝 다시 보기 →</button>
            </div>
          )}
        </section>
      </div>
    </main>
  )
}
