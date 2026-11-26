import { http } from 'msw/http'
import { guard, respond, studentOnly } from './student.ts'
import { parentGuard } from './parent.ts'
import { mockIdentity } from '../fixtures/accounts.ts'
import {
  completeMockOnboarding,
  mockOnboarding,
  parentOnboardingKey,
  studentOnboardingKey,
} from '../fixtures/onboarding.ts'

const parentKey = (request: Request) => {
  parentGuard(request)
  return parentOnboardingKey(mockIdentity.email)
}
const studentKey = (request: Request) => {
  guard(request)
  return studentOnboardingKey(studentOnly().id)
}

// 첫 사용 안내 완료 기록 (API 명세 `/me/onboarding`·`/students/me/onboarding`, core #1035와 같은 계약)
export const onboardingHandlers = [
  http.get('/api/v1/me/onboarding', ({ request }) => respond(async () => mockOnboarding(parentKey(request)))),
  http.put('/api/v1/me/onboarding', ({ request }) => respond(async () => completeMockOnboarding(parentKey(request)))),
  http.get('/api/v1/students/me/onboarding', ({ request }) => respond(async () => mockOnboarding(studentKey(request)))),
  http.put('/api/v1/students/me/onboarding', ({ request }) => respond(async () => completeMockOnboarding(studentKey(request)))),
]
