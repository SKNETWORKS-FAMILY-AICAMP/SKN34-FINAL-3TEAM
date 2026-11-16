import { useMutation } from '@tanstack/react-query'
import { memoryApi } from './api.ts'

/**
 * 검색·설명은 하루 횟수(검색 20·설명 10)를 쓰므로 자동 조회·재시도 없이 누를 때만 부른다(mutation).
 * 설명은 검색과 따로 두어 설명이 실패해도 검색 결과가 남는다(#567 지침, FN-RET-13).
 */
export const useMemorySearch = (childId: string | undefined) =>
  useMutation({ mutationKey: ['memory-search', childId], mutationFn: (query: string) => memoryApi.search(query), retry: false })

export const useMemoryExplanation = (childId: string | undefined) =>
  useMutation({
    mutationKey: ['memory-explanation', childId],
    mutationFn: ({ query, attemptIds }: { query: string; attemptIds: string[] }) => memoryApi.explain(query, attemptIds),
    retry: false,
  })
