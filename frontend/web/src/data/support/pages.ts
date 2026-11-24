import { apiFetch } from '../apiClient.ts'
import type { Page } from '../../domain/parent.ts'

/** 공지 검색과 본인 접수 이력은 서버의 전체 공개 범위를 대상으로 한다. */
export async function readServicePages<T>(path: string, signal?: AbortSignal) {
  const first = await apiFetch<Page<T>>(path, { signal })
  const items = [...first.items]
  for (let page = 1; first.size > 0 && page * first.size < first.totalElements; page++) {
    const next = await apiFetch<Page<T>>(`${path}?page=${page}&size=${first.size}`, { signal })
    items.push(...next.items)
  }
  return { items }
}
