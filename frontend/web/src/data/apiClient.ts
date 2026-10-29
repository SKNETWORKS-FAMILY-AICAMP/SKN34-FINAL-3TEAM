import type { ProblemDetail } from '../domain/problem.ts'

export const API_BASE = '/api/v1'

// access token은 메모리에만 보관, refresh token은 httpOnly 쿠키 (아키텍처 3장)
let accessToken: string | null = null
let refreshInFlight: Promise<void> | null = null
let tokenRevision = 0
let accessRole: 'PARENT' | 'STUDENT' | 'ADMIN' | undefined
let studentMode = false
export function hasAccessToken() { return accessToken !== null }
export function studentAuthenticationRequired() {
  setAccessToken(null)
  studentMode = true
  if (typeof window !== 'undefined') window.dispatchEvent(new Event('sagomungchi:student-auth-required'))
  return new ApiError({ status: 401, code: 'STUDENT_REAUTH_REQUIRED', title: '학생 로그인을 다시 진행해 주세요.', retryable: false })
}

export function setAccessToken(token: string | null, role?: 'PARENT' | 'STUDENT' | 'ADMIN') {
  accessRole = token ? role ?? accessRole : undefined
  studentMode = accessRole === 'STUDENT'
  accessToken = token
  tokenRevision++
}

// Web Locks serialize cookie rotation across tabs; no tokens are persisted.
export async function withAuthLock<T>(action: () => Promise<T>): Promise<T> {
  if (typeof navigator !== 'undefined' && navigator.locks)
    return navigator.locks.request('sagomungchi-auth', action)
  // LAN HTTP 시연에는 Web Locks가 없다. 공유 목업 모드에서만 가상 인증을 실행한다.
  if (import.meta.env?.DEV && import.meta.env?.VITE_API_MOCK === 'true' &&
      import.meta.env?.VITE_SHARED_DEVICE_MOCK === 'true') return action()
  if (typeof window !== 'undefined') throw new Error('이 브라우저에서는 안전한 로그인 동기화를 지원하지 않습니다.')
  return action() // Node contract tests have no browser cookie jar.
}
let channel: BroadcastChannel | undefined
function authChannel() {
  if (typeof window !== 'undefined' && typeof BroadcastChannel !== 'undefined')
    return (channel ??= new BroadcastChannel('sagomungchi-auth'))
}
export function notifyAuthChange(mode: 'PARENT' | 'STUDENT' | 'ADMIN' | 'LOGOUT' = 'PARENT') { authChannel()?.postMessage(mode) }
export function watchAuthChange(listener: (mode: string) => void) {
  const target = authChannel()
  const handler = (event: MessageEvent) => {
    setAccessToken(null)
    if (event.data === 'STUDENT') studentMode = true
    listener(typeof event.data === 'string' ? event.data : 'PARENT')
  }
  target?.addEventListener('message', handler)
  return () => target?.removeEventListener('message', handler)
}
export async function refreshAccessToken() {
  if (studentMode) throw studentAuthenticationRequired()
  if (!refreshInFlight) {
    const revision = tokenRevision
    const hadAccess = accessToken !== null
    refreshInFlight = withAuthLock(async () => {
      const response = await fetch(API_BASE + '/auth/refresh', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      })
      if (!response.ok) throw await toApiError(response)
      const data: unknown = await response.json()
      if (
        !data ||
        typeof data !== 'object' ||
        !('accessToken' in data) ||
        typeof data.accessToken !== 'string'
      )
        throw new Error('토큰 재발급 응답을 확인하지 못했습니다.')
      // 로그아웃/다른 로그인과 경합한 늦은 refresh 응답은 기존 세션을 되살리지 않는다.
      if (revision !== tokenRevision) throw new Error('인증 상태가 변경되었습니다.')
      if ('role' in data && data.role === 'STUDENT') throw new Error('학생 refresh 발급은 허용되지 않습니다.')
      const role = 'role' in data && data.role === 'ADMIN' ? 'ADMIN' : 'PARENT'
      setAccessToken(data.accessToken, role)
    })
      .catch((error) => {
        if (error instanceof ApiError && error.problem.status >= 500) throw error
        if (revision === tokenRevision) {
          setAccessToken(null)
          if(hadAccess && typeof window!=='undefined') window.dispatchEvent(new Event('sagomungchi:session-expired'))
        }
        throw new ApiError({
          status: 401,
          code: 'UNAUTHENTICATED',
          title: '로그인이 만료되었습니다. 다시 로그인해 주세요.',
          retryable: false,
        })
      })
      .finally(() => {
        refreshInFlight = null
      })
  }
  return refreshInFlight
}

