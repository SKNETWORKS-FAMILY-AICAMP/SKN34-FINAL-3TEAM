import { apiFetch, ApiError } from '../apiClient.ts'
export interface SharingPreference { studentId: string; parentSharingEnabled: boolean }
function validate(value: SharingPreference, studentId: string) {
  if (value?.studentId !== studentId || typeof value.parentSharingEnabled !== 'boolean')
    throw new ApiError({ status: 502, code: 'CONTRACT_NOT_READY', title: '공개 설정을 확인하지 못했습니다.' })
  return value
}
export const sharingApi = {
  async get(studentId: string, role: 'STUDENT' | 'PARENT', signal?: AbortSignal) {
    return validate(await apiFetch<SharingPreference>(role === 'STUDENT' ? '/students/me/sharing-preferences'
      : `/children/${encodeURIComponent(studentId)}/sharing-preferences`, { signal, cache: 'no-store' }), studentId)
  },
  async save(studentId: string, parentSharingEnabled: boolean) {
    return validate(await apiFetch<SharingPreference>('/students/me/sharing-preferences', {
      method: 'PUT', body: JSON.stringify({ parentSharingEnabled }), cache: 'no-store',
    }), studentId)
  },
}
