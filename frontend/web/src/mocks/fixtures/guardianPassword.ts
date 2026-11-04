import { mockIdentity } from './accounts.ts'

/** DEV MSW 전용 보호자 비밀번호 (core `guardian_password`와 같은 규칙: 5회 실패 잠금, 재설정 시 해제). */
const FAILURE_LIMIT = 5
const passwords = new Map<string, { password: string; failed: number; locked: boolean; updatedAt: string }>()
/** 동석 학생 진입으로 잠긴 학부모 세션 (core `auth_session.locked_at`) */
let parentLocked = false

export const guardianPasswordState = () => {
  const row = passwords.get(mockIdentity.email)
  return { set: !!row, locked: !!row?.locked, updatedAt: row?.updatedAt ?? null }
}
export function setGuardianPassword(password: string) {
  passwords.set(mockIdentity.email, { password, failed: 0, locked: false, updatedAt: new Date().toISOString() })
  return guardianPasswordState()
}
export function attemptGuardianPassword(password: string): { code?: string; remainingAttempts?: number } {
  const row = passwords.get(mockIdentity.email)
  if (!row) return { code: 'GUARDIAN_PASSWORD_NOT_SET' }
  if (row.locked) return { code: 'GUARDIAN_PASSWORD_LOCKED', remainingAttempts: 0 }
  if (row.password === password) { row.failed = 0; return {} }
  row.failed += 1
  row.locked = row.failed >= FAILURE_LIMIT
  return { code: row.locked ? 'GUARDIAN_PASSWORD_LOCKED' : 'GUARDIAN_PASSWORD_INVALID', remainingAttempts: Math.max(0, FAILURE_LIMIT - row.failed) }
}
export const parentSessionLocked = () => parentLocked
export function lockParentSession(locked: boolean) { parentLocked = locked }
