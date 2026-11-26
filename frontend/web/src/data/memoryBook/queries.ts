import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { memoryBookApi } from './api.ts'
import type { MemoryBookRound } from '../../domain/memoryBook.ts'
import { MEMORY_BOOK_POLL_MS, memoryBookPolling } from '../../domain/memoryBook.ts'

/** 발급 화면 회차 목록. 만드는 중(QUEUED) 그림책이 있으면 몇 초마다 다시 본다 */
export const useMemoryBookRounds = (childId: string, page = 0) =>
  useQuery({
    queryKey: ['memory-books', 'rounds', childId, page],
    queryFn: ({ signal }) => memoryBookApi.rounds(childId, signal, page),
    retry: false,
    refetchInterval: (query) => (memoryBookPolling(query.state.data?.items) ? MEMORY_BOOK_POLL_MS : false),
  })

/** 발급: 유료·한도·공개 확인은 서버. 실패를 다시 시도하지 않는다(하루 한도를 쓰므로) */
export function useCreateMemoryBook(childId: string) {
  const cache = useQueryClient()
  return useMutation({
    mutationKey: ['memory-book-create', childId],
    mutationFn: (round: MemoryBookRound) => memoryBookApi.create(childId, round),
    retry: false,
    onSuccess: () => void cache.invalidateQueries({ queryKey: ['memory-books', 'rounds', childId] }),
  })
}

/**
 * 같이 읽었어요: 성공하면 책장 회차 목록을 다시 받아 표지에 날짜를 보인다.
 * 다시 받을 때까지 기다려(Promise를 돌려줌) 그동안 isPending이 유지되므로 단추가 다시 눌리는 틈이 없다
 */
export function useReadTogether(childId: string) {
  const cache = useQueryClient()
  return useMutation({
    mutationKey: ['memory-book-read-together', childId],
    mutationFn: (bookId: string) => memoryBookApi.readTogether(childId, bookId),
    retry: false,
    onSuccess: () => cache.invalidateQueries({ queryKey: ['memory-books', 'rounds', childId] }),
  })
}

export const useMemoryBookDownload = (childId: string) =>
  useMutation({ mutationKey: ['memory-book-download', childId], mutationFn: (bookId: string) => memoryBookApi.download(childId, bookId), retry: false })
