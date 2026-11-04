import test, { before, after, beforeEach } from 'node:test'
import assert from 'node:assert/strict'
import { setupServer } from 'msw/node'
import type { Child } from '../src/domain/classroom.ts'
import { parentHandlers } from '../src/mocks/handlers/parent.ts'
import { studentHandlers } from '../src/mocks/handlers/student.ts'
import { serviceHandlers } from '../src/mocks/handlers/service.ts'
import { guardianTransferHandlers } from '../src/mocks/handlers/guardianTransfers.ts'
import { paymentHandlers } from '../src/mocks/handlers/payments.ts'
import { mockAccounts, mockAccountChildren, mockConsentHistory, setWorkspaceScenario } from '../src/mocks/fixtures/accounts.ts'
import { mockGuardianTransferConfig, mockTransfers, transferUnavailableChildren } from '../src/mocks/fixtures/guardianTransfers.ts'
import { conversations, conversationOwners } from '../src/mocks/fixtures/parent.ts'
import { deviceState } from '../src/mocks/fixtures/studentDevice.ts'
import { saveSharing } from '../src/mocks/fixtures/sharing.ts'

Object.defineProperty(globalThis, 'location', { value: new URL('http://localhost/'), configurable: true })
const server = setupServer(...guardianTransferHandlers, ...parentHandlers, ...serviceHandlers, ...paymentHandlers, ...studentHandlers)
const consents = [{ documentId: 'guardian-v1', version: '1.0', agreed: true }]
let token = '', sender = '', receiver = '', serial = 0
let child: Child
async function call(path: string, method = 'GET', body?: unknown, grant?: string) {
  const response = await fetch('http://localhost/api/v1' + path, { method,
    headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json', ...(grant ? { 'X-Reauth-Token': grant } : {}) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
  return { status: response.status, data: response.status === 204 ? null : await response.json(), headers: response.headers }
}
async function login(email: string) {
  const result = await call('/auth/login', 'POST', { email, password: 'demo-only' })
  assert.equal(result.status, 200)
  token = result.data.accessToken
}
async function proof(purpose: string, childId?: string) {
  const start = await call('/me/reauth', 'POST', { purpose, ...(childId ? { childId } : {}) })
  assert.equal(start.status, 200)
  assert.equal(typeof start.data.authorizationUrl, 'string')
  const finish = await call('/me/reauth', 'POST', { challengeId: start.data.challengeId })
  assert.equal(finish.status, 200)
  return finish.data.reauthToken as string
}
async function send(includeConversations = false) {
  const recipient = await call('/guardian-transfers/recipient', 'POST', { email: receiver })
  assert.equal(recipient.status, 200)
  const body = { childId: child.id, recipientId: recipient.data.id, includeConversations }
  const result = await call('/guardian-transfers', 'POST', body, await proof('CHILD_TRANSFER', child.id))
  assert.equal(result.status, 200)
  return { ...result, body }
}
before(() => server.listen({ onUnhandledFrame: 'error' }))
after(() => server.close())
beforeEach(async () => {
  sender = `sender-${++serial}@example.test`; receiver = `receiver-${serial}@example.test`
  child = { id: crypto.randomUUID(), nickname: '이관 자녀', grade: 5, birthYear: 2015, plan: 'FREE' }
  mockAccounts.add(sender); mockAccounts.add(receiver)
  mockAccountChildren.set(sender, [child]); mockAccountChildren.set(receiver, [])
  mockTransfers.clear(); transferUnavailableChildren.clear(); conversations.clear(); conversationOwners.clear()
  mockGuardianTransferConfig.enabled = true; setWorkspaceScenario('normal')
  await login(sender)
})

test('기본 꺼짐·필수 동의·역할·수신자 이메일 및 3명 한도 계약', async () => {
  mockGuardianTransferConfig.enabled = false
  assert.equal((await call('/guardian-transfers')).status, 404)
  mockGuardianTransferConfig.enabled = true
  assert.equal((await call('/guardian-transfers/recipient', 'POST', { email: sender })).status, 400)
  for (const email of ['missing@example.test', 'admin@example.test']) {
    const r = await call('/guardian-transfers/recipient', 'POST', { email })
    assert.equal(r.status, 404); assert.equal(r.data.code, 'TRANSFER_RECIPIENT_NOT_FOUND')
  }
  const full = await call('/guardian-transfers/recipient', 'POST', { email: 'full@example.test' })
  assert.equal(full.data.code, 'CHILD_LIMIT_REACHED')
  mockConsentHistory.set(sender, [])
  assert.equal((await call('/guardian-transfers')).data.code, 'CONSENT_REQUIRED')
  mockConsentHistory.delete(sender)
  await login('admin@example.test')
  assert.equal((await call('/guardian-transfers')).status, 403)
})

test('두 이관 목적은 Google 재인증·자녀 범위·세션 및 1회 사용을 검사한다', async () => {
  assert.equal((await call('/me/reauth', 'POST', { purpose: 'CHILD_TRANSFER' })).status, 400)
  assert.equal((await call('/me/reauth', 'POST', { purpose: 'TRANSFER_ACCEPT', childId: child.id })).status, 400)
  assert.equal((await call('/me/reauth', 'POST', { purpose: 'CHILD_TRANSFER', childId: child.id, scope: 'PROFILE' })).status, 400)
  const recipient = (await call('/guardian-transfers/recipient', 'POST', { email: receiver })).data
  const body = { childId: child.id, recipientId: recipient.id }
  const wrong = await proof('TRANSFER_ACCEPT')
  assert.equal((await call('/guardian-transfers', 'POST', body, wrong)).data.code, 'REAUTH_REQUIRED')
  const grant = await proof('CHILD_TRANSFER', child.id)
  const request = await call('/guardian-transfers', 'POST', body, grant)
  assert.equal(request.status, 200)
  assert.equal((await call('/guardian-transfers', 'POST', body, grant)).data.id, request.data.id)
  await call(`/guardian-transfers/${request.data.id}/cancel`, 'POST', {})
  assert.equal((await call('/guardian-transfers', 'POST', body, grant)).data.code, 'REAUTH_REQUIRED')
  const oldSessionGrant = await proof('CHILD_TRANSFER', child.id)
  await login(sender)
  assert.equal((await call('/guardian-transfers', 'POST', body, oldSessionGrant)).data.code, 'REAUTH_REQUIRED')
})

test('대기 중 탈퇴·해제·삭제 차단, 본인 취소·거절과 종료 상태 멱등성', async () => {
  const sent = await send()
  assert.equal(sent.headers.get('Cache-Control'), 'no-store')
  const id = sent.data.id
  assert.equal((await call(`/children/${child.id}/link`, 'DELETE')).data.code, 'TRANSFER_PENDING')
  assert.equal((await call(`/children/${child.id}/deletion-requests`, 'POST', { scope: 'PROFILE' })).data.code, 'TRANSFER_PENDING')
  assert.equal((await call('/me/withdrawal', 'POST', {})).data.code, 'TRANSFER_PENDING')
  assert.equal((await call('/guardian-transfers', 'POST', { ...sent.body, includeConversations: true })).data.code, 'TRANSFER_PENDING')
  assert.equal((await call(`/guardian-transfers/${id}/accept`, 'POST', { consents })).status, 403)
  await login('spare@example.test')
  assert.deepEqual((await call('/guardian-transfers')).data.items, [])
  assert.equal((await call(`/guardian-transfers/${id}/cancel`, 'POST', {})).status, 404)
  await login(receiver)
  assert.equal((await call(`/guardian-transfers/${id}/cancel`, 'POST', {})).status, 403)
  assert.equal((await call(`/guardian-transfers/${id}/reject`, 'POST', {})).data.status, 'REJECTED')
  assert.equal((await call(`/guardian-transfers/${id}/reject`, 'POST', {})).data.status, 'REJECTED')
  await login(sender)
  assert.equal((await call(`/guardian-transfers/${id}/cancel`, 'POST', {})).data.code, 'TRANSFER_ALREADY_RESOLVED')
  const next = await send()
  // #307 미해결 조건도 현재 core처럼 유지한다.
  mockGuardianTransferConfig.enabled = false
  assert.equal((await call(`/guardian-transfers/${next.data.id}/cancel`, 'POST', {})).status, 404)
  assert.equal((await call('/me/withdrawal', 'POST', {})).data.code, 'TRANSFER_PENDING')
  mockGuardianTransferConfig.enabled = true
  assert.equal((await call('/guardian-transfers/cancel-outgoing', 'POST', {})).data.cancelled, 1)
  assert.equal((await call('/guardian-transfers/cancel-outgoing', 'POST', {})).data.cancelled, 0)
  assert.equal((await call(`/guardian-transfers/${next.data.id}/cancel`, 'POST', {})).data.status, 'CANCELLED')
  assert.equal((await call('/children')).data.items.length, 1)
})

for (const include of [false, true]) test(`자녀 없는 수신자 수락, 단일 연결·동의·대화 선택(${include})·기기 해제`, async () => {
  saveSharing(child.id, true)
  conversations.set('conversation', { conversationId: 'conversation', childId: child.id, title: '상담', period: { from: '2026-11-01', to: '2026-11-02' }, createdAt: new Date().toISOString(), messages: [] })
  conversationOwners.set('conversation', sender)
  deviceState.devices.push({ deviceId: 'transfer-device', owner: sender, childIds: [child.id], label: '기기', createdAt: '', lastUsedAt: null, expiresAt: '', revokedAt: null })
  const sent = await send(include)
  await login(receiver)
  assert.deepEqual((await call('/children')).data.items, [])
  assert.equal((await call(`/children/${child.id}/summary`)).status, 403)
  assert.equal((await call('/guardian-transfers')).data.items[0].direction, 'INCOMING')
  const grant = await proof('TRANSFER_ACCEPT')
  const path = `/guardian-transfers/${sent.data.id}/accept`
  assert.equal((await call(path, 'POST', { consents: [{ ...consents[0], version: 'stale' }] }, grant)).data.code, 'CONSENT_DOCUMENT_CHANGED')
  assert.equal((await call('/children')).data.items.length, 0)
  const accepted = await call(path, 'POST', { consents }, grant)
  assert.equal(accepted.data.status, 'ACCEPTED')
  assert.equal((await call(path, 'POST', { consents })).data.status, 'ACCEPTED')
  assert.equal((await call('/children')).data.items[0].id, child.id)
  assert.equal(mockAccountChildren.get(sender)!.length, 0)
  assert.ok(mockConsentHistory.get(receiver)!.some(c => c.studentId === child.id && c.agreed))
  assert.ok(deviceState.devices.every(d => !d.childIds.includes(child.id)))
  assert.equal((await call(`/conversations?childId=${child.id}`)).data.items.length, include ? 1 : 0)
  assert.equal((await call('/conversations/conversation')).status, include ? 200 : 404)
  await login(sender)
  assert.equal((await call('/guardian-transfers')).data.items[0].childName, null)
  assert.equal((await call(`/children/${child.id}/summary`)).status, 403)
})

test('수락 시 3명 한도·자녀 상태·실행 중 분석을 재검사하고 실패 시 요청을 유지한다', async () => {
  const sent = await send()
  await login(receiver)
  const path = `/guardian-transfers/${sent.data.id}/accept`
  transferUnavailableChildren.add(child.id)
  assert.equal((await call(path, 'POST', { consents })).data.code, 'TRANSFER_CHILD_UNAVAILABLE')
  transferUnavailableChildren.clear()
  conversations.set('running', { conversationId: 'running', childId: child.id, title: '', period: { from: '', to: '' }, createdAt: '', messages: [{ messageId: 'm', question: 'q', status: 'RUNNING', scope: { childId: child.id, from: '', to: '' } }] })
  assert.equal((await call(path, 'POST', { consents })).data.code, 'TRANSFER_ACTIVITY_IN_PROGRESS')
  conversations.clear()
  mockAccountChildren.set(receiver, Array.from({ length: 3 }, () => ({ ...child, id: crypto.randomUUID() })))
  await login(receiver)
  assert.equal((await call(path, 'POST', { consents })).data.code, 'CHILD_LIMIT_REACHED')
  assert.equal(mockTransfers.get(sent.data.id)!.status, 'PENDING')
  assert.equal(mockAccountChildren.get(sender)![0].id, child.id)
})

test('기존 결제 fixture의 구독 및 결제 확인 중 상태를 요청·수락에 반영한다', async () => {
  const sent = await send()
  const products = await call('/products')
  const premium = products.data.items.find((p: { code: string }) => p.code === 'PREMIUM')
  assert.ok(premium)
  // PG 확인 중 상태는 기존 payment-scenario를 통해 만든다.
  const orderResponse = await fetch('http://localhost/api/v1/orders', { method: 'POST', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ childId: child.id, productId: premium.id }) })
  const order = await orderResponse.json()
  assert.equal(orderResponse.status, 201)
  setWorkspaceScenario('payment-confirming')
  const paymentResponse = await fetch('http://localhost/api/v1/payments/confirm', { method: 'POST', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ orderId: order.orderId, paymentKey: 'mock-payment-' + order.orderId, amount: order.amount }) })
  assert.equal(paymentResponse.status, 202)
  setWorkspaceScenario('normal')
  await login(receiver)
  assert.equal((await call(`/guardian-transfers/${sent.data.id}/accept`, 'POST', { consents })).data.code, 'TRANSFER_PAYMENT_BLOCKED')
  await login(sender)
  await call(`/payments/${order.orderId}`) // 기존 목업의 PG 확인 완료 → ACTIVE 구독
  assert.equal((await call('/guardian-transfers', 'POST', sent.body)).data.code, 'WITHDRAWAL_BLOCKED')
})
