import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { onboardingApi } from './api.ts'
import type { OnboardingRole, OnboardingState } from './api.ts'

const key = (role: OnboardingRole, childId: string | undefined) => ['onboarding', role, childId] as const

/** 완료 기록 조회. 학생은 자녀별 기록이라 childId가 있을 때만 받는다. */
export function useOnboarding(role: OnboardingRole, childId?: string) {
  return useQuery({
    queryKey: key(role, childId),
    queryFn: ({ signal }) => onboardingApi.get(role, signal),
    enabled: role === 'PARENT' || !!childId,
    retry: false,
    staleTime: Infinity,
  })
}

/** 받기 전·실패 시에는 안내를 띄우지 않는다(화면은 그대로 동작). 미완료로 확인된 때만 true. */
export const needsOnboarding = (query: { isSuccess: boolean; data?: OnboardingState }) =>
  query.isSuccess && query.data?.completedAt === null

/** 완료 기록. 성공한 경우에만 캐시를 갱신하고, 실패 시 호출 화면에서 재시도를 안내한다. */
export function useCompleteOnboarding(role: OnboardingRole, childId?: string) {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: () => onboardingApi.complete(role),
    onSuccess: (saved) => cache.setQueryData(key(role, childId), saved),
  })
}
