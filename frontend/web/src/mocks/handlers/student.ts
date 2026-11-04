import { http, HttpResponse } from 'msw/http'
import { isShared, saveSharing, requireShared } from '../fixtures/sharing.ts'
import { ApiError } from '../../data/apiClient.ts'
import { DraftConflictError } from '../../data/classroom/errors.ts'
import type { Child, DemoScenario, Feedback, Period } from '../../domain/classroom.ts'
import { previousWeek, thisWeek } from '../../domain/classroom.ts'
import {
  mockAccounts,
  mockIdentity,
  permissionsFor,
  mockAccountChildren,
  mockConsentRequired, mockGuardianConsentRequired,
} from '../fixtures/accounts.ts'
import {
  fixtureStore as store,
  normalizeAnswer,
  wireAttempt,
  wireDraft,
  persistFixtureState,
  mockSubmissionReceipts,
} from '../fixtures/student.ts'
import { mockLooks, persistLooks } from '../fixtures/studentLook.ts'
import { attemptGuardianPassword, lockParentSession, parentSessionLocked } from '../fixtures/guardianPassword.ts'
import { DEFAULT_LOOK, isCompanionId, isThemeId } from '../../domain/studentLook.ts'
import { difficultyCodes } from '../../domain/learning.ts'

let child: Child | undefined = store.snapshot().session?.child,
  token = '',
  serial = 0,
  scenario: DemoScenario = 'normal'
