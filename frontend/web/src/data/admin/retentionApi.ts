import { apiFetch } from '../apiClient.ts'
import { json } from '../parent/api.ts'
import type { Page } from '../../domain/parent.ts'
import { themeDraftOf } from '../../domain/admin/themeDrafts.ts'
import type { ThemeDraftRequest } from '../../domain/admin/themeDrafts.ts'
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

/** 관리자 주간 테마·초안·꾸미기 아이템 (API 명세 2.8, CONTENT 권한). 변경은 서버가 감사 이력에 남긴다. */
export const adminRetentionApi = {
  themeDrafts: async (filters: Record<string, string>, signal?: AbortSignal) => {
    const raw = await apiFetch<{ items: unknown[]; totalElements?: unknown }>(`/admin/theme-drafts?${query(filters)}`, { signal })
    if (!Array.isArray(raw?.items)) throw new Error('테마 초안 목록 응답을 확인하지 못했습니다.')
    // learning ThemeDraftPage {items, page, size, totalElements}. 합계가 없으면 받은 개수로 다음 쪽 여부를 판단
    return { items: raw.items.map(themeDraftOf), totalElements: Number.isInteger(raw.totalElements) ? Number(raw.totalElements) : null }
  },
  themeDraft: async (id: string, signal?: AbortSignal) => themeDraftOf(await apiFetch(`/admin/theme-drafts/${p(id)}`, { signal })),
  requestThemeDraft: async (body: ThemeDraftRequest) => themeDraftOf(await apiFetch('/admin/theme-drafts', json(body))),
  themeDraftAction: async (id: string, action: 'discard' | 'regenerate') => themeDraftOf(await apiFetch(`/admin/theme-drafts/${p(id)}/${action}`, json({}))),
  adoptThemeDraft: async (id: string) => {
    const result = await apiFetch<{ themeId?: unknown }>(`/admin/theme-drafts/${p(id)}/adopt`, json({}))
    if (typeof result?.themeId !== 'string' || !result.themeId) throw new Error('채택한 테마를 확인하지 못했습니다. 목록에서 결과를 먼저 확인해 주세요.')
    return { themeId: result.themeId }
  },
  themes: (filters: { grade?: string; weekStart?: string; status?: string }, signal?: AbortSignal) =>
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
