import { ApiError } from '../../data/apiClient.ts'
const storageKey = 'sagomungchi:mock-parent-sharing:v1'
function read(): [string, boolean][] {
  try { const raw: unknown = typeof localStorage === 'undefined' ? [] : JSON.parse(localStorage.getItem(storageKey) ?? '[]')
    return Array.isArray(raw) ? raw.filter((entry): entry is [string, boolean] => Array.isArray(entry) && typeof entry[0] === 'string' && typeof entry[1] === 'boolean') : []
  } catch { return [] }
}
export const mockSharing = new Map<string, boolean>(read())
export const isShared = (id: string) => mockSharing.get(id) === true
export function saveSharing(id: string, enabled: boolean) {
  mockSharing.set(id, enabled)
  if (typeof localStorage !== 'undefined') localStorage.setItem(storageKey, JSON.stringify([...mockSharing]))
}
export function requireShared(id: string) {
  if (!isShared(id)) throw new ApiError({ status: 403, code: 'STUDENT_RECORDS_PRIVATE', title: '학생이 답변 원문을 비공개로 설정했습니다. 학습 수치는 계속 볼 수 있습니다.', retryable: false })
}
export function privateReport<T extends { narrative?: unknown; eveningQuestion?: unknown; quotes?: unknown; changes?: unknown[]; reflections?: unknown[]; thinkingTypes?: unknown[] }>(report: T) {
  return { ...report, parentSharingEnabled: false, narrative: null, eveningQuestion: null, quotes: [],
    changes: report.changes?.map(item => { const v = item as Record<string, unknown>; return { itemId: v.itemId, attemptId: v.attemptId, counts: v.counts, first: { text: null }, revised: { text: null }, followup: null } }),
    reflections: report.reflections?.map(item => { const v = item as Record<string, unknown>; return { itemId: v.itemId, attemptId: v.attemptId, written: v.written, difficulty: v.difficulty, text: null } }),
    thinkingTypes: report.thinkingTypes?.map(item => { const v = item as Record<string, unknown>; return { itemId: v.itemId, type: v.type, state: v.state, missions: v.missions } }),
  }
}
