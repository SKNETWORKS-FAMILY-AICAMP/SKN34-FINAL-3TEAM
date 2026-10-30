import { http, HttpResponse } from 'msw/http'
import { ApiError } from '../../data/apiClient.ts'
import { counts } from '../../domain/classroom.ts'
import type { Child, Period } from '../../domain/classroom.ts'
import type { Consent, ConsentDocument, ConsentHistory, Conversation, Scope } from '../../domain/parent.ts'
import { validPeriod } from '../../domain/parent.ts'
import { fixtureStore as store } from '../fixtures/student.ts'
import {
  mockAccounts,
  mockIdentity,
  mockAccountChildren,
  mockConsentHistory, mockConsentRequired, mockGuardianConsentRequired,
  workspaceScenario as mode,
} from '../fixtures/accounts.ts'
import {
  conversations,
  reports,
  regenerateCounts,
  pendingReports,
  scopedRows,
  evidence,
  thinking,
  ensureReports,
  makeWeekly,
  inclusionRule,
} from '../fixtures/parent.ts'
import { guard, respond, problem } from './student.ts'
export const page = <T>(items: T[]) => ({ items, page: 0, size: 20, totalElements: items.length })
export const fail = (code: string, title: string, status = 400, retryable = false): never => {
  throw new ApiError({ code, title, status, retryable })
}
export function parentGuard(request: Request) {
  guard(request)
  if (store.snapshot().session?.role !== 'PARENT')
    fail('FORBIDDEN', '학부모 권한이 필요합니다.', 403)
  if (!new URL(request.url).pathname.startsWith('/api/v1/me/consents') && mockConsentRequired())
    fail('CONSENT_REQUIRED', '필수 동의를 먼저 완료해 주세요.', 403)
}
export async function parentChild(request: Request, id: string) {
  parentGuard(request)
  if (mode === 'unlinked') fail('CHILD_NOT_LINKED', '연결되지 않은 자녀입니다.', 403)
  const c = (await store.children()).find((c) => c.id === id)
  if (!c || mockGuardianConsentRequired(id)) fail('CHILD_NOT_LINKED', '연결 또는 법정대리인 동의를 확인해 주세요.', 403)
  return c!
}
const docs: ConsentDocument[] = [
  {
    documentId: 'terms-v1',
    kind: 'TERMS',
    version: '1.0',
    title: '이용 안내',
    content: '가상 데이터로 학습 흐름을 확인하는 개발 시연입니다. 실제 개인정보를 입력하지 마세요.',
    required: true,
  },
  {
    documentId: 'privacy-v1',
    kind: 'PRIVACY',
    version: '1.0',
    title: '개인정보 처리 동의',
    content: '이 화면은 개발용 목업입니다. 운영 동의 문서는 법률·서비스 검토 후 확정해야 합니다.',
    required: true,
  },
  {
    documentId: 'guardian-v1',
    kind: 'GUARDIAN',
    version: '1.0',
    title: '법정대리인 동의',
    content:
      '만 14세 미만 자녀의 법정대리인임을 확인하고 자녀 정보 처리에 동의합니다. 개발 시연 문구입니다.',
    required: true,
  },
]
function fixtureConsent(document: ConsentDocument, studentId: string | null = null, agreed = true): ConsentHistory {
  const now = new Date().toISOString()
  return { consentId: `msw-consent-${crypto.randomUUID()}`, subjectUserId: mockIdentity.userId, studentId,
    document, agreed, status: agreed ? 'AGREED' : 'WITHDRAWN', agreedAt: now, withdrawnAt: agreed ? null : now }
}
async function consentRows() {
  let rows = mockConsentHistory.get(mockIdentity.email)
  if (!rows) {
    // Existing demo accounts/children are explicitly pre-consented synthetic fixtures.
    rows = docs.filter((d) => d.kind !== 'GUARDIAN').map((d) => fixtureConsent(d))
    for (const c of await store.children()) rows.push(fixtureConsent(docs.find((d) => d.kind === 'GUARDIAN')!, c.id))
    mockConsentHistory.set(mockIdentity.email, rows)
  }
  return rows
}
export function mockChildConsentMetadata(c: Child) {
  const blocked = mockGuardianConsentRequired(c.id)
  const hasRecords = store.snapshot().attempts.some((a) => a.studentId === c.id && a.answers.some((v) => v.feedback.status !== 'FAILED'))
  return { ...c, guardianConsentRequired: blocked, hasRecords: blocked ? null : hasRecords,
    recordState: blocked ? 'CONSENT_REQUIRED' as const : 'AVAILABLE' as const }
}
function consentCheck(consents: Consent[], guardian = false) {
  for (const d of docs.filter((d) => (guardian ? d.kind === 'GUARDIAN' : d.kind !== 'GUARDIAN')))
    if (
      !consents?.some((c) => c.documentId === d.documentId && c.version === d.version && c.agreed)
    )
      fail('VALIDATION_FAILED', `${d.title} 문서 버전과 동의 여부를 확인해 주세요.`)
}
function period(request: Request): Period {
  const q = new URL(request.url).searchParams,
    p = { from: q.get('from') ?? '2026-10-20', to: q.get('to') ?? '2026-10-26' }
  if (!validPeriod(p)) fail('VALIDATION_FAILED', '조회 기간을 확인해 주세요.')
  return p
}
function queryFault() {
  if (mode === 'query-fail')
    fail('QUERY_FAILED', '기록 조회에 실패했습니다. 기록 없음과는 다른 상태입니다.', 503, true)
}
const conv = (id: string) => {
  const c = conversations.get(id)
  if (!c) fail('NOT_FOUND', '대화를 찾을 수 없습니다.', 404)
  return c!
}
async function conversationGuard(request: Request, id: string) {
  const c = conv(id)
  const child = await parentChild(request, c.childId)
  if (request.method === 'POST' && child.plan !== 'PREMIUM')
    fail('USAGE_LIMIT_REACHED', '무료 플랜은 분석 대화를 제공하지 않습니다.', 429)
  return c
}
async function reportGuard(request: Request, id: string) {
  const versions = reports.get(id)
  if (!versions) fail('NOT_FOUND', '리포트를 찾을 수 없습니다.', 404)
  await parentChild(request, versions![0].childId)
  return versions!
}
function evidenceResponse(items: ReturnType<typeof evidence>) {
  if (mode === 'gone-evidence')
    fail('DATA_UNAVAILABLE', '이 근거는 삭제되어 이용할 수 없습니다.', 410)
  return { items }
}
const downloadTickets = new Map<string, { file: string; childId: string; expires: number }>()
const pinChallenges = new Map<string, { childId?: string; purpose?: string; scope?: string; bearer: string; expires: number }>()
const pinGrants = new Map<string, { childId?: string; purpose?: string; scope?: string; bearer: string; expires: number }>()
export function consumePinReauth(request: Request, childId: string) { return consumeActionReauth(request, 'PIN_CHANGE', childId) }
export function consumeActionReauth(request: Request, purpose: string, childId?: string, scope?: string) {
  const key = request.headers.get('X-Reauth-Token') ?? ''
  const grant = pinGrants.get(key)
  if (!grant || grant.purpose !== purpose || grant.childId !== childId || grant.scope !== scope || grant.bearer !== request.headers.get('Authorization') || grant.expires <= Date.now())
    fail('REAUTH_REQUIRED', '해당 자녀의 Google 재확인이 필요합니다.', 403)
  pinGrants.delete(key)
}
let reauthToken = '',
  reauthExpires = 0
