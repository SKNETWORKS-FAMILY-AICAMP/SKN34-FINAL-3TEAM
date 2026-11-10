import type { LoadingReport, PreflightRequest, PreflightResult, RegistrationProvenance } from '../../domain/admin/modelRegistration.ts'
import { apiFetch } from '../apiClient.ts'
import { json } from '../parent/api.ts'
import type { Page } from '../../domain/parent.ts'
import type { Mission, Period } from '../../domain/classroom.ts'
import type {
  AdminMission,
  Audit,
  Job,
  JobRetryResult,
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
import type { AchievementStandard, MissionDraft, MissionDraftRequest } from '../../domain/admin/missionStandards.ts'
const operationFilters = (values: Record<string, string | undefined>) => new URLSearchParams(
  Object.entries(values).filter((entry): entry is [string, string] => entry[1] !== undefined && entry[1] !== ''),
)
const p = (id: string) => encodeURIComponent(id)
export const adminApi = {
  preflightModel: (body: PreflightRequest) => apiFetch<PreflightResult>('/admin/models/preflight', { ...json(body), signal: AbortSignal.timeout(25_000) }),
  modelLoading: (signal?: AbortSignal) => apiFetch<LoadingReport>('/admin/model-loading', { signal }),
  overview: (period: Period, signal?: AbortSignal) =>
    apiFetch<Overview>(`/admin/overview?${new URLSearchParams({ ...period })}`, { signal }),
  jobs: (type: string, status: string, signal?: AbortSignal, period?: Period) =>
    apiFetch<Page<Job>>(`/admin/jobs?${operationFilters({ type, status, ...period })}`, {
      signal,
    }),
  job: (id: string, signal?: AbortSignal) => apiFetch<Job>(`/admin/jobs/${p(id)}`, { signal }),
  retry: (id: string, key: string) =>
    apiFetch<JobRetryResult>(`/admin/jobs/${p(id)}/retry`, {
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
      json(missionWritePayload(data), id ? 'PATCH' : 'POST'),
    ),
  rubric: (id: string, data: Omit<Rubric, 'version'>) =>
    apiFetch<AdminMission>(`/admin/missions/${p(id)}/rubric`, json(rubricWritePayload(data), 'PUT')),
  preview: (id: string, signal?: AbortSignal) =>
    apiFetch<{ mission: Mission; missionVersion: number; rubricVersion: number | null }>(
      `/admin/missions/${p(id)}/preview`,
      { signal },
    ),
  action: (id: string, action: string, data: unknown = {}) =>
    apiFetch<AdminMission>(`/admin/missions/${p(id)}/${action}`, json(data)),
  /** 성취기준 표 조회 (api-spec 2.8, #355). gradeBand는 '초3~4' 같은 한글 값 */
  standards: (filters: Record<string, string>, signal?: AbortSignal) =>
    apiFetch<Page<AchievementStandard>>(`/admin/achievement-standards?${operationFilters(filters)}`, { signal }),
  /** 미션에 저장된 코드의 표 행. 코드마다 q로 찾아 같은 코드만 남김(표에 없는 코드는 빠짐) */
  standardsByCodes: async (codes: string[], signal?: AbortSignal) => {
    const found: Record<string, AchievementStandard> = {}
    await Promise.all([...new Set(codes.map((c) => c.trim()).filter(Boolean))].map(async (code) => {
      const hit = (await adminApi.standards({ q: code, size: '100' }, signal)).items.find((s) => s.code === code)
      if (hit) found[code] = hit
    }))
    return found
  },
  drafts: (filters: Record<string, string>, signal?: AbortSignal) =>
    apiFetch<Page<MissionDraft>>(`/admin/mission-drafts?${operationFilters(filters)}`, { signal }),
  draft: (id: string, signal?: AbortSignal) =>
    apiFetch<MissionDraft>(`/admin/mission-drafts/${p(id)}`, { signal }),
  /** 202: 생성·자동 검사는 비동기 (state-diagram 3.4) */
  requestDraft: (body: MissionDraftRequest) => apiFetch<MissionDraft>('/admin/mission-drafts', json(body)),
  adoptDraft: (id: string) => apiFetch<AdminMission>(`/admin/mission-drafts/${p(id)}/adopt`, json({})),
  discardDraft: (id: string) => apiFetch<MissionDraft>(`/admin/mission-drafts/${p(id)}/discard`, json({})),
  models: (signal?: AbortSignal) =>
    apiFetch<Page<ModelVersion>>('/admin/model-versions', { signal }),
  allModels: async (signal?: AbortSignal) => {
    const items: ModelVersion[] = []
    for (let page = 0; ; page++) {
      const result = await apiFetch<Page<ModelVersion>>(`/admin/model-versions?page=${page}&size=100`, { signal, cache: 'no-store' })
      items.push(...result.items)
      if (items.length >= result.totalElements) return { ...result, items }
      if (!result.items.length) throw new Error('전체 모델 목록을 확인하지 못했습니다. 다시 조회해 주세요.')
    }
  },
  registerModel: (data: {
    kind: string
    name: string
    version: string
    evaluation: EvaluationEvidence
    refId?: string
    artifactUri?: string
    registration?: RegistrationProvenance
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

export function missionWritePayload(data: Omit<MissionVersion, 'version' | 'createdAt'> & { demoOnly: boolean }) {
  return {
    title: data.title, subject: data.subject, gradeMin: data.gradeMin, gradeMax: data.gradeMax,
    thinkingType: data.thinkingType, inputType: data.inputType, question: data.question, guide: data.guide,
    sceneUri: data.sceneUri, staticSceneUri: data.staticSceneUri,
    achievementStandards: data.achievementStandards, achievementLevels: data.achievementLevels ?? null, choices: data.choices ?? [], categories: data.categories ?? [],
    answerUnit: data.inputType === 'SOLUTION_STEPS' ? data.answerUnit?.trim() || null : null,
    inputTemplate: ['SOLUTION_STEPS', 'ESSAY'].includes(data.inputType) ? data.inputTemplate ?? [] : [],
    demoOnly: data.demoOnly,
  }
}

/**
 * PUT /admin/missions/{id}/rubric 본문. learning은 빠진 keywords·essayType을 빈 값으로 새 rubric_version에 저장하므로
 * 화면에서 편집하지 않는 두 필드도 불러온 값을 그대로 보낸다 (#306, learning-service.yaml AdminRubricRequest).
 */
export function rubricWritePayload(data: Omit<Rubric, 'version'>) {
  return {
    elements: data.elements, answerKey: data.answerKey ?? null, exampleAnswer: data.exampleAnswer,
    forbiddenTerms: data.forbiddenTerms, hints: data.hints,
    keywords: data.keywords ?? [], essayType: data.essayType ?? null,
  }
}
