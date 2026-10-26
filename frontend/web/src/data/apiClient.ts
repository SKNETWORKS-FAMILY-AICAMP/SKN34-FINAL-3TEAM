import type { ProblemDetail } from '../domain/problem.ts'

export const API_BASE = '/api/v1'

// access token은 메모리에만 보관, refresh token은 httpOnly 쿠키 (아키텍처 3장)
let accessToken: string | null = null

export function setAccessToken(token: string | null) {
  accessToken = token
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
    return new ApiError((await response.json()) as ProblemDetail)
  }
  return new ApiError({ title: response.statusText, status: response.status, code: 'REQUEST_FAILED' })
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = withAuth(init.headers)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await fetch(API_BASE + path, { ...init, headers, credentials: 'same-origin' })
  if (!response.ok) throw await toApiError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}
