import type { ProblemDetail } from '../domain/problem.ts'

export const API_BASE = '/api/v1'

// access token은 메모리에만 보관, refresh token은 httpOnly 쿠키 (아키텍처 3장)
let accessToken: string | null = null
let refreshInFlight: Promise<void> | null = null
let tokenRevision = 0

export function setAccessToken(token: string | null) {
  accessToken = token
  tokenRevision++
}

async function refreshAccessToken() {
  if (!refreshInFlight) {
    const revision = tokenRevision
    refreshInFlight = (async () => {
      const response = await fetch(API_BASE + '/auth/refresh', {
        method: 'POST',
        credentials: 'same-origin',
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
      setAccessToken(data.accessToken)
    })()
      .catch(() => {
        if (revision === tokenRevision) {
          setAccessToken(null)
          if(typeof window!=='undefined') window.dispatchEvent(new Event('sagomungchi:session-expired'))
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

/** JSON·SSE가 공유하는 인증 요청. 만료 시 refresh 1회 공유, 원 요청은 한 번만 재시도한다. */
export async function apiRequest(path: string, init: RequestInit = {}): Promise<Response> {
  const send = () =>
    fetch(API_BASE + path, { ...init, headers: withAuth(init.headers), credentials: 'same-origin' })
  const sentRevision = tokenRevision
  let response = await send()
  if (response.status === 401 && !['/auth/login', '/auth/refresh', '/auth/logout'].includes(path)) {
    const error = await toApiError(response.clone())
    if (error.problem.code === 'TOKEN_EXPIRED') {
      if (sentRevision === tokenRevision) await refreshAccessToken()
      response = await send()
    }
  }
  if (!response.ok) throw await toApiError(response)
  return response
}

export function withAuth(headers: HeadersInit = {}): Headers {
  const result = new Headers(headers)
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
