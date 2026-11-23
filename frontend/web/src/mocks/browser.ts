import { guardianTransferHandlers } from './handlers/guardianTransfers.ts'
import { paymentHandlers } from './handlers/payments.ts'
import { adminServiceHandlers } from './handlers/adminService.ts'
import { setupWorker } from 'msw/browser'
import { serviceHandlers } from './handlers/service.ts'
import { studentHandlers, setMockScenario, mockStudent } from './handlers/student.ts'
import { applyMockThemeState } from './fixtures/themeState.ts'
import type { MockThemeState } from './fixtures/themeState.ts'
import type { DemoScenario } from '../domain/classroom.ts'
import { parentHandlers, reviseMockConsents } from './handlers/parent.ts'
import { retentionHandlers } from './handlers/retention.ts'
import { memoryHandlers } from './handlers/memory.ts'
import { MOCK_MEMORY_BOOK_DEMO_KEY, memoryBookHandlers } from './handlers/memoryBook.ts'
import { adminHandlers } from './handlers/admin.ts'
import { adminThemeDraftHandlers } from './handlers/adminThemeDrafts.ts'
import { setWorkspaceScenario } from './fixtures/accounts.ts'
import { setMockChildPlan } from './fixtures/childPlan.ts'
import { studentDeviceHandlers } from './handlers/studentDevice.ts'
import { setDeviceScenario } from './fixtures/studentDevice.ts'
import type { DeviceScenario } from './fixtures/studentDevice.ts'
import { demoRequest, sharedDeviceDemo } from './sharedDevice.ts'

// 학생 기기 핸들러가 GET /children에 PIN 상태를 더하므로 기존 핸들러보다 먼저 둔다.
export const mockHandlers = [
  ...guardianTransferHandlers,
  ...paymentHandlers,
  ...adminServiceHandlers,
  // 커뮤니티 신고·선택 동의는 기존 신고·동의 목업보다 먼저 받아야 한다.
  ...retentionHandlers,
  ...memoryHandlers,
  ...memoryBookHandlers,
  ...serviceHandlers,
  ...studentDeviceHandlers,
  ...parentHandlers,
  ...adminThemeDraftHandlers,
  ...adminHandlers,
  ...studentHandlers,
]
export function installMockEvents() {
  window.addEventListener('sagomungchi:device-scenario', (event) => {
    const value = (event as CustomEvent<DeviceScenario>).detail
    if (sharedDeviceDemo) {
      void demoRequest('/scenario', { method: 'POST', body: JSON.stringify({ value }) })
        .then(() => window.dispatchEvent(new Event('sagomungchi:device-scenario-applied')))
        .catch(() => window.dispatchEvent(new Event('sagomungchi:device-scenario-failed')))
    } else {
      setDeviceScenario(value)
      window.dispatchEvent(new Event('sagomungchi:device-scenario-applied'))
    }
  })
  window.addEventListener('sagomungchi:test-child-plan', (event) => {
    const detail = (event as CustomEvent<unknown>).detail
    window.dispatchEvent(new CustomEvent('sagomungchi:test-child-plan-result', {
      detail: { applied: setMockChildPlan(detail) },
    }))
  })
  window.addEventListener('sagomungchi:workspace-scenario', (event) =>
    setWorkspaceScenario((event as CustomEvent<string>).detail),
  )
  // 개발 점검표 "동의 문서 개정(재동의) 시연": 지금 계정을 개정 전 문서에만 동의한 상태로 (#912)
  window.addEventListener('sagomungchi:mock-consent-revised', () => reviseMockConsents())
  // 개발 목업 "홈 상태"(캔버스 Home 보드와 같은 8가지)·프리미엄 바꿔 보기
  window.addEventListener('sagomungchi:mock-theme-state', (event) => {
    const { state, premium } = (event as CustomEvent<{ state: MockThemeState | ''; premium: boolean }>).detail
    let student
    try { student = mockStudent() } catch { return }
    void applyMockThemeState(student, state, premium).finally(() => window.dispatchEvent(new Event('sagomungchi:mock-theme-state-applied')))
  })
  window.addEventListener('sagomungchi:mock-scenario', (event) =>
    setMockScenario((event as CustomEvent<DemoScenario>).detail),
  )
}
export async function startMockWorker() {
  // 추억 그림책 시연(docs/proposals/memory-book.md, 미도입 시험 구현): ?memoryBookDemo=1로 열면 이 탭에서 유료·원문 공개로 본다
  if (new URLSearchParams(location.search).get('memoryBookDemo') === '1') sessionStorage.setItem(MOCK_MEMORY_BOOK_DEMO_KEY, '1')
  const reportDemo = await import('./fixtures/structuredReportDemo.ts')
  if (reportDemo.structuredReportDemoRequested()) reportDemo.rememberStructuredReportDemo()
  if (reportDemo.hasStructuredReportDemo()) {
    // Generated server-side by the explicitly invoked runner. Never a paid call on page load.
    let cache: import('./fixtures/structuredReportDemo.ts').GemmaReportCache | undefined
    try {
      const response = await fetch('/.taste-skill/structured-report-demo/gemma-explanations.json', { cache: 'no-store' })
      if (response.ok) {
        const value = await response.json()
        if (typeof value?.model === 'string' && typeof value?.promptVersion === 'string' && Array.isArray(value?.items)) cache = value
      }
    } catch { /* No handwritten explanation is substituted when the real output is missing. */ }
    reportDemo.seedStructuredReportDemo(cache)
  }
  installMockEvents()
  const worker = setupWorker(...mockHandlers)
  await worker.start({
    quiet: true,
    onUnhandledFrame: 'bypass',
  })
  if (reportDemo.structuredReportDemoRequested()) {
    // Explicit local demo entry only, not a production authentication shortcut.
    const response = await fetch('/api/v1/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'parent@example.test', password: 'demo-only' }) })
    if (!response.ok) throw new Error('리포트 시연 계정에 로그인하지 못했습니다.')
  }
}
