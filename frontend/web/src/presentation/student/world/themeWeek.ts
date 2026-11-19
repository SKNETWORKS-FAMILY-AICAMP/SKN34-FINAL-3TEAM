import { useStudentHome } from '../../../data/classroom/useClassroom.ts'
import type { Child, Mission } from '../../../domain/classroom.ts'
import { DAY_LABELS, ruledOutOn } from '../../../domain/retention.ts'
import type { AttemptContext, ThemeDay, WeeklyTheme, WeeklyThemeDay } from '../../../domain/retention.ts'

/* 주간 테마 화면(단서 모음·정답 고르기·이야기·되돌아보기)이 같이 쓰는 말 다듬기·판정·미션 열기(#440·#487) */

/** 받침 유무로 고르는 조사: 은/는, 이/가, 이었어/였어, 으로/로, 이야/야 */
function hasFinal(word: string) {
  const code = word.charCodeAt(word.length - 1) - 0xac00
  return code >= 0 && code <= 11171 && code % 28 !== 0
}
const finalRieul = (word: string) => (word.charCodeAt(word.length - 1) - 0xac00) % 28 === 8
export const josa = {
  topic: (w: string) => w + (hasFinal(w) ? '은' : '는'),
  subject: (w: string) => w + (hasFinal(w) ? '이' : '가'),
  was: (w: string) => w + (hasFinal(w) ? '이었어' : '였어'),
  to: (w: string) => w + (hasFinal(w) && !finalRieul(w) ? '으로' : '로'),
  is: (w: string) => w + (hasFinal(w) ? '이야' : '야'),
}
export const list = (xs: string[]) => xs.join(', ')
export const dayName = (d: ThemeDay) => `${DAY_LABELS[d]}요일`

/**
 * 요일 문제 열기(홈과 같은 규칙): 맥락을 붙여 연다. 푸는 중인 문제도 같은 길로 보내 오늘 장면이 이어하기를 판단한다
 * (답을 안 쓴 시도는 장면부터, 쓴 게 있으면 바로 답변 작성, #807). 미션 그림도 여기서 찾는다.
 */
export function useThemeMissions(
  child: Child,
  onStartTheme: (mission: Mission, context: AttemptContext) => void,
) {
  const home = useStudentHome(child)
  const byId = new Map((home.data?.missions ?? []).map((m) => [m.id, m]))
  const open = (missionId: string, context: AttemptContext) => {
    const m = byId.get(missionId)
    if (m) onStartTheme(m, context)
  }
  const image = (missionId: string) => {
    const m = byId.get(missionId)
    const uri = m?.staticSceneUri || m?.sceneUri || ''
    return /^(https?:\/\/|\/[^/])/.test(uri) ? uri : null
  }
  return { byId, open, image, home }
}

/** 단서 한 장이 후보에 준 영향(시안 Clues): 이번에 새로 뺀 후보와 이미 빠져 있던 후보를 나눈다. */
export function clueEffect(theme: WeeklyTheme, d: WeeklyThemeDay) {
  const outs = d.rulesOut ?? []
  const fresh = outs.filter((c) => ruledOutOn(theme, c) === d.day)
  const again = outs.filter((c) => ruledOutOn(theme, c) !== d.day)
  return { fresh, again }
}
/** 가장 최근에 얻은 단서 요일(그날 문제를 마친 직후 "새 단서!"). */
export const latestClueDay = (theme: WeeklyTheme) => theme.days.filter((d) => d.clue).at(-1)?.day ?? null