export function requireReauth(request: Request) {
  if (
    !reauthToken ||
    Date.now() > reauthExpires ||
    request.headers.get('X-Reauth-Token') !== reauthToken
  )
    fail('REAUTH_REQUIRED', '중요 변경 전에 다시 확인해 주세요.', 403)
}
function streamMessage(
  request: Request,
  c: Conversation,
  data: { question: string; scope: Scope },
  retryId?: string,
) {
  const scope = { ...c.period, ...data.scope, childId: c.childId },
    messageId = retryId ?? crypto.randomUUID()
  let msg = c.messages.find((m) => m.messageId === messageId)
  if (!msg) {
    msg = { messageId, question: data.question, status: 'RUNNING', scope }
    c.messages.push(msg)
  } else {
    msg.status = 'RUNNING'
    msg.failureCode = undefined
    msg.answer = undefined
  }
  const message = msg,
    encoder = new TextEncoder()
  let stopped = false
  const stop = () => {
    stopped = true
    if (message.status === 'RUNNING') {
      message.status = 'FAILED'
      message.failureCode = 'STREAM_INTERRUPTED'
      message.retryable = true
    }
  }
  request.signal.addEventListener('abort', stop, { once: true })
  return new HttpResponse(
    new ReadableStream({
      async start(controller) {
        const push = (event: string, value: unknown) => {
          if (!stopped)
            controller.enqueue(
              encoder.encode(`event: ${event}\ndata: ${JSON.stringify(value)}\n\n`),
            )
        }
        try {
          push('status', { state: 'RUNNING', messageId, message: '기록을 조회하고 있습니다.' })
          if (mode === 'clarification' && !scope.changed) {
            push('clarification', {
              question: '어느 기간의 기록을 살펴볼까요?',
              options: [
                { label: '현재 선택 기간', scope: { ...scope, changed: true } },
                {
                  label: '지난주',
                  scope: {
                    childId: c.childId,
                    from: '2026-10-19',
                    to: '2026-10-25',
                    changed: true,
                  },
                },
              ],
            })
            message.status = 'COMPLETED'
            return
          }
          push('delta', { text: '대조 전 임시 문장입니다. 아직 확정되지 않았습니다.' })
          await new Promise((resolve) => setTimeout(resolve, mode === 'analysis-slow' ? 2500 : 120))
          if (stopped) return
          if (mode === 'analysis-fail' || mode === 'verification-error') {
            message.status = 'FAILED'
            message.failureCode =
              mode === 'verification-error' ? 'VERIFICATION_FAILED' : 'AI_UNAVAILABLE'
            message.retryable = true
            push('error', {
              messageId,
              status: 503,
              code: message.failureCode,
              title: '분석을 완료하지 못했습니다. 임시 문장은 폐기했습니다.',
              retryable: true,
            })
            return
          }
          const child = await parentChild(request, scope.childId),
            rows = scopedRows(child, scope),
            metrics = counts(rows, scope)
          const actualScope =
            mode === 'scope-change'
              ? { ...scope, from: '2026-10-19', to: '2026-10-25', changed: true }
              : scope
          const actualRows = scopedRows(child, actualScope),
            actualMetrics = counts(actualRows, actualScope)
          const result = {
            messageId,
            answer: `조회한 집계 대상 기록은 ${actualMetrics[0].count}건입니다. 기록에 남은 생각만 살펴보며 사고력 수준을 진단하지 않습니다.`,
            scope: actualScope,
            metrics: mode === 'scope-change' ? actualMetrics : metrics,
            evidence: evidence(mode === 'scope-change' ? actualRows : rows),
            recordCount: actualRows.length,
            source: 'TEMPLATE' as const,
            verification: { numbersMatched: true, quotesMatched: true },
            ...(mode === 'verification-fallback'
              ? { fallback: { reason: 'VERIFICATION_FAILED' } }
              : {}),
          }
          Object.assign(message, result, { status: 'COMPLETED' })
          c.period = { from: actualScope.from, to: actualScope.to }
          push('result', result)
        } catch (e) {
          message.status = 'FAILED'
          message.failureCode = 'QUERY_FAILED'
          message.retryable = true
          push('error', { ...problem(e), messageId })
        } finally {
          if (!stopped) {
            push('done', {})
            controller.close()
          }
          request.signal.removeEventListener('abort', stop)
        }
      },
      cancel: stop,
    }),
    { headers: { 'Content-Type': 'text/event-stream' } },
  )
}
export const parentHandlers = [
  http.get('/api/v1/consent-documents', () => HttpResponse.json(page(docs))),
  http.get('/api/v1/me/consents', ({ request }) => respond(async () => {
    parentGuard(request)
    return page(await consentRows())
  })),
  http.post('/api/v1/me/consents', ({ request }) => respond(async () => {
    parentGuard(request)
    const d = await request.json() as { childId?: string; consents: Consent[] }
    if (d.childId && !(await store.children()).some((c) => c.id === d.childId)) fail('CHILD_NOT_LINKED', '연결되지 않은 자녀입니다.', 403)
    const expected = docs.filter((doc) => d.childId ? doc.kind === 'GUARDIAN' : doc.kind !== 'GUARDIAN')
    if (d.consents.some((c) => !expected.some((doc) => doc.documentId === c.documentId && doc.version === c.version)))
      fail('CONSENT_DOCUMENT_CHANGED', '현재 문서를 다시 확인해 주세요.', 409)
    if (d.consents.length !== expected.length || new Set(d.consents.map((c) => c.documentId)).size !== d.consents.length)
      fail('VALIDATION_FAILED', '동의 항목을 확인해 주세요.')
    consentCheck(d.consents, !!d.childId)
    const rows = await consentRows()
    const selected = expected.map((doc) => {
      const agreed = d.consents.find((c) => c.documentId === doc.documentId)!.agreed
      const current = rows.find((c) => c.document.documentId === doc.documentId && c.studentId === (d.childId ?? null))
      if (current && current.agreed === agreed && current.status === (agreed ? 'AGREED' : 'WITHDRAWN')) return current
      const entry = fixtureConsent(doc, d.childId ?? null, agreed); rows.unshift(entry); return entry
    })
    return page(selected)
  })),
  http.post('/api/v1/me/consents/:consentId/withdrawal', ({ request, params }) => respond(async () => {
    parentGuard(request)
    const entry = (await consentRows()).find((c) => c.consentId === params.consentId)
    if (!entry) fail('FORBIDDEN', '본인의 동의만 철회할 수 있습니다.', 403)
    if (entry!.status !== 'WITHDRAWN') { entry!.status = 'WITHDRAWN'; entry!.withdrawnAt = new Date().toISOString() }
    return entry!
  })),
  http.post('/api/v1/auth/signup', ({ request }) =>
    respond(async () => {
      const d = (await request.json()) as {
        email: string
        password: string
        name: string
        consents: Consent[]
      }
      consentCheck(d.consents)
      if (!d.email.endsWith('@example.test') || !d.password || !d.name.trim())
        fail('VALIDATION_FAILED', '시연에는 example.test 이메일·이름·비밀번호가 필요합니다.')
      if (mockAccounts.has(d.email)) fail('VALIDATION_FAILED', '이미 등록된 시연 이메일입니다.')
      mockAccounts.add(d.email)
      mockIdentity.name = d.name
      mockAccountChildren.set(d.email, [])
      mockConsentHistory.set(d.email, docs.filter((doc) => doc.kind !== 'GUARDIAN').map((doc) => fixtureConsent(doc)))
      return { userId: crypto.randomUUID() }
    }, 201),
  ),
  http.get('/api/v1/children', ({ request }) =>
    respond(async () => {
      parentGuard(request)
      queryFault()
      return page(
        mode === 'no-children'
          ? []
          : (await store.children()).map((c) => ({ ...mockChildConsentMetadata(c), childId: c.id })),
      )
    }),
  ),
  http.post('/api/v1/children', ({ request }) =>
    respond(async () => {
      parentGuard(request)
      const d = (await request.json()) as Child & { consents: Consent[] }
      consentCheck(d.consents, true)
      const children = await store.children()
      if (children.length >= 3)
        fail('CHILD_LIMIT_REACHED', '자녀는 최대 3명까지 등록할 수 있습니다.', 409)
      if (
        !d.nickname.trim() ||
        !Number.isInteger(d.grade) ||
        d.grade < 3 ||
        d.grade > 6 ||
        !Number.isInteger(d.birthYear) ||
        d.birthYear < 1900 ||
        d.birthYear > 2026
      )
        fail('VALIDATION_FAILED', '별명·지원 학년·출생연도를 확인해 주세요.')
      const rows = await consentRows()
      const c: Child = {
        id: crypto.randomUUID(),
        nickname: d.nickname,
        grade: d.grade,
        birthYear: d.birthYear,
        plan: 'FREE',
      }
      rows.unshift(fixtureConsent(docs.find((doc) => doc.kind === 'GUARDIAN')!, c.id))
      store.replaceChildren([...children, c])
      mockAccountChildren.set(mockIdentity.email, structuredClone([...children, c]))
      return c
    }, 201),
  ),
  http.patch('/api/v1/children/:childId', ({ request, params }) =>
    respond(async () => {
      const c = await parentChild(request, String(params.childId))
      // nickname·grade 모두 선택, 그 밖의 필드는 거부 (core-service.yaml PATCH /children/{childId})
      const d = (await request.json()) as { nickname?: unknown; grade?: unknown }
      const nickname = typeof d.nickname === 'string' ? d.nickname.trim() : undefined
      if (
        Object.keys(d).some((k) => k !== 'nickname' && k !== 'grade') ||
        (d.nickname !== undefined && (!nickname || nickname.length > 40)) ||
        (d.grade !== undefined && (!Number.isInteger(d.grade) || Number(d.grade) < 3 || Number(d.grade) > 6))
      )
        fail('VALIDATION_FAILED', '별명·지원 학년을 확인해 주세요.')
      const updated = {
        ...c,
        ...(nickname !== undefined ? { nickname } : {}),
        ...(d.grade !== undefined ? { grade: Number(d.grade) } : {}),
      }
      store.replaceChildren((await store.children()).map((v) => (v.id === c.id ? updated : v)))
      mockAccountChildren.set(mockIdentity.email, structuredClone(await store.children()))
      return updated
    }),
  ),
  http.patch('/api/v1/me', ({ request }) =>
    respond(async () => {
      parentGuard(request)
      const d = (await request.json()) as { name: string }
      if (!d.name.trim()) fail('VALIDATION_FAILED', '이름을 입력해 주세요.')
      mockIdentity.name = d.name
      return { ...mockIdentity, role: 'PARENT' }
    }),
  ),
  http.post('/api/v1/me/reauth', ({ request }) =>
    respond(async () => {
      parentGuard(request)
      const body = (await request.json()) as { password?: string; purpose?: string; childId?: string; challengeId?: string; scope?: string }
      const bearer = request.headers.get('Authorization') ?? ''
      if (body.purpose && ['PIN_CHANGE','CHILD_UNLINK','CHILD_DELETE','WITHDRAWAL'].includes(body.purpose)) {
        if (body.purpose !== 'WITHDRAWAL') { if (!body.childId) fail('VALIDATION_FAILED','대상 자녀가 필요합니다.',422); await parentChild(request, body.childId!) }
        if (body.purpose==='CHILD_DELETE' && !['PROFILE','RECORDS'].includes(body.scope ?? '')) fail('VALIDATION_FAILED','삭제 범위가 필요합니다.',422)
        const challengeId = crypto.randomUUID()
        pinChallenges.set(challengeId, { childId: body.childId, purpose:body.purpose,scope:body.scope,bearer,expires:Date.now()+600000 })
        // DEV MSW only: Google proof is a test double, never an actual Google verification.
        return { challengeId, authorizationUrl: '/login?reauthMock=1', expiresAt: new Date(Date.now() + 600000).toISOString() }
      }
      if (body.challengeId) {
        const value = pinChallenges.get(body.challengeId)
        if (!value || value.bearer !== bearer || value.expires <= Date.now()) fail('REAUTH_REQUIRED', '재확인을 다시 시작해 주세요.', 403)
        pinChallenges.delete(body.challengeId)
        const reauthToken = crypto.randomUUID(), expires = Date.now() + 300000
        pinGrants.set(reauthToken, { ...value!, expires })
        return { reauthToken, expiresAt: new Date(expires).toISOString() }
      }
      const { password } = body
      if (password !== 'demo-only') fail('UNAUTHENTICATED', '시연 비밀번호를 확인해 주세요.', 401)
      reauthToken = crypto.randomUUID()
      reauthExpires = Date.now() + 300000
      return { reauthToken, expiresAt: new Date(reauthExpires).toISOString() }
    }),
  ),
  http.get('/api/v1/children/:childId/summary', ({ request, params }) =>
    respond(async () => {
      const c = await parentChild(request, String(params.childId))
      queryFault()
      const p = period(request),
        metrics = counts(scopedRows(c, p), p)
      return { childId: c.id, period: p, state: metrics[0].state, inclusionRule, metrics }
    }),
  ),
  http.get('/api/v1/children/:childId/thinking-types', ({ request, params }) =>
    respond(async () => {
      const c = await parentChild(request, String(params.childId))
      queryFault()
      const p = period(request)
      return {
        childId: c.id,
        period: p,
        state: scopedRows(c, p).length ? 'OK' : 'NO_RECORD',
        items: thinking(c, p),
      }
    }),
  ),
  http.get('/api/v1/children/:childId/attempts', ({ request, params }) =>
    respond(async () => {
      const c = await parentChild(request, String(params.childId))
      queryFault()
      const p = period(request),
        rows = scopedRows(c, p)
      const query = new URL(request.url).searchParams
      const index = Number(query.get('page') ?? 0), size = Number(query.get('size') ?? 20)
      if (!Number.isInteger(index) || index < 0 || !Number.isInteger(size) || size < 1 || size > 100) fail('VALIDATION_FAILED', '페이지를 확인해 주세요.')
      return {
        items: rows.slice(index * size, (index + 1) * size), page: index, size, totalElements: rows.length,
        childId: c.id,
        state: rows.length ? 'OK' : 'NO_RECORD',
        period: p,
        inclusionRule,
      }
    }),
  ),
  http.get('/api/v1/children/:childId/attempts/:attemptId', ({ request, params }) =>
    respond(async () => {
      const c = await parentChild(request, String(params.childId))
      const a = store
        .snapshot()
        .attempts.find((a) => a.attemptId === params.attemptId && a.studentId === c.id)
      if (!a) fail('NOT_FOUND', '기록을 찾을 수 없습니다.', 404)
      const { draft: _private, ...visible } = a!
      return { ...visible, state: 'OK', period: period(request) }
    }),
  ),
  http.get('/api/v1/conversations', ({ request }) =>
    respond(async () => {
      const childId = new URL(request.url).searchParams.get('childId') ?? ''
      await parentChild(request, childId)
      queryFault()
      return page([...conversations.values()].filter((c) => c.childId === childId))
    }),
  ),
  http.post('/api/v1/conversations', ({ request }) =>
    respond(async () => {
      const scope = (await request.json()) as Scope,
        c = await parentChild(request, scope.childId)
      if (c.plan !== 'PREMIUM')
        fail('USAGE_LIMIT_REACHED', '무료 플랜은 분석 대화를 제공하지 않습니다.', 429)
      if (!validPeriod(scope)) fail('VALIDATION_FAILED', '기간을 확인해 주세요.')
      const v: Conversation = {
        conversationId: crypto.randomUUID(),
        childId: c.id,
        period: { from: scope.from, to: scope.to },
        title: '새 분석 대화',
        createdAt: new Date().toISOString(),
        messages: [],
      }
      conversations.set(v.conversationId, v)
      return v
    }, 201),
  ),
  http.get('/api/v1/conversations/:conversationId', ({ request, params }) =>
    respond(() => conversationGuard(request, String(params.conversationId))),
  ),
  http.post('/api/v1/conversations/:conversationId/messages', async ({ request, params }) => {
    try {
      const c = await conversationGuard(request, String(params.conversationId)),
        d = (await request.json()) as { question: string; scope: Scope }
      if (!d.question.trim()) fail('VALIDATION_FAILED', '질문을 입력해 주세요.')
      await parentChild(request, d.scope.childId)
      if (!validPeriod(d.scope)) fail('VALIDATION_FAILED', '기간을 확인해 주세요.')
      if (d.scope.childId !== c.childId)
        fail('VALIDATION_FAILED', '다른 자녀는 새 대화에서 질문해 주세요.')
      return streamMessage(request, c, d)
    } catch (e) {
      return respond(async () => {
        throw e
      })
    }
  }),
  http.post(
    '/api/v1/conversations/:conversationId/messages/:messageId/retry',
    async ({ request, params }) => {
      try {
        const c = await conversationGuard(request, String(params.conversationId)),
          m = c.messages.find((m) => m.messageId === params.messageId)
        if (!m || m.status !== 'FAILED')
          fail('VALIDATION_FAILED', '실패한 메시지만 재시도할 수 있습니다.')
        return streamMessage(request, c, { question: m!.question, scope: m!.scope! }, m!.messageId)
      } catch (e) {
        return respond(async () => {
          throw e
        })
      }
    },
  ),
  http.get(
    '/api/v1/conversations/:conversationId/messages/:messageId/evidence',
    ({ request, params }) =>
      respond(async () => {
        const c = await conversationGuard(request, String(params.conversationId)),
          m = c.messages.find((m) => m.messageId === params.messageId)
        if (!m) fail('NOT_FOUND', '메시지를 찾을 수 없습니다.', 404)
        const es = m!.evidence ?? []
        return evidenceResponse(
          es.map((e) =>
            mode === 'deleted-evidence' ? { ...e, available: false, quote: undefined } : e,
          ),
        )
      }),
  ),
  http.get('/api/v1/children/:childId/reports', ({ request, params }) =>
    respond(async () => {
      const c = await parentChild(request, String(params.childId))
      queryFault()
      const status = new URL(request.url).searchParams.get('status')
      // 리포트 목록은 페이지 없이 {items}만 반환한다(api-spec 1.1·5.5, ReportList).
      return {
        items: ensureReports(c)
          .map((r) => ({
            ...r,
            status:
              mode === 'report-running'
                ? 'RUNNING'
                : mode === 'report-failed'
                  ? 'FAILED'
                  : r.status,
          }))
          .filter((r) => !status || r.status === status),
      }
    }),
  ),
  http.get('/api/v1/reports/:reportId', ({ request, params }) =>
    respond(async () => {
      const id = String(params.reportId),
        versions = await reportGuard(request, id),
        rev = new URL(request.url).searchParams.get('revision'),
        r = rev ? versions.find((r) => r.revision === Number(rev)) : versions.at(-1)
      if (!r) fail('NOT_FOUND', '이전 판을 찾을 수 없습니다.', 404)
      const pending = pendingReports.get(id)
      if (pending && Date.now() < pending) return { ...r, status: 'RUNNING' }
      pendingReports.delete(id)
      const c = await parentChild(request, r!.childId)
      const recomputed =
        mode === 'empty' || mode === 'small' ? makeWeekly(c, r!.period, r!.revision) : r!
      return {
        ...recomputed,
        revisions: versions.map((v) => ({ revision: v.revision, generatedAt: v.generatedAt })),
        status:
          mode === 'report-running' ? 'RUNNING' : mode === 'report-failed' ? 'FAILED' : r!.status,
      }
    }),
  ),
  http.post('/api/v1/reports/:reportId/regenerate', ({ request, params }) =>
    respond(async () => {
      const id = String(params.reportId),
        versions = await reportGuard(request, id)
      if ((regenerateCounts.get(id) ?? 0) >= 1)
        fail('REPORT_REGENERATION_LIMIT', '학부모 재생성은 리포트당 한 번만 가능합니다.', 409)
      const prev = versions.at(-1)!,
        c = await parentChild(request, prev.childId),
        next = makeWeekly(c, prev.period, prev.revision + 1)
      versions.push(next)
      regenerateCounts.set(id, 1)
      pendingReports.set(id, Date.now() + 1400)
      return { reportId: id, status: 'QUEUED' }
    }, 202),
  ),
  http.get('/api/v1/reports/:reportId/evidence/:itemId', ({ request, params }) =>
    respond(async () => {
      const versions = await reportGuard(request, String(params.reportId)),
        r = versions.at(-1)!,
        c = await parentChild(request, r.childId),
        rows = scopedRows(c, r.period),
        key = String(params.itemId)
      return evidenceResponse(
        evidence(
          rows.filter(
            (a) => key.startsWith('metric-') || key === a.attemptId || key.endsWith(a.attemptId),
          ),
        ),
      )
    }),
  ),
  http.get('/api/v1/reports/:reportId/download', ({ request, params }) =>
    respond(async () => {
      const versions = await reportGuard(request, String(params.reportId))
      if (
        versions.at(-1)!.status !== 'COMPLETED' ||
        mode === 'report-running' ||
        mode === 'report-failed'
      )
        fail('VALIDATION_FAILED', '완료된 리포트만 내려받을 수 있습니다.')
      const format = new URL(request.url).searchParams.get('format')
      if (!['pdf', 'md'].includes(format ?? ''))
        fail('VALIDATION_FAILED', '파일 형식을 확인해 주세요.')
      if ((pendingReports.get(String(params.reportId)) ?? 0) > Date.now())
        fail('VALIDATION_FAILED', '재생성 중에는 파일을 내려받을 수 없습니다.')
      const ticket = crypto.randomUUID(),
        file = `${params.reportId}.${format}`,
        expires = Date.now() + 300000
      downloadTickets.set(ticket, { file, childId: versions.at(-1)!.childId, expires })
      return {
        url: `/api/v1/mock-report-files/${file}?ticket=${ticket}`,
        expiresAt: new Date(expires).toISOString(),
      }
    }),
  ),
  // 개발 다운로드만 동일 mock API를 사용한다. 운영은 서버의 단기 URL을 그대로 따른다.
  http.get('/api/v1/mock-report-files/:file', ({ request, params }) => {
    const file = String(params.file),
      id = file.replace(/\.(pdf|md)$/, ''),
      r = reports.get(id)?.at(-1)
    if (!r) return new HttpResponse(null, { status: 404 })
    const ticket = downloadTickets.get(new URL(request.url).searchParams.get('ticket') ?? '')
    if (
      !ticket ||
      ticket.file !== file ||
      ticket.expires <= Date.now() ||
      store.snapshot().session?.role !== 'PARENT' ||
      !store.snapshot().children?.some((c) => c.id === ticket.childId) ||
      mode === 'unlinked'
    )
      return new HttpResponse(null, { status: 403 })
    const text =
      `SAGOMUNGCHI - MOCK REPORT ONLY\nChild: ${r.childId}\nPeriod: ${r.period.from} - ${r.period.to}\nRevision: ${r.revision}\n` +
      r.metrics
        .map(
          (m, i) =>
            `Metric ${i + 1}: count ${m.count}, numerator ${m.numerator}, denominator ${m.denominator}`,
        )
        .join('\n')
    if (file.endsWith('.md'))
      return new HttpResponse(text, {
        headers: {
          'Content-Type': 'text/markdown; charset=utf-8',
          'Content-Disposition': `attachment; filename="mock-report.md"`,
        },
      })
    return new HttpResponse(mockPdf(text), {
      headers: {
        'Content-Type': 'application/pdf',
        'Content-Disposition': 'attachment; filename="mock-report.pdf"',
      },
    })
  }),
]
function mockPdf(text: string) {
  const stream =
    'BT /F1 12 Tf 50 770 Td ' +
    text
      .split('\n')
      .map((line, i) => `${i ? '0 -18 Td ' : ''}(${line.replace(/[()\\]/g, '\\$&')}) Tj`)
      .join('\n') +
    ' ET'
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
  ]
  let pdf = '%PDF-1.4\n'
  const offsets = [0]
  objects.forEach((s, i) => {
    offsets.push(pdf.length)
    pdf += `${i + 1} 0 obj\n${s}\nendobj\n`
  })
  const start = pdf.length
  pdf +=
    `xref\n0 6\n0000000000 65535 f \n` +
    offsets
      .slice(1)
      .map((n) => `${String(n).padStart(10, '0')} 00000 n \n`)
      .join('') +
    `trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${start}\n%%EOF`
  return pdf
}
