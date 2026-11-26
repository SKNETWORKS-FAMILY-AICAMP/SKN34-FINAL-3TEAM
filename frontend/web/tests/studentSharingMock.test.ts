import test from 'node:test'
import assert from 'node:assert/strict'
Object.defineProperty(globalThis, 'location', { value: new URL('http://localhost/'), configurable: true })
const { setupServer } = await import('msw/node')
const { studentHandlers } = await import('../src/mocks/handlers/student.ts')
const { parentHandlers } = await import('../src/mocks/handlers/parent.ts')
const server = setupServer(...parentHandlers, ...studentHandlers)
server.listen({ onUnhandledFrame: 'error' }); test.after(() => server.close())
let token = ''
async function call(path: string, method = 'GET', data?: unknown) {
  const response = await fetch('http://localhost/api/v1' + path, { method,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    ...(data === undefined ? {} : { body: JSON.stringify(data) }) })
  return { status: response.status, data: await response.json() }
}
async function parent() {
  token = (await call('/auth/login', 'POST', { email: 'parent@example.test', password: 'demo-only' })).data.accessToken
  return (await call('/children')).data.items[0].childId as string
}

// #1064: 학생이 학부모 공개를 고르던 설정(#206)은 없어졌다. 동의는 자녀 등록 때 법정대리인 동의서(GUARDIAN 1.2)로 받는다.
test('학생 공개 설정 API가 목업에 없다', () => {
  const paths = [...parentHandlers, ...studentHandlers].map(h => String((h.info as { path?: unknown }).path ?? ''))
  assert.equal(paths.some(path => path.includes('sharing-preferences')), false)
})

test('학부모는 학생 설정 없이 원문·리포트·근거를 바로 본다', async () => {
  const id = await parent(), path = `/children/${id}`
  assert.equal((await call(`${path}/attempts?from=2026-10-01&to=2026-11-01`)).status, 200)
  assert.equal((await call(`${path}/summary?from=2026-10-01&to=2026-11-01`)).status, 200)
  const reportId = (await call(`${path}/reports`)).data.items[0].reportId as string
  const report = await call(`/reports/${reportId}`)
  assert.equal(report.status, 200)
  assert.equal('parentSharingEnabled' in report.data, false)
  assert.ok(Array.isArray(report.data.metrics))
  assert.notEqual((await call(`/reports/${reportId}/evidence/metric-1`)).data?.code, 'STUDENT_RECORDS_PRIVATE')
})
