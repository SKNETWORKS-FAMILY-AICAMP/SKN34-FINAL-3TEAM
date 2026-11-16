import type { Permission } from '../../domain/admin/operations.ts'
import type { Child } from '../../domain/classroom.ts'
export const mockAccountChildren = new Map<string, Child[]>()
export const mockAccounts = new Set([
  'parent@example.test',
  'admin@example.test',
  'content@example.test',
  'ops@example.test',
  'payment@example.test',
  'refund@example.test',
])
export const mockIdentity = {
  userId: 'mock-user',
  name: '시연 보호자',
  email: 'parent@example.test',
  permissions: [] as Permission[],
}
export const permissionsFor = (email: string): Permission[] =>
  email === 'admin@example.test'
    ? ['CONTENT', 'SERVICE_OPS', 'PAYMENT_VIEW', 'PAYMENT_REFUND']
    : email === 'content@example.test'
      ? ['CONTENT']
      : email === 'ops@example.test'
        ? ['SERVICE_OPS']
        : email === 'payment@example.test'
          ? ['PAYMENT_VIEW']
          : email === 'refund@example.test'
            ? ['PAYMENT_REFUND']
            : []
/**
 * #415 ID·비밀번호 학부모(core parent_credential과 같은 규칙). 개발 목업 전용이며 비밀번호는 메모리에만 둔다.
 * 목업 저장소는 이메일을 키로 쓰므로 `<id>@id.example.test`를 내부 키로만 쓴다(/me에는 노출하지 않음).
 */
export const mockPasswordParents = new Map<string, { password: string; email: string; failed: number; lockedUntil: number }>()
export const mockPasswordLogin = { loginId: null as string | null }
export const passwordParentKey = (loginId: string) => `${loginId}@id.example.test`
export let workspaceScenario = 'normal'
export function setWorkspaceScenario(value: string) {
  workspaceScenario = value
}


// Development fixture state only; never imported by the production API path.
export const mockConsentHistory = new Map<string, import('../../domain/parent.ts').ConsentHistory[]>()
export function mockConsentRequired(email = mockIdentity.email) {
  const rows = mockConsentHistory.get(email)
  if (!rows) return false // legacy demo fixtures start with consent already completed
  return ['TERMS', 'PRIVACY'].some((kind) => {
    const entry = rows.find((r) => !r.studentId && r.document.kind === kind)
    return !entry?.agreed || entry.status !== 'AGREED'
  })
}
export function mockGuardianConsentRequired(childId: string, email = mockIdentity.email) {
  const entry = mockConsentHistory.get(email)?.find((r) => r.studentId === childId && r.document.kind === 'GUARDIAN') // 선택 동의(COMMUNITY)는 이용 제한과 무관
  return !!entry && (!entry.agreed || entry.status !== 'AGREED')
}
