import { apiFetch } from './apiClient.ts'
import { json } from './parent/api.ts'
import type { Consent } from '../domain/parent.ts'

export interface TransferRecipient { id: string; name: string | null; email: string; childCount: number }
export interface GuardianTransfer {
  id: string; childId: string; childName: string | null; senderName: string | null;
  recipientName: string | null; recipientEmail: string; direction: 'INCOMING' | 'OUTGOING';
  includeConversations: boolean; status: 'PENDING' | 'ACCEPTED' | 'REJECTED' | 'CANCELLED';
  createdAt: string; resolvedAt: string | null;
}
const key = encodeURIComponent
const proof = (body: unknown, token: string) => ({ ...json(body), headers: { 'Content-Type': 'application/json', 'X-Reauth-Token': token } })
export const guardianTransfers = {
  recipient: (email: string) => apiFetch<TransferRecipient>('/guardian-transfers/recipient', json({ email })),
  list: (signal?: AbortSignal) => apiFetch<{ items: GuardianTransfer[] }>('/guardian-transfers', { signal }),
  request: (body: { childId: string; recipientId: string; includeConversations: boolean }, token: string) =>
    apiFetch<GuardianTransfer>('/guardian-transfers', proof(body, token)),
  accept: (id: string, consents: Consent[], token: string) => apiFetch<GuardianTransfer>(`/guardian-transfers/${key(id)}/accept`, proof({ consents }, token)),
  reject: (id: string) => apiFetch<GuardianTransfer>(`/guardian-transfers/${key(id)}/reject`, json({})),
  cancel: (id: string) => apiFetch<GuardianTransfer>(`/guardian-transfers/${key(id)}/cancel`, json({})),
  cancelOutgoing: () => apiFetch<{ cancelled: number }>('/guardian-transfers/cancel-outgoing', json({})),
}
