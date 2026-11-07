import { apiFetch } from '../apiClient.ts'
import { json } from '../parent/api.ts'
import { readLook } from '../../domain/studentLook.ts'
import type { StudentLook } from '../../domain/studentLook.ts'

export type LookChoice = Pick<StudentLook, 'theme' | 'companion'> & Partial<Pick<StudentLook, 'equipped'>>

/** 학생 꾸미기 설정 (API 명세 3.12, core #234). `equipped`는 P22 확장이라 고른 때만 보낸다. */
export const studentLookApi = {
  get: async (signal?: AbortSignal): Promise<StudentLook> =>
    readLook(await apiFetch<unknown>('/students/me/preferences', { signal })),
  save: async (look: LookChoice): Promise<StudentLook> =>
    readLook(await apiFetch<unknown>('/students/me/preferences', json(look, 'PUT'))),
}