export async function waitForPendingRefresh() {
  // A role-change invalidation must finish rejecting the old response before a fresh restore.
  try { await refreshInFlight } catch { /* The next restore reads the current cookie. */ }
}

/** JSON·SSE가 공유하는 인증 요청. 만료 시 refresh 1회 공유, 원 요청은 한 번만 재시도한다. */
export async function apiRequest(path: string, init: RequestInit = {}): Promise<Response> {
  const send = () => {
    const execute = () => fetch(API_BASE + path, { ...init, headers: withAuth(init.headers), credentials: 'same-origin' })
    return ['/auth/logout', '/auth/student-sessions'].includes(path) ? withAuthLock(execute) : execute()
  }
  const sentRevision = tokenRevision
  // 학생 기기·PIN 엔드포인트(API 명세 3.11)의 401은 로그인 단계 오류다. 학생 재로그인 처리로 바꾸지 않는다.
  const studentEntry = path.startsWith('/auth/student/')
  let response = await send()
  if (response.status === 401 && !studentEntry && !['/auth/login', '/auth/refresh', '/auth/logout'].includes(path)) {
    const error = await toApiError(response.clone())
    if (error.problem.code === 'TOKEN_EXPIRED') {
      if (studentMode) throw studentAuthenticationRequired()
      if (sentRevision === tokenRevision) await refreshAccessToken()
      response = await send()
    }
  }
  if (!response.ok) {
    const error = await toApiError(response)
    if (studentEntry) throw error
    if (studentMode && ['CONSENT_REQUIRED', 'CHILD_NOT_LINKED'].includes(error.problem.code)) throw studentAuthenticationRequired()
    if (error.problem.code === 'CONSENT_REQUIRED' && typeof window !== 'undefined')
      window.dispatchEvent(new Event('sagomungchi:consent-required'))
    if (error.problem.code === 'SESSION_CHANGED' && typeof window !== 'undefined') {
      if (studentMode) throw studentAuthenticationRequired()
      setAccessToken(null)
      window.dispatchEvent(new Event('sagomungchi:session-changed'))
    }
    if (error.problem.status === 401 && !['TOKEN_EXPIRED', 'SESSION_CHANGED'].includes(error.problem.code)) {
      if (studentMode) throw studentAuthenticationRequired()
      setAccessToken(null)
      if (typeof window !== 'undefined') window.dispatchEvent(new Event('sagomungchi:session-expired'))
    }
    throw error
  }
  return response
}

export function withAuth(headers: HeadersInit = {}): Headers {
  const result = new Headers(headers)
  result.set('X-Requested-With', 'XMLHttpRequest')
  if (accessToken) result.set('Authorization', `Bearer ${accessToken}`)
  return result
}

export class ApiError extends Error {
  readonly problem: ProblemDetail

  constructor(problem: ProblemDetail) {
    super(problem.detail ?? problem.title)
    this.problem = problem
  }
}

export async function toApiError(response: Response): Promise<ApiError> {
  if (response.headers.get('content-type')?.includes('json')) {
    const data = (await response.json()) as Partial<ProblemDetail>
    return new ApiError({
      ...data,
      title: data.title ?? '요청을 처리하지 못했습니다.',
      status: response.status,
      code: data.code ?? 'REQUEST_FAILED',
    })
  }
  return new ApiError({
    title: response.statusText,
    status: response.status,
    code: 'REQUEST_FAILED',
  })
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await apiResponse<T>(path, init)).data
}

/** 초안 동시성 제어에 필요한 ETag를 보존한다. */
export async function apiResponse<T>(
  path: string,
  init: RequestInit = {},
): Promise<{ data: T; etag: string | null }> {
  const headers = withAuth(init.headers)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await apiRequest(path, { ...init, headers })
  return {
    data: response.status === 204 ? (undefined as T) : ((await response.json()) as T),
    etag: response.headers.get('ETag'),
  }
}
