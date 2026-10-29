import { apiFetch } from '../apiClient.ts'
import type { Consent } from '../../domain/parent.ts'
import { json } from './api.ts'

/**
 * 개발 시연(MSW) 전용 이메일 이용 등록 (#97). 실제 서비스는 Google 인증으로 시작하며
 * core에 이 경로가 없다. 운영 빌드에서는 호출하는 화면이 빠지므로 함께 제외된다.
 */
export const demoSignup = (data: {
  email: string
  password: string
  name: string
  consents: Consent[]
}) => apiFetch<{ userId: string }>('/auth/signup', json(data))
