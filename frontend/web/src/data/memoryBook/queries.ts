import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { memoryBookApi } from './api.ts'
import type { MemoryBookRound } from '../../domain/memoryBook.ts'
import { MEMORY_BOOK_POLL_MS, memoryBookPolling } from '../../domain/memoryBook.ts'

/** 학생 본인 그림책 목록. 만드는 중(QUEUED)이 있으면 몇 초마다 다시 본다 */
export const useMyMemoryBooks = (childId: string | undefined) =>
  useQuery({
    queryKey: ['memory-books', 'me', childId],
    queryFn: ({ signal }) => memoryBookApi.mine(signal),
    enabled: !!childId,
    retry: false,
    refetchInterval: (query) => (memoryBookPolling(query.state.data?.items) ? MEMORY_BOOK_POLL_MS : false),
  })

/** 만들기: 유료·한도·공개 확인은 서버. 실패를 다시 시도하지 않는다(하루 한도를 쓰므로) */
export function useCreateMemoryBook(childId: string | undefined) {
  const cache = useQueryClient()
  return useMutation({
    mutationKey: ['memory-book-create', childId],
    mutationFn: (round: MemoryBookRound) => memoryBookApi.create(round),
    retry: false,
    onSuccess: () => void cache.invalidateQueries({ queryKey: ['memory-books', 'me', childId] }),
  })
}

export const useMemoryBookDownload = () =>
  useMutation({ mutationKey: ['memory-book-download'], mutationFn: (bookId: string) => memoryBookApi.mineDownload(bookId), retry: false })

/** 학부모: 연결된 자녀의 그림책 목록 */
export const useChildMemoryBooks = (childId: string) =>
  useQuery({
    queryKey: ['memory-books', 'child', childId],
    queryFn: ({ signal }) => memoryBookApi.child(childId, signal),
    retry: false,
    refetchInterval: (query) => (memoryBookPolling(query.state.data?.items) ? MEMORY_BOOK_POLL_MS : false),
  })

export const useChildMemoryBookDownload = (childId: string) =>
  useMutation({ mutationKey: ['memory-book-download', childId], mutationFn: (bookId: string) => memoryBookApi.childDownload(childId, bookId), retry: false })
