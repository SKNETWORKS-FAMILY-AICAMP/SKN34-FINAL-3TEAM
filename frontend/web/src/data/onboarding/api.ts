import { apiFetch } from '../apiClient.ts'

export type OnboardingRole = 'PARENT' | 'STUDENT'
export type OnboardingState = { completedAt: string | null }

const path = (role: OnboardingRole) => (role === 'PARENT' ? '/me/onboarding' : '/students/me/onboarding')

/** 알 수 없는 값은 미완료(null)로 읽는다. */
export const readOnboarding = (raw: unknown): OnboardingState => {
  const value = (raw as { completedAt?: unknown } | null)?.completedAt
  return { completedAt: typeof value === 'string' ? value : null }
}

/** 첫 사용 안내 완료 기록 (API 명세 `/me/onboarding`·`/students/me/onboarding`, core #1035). PUT은 본문 없이 멱등. */
export const onboardingApi = {
  get: async (role: OnboardingRole, signal?: AbortSignal): Promise<OnboardingState> =>
    readOnboarding(await apiFetch<unknown>(path(role), { signal, cache: 'no-store' })),
  complete: async (role: OnboardingRole): Promise<OnboardingState> =>
    readOnboarding(await apiFetch<unknown>(path(role), { method: 'PUT', cache: 'no-store' })),
}
