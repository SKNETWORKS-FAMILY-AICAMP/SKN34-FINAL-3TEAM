import { useEffect, useRef, useState } from 'react'
import { useRecordStoryView, useWeeklyTheme } from '../../../data/retention/queries.ts'
import type { Child } from '../../../domain/classroom.ts'
import { themeClosed } from '../../../domain/retention.ts'
import type { StoryKind, WeeklyTheme } from '../../../domain/retention.ts'
import { ThemeMotionPlayer } from '../../common/ThemeMotionPlayer.tsx'
import { useReducedMotion } from '../../common/useReducedMotion.ts'
import { readThemeMotion } from '../../../domain/themeMotion.ts'
import { QueryStateNotice } from '../../common/QueryStateNotice.tsx'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import { Companion } from './Companion.tsx'
import { useLook } from './lookContext.ts'
import { josa } from './themeWeek.ts'
import './theme-week.css'

/** 화면 가득 먼저 재생할 것이 있는지: 영상, 또는 그림 + 움직임(카메라·문구). 목업처럼 영상 파일이 없어도 그림 장면을 영상처럼 먼저 보여 준다 */
const playable = (m: { image: string | null; video: string | null; motion: unknown }) => {
  if (m.video) return true
  const motion = readThemeMotion(m.motion)
  return !!m.image && !!motion && (!!motion.camera || motion.captions.length > 0)
}
const media = (theme: WeeklyTheme, kind: StoryKind) =>
  kind === 'INTRO'
    ? { text: theme.intro, image: theme.introImageUrl, video: theme.introVideoUrl, motion: theme.introMotion }
    : { text: theme.outro, image: theme.outroImageUrl, video: theme.outroVideoUrl, motion: theme.outroMotion }

/**
 * 주간 테마 시작 이야기·이야기의 끝(#440 시안 Main 시작 영상·Ending).
 * 영상(또는 그림 + 움직임)이 있으면 먼저 화면 가득 재생(컷 문구는 움직임 captions, 끝나면 이야기로, "건너뛰기"), 이야기 화면에는 마지막 그림을 멈춘 채로 둔다.
 * 둘 다 없으면 바로 이야기(글만). 사용자 의견 2026-11-16 "인트로처럼 화면 가득 차서 영상 나오고 마지막 그림에 저 화면이 나와야".
 * 처음 볼 때만 열람을 기록한다(시작은 "이번 주 시작하기"를 누를 때, 끝은 이야기를 펼칠 때). 다시 보기는 기록하지 않는다.
 * 움직임 줄이기면 화면 가득 재생 없이 바로 이야기(정지 그림), 그림·영상을 못 불러오면 그것만 빼고 글로(#440 "이미지 로딩 실패 대체 표시",
 * 그림 없는 수동 테마와 같은 모양).
 */
