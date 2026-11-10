import type { ProblemDetail } from '../domain/problem.ts'

export const API_BASE = '/api/v1'

// access token은 메모리에만 보관, refresh token은 httpOnly 쿠키 (아키텍처 3장)
let accessToken: string | null = null
let refreshInFlight: Promise<void> | null = null
let tokenRevision = 0
let authGeneration = 0
let accessRole: 'PARENT' | 'STUDENT' | 'ADMIN' | undefined
let studentMode = false
const parentLoginKey = 'sagomungchi:parent-login-required'
let parentLoginPending = false
export function parentLoginRequired() {
  try { return parentLoginPending || (typeof sessionStorage !== 'undefined' && sessionStorage.getItem(parentLoginKey) === 'true') }
  catch { return parentLoginPending }
}
export function requireParentLogin() {
  setAccessToken(null)
  parentLoginPending = true
  try { if (typeof sessionStorage !== 'undefined') sessionStorage.setItem(parentLoginKey, 'true') } catch { /* 탭 메모리의 복귀 표시는 유지한다. */ }
  if (typeof window !== 'undefined') window.dispatchEvent(new Event('sagomungchi:parent-login-required'))
}
// 동석 학생 진입으로 학부모 세션이 잠긴 탭 표시. 값은 여부뿐이며 토큰은 저장하지 않는다 (FN-ACC-05).
const parentLockedKey = 'sagomungchi:parent-session-locked'
export function parentSessionLocked() {
  try { return typeof sessionStorage !== 'undefined' && sessionStorage.getItem(parentLockedKey) === 'true' } catch { return false }
}
export function markParentSessionLocked(locked: boolean) {
  try {
    if (typeof sessionStorage === 'undefined') return
    if (locked) sessionStorage.setItem(parentLockedKey, 'true')
    else sessionStorage.removeItem(parentLockedKey)
  } catch { /* 표시만 사라지며 Google 로그인은 그대로 가능 */ }
}
export function isStudentSession() { return studentMode }
export function hasAccessToken() { return accessToken !== null }
export function studentAuthenticationRequired() {
  setAccessToken(null)
  studentMode = true
  if (typeof window !== 'undefined') window.dispatchEvent(new Event('sagomungchi:student-auth-required'))
  return new ApiError({ status: 401, code: 'STUDENT_REAUTH_REQUIRED', title: '학생 로그인을 다시 진행해 주세요.', retryable: false })
}

