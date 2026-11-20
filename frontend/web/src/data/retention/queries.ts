import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { retentionApi } from './api.ts'
import type { DecorSpot, DecorSurface, FrameSlot, LookItem, Points, Reaction, StoryKind } from '../../domain/retention.ts'

// ---------- 내 방 추억의 벽·추억 앨범 (2.12, P27) ----------
export const useFrameSlots = (childId: string | undefined) =>
  useQuery({ queryKey: ['frame-slots', childId], queryFn: ({ signal }) => retentionApi.frameSlots(signal), enabled: !!childId, retry: false })
/** 방 소품 놓은 칸(#705, core #723 계약안) */
export const useDecorSpots = (childId: string | undefined) =>
  useQuery({ queryKey: ['decor-spots', childId], queryFn: ({ signal }) => retentionApi.decorSpots(signal), enabled: !!childId, retry: false })
export function useSaveDecorSpots(childId: string | undefined) {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: (spots: { surface: DecorSurface; col: number; row: number; itemKey: string; color?: string | null }[]) => retentionApi.saveDecorSpots(spots),
    onSuccess: (saved) => cache.setQueryData<DecorSpot[]>(['decor-spots', childId], saved),
  })
}
/** 저장이 끝나면 서버가 돌려준 목록으로 바꾸고, 앨범의 전시 여부도 다시 받는다 */
export function useSaveFrameSlots(childId: string | undefined) {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: (slots: { slotNo: number; themeId: string; weekStart: string }[]) => retentionApi.saveFrameSlots(slots),
    onSuccess: (saved) => {
      cache.setQueryData<FrameSlot[]>(['frame-slots', childId], saved)
      void cache.invalidateQueries({ queryKey: ['album', childId] })
    },
  })
}
export const useAlbum = (childId: string | undefined, page = 0, size = 12) =>
  useQuery({ queryKey: ['album', childId, page, size], queryFn: ({ signal }) => retentionApi.album(signal, page, size), enabled: !!childId, retry: false })
export const useEpisode = (childId: string | undefined, themeId: string, weekStart: string) =>
  useQuery({
    queryKey: ['album', childId, 'episode', themeId, weekStart],
    queryFn: ({ signal }) => retentionApi.episode(themeId, weekStart, signal),
    enabled: !!childId && !!themeId && !!weekStart,
    retry: false,
  })
export function useMarkFramesSeen(childId: string | undefined) {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: (frames: { themeId: string; weekStart: string }[]) =>
      Promise.all(frames.map((f) => retentionApi.markFrameSeen(f.themeId, f.weekStart))),
    onSettled: () => cache.invalidateQueries({ queryKey: ['album', childId] }),
  })
}

/** 참여 기능 조회는 학습 화면을 막지 않는다: 실패해도 재시도 없이 오류만 보인다. */
const quiet = { retry: false } as const

export const useMyPoints = (childId: string | undefined, page = 0) =>
  useQuery({ queryKey: ['points', childId, page], queryFn: ({ signal }) => retentionApi.myPoints(signal, page), enabled: !!childId, ...quiet })
export const useChildPoints = (childId: string | undefined, page = 0) =>
  useQuery({
    queryKey: ['parent', 'points', childId, page],
    queryFn: ({ signal }) => retentionApi.childPoints(childId!, signal, page),
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
    onSuccess: (result) => {
      // 차감액을 추측하지 않고 서버가 확정한 잔액·해금만 반영한다.
      cache.setQueriesData<Points>({ queryKey: ['points', childId] }, before => before ? { ...before, balance: result.balance } : before)
      cache.setQueryData<LookItem[]>(['look-items', childId], before => before?.map(item =>
        item.itemKey === result.itemKey ? { ...item, unlocked: true } : item))
    },
    onSettled: () => Promise.all([
      cache.invalidateQueries({ queryKey: ['look-items', childId] }),
      cache.invalidateQueries({ queryKey: ['points', childId] }),
      cache.invalidateQueries({ queryKey: ['parent', 'points', childId] }),
    ]),
  })
}

