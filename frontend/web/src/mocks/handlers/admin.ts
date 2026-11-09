import { http } from 'msw/http'
import { ApiError } from '../../data/apiClient.ts'
import type {
  Permission,
  AdminMission,
  MissionVersion,
  Rubric,
  ModelVersion,
} from '../../domain/admin/operations.ts'
import { essayTypes, missingMissionFields } from '../../domain/admin/operations.ts'
import type { AchievementStandard, GeneratedDraft, MissionDraft, MissionDraftRequest } from '../../domain/admin/missionStandards.ts'
import {
  answerKeyInputs, commonElementsOf, discardableDraft, draftRequestErrors, gradeBands, isLevelShape, isValidElementCode,
} from '../../domain/admin/missionStandards.ts'
import type { LearningMission } from '../../domain/learning.ts'
import type { Period } from '../../domain/classroom.ts'
import { validPeriod } from '../../domain/parent.ts'
import { workspaceScenario as mode } from '../fixtures/accounts.ts'
import { fixtureStore as store } from '../fixtures/student.ts'
import {
  jobs,
  missions,
  missionDrafts,
  achievementStandards,
  audits,
  audit,
  modelVersions,
  errorReports,
  reportedAttemptIds,
  retryReceipts,
  stamp,
} from '../fixtures/admin/operations.ts'
import { guard, respond } from './student.ts'
import { fail, page } from './parent.ts'
const unpublishedChanges = (m: AdminMission) => m.currentVersion !== m.publishedVersion || m.currentRubricVersion !== m.publishedRubricVersion
const reviewable = (m: AdminMission) => m.status === 'REVIEW_REQUIRED' || m.status === 'PUBLISHED' && unpublishedChanges(m)
export function allow(request: Request, permission?: Permission) {
  guard(request)
  const s = store.snapshot().session
  if (
    s?.role !== 'ADMIN' ||
    mode === 'forbidden' ||
    (permission && !s.permissions?.includes(permission))
  )
    fail('FORBIDDEN', '이 작업에 필요한 관리자 권한이 없습니다.', 403)
}
function queryFault() {
  if (mode === 'query-fail') fail('QUERY_FAILED', '관리자 조회에 실패했습니다.', 503, true)
}
function period(request: Request): Period {
  const q = new URL(request.url).searchParams,
    p = { from: q.get('from') ?? '2026-10-20', to: q.get('to') ?? '2026-10-26' }
  if (!validPeriod(p)) fail('VALIDATION_FAILED', '집계 기간을 확인해 주세요.')
  return p
}
const mission = (id: string) => {
  const m = missions.find((m) => m.missionId === id)
  if (!m) fail('NOT_FOUND', '미션이 없습니다.', 404)
  return m!
}
/** core가 learning 400을 다시 쓸 때의 제목 (AdminLearningService.sanitize): detail 없이 코드만 전달 */
const learningFail = (status = 400, code = 'VALIDATION_FAILED'): never =>
  fail(code, '학습 서비스가 관리자 요청을 처리하지 못했습니다.', status)
