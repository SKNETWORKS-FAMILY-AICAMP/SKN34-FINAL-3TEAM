import { apiFetch } from '../apiClient.ts'
import { json } from '../parent/api.ts'
import type { Page } from '../../domain/parent.ts'
import type { Mission, Period } from '../../domain/classroom.ts'
import type {
  AdminMission,
  Audit,
  Job,
  ModelVersion,
  Overview,
  Rubric,
  MissionVersion,
  ErrorReport,
  Usage,
} from '../../domain/admin/operations.ts'
const p = (id: string) => encodeURIComponent(id)
export const adminApi = {
  overview: (period: Period, signal?: AbortSignal) =>
    apiFetch<Overview>(`/admin/overview?${new URLSearchParams({ ...period })}`, { signal }),
  jobs: (type: string, status: string, signal?: AbortSignal, period?: Period) =>
    apiFetch<Page<Job>>(`/admin/jobs?${new URLSearchParams({ type, status, ...period })}`, {
      signal,
    }),
  job: (id: string, signal?: AbortSignal) => apiFetch<Job>(`/admin/jobs/${p(id)}`, { signal }),
  retry: (id: string, key: string) =>
    apiFetch<Job>(`/admin/jobs/${p(id)}/retry`, {
      ...json({}),
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
    }),
  queues: (signal?: AbortSignal) =>
    apiFetch<{ items: { name: string; length: number; dlq: number }[] }>('/admin/queues', {
      signal,
    }),
  audits: (period: Period, targetType: string, signal?: AbortSignal) =>
    apiFetch<Page<Audit>>(`/admin/audit-logs?${new URLSearchParams({ ...period, targetType })}`, {
      signal,
    }),
  missions: (filters: Record<string, string>, signal?: AbortSignal) =>
    apiFetch<Page<AdminMission> & { counts: Overview['missionCounts'] }>(
      `/admin/missions?${new URLSearchParams(filters)}`,
      { signal },
    ),
  mission: (id: string, signal?: AbortSignal) =>
    apiFetch<AdminMission>(`/admin/missions/${p(id)}`, { signal }),
  save: (
    data: Omit<MissionVersion, 'version' | 'createdAt'> & { demoOnly: boolean },
    id?: string,
  ) =>
    apiFetch<AdminMission>(
      `/admin/missions${id ? `/${p(id)}` : ''}`,
      json(data, id ? 'PATCH' : 'POST'),
    ),
  rubric: (id: string, data: Omit<Rubric, 'version'>) =>
    apiFetch<AdminMission>(`/admin/missions/${p(id)}/rubric`, json(data, 'PUT')),
  preview: (id: string, signal?: AbortSignal) =>
    apiFetch<{ mission: Mission; missionVersion: number; rubricVersion: number | null }>(
      `/admin/missions/${p(id)}/preview`,
      { signal },
    ),
  action: (id: string, action: string, data: unknown = {}) =>
    apiFetch<AdminMission>(`/admin/missions/${p(id)}/${action}`, json(data)),
  models: (signal?: AbortSignal) =>
    apiFetch<Page<ModelVersion>>('/admin/model-versions', { signal }),
  registerModel: (data: {
    kind: string
    name: string
    version: string
    evalResult: string
    approvedBy: string
  }) => apiFetch<ModelVersion>('/admin/model-versions', json(data)),
  modelAction: (id: string, action: 'activate' | 'rollback', reason: string) =>
    apiFetch<ModelVersion>(
      `/admin/model-versions/${p(id)}/${action}`,
      json({ reason, reanalyze: false }),
    ),
  usage: (period: Period, callType: string, signal?: AbortSignal) =>
    apiFetch<Usage>(`/admin/ai-usage?${new URLSearchParams({ ...period, callType })}`, { signal }),
  errors: (signal?: AbortSignal) => apiFetch<Page<ErrorReport>>('/admin/error-reports', { signal }),
  error: (id: string, signal?: AbortSignal) =>
    apiFetch<ErrorReport>(`/admin/error-reports/${p(id)}`, { signal }),
  reviewError: (id: string, status: string, reviewReason: string) =>
    apiFetch<ErrorReport>(`/admin/error-reports/${p(id)}`, json({ status, reviewReason }, 'PATCH')),
  correction: (id: string, reason: string, corrected: string, key: string) =>
    apiFetch<ErrorReport>(`/admin/error-reports/${p(id)}/corrections`, { ...json({ reason, corrected }), headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key } }),
}
