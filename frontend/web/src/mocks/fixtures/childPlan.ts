import { mockAccountChildren, mockIdentity } from './accounts.ts'
import { fixtureStore, persistFixtureState } from './student.ts'
import type { Child } from '../../domain/classroom.ts'

// DEV+MSW bootstrap에서만 연결하는 테스트 설정입니다. 구독/결제 API가 아닙니다.
// 신규 가입 기본값(FREE)은 변경하지 않고, 현재 가상 보호자 소속 자녀만 설정합니다.
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
  const children: Child[] = owned.map((c) => (c.id === childId ? { ...c, plan } : c))
  mockAccountChildren.set(mockIdentity.email, structuredClone(children))
  fixtureStore.replaceChildren(children)
  persistFixtureState()
  return true
}