const standardsByCode = () => Object.fromEntries(achievementStandards.map((s) => [s.code, s])) as Record<string, AchievementStandard>
const draft = (id: string) => {
  const d = missionDrafts.find((d) => d.draftId === id)
  if (!d) fail('NOT_FOUND', '미션 초안을 찾을 수 없습니다.', 404)
  return d!
}
/** 목업 생성 진행: 생성 중 초안은 두 번째 조회부터 1회 시도로 READY (실제는 10초 주기 작업, state-diagram 3.4) */
const draftReads = new Map<string, number>()
function advance(d: MissionDraft) {
  if (d.status !== 'GENERATING') return d
  const reads = (draftReads.get(d.draftId) ?? 0) + 1
  draftReads.set(d.draftId, reads)
  if (reads < 2) return d
  Object.assign(d, { status: 'READY', attempts: d.attempts + 1, draft: generated(d.input), updatedAt: stamp(),
    versions: { prompt: 'mission-draft-mock-1', model: 'mock-model' } })
  return d
}
/** 입력 방식·유형에 맞는 목업 초안 (learning DraftRules.elementCodes와 같은 code) */
function generated(input: MissionDraftRequest): GeneratedDraft {
  const std = standardsByCode()[input.standardCodes[0]], keyed = answerKeyInputs.includes(input.inputType)
  const choices = keyed ? [{ id: 'c1', label: '첫째' }, { id: 'c2', label: '둘째' }] : null
  const categories = input.inputType === 'CLASSIFICATION' ? [{ id: 'g1', label: '모둠 1' }] : null
  const elements = keyed
    ? [{ code: 'ANSWER_KEY', label: '정답', description: '고른 답이 정답과 같음', goodThought: true, standardCode: null }]
    : [...commonElementsOf(input.thinkingType).map((e) => ({ code: e.code, label: e.label, description: e.description, goodThought: true, standardCode: std.code })),
      ...(input.inputType === 'SOLUTION_STEPS' ? [{ code: 'FINAL_ANSWER', label: '최종 답', description: '최종 답이 정답과 같음', goodThought: true, standardCode: null }] : [])]
  return {
    title: `[목업 초안] ${std.area}`, question: `${std.statement.replace(/[.]$/, '')}에 대해 생각을 말해 보세요.`, guide: '장면을 살펴보세요.',
    sceneNote: '목업 장면 메모', choices, categories,
    answerKey: input.inputType === 'CHOICE' ? { choiceIds: ['c1'] } : input.inputType === 'ORDERING' ? { choiceIds: ['c1', 'c2'] }
      : input.inputType === 'CLASSIFICATION' ? { assignments: [{ choiceId: 'c1', categoryId: 'g1' }, { choiceId: 'c2', categoryId: 'g1' }] }
      : input.inputType === 'SOLUTION_STEPS' ? { finalAnswer: '30' } : null,
    exampleAnswer: ['NARRATIVE', 'ESSAY'].includes(input.inputType) ? '목업 예시 답입니다.' : null,
    forbiddenTerms: ['정답'], hints: ['무엇을 보았나요?'], elements,
  }
}
const inputTemplates: Partial<Record<MissionDraftRequest['inputType'], string[]>> = {
  SOLUTION_STEPS: ['① 무엇을 구하나요?', '② 어떻게 구할까요?', '③ 계산', '④ 확인해 보기'],
  ESSAY: ['주장', '까닭 1', '까닭 2', '반대 의견에 답하기'],
}
const job = (id: string) => {
  const j = jobs.find((j) => j.jobId === id)
  if (!j) fail('NOT_FOUND', '작업이 없습니다.', 404)
  return j!
}
const model = (id: string) => {
  const v = modelVersions.find((v) => v.id === id)
  if (!v) fail('NOT_FOUND', '버전이 없습니다.', 404)
  return v!
}
function versionData(d: Partial<MissionVersion>, version: number): MissionVersion {
  if (!d.title?.trim()) fail('VALIDATION_FAILED', '제목을 입력해 주세요.')
  const inputType = d.inputType ?? 'NARRATIVE',
    thinkingType = d.thinkingType ?? 'ANALYZE'
  if (
    !['CHOICE', 'ORDERING', 'CLASSIFICATION', 'NARRATIVE', 'SOLUTION_STEPS', 'ESSAY'].includes(
      inputType,
    ) ||
    !['ANALYZE', 'EVALUATE', 'CREATE', 'SOLVE', 'REFLECT'].includes(thinkingType)
  )
    fail('VALIDATION_FAILED', '입력 방식·생각 유형을 확인해 주세요.')
  if (
    !Number.isInteger(d.gradeMin) ||
    !Number.isInteger(d.gradeMax) ||
    d.gradeMin! < 3 ||
    d.gradeMax! > 6 ||
    d.gradeMin! > d.gradeMax! ||
    (inputType === 'ESSAY' && d.gradeMin! < 5)
  )
    fail('VALIDATION_FAILED', '지원 학년을 확인해 주세요.')
  // learning requireLevelShape: 저장 때는 {코드: A~E} 모양만 (#353)
  if (d.achievementLevels && Object.entries(d.achievementLevels).some(([code, level]) => !code.trim() || !isLevelShape(level)))
    learningFail()
  return {
    version,
    title: d.title!,
    subject: d.subject ?? '',
    gradeMin: d.gradeMin!,
    gradeMax: d.gradeMax!,
    thinkingType,
    inputType,
    question: d.question ?? '',
    guide: d.guide ?? '',
    answerUnit: d.answerUnit ?? null,
    inputTemplate: d.inputTemplate ?? [],
    sceneUri: d.sceneUri ?? '',
    staticSceneUri: d.staticSceneUri ?? '',
    achievementStandards: d.achievementStandards ?? [],
    achievementLevels: d.achievementLevels ?? null,
    choices: d.choices,
    categories: d.categories,
    createdAt: stamp(),
  }
}
export const adminHandlers = [
  http.get('/api/v1/admin/overview', ({ request }) =>
    respond(async () => {
      allow(request)
      queryFault()
      const p = period(request),
        visible =
          mode === 'empty'
            ? []
            : jobs.filter(
                (j) => j.createdAt.slice(0, 10) >= p.from && j.createdAt.slice(0, 10) <= p.to,
              ),
        types = ['CONVERSATION', 'REPORT', 'NOTIFICATION'] as const,
        statuses = ['QUEUED', 'RUNNING', 'COMPLETED', 'FAILED'] as const
      return {
        period: p,
        inclusionRule:
          '개발 목업 작업 집계 · 실제 운영 집계 아님 · 시연 학습 기록은 운영 통계에서 제외',
        learning: { attempts: 0, completedAttempts: 0, students: 0, inclusionRule: '개발 목업 · 실제 학습 통계 아님' },
        jobCounts: types.flatMap((type) =>
          statuses.map((status) => ({
            type,
            status,
            count: visible.filter((j) => j.type === type && j.status === status).length,
          })),
        ),

      }
    }),
  ),
  http.get('/api/v1/admin/jobs', ({ request }) =>
    respond(async () => {
      allow(request, 'SERVICE_OPS')
      queryFault()
      const q = new URL(request.url).searchParams
      return page(
        mode === 'empty'
          ? []
          : jobs.filter(
              (j) =>
                (!q.get('from') || j.createdAt.slice(0, 10) >= q.get('from')!) &&
                (!q.get('to') || j.createdAt.slice(0, 10) <= q.get('to')!) &&
                (!q.get('type') || j.type === q.get('type')) &&
                (!q.get('status') || j.status === q.get('status')),
            ),
      )
    }),
  ),
  http.get('/api/v1/admin/jobs/:jobId', ({ request, params }) =>
    respond(async () => {
      allow(request, 'SERVICE_OPS')
      queryFault()
      return job(String(params.jobId))
    }),
  ),
  http.post('/api/v1/admin/jobs/:jobId/retry', ({ request, params }) =>
    respond(async () => {
      allow(request, 'SERVICE_OPS')
      const j = job(String(params.jobId)),
        key = request.headers.get('Idempotency-Key')
      if (!key) fail('VALIDATION_FAILED', '멱등 키가 필요합니다.')
      const receipt = retryReceipts.get(key!)
      if (receipt) {
        if (receipt.jobId !== j.jobId)
          fail('IDEMPOTENCY_KEY_REUSED', '같은 키로 다른 작업을 요청할 수 없습니다.', 422)
        return receipt.response
      }
      if (j.status !== 'FAILED') fail('VALIDATION_FAILED', '실패 작업만 재처리할 수 있습니다.')
      if (!j.retryable) fail('JOB_RETRY_UNAVAILABLE', '재처리 공급자 연결 대기', 503)
      j.retryCount++
      j.status = mode === 'retry-fail' ? 'FAILED' : 'COMPLETED'
      j.failureReason = j.status === 'FAILED' ? '재처리에서도 외부 응답 시간 초과' : null
      j.retryable = j.status === 'FAILED'
      j.retryUnavailableReason = j.retryable ? null : 'JOB_NOT_FAILED'
      j.executions.push({
        executionId: crypto.randomUUID(),
        attemptNo: j.executions.length + 1,
        status: j.status,
        errorCode: j.status === 'FAILED' ? 'AI_UNAVAILABLE' : null,
        triggeredBy: 'mock-admin',
        startedAt: stamp(),
        finishedAt: stamp(),
      })
      audit(
        'JOB_RETRY',
        'JOB',
        j.jobId,
        j.status === 'FAILED' ? 'FAILURE' : 'SUCCESS',
        `재처리 ${j.retryCount}회 · ${j.status}`,
      )
      retryReceipts.set(key!, { jobId: j.jobId, response: structuredClone(j) })
      return j
    }),
  ),
  http.get('/api/v1/admin/queues', ({ request }) =>
    respond(async () => {
      allow(request, 'SERVICE_OPS')
      queryFault()
      return {
        vhost: '/',
        items: ['report.report.generate', 'report.report.generate.retry.1', 'report.report.generate.dlq'].map((name) => ({
          name,
          kind: name.endsWith('.dlq') ? 'DLQ' : name.includes('.retry.') ? 'RETRY' : 'WORK',
          messages: 0,
          messagesReady: 0,
          messagesUnacknowledged: 0,
          consumers: 0,
          state: 'running',
        })),
      }
    }),
  ),
  http.get('/api/v1/admin/audit-logs', ({ request }) =>
    respond(async () => {
      allow(request)
      queryFault()
      const p = period(request),
        q = new URL(request.url).searchParams
      return page(
        audits.filter(
          (a) =>
            (!q.get('targetType') || a.targetType === q.get('targetType')) &&
            a.createdAt.slice(0, 10) >= p.from &&
            a.createdAt.slice(0, 10) <= p.to,
        ),
      )
    }),
  ),
  http.get('/api/v1/admin/missions', ({ request }) =>
    respond(async () => {
      allow(request, 'CONTENT'); queryFault()
      const q = new URL(request.url).searchParams
      const index = Number(q.get('page') ?? 0), size = Number(q.get('size') ?? 20)
      if (!Number.isInteger(index) || index < 0 || !Number.isInteger(size) || size < 1 || size > 100)
        fail('VALIDATION_FAILED', '페이지를 확인해 주세요.')
      const rows = mode === 'empty' ? [] : missions.filter((m) => {
        const v = m.versions.find((v) => v.version === m.currentVersion)!
        return (!q.get('status') || m.status === q.get('status')) &&
          (!q.get('grade') || (v.gradeMin <= Number(q.get('grade')) && v.gradeMax >= Number(q.get('grade')))) &&
          (!q.get('thinkingType') || v.thinkingType === q.get('thinkingType'))
      })
      return { items: rows.slice(index * size, (index + 1) * size), page: index, size, totalElements: rows.length,
        counts: (['DRAFT', 'REVIEW_REQUIRED', 'PUBLISHED', 'UNPUBLISHED'] as const).map(
          (status) => ({ status, count: missions.filter((m) => m.status === status).length })),
      }
    }),
  ),
  http.post('/api/v1/admin/missions', ({ request }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const data = (await request.json()) as MissionVersion & { demoOnly: boolean },
        v = versionData(data, 1),
        m: AdminMission = {
          missionId: crypto.randomUUID(),
          code: `MOCK-${missions.length + 1}`,
          source: 'MANUAL',
          status: 'DRAFT',
          demoOnly: data.demoOnly,
          currentVersion: 1,
          currentRubricVersion: null,
          publishedVersion: null,
          publishedRubricVersion: null,
          versions: [v],
          rubrics: [],
          reviews: [],
        }
      missions.push(m)
      audit('MISSION_CREATE', 'MISSION', m.missionId, 'SUCCESS', '새 미션 버전 1')
      return m
    }, 201),
  ),
  http.get('/api/v1/admin/missions/:missionId', ({ request, params }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      queryFault()
      return mission(String(params.missionId))
    }),
  ),
  http.patch('/api/v1/admin/missions/:missionId', ({ request, params }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const m = mission(String(params.missionId)),
        d = (await request.json()) as MissionVersion & { demoOnly: boolean }
      m.versions.push(versionData(d, m.currentVersion + 1))
      m.currentVersion++
      m.demoOnly = d.demoOnly
      if (m.status === 'REVIEW_REQUIRED') m.status = 'DRAFT'
      audit(
        'MISSION_UPDATE',
        'MISSION',
        m.missionId,
        'SUCCESS',
        `새 미션 버전 ${m.currentVersion} · 기존 학습 버전 유지`,
      )
      return m
    }),
  ),
  http.put('/api/v1/admin/missions/:missionId/rubric', ({ request, params }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const m = mission(String(params.missionId)),
        d = (await request.json()) as Omit<Rubric, 'version'>
      if (d.elements?.some((e) => !e.label.trim() || !Number.isInteger(e.points) || e.points <= 0))
        fail('VALIDATION_FAILED', '요소 이름과 양의 정수 배점을 확인해 주세요.')
      // learning #262 저장 검사: code 모양·중복, standardCode는 null 또는 비지 않은 값
      const codes = d.elements?.map((e) => e.code) ?? []
      if (codes.some((c) => !c?.trim() || !isValidElementCode(c)) || new Set(codes).size !== codes.length ||
          d.elements?.some((e) => e.standardCode != null && !e.standardCode.trim()))
        learningFail()
      // learning AdminRubricRequest와 같이 keywords ≤100개·각 1~200자, essayType은 다섯 값 또는 null. 빠지면 빈 값으로 저장한다 (#306).
      const keywords = d.keywords ?? [], essayType = d.essayType ?? null
      if (!Array.isArray(keywords) || keywords.length > 100 || keywords.some((k) => typeof k !== 'string' || !k.length || k.length > 200))
        fail('VALIDATION_FAILED', '핵심어 묶음을 확인해 주세요.')
      if (essayType !== null && !(essayTypes as readonly string[]).includes(essayType))
        fail('VALIDATION_FAILED', '글 종류를 확인해 주세요.')
      m.currentRubricVersion = (m.currentRubricVersion ?? 0) + 1
      m.rubrics.push({ ...d, keywords, essayType, version: m.currentRubricVersion })
      if (m.status === 'REVIEW_REQUIRED') m.status = 'DRAFT'
      audit(
        'RUBRIC_UPDATE',
        'MISSION',
        m.missionId,
        'SUCCESS',
        `새 기준표 버전 ${m.currentRubricVersion}`,
      )
      return m
    }),
  ),
  http.get('/api/v1/admin/missions/:missionId/preview', ({ request, params }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const m = mission(String(params.missionId)),
        v = m.versions.at(-1)!
      return {
        mission: {
          id: m.missionId,
          title: v.title,
          subject: v.subject,
          grade: v.gradeMin,
          thinkingType: v.thinkingType,
          inputType: v.inputType,
          question: v.question,
          hint: '',
          scene: v.subject === '수학' ? 'math' : v.subject === '과학' ? 'science' : v.subject === '영어' ? 'english' : 'korean',
          answerUnit: v.answerUnit,
          inputTemplate: v.inputTemplate,
          sceneUri: v.sceneUri,
          staticSceneUri: v.staticSceneUri,
          choices: v.choices,
          categories: v.categories,
        },
        missionVersion: m.currentVersion,
        rubricVersion: m.currentRubricVersion,
      }
    }),
  ),
  ...(['review-request', 'review', 'publish', 'unpublish'] as const).map((action) =>
    http.post(`/api/v1/admin/missions/:missionId/${action}`, ({ request, params }) =>
      respond(async () => {
        allow(request, 'CONTENT')
        const m = mission(String(params.missionId))
        if (action === 'review-request') {
          const d = (await request.json()) as { missionVersion: number; rubricVersion: number }
          if (d.missionVersion !== m.currentVersion || d.rubricVersion !== m.currentRubricVersion)
            fail('VALIDATION_FAILED', '현재 미션·기준표 버전을 확인해 주세요.')
          if (m.status === 'DRAFT' || m.status === 'UNPUBLISHED') m.status = 'REVIEW_REQUIRED'
          else if (!(m.status === 'PUBLISHED' && unpublishedChanges(m))) fail('CONFLICT', '검토 요청할 수정본이 없습니다.', 409)
        }
        if (action === 'review') {
          const d = (await request.json()) as {
            missionVersion: number
            rubricVersion: number
            result: 'APPROVED' | 'CHANGES_REQUESTED'
            comment: string
          }
          if (
            !reviewable(m) ||
            d.missionVersion !== m.currentVersion ||
            d.rubricVersion !== m.currentRubricVersion ||
            !['APPROVED', 'CHANGES_REQUESTED'].includes(d.result)
          )
            fail('VALIDATION_FAILED', '검토 요청된 현재 버전을 확인해 주세요.')
          m.reviews.push({ ...d, createdAt: stamp() })
          if (d.result === 'CHANGES_REQUESTED' && m.status !== 'PUBLISHED') m.status = 'DRAFT'
        }
        if (action === 'publish') {
          if (!reviewable(m)) fail('CONFLICT', '검토 가능한 상태가 아닙니다.', 409)
          const missing = missingMissionFields(m, standardsByCode())
          if (mode === 'publish-missing') missing.push('staticSceneUri')
          if (missing.length) {
            audit('MISSION_PUBLISH', 'MISSION', m.missionId, 'FAILURE', missing.join(', '))
            throw new ApiError({
              status: 422,
              code: 'MISSION_PUBLISH_INCOMPLETE',
              title: '게시 필수 항목을 확인해 주세요.',
              missingFields: missing,
              retryable: false,
            })
          }
          m.status = 'PUBLISHED'
          m.publishedVersion = m.currentVersion
          m.publishedRubricVersion = m.currentRubricVersion
          const v = m.versions.at(-1)!,
            r = m.rubrics.at(-1)!
          store.publishCatalog(m.missionId, {
            id: m.missionId,
            title: v.title,
            subject: v.subject,
            grade: v.gradeMin,
            gradeMax: v.gradeMax,
            thinkingType: v.thinkingType,
            inputType: v.inputType,
            question: v.question,
            hint: r.hints[0] ?? '장면을 다시 살펴보세요.',
            scene: v.subject === '수학' ? 'math' : v.subject === '과학' ? 'science' : v.subject === '영어' ? 'english' : 'korean',
          answerUnit: v.answerUnit,
          inputTemplate: v.inputTemplate,
            sceneUri: v.sceneUri,
            staticSceneUri: v.staticSceneUri,
            choices: v.choices,
            categories: v.categories,
          } as LearningMission)
        }
        if (action === 'unpublish') {
          if (m.status !== 'PUBLISHED') fail('CONFLICT', '공개 중인 미션이 아닙니다.', 409)
          m.status = 'UNPUBLISHED'
          store.publishCatalog(m.missionId, null)
        }
        audit(
          `MISSION_${action.toUpperCase().replace('-', '_')}`,
          'MISSION',
          m.missionId,
          'SUCCESS',
          '기존 시도는 시작 당시 버전으로 유지',
        )
        return m
      }),
    ),
  ),
  http.get('/api/v1/admin/achievement-standards', ({ request }) =>
    respond(async () => {
      allow(request, 'CONTENT'); queryFault()
      const q = new URL(request.url).searchParams
      const index = Number(q.get('page') ?? 0), size = Number(q.get('size') ?? 20), band = q.get('gradeBand'), text = q.get('q') ?? ''
      if (!Number.isInteger(index) || index < 0 || !Number.isInteger(size) || size < 1 || size > 100 || text.length > 100 ||
          (band && !(band in gradeBands))) fail('VALIDATION_FAILED', '조회 조건을 확인해 주세요.')
      const rows = mode === 'empty' ? [] : achievementStandards.filter((s) =>
        (!q.get('subject') || s.subject === q.get('subject')) && (!band || s.gradeBand === band) &&
        (!text || s.code.includes(text) || s.statement.includes(text)))
      return { items: rows.slice(index * size, (index + 1) * size), page: index, size, totalElements: rows.length }
    }),
  ),
  http.post('/api/v1/admin/mission-drafts', ({ request }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const body = (await request.json()) as MissionDraftRequest
      if (!Array.isArray(body.standardCodes) || new Set(body.standardCodes).size !== body.standardCodes.length ||
          draftRequestErrors(body, standardsByCode()).length) learningFail()
      const d: MissionDraft = {
        draftId: crypto.randomUUID(), status: 'GENERATING', attempts: 0, maxAttempts: 3,
        input: { ...body, achievementLevels: body.achievementLevels ?? null }, checkResults: [], draft: null, failureCode: null,
        versions: { prompt: null, model: null }, missionId: null, requestedBy: 'mock-admin', createdAt: stamp(), updatedAt: stamp(),
      }
      missionDrafts.unshift(d)
      audit('MISSION_DRAFT_REQUEST', 'MISSION_DRAFT', d.draftId, 'SUCCESS', '초안 생성 요청')
      return d
    }, 202),
  ),
  http.get('/api/v1/admin/mission-drafts', ({ request }) =>
    respond(async () => {
      allow(request, 'CONTENT'); queryFault()
      const q = new URL(request.url).searchParams
      const index = Number(q.get('page') ?? 0), size = Number(q.get('size') ?? 20), status = q.get('status')
      if (!Number.isInteger(index) || index < 0 || !Number.isInteger(size) || size < 1 || size > 100 ||
          (status && !['GENERATING', 'READY', 'CHECK_FAILED', 'FAILED', 'ADOPTED', 'DISCARDED'].includes(status)))
        fail('VALIDATION_FAILED', '조회 조건을 확인해 주세요.')
      const rows = mode === 'empty' ? [] : missionDrafts.map(advance).filter((d) => !status || d.status === status)
      return { items: rows.slice(index * size, (index + 1) * size), page: index, size, totalElements: rows.length }
    }),
  ),
  http.get('/api/v1/admin/mission-drafts/:draftId', ({ request, params }) =>
    respond(async () => {
      allow(request, 'CONTENT'); queryFault()
      return advance(draft(String(params.draftId)))
    }),
  ),
  http.post('/api/v1/admin/mission-drafts/:draftId/adopt', ({ request, params }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const d = draft(String(params.draftId))
      if (d.status !== 'READY' || !d.draft) learningFail(409, 'CONFLICT')
      const g = d.draft!, input = d.input
      // learning DraftRules: 교과는 첫 성취기준 교과, 장면·단위 비움, 시연 전용 아님, 요소 배점 1·검증 전
      const m: AdminMission = {
        missionId: crypto.randomUUID(), code: `MOCK-${missions.length + 1}`, source: 'LLM_DRAFT', status: 'DRAFT', demoOnly: false,
        currentVersion: 1, currentRubricVersion: 1, publishedVersion: null, publishedRubricVersion: null,
        versions: [{
          version: 1, title: g.title, subject: standardsByCode()[input.standardCodes[0]]?.subject ?? '', gradeMin: input.gradeMin,
          gradeMax: input.gradeMax, thinkingType: input.thinkingType, inputType: input.inputType, question: g.question, guide: g.guide,
          answerUnit: null, inputTemplate: inputTemplates[input.inputType] ?? [], sceneUri: null, staticSceneUri: null,
          achievementStandards: input.standardCodes, achievementLevels: input.achievementLevels, choices: g.choices ?? [],
          categories: g.categories ?? [], createdAt: stamp(),
        }],
        rubrics: [{
          version: 1, elements: g.elements.map((e) => ({ ...e, points: 1, commonErrors: [], judgeVerified: false })),
          answerKey: g.answerKey, exampleAnswer: g.exampleAnswer, forbiddenTerms: g.forbiddenTerms, hints: g.hints, keywords: [], essayType: null,
        }],
        reviews: [],
      }
      missions.push(m)
      Object.assign(d, { status: 'ADOPTED', missionId: m.missionId, updatedAt: stamp() })
      audit('MISSION_DRAFT_ADOPT', 'MISSION_DRAFT', d.draftId, 'SUCCESS', `미션 ${m.missionId} 생성`)
      return m
    }, 201),
  ),
  http.post('/api/v1/admin/mission-drafts/:draftId/discard', ({ request, params }) =>
    respond(async () => {
      allow(request, 'CONTENT')
      const d = draft(String(params.draftId))
      if (!discardableDraft(d.status)) learningFail(409, 'CONFLICT')
      Object.assign(d, { status: 'DISCARDED', updatedAt: stamp() })
      audit('MISSION_DRAFT_DISCARD', 'MISSION_DRAFT', d.draftId, 'SUCCESS', '초안 버림')
      return d
    }),
  ),
  http.get('/api/v1/admin/model-versions', ({ request }) =>
    respond(async () => {
      allow(request, 'SERVICE_OPS')
      queryFault()
      const q = new URL(request.url).searchParams, kind = q.get('kind')
      const rows = modelVersions.filter(v => !kind || v.kind === kind)
      const index = Number(q.get('page') ?? 0), size = Number(q.get('size') ?? 20)
      return { items: rows.slice(index * size, (index + 1) * size), page: index, size, totalElements: rows.length }
    }),
  ),
  http.post('/api/v1/admin/model-versions', ({ request }) =>
    respond(async () => {
      allow(request, 'SERVICE_OPS')
      const d = (await request.json()) as Omit<ModelVersion,'evalResult'> & { evaluation: import('../../domain/admin/operations.ts').EvaluationEvidence }
      const e = d.evaluation
      const fields = ['datasetId','datasetVersion','baselineVersion','comparisonReport','trainingEvaluationSeparation','quoteAccuracy','calculationAccuracy','humanReview'] as const
      if ((d.kind === 'MODEL' && !d.artifactUri?.trim()) || !d.name?.trim() || !d.version?.trim() || !['RUBRIC','MODEL','PROMPT','GENERATION'].includes(d.kind) ||
          !e || fields.some(k => !e[k]?.trim()) || !e.evaluatedScopes?.length ||
          new Set(e.evaluatedScopes).size !== e.evaluatedScopes.length || e.evaluatedScopes.some(v=>typeof v!=='string'||v.length>200||!/^[a-z0-9][a-z0-9._:/-]*$/.test(v)) ||
          (d.kind==='RUBRIC' ? !d.refId : !!d.refId)) fail('MODEL_APPROVAL_REJECTED','평가 근거·범위·기준표 ID를 확인해 주세요.',422)
      if (modelVersions.some(v=>v.kind===d.kind&&v.name===d.name&&v.version===d.version)) fail('MODEL_VERSION_CONFLICT','이미 등록된 버전입니다.',409)
      const v: ModelVersion = { id:crypto.randomUUID(),kind:d.kind,name:d.name,version:d.version,refId:d.refId,artifactUri:d.artifactUri,status:'REGISTERED',createdAt:stamp(),evalResult:{ evidence:e,approval:null,activeScopes:[],revision:0 } }
      modelVersions.push(v)
      audit('MODEL_REGISTER', 'MODEL_VERSION', v.id, 'SUCCESS', { name: v.name, version: v.version })
      return v
    }, 201),
  ),
  ...(['activate', 'rollback'] as const).map((action) =>
    http.post(`/api/v1/admin/model-versions/:versionId/${action}`, ({ request, params }) =>
      respond(async () => {
        allow(request, 'SERVICE_OPS')
        const v = model(String(params.versionId)),
          d = (await request.json()) as { reason: string; scopes: string[]; approved?: boolean; reanalysisPlanned: boolean }
        const evaluation = v.evalResult
        if (action==='activate' ? v.status!=='REGISTERED'||!!v.approvedBy : v.status!=='INACTIVE'||!evaluation?.approval||!modelVersions.some(m=>m.kind===v.kind&&m.name===v.name&&m.status==='ACTIVE'))
          fail('MODEL_VERSION_CONFLICT','현재 상태에서는 변경할 수 없습니다.',409)
        if (!evaluation || !d.reason?.trim() || !Array.isArray(d.scopes) || !d.scopes.length || new Set(d.scopes).size!==d.scopes.length)
          fail('MODEL_APPROVAL_REJECTED','평가·적용 범위와 변경 사유가 필요합니다.',422)
        const allowed = action==='activate' ? evaluation!.evidence.evaluatedScopes : evaluation!.approval?.scopes
        if (!allowed || d.scopes.some(scope=>!allowed.includes(scope)) || (action==='activate'&&d.approved!==true)) fail('MODEL_APPROVAL_REJECTED','승인된 평가 범위만 적용할 수 있습니다.',422)
        const previous = modelVersions.find(m => m.kind === v.kind && m.name === v.name && m.status === 'ACTIVE')
        const revision=Math.max(...modelVersions.filter(m=>m.kind===v.kind&&m.name===v.name).map(m=>m.evalResult?.revision??0))+1
        for (const other of modelVersions) if (other.kind===v.kind&&other.name===v.name&&other.status==='ACTIVE') { other.status='INACTIVE'; if (other.evalResult) other.evalResult.activeScopes=[] }
        v.status='ACTIVE';v.activatedAt=stamp()
        if (action==='activate') { evaluation!.approval={ scopes:d.scopes,reason:d.reason,approvedBy:'mock-service-ops',approvedAt:stamp() }; v.approvedBy='mock-service-ops' }
        evaluation!.activeScopes=d.scopes;evaluation!.revision=revision
        audit(action==='activate'?'MODEL_ACTIVATE':'MODEL_ROLLBACK','MODEL_VERSION',v.id,'SUCCESS',{ name: v.name, version: v.version, scopes: d.scopes, reason: d.reason, reanalysisPlanned: d.reanalysisPlanned, previousVersionId: previous?.id ?? null })
        return v
      }),
    ),
  ),
  http.get('/api/v1/admin/ai-usage', ({ request }) =>
    respond(async () => {
      allow(request, 'SERVICE_OPS')
      queryFault()
      const p = period(request),
        filter = new URL(request.url).searchParams.get('callType')
      if (filter && !['JUDGMENT','FOLLOWUP','ANALYSIS','REPORT_NARRATIVE','MISSION_DRAFT','M2','M1'].includes(filter)) fail('VALIDATION_FAILED','호출 종류를 확인해 주세요.',400)
      return {
        period: p,
        items: [],
      }
    }),
  ),
  http.get('/api/v1/admin/error-reports', ({ request }) =>
    respond(async () => {
      allow(request, 'SERVICE_OPS')
      queryFault()
      return page(errorReports)
    }),
  ),
  http.get('/api/v1/admin/error-reports/:reportId', ({ request, params }) =>
    respond(async () => {
      allow(request, 'SERVICE_OPS')
      const r = errorReports.find((r) => r.reportId === params.reportId)
      if (!r) fail('NOT_FOUND', '신고가 없습니다.', 404)
      audit('ERROR_REPORT_VIEW', 'ERROR_REPORT', r!.reportId, 'SUCCESS', '신고 연결 시도 원문 열람')
      const a = store
        .snapshot()
        .attempts.find((a) => a.attemptId === reportedAttemptIds.get(r!.reportId))
      if (!a) return r
      const { draft: _private, ...linkedAttempt } = a
      return { ...r, linkedAttempt }
    }),
  ),
  http.patch('/api/v1/admin/error-reports/:reportId', ({ request, params }) =>
    respond(async () => {
      allow(request, 'SERVICE_OPS')
      const r = errorReports.find((r) => r.reportId === params.reportId)
      if (!r) fail('NOT_FOUND', '신고가 없습니다.', 404)
      const d = (await request.json()) as {
        status: 'RECEIVED' | 'IN_REVIEW' | 'RESOLVED'
        reviewReason: string
      }
      if (!d.reviewReason?.trim() || !['RECEIVED', 'IN_REVIEW', 'RESOLVED'].includes(d.status))
        fail('VALIDATION_FAILED', '검토 사유·상태를 확인해 주세요.')
      Object.assign(r!, d)
      audit('ERROR_REPORT_REVIEW', 'ERROR_REPORT', r!.reportId, 'SUCCESS', d.reviewReason)
      return r
    }),
  ),
  http.post('/api/v1/admin/error-reports/:reportId/corrections', ({ request, params }) =>
    respond(async () => {
      allow(request, 'SERVICE_OPS')
      const r = errorReports.find((r) => r.reportId === params.reportId)
      if (!r) fail('NOT_FOUND', '신고가 없습니다.', 404)
      const d = (await request.json()) as { reason: string; corrected: string }
      if (!d.reason?.trim() || !d.corrected?.trim())
        fail('VALIDATION_FAILED', '정정 사유와 결과를 입력해 주세요.')
      r!.corrections.push({
        ...d,
        createdAt: stamp(),
        impact: '대화·집계·리포트 반영 확인 대기(목업). 원본 답변은 변경하지 않음.',
      })
      audit('JUDGMENT_CORRECTION', 'ERROR_REPORT', r!.reportId, 'SUCCESS', d.reason)
      return r
    }),
  ),
]
