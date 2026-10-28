import { apiFetch } from '../apiClient.ts'
import { json } from '../parent/api.ts'
import { readLook } from '../../domain/studentLook.ts'
import type { CompanionId, StudentLook, ThemeId } from '../../domain/studentLook.ts'

/** 학생 꾸미기 설정 (API 명세 3.12, 목업 계약 초안). */
export const studentLookApi = {
  get: async (signal?: AbortSignal): Promise<StudentLook> =>
    readLook(await apiFetch<unknown>('/students/me/preferences', { signal })),
  save: async (look: { theme: ThemeId; companion: CompanionId }): Promise<StudentLook> =>
    readLook(await apiFetch<unknown>('/students/me/preferences', json(look, 'PUT'))),
}
