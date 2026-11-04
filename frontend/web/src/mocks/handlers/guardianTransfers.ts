import { http } from 'msw/http'
import type { GuardianTransfer } from '../../data/guardianTransfers.ts'
import type { Consent } from '../../domain/parent.ts'
import { mockAccounts, mockConsentHistory, mockIdentity, permissionsFor } from '../fixtures/accounts.ts'
import { conversations, conversationOwners } from '../fixtures/parent.ts'
import { deviceState, persistDeviceState } from '../fixtures/studentDevice.ts'
import { mockGuardianTransferConfig, mockTransfers, transferAccountId, transferChildren,
  replaceTransferChildren, transferUnavailableChildren, type MockTransfer } from '../fixtures/guardianTransfers.ts'
import { parentGuard, fail, consumeActionReauth, consentCheck, consentRows, fixtureConsent, docs } from './parent.ts'
import { respond } from './student.ts'
import { requireMockTransferPaymentReady } from './payments.ts'

function transferGuard(request: Request) {
  if (!mockGuardianTransferConfig.enabled) fail('NOT_FOUND', '이관 기능이 비활성입니다.', 404)
  // 현재 core와 같이 조회·거절·취소도 필수 동의 검사. #307 정책은 변경하지 않는다.
  parentGuard(request)
}
async function reply(request: Request, action: () => Promise<unknown>) {
  const response = await respond(async () => { transferGuard(request); return action() })
  response.headers.set('Cache-Control', 'no-store')
  return response
}
function capacity(email: string) {
  if (transferChildren(email).length >= 3) fail('CHILD_LIMIT_REACHED', '해당 학부모는 자녀 등록 한도(3명)에 도달하여 이관받을 수 없습니다.', 409)
}
function childAvailable(childId: string) {
  if (transferUnavailableChildren.has(childId)) fail('TRANSFER_CHILD_UNAVAILABLE', '삭제 중이거나 이용할 수 없는 자녀입니다.', 409)
}
function view(row: MockTransfer): GuardianTransfer {
  const { sender, recipient, ...data } = row
  const linked = transferChildren(mockIdentity.email).some(c => c.id === row.childId)
  return { ...data, childName: linked || (row.status === 'PENDING' && recipient === mockIdentity.email) ? row.childName : null,
    direction: sender === mockIdentity.email ? 'OUTGOING' : 'INCOMING' }
}
function owned(id: string, role: 'sender' | 'recipient') {
  const row = mockTransfers.get(id)
  if (!row || ![row.sender, row.recipient].includes(mockIdentity.email)) return fail('NOT_FOUND', '이관 요청을 확인할 수 없습니다.', 404)
  if (row[role] !== mockIdentity.email) fail('FORBIDDEN', '본인의 이관 요청만 처리할 수 있습니다.', 403)
  return row
}
function pending(row: MockTransfer) {
  if (row.status !== 'PENDING') fail('TRANSFER_ALREADY_RESOLVED', '이미 처리된 이관 요청입니다. 상태를 새로 확인해 주세요.', 409)
}
function resolve(row: MockTransfer, status: MockTransfer['status']) {
  row.status = status
  row.resolvedAt = new Date().toISOString()
  return view(row)
}

