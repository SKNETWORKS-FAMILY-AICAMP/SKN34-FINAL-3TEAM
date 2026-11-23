import { apiFetch } from '../apiClient.ts'
import { json } from '../parent/api.ts'
import { readMemoryBook, readMemoryBookDownload, readMemoryBookPage, readMemoryBookRoundPage } from '../../domain/memoryBook.ts'
import type { MemoryBook, MemoryBookDownload, MemoryBookPage, MemoryBookRound, MemoryBookRoundPage } from '../../domain/memoryBook.ts'

const e = encodeURIComponent

/**
 * 추억 그림책 (docs/proposals/memory-book.md 7.1, 미도입 시험 구현). 학부모만, 연결된 자녀 기준.
 * 서버가 no-store라 캐시하지 않는다.
 */
export const memoryBookApi = {
  /** 발급 화면: 자녀의 보유 액자 회차와 회차마다 가장 최근 그림책 */
  rounds: async (childId: string, signal?: AbortSignal): Promise<MemoryBookRoundPage> =>
    readMemoryBookRoundPage(await apiFetch<unknown>(`/children/${e(childId)}/memory-books/rounds?page=0&size=50`, { signal, cache: 'no-store' })),
  create: async (childId: string, round: MemoryBookRound): Promise<MemoryBook> =>
    readMemoryBook(await apiFetch<unknown>(`/children/${e(childId)}/memory-books`, { ...json({ rounds: [round] }), cache: 'no-store' })),
  books: async (childId: string, signal?: AbortSignal): Promise<MemoryBookPage> =>
    readMemoryBookPage(await apiFetch<unknown>(`/children/${e(childId)}/memory-books?page=0&size=50`, { signal, cache: 'no-store' })),
  download: async (childId: string, bookId: string): Promise<MemoryBookDownload> =>
    readMemoryBookDownload(await apiFetch<unknown>(`/children/${e(childId)}/memory-books/${e(bookId)}/download`, { cache: 'no-store' })),
}

/** 받은 주소로 이동(파일은 서버가 attachment로 내려 준다) */
export function openDownload(download: MemoryBookDownload) {
  window.location.assign(new URL(download.url, location.href).href)
}
