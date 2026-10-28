import test from 'node:test'
import assert from 'node:assert/strict'
import { parentApi } from '../src/data/parent/api.ts'
import { createApiGateway } from '../src/data/classroom/apiGateway.ts'
import { apiFetch, setAccessToken } from '../src/data/apiClient.ts'

const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
test('onboarding consumer sends exact document versions then observes server nextAction and child contract', async (t) => {
  let nextAction = 'CONSENT_REQUIRED'
  const choice = { documentId: 'terms', version: 'v2', agreed: true }
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    assert.equal(new Headers(init.headers).get('Authorization'), 'Bearer synthetic-parent')
    if (url.endsWith('/me/consents')) {
      assert.deepEqual(JSON.parse(String(init.body)), { consents: [choice] })
      nextAction = 'CHILD_REGISTRATION_REQUIRED'; return json({ items: [], page: 0, size: 0, totalElements: 0 })
    }
    if (url.endsWith('/children') && init.method === 'POST') {
      assert.equal(JSON.parse(String(init.body)).consents[0].version, 'v2')
      nextAction = 'READY'; return json({ id: 'child', nickname: '별명', grade: 3, birthYear: 2017 }, 201)
    }
    if (url.endsWith('/children')) return json({ items: [{ id: 'child', nickname: '별명', grade: 3, birthYear: 2017, hasRecords: null, recordState: 'UNAVAILABLE', guardianConsentRequired: false }] })
    return json({ role: 'PARENT', nextAction, startPath: nextAction === 'READY' ? '/parent/journal' : '/parent/children/new' })
  })
  setAccessToken('synthetic-parent', 'PARENT')
  assert.equal((await createApiGateway().restore()).nextAction, 'CONSENT_REQUIRED')
  await parentApi.saveConsents({ consents: [choice] })
  assert.equal((await createApiGateway().restore()).nextAction, 'CHILD_REGISTRATION_REQUIRED')
  const c = await parentApi.register({ nickname: '별명', grade: 3, birthYear: 2017, consents: [choice] })
  assert.equal(c.id, 'child')
  assert.equal((await createApiGateway().restore()).nextAction, 'READY')
  const children = await createApiGateway().children()
  assert.equal(children[0].hasRecords, null)
  assert.equal(children[0].recordState, 'UNAVAILABLE')
  assert.equal(children[0].plan, undefined)
  setAccessToken(null)
})
test('withdrawal and renewal use parent consent APIs and stale version errors propagate', async (t) => {
  const paths: string[] = []
  t.mock.method(globalThis, 'fetch', async (url: string) => {
    paths.push(url)
    if (url.endsWith('/withdrawal')) return json({ consentId: 'history-id', status: 'WITHDRAWN' })
    return json({ code: 'CONSENT_DOCUMENT_CHANGED', status: 409, title: '문서를 다시 확인해 주세요.' }, 409)
  })
  assert.equal((await parentApi.withdrawConsent('history-id')).status, 'WITHDRAWN')
  await assert.rejects(parentApi.saveConsents({ childId: 'child', consents: [{ documentId: 'old', version: 'v1', agreed: true }] }),
    (e: { problem: { code: string } }) => e.problem.code === 'CONSENT_DOCUMENT_CHANGED')
  assert.deepEqual(paths, ['/api/v1/me/consents/history-id/withdrawal', '/api/v1/me/consents'])
})
test('revoked student consent does not refresh parent credentials', async (t) => {
  let calls = 0
  t.mock.method(globalThis, 'fetch', async () => { calls++; return json({ code: 'CHILD_NOT_LINKED', title: '동의 필요' }, 403) })
  setAccessToken('student-access', 'STUDENT')
  await assert.rejects(apiFetch('/students/me/home'), (e: { problem: { code: string } }) => e.problem.code === 'STUDENT_REAUTH_REQUIRED')
  assert.equal(calls, 1)
  setAccessToken(null)
})


test('PIN entry consent error stays local while a student resource revocation requires re-entry', async (t) => {
  setAccessToken('student-access', 'STUDENT')
  t.mock.method(globalThis, 'fetch', async () => json({ code: 'CHILD_NOT_LINKED', title: '법정대리인 동의 필요' }, 403))
  await assert.rejects(apiFetch('/auth/student/login', { method: 'POST', body: '{}' }),
    (e: { problem: { code: string } }) => e.problem.code === 'CHILD_NOT_LINKED')
  await assert.rejects(apiFetch('/students/me/home'),
    (e: { problem: { code: string } }) => e.problem.code === 'STUDENT_REAUTH_REQUIRED')
  setAccessToken(null)
})

test('child adapter preserves optional device metadata and consent access state together', async (t) => {
  setAccessToken('synthetic-parent', 'PARENT')
  t.mock.method(globalThis, 'fetch', async () => json({ items: [{ childId: 'child', nickname: '별명', grade: 3, birthYear: 2017,
    pinSet: true, pinLocked: false, guardianConsentRequired: true, hasRecords: null, recordState: 'CONSENT_REQUIRED' }] }))
  const [child] = await createApiGateway().children()
  assert.equal(child.pinSet, true); assert.equal(child.pinLocked, false)
  assert.equal(child.guardianConsentRequired, true); assert.equal(child.recordState, 'CONSENT_REQUIRED')
  assert.equal(child.plan, undefined)
  setAccessToken(null)
})
