import { fixtureStore, persistFixtureState } from './student.ts'
import { MOCK_STORY, MOCK_WEEKDAY_KEY, persistRetention, retentionState, themeMissions, weekStart } from './retention.ts'
import { setMockSubscription } from './payments.ts'
import type { Child } from '../../domain/classroom.ts'

/**
 * 개발 목업 "홈 상태" 바꿔 보기(캔버스 Home 보드의 homeState와 같은 8가지, 2026-11-15).
 * 고르면 그 요일로 바꾸고 이번 주 테마 다섯 문제의 푼 상태·정답 고르기·이야기 열람을 그 상황으로 만든다(목업 전용).
 */
export type MockThemeState = 'today' | 'behind' | 'resume' | 'pick' | 'ended' | 'sat' | 'sun' | 'none'
export const MOCK_THEME_NONE_KEY = 'sagomungchi:msw-theme-none'

/**
 * 목업 한 주 상황(#487 확인·시험용). 요일(월=0 … 일=6)과 월~금 상태 글자: D 그날 풂, L 늦게 풂(고르는 요일에 마무리), P 푸는 중, - 안 풂.
 * pick: 큰 질문 정답을 맞힘·틀림으로 골라 둠(없으면 안 고름). 맞히면 엔딩이라 끝 이야기도 본 것으로 둔다(홈이 끝 이야기를 먼저 띄우지 않게).
 */
export interface MockWeek { weekday: number; days: string; pick?: 'correct' | 'wrong' }
const PLANS: Record<Exclude<MockThemeState, 'none'>, MockWeek> = {
  today: { weekday: 3, days: 'DDD--' },
  behind: { weekday: 3, days: 'D-D--' },
  resume: { weekday: 3, days: 'DDDP-' },
  pick: { weekday: 4, days: 'DDDDD' },
  ended: { weekday: 4, days: 'DDDDD', pick: 'correct' },
  sat: { weekday: 5, days: 'DDDD-' },
  sun: { weekday: 6, days: 'DDDDD' },
}

export const mockThemeNone = () => {
  try { return sessionStorage.getItem(MOCK_THEME_NONE_KEY) === 'true' } catch { return false }
}

export async function applyMockThemeState(child: Child, state: MockThemeState | '', premium: boolean) {
  setMockSubscription(child.id, premium ? 'PREMIUM' : 'FREE')
  try {
    sessionStorage.setItem(MOCK_THEME_NONE_KEY, String(state === 'none'))
    if (!state || state === 'none') sessionStorage.removeItem(MOCK_WEEKDAY_KEY)
  } catch { /* 저장소를 못 쓰면 실제 날짜 */ }
  if (!state || state === 'none') return
  await applyMockWeek(child, PLANS[state])
}

/**
 * 요일을 바꾸고 이번 주 테마 다섯 문제의 푼 상태·정답 고르기·이야기 열람을 그 상황으로 만든다(목업 전용, 홈 상태 바꿔 보기와 시험이 같이 씀).
 * premium을 주면 이용권도 바꾼다(무료·프리미엄 일요일).
 */
export async function applyMockWeek(child: Child, plan: MockWeek, premium?: boolean) {
  if (premium !== undefined) setMockSubscription(child.id, premium ? 'PREMIUM' : 'FREE')
  try { sessionStorage.setItem(MOCK_WEEKDAY_KEY, String(plan.weekday)) } catch { /* 저장소를 못 쓰면 실제 날짜 */ }
  const missions = themeMissions((await fixtureStore.home(child)).missions, child.grade).days.map((d) => d.mission)
  const ids = new Set(missions.map((m) => m.id))
  const data = fixtureStore.snapshot()
  const base = data.attempts.find((a) => a.finishedAt)
  if (!base) return
  const now = new Date().toISOString()
  const added = missions.flatMap((m, i) => {
    const mark = plan.days[i]
    if (mark !== 'D' && mark !== 'L' && mark !== 'P') return []
    const a = structuredClone(base)
    a.studentId = child.id
    a.attemptId = `theme-state-${i}-${Date.now()}`
    a.mission = { ...base.mission, ...m }
    if (mark === 'P') {
      a.status = 'IN_PROGRESS'
      delete a.finishedAt
      delete a.reflection
    } else a.status = 'COMPLETED'
    return [a]
  })
  fixtureStore.restoreSnapshot({
    ...data,
    attempts: [...data.attempts.filter((a) => !(a.studentId === child.id && ids.has(a.mission.id))), ...added],
  })
  persistFixtureState()
  const week = `${child.id}:${weekStart()}`
  missions.forEach((m, i) => {
    const key = `${week}:${m.id}`
    const mark = plan.days[i]
    if (mark === 'D' || mark === 'L') retentionState.completions[key] = { weekday: mark === 'D' ? i : plan.weekday, at: now }
    else delete retentionState.completions[key]
  })
  const wrong = MOCK_STORY.candidates.find((c) => c !== MOCK_STORY.answer)!
  if (plan.pick) retentionState.picks[week] = { pick: plan.pick === 'correct' ? MOCK_STORY.answer : wrong, correct: plan.pick === 'correct', at: now }
  else delete retentionState.picks[week]
  // 캔버스 홈 상태처럼 시작 이야기는 본 것으로, 엔딩 뒤는 끝 이야기도 본 것으로(홈 그대로 보이게)
  retentionState.storyViews = retentionState.storyViews.filter((v) => !v.startsWith(`${week}:`))
  retentionState.storyViews.push(`${week}:INTRO`)
  if (plan.pick === 'correct') retentionState.storyViews.push(`${week}:OUTRO`)
  persistRetention()
}
