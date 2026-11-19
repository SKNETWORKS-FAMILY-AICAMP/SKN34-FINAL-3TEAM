import { useEffect } from 'react'
import { useStudentHome } from '../../../data/classroom/useClassroom.ts'
import { useMyPoints, useWeeklyTheme } from '../../../data/retention/queries.ts'
import type { Child, Mission } from '../../../domain/classroom.ts'
import { studentThinkingLabels } from '../../../domain/classroom.ts'
import { DAY_LABELS, clueCount, dayAction, onTimeCount, pickStage, remainingCandidates, storyToShow, themeClosed, todayThemeDay } from '../../../domain/retention.ts'
import type { AttemptContext, StoryKind, WeeklyTheme, WeeklyThemeDay } from '../../../domain/retention.ts'
import { ErrorNotice } from '../../shared/ClassroomParts.tsx'
import { QueryStateNotice } from '../../common/QueryStateNotice.tsx'
import { HomeScene } from './HomeScene.tsx'
import { useLook } from './lookContext.ts'
import './home.css'

/** 이 탭에서 이미 자동으로 띄운 이야기(열람 기록이 실패해도 같은 세션에서 다시 띄우지 않음) */
const autoShown = new Set<string>()

type ChipState = 'done' | 'late' | 'missed' | 'closed' | 'today' | 'doing' | 'later'

/**
 * 요일 칩 상태: ✓ 그날 풀었음(색칠), ✓ 늦게 풀었음(흰 바탕, "그날 풀면 ✓"·개근 진행과 어긋나지 않게, 사용자 확인 2026-11-16),
 * ✗ 지난 요일인데 안 풀었음(평일은 토요일까지, 토요일·프리미엄 일요일은 오늘까지 풀 수 있음), ✗ 닫혀서 못 풀었음(무료 일요일), 오늘·푸는 중, 아직 안 열림
 */
function chipState(d: WeeklyThemeDay, today: WeeklyThemeDay | null): ChipState {
  if (d.attemptStatus === 'COMPLETED') return d.completedOnDay ? 'done' : 'late'
  if (d.attemptStatus === 'IN_PROGRESS') return 'doing'
  if (today && d.day === today.day) return 'today'
  if (d.state === 'LOCKED') return 'later'
  if (d.state === 'CLOSED') return 'closed'
  return 'missed'
}
const CHIP_MARK: Record<ChipState, string> = { done: '✓', late: '✓', missed: '✗', closed: '✗', today: '오늘', doing: '푸는 중', later: '' }
/**
 * 칩 설명(화면 읽기). 안 푼 문제를 풀 수 있는 마지막 날: 평일은 토요일, 토요일·프리미엄 일요일(되돌아보기 열림)은 오늘(#487 45행,
 * 응답만으로는 토요일과 프리미엄 일요일을 가를 수 없어 둘 다 "오늘까지")
 */
const chipNote = (st: ChipState, until: string): string =>
  ({
    done: '그날 풀었어요',
    late: '풀었어요, 그날은 아니에요',
    missed: `아직 안 풀었어요, ${until} 풀 수 있어요`,
    closed: '풀지 못했어요',
    today: '오늘 문제',
    doing: '푸는 중',
    later: '아직 안 열렸어요',
  })[st]
const dayList = (days: WeeklyThemeDay[]) => `${days.map((d) => DAY_LABELS[d.day]).join('·')}요일`

/** "물고기방이었어" / "로봇 방이었어": 받침이 있으면 '이었어', 없으면 '였어' */
function wasWord(word: string) {
  const code = word.charCodeAt(word.length - 1) - 0xac00
  return code >= 0 && code <= 11171 && code % 28 !== 0 ? '이었어' : '였어'
}

