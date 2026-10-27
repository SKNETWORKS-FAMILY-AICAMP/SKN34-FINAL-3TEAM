import { setupWorker } from 'msw/browser'
import { studentHandlers, setMockScenario } from './handlers/student.ts'
import type { DemoScenario } from '../domain/classroom.ts'
import { parentHandlers } from './handlers/parent.ts'
import { adminHandlers } from './handlers/admin.ts'
import { setWorkspaceScenario } from './fixtures/accounts.ts'
import { setMockChildPlan } from './fixtures/childPlan.ts'

const worker = setupWorker(...parentHandlers, ...adminHandlers, ...studentHandlers)
export async function startMockWorker() {
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
  await worker.start({
    quiet: true,
    onUnhandledFrame: 'bypass',
  })
}
