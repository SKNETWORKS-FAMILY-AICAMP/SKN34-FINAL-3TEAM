import test from 'node:test'
import assert from 'node:assert/strict'
Object.defineProperty(globalThis, 'location', { value: new URL('http://localhost/'), configurable: true })
const { setupServer } = await import('msw/node')
const { studentDeviceHandlers } = await import('../src/mocks/handlers/studentDevice.ts')
const { parentHandlers } = await import('../src/mocks/handlers/parent.ts')
const { studentHandlers } = await import('../src/mocks/handlers/student.ts')
const server = setupServer(...studentDeviceHandlers, ...parentHandlers, ...studentHandlers)
server.listen({ onUnhandledRequest: 'error' })
test.after(() => server.close())
const base = 'http://localhost/api/v1'
test('MSW consent APIs keep the new onboarding and device child list contracts connected', async () => {
  let token = ''
  async function call(path: string, body?: unknown, expected = 200) {
    const response = await fetch(base + path, { method: body ? 'POST' : 'GET',
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body ? { 'Content-Type': 'application/json' } : {}) },
      body: body ? JSON.stringify(body) : undefined })
    const data = await response.json()
    assert.equal(response.status, expected, `${path}: ${JSON.stringify(data)}`)
    return data
  }
  const docs = (await call('/consent-documents')).items as { documentId: string; version: string; kind: string }[]
  const choices = docs.map((d) => ({ documentId: d.documentId, version: d.version, agreed: true }))
  const guardian = choices.filter((c) => docs.find((d) => d.documentId === c.documentId)?.kind === 'GUARDIAN')
  const account = choices.filter((c) => !guardian.includes(c))
  const email = `consent-${Date.now()}@example.test`
  await call('/auth/signup', { email, password: 'demo-only', name: '합성 보호자', consents: account }, 201)
  token = (await call('/auth/login', { email, password: 'demo-only' })).accessToken
  assert.equal((await call('/me')).nextAction, 'CHILD_REGISTRATION_REQUIRED')
  const child = await call('/children', { nickname: '합성 자녀', grade: 3, birthYear: 2017, consents: guardian }, 201)
  assert.equal((await call('/me')).nextAction, 'READY')
  const initial = (await call('/me/consents')).items
  assert.equal(initial.length, 3)
  const g = initial.find((c: { studentId: string }) => c.studentId === child.id)
  await call(`/me/consents/${g.consentId}/withdrawal`, {})
  const row = (await call('/children')).items.find((c: { id: string }) => c.id === child.id)
  assert.equal(row.guardianConsentRequired, true)
  assert.equal(row.hasRecords, null); assert.equal(row.recordState, 'CONSENT_REQUIRED')
  assert.equal((await call('/auth/student-sessions', { childId: child.id }, 403)).code, 'CHILD_NOT_LINKED')
  await call('/me/consents', { childId: child.id, consents: guardian })
  assert.equal((await call('/me/consents')).items.length, 4)
  const terms = initial.find((c: { document: { kind: string } }) => c.document.kind === 'TERMS')
  await call(`/me/consents/${terms.consentId}/withdrawal`, {})
  assert.equal((await call('/me')).nextAction, 'CONSENT_REQUIRED')
  assert.equal((await call('/children', undefined, 403)).code, 'CONSENT_REQUIRED')
  assert.equal((await call('/me/consents', { consents: account.map((c) => ({ ...c, version: 'old' })) }, 409)).code, 'CONSENT_DOCUMENT_CHANGED')
  await call('/me/consents', { consents: account })
  assert.equal((await call('/me')).nextAction, 'READY')
  assert.equal((await call('/children')).items[0].guardianConsentRequired, false)
})
