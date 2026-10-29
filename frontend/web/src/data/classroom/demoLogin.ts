import { apiFetch, setAccessToken } from '../apiClient.ts'
import type { Session } from '../../domain/classroom.ts'

/**
 * 개발 시연(MSW) 전용 이메일 로그인 (#97). 실제 학부모·관리자는 Google 인증,
 * 학생은 기기 등록과 PIN으로 들어오며 core에 이 경로가 없다.
 * 목업도 실제 게이트웨이 경로를 MSW가 가로채는 구조라, 시연 로그인만 여기에 따로 둔다.
 * isDemo가 거짓인 운영 빌드에서는 호출하는 곳이 사라져 함께 제외된다.
 */
export async function demoEmailLogin(email: string, password: string): Promise<Session> {
  const raw = (await apiFetch<Record<string, unknown>>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })) ?? {}
  if (raw.role !== 'PARENT' && raw.role !== 'ADMIN' || typeof raw.accessToken !== 'string')
    throw new Error('학부모/관리자 로그인 응답이 계약과 다릅니다.')
  setAccessToken(raw.accessToken, raw.role)
  const me = raw.role === 'ADMIN' ? ((await apiFetch<Record<string, unknown>>('/me')) ?? {}) : raw
  return { role: raw.role, permissions: me.permissions } as Session
}