/** 말풍선 대사(규칙 기반, AI 호출 없음). 마지막 줄은 늘 테마 장소 인사 */
function lines(theme: WeeklyTheme | null, place: string, missed: WeeklyThemeDay[], today: WeeklyThemeDay | null, until: string) {
  const first = !theme
    ? '새 테마를 준비하고 있어. 그동안 내 공책을 볼까?'
    : theme.ending === 'ENDED'
      ? // 엔딩 뒤에만 정답이 오므로(P23) 그때만 정답을 말한다. 엔딩 전이면 일요일이어도 정답을 말하지 않는다
        theme.answer
        ? `정답은 ${theme.answer}${wasWord(theme.answer)}! 이번 주 이야기가 끝났어.`
        : '이번 주 이야기가 끝났어! 언제든 다시 볼 수 있어.'
      : themeClosed(theme)
        ? '이번 주 테마가 끝났어. 다음 테마는 월요일에 열려!'
      : missed.length
        ? // 둘 이상이면 요일 칩을 눌러 골라 풀 수 있다고 알려 준다(#487 42행)
          `${dayList(missed)} 문제를 아직 안 풀었어. ${missed.length > 1 ? '아래 요일을 눌러 골라 풀 수 있어!' : `${until} 풀 수 있어!`}`
        : today?.attemptStatus === 'IN_PROGRESS'
          ? '쓰던 답이 저장돼 있어. 이어서 써 볼까?'
          : today && today.attemptStatus !== 'COMPLETED'
            ? '오늘 문제를 풀면 단서가 하나 더 생겨!'
            : theme.review.open
              ? '주말이야! 안 푼 문제를 풀거나 다시 풀어 볼까?'
              : '오늘 문제를 다 풀었어! 내일 또 만나.'
  return [first, `우리 ${place}에 와 줘서 고마워!`]
}

/**
 * 학생 홈(SC-02-004, #589·#648·#487). 왼쪽은 이번 주 테마·오늘 문제·모은 단서·포인트, 오른쪽은 "우리 집" 장면과 요일 칩.
 * 1440×900에서 스크롤 없이 보이게 장면 크기를 창 높이에 맞춘다.
 */