let mockRole = store.snapshot().session?.role
const usedKeys = mockSubmissionReceipts
const reports = new Map<string, { child: Child; period: Period }>()
const conversations = new Map<string, { child: Child; period: Period }>()
const selfChecks = new Map<string, Map<string, boolean>>()
mockAccountChildren.set('parent@example.test', structuredClone(store.snapshot().children ?? []))
export function setMockScenario(value: DemoScenario) {
  scenario = value
  store.setScenario(value)
  if (value === 'token-expired' || value === 'refresh-fail') token = `expired-${token}`
  if (typeof window !== 'undefined') window.dispatchEvent(new Event('sagomungchi:mock-invalidate'))
}
const issueToken = () => (token = `msw-access-${++serial}`)
/** 잠기지 않은 세션의 refresh 회전. 실제 쿠키/보안 속성 검증은 백엔드 통합 대상이며 목은 로그인 상태만 모사한다. */
function refreshUnlocked() {
  if (scenario === 'refresh-fail' || !store.snapshot().session || mockRole === 'STUDENT')
    throw new ApiError({ status: 401, code: 'UNAUTHENTICATED', title: '다시 로그인해 주세요.' })
  return { accessToken: issueToken(), role: mockRole }
}
/** 기기 PIN 로그인 성공 시 학생 세션을 연다. 학부모 로그인 없이 기기 소유 학부모의 자녀 목록을 쓴다. */
export function startDeviceStudentSession(selected: Child, ownerChildren: Child[]) {
  store.restoreSnapshot({
    ...store.snapshot(),
    children: structuredClone(ownerChildren),
    session: { role: 'STUDENT', entry: 'DEVICE', child: structuredClone(selected) },
  })
  mockRole = 'STUDENT'
  child = selected
  return issueToken()
}
const page = (items: unknown[]) => ({ items, page: 0, size: 20, totalElements: items.length })
export function guard(request: Request) {
  if ((scenario === 'token-expired' || scenario === 'refresh-fail') && token.startsWith('expired-'))
    throw new ApiError({ status: 401, code: 'TOKEN_EXPIRED', title: '시연 토큰 만료' })
  if (!token || request.headers.get('Authorization') !== `Bearer ${token}`)
    throw new ApiError({ status: 401, code: 'UNAUTHENTICATED', title: '로그인이 필요합니다.' })
}
export function problem(error: unknown) {
  if (error instanceof ApiError)
    return {
      ...error.problem,
      retryable: error.problem.status >= 500,
      ...(error instanceof DraftConflictError ? { latest: wireDraft(error.latest) } : {}),
    }
  return {
    status: 400,
    code: 'VALIDATION_FAILED',
    title: '요청 형식을 확인해 주세요.',
    retryable: false,
  }
}
export async function respond(action: () => Promise<unknown>, status = 200): Promise<Response> {
  try {
    const data = await action()
    persistFixtureState()
    return new HttpResponse(JSON.stringify(data), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })
  } catch (error) {
    persistFixtureState()
    const data = problem(error)
    return HttpResponse.json(data, {
      status: data.status,
      headers: { 'Content-Type': 'application/problem+json' },
    })
  }
}
function sse(run: (push: (event: string, data: unknown) => void) => Promise<void>) {
  const encoder = new TextEncoder()
  return new HttpResponse(
    new ReadableStream({
      async start(controller) {
        const push = (event: string, data: unknown) =>
          controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`))
        controller.enqueue(encoder.encode(': ping\n\n'))
        try {
          await run(push)
        } catch (e) {
          // SSE error는 learning처럼 오류가 정한 retryable을 그대로(ai 4xx·계약 밖은 false, #82)
          const own = e instanceof ApiError ? e.problem.retryable : undefined
          push('error', { ...problem(e), ...(own === undefined ? {} : { retryable: own }) })
        }
        push('done', {})
        persistFixtureState()
        controller.close()
      },
    }),
    { headers: { 'Content-Type': 'text/event-stream' } },
  )
}
async function linked(id: string) {
  const c = (await store.children()).find((c) => c.id === id)
  if (!c)
    throw new ApiError({ status: 403, code: 'CHILD_NOT_LINKED', title: '연결된 자녀가 아닙니다.' })
  return c
}
function studentOnly() {
  if (mockRole !== 'STUDENT' || !child)
    throw new ApiError({ status: 403, code: 'FORBIDDEN', title: '학생만 바꿀 수 있는 설정입니다.' })
  return child
}
const id = (value: string | readonly string[] | undefined) => {
  if (!value) throw new Error('경로 식별값이 없습니다.')
  return String(value)
}
export const studentHandlers = [
  http.post('/api/v1/auth/login', ({ request }) =>
    respond(async () => {
      const data = (await request.json()) as { email: string; password: string }
      if (!mockAccounts.has(data.email) || data.password !== 'demo-only')
        throw new ApiError({
          status: 401,
          code: 'UNAUTHENTICATED',
          title: '시연 계정을 확인해 주세요.',
        })
      const session = await store.login(data.email, data.password)
      lockParentSession(false)
      if (!permissionsFor(data.email).length)
        store.replaceChildren(structuredClone(mockAccountChildren.get(data.email) ?? []))
      mockIdentity.email = data.email
      mockIdentity.permissions = permissionsFor(data.email)
      mockRole = mockIdentity.permissions.length ? 'ADMIN' : 'PARENT'
      if (mockRole === 'ADMIN')
        store.restoreSnapshot({
          ...store.snapshot(),
          session: { role: 'ADMIN', permissions: mockIdentity.permissions },
        })
      child = undefined
      return { ...session, role: mockRole, accessToken: issueToken() }
    }),
  ),
  http.post('/api/v1/auth/refresh', () =>
    respond(async () => {
      // 동석 진입으로 잠긴 학부모 세션은 refresh로 풀리지 않는다 (core PARENT_SESSION_LOCKED).
      if (parentSessionLocked())
        throw new ApiError({ status: 401, code: 'PARENT_SESSION_LOCKED', title: '보호자 비밀번호로 돌아와 주세요.' })
      return refreshUnlocked()
    }),
  ),
  http.post('/api/v1/auth/parent-unlock', ({ request }) =>
    respond(async () => {
      // core와 같이 잠기지 않은 세션은 비밀번호를 확인하지 않고 refresh와 같이 처리한다 (#310).
      if (!parentSessionLocked()) return refreshUnlocked()
      const data = (await request.json()) as { password?: unknown }
      const result = attemptGuardianPassword(typeof data.password === 'string' ? data.password : '')
      if (result.code)
        throw new ApiError({
          status: result.code === 'GUARDIAN_PASSWORD_LOCKED' ? 423 : result.code === 'GUARDIAN_PASSWORD_NOT_SET' ? 409 : 401,
          code: result.code,
          title: '보호자 비밀번호를 확인해 주세요.',
          ...(result.remainingAttempts === undefined ? {} : { remainingAttempts: result.remainingAttempts }),
        })
      lockParentSession(false)
      await store.login(mockIdentity.email, 'demo-only')
      mockRole = 'PARENT'
      child = undefined
      return { accessToken: issueToken(), role: 'PARENT', child: null, nextAction: 'READY', startPath: '/parent/journal' }
    }),
  ),
  http.post('/api/v1/auth/student/logout', ({ request }) =>
    respond(async () => {
      guard(request)
      if (mockRole !== 'STUDENT') throw new ApiError({ status: 403, code: 'FORBIDDEN', title: '학생 세션이 필요합니다.' })
      await store.logout()
      mockRole = undefined
      token = ''
      child = undefined
      return undefined
    }, 204),
  ),
  http.post('/api/v1/auth/logout', () =>
    respond(async () => {
      lockParentSession(false)
      await store.logout()
      mockRole = undefined
      token = ''
      child = undefined
      usedKeys.clear()
      conversations.clear()
      return {}
    }),
  ),
  http.get('/api/v1/me', ({ request }) =>
    respond(async () => {
      guard(request)
      const s = await store.restore()
      if (s.role === 'STUDENT') return { role: 'STUDENT', child: s.child }
      const nextAction = s.role !== 'PARENT' ? 'READY' : mockConsentRequired() ? 'CONSENT_REQUIRED' : (await store.children()).length ? 'READY' : 'CHILD_REGISTRATION_REQUIRED'
      return {
        ...s,
        ...(s.role === 'PARENT' ? { nextAction, startPath: nextAction === 'CONSENT_REQUIRED' ? '/parent/onboarding' : nextAction === 'CHILD_REGISTRATION_REQUIRED' ? '/parent/children/new' : '/parent/journal' } : {}),
        ...mockIdentity,
        role: mockRole ?? s.role,
        permissions: s.role === 'ADMIN' ? (s.permissions ?? mockIdentity.permissions) : [],
      }
    }),
  ),
  http.get('/api/v1/students/me/home', ({ request }) =>
    respond(async () => {
      guard(request)
      const h = await store.home(child!)
      return { ...h, resume: h.resume ? wireAttempt(h.resume) : null }
    }),
  ),
  // 꾸미기 설정 (API 명세 3.12, core #234와 같은 계약): 학생 토큰 전용
  http.get('/api/v1/students/me/preferences', ({ request }) =>
    respond(async () => {
      guard(request)
      return mockLooks.get(studentOnly().id) ?? DEFAULT_LOOK
    }),
  ),
  http.put('/api/v1/students/me/preferences', ({ request }) =>
    respond(async () => {
      guard(request)
      const me = studentOnly()
      const body = (await request.json()) as { theme?: unknown; companion?: unknown }
      if (!isThemeId(body.theme) || !isCompanionId(body.companion))
        throw new ApiError({ status: 422, code: 'VALIDATION_FAILED', title: '고를 수 없는 테마나 캐릭터입니다.' })
      const look = { theme: body.theme, companion: body.companion, updatedAt: new Date().toISOString() }
      mockLooks.set(me.id, look)
      persistLooks()
      return look
    }),
  ),
  http.get('/api/v1/students/me/sharing-preferences', ({ request }) => respond(async () => {
    guard(request)
    if (store.snapshot().session?.role !== 'STUDENT' || !child) throw new ApiError({ status: 403, code: 'FORBIDDEN', title: '학생 본인만 설정할 수 있습니다.' })
    return { studentId: child.id, parentSharingEnabled: isShared(child.id) }
  })),
  http.put('/api/v1/students/me/sharing-preferences', ({ request }) => respond(async () => {
    guard(request)
    if (store.snapshot().session?.role !== 'STUDENT' || !child) throw new ApiError({ status: 403, code: 'FORBIDDEN', title: '학생 본인만 설정할 수 있습니다.' })
    const data = await request.json() as Record<string, unknown>
    if (typeof data.parentSharingEnabled !== 'boolean') throw new Error('공개 여부를 확인해 주세요.')
    saveSharing(child.id, data.parentSharingEnabled)
    return { studentId: child.id, parentSharingEnabled: isShared(child.id) }
  })),
  http.get('/api/v1/children/:childId/sharing-preferences', ({ request, params }) => respond(async () => {
    guard(request)
    if (store.snapshot().session?.role !== 'PARENT') throw new ApiError({ status: 403, code: 'FORBIDDEN', title: '학부모 권한이 필요합니다.' })
    const selected = await linked(id(params.childId))
    return { studentId: selected.id, parentSharingEnabled: isShared(selected.id) }
  })),
  http.get('/api/v1/children', ({ request }) =>
    respond(async () => {
      guard(request)
      return page((await store.children()).map((c) => ({ ...c, childId: c.id })))
    }),
  ),
  http.post('/api/v1/auth/student-sessions', ({ request }) =>
    respond(async () => {
      guard(request)
      const data = (await request.json()) as { childId: string }
      if (mockConsentRequired()) throw new ApiError({ status: 403, code: 'CONSENT_REQUIRED', title: '필수 동의가 필요합니다.' })
      if (mockGuardianConsentRequired(data.childId)) throw new ApiError({ status: 403, code: 'CHILD_NOT_LINKED', title: '법정대리인 동의가 필요합니다.' })
      const selected = await linked(data.childId)
      const session = await store.enterStudent(selected)
      lockParentSession(true)
      mockRole = 'STUDENT'
      child = selected
      return { role: session.role, accessToken: issueToken() }
    }),
  ),
  http.get('/api/v1/missions', ({ request }) =>
    respond(async () => {
      guard(request)
      if (!child)
        throw new ApiError({ status: 403, code: 'FORBIDDEN', title: '학생 진입이 필요합니다.' })
      return page(await store.missions(child))
    }),
  ),
  http.get('/api/v1/missions/:missionId', ({ request, params }) =>
    respond(async () => {
      guard(request)
      return store.mission(id(params.missionId), child!)
    }),
  ),
  http.post('/api/v1/missions/:missionId/attempts', ({ request, params }) =>
    respond(async () => {
      guard(request)
      const m = await store.mission(id(params.missionId), child!)
      return wireAttempt(await store.start(m, child!))
    }, 201),
  ),
  http.get('/api/v1/attempts/:attemptId', ({ request, params }) =>
    respond(async () => {
      guard(request)
      return wireAttempt(await store.attempt(id(params.attemptId)))
    }),
  ),
  http.get('/api/v1/attempts/:attemptId/comparison', ({ request, params }) => respond(async () => {
    guard(request)
    if (store.snapshot().session?.role !== 'STUDENT') throw new ApiError({ status: 403, code: 'FORBIDDEN', title: '학생 본인만 비교할 수 있습니다.' })
    const current = await store.attempt(id(params.attemptId))
    if (!current.finishedAt) throw new ApiError({ status: 409, code: 'REVEAL_CONDITION_UNMET', title: '마무리 뒤 비교할 수 있습니다.' })
    const attempts = store.snapshot().attempts
    const index = attempts.findIndex(a => a.attemptId === current.attemptId)
    // 가상 저장소는 시도 생성 순서로 보관한다. 실서버의 시점 조건은 learning DB에서 검사한다.
    const previous = attempts.slice(0, index).reverse().filter(a => a.studentId === current.studentId &&
      a.mission.id === current.mission.id && a.finishedAt).sort((a, b) => b.finishedAt!.localeCompare(a.finishedAt!))[0]
    const snapshot = (a: typeof current) => ({ attemptId: a.attemptId, finishedAt: a.finishedAt!, mission: { ...a.mission, choices: a.mission.choices ?? [], categories: a.mission.categories ?? [], answerUnit: (a.mission as { answerUnit?: string }).answerUnit ?? null },
      answers: a.answers.map(answer => ({ answerId: answer.answerId, version: answer.version, text: answer.text,
        content: answer.content ?? { text: answer.text } })),
      judgment: a.answers.toReversed().find(answer => answer.feedback.judgment)?.feedback.judgment?.result ?? null,
      elements: a.checklist ?? [] })
    const same = previous && previous.mission.inputType === current.mission.inputType &&
      previous.mission.question === current.mission.question &&
      JSON.stringify(previous.checklist?.map(e => e.elementId)) === JSON.stringify(current.checklist?.map(e => e.elementId))
    const elements = !same ? [] : (current.checklist ?? []).map(e => {
      const before = previous!.checklist?.find(old => old.elementId === e.elementId)?.satisfied === true
      return { elementId: e.elementId, label: e.label, previousSatisfied: before, currentSatisfied: e.satisfied,
        change: e.satisfied ? before ? 'RETAINED' : 'ADDED' : before ? 'NOT_CONFIRMED_NOW' : 'NOT_CONFIRMED' }
    })
    return { attemptId: current.attemptId, state: !previous ? 'NO_PREVIOUS' : same ? 'COMPARABLE' : 'CRITERIA_CHANGED',
      previous: previous ? snapshot(previous) : null, current: snapshot(current), elements }
  })),
  http.put('/api/v1/attempts/:attemptId/draft', ({ request, params }) =>
    respond(async () => {
      guard(request)
      const attemptId = id(params.attemptId),
        a = await store.attempt(attemptId)
      const data = (await request.json()) as {
        content: { answer: Record<string, unknown>; memo: string }
      }
      const d = await store.saveDraft(attemptId, {
        answer: normalizeAnswer(data.content.answer, a.mission),
        memo: data.content.memo,
        version: (request.headers.get('If-Match') ?? '').replaceAll('"', ''),
      })
      return wireDraft(d)
    }),
  ),
  http.post('/api/v1/attempts/:attemptId/hints', ({ request, params }) =>
    respond(async () => {
      guard(request)
      return { question: await store.hint(id(params.attemptId)) }
    }),
  ),
  http.post('/api/v1/attempts/:attemptId/answers', ({ request, params }) =>
    respond(async () => {
      guard(request)
      const attemptId = id(params.attemptId),
        a = await store.attempt(attemptId),
        key = request.headers.get('Idempotency-Key')
      if (!key)
        throw new ApiError({
          status: 400,
          code: 'VALIDATION_FAILED',
          title: '멱등 키가 필요합니다.',
        })
      const data = (await request.json()) as Record<string, unknown>,
        signature = JSON.stringify(data),
        scope = `${attemptId}:${key}`
      if (usedKeys.has(scope) && usedKeys.get(scope)?.signature !== signature)
        throw new ApiError({
          status: 422,
          code: 'IDEMPOTENCY_KEY_REUSED',
          title: '같은 키에 다른 답변을 보낼 수 없습니다.',
        })
      const receipt = usedKeys.get(scope)
      if (receipt) return receipt.response
      const saved = await store.submit(
        attemptId,
        normalizeAnswer(data, a.mission),
        key,
        typeof data.followupId === 'string' ? data.followupId : undefined,
      )
      const answer = saved.answers.at(-1)!
      const response = {
        answerId: answer.answerId,
        attemptId,
        version: answer.version,
        followupId: answer.followupId,
        submittedAt: answer.submittedAt,
        feedback: { status: 'PENDING' as const },
      }
      usedKeys.set(scope, { signature, response })
      return response
    }, 201),
  ),
  http.post('/api/v1/answers/:answerId/feedback', async ({ request, params }) => {
    try {
      guard(request)
    } catch (e) {
      return respond(async () => {
        throw e
      })
    }
    const answerId = id(params.answerId),
      attemptId = answerId.slice(0, answerId.lastIndexOf('-a'))
    return sse(async (push) => {
      push('status', { state: 'RUNNING', message: '생각을 살펴보는 중' })
      const f: Feedback = await store.feedback(attemptId, answerId, () => {})
      if (f.status === 'DONE') push('result', f)
      else push('status', { state: f.status, message: '처리 중입니다. 잠시 후 다시 확인합니다.' })
    })
  }),
  http.post('/api/v1/attempts/:attemptId/finish', ({ request, params }) =>
    respond(async () => {
      guard(request)
      return wireAttempt(await store.finish(id(params.attemptId)))
    }),
  ),
  http.post('/api/v1/attempts/:attemptId/reflection', ({ request, params }) =>
    respond(async () => {
      guard(request)
      const raw = await request.json() as { difficulty: string; text: string }
      const difficulty = ({ EASY: '쉬웠어', NORMAL: '보통', HARD: '어려웠어' } as const)[raw.difficulty as 'EASY' | 'NORMAL' | 'HARD']
      if (!difficulty) throw new ApiError({ status: 400, code: 'VALIDATION_FAILED', title: '난이도 코드를 확인해 주세요.' })
      return wireAttempt(await store.reflect(id(params.attemptId), { difficulty, text: raw.text }))
    }),
  ),
  http.post('/api/v1/attempts/:attemptId/self-assessment', ({ request, params }) =>
    respond(async () => {
      guard(request)
      const attemptId = id(params.attemptId), a = await store.attempt(attemptId)
      if (!a.finishedAt) throw new ApiError({ status: 409, code: 'REVEAL_CONDITION_UNMET', title: '마무리 후 확인할 수 있어요.' })
      if (a.status === 'COMPLETED') throw new ApiError({ status: 409, code: 'ATTEMPT_CLOSED', title: '완료한 활동은 바꿀 수 없어요.' })
      const { checks } = await request.json() as { checks: { elementId: string; checked: boolean }[] }
      const elements = a.checklist ?? []
      if (!Array.isArray(checks) || !checks.length || new Set(checks.map((c) => c?.elementId)).size !== checks.length ||
          checks.some((c) => !c || typeof c.checked !== 'boolean' || !elements.some((e) => e.elementId === c.elementId)))
        throw new ApiError({ status: 400, code: 'VALIDATION_FAILED', title: '자기 평가 항목을 확인해 주세요.' })
      const saved = selfChecks.get(attemptId) ?? new Map<string, boolean>()
      checks.forEach((c) => saved.set(c.elementId, c.checked)); selfChecks.set(attemptId, saved)
      return elements.map((e) => ({ elementId: e.elementId, label: e.label, selfChecked: saved.get(e.elementId) ?? null,
        aiChecked: e.satisfied, quote: e.quote }))
    }),
  ),
  http.get('/api/v1/students/me/attempts', ({ request }) =>
    respond(async () => {
      guard(request)
      const q = new URL(request.url).searchParams
      const period = { from: q.get('from') ?? '2000-01-01', to: q.get('to') ?? '2099-12-31' }
      const index = Number(q.get('page') ?? 0), size = Number(q.get('size') ?? 20)
      const rows = await store.records(child!, 'STUDENT', period)
      return { items: rows.slice(index * size, (index + 1) * size), page: index, size, totalElements: rows.length,
        studentId: child!.id, state: rows.length ? 'OK' : 'NO_RECORD', period, inclusionRule: 'P08' }
    }),
  ),
  // core DSH-04 응답 모양(#240): 학생 토큰 전용, 돌아보기는 EASY/NORMAL/HARD 코드와 nullable text
  http.get('/api/v1/students/me/thinking-activities', ({ request }) =>
    respond(async () => {
      guard(request)
      const me = studentOnly(), q = new URL(request.url).searchParams
      const period = { from: q.get('from') ?? thisWeek.from, to: q.get('to') ?? thisWeek.to }
      const rows = await store.records(me, 'STUDENT', period)
      return { studentId: me.id, state: rows.length ? 'OK' : 'NO_RECORD', period, items: rows.map(r => ({
        attemptId: r.attemptId, thinkingType: r.mission.thinkingType, missionTitle: r.mission.title,
        reflection: r.reflection ? { difficulty: difficultyCodes[r.reflection.difficulty], text: r.reflection.text || null } : null,
      })) }
    }),
  ),
  // 이전 학부모 시안의 조회를 유지하는 호환 목. 별도 학부모 이슈 완료를 의미하지 않는다.
  http.get('/api/v1/children/:childId/attempts', ({ request, params }) =>
    respond(async () => {
      guard(request)
      const url = new URL(request.url)
      requireShared(id(params.childId))
      return page(
        await store.records(await linked(id(params.childId)), 'PARENT', {
          from: url.searchParams.get('from')!,
          to: url.searchParams.get('to')!,
        }),
      )
    }),
  ),
  http.get('/api/v1/children/:childId/attempts/:attemptId', ({ request, params }) =>
    respond(async () => {
      guard(request)
      const selected = await linked(id(params.childId))
      requireShared(selected.id)
      return store.record(selected, id(params.attemptId))
    }),
  ),
  http.get('/api/v1/children/:childId/reports', ({ request, params }) =>
    respond(async () => {
      guard(request)
      const c = await linked(id(params.childId))
      const rows = []
      for (const p of [previousWeek, thisWeek, { from: '2026-10-12', to: '2026-10-18' }]) {
        const r = await store.report(c, p)
        reports.set(r.reportId, { child: c, period: p })
        rows.push(r)
      }
      return page(rows)
    }),
  ),
  http.get('/api/v1/reports/:reportId', ({ request, params }) =>
    respond(async () => {
      guard(request)
      const context = reports.get(id(params.reportId))
      if (!context) throw new Error('목 리포트 없음')
      const revision = new URL(request.url).searchParams.get('revision')
      const r = await store.report(
        context.child,
        context.period,
        revision ? Number(revision) : undefined,
      )
      return {
        ...(isShared(context.child.id) ? r : { ...r, records: [], narrative: null, eveningQuestion: null }),
        revisions: r.revisions.map((revision) => ({ revision })),
        narrative: isShared(context.child.id) && r.narrative ? { text: r.narrative, source: 'TEMPLATE' } : null,
        verification: { numbersMatched: true, quotesMatched: true },
      }
    }),
  ),
  http.post('/api/v1/reports/:reportId/regenerate', ({ request, params }) =>
    respond(async () => {
      guard(request)
      const context = reports.get(id(params.reportId))!
      await store.regenerate(await store.report(context.child, context.period))
      return {}
    }, 202),
  ),
  http.post('/api/v1/conversations', ({ request }) =>
    respond(async () => {
      guard(request)
      const data = (await request.json()) as { childId: string; from: string; to: string }
      const conversationId = `msw-conversation-${++serial}`
      conversations.set(conversationId, {
        child: await linked(data.childId),
        period: { from: data.from, to: data.to },
      })
      return { conversationId }
    }, 201),
  ),
  http.post('/api/v1/conversations/:conversationId/messages', async ({ request, params }) => {
    try {
      guard(request)
    } catch (e) {
      return respond(async () => {
        throw e
      })
    }
    const data = (await request.json()) as { question: string },
      context = conversations.get(id(params.conversationId))!
    return sse(async (push) => {
      push('status', { state: 'RUNNING' })
      push('result', await store.analyze(context.child, context.period, data.question))
    })
  }),
  http.all('/api/v1/*', () =>
    HttpResponse.json(
      {
        status: 501,
        code: 'MOCK_NOT_IMPLEMENTED',
        title: '이 경로의 MSW 목업은 아직 없습니다.',
        retryable: false,
      },
      { status: 501 },
    ),
  ),
]
export const currentMockScenario = () => scenario
