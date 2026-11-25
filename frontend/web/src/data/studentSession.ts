// Client parsing is for storage/tab routing only. The server verifies signature, expiry and authorization.
export const studentTokenKey = 'sagomungchi:student-access'
export function studentClaims(token: string): { sid: string; exp: number; iat: number } | null {
  try {
    const data = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return data.role === 'STUDENT' && typeof data.sid === 'string' &&
      Number.isFinite(data.exp) && Number.isFinite(data.iat) ? data : null
  } catch { return null }
}
export function readStudentToken(): string | null {
  try {
    const token = sessionStorage.getItem(studentTokenKey)
    // Keep expired credentials until server validation: a live sibling tab can supply a newer token.
    return token && studentClaims(token) ? token : null
  } catch { return null }
}
export function storeStudentToken(token: string | null) {
  try {
    if (token) sessionStorage.setItem(studentTokenKey, token)
    else sessionStorage.removeItem(studentTokenKey)
  } catch { /* Storage restrictions leave this tab usable in memory; reload will require PIN. */ }
}
