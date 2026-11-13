import { apiFetch } from '../apiClient.ts'
import { json } from '../parent/api.ts'
import { readMemoryExplanation, readMemorySearch } from '../../domain/memory.ts'
import type { MemoryExplanation, MemorySearch } from '../../domain/memory.ts'

/**
 * 추억 검색·설명 (API 명세 2.12, P27, #567). 학생 본인만.
 * 둘 다 하루 횟수를 쓰므로 응답을 캐시하지 않고(서버도 no-store) 누를 때만 부른다.
 */
export const memoryApi = {
  search: async (query: string): Promise<MemorySearch> =>
    readMemorySearch(await apiFetch<unknown>('/students/me/memories/search', { ...json({ query }), cache: 'no-store' })),
  /** attemptIds는 검색 결과 카드의 시도 1~3개(`explanationAttempts`) */
  explain: async (query: string, attemptIds: string[]): Promise<MemoryExplanation> =>
    readMemoryExplanation(
      await apiFetch<unknown>('/students/me/memories/explanations', { ...json({ query, attemptIds }), cache: 'no-store' }),
      attemptIds,
    ),
}
