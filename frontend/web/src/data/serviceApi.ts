import { apiFetch } from './apiClient.ts'
import { json } from './parent/api.ts'
import type { Page } from '../domain/parent.ts'
import type { SupportCase, SupportTarget, Notice, NotificationItem, NotificationSettings, ReauthPurpose, DeletionScope, DeletionRequest } from '../domain/service.ts'
const id = encodeURIComponent
export const serviceApi = {
  help: (role: string, signal?: AbortSignal) => apiFetch<{ items: { id: string; title: string; content: string }[] }>(`/help?role=${id(role)}`, { signal }),
  notices: (signal?: AbortSignal) => apiFetch<{ items: Notice[] }>('/notices', { signal }),
  cases: (kind: 'error-reports' | 'inquiries', signal?: AbortSignal) => apiFetch<Page<SupportCase>>('/' + kind, { signal }),
  createCase: (kind: 'error-reports' | 'inquiries', data: { targetType?: SupportTarget; targetId?: string; category: string; comment: string }) => apiFetch<SupportCase>('/' + kind, json(data)),
  adminInquiries: (signal?: AbortSignal) => apiFetch<{ items:SupportCase[] }>('/admin/inquiries',{signal}),
  answerInquiry: (key:string,answer:string) => apiFetch<SupportCase>(`/admin/inquiries/${id(key)}`,json({answer,status:'RESOLVED'},'PATCH')),
  publishNotice: (data:Omit<Notice,'id'>) => apiFetch<Notice>('/admin/notices',json(data)),
  notifications: (unreadOnly: boolean, page: number, signal?: AbortSignal) => apiFetch<{ items: NotificationItem[]; page: number; size: number; hasNext: boolean }>(`/notifications?unreadOnly=${unreadOnly}&page=${page}&size=20`, { signal }),
  read: (key: string) => apiFetch<void>(`/notifications/${id(key)}/read`, json({}, 'PATCH')),
  readAll: () => apiFetch<void>('/notifications/read-all', json({})),
  settings: (signal?: AbortSignal) => apiFetch<NotificationSettings>('/notification-settings', { signal }),
  saveSettings: (data: NotificationSettings) => apiFetch<NotificationSettings>('/notification-settings', json(data, 'PUT')),
  startReauth: (data: { purpose: ReauthPurpose; childId?: string; scope?: DeletionScope }) => apiFetch<{ challengeId: string; authorizationUrl: string; expiresAt: string }>('/me/reauth', json(data)),
  finishReauth: (challengeId: string) => apiFetch<{ reauthToken: string; expiresAt: string }>('/me/reauth', json({ challengeId })),
  impact: (childId: string, signal?: AbortSignal) => apiFetch<{ childId: string; actions: { scope: string; effect: string }[]; retainedTransactionsYears: number; deviceCleanupPending: boolean }>(`/children/${id(childId)}/deletion-impact`, { signal }),
  unlink: (childId: string, token: string) => apiFetch<void>(`/children/${id(childId)}/link`, { method: 'DELETE', headers: { 'X-Reauth-Token': token } }),
  deleteChild: (childId: string, scope: DeletionScope, token: string) => apiFetch<DeletionRequest>(`/children/${id(childId)}/deletion-requests`, { ...json({ scope }), headers: { 'Content-Type': 'application/json', 'X-Reauth-Token': token } }),
  deletion: (childId: string, requestId: string) => apiFetch<DeletionRequest>(`/children/${id(childId)}/deletion-requests/${id(requestId)}`),
  precheck: () => apiFetch<{ canWithdraw: boolean; activeSubscriptions: number; unresolvedRefunds: number; retainedTransactionsYears: number }>('/me/withdrawal/precheck'),
  withdraw: (token: string) => apiFetch<{ withdrawalRequestId: string; status: string; statusToken: string }>('/me/withdrawal', { ...json({}), headers: { 'Content-Type': 'application/json', 'X-Reauth-Token': token } }),
  withdrawal: (token: string) => apiFetch<{ withdrawalRequestId: string; status: string }>('/me/withdrawal', { headers: { 'X-Withdrawal-Status-Token': token } }),
}
