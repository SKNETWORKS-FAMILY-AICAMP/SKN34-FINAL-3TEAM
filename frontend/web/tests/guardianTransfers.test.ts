import test from 'node:test'
import assert from 'node:assert/strict'
import { guardianTransfers } from '../src/data/guardianTransfers.ts'
import { ApiError, setAccessToken } from '../src/data/apiClient.ts'
import type { GuardianTransfer } from '../src/data/guardianTransfers.ts'

// core GuardianTransferController / OpenAPI #289. HTTP 대역이며 실제 자녀를 이관하지 않는다.
const transfer: GuardianTransfer = {
  id: 'transfer-1', childId: 'child-1', childName: null, senderName: null,
  recipientName: null, recipientEmail: 'recipient@example.test', direction: 'OUTGOING',
  includeConversations: false, status: 'PENDING', createdAt: '2026-11-03T00:00:00Z', resolvedAt: null,
}

test('이관 대상 조회·목록은 공개 경로·POST/GET·취소 신호와 null 이름을 유지한다', async t => {
  setAccessToken('synthetic-parent', 'PARENT'); t.after(() => setAccessToken(null))
  const requests: { url: string; init: RequestInit }[] = []
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    requests.push({ url, init })
    return Response.json(url.endsWith('/recipient')
      ? { id: 'recipient-1', name: null, email: 'recipient@example.test', childCount: 0 }
      : { items: [transfer] })
  })
  const recipient = await guardianTransfers.recipient('recipient@example.test')
  const controller = new AbortController()
  assert.deepEqual(await guardianTransfers.list(controller.signal), { items: [transfer] })
  assert.equal(recipient.name, null)
  assert.deepEqual(requests.map(r => r.url), ['/api/v1/guardian-transfers/recipient', '/api/v1/guardian-transfers'])
  assert.equal(requests[0].init.method, 'POST')
  assert.deepEqual(JSON.parse(String(requests[0].init.body)), { email: 'recipient@example.test' })
  assert.equal(requests[1].init.method ?? 'GET', 'GET')
  assert.equal(requests[1].init.signal, controller.signal)
  assert.equal(requests[1].init.body, undefined)
})

test('이관 요청·수락만 재인증 토큰을 보내고 대화 미포함 false·동의 버전을 보존한다', async t => {
  setAccessToken('synthetic-parent', 'PARENT'); t.after(() => setAccessToken(null))
  const requests: { url: string; init: RequestInit }[] = []
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    requests.push({ url, init }); return Response.json(transfer)
  })
  const body = { childId: 'child-1', recipientId: 'recipient-1', includeConversations: false }
  const consents = [{ documentId: 'guardian-document', version: '2026-11-03', agreed: true }]
  await guardianTransfers.request(body, 'create-proof')
  await guardianTransfers.accept('transfer/id', consents, 'accept-proof')
  await guardianTransfers.reject('transfer/id')
  await guardianTransfers.cancel('transfer/id')
  assert.deepEqual(requests.map(r => r.url), [
    '/api/v1/guardian-transfers', '/api/v1/guardian-transfers/transfer%2Fid/accept',
    '/api/v1/guardian-transfers/transfer%2Fid/reject', '/api/v1/guardian-transfers/transfer%2Fid/cancel',
  ])
  assert.deepEqual(requests.map(r => JSON.parse(String(r.init.body))), [body, { consents }, {}, {}])
  assert.deepEqual(requests.map(r => new Headers(r.init.headers).get('X-Reauth-Token')), ['create-proof', 'accept-proof', null, null])
  for (const request of requests) {
    assert.equal(request.init.method, 'POST')
    assert.equal(new Headers(request.init.headers).get('Authorization'), 'Bearer synthetic-parent')
    assert.equal(new Headers(request.init.headers).get('Content-Type'), 'application/json')
  }
})

test('탈퇴 전 발신 이관 일괄 취소는 POST이며 접수 건수를 변경하지 않는다', async t => {
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    assert.equal(url, '/api/v1/guardian-transfers/cancel-outgoing')
    assert.equal(init.method, 'POST')
    assert.deepEqual(JSON.parse(String(init.body)), {})
    assert.equal(new Headers(init.headers).get('X-Reauth-Token'), null)
    return Response.json({ cancelled: 2 })
  })
  assert.deepEqual(await guardianTransfers.cancelOutgoing(), { cancelled: 2 })
})

test('비활성 이관 404·이미 처리된 요청 409는 refresh나 성공 대체 없이 전달한다', async t => {
  setAccessToken('synthetic-parent', 'PARENT'); t.after(() => setAccessToken(null))
  let calls = 0
  t.mock.method(globalThis, 'fetch', async () => {
    calls++
    const status = calls === 1 ? 404 : 409
    return Response.json({ status, code: status === 404 ? 'NOT_FOUND' : 'TRANSFER_ALREADY_RESOLVED', title: '이관 요청 거부' }, { status })
  })
  await assert.rejects(guardianTransfers.list(), e => e instanceof ApiError && e.problem.status === 404)
  await assert.rejects(guardianTransfers.accept('transfer-1', [], 'proof'), e =>
    e instanceof ApiError && e.problem.status === 409 && e.problem.code === 'TRANSFER_ALREADY_RESOLVED')
  assert.equal(calls, 2)
})