export function setAccessToken(token: string | null, role?: 'PARENT' | 'STUDENT' | 'ADMIN') {
  authGeneration++
  assignAccessToken(token, role)
}
function assignAccessToken(token: string | null, role?: 'PARENT' | 'STUDENT' | 'ADMIN') {
  accessRole = token ? role ?? accessRole : undefined
  studentMode = accessRole === 'STUDENT'
  accessToken = token
  tokenRevision++
  if (token && (accessRole === 'PARENT' || accessRole === 'ADMIN')) {
    parentLoginPending = false
    try { if (typeof sessionStorage !== 'undefined') sessionStorage.removeItem(parentLoginKey) } catch { /* 저장소 제한으로 정상 로그인을 실패시키지 않는다. */ }
    markParentSessionLocked(false)
  }
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
  try {
    if (typeof window !== 'undefined' && typeof BroadcastChannel !== 'undefined')
      return (channel ??= new BroadcastChannel('sagomungchi-auth'))
  } catch { /* 탭 알림이 차단되어도 서버의 세션 검증은 유지된다. */ }
}
export function notifyAuthChange(mode: 'PARENT' | 'STUDENT' | 'ADMIN' | 'LOGOUT' = 'PARENT') {
  try { authChannel()?.postMessage(mode) } catch { /* 다른 탭 알림 실패를 현재 로그인 실패로 바꾸지 않는다. */ }
}
export function watchAuthChange(listener: (mode: string) => void) {
  const target = authChannel()
  const handler = (event: MessageEvent) => {
    // A different tab's parent login must not switch a student/guardian-entry tab's role.
    if (event.data === 'PARENT' && (studentMode || parentLoginRequired() || window.location.pathname.startsWith('/student/'))) return
    setAccessToken(null)
    if (event.data === 'STUDENT') studentMode = true
    listener(typeof event.data === 'string' ? event.data : 'PARENT')
  }
  target?.addEventListener('message', handler)
  return () => target?.removeEventListener('message', handler)
}
export async function refreshAccessToken() {
  if (studentMode) throw studentAuthenticationRequired()
  if (parentLoginRequired() && (typeof window === 'undefined' || window.location.pathname !== '/oauth/complete'))
    throw new ApiError({ status: 401, code: 'PARENT_LOGIN_REQUIRED', title: 'Google 계정으로 보호자 로그인을 진행해 주세요.', retryable: false })
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
        typeof data.accessToken !== 'string' || !data.accessToken
      )
        throw new ApiError({ status: 502, code: 'AUTH_RESPONSE_INVALID', title: '로그인 확인 응답을 읽지 못했습니다. 다시 확인해 주세요.', retryable: true })
      // 로그아웃/다른 로그인과 경합한 늦은 refresh 응답은 기존 세션을 되살리지 않는다.
      if (revision !== tokenRevision) throw authChanged()
      if ('role' in data && data.role === 'STUDENT') throw new ApiError({ status: 502, code: 'AUTH_RESPONSE_INVALID', title: '로그인 확인 응답이 올바르지 않습니다.', retryable: false })
      const role = 'role' in data && data.role === 'ADMIN' ? 'ADMIN' : 'PARENT'
      assignAccessToken(data.accessToken, role)
    })
      .catch((error) => {
        // 연결·서버·응답 오류는 세션 만료의 증거가 아니다. 다음 확인에서 다시 시도한다.
        if (!(error instanceof ApiError)) throw new ApiError({ status: 503, code: 'AUTH_UNAVAILABLE', title: '로그인 상태를 확인하지 못했습니다. 연결을 확인한 뒤 다시 시도해 주세요.', retryable: true })
        if (error.problem.status !== 401) throw error
        if (error.problem.code === 'SESSION_CHANGED' || revision !== tokenRevision) throw authChanged()
        if (error instanceof ApiError && error.problem.code === 'PARENT_SESSION_LOCKED') markParentSessionLocked(true)
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

/** 학생 화면 → 학부모 화면 복귀. 잠긴 학부모 refresh 쿠키와 보호자 비밀번호로 새 학부모 access를 받는다. */
export async function unlockParentSession(password: string) {
  await withAuthLock(async () => {
    const response = await fetch(API_BASE + '/auth/parent-unlock', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      body: JSON.stringify({ password }),
    })
    if (!response.ok) {
      const error = await toApiError(response)
      // 잠김·미설정이면 비밀번호로는 돌아갈 수 없다. Google 로그인만 남긴다.
      if (['GUARDIAN_PASSWORD_LOCKED', 'GUARDIAN_PASSWORD_NOT_SET', 'UNAUTHENTICATED', 'REFRESH_REUSED'].includes(error.problem.code))
        markParentSessionLocked(false)
      throw error
    }
    const data: unknown = await response.json()
    if (!data || typeof data !== 'object' || !('accessToken' in data) || typeof data.accessToken !== 'string')
      throw new Error('학부모 화면 복귀 응답을 확인하지 못했습니다.')
    markParentSessionLocked(false)
    setAccessToken(data.accessToken, 'role' in data && data.role === 'ADMIN' ? 'ADMIN' : 'PARENT')
  })
  notifyAuthChange('PARENT')
}

export async function waitForPendingRefresh() {
  // A role-change invalidation must finish rejecting the old response before a fresh restore.
  try { await refreshInFlight } catch { /* The next restore reads the current cookie. */ }
}

/** JSON·SSE가 공유하는 인증 요청. 만료 시 refresh 1회 공유, 원 요청은 한 번만 재시도한다. */
export async function apiRequest(path: string, init: RequestInit = {}): Promise<Response> {
  const generation = authGeneration
  let sentRevision = tokenRevision
  const send = () => {
    const execute = () => {
      if (generation !== authGeneration) throw authChanged()
      sentRevision = tokenRevision
      return fetch(API_BASE + path, { ...init, headers: withAuth(init.headers), credentials: 'same-origin' })
    }
    return ['/auth/logout', '/auth/student-sessions'].includes(path) ? withAuthLock(execute) : execute()
  }
  // 학생 기기·PIN 엔드포인트(API 명세 3.11)의 401은 로그인 단계 오류다. 학생 재로그인 처리로 바꾸지 않는다.
  const studentEntry = path.startsWith('/auth/student/')
  let response = await send()
  if (generation !== authGeneration) throw authChanged()
  if (response.status === 401 && !studentEntry && !['/auth/refresh', '/auth/logout'].includes(path)) {
    const error = await toApiError(response.clone())
    if (error.problem.code === 'TOKEN_EXPIRED') {
      if (studentMode) throw studentAuthenticationRequired()
      if (sentRevision === tokenRevision) await refreshAccessToken()
      response = await send()
      if (generation !== authGeneration) throw authChanged()
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

function authChanged() {
  return new ApiError({ status: 401, code: 'SESSION_CHANGED', title: '로그인 상태가 변경되어 이전 요청을 중단했습니다. 현재 화면에서 다시 확인해 주세요.', retryable: false })
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
