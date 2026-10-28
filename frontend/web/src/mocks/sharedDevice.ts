import { ApiError } from '../data/apiClient.ts'
import type { Child } from '../domain/classroom.ts'
import { fixtureStore } from './fixtures/student.ts'
import { mockIdentity } from './fixtures/accounts.ts'

export const sharedDeviceDemo = !!import.meta.env?.DEV && import.meta.env?.VITE_API_MOCK === 'true' &&
  import.meta.env?.VITE_SHARED_DEVICE_MOCK === 'true'

type DemoConfig = { instanceId: string; origins: { label: string; origin: string }[] }
let config: Promise<DemoConfig> | undefined
export async function demoRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('X-Sagomungchi-Demo', '1')
  if (init.body) headers.set('Content-Type', 'application/json')
  const response = await fetch('/__demo/device' + path, { ...init, headers, credentials: 'same-origin', cache: 'no-store' })
    .catch((error) => {
      if (init.signal?.aborted) throw error
      throw new ApiError({ status: 503, code: 'DEMO_UNAVAILABLE',
        title: '공유 시연 서버에 연결하지 못했습니다. 개발 서버를 확인한 뒤 다시 시도해 주세요.' })
    })
  if (!response.ok) {
    const problem = await response.json().catch(() => ({}))
    throw new ApiError({ status: response.status, code: problem.code ?? 'DEMO_UNAVAILABLE',
      title: problem.title ?? '공유 시연 서버에 연결하지 못했습니다.', remainingAttempts: problem.remainingAttempts })
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>
}
export function deviceDemoConfig() {
  return config ??= demoRequest<DemoConfig>('/instance').catch((error) => { config = undefined; throw error })
}

const owners = new Map<string, Promise<string>>()
async function ownerToken() {
  const { instanceId } = await deviceDemoConfig()
  const key = `sagomungchi:qr-demo-owner:${instanceId}:${mockIdentity.email}`
  let pending = owners.get(key)
  if (!pending) {
    pending = (async () => {
      const saved = sessionStorage.getItem(key)
      if (saved) return saved
      const result = await demoRequest<{ ownerToken: string }>('/owners', {
        method: 'POST', body: JSON.stringify({ children: await fixtureStore.children() }),
      })
      // 실제 로그인 토큰이 아닌 이 개발 서버의 임시 목업 소유권 키. QR에는 넣지 않는다.
      sessionStorage.setItem(key, result.ownerToken)
      return result.ownerToken
    })().catch((error) => { owners.delete(key); throw error })
    owners.set(key, pending)
  }
  return pending
}
export async function sharedParentRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Authorization', `Bearer ${await ownerToken()}`)
  const children = await fixtureStore.children()
  const synced = await demoRequest<T>('/children', { method: 'PUT', headers, body: JSON.stringify({ children }) })
  return path === '/children' ? synced : demoRequest<T>(path, { ...init, headers })
}
export type SharedLogin = { child: Child; children: Child[] }
