import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { retentionApi } from './api.ts'
import type { Reaction } from '../../domain/retention.ts'

/** 참여 기능 조회는 학습 화면을 막지 않는다: 실패해도 재시도 없이 오류만 보인다. */
const quiet = { retry: false } as const

export const useMyPoints = (childId: string | undefined) =>
  useQuery({ queryKey: ['points', childId], queryFn: ({ signal }) => retentionApi.myPoints(signal), enabled: !!childId, ...quiet })
export const useChildPoints = (childId: string | undefined) =>
  useQuery({
    queryKey: ['parent', 'points', childId],
    queryFn: ({ signal }) => retentionApi.childPoints(childId!, signal),
    enabled: !!childId,
    ...quiet,
  })
export const useLookItems = (childId: string | undefined) =>
  useQuery({ queryKey: ['look-items', childId], queryFn: ({ signal }) => retentionApi.lookItems(signal), enabled: !!childId, ...quiet })

/** 해금: 버튼 한 번에 키 하나. 끝나면 목록·잔액을 다시 받는다(차감은 서버만 계산). */
export function useUnlock(childId: string | undefined) {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: ({ itemKey, key }: { itemKey: string; key: string }) => retentionApi.unlock(itemKey, key),
    onSettled: () => {
      void cache.invalidateQueries({ queryKey: ['look-items', childId] })
      void cache.invalidateQueries({ queryKey: ['points', childId] })
    },
  })
}

export const useWeeklyTheme = (childId: string | undefined) =>
  useQuery({
    queryKey: ['weekly-theme', childId],
    queryFn: ({ signal }) => retentionApi.weeklyTheme(signal),
    enabled: !!childId,
    ...quiet,
  })

export function useRecordReviewView(childId: string | undefined) {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: () => retentionApi.recordReviewView(),
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ['weekly-theme', childId] })
      void cache.invalidateQueries({ queryKey: ['points', childId] })
    },
  })
}

export const useCommunitySettings = (childId: string | undefined) =>
  useQuery({
    queryKey: ['community-settings', childId],
    queryFn: ({ signal }) => retentionApi.communitySettings(signal),
    enabled: !!childId,
    ...quiet,
  })

export function useSaveCommunitySettings(childId: string | undefined) {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: (enabled: boolean) => retentionApi.saveCommunitySettings(enabled),
    onSuccess: (saved) => {
      cache.setQueryData(['community-settings', childId], saved)
      void cache.invalidateQueries({ queryKey: ['community', 'mine', childId] })
    },
  })
}

export const useMissionPosts = (childId: string | undefined, missionId: string | null, seed: string) =>
  useQuery({
    queryKey: ['community', 'mission', childId, missionId, seed],
    queryFn: ({ signal }) => retentionApi.missionPosts(missionId!, seed, signal),
    enabled: !!childId && !!missionId,
    ...quiet,
  })
export const useMyPosts = (childId: string | undefined) =>
  useQuery({ queryKey: ['community', 'mine', childId], queryFn: ({ signal }) => retentionApi.myPosts(signal), enabled: !!childId, ...quiet })
export const useChildPosts = (childId: string | undefined) =>
  useQuery({
    queryKey: ['parent', 'community', childId],
    queryFn: ({ signal }) => retentionApi.childPosts(childId!, signal),
    enabled: !!childId,
    ...quiet,
  })

export function useReact(childId: string | undefined) {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: ({ postId, reaction, on }: { postId: string; reaction: Reaction; on: boolean }) =>
      retentionApi.react(postId, reaction, on),
    onSettled: () => {
      void cache.invalidateQueries({ queryKey: ['community', 'mission', childId] })
      void cache.invalidateQueries({ queryKey: ['points', childId] })
    },
  })
}

export function useReportPost(childId: string | undefined) {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: ({ postId, comment, key }: { postId: string; comment: string; key: string }) =>
      retentionApi.reportPost(postId, comment, key),
    onSuccess: () => void cache.invalidateQueries({ queryKey: ['community', 'mission', childId] }),
  })
}