/**
 * 방 소품 사기(#704). 멱등 키는 부르는 쪽(lookShop)이 사기마다 새로 만든다. 성공하면 서버가 확정한
 * 보유 개수·잔액을 바로 반영하고(보유 1개 이상 = `unlocked` true), 끝나면 목록·잔액을 다시 받는다.
 */
export function usePurchaseDecor(childId: string | undefined) {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: ({ itemKey, key }: { itemKey: string; key: string }) => retentionApi.purchaseDecor(itemKey, key),
    onSuccess: (result) => {
      cache.setQueriesData<Points>({ queryKey: ['points', childId] }, before => before ? { ...before, balance: result.balance } : before)
      cache.setQueryData<LookItem[]>(['look-items', childId], before => before?.map(item =>
        item.itemKey === result.itemKey ? { ...item, ownedCount: result.ownedCount, unlocked: true } : item))
    },
    onSettled: () => Promise.all([
      cache.invalidateQueries({ queryKey: ['look-items', childId] }),
      cache.invalidateQueries({ queryKey: ['points', childId] }),
      cache.invalidateQueries({ queryKey: ['parent', 'points', childId] }),
    ]),
  })
}

export const useWeeklyTheme = (childId: string | undefined) =>
  useQuery({
    queryKey: ['weekly-theme', childId],
    queryFn: ({ signal }) => retentionApi.weeklyTheme(signal),
    enabled: !!childId,
    ...quiet,
  })

/** 주간 테마를 지금 다시 받는다(캐시도 갱신). 문제를 마무리한 직후 엔딩이 됐는지 볼 때 쓴다(#440). */
export function useFetchWeeklyTheme(childId: string | undefined) {
  const cache = useQueryClient()
  return () => cache.fetchQuery({
    queryKey: ['weekly-theme', childId],
    queryFn: ({ signal }) => retentionApi.weeklyTheme(signal),
    staleTime: 0,
  })
}

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

/** 이야기 열람 기록. 실패해도 화면은 닫히고(다시 띄우지 않음) 다음 조회의 `introSeen`·`outroSeen`을 따른다. */
export function useRecordStoryView(childId: string | undefined) {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: (kind: StoryKind) => retentionApi.recordStoryView(kind),
    onSettled: () => void cache.invalidateQueries({ queryKey: ['weekly-theme', childId] }),
  })
}

/** 큰 질문 정답 고르기. 엔딩이 되면 종료 이야기·정답과 잠겼던 커뮤니티가 열리므로 함께 다시 받는다. */
export function useAnswerPick(childId: string | undefined) {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: (pick: string) => retentionApi.pickAnswer(pick),
    onSettled: () => Promise.all([
      cache.invalidateQueries({ queryKey: ['weekly-theme', childId] }),
      cache.invalidateQueries({ queryKey: ['community', 'mission', childId] }),
    ]),
  })
}

/** 보호자가 다른 창·기기에서 동의하면 학생이 창으로 돌아올 때 바로 반영되도록 포커스마다 다시 읽는다(#433). */
export const useCommunitySettings = (childId: string | undefined) =>
  useQuery({
    queryKey: ['community-settings', childId],
    queryFn: ({ signal }) => retentionApi.communitySettings(signal),
    enabled: !!childId,
    staleTime: 0,
    refetchOnWindowFocus: 'always',
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
/** 친구 방(#709). 들어갈 때마다 다시 받는다(친구가 그사이 방을 바꿨을 수 있음, 서버 no-store) */
export const useFriendRoom = (childId: string | undefined, postId: string | null) =>
  useQuery({
    queryKey: ['community', 'room', childId, postId],
    queryFn: ({ signal }) => retentionApi.friendRoom(postId!, signal),
    enabled: !!childId && !!postId,
    gcTime: 0,
    ...quiet,
  })
export const useMyPosts = (childId: string | undefined) =>
  useQuery({ queryKey: ['community', 'mine', childId], queryFn: ({ signal }) => retentionApi.myPosts(signal), enabled: !!childId, ...quiet })
export const useChildPosts = (childId: string | undefined, enabled = true) =>
  useQuery({
    queryKey: ['parent', 'community', childId],
    queryFn: ({ signal }) => retentionApi.childPosts(childId!, signal),
    enabled: !!childId && enabled,
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