export const guardianTransferHandlers = [
  http.post('/api/v1/guardian-transfers/recipient', ({ request }) => reply(request, async () => {
    const { email } = await request.json() as { email?: unknown }
    if (typeof email !== 'string' || email.trim().length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()))
      return fail('VALIDATION_FAILED', '가입 이메일을 확인해 주세요.')
    const matches = [...mockAccounts].filter(candidate => candidate.toLowerCase() === email.trim().toLowerCase() && !permissionsFor(candidate).length)
    if (matches.length !== 1) return fail('TRANSFER_RECIPIENT_NOT_FOUND', '가입한 학부모 이메일을 확인해 주세요.', 404)
    const recipient = matches[0]
    if (recipient === mockIdentity.email) fail('VALIDATION_FAILED', '본인에게 이관할 수 없습니다.')
    capacity(recipient)
    return { id: transferAccountId(recipient), name: recipient.split('@')[0], email: recipient, childCount: transferChildren(recipient).length }
  })),
  http.get('/api/v1/guardian-transfers', ({ request }) => reply(request, async () => ({
    items: [...mockTransfers.values()].filter(row => [row.sender, row.recipient].includes(mockIdentity.email)).reverse().map(view),
  }))),
  http.post('/api/v1/guardian-transfers', ({ request }) => reply(request, async () => {
    const { childId, recipientId, includeConversations = false } = await request.json() as { childId: string; recipientId: string; includeConversations?: boolean }
    if (typeof childId !== 'string' || typeof recipientId !== 'string' || typeof includeConversations !== 'boolean') fail('VALIDATION_FAILED', '이관 대상과 대화 포함 여부를 확인해 주세요.')
    const sender = mockIdentity.email
    const recipient = [...mockAccounts].find(email => transferAccountId(email) === recipientId && !permissionsFor(email).length)
    if (!recipient) return fail('NOT_FOUND', '받는 학부모를 확인할 수 없습니다.', 404)
    if (sender === recipient) fail('VALIDATION_FAILED', '본인에게 이관할 수 없습니다.')
    childAvailable(childId)
    const child = transferChildren(sender).find(c => c.id === childId)
    if (!child) return fail('CHILD_NOT_LINKED', '현재 연결된 자녀만 이관할 수 있습니다.', 403)
    capacity(recipient)
    requireMockTransferPaymentReady(sender, childId)
    const previous = [...mockTransfers.values()].find(row => row.childId === childId && row.status === 'PENDING')
    if (previous) {
      if (previous.sender === sender && previous.recipient === recipient && previous.includeConversations === includeConversations) return view(previous)
      return fail('TRANSFER_PENDING', '이미 진행 중인 이관 요청이 있습니다.', 409)
    }
    consumeActionReauth(request, 'CHILD_TRANSFER', childId)
    const row: MockTransfer = { id: crypto.randomUUID(), childId, childName: child.nickname, sender, recipient,
      senderName: mockIdentity.name, recipientName: recipient.split('@')[0], recipientEmail: recipient,
      includeConversations, status: 'PENDING', createdAt: new Date().toISOString(), resolvedAt: null }
    mockTransfers.set(row.id, row)
    return view(row)
  })),
  http.post('/api/v1/guardian-transfers/:id/accept', ({ request, params }) => reply(request, async () => {
    const { consents } = await request.json() as { consents: Consent[] }
    const history = await consentRows()
    // 마지막 비동기 읽기 이후 현재 상태를 재검사하고, 변경은 동기적으로 완료한다.
    const row = owned(String(params.id), 'recipient')
    childAvailable(row.childId)
    if (row.status === 'ACCEPTED') return view(row)
    pending(row)
    const child = transferChildren(row.sender).find(c => c.id === row.childId)
    if (!child) return fail('CHILD_NOT_LINKED', '발신자의 현재 자녀 연결을 확인해 주세요.', 403)
    capacity(row.recipient)
    requireMockTransferPaymentReady(row.sender, row.childId)
    const senderConversations = [...conversations.values()].filter(c => c.childId === row.childId && (conversationOwners.get(c.conversationId) ?? row.sender) === row.sender)
    if (senderConversations.some(c => c.messages.some(m => m.status === 'RUNNING')))
      fail('TRANSFER_ACTIVITY_IN_PROGRESS', '분석 상담이 끝난 뒤 이관을 수락해 주세요.', 409)
    // 모든 검사가 끝난 뒤 한 번에 상태 변경. 실패 시 연결·동의·grant를 유지한다.
    if (!Array.isArray(consents) || new Set(consents.map(c => c.documentId)).size !== consents.length)
      fail('VALIDATION_FAILED', '동의 항목을 확인해 주세요.')
    if (consents.some(c => !docs.some(d => d.kind === 'GUARDIAN' && c.documentId === d.documentId && c.version === d.version)))
      fail('CONSENT_DOCUMENT_CHANGED', '현재 법정대리인 동의 문서를 다시 확인해 주세요.', 409)
    consentCheck(consents, true)
    consumeActionReauth(request, 'TRANSFER_ACCEPT')
    replaceTransferChildren(row.sender, transferChildren(row.sender).filter(c => c.id !== child.id))
    replaceTransferChildren(row.recipient, [...transferChildren(row.recipient), child])
    history.unshift(fixtureConsent(docs.find(d => d.kind === 'GUARDIAN')!, child.id))
    mockConsentHistory.set(row.recipient, history)
    for (const c of senderConversations) conversationOwners.set(c.conversationId, row.includeConversations ? row.recipient : row.sender)
    for (const device of deviceState.devices) device.childIds = device.childIds.filter(id => id !== child.id)
    for (const [code, pairing] of Object.entries(deviceState.pairings)) if (pairing.children.some(c => c.id === child.id)) delete deviceState.pairings[code]
    persistDeviceState()
    return resolve(row, 'ACCEPTED')
  })),
  ...(['reject', 'cancel'] as const).map(action => http.post(`/api/v1/guardian-transfers/:id/${action}`, ({ request, params }) => reply(request, async () => {
    const row = owned(String(params.id), action === 'reject' ? 'recipient' : 'sender')
    const target = action === 'reject' ? 'REJECTED' : 'CANCELLED'
    if (row.status === target) return view(row)
    pending(row)
    return resolve(row, target)
  }))),
  http.post('/api/v1/guardian-transfers/cancel-outgoing', ({ request }) => reply(request, async () => {
    const rows = [...mockTransfers.values()].filter(row => row.sender === mockIdentity.email && row.status === 'PENDING')
    for (const row of rows) resolve(row, 'CANCELLED')
    return { cancelled: rows.length }
  })),
]
