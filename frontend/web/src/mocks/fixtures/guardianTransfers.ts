import { ApiError } from '../../data/apiClient.ts'
import type { GuardianTransfer } from '../../data/guardianTransfers.ts'
import type { Child } from '../../domain/classroom.ts'
import { mockAccounts, mockAccountChildren, mockIdentity } from './accounts.ts'
import { fixtureStore } from './student.ts'

// 개발 목업의 상태만 보관한다. 서버 플래그·DB·실계정에는 영향을 주지 않는다.
export const mockGuardianTransferConfig = { enabled: import.meta.env?.VITE_GUARDIAN_TRANSFER_ENABLED === 'true' }
export type MockTransfer = Omit<GuardianTransfer, 'direction'> & { sender: string; recipient: string }
export const mockTransfers = new Map<string, MockTransfer>()
export const transferUnavailableChildren = new Set<string>()
const accountIds = new Map<string, string>()
export function transferAccountId(email: string) {
  if (!accountIds.has(email)) accountIds.set(email, crypto.randomUUID())
  return accountIds.get(email)!
}
export function transferChildren(email: string): Child[] {
  return email === mockIdentity.email ? fixtureStore.snapshot().children ?? [] : mockAccountChildren.get(email) ?? []
}
export function replaceTransferChildren(email: string, children: Child[]) {
  mockAccountChildren.set(email, structuredClone(children))
  if (email === mockIdentity.email) fixtureStore.replaceChildren(structuredClone(children))
}
export function requireNoPendingTransfer(childId?: string) {
  if ([...mockTransfers.values()].some(row => row.status === 'PENDING' &&
    (childId ? row.childId === childId : row.sender === mockIdentity.email)))
    throw new ApiError({ status: 409, code: 'TRANSFER_PENDING', title: '진행 중인 이관을 먼저 취소하거나 완료해 주세요.' })
}

// 동일 탭에서 로그아웃 후 시연 계정 로그인으로 수신자·한도 상태를 확인할 수 있다.
for (const email of ['receiver@example.test', 'full@example.test', 'spare@example.test']) {
  mockAccounts.add(email)
  if (!mockAccountChildren.has(email)) mockAccountChildren.set(email, email === 'full@example.test'
    ? Array.from({ length: 3 }, (_, i) => ({ id: crypto.randomUUID(), nickname: `한도 자녀 ${i + 1}`, grade: 5, birthYear: 2015 })) : [])
}
