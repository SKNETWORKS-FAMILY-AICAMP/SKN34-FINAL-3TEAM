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
export let workspaceScenario = 'normal'
export function setWorkspaceScenario(value: string) {
  workspaceScenario = value
}