export function StudentHome({
  child,
  onStartTheme,
  onJournal,
  onRoom,
  onMissions,
  onPoints,
  onClues,
  onPick,
  onStory,
  onIntroThen,
  onReview,
}: {
  child: Child
  /** 테마 문제 열기(새로 시작·이어 풀기 모두, 오늘 장면 #807) */
  onStartTheme: (mission: Mission, context: AttemptContext) => void
  onJournal: () => void
  onRoom: () => void
  /** 더 풀어 보기(생각 유형별 미션 고르기). 무료 학생은 미션을 시작할 때 403 PREMIUM_REQUIRED를 받아 안내 창이 프리미엄 안내를 띄운다(#487, 결제 유도 문구 없음) */
  onMissions: () => void
  /** 내 포인트 카드 → 뭉치 친구들(#648 구현 전에는 설정의 포인트) */
  onPoints: () => void
  onClues: () => void
  onPick: () => void
  /** 시작 이야기·이야기의 끝(#440). replace는 홈에 들어오자마자 자동으로 띄울 때(뒤로 가기로 홈에 갇히지 않게) */
  onStory: (kind: StoryKind, replace?: boolean) => void
  /** 그 주 시작 이야기를 아직 안 봤으면 문제를 열기 전에 시작 이야기부터(이야기를 닫으면 그 문제로 이어감) */
  onIntroThen: (mission: Mission, context: AttemptContext) => void
  onReview: () => void
}) {
  const { t, companion, worn } = useLook()
  const homeQuery = useStudentHome(child)
  const home = homeQuery.error ? undefined : homeQuery.data
  const ready = home && home.state !== 'FAILED' && home.state !== 'PROCESSING'
  const themeQuery = useWeeklyTheme(child.id)
  const points = useMyPoints(child.id)
  const theme = themeQuery.error ? null : (themeQuery.data ?? null)
  const byId = new Map((home?.missions ?? []).map((m) => [m.id, m]))
  const open = (missionId: string, context: AttemptContext) => {
    const m = byId.get(missionId)
    if (!m) return
    // 푸는 중이면 오늘 장면이 이어하기를 판단한다(답을 안 쓴 시도는 장면부터, 쓴 게 있으면 바로 답변 작성, #807)
    if (m.status === 'IN_PROGRESS' && m.attemptId) onStartTheme(m, context)
    // 그 주 처음 문제를 열 때 시작 이야기부터(user-flow: 그 주 처음 '오늘 문제 풀기'를 누를 때, 사용자 결정 2026-11-13·14)
    else if (context === 'THEME_DAY' && theme?.intro && !theme.introSeen && !themeClosed(theme)) onIntroThen(m, context)
    else onStartTheme(m, context)
  }
  const today = theme ? todayThemeDay(theme) : null
  // 공개됐는데 아직 시작하지 않은 지난 요일(오늘 문제는 큰 버튼). 모두 시작할 수 있다(#483 누적 공개, #487 42행)
  const missed = theme?.days.filter((d) => chipState(d, today) === 'missed') ?? []
  const closed = theme ? themeClosed(theme) : false
  const until = theme?.review.open ? '오늘까지' : '토요일까지'
  const todayTitle = today ? (today.title ?? byId.get(today.missionId)?.title ?? '오늘의 문제') : null
  const left = theme ? remainingCandidates(theme) : []
  const stage = theme ? pickStage(theme) : null
  // 엔딩 뒤 아직 안 봤으면 이야기의 끝을 먼저 띄운다(시안 Home ended "엔딩 뒤 처음 들어오면 끝 영상이 먼저"). 시작 이야기는 홈에서 자동으로 띄우지 않고
  // 그 주 처음 문제를 열 때(open) 보여 준다(user-flow 사용자 결정 2026-11-13·14)
  const story = theme && storyToShow(theme) === 'OUTRO' ? 'OUTRO' : null
  useEffect(() => {
    if (!theme || !story) return
    const key = `${child.id}:${theme.themeId}:${theme.weekStart}:${story}`
    if (autoShown.has(key)) return
    autoShown.add(key)
    onStory(story, true)
  }, [theme, story, child.id, onStory])

  return (
    <main className="sh-home">
      {(homeQuery.isPending || themeQuery.isPending) && <QueryStateNotice state="PROCESSING" />}
      <ErrorNotice error={homeQuery.error} retry={() => void homeQuery.refetch()} />
      {home && home.state !== 'OK' && <QueryStateNotice state={home.state} />}
      <div className="sh-hero">
        <div className="sh-left">
          {theme ? (
            <>
              <p className="sh-hello">
                안녕, {child.nickname}! · 이번 주 테마{theme.reused && ' · 지난 테마를 다시 만나요'}
              </p>
              <h1 className="sh-title">{theme.title}</h1>
              {theme.bigQuestion && <p className="sh-question">{theme.bigQuestion}</p>}
              {ready && today && today.attemptStatus !== 'COMPLETED' ? (
                <div className="sh-cta-row">
                  <button type="button" className="sh-cta" onClick={() => open(today.missionId, 'THEME_DAY')}>
                    {today.attemptStatus === 'IN_PROGRESS' ? '이어서 풀기' : '오늘 문제 풀기'}
                    <span aria-hidden="true" className="sh-cta-play">
                      ▶
                    </span>
                  </button>
                  <p className="sh-cta-note">
                    <span>
                      {DAY_LABELS[today.day]}요일 · {studentThinkingLabels[today.thinkingType]} · {todayTitle}
                    </span>
                    <b>오늘 안에 풀면 +5 포인트</b>
                  </p>
                </div>
              ) : stage === 'READY' ? (
                // 금요일 문제까지 마쳐 단서를 다 모았으면 정답 고르기(시안 Home pick)
                <div className="sh-cta-row">
                  <button type="button" className="sh-cta" onClick={onPick}>
                    정답 고르러 가기
                    <span aria-hidden="true" className="sh-cta-play">
                      ▶
                    </span>
                  </button>
                  <p className="sh-cta-note">
                    {/* 다 모았을 때만 "모두"(한 요일을 건너뛰면 5장 중 4장, #715) */}
                    <span>단서 {clueCount(theme)}장을 {clueCount(theme) >= theme.days.length ? '모두 ' : ''}모았어요</span>
                    <b>정답은 한 주에 한 번 골라요</b>
                  </p>
                </div>
              ) : theme.review.open ? (
                <div className="sh-cta-row">
                  <button type="button" className="sh-cta" onClick={onReview}>
                    주말 되돌아보기
                    <span aria-hidden="true" className="sh-cta-play">
                      ▶
                    </span>
                  </button>
                  <p className="sh-cta-note">
                    <span>안 푼 문제는 지금 풀고</span>
                    <b>푼 문제는 다시 풀 수 있어요</b>
                  </p>
                </div>
              ) : theme.ending === 'ENDED' && theme.outro && !themeClosed(theme) ? (
                // 시안 Home ended: "이야기의 끝 다시 보기"
                <div className="sh-cta-row">
                  <button type="button" className="sh-cta" onClick={() => onStory('OUTRO')}>
                    이야기의 끝 다시 보기
                    <span aria-hidden="true" className="sh-cta-play">
                      ▶
                    </span>
                  </button>
                  <p className="sh-cta-note">
                    {theme.answer && <b>정답은 {theme.answer}{wasWord(theme.answer)}요!</b>}
                    <span>내 공책에서 이번 주 기록을 볼 수 있어요.</span>
                  </p>
                </div>
              ) : themeClosed(theme) ? (
                // 시안 Home 일요일 상태: 주황 버튼 "이번 주 기록 보기" → 주말 되돌아보기 닫힘 화면(시안 Review sun, 기록·이야기의 끝 다시 보기)
                <div className="sh-cta-row">
                  <button type="button" className="sh-cta" onClick={onReview}>
                    이번 주 기록 보기
                    <span aria-hidden="true" className="sh-cta-play">
                      ▶
                    </span>
                  </button>
                  <p className="sh-cta-note">
                    <b>이번 주 테마가 끝났어요.</b>
                    <span>다음 테마는 월요일에 열려요.</span>
                  </p>
                </div>
              ) : missed.length > 0 ? (
                // 오늘 문제는 풀었지만 지난 요일이 남음("모두 풀었어요"라고 하지 않게, #487 확인 표에서 찾음)
                <p className="sh-cta-note">
                  <b>오늘 문제를 풀었어요.</b>
                  <span>안 푼 문제는 {until} 풀 수 있어요.</span>
                </p>
              ) : today?.day === 'FRI' ? (
                // 금요일 뒤에는 새 문제가 없다(토요일은 되돌아보기, #487 확인 표에서 찾음)
                <p className="sh-cta-note">
                  <b>이번 주 문제를 모두 풀었어요.</b>
                  <span>토요일에는 푼 문제를 다시 풀어 볼 수 있어요.</span>
                </p>
              ) : (
                <p className="sh-cta-note">
                  <b>오늘 열린 문제를 모두 풀었어요.</b>
                  <span>다음 요일에 새 문제가 열려요.</span>
                </p>
              )}
              {ready && missed.length > 0 && (
                // 시안 Home behind "아직 안 푼 문제 1개 · 화요일". 둘 이상이면 가장 앞 요일부터 열고, 다른 요일은 아래 요일 칩으로 고른다
                <button type="button" className="sh-missed" onClick={() => open(missed[0].missionId, 'THEME_DAY')}>
                  <b>
                    아직 안 푼 문제 {missed.length}개 · {dayList(missed)}
                  </b>
                  <span>
                    {until} 풀 수 있어요{missed.length > 1 && ` · ${DAY_LABELS[missed[0].day]}요일부터`} →
                  </span>
                </button>
              )}
              <div className="sh-stats" aria-label="이번 주 기록">
                {/* 테마가 닫힌 뒤(일요일 등)에는 단서가 더 쓰일 데가 없어 숨긴다(사용자 결정 2026-11-15) */}
                {!themeClosed(theme) && (
                  <button type="button" className="sh-stat sh-stat-clue" onClick={onClues}>
                    <small>모은 단서 →</small>
                    <b>{clueCount(theme)}장</b>
                    {theme.candidates.length > 0 && <small>남은 후보 {left.length}개</small>}
                  </button>
                )}
                <button type="button" className="sh-stat sh-stat-point" onClick={onPoints}>
                  <small>내 포인트 →</small>
                  <b>{points.data ? points.data.balance : '…'}</b>
                </button>
              </div>
              {/* 평일에만: 토요일·프리미엄 일요일은 큰 버튼이 되돌아보기, 무료 일요일은 다시 풀 수 없음(#487 45행) */}
              {stage === 'RETRY' && !theme.review.open && !closed && (
                <p className="sh-cta-note">
                  <span>정답 고르기는 아쉬웠어요.</span>
                  <b>토요일에 금요일 문제를 다시 풀면 이야기의 끝을 볼 수 있어요.</b>
                </p>
              )}
              <div className="sh-links">
                {theme.intro && (
                  <button type="button" onClick={() => onStory('INTRO')}>
                    {theme.introVideoUrl ? '시작 영상 다시 보기' : '시작 이야기 다시 보기'}
                  </button>
                )}
                {/* 토요일·프리미엄 일요일은 큰 버튼이 되돌아보기라 엔딩 다시 보기를 여기에(평일은 큰 버튼, 무료 일요일은 되돌아보기 닫힘 화면) */}
                {theme.ending === 'ENDED' && theme.outro && theme.review.open && (
                  <button type="button" onClick={() => onStory('OUTRO')}>
                    이야기의 끝 다시 보기
                  </button>
                )}
                <button type="button" onClick={onMissions}>
                  더 풀어 보기(미션 고르기) →
                </button>
              </div>
            </>
          ) : themeQuery.isPending ? null /* 불러오는 동안 "테마 없음"을 잠깐 보이지 않게(점검 2026-11-15) */ : (
            <>
              <h1 className="sh-title">이번 주 테마를 준비하고 있어요</h1>
              <p className="sh-cta-note">
                <span>테마가 열리면 여기에서 오늘 문제를 풀 수 있어요.</span>
                <span>그동안 내 공책에서 지난 기록을 볼 수 있어요.</span>
              </p>
              <button type="button" className="sh-cta sh-cta-plain" onClick={onJournal}>
                내 공책 보기
              </button>
              {/* 테마가 없는 학년도 미션 고르기로 갈 수 있게(실서버 E2E 2026-11-16 발견: 버튼이 테마 있을 때만 있었음) */}
              <div className="sh-links">
                <button type="button" onClick={onMissions}>
                  더 풀어 보기(미션 고르기) →
                </button>
              </div>
            </>
          )}
        </div>
        <div className="sh-scene-col">
          <HomeScene t={t} companion={companion} worn={worn} lines={lines(theme, t.place, missed, today, until)} onRoom={onRoom} />
          {theme && (
            <>
              <ol className="sh-chips" aria-label="이번 주 진행">
                {theme.days.map((d) => {
                  const st = chipState(d, today)
                  // 지금 새로 시작하거나 이어서 할 수 있는 날만 누를 수 있다(공개된 안 푼 문제·푸는 중, #487 42행). 마무리한 날(다시 풀기는 주말 되돌아보기)·
                  // 안 열린 날·무료 일요일(이번 주 기록·엔딩 다시 보기만, FN-DSH-01)은 누르지 않는다
                  const action = ready && !closed ? dayAction(theme, d) : null
                  const mark = (
                    <>
                      {DAY_LABELS[d.day]}
                      {/* 오늘·푸는 중은 요일 글자와 떨어진 작은 꼬리표로("목 푸는 중"이 한 말처럼 읽히지 않게, 사용자 의견 2026-11-16) */}
                      {CHIP_MARK[st] && <span aria-hidden="true" className={st === 'today' || st === 'doing' ? 'sh-chip-tag' : undefined}>{CHIP_MARK[st]}</span>}
                    </>
                  )
                  return (
                    <li key={d.day} data-state={st} data-can={action === 'START' || action === 'RESUME' || undefined} aria-label={`${DAY_LABELS[d.day]}요일 ${chipNote(st, until)}`}>
                      {action === 'START' || action === 'RESUME' ? (
                        <button type="button" className="sh-chip-btn" aria-label={`${DAY_LABELS[d.day]}요일 문제 ${action === 'RESUME' ? '이어서 풀기' : '풀기'}`}
                          onClick={() => open(d.missionId, 'THEME_DAY')}>
                          {mark}
                        </button>
                      ) : (
                        mark
                      )}
                    </li>
                  )
                })}
              </ol>
              <p className="sh-chip-note">
                색칠된 ✓는 그날 푼 날 · 5일 모두 그날 풀면 <b>+30 포인트</b> (지금 {onTimeCount(theme)} / 5)
              </p>
            </>
          )}
        </div>
      </div>
    </main>
  )
}
