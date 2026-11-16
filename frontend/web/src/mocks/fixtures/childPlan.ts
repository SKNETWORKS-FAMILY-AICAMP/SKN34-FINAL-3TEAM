import { mockAccountChildren, mockIdentity } from './accounts.ts'
import { fixtureStore } from './student.ts'
import { setMockSubscription } from './payments.ts'

// DEV+MSW bootstrap에서만 연결하는 테스트 설정입니다. 구독/결제 API가 아닙니다.
// 자녀 정보에는 이용권을 넣지 않고 결제 목업의 구독만 바꿉니다(이용권의 한 출처, fixtures/payments.ts).
// 신규 가입 기본값(구독 없음 = 무료)은 변경하지 않고, 현재 가상 보호자 소속 자녀만 설정합니다.
export function setMockChildPlan(value: unknown): boolean {
  if (!value || typeof value !== 'object') return false
  const { childId, plan } = value as { childId?: unknown; plan?: unknown }
  if (typeof childId !== 'string' || (plan !== 'FREE' && plan !== 'PREMIUM')) return false
  const snapshot = fixtureStore.snapshot(),
    owned = mockAccountChildren.get(mockIdentity.email)
  if (
    snapshot.session?.role !== 'PARENT' ||
    !mockIdentity.email.endsWith('@example.test') ||
    !owned?.some((c) => c.id === childId) ||
    !snapshot.children?.some((c) => c.id === childId)
  )
    return false
  setMockSubscription(childId, plan)
  return true
}
