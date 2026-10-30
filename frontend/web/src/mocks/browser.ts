import { adminServiceHandlers } from './handlers/adminService.ts'
import { setupWorker } from 'msw/browser'
import { serviceHandlers } from './handlers/service.ts'
import { studentHandlers, setMockScenario } from './handlers/student.ts'
import type { DemoScenario } from '../domain/classroom.ts'
import { parentHandlers } from './handlers/parent.ts'
import { adminHandlers } from './handlers/admin.ts'
import { setWorkspaceScenario } from './fixtures/accounts.ts'
import { setMockChildPlan } from './fixtures/childPlan.ts'
import { studentDeviceHandlers } from './handlers/studentDevice.ts'
import { setDeviceScenario } from './fixtures/studentDevice.ts'
import type { DeviceScenario } from './fixtures/studentDevice.ts'
import { demoRequest, sharedDeviceDemo } from './sharedDevice.ts'

// 학생 기기 핸들러가 GET /children에 PIN 상태를 더하므로 기존 핸들러보다 먼저 둔다.
export const mockHandlers = [
  ...adminServiceHandlers,
  ...serviceHandlers,
  ...studentDeviceHandlers,
  ...parentHandlers,
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
  window.addEventListener('sagomungchi:mock-scenario', (event) =>
    setMockScenario((event as CustomEvent<DemoScenario>).detail),
  )
}
export async function startMockWorker() {
  installMockEvents()
  const worker = setupWorker(...mockHandlers)
  await worker.start({
    quiet: true,
    onUnhandledFrame: 'bypass',
  })
}
