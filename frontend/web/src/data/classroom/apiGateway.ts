import { refreshAccessToken, notifyAuthChange, hasAccessToken } from '../apiClient.ts'
import { ApiError, apiFetch, apiResponse, setAccessToken } from '../apiClient.ts'
import { streamSse } from '../sse.ts'
import { blankAnswer, inPeriod, publicAttempt } from '../../domain/classroom.ts'
import type {
  AnswerContent,
  AnalysisResult,
  Attempt,
  Child,
  Draft,
  Feedback,
  Mission,
  Period,
  Report,
  Session,
} from '../../domain/classroom.ts'
import type { ClassroomGateway } from './gateway.ts'
import { DraftConflictError } from './errors.ts'

type JsonObject = Record<string, unknown>
const contractError = (detail: string): never => {
  throw new ApiError({
    code: 'CONTRACT_NOT_READY',
    status: 502,
    title: '백엔드 응답 계약 확인이 필요합니다.',
    detail,
  })
}
function object(raw: unknown): JsonObject {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw))
    return contractError('JSON 객체 응답을 받지 못했습니다.')
  return raw as JsonObject
}
function list(raw: unknown): unknown[] {
  if (Array.isArray(raw)) return raw
  const rows = object(raw).items
  if (!Array.isArray(rows)) return contractError('목록의 items 필드가 없습니다.')
  return rows
}
function text(raw: unknown, field: string): string {
  if (typeof raw !== 'string') return contractError(`${field} 필드를 확인해 주세요.`)
  return raw
}
function draftDto(raw: unknown, inputType: AnswerContent['inputType']): Draft {
  const d = object(raw),
    content = object(d.content),
    wireAnswer = object(content.answer)
  if (typeof d.version !== 'number' && typeof d.version !== 'string')
    return contractError('초안 version이 필요합니다.')
  if (typeof content.memo !== 'string') return contractError('초안 content.memo가 필요합니다.')
  const version = typeof d.version === 'number' ? `"${d.version}"` : d.version
  return {
    answer: { ...blankAnswer(inputType), ...wireAnswer, inputType } as AnswerContent,
    memo: content.memo,
    version,
    savedAt: typeof d.savedAt === 'string' ? d.savedAt : undefined,
  }
}
function attemptDto(raw: unknown): Attempt {
  const data = object(raw)
  if (
    typeof data.attemptId !== 'string' ||
    typeof data.studentId !== 'string' ||
    !data.mission ||
    !Array.isArray(data.answers) ||
    !['IN_PROGRESS', 'COMPLETED'].includes(String(data.status))
  )
    return contractError(
      '시도 상세의 attemptId·studentId·mission·answers·status 구조가 필요합니다. 공개 Controller 구현 시 어댑터와 함께 확정해 주세요.',
    )
  const a = data as unknown as Attempt
  if (!a.finishedAt && (a.reveal != null || a.revealKind != null || a.checklist != null))
    return contractError('마무리 전 응답에 정답·예시·체크리스트가 포함되어 표시하지 않았습니다.')
  if (a.draft) a.draft = draftDto(data.draft, a.mission.inputType)
  return a
}
function feedbackDto(raw: unknown): Feedback {
  const f = object(raw)
  if (
    !['PENDING', 'RUNNING', 'DONE', 'FAILED'].includes(String(f.status)) ||
    !Array.isArray(f.nextActions)
  )
    return contractError('피드백 status·nextActions가 유효하지 않습니다.')
  return f as unknown as Feedback
}
function payload(a: AnswerContent, followupId?: string): object {
  const extra = { dictatedByGuardian: a.dictatedByGuardian, ...(followupId ? { followupId } : {}) }
  if (a.inputType === 'NARRATIVE')
    return {
      inputType: a.inputType,
      text: a.text,
      ...extra,
    }
  if (a.inputType === 'ESSAY') return { inputType: a.inputType, essay: a.essay, ...extra }
  if (a.inputType === 'CHOICE' || a.inputType === 'ORDERING')
    return { inputType: a.inputType, choiceIds: a.choiceIds, ...extra }
  if (a.inputType === 'SOLUTION_STEPS')
    return { inputType: a.inputType, finalAnswer: a.finalAnswer, steps: a.steps, ...extra }
  if (a.inputType === 'CLASSIFICATION')
    return { inputType: a.inputType, assignments: a.assignments, ...extra }
  return contractError(
    `${a.inputType}의 제출 JSON 필드가 아직 API 명세에 정의되어 있지 않습니다. 임의 형식으로 전송하지 않았습니다.`,
  )
}
const body = (data: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(data) })
export function createApiGateway(): ClassroomGateway {
  const conversations = new Map<string, string>()
  const regenerating = new Map<string, number>()
  async function childRecords(child: Child, role: 'STUDENT' | 'PARENT', period: Period) {
    const path =
      role === 'STUDENT'
        ? '/students/me/attempts'
        : `/children/${child.id}/attempts?from=${period.from}&to=${period.to}`
    const rows = list(await apiFetch<unknown>(path)).map((raw) => publicAttempt(attemptDto(raw)))
    if (rows.some((a) => a.studentId !== child.id))
      return contractError('목록에 요청 범위 밖의 자녀 기록이 있습니다.')
    return role === 'STUDENT'
      ? rows.filter((a) => a.answers.some((v) => inPeriod(v.submittedAt, period)))
      : rows
  }
  return {
    demo: false,
    setScenario() {
      /* UI 시연 전용. 실제 API 결과를 변조하지 않는다. */
    },
    async login(email, password) {
      const raw = object(await apiFetch<unknown>('/auth/login', body({ email, password })))
      if (!['PARENT', 'ADMIN'].includes(String(raw.role)))
        return contractError('학부모/관리자 로그인 role이 필요합니다.')
      setAccessToken(text(raw.accessToken, 'accessToken'), raw.role as 'PARENT' | 'ADMIN')
      const me = raw.role === 'ADMIN' ? object(await apiFetch('/me')) : raw
      return { role: raw.role, permissions: me.permissions } as Session
    },
    async logout() {
      try {
        await apiFetch('/auth/logout', body({}))
        notifyAuthChange('LOGOUT')
      } finally {
        setAccessToken(null)
        conversations.clear()
      }
    },
    async restore() {
      if (!hasAccessToken()) await refreshAccessToken()
      const me = object(await apiFetch('/me'))
      if (!['PARENT', 'STUDENT', 'ADMIN'].includes(String(me.role)))
        return contractError('복원할 역할을 확인하지 못했습니다.')
      if (me.role === 'STUDENT') {
        const c = object(me.child)
        if (
          typeof c.id !== 'string' ||
          typeof c.nickname !== 'string' ||
          !Number.isInteger(c.grade) ||
          Number(c.grade) < 3 ||
          Number(c.grade) > 6
        )
          return contractError('학생 범위를 복원하지 못했습니다.')
        return { role: 'STUDENT', child: c as unknown as Child, nextAction: me.nextAction, startPath: me.startPath } as Session
      }
      return { role: me.role, permissions: me.permissions, nextAction: me.nextAction, startPath: me.startPath } as Session
    },
    async home(child) {
      const raw = object(await apiFetch('/students/me/home'))
      const c = object(raw.student)
      if (
        c.id !== child.id ||
        !Array.isArray(raw.missions) ||
        !['OK', 'NO_RECORD', 'INSUFFICIENT_SAMPLE', 'PROCESSING', 'FAILED'].includes(
          String(raw.state),
        )
      )
        return contractError('학생 홈의 대상·상태·미션을 확인해 주세요.')
      return {
        ...raw,
        resume: raw.resume ? attemptDto(raw.resume) : null,
      } as unknown as import('../../domain/classroom.ts').StudentHome
    },
    async children() {
      return list(await apiFetch<unknown>('/children')).map((raw) => {
        const c = object(raw)
        const grade = Number(c.grade)
        if (grade < 3 || grade > 6) return contractError('자녀의 지원 학년은 3~6입니다.')
        return {
          id: text(c.childId ?? c.id, 'childId'),
          nickname: text(c.nickname, 'nickname'),
          grade,
          birthYear: Number(c.birthYear),
          plan: c.plan === 'PREMIUM' ? 'PREMIUM' : 'FREE',
        } as Child
      })
    },
    async enterStudent(child) {
      const raw = object(
        await apiFetch<unknown>('/auth/student-sessions', body({ childId: child.id })),
      )
      if (raw.role !== 'STUDENT') return contractError('학생 세션 role이 필요합니다.')
      setAccessToken(text(raw.accessToken, 'accessToken'), 'STUDENT')
      notifyAuthChange('STUDENT')
      return { role: 'STUDENT', child }
    },
    async missions() {
      return list(await apiFetch<unknown>('/missions')).map((raw) => {
        const m = object(raw)
        if (typeof m.title !== 'string' || typeof m.inputType !== 'string')
          return contractError('미션의 title·inputType이 필요합니다.')
        return { ...m, id: text(m.missionId ?? m.id, 'missionId') } as unknown as Mission
      })
    },
    async mission(id) {
      const m = object(await apiFetch<unknown>(`/missions/${id}`))
      if (
        typeof m.question !== 'string' ||
        typeof m.title !== 'string' ||
        typeof m.inputType !== 'string'
      )
        return contractError('미션 상세의 질문·제목·입력 틀을 받지 못했습니다.')
      return { ...m, id: text(m.missionId ?? m.id, 'missionId') } as unknown as Mission
    },
    records: childRecords,
    async record(child, id) {
      const a = publicAttempt(
        attemptDto(await apiFetch<unknown>(`/children/${child.id}/attempts/${id}`)),
      )
      if (a.studentId !== child.id) return contractError('요청한 자녀와 원문의 자녀가 다릅니다.')
      return a
    },
    async start(mission, _child) {
      return attemptDto(await apiFetch<unknown>(`/missions/${mission.id}/attempts`, body({})))
    },
    async attempt(id) {
      const response = await apiResponse<unknown>(`/attempts/${id}`)
      const a = attemptDto(response.data)
      if (a.draft && response.etag) a.draft.version = response.etag
      return a
    },
    async saveDraft(id, draft) {
      let response
      try {
        response = await apiResponse<unknown>(`/attempts/${id}/draft`, {
          method: 'PUT',
          headers: { 'If-Match': draft.version },
          body: JSON.stringify({ content: { answer: payload(draft.answer), memo: draft.memo } }),
        })
      } catch (error) {
        if (error instanceof ApiError && error.problem.status === 409 && error.problem.latest)
          throw new DraftConflictError(draftDto(error.problem.latest, draft.answer.inputType))
        throw error
      }
      const raw = object(response.data),
        version = response.etag ?? raw.version
      if (typeof version !== 'string' && typeof version !== 'number')
        return contractError('초안 저장 응답에 ETag 또는 version이 필요합니다.')
      return {
        ...draft,
        version: typeof version === 'number' ? `"${version}"` : version,
        savedAt: typeof raw.savedAt === 'string' ? raw.savedAt : undefined,
      }
    },
    async hint(id) {
      const raw = object(await apiFetch<unknown>(`/attempts/${id}/hints`, body({})))
      return text(raw.question, 'question')
    },
    async submit(id, answer, key, followupId) {
      await apiFetch<unknown>(`/attempts/${id}/answers`, {
        ...body(payload(answer, followupId)),
        headers: { 'Idempotency-Key': key },
      })
      return attemptDto(await apiFetch<unknown>(`/attempts/${id}`))
    },
    async feedback(_id, answerId, onStatus, signal) {
      let result: Feedback | undefined
      await streamSse(`/answers/${answerId}/feedback`, {
        signal,
        onEvent(event) {
          if (event.event === 'result') {
            result = feedbackDto(event.data)
            onStatus(result)
          } else if (event.event === 'status') {
            const raw = object(event.data)
            onStatus({ status: raw.state === 'FAILED' ? 'FAILED' : 'RUNNING', nextActions: [] })
          } else if (event.event === 'error') {
            const raw = object(event.data)
            throw new ApiError({
              ...raw,
              status: typeof raw.status === 'number' ? raw.status : 503,
              code: typeof raw.code === 'string' ? raw.code : 'AI_UNAVAILABLE',
              title: typeof raw.title === 'string' ? raw.title : '처리를 완료하지 못했습니다.',
            })
          }
        },
      })
      return result ?? { status: 'RUNNING', nextActions: [] }
    },
    async finish(id) {
      await apiFetch(`/attempts/${id}/finish`, body({}))
      return attemptDto(await apiFetch<unknown>(`/attempts/${id}`))
    },
    async reflect(id, reflection) {
      await apiFetch(
        `/attempts/${id}/reflection`,
        body({ difficulty: reflection.difficulty, text: reflection.text }),
      )
      return attemptDto(await apiFetch<unknown>(`/attempts/${id}`))
    },
    async report(child, period, revision) {
      const reports = list(await apiFetch<unknown>(`/children/${child.id}/reports`)).map(object)
      const found = reports.find((r) => object(r.period).from === period.from)
      if (!found)
        throw new ApiError({
          code: 'REPORT_NOT_GENERATED',
          status: 404,
          title: '아직 생성된 리포트가 없습니다.',
          detail: '완료된 기록 없음 리포트와 생성 전 상태는 다릅니다.',
        })
      const id = text(found.reportId, 'reportId'),
        raw = object(
          await apiFetch<unknown>(`/reports/${id}${revision ? `?revision=${revision}` : ''}`),
        )
      if (!['QUEUED', 'RUNNING', 'COMPLETED', 'FAILED'].includes(String(raw.status)))
        return contractError('리포트 status가 필요합니다.')
      const reportPeriod = object(raw.period)
      if (
        raw.childId !== child.id ||
        reportPeriod.from !== period.from ||
        reportPeriod.to !== period.to
      )
        return contractError('요청한 자녀·기간과 리포트 범위가 다릅니다.')
      if (raw.status === 'COMPLETED' && child.plan === 'PREMIUM' && raw.narrative) {
        const verification = object(raw.verification)
        if (verification.numbersMatched !== true || verification.quotesMatched !== true)
          return contractError('리포트의 숫자·인용 대조가 완료되지 않았습니다.')
      }
      const baseline = regenerating.get(id)
      if (!revision && baseline !== undefined) {
        if (Number(raw.revision) <= baseline && raw.status === 'COMPLETED') raw.status = 'QUEUED'
        else if (raw.status === 'FAILED' || Number(raw.revision) > baseline) regenerating.delete(id)
      }
      const records = raw.status === 'COMPLETED' ? await childRecords(child, 'PARENT', period) : []
      return {
        reportId: id,
        childId: child.id,
        period,
        revision: Number(raw.revision ?? 1),
        revisions: Array.isArray(raw.revisions)
          ? raw.revisions.map((v) => Number(object(v).revision))
          : [1],
        status: raw.status,
        state: raw.state,
        metrics: Array.isArray(raw.metrics) ? raw.metrics : [],
        records,
        eveningQuestion:
          child.plan === 'PREMIUM' && typeof raw.eveningQuestion === 'string'
            ? raw.eveningQuestion
            : undefined,
        narrative:
          child.plan === 'FREE'
            ? null
            : typeof object(raw.narrative ?? {}).text === 'string'
              ? object(raw.narrative).text
              : null,
        regenerations: Math.max(0, (Array.isArray(raw.revisions) ? raw.revisions.length : 1) - 1),
      } as Report
    },
    async regenerate(report) {
      if (regenerating.has(report.reportId))
        throw new ApiError({
          status: 409,
          code: 'REGENERATE_NOT_ALLOWED',
          title: '이미 새 판을 생성 중입니다.',
        })
      await apiFetch(`/reports/${report.reportId}/regenerate`, body({}))
      regenerating.set(report.reportId, report.revision)
      return { ...report, status: 'QUEUED', regenerations: 1 }
    },
    async analyze(child, period, question) {
      const scopeKey = `${child.id}:${period.from}:${period.to}`
      let id = conversations.get(scopeKey)
      if (!id) {
        id = text(
          object(await apiFetch<unknown>('/conversations', body({ childId: child.id, ...period })))
            .conversationId,
          'conversationId',
        )
        conversations.set(scopeKey, id)
      }
      let result: AnalysisResult | undefined
      await streamSse(`/conversations/${id}/messages`, {
        body: { question, scope: period },
        onEvent(event) {
          // delta는 검증 전 임시 출력. 확정 응답으로 사용하지 않는다.
          if (event.event === 'result') {
            const raw = object(event.data),
              v = object(raw.verification)
            if (v.numbersMatched !== true || v.quotesMatched !== true)
              return contractError('숫자·인용 대조를 통과한 result가 필요합니다.')
            result = raw as unknown as AnalysisResult
          } else if (event.event === 'clarification')
            throw new ApiError({
              code: 'CLARIFICATION_REQUIRED',
              status: 422,
              title: text(object(event.data).question, 'question'),
            })
          else if (event.event === 'error') {
            const raw = object(event.data)
            throw new ApiError({
              ...raw,
              status: typeof raw.status === 'number' ? raw.status : 503,
              code: typeof raw.code === 'string' ? raw.code : 'AI_UNAVAILABLE',
              title: typeof raw.title === 'string' ? raw.title : '처리를 완료하지 못했습니다.',
            })
          }
        },
      })
      if (!result) return contractError('대조 완료된 분석 결과를 받지 못했습니다.')
      return result
    },
  }
}
export { DraftConflictError }