export function ThemeStory({ child, kind, onHome, onAlbum, onCommunity, continuing = false }: {
  child: Child
  kind: StoryKind
  /** 닫기(시작 이야기를 '오늘 문제 풀기'에서 열었으면 부모가 그 문제 안내로 이어감) */
  onHome: () => void
  /** 시작 이야기 뒤 문제로 이어가는지(버튼 문구) */
  continuing?: boolean
  onAlbum: () => void
  onCommunity: () => void
}) {
  const query = useWeeklyTheme(child.id)
  const record = useRecordStoryView(child.id)
  const { companion, worn } = useLook()
  const theme = query.error ? null : (query.data ?? null)
  const reduce = useReducedMotion()
  // 못 불러온 그림·영상 주소(그것만 빼고 보여 줌)
  const [broken, setBroken] = useState<string[]>([])
  const fail = (url: string | null) => url && setBroken((list) => (list.includes(url) ? list : [...list, url]))
  const raw = theme ? media(theme, kind) : null
  const m = raw && {
    ...raw,
    image: raw.image && !broken.includes(raw.image) ? raw.image : null,
    video: raw.video && !broken.includes(raw.video) ? raw.video : null,
  }
  // 첫 화면: 재생할 것(영상, 그림 + 움직임)이 있으면 그것부터(고른 적이 없으면 응답에서 정함). 움직임 줄이기면 재생하지 않는다
  const [picked, setStage] = useState<'video' | 'story' | null>(null)
  const canPlay = !!m && !reduce && playable(m)
  const stage = picked ?? (m ? (canPlay ? 'video' : 'story') : null)
  const head = useRef<HTMLHeadingElement>(null)
  // 끝 이야기를 처음 펼치면 한 번 기록(서버도 멱등)
  const sent = useRef(false)
  useEffect(() => {
    if (!theme || stage !== 'story' || sent.current) return
    head.current?.focus()
    // OUTRO 열람 기록은 엔딩이고 무료 일요일이 아닐 때만 받는다(state-diagram 3.2.2)
    if (kind === 'OUTRO' && !theme.outroSeen && !themeClosed(theme)) { sent.current = true; record.mutate('OUTRO') }
  }, [theme, stage, kind, record])

  if (query.isPending) return <main className="st-paper st-sheet tw-page"><QueryStateNotice state="PROCESSING" /></main>
  if (!theme || !m?.text)
    return (
      <main className="st-paper st-sheet tw-page">
        <ErrorNotice error={query.error} retry={() => void query.refetch()} />
        {!query.error && <p className="st-empty">{kind === 'INTRO' ? '이번 주 시작 이야기가 아직 없어요.' : '이야기의 끝은 정답을 맞히거나 토요일에 금요일 문제를 다시 풀면 열려요.'}</p>}
        <button type="button" className="tw-go tw-go-plain" onClick={onHome}>홈으로</button>
      </main>
    )
  const label = kind === 'INTRO' ? '시작 이야기' : '이야기의 끝'

  if (stage === 'video' && canPlay)
    return (
      <main className="tw-video-stage" aria-label={kind === 'INTRO' ? '시작 영상' : '끝 영상'}>
        <div className="tw-video-box">
          <ThemeMotionPlayer imageUrl={m.image} videoUrl={m.video} motion={m.motion} label={label} onEnded={() => setStage('story')}
            onImageError={() => fail(m.image)} onVideoError={() => fail(m.video)} />
        </div>
        <div className="tw-video-foot">
          <span>{kind === 'INTRO' ? '영상이 끝나면 이번 주 이야기로 바로 이어져요' : '영상이 끝나면 끝 이야기로 바로 이어져요'}</span>
          <button type="button" onClick={() => setStage('story')}>건너뛰기 →</button>
        </div>
      </main>
    )

  if (kind === 'INTRO')
    return (
      <main className="st-paper st-sheet tw-page tw-story tw-intro">
        <header className="tw-head">
          <div>
            <p className="tw-kicker">이번 주 테마{theme.reused ? ' · 지난 테마를 다시 만나요' : ''}</p>
            <h1 ref={head} tabIndex={-1} className="tw-story-title">{theme.title}</h1>
          </div>
          {canPlay && <button type="button" className="tw-go tw-go-plain tw-go-small" onClick={() => setStage('video')}>{m.video ? '시작 영상 다시 보기' : '시작 장면 다시 보기'}</button>}
        </header>
        <div className="tw-story-body">
          <section aria-label="시작 이야기" className="tw-story-main">
            {(m.image || (!canPlay && m.video)) && (
              <div className="tw-story-art">
                <StoryArt m={m} label={label} still={canPlay} onImageError={() => fail(m.image)} onVideoError={() => fail(m.video)} />
              </div>
            )}
            <p className="tw-story-text">{m.text}</p>
          </section>
          <aside className="tw-story-side" aria-label="이번 주 수수께끼">
            {theme.bigQuestion && (
              <div className="tw-answer-card">
                <span>이번 주 수수께끼</span>
                <strong className="tw-story-q">{theme.bigQuestion}</strong>
                {theme.candidates.length > 0 && (
                  <ul className="tw-chip-list" aria-label="후보">
                    {theme.candidates.map((c) => <li key={c}>{c}</li>)}
                  </ul>
                )}
              </div>
            )}
            <p className="tw-story-how">월요일부터 금요일까지 하루에 한 문제씩 열려요. 문제를 마칠 때마다 단서가 하나씩 생기고, 금요일에 정답을 골라요.</p>
            {/* 무료 일요일(테마 닫힘)에는 다시 보기만: 서버가 INTRO 기록을 받지 않고(409 THEME_STORY_NOT_ALLOWED) 시작할 문제도 없어 홈으로만(#487 45행) */}
            <button type="button" className="tw-go tw-go-big" disabled={record.isPending}
              onClick={() => {
                if (theme.introSeen || themeClosed(theme)) return onHome()
                record.mutate('INTRO', { onSettled: onHome })
              }}>
              {themeClosed(theme) ? '홈으로' : continuing ? '이번 주 시작하기 · 오늘 문제로 →' : '이번 주 시작하기 →'}
            </button>
          </aside>
        </div>
        {/* 시작 이야기의 뭉치 장식은 뺌(사용자 의견 2026-11-16 "뭉치가 왜 있는지도 모르겠어", 시작 이야기 시안 없음). 이야기의 끝은 시안 Ending대로 둠 */}
      </main>
    )

  // 이야기의 끝(시안 Ending)
  const pick = theme.answerPick
  const allDone = theme.days.length === 5 && theme.days.every((d) => d.attemptStatus === 'COMPLETED')
  const rewards = [theme.completed && '개근 +30 포인트', theme.finished && '주간 완주 +10 포인트'].filter((x): x is string => !!x)
  return (
    <main className="st-paper st-sheet tw-page tw-story">
      <header className="tw-head">
        <div>
          {/* 머리말은 테마 제목만: 고른 날짜가 응답에 없어 요일을 정답 여부로 짐작하면 토요일에 맞혀도 "금요일"로 나왔음(#715). 맞혔는지는 오른쪽 결과 문구가 보여 줌 */}
          <p className="tw-kicker">{theme.title}</p>
          <h1 ref={head} tabIndex={-1} className="st-title-mix tw-ending-title"><span>이야기의</span>끝</h1>
        </div>
        {canPlay && <button type="button" className="tw-go tw-go-plain tw-go-small" onClick={() => setStage('video')}>{m.video ? '끝 영상 다시 보기' : '끝 장면 다시 보기'}</button>}
      </header>
      <div className="tw-story-body">
        <section aria-label="끝 이야기" className="tw-story-main">
          {(m.image || (!canPlay && m.video)) && (
            <div className="tw-story-art">
              <StoryArt m={m} label={label} still={canPlay} onImageError={() => fail(m.image)} onVideoError={() => fail(m.video)} />
            </div>
          )}
          <p className="tw-story-text">{m.text}</p>
        </section>
        <aside className="tw-story-side" aria-label="정답과 받은 것">
          {theme.answer && (
            <div className="tw-answer-card" data-right={pick?.correct || undefined}>
              {theme.bigQuestion && <span>{theme.bigQuestion}</span>}
              <strong className="tw-answer">{theme.answer}</strong>
              {pick && <span className="tw-pill" data-right={pick.correct || undefined}>내가 고른 답 · {pick.pick}</span>}
              {pick && (
                <p>{pick.correct ? '단서를 모아 정답을 맞혔어요!' : `정답은 ${josa.was(theme.answer)}요. 금요일 문제를 다시 풀어서 이야기의 끝까지 왔어요.`}</p>
              )}
            </div>
          )}
          <div className="tw-rewards">
            <h2>이번 주 받은 것</h2>
            {allDone ? (
              <p className="tw-frame-row">
                {m.image && <img src={m.image} alt="" />}
                {/* 액자는 다음 주 월요일부터 보유(서버 기준: 지난주까지만 앨범·추억의 벽). 그 주에는 정답이 담긴 액자가 친구들에게 먼저 새지 않게 월요일에 건다(사용자 결정 2026-11-16) */}
                <span><b>기념 액자</b>다섯 문제를 모두 마쳤어요. 다음 주 월요일부터 추억의 벽에 걸 수 있어요.</span>
              </p>
            ) : (
              <p>다섯 문제를 모두 마치면 기념 액자를 받아요.</p>
            )}
            {rewards.length > 0 && <ul className="tw-chip-list tw-chip-yellow">{rewards.map((r) => <li key={r}>{r}</li>)}</ul>}
            <p>금요일 문제의 친구 생각이 열렸어요.</p>
          </div>
          <div className="tw-story-actions">
            {allDone && <button type="button" className="tw-go" onClick={onAlbum}>추억 앨범 보기</button>}
            <button type="button" className="tw-go tw-go-plain" onClick={onCommunity}>친구 생각 보기</button>
            <button type="button" className="tw-go tw-go-plain" onClick={onHome}>홈으로</button>
          </div>
          <ErrorNotice error={record.error} />
        </aside>
      </div>
      <span className="tw-story-buddy" aria-hidden="true"><Companion kind={companion} worn={worn} size={110} decorative /></span>
    </main>
  )
}

/**
 * 이야기 화면의 그림. 화면 가득 재생을 했으면(still) 정지 그림, 아니면 그림 위 움직임(효과 등).
 * 화면 가득 재생이 없을 때(움직임 줄이기 등) 영상이 있으면 재생기에 넘겨 직접 재생할 수 있게 한다(자동 재생 없음).
 */
function StoryArt({ m, label, still, onImageError, onVideoError }: {
  m: { image: string | null; video: string | null; motion: unknown }
  label: string
  still: boolean
  onImageError: () => void
  onVideoError: () => void
}) {
  return (
    <ThemeMotionPlayer imageUrl={m.image} videoUrl={still ? null : m.video} motion={m.motion} label={label} still={still}
      onImageError={onImageError} onVideoError={onVideoError} />
  )
}
