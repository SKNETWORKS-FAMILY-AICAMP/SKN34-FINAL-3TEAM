import { apiFetch } from '../apiClient.ts'
import { json } from '../parent/api.ts'
import {
  readCommunityPosts,
  readCommunitySettings,
  readLookItems,
  readMyPosts,
  readPoints,
  readUnlockResult,
  readWeeklyTheme,
} from '../../domain/retention.ts'
import type {
  CommunityPost,
  CommunitySettings,
  LookItem,
  MyCommunityPost,
  Points,
  Reaction,
  WeeklyTheme,
} from '../../domain/retention.ts'

const e = encodeURIComponent
const pageQuery = (page = 0, size = 20) => `page=${page}&size=${size}`

/**
 * 포인트·꾸미기는 #389 RewardController 계약, 나머지는 API 명세 2.9~2.11.
 * 서버 응답은 domain 읽기 함수로 검사해 모르는 값이 화면을 깨지 않게 한다.
 */
export const retentionApi = {
  // 포인트·꾸미기 (2.10)
  myPoints: async (signal?: AbortSignal, page = 0): Promise<Points> =>
    readPoints(await apiFetch<unknown>(`/students/me/points?${pageQuery(page)}`, { signal, cache: 'no-store' })),
  childPoints: async (childId: string, signal?: AbortSignal, page = 0): Promise<Points> =>
    readPoints(await apiFetch<unknown>(`/children/${e(childId)}/points?${pageQuery(page)}`, { signal, cache: 'no-store' })),
  lookItems: async (signal?: AbortSignal): Promise<LookItem[]> =>
    readLookItems(await apiFetch<unknown>('/students/me/look-items', { signal, cache: 'no-store' })),
  /** 해금은 Idempotency-Key 필수. 같은 키 재전송은 한 번만 차감된다. */
  unlock: async (itemKey: string, idempotencyKey: string) =>
    readUnlockResult(await apiFetch<unknown>(`/students/me/look-items/${e(itemKey)}/unlock`, {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      cache: 'no-store',
    }), itemKey),

  // 주간 테마·되돌아보기 (2.11)
  weeklyTheme: async (signal?: AbortSignal): Promise<WeeklyTheme | null> =>
    readWeeklyTheme(await apiFetch<unknown>('/students/me/weekly-theme', { signal })),
  recordReviewView: async (): Promise<void> => {
    await apiFetch<unknown>('/students/me/weekly-theme/review-views', { method: 'POST' })
  },

  // 커뮤니티 (2.9)
  communitySettings: async (signal?: AbortSignal): Promise<CommunitySettings> =>
    readCommunitySettings(await apiFetch<unknown>('/students/me/community-settings', { signal, cache: 'no-store' })),
  saveCommunitySettings: async (enabled: boolean): Promise<CommunitySettings> =>
    readCommunitySettings(await apiFetch<unknown>('/students/me/community-settings', json({ enabled }, 'PUT'))),
  missionPosts: async (missionId: string, seed: string, signal?: AbortSignal): Promise<CommunityPost[]> =>
    readCommunityPosts(
      await apiFetch<unknown>(`/missions/${e(missionId)}/community-posts?seed=${e(seed)}&${pageQuery()}`, { signal }),
    ),
  myPosts: async (signal?: AbortSignal): Promise<MyCommunityPost[]> =>
    readMyPosts(await apiFetch<unknown>('/students/me/community-posts', { signal })),
  childPosts: async (childId: string, signal?: AbortSignal): Promise<MyCommunityPost[]> =>
    readMyPosts(await apiFetch<unknown>(`/children/${e(childId)}/community-posts`, { signal })),
  react: async (postId: string, reaction: Reaction, on: boolean): Promise<void> => {
    await apiFetch<unknown>(`/community-posts/${e(postId)}/reactions/${reaction}`, { method: on ? 'PUT' : 'DELETE' })
  },
  /** 기존 오류 신고에 대상 COMMUNITY_POST만 더한다(유형은 '부적절한 표현'). 같은 키 재전송은 한 번만 접수된다. */
  reportPost: async (postId: string, comment: string, idempotencyKey: string): Promise<void> => {
    const init = json({ targetType: 'COMMUNITY_POST', targetId: postId, category: 'INAPPROPRIATE', comment })
    await apiFetch<unknown>('/error-reports', { ...init, headers: { ...init.headers, 'Idempotency-Key': idempotencyKey } })
  },
}
