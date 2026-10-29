import { apiFetch, ApiError } from '../apiClient.ts'
import { recordDto } from '../recordDto.ts'
import { streamSse } from '../sse.ts'
import { reduceAnalysis } from '../../domain/parent.ts'
import type { Child, Period, PublicAttempt } from '../../domain/classroom.ts'
import type {
  Consent,
  ConsentDocument,
  ConsentHistory,
  Page,
  Scope,
  Summary,
  ThinkingResponse,
  RecordPage,
  Conversation,
  StreamState,
  Evidence,
  ReportItem,
  WeeklyReport,
} from '../../domain/parent.ts'
export const json = (data: unknown, method = 'POST'): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(data),
})
export const scopeQuery = (scope: Scope) =>
  new URLSearchParams({ childId: scope.childId, from: scope.from, to: scope.to }).toString()
const range = (p: Period) => new URLSearchParams({ from: p.from, to: p.to }).toString()
const item = (id: string) => encodeURIComponent(id)
function assertChild<T extends { childId: string }>(r: T, scope: Scope): T {
  if (r.childId !== scope.childId) throw new Error('선택한 자녀와 응답 범위가 다릅니다.')
  return r
}
export const parentApi = {
  documents: (signal?: AbortSignal) =>
    apiFetch<Page<ConsentDocument>>('/consent-documents', { signal }),
  saveConsents: (data: { consents: Consent[]; childId?: string }) =>
    apiFetch<Page<ConsentHistory>>('/me/consents', json(data)),
  consentHistory: (signal?: AbortSignal) => apiFetch<Page<ConsentHistory>>('/me/consents', { signal }),
  withdrawConsent: (id: string) => apiFetch<ConsentHistory>(`/me/consents/${item(id)}/withdrawal`, json({})),
  children: (signal?: AbortSignal) => apiFetch<Page<Child>>('/children', { signal }),
  register: (data: { nickname: string; grade: number; birthYear: number; consents: Consent[] }) =>
    apiFetch<Child>('/children', json(data)),
  me: () => apiFetch<{ userId: string; name: string; email: string; role: string }>('/me'),
  updateMe: (name: string) => apiFetch('/me', json({ name }, 'PATCH')),
  updateChild: (id: string, data: { nickname: string; grade: number }) =>
    apiFetch<Child>(`/children/${item(id)}`, json(data, 'PATCH')),
  async summary(scope: Scope, signal?: AbortSignal) {
    return assertChild(
      await apiFetch<Summary>(`/children/${item(scope.childId)}/summary?${range(scope)}`, {
        signal,
      }),
      scope,
    )
  },
  async thinking(scope: Scope, signal?: AbortSignal) {
    return assertChild(
      await apiFetch<ThinkingResponse>(
        `/children/${item(scope.childId)}/thinking-types?${range(scope)}`,
        { signal },
      ),
      scope,
    )
  },
  async records(scope: Scope, signal?: AbortSignal, page = 0) {
    const result = assertChild(
      await apiFetch<RecordPage>(`/children/${item(scope.childId)}/attempts?${range(scope)}&page=${page}&size=20`, {
        signal,
      }),
      scope,
    )
    return { ...result, items: result.items.map((row) => recordDto(row, scope.childId)) }
  },
  async record(childId: string, id: string, signal?: AbortSignal, period?: Period) {
    const result = await apiFetch<PublicAttempt & { state: import('../../domain/queryState.ts').QueryState; period: Period }>(
      `/children/${item(childId)}/attempts/${item(id)}${period ? `?${range(period)}` : ''}`, { signal })
    return { ...result, ...recordDto(result, childId) }
  },
  conversations: (childId: string, signal?: AbortSignal) =>
    apiFetch<Page<Conversation>>(`/conversations?childId=${item(childId)}`, { signal }),
  conversation: (id: string, signal?: AbortSignal) =>
    apiFetch<Conversation>(`/conversations/${item(id)}`, { signal }),
  create: (scope: Scope) => apiFetch<Conversation>('/conversations', json(scope)),
  async message(
    id: string,
    question: string,
    scope: Scope,
    notify: (s: StreamState) => void,
    signal: AbortSignal,
    retryId?: string,
  ) {
    let state: StreamState = { phase: 'RUNNING', temporary: '' }
    try {
      await streamSse(
        `/conversations/${item(id)}/messages${retryId ? `/${item(retryId)}/retry` : ''}`,
        {
          body: { question, scope },
          signal,
          onEvent(event) {
            if (
              event.event === 'result' &&
              (event.data as { scope?: Scope }).scope?.childId !== scope.childId
            )
              throw new Error('분석 결과의 자녀 범위가 다릅니다.')
            state = reduceAnalysis(state, event)
            notify(state)
            if (event.event === 'error')
              throw new ApiError(event.data as ConstructorParameters<typeof ApiError>[0])
          },
        },
      )
      if (!['DONE', 'CLARIFICATION'].includes(state.phase))
        throw new ApiError({
          status: 503,
          code: 'STREAM_INTERRUPTED',
          title: '확정 결과를 받지 못했습니다.',
          retryable: true,
        })
      return state
    } catch (e) {
      notify({ ...state, phase: 'FAILED', temporary: '', result: undefined })
      throw e
    }
  },
  messageEvidence: (id: string, messageId: string, signal?: AbortSignal) =>
    apiFetch<{ items: Evidence[] }>(
      `/conversations/${item(id)}/messages/${item(messageId)}/evidence`,
      { signal },
    ),
  reports: (childId: string, status: string, signal?: AbortSignal) =>
    apiFetch<Page<ReportItem>>(
      `/children/${item(childId)}/reports${status ? `?status=${item(status)}` : ''}`,
      { signal },
    ),
  async report(id: string, childId: string, revision?: number, signal?: AbortSignal) {
    const r = await apiFetch<WeeklyReport>(
      `/reports/${item(id)}${revision ? `?revision=${revision}` : ''}`,
      { signal },
    )
    if (r.childId !== childId) throw new Error('리포트 자녀 범위가 다릅니다.')
    if (
      r.status === 'COMPLETED' &&
      r.narrative &&
      (!r.verification?.numbersMatched || !r.verification.quotesMatched)
    )
      throw new Error('검증되지 않은 요약은 표시하지 않습니다.')
    return r
  },
  reportEvidence: (id: string, itemId: string, signal?: AbortSignal) =>
    apiFetch<{ items: Evidence[] }>(`/reports/${item(id)}/evidence/${item(itemId)}`, { signal }),
  download: (id: string, format: 'pdf' | 'md') =>
    apiFetch<{ url: string; expiresAt: string }>(`/reports/${item(id)}/download?format=${format}`),
  regenerate: (id: string) => apiFetch(`/reports/${item(id)}/regenerate`, json({})),
}
