import { apiFetch } from '../apiClient.ts'
import { json } from '../parent/api.ts'
import type { AdminWeeklyTheme, ThemeGrade, ThemeStatus } from '../../domain/admin/retention.ts'
import type { Page } from '../../domain/parent.ts'

export interface PlannerDraft { draftId: string; title: string; generationWeek: string; plannedWeek: string | null }
export interface PlannerTheme { themeId: string; title: string; status: ThemeStatus; version: number }
export interface WeekSlot { weekStart: string; locked: boolean; planned: PlannerDraft | null; themes: PlannerTheme[] }
export interface WeekBoard { grade: ThemeGrade; weekStart: string; weeks: WeekSlot[]; candidates: PlannerDraft[] }
export interface PlanChange { grade: ThemeGrade; draftId: string; expectedWeek: string | null; targetWeek: string | null; expectedTargetDraftId: string | null }

export const themePlannerApi = {
  get: async (grade: ThemeGrade, weekStart: string, signal?: AbortSignal) => {
    const board=await apiFetch<WeekBoard>('/admin/weekly-themes/planner?' + new URLSearchParams({ grade, weekStart }), { signal })
    if (!Array.isArray(board?.weeks) || !Array.isArray(board.candidates)) throw new Error('주간 편성 목록을 확인하지 못했습니다.')
    return board
  },
  apply: (plan: PlanChange) => apiFetch<{draftId: string; plannedWeek: string | null}>('/admin/weekly-themes/planner', json(plan, 'PUT')),
  awaiting: (page:number,signal?:AbortSignal) => apiFetch<Page<AdminWeeklyTheme>>('/admin/weekly-themes?status=REVIEW_REQUIRED&page='+page+'&size=20',{signal}),
  publish: (theme: PlannerTheme,expectedPlannedDraftId:string|null) => apiFetch<AdminWeeklyTheme>('/admin/weekly-themes/' + encodeURIComponent(theme.themeId) + '/publish',
    json({ expectedVersion: theme.version,expectedPlannedDraftId })),
}
