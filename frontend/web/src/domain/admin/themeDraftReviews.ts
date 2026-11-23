import { THEME_GRADE_LABELS, type ThemeGrade } from './retention.ts'
import { THEME_SCENES, themeDraftLabels, themeDraftSourceLabels } from './themeDrafts.ts'
import type { ThemeDraftSource, ThemeDraftStatus, ThemeSceneName } from './themeDrafts.ts'

export const reviewStageLabels = {
  review: '검수 대기', pair: '영상 비교 대기', adopted: '미션 검토 중', closed: '게시 마감 · 미선정',
  ready: '게시 대기', published: '게시 완료', discarded: '버림', generating: '생성 중', check_failed: '검사 실패', failed: '생성 실패',
} as const
export type ThemeReviewStage = keyof typeof reviewStageLabels
export interface ThemeDraftReviewRow {
  draftId: string; title: string; thumbnailUrl: string | null; grade: ThemeGrade; source: ThemeDraftSource; status: ThemeDraftStatus
  stage: ThemeReviewStage; weekStart: string; appliedWeek: string; plannedWeek: string | null; updatedAt: string
  themeId: string | null; comparisonScene: ThemeSceneName | null
}
export interface ThemeDraftReviewPage { items: ThemeDraftReviewRow[]; page: number; size: number; totalElements: number; weeks: string[] }

const record = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)
const isoDate = (value: unknown): value is string => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
const member = <K extends string>(labels: Record<K, unknown>, value: unknown): value is K => typeof value === 'string' && Object.hasOwn(labels, value)
const natural = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0

export function readThemeDraftReviewPage(raw: unknown): ThemeDraftReviewPage {
  const invalid = () => new Error('주간 테마 검수 목록 응답을 확인할 수 없습니다.')
  if (!record(raw) || !natural(raw.page) || !natural(raw.size) || raw.size < 1 || !natural(raw.totalElements)
    || !Array.isArray(raw.weeks) || !raw.weeks.every(isoDate) || !Array.isArray(raw.items)) throw invalid()
  const items = raw.items.map((r: unknown): ThemeDraftReviewRow => {
    if (!record(r) || typeof r.draftId !== 'string' || !r.draftId || typeof r.title !== 'string' ||
      (r.thumbnailUrl !== null && typeof r.thumbnailUrl !== 'string') || !member(THEME_GRADE_LABELS, r.grade) ||
      !member(themeDraftSourceLabels, r.source) || !member(themeDraftLabels, r.status) || !member(reviewStageLabels, r.stage) ||
      !isoDate(r.weekStart) || !isoDate(r.appliedWeek) || (r.plannedWeek !== null && !isoDate(r.plannedWeek)) ||
      typeof r.updatedAt !== 'string' || (r.themeId !== null && typeof r.themeId !== 'string') ||
      (r.comparisonScene !== null && !THEME_SCENES.includes(r.comparisonScene as ThemeSceneName))) throw invalid()
    return { draftId: r.draftId, title: r.title, thumbnailUrl: r.thumbnailUrl, grade: r.grade, source: r.source, status: r.status,
      stage: r.stage, weekStart: r.weekStart, appliedWeek: r.appliedWeek, plannedWeek: r.plannedWeek, updatedAt: r.updatedAt,
      themeId: r.themeId, comparisonScene: r.comparisonScene as ThemeSceneName | null }
  })
  return { page: raw.page, size: raw.size, totalElements: raw.totalElements, weeks: raw.weeks, items }
}
