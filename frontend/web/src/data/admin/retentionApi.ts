import { apiFetch } from '../apiClient.ts'
import { json } from '../parent/api.ts'
import type { Page } from '../../domain/parent.ts'
import type {
  AdminLookItem,
  AdminWeeklyTheme,
  LookItemInput,
  LookItemStatus,
  WeeklyThemeInput,
} from '../../domain/admin/retention.ts'

const p = (id: string) => encodeURIComponent(id)
const query = (values: Record<string, string | undefined>) =>
  new URLSearchParams(Object.entries(values).filter((e): e is [string, string] => !!e[1]))

/** 관리자 주간 테마·꾸미기 아이템 (API 명세 2.8 구현 예정, CONTENT 권한). 변경은 서버가 감사 이력에 남긴다. */
export const adminRetentionApi = {
  themes: (filters: { gradeBand?: string; weekStart?: string; status?: string }, signal?: AbortSignal) =>
    apiFetch<Page<AdminWeeklyTheme>>(`/admin/weekly-themes?${query(filters)}`, { signal }),
  theme: (id: string, signal?: AbortSignal) => apiFetch<AdminWeeklyTheme>(`/admin/weekly-themes/${p(id)}`, { signal }),
  createTheme: (data: WeeklyThemeInput) => apiFetch<AdminWeeklyTheme>('/admin/weekly-themes', json(data)),
  saveTheme: (id: string, data: WeeklyThemeInput) =>
    apiFetch<AdminWeeklyTheme>(`/admin/weekly-themes/${p(id)}`, json(data, 'PUT')),
  themeAction: (id: string, action: 'review-request' | 'publish' | 'unpublish') =>
    apiFetch<AdminWeeklyTheme>(`/admin/weekly-themes/${p(id)}/${action}`, json({})),
  items: (signal?: AbortSignal) => apiFetch<Page<AdminLookItem>>('/admin/look-items', { signal }),
  createItem: (data: LookItemInput) => apiFetch<AdminLookItem>('/admin/look-items', json(data)),
  updateItem: (id: string, data: Partial<Pick<AdminLookItem, 'name' | 'pricePoints' | 'assetKey'>> & { status?: LookItemStatus }) =>
    apiFetch<AdminLookItem>(`/admin/look-items/${p(id)}`, json(data, 'PATCH')),
}
