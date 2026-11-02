import test from 'node:test'
import assert from 'node:assert/strict'
Object.defineProperty(globalThis, 'location', { value: new URL('http://localhost/'), configurable: true })
const { setupServer } = await import('msw/node')
const { studentHandlers } = await import('../src/mocks/handlers/student.ts')
const { parentHandlers } = await import('../src/mocks/handlers/parent.ts')
const { mockSharing } = await import('../src/mocks/fixtures/sharing.ts')
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
async function student(id: string) {
  token = (await call('/auth/student-sessions', 'POST', { childId: id })).data.accessToken
}

test('기본 비공개 → 학생 공개 → 학부모 원문 허용 → 학생 비공개로 기존 원문 재차 차단', async () => {
  mockSharing.clear()
  const id = await parent(), path = `/children/${id}`
  assert.equal((await call(`${path}/sharing-preferences`)).data.parentSharingEnabled, false)
  assert.equal((await call('/students/me/sharing-preferences', 'PUT', { parentSharingEnabled: true })).status, 403)
  assert.equal((await call(`${path}/attempts?from=2026-10-01&to=2026-11-01`)).data.code, 'STUDENT_RECORDS_PRIVATE')
  assert.equal((await call(`${path}/summary?from=2026-10-01&to=2026-11-01`)).status, 200)
  assert.equal((await call(`/conversations?childId=${id}`)).status, 403)
  const reportId = (await call(`${path}/reports`)).data.items[0].reportId as string
  const report = await call(`/reports/${reportId}`)
  assert.equal(report.status, 200)
  assert.equal(report.data.parentSharingEnabled, false)
  assert.equal(report.data.narrative, null)
  assert.deepEqual(report.data.quotes, [])
  assert.ok(Array.isArray(report.data.metrics))
  assert.ok(report.data.changes.every((c: { first: { text: null }; revised: { text: null } }) => c.first.text === null && c.revised.text === null))
  assert.equal((await call(`/reports/${reportId}/download?format=pdf`)).status, 403)
  await student(id)
  assert.equal((await call('/students/me/sharing-preferences')).data.parentSharingEnabled, false)
  assert.equal((await call('/students/me/sharing-preferences', 'PUT', { parentSharingEnabled: null })).status, 400)
  assert.equal((await call('/students/me/sharing-preferences', 'PUT', { parentSharingEnabled: true })).status, 200)
  await parent()
  assert.equal((await call(`${path}/attempts?from=2026-10-01&to=2026-11-01`)).status, 200)
  await student(id)
  await call('/students/me/sharing-preferences', 'PUT', { parentSharingEnabled: false })
  await parent()
  assert.equal((await call(`${path}/attempts?from=2026-10-01&to=2026-11-01`)).status, 403)
  assert.equal((await call(`/reports/${reportId}`)).data.parentSharingEnabled, false)
  assert.equal((await call(`/reports/${reportId}/evidence/metric-1`)).status, 403)
})
