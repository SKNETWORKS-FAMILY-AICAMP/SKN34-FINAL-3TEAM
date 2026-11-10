import type { ItemSlot, ThemeDay } from '../retention.ts'

/** 관리자 주간 테마 (FN-ADM-22, API 명세 2.8 구현 예정). 미션과 같은 작성→검토→게시 흐름. */
export type ThemeGrade = 'G3' | 'G4' | 'G5' | 'G6'
export const THEME_GRADE_LABELS: Record<ThemeGrade, string> = { G3: '초3', G4: '초4', G5: '초5', G6: '초6' }
export type ThemeStatus = 'DRAFT' | 'REVIEW_REQUIRED' | 'PUBLISHED' | 'UNPUBLISHED'
export const THEME_STATUS_LABELS: Record<ThemeStatus, string> = {
  DRAFT: '작성 중',
  REVIEW_REQUIRED: '검토 요청',
  PUBLISHED: '게시 중',
  UNPUBLISHED: '게시 중단',
}
export interface AdminWeeklyTheme {
  themeId: string
  grade: ThemeGrade
  weekStart: string
  title: string
  intro: string
  days: { day: ThemeDay; missionId: string }[]
  status: ThemeStatus
  updatedAt: string
}
export type WeeklyThemeInput = Pick<AdminWeeklyTheme, 'grade' | 'weekStart' | 'title' | 'intro' | 'days'>

/** 관리자 꾸미기 아이템 (FN-ADM-23). 삭제는 없고 판매 중단만 있다. */
export type LookItemStatus = 'ON_SALE' | 'STOPPED'
export interface AdminLookItem {
  itemId: string
  code: string
  slot: ItemSlot
  name: string
  pricePoints: number
  assetKey: string
  status: LookItemStatus
  updatedAt: string
}
export type LookItemInput = Pick<AdminLookItem, 'code' | 'slot' | 'name' | 'pricePoints' | 'assetKey'>

/** 게시 검사 실패(422 WEEKLY_THEME_PUBLISH_INCOMPLETE)의 이유 목록. 서버가 `errors`로 주면 그대로 보인다. */
export function publishProblems(problem: unknown): string[] {
  const errors = (problem as { errors?: unknown })?.errors
  if (!Array.isArray(errors)) return []
  return errors.flatMap((e) => {
    const v = (e ?? {}) as Record<string, unknown>
    const text = typeof v.message === 'string' ? v.message : typeof v.detail === 'string' ? v.detail : null
    return text ? [text] : []
  })
}
