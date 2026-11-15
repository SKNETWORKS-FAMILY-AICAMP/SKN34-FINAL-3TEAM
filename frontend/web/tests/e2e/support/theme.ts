import { expect, type Browser } from '@playwright/test'
import { withAdminApi } from './admin.ts'

export const THEME_TITLE = 'E2E 쉬는 시간 탐정단'
export const THEME_INTRO = '쉬는 시간이 늘어난다는 소문이 돌아요. 이번 주에는 그 소문이 사실인지 함께 따져 봐요.'
/** 월요일 문제: 데모 미션 2번(초3·EVALUATE·NARRATIVE). 서술형이라 되묻기가 생긴다 */
export const MONDAY_MISSION = '쉬는 시간을 늘린다면?'

// backend/learning-service/db/seed/demo_missions.sql 초3 게시 미션 1~5번: 다섯 생각 유형 하나씩(게시 검사 THINKING_TYPES)
const demo = (n: number) => `d1000000-0000-4000-8000-00000000000${n}`
const DAYS = [['MON', 2], ['TUE', 1], ['WED', 3], ['THU', 4], ['FRI', 5]] as const

/** KST 요일(0=일 … 6=토). 서버 날짜를 고정할 수 없어 테마 요일 규칙에 걸리는 날을 건너뛸 때 쓴다 */
export function kstWeekday(now = new Date()) {
  return new Date(now.getTime() + 9 * 3_600_000).getUTCDay()
}

/** 이번 주 월요일(KST) yyyy-mm-dd */
export function kstMonday(now = new Date()) {
  const kst = new Date(now.getTime() + 9 * 3_600_000)
  kst.setUTCDate(kst.getUTCDate() - ((kst.getUTCDay() + 6) % 7))
  return kst.toISOString().slice(0, 10)
}

/**
 * 이번 주 초3 주간 테마를 관리자 경로로 작성 → 검토 요청 → 게시한다(api-spec 2.8, core → learning 프록시).
 * 같은 학년·주에 게시 테마는 하나뿐이라 이미 있으면 그대로 쓴다(같은 스택에서 다시 실행).
 */
export function ensureWeeklyTheme(browser: Browser, baseURL: string) {
  return withAdminApi(browser, baseURL, async ({ request, headers }) => {
    const api = (path: string) => `/api/v1/admin/weekly-themes${path}`
    const weekStart = kstMonday()
    const listed = await request.get(api(`?grade=G3&weekStart=${weekStart}&status=PUBLISHED`), { headers })
    expect(listed.ok(), await listed.text()).toBe(true)
    const { items } = await listed.json() as { items: { themeId: string; weekStart: string; title: string }[] }
    const current = items.find((item) => item.weekStart === weekStart)
    if (current) return current

    const created = await request.post(api(''), {
      headers,
      data: {
        grade: 'G3', weekStart, title: THEME_TITLE, intro: THEME_INTRO,
        days: DAYS.map(([day, n]) => ({ day, missionId: demo(n) })),
      },
    })
    expect(created.status(), await created.text()).toBe(201)
    const { themeId } = await created.json() as { themeId: string }
    for (const action of ['review-request', 'publish']) {
      const response = await request.post(api(`/${themeId}/${action}`), { headers, data: {} })
      expect(response.ok(), `${action}: ${await response.text()}`).toBe(true)
    }
    return { themeId, weekStart, title: THEME_TITLE }
  })
}
