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
  MissionStatus,
  OperationQueue,
  Rubric,
  MissionVersion,
  ErrorReport,
  Usage,
  EvaluationEvidence,
} from '../../domain/admin/operations.ts'
const operationFilters = (values: Record<string, string | undefined>) => new URLSearchParams(
  Object.entries(values).filter((entry): entry is [string, string] => entry[1] !== undefined && entry[1] !== ''),
)
const p = (id: string) => encodeURIComponent(id)
export const adminApi = {
  overview: (period: Period, signal?: AbortSignal) =>
    apiFetch<Overview>(`/admin/overview?${new URLSearchParams({ ...period })}`, { signal }),
  jobs: (type: string, status: string, signal?: AbortSignal, period?: Period) =>
    apiFetch<Page<Job>>(`/admin/jobs?${operationFilters({ type, status, ...period })}`, {
      signal,
    }),
  job: (id: string, signal?: AbortSignal) => apiFetch<Job>(`/admin/jobs/${p(id)}`, { signal }),
  retry: (id: string, key: string) =>
    apiFetch<Job>(`/admin/jobs/${p(id)}/retry`, {
      ...json({}),
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
    }),
  queues: (signal?: AbortSignal) =>
    apiFetch<{ vhost: string; items: OperationQueue[] }>('/admin/queues', {
      signal,
    }),
  audits: (period: Period, targetType: string, signal?: AbortSignal) =>
    apiFetch<Page<Audit>>(`/admin/audit-logs?${operationFilters({ ...period, targetType })}`, {
      signal,
    }),
  missions: (filters: Record<string, string>, signal?: AbortSignal) =>
    apiFetch<Page<AdminMission> & { counts: { status: MissionStatus; count: number }[] }>(
      `/admin/missions?${operationFilters(filters)}`,
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
    evaluation: EvaluationEvidence
    refId?: string
    artifactUri?: string
  }) => apiFetch<ModelVersion>('/admin/model-versions', json(data)),
  modelAction: (id: string, action: 'activate' | 'rollback', reason: string, scopes: string[], reanalysisPlanned = false) =>
    apiFetch<ModelVersion>(
      `/admin/model-versions/${p(id)}/${action}`,
      json({ reason, scopes, reanalysisPlanned, ...(action === 'activate' ? { approved: true } : {}) }),
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
