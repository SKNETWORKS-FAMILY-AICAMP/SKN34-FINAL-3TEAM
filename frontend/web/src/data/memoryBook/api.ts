import { apiFetch } from '../apiClient.ts'
import { json } from '../parent/api.ts'
import { readMemoryBook, readMemoryBookDownload, readMemoryBookPage } from '../../domain/memoryBook.ts'
import type { MemoryBook, MemoryBookDownload, MemoryBookPage, MemoryBookRound } from '../../domain/memoryBook.ts'

const e = encodeURIComponent

/**
 * 추억 그림책 (docs/proposals/memory-book.md 7.1, 미도입 시험 구현). 서버가 no-store라 캐시하지 않는다.
 * 학생은 세션 본인, 학부모는 연결된 자녀.
 */
export const memoryBookApi = {
  create: async (round: MemoryBookRound): Promise<MemoryBook> =>
    readMemoryBook(await apiFetch<unknown>('/students/me/memory-books', { ...json({ rounds: [round] }), cache: 'no-store' })),
  mine: async (signal?: AbortSignal): Promise<MemoryBookPage> =>
    readMemoryBookPage(await apiFetch<unknown>('/students/me/memory-books?page=0&size=50', { signal, cache: 'no-store' })),
  mineDownload: async (bookId: string): Promise<MemoryBookDownload> =>
    readMemoryBookDownload(await apiFetch<unknown>(`/students/me/memory-books/${e(bookId)}/download`, { cache: 'no-store' })),
  child: async (childId: string, signal?: AbortSignal): Promise<MemoryBookPage> =>
    readMemoryBookPage(await apiFetch<unknown>(`/children/${e(childId)}/memory-books?page=0&size=50`, { signal, cache: 'no-store' })),
  childDownload: async (childId: string, bookId: string): Promise<MemoryBookDownload> =>
    readMemoryBookDownload(await apiFetch<unknown>(`/children/${e(childId)}/memory-books/${e(bookId)}/download`, { cache: 'no-store' })),
}

/** 받은 주소로 이동(파일은 서버가 attachment로 내려 준다) */
export function openDownload(download: MemoryBookDownload) {
  window.location.assign(new URL(download.url, location.href).href)
}
