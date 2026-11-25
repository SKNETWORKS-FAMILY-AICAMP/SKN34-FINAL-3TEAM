// 개발 목업 전용: 첫 사용 안내 완료 기록(core #1035). 학부모는 이메일, 학생은 학생 id 기준.
// 기본은 미완료(기록 없음). 새로고침해도 유지되도록 sessionStorage에 가상 값만 둔다.
const onboardingKey = 'sagomungchi:msw-onboarding:v1'
/** 완료 상태 fixture 시각 */
export const ONBOARDING_DONE_AT = '2026-11-24T09:00:00+09:00'
export const parentOnboardingKey = (email: string) => `parent:${email}`
export const studentOnboardingKey = (studentId: string) => `student:${studentId}`

const completed = new Map<string, string>()
if (typeof sessionStorage !== 'undefined') {
  try {
    const raw = sessionStorage.getItem(onboardingKey)
    if (raw) for (const [id, at] of Object.entries(JSON.parse(raw) as Record<string, string>)) completed.set(id, at)
  } catch {
    /* 손상된 개발 상태는 버린다 */
  }
}
function persist() {
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.setItem(onboardingKey, JSON.stringify(Object.fromEntries(completed)))
  } catch {
    /* 저장소를 못 쓰면 메모리 값만 유지 */
  }
}

export const mockOnboarding = (key: string) => ({ completedAt: completed.get(key) ?? null })
/** core와 같이 이미 있으면 처음 시각을 유지한다. */
export function completeMockOnboarding(key: string) {
  if (!completed.has(key)) {
    completed.set(key, new Date().toISOString())
    persist()
  }
  return mockOnboarding(key)
}
/** 시험·시연용: 완료(시각)·미완료(null) 상태로 바꾼다. */
export function setMockOnboarding(key: string, completedAt: string | null) {
  if (completedAt) completed.set(key, completedAt)
  else completed.delete(key)
  persist()
}
