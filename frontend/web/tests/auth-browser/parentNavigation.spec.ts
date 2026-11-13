import { test, expect } from '@playwright/test'
import type { BrowserContext, Page } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import type { Conversation, ConversationMessage, WeeklyReport } from '../../src/domain/parent.ts'

const childId = '00000000-0000-4000-8000-000000000001'
const otherId = '00000000-0000-4000-8000-000000000002'

async function parentServer(context: BrowserContext, periodType: 'DAILY' | 'WEEKLY' = 'DAILY', withHighlights = false) {
  const children = [childId, otherId].map((id, index) => ({ id, nickname: index ? '달빛' : '별빛', grade: 3, birthYear: 2017, pinSet: false, pinLocked: false }))
  // 이용권은 /children이 아니라 entitlement로만 내려온다(#602).
  const entitlement = { product: { id: 'premium', code: 'PREMIUM', name: '프리미엄', price: 14900, billingCycle: 'MONTHLY', childLimit: 1, active: true, features: {}, limits: { dailyMissions: 5 } }, status: 'ACTIVE', autoRenew: false, refundPending: false, conversationEnabled: true, narrativeEnabled: true }
  const period = { from: '2026-11-09', to: periodType === 'DAILY' ? '2026-11-09' : '2026-11-15' }
  const report: WeeklyReport = { reportId: 'report-1', childId, period, periodType, revision: 1, status: 'COMPLETED', state: 'OK', parentSharingEnabled: true,
    revisions: [{ revision: 1 }], inclusionRule: '합성 리포트 검증 자료', metrics: [], thinkingTypes: [], changes: [], reflections: [], quotes: [], problems: [], narrative: null, verification: { numbersMatched: true, quotesMatched: true } }
  const controls = { evidenceAvailable: true, evidenceFails: false, latestRevision: 1, omitSources: false, waitForReply: null as Promise<void> | null }
  const metric = { label: '답변 제출 시도 수', formula: '집계 대상 시도 수', period, count: 6, numerator: 6, denominator: 6, value: null, sourceType: 'RECORD' as const, state: 'OK' as const }
  if (withHighlights) {
    report.metrics = [metric, { ...metric, label: '다른 활동', formula: '다른 집계 기준' }]
    report.problems = [{ missionId: 'mission-1', attemptId: 'attempt-1', title: '나무는 어떤 도움을 줄까요?', context: 'EXTRA', judgment: 'CORRECT',
      finalAnswer: '나무가 그늘을 만들어 줍니다.', followups: [], elements: [], reflection: null,
      quotes: [{ answerId: 'answer-1', text: '나무가 그늘을 만들어 줍니다.', verified: true }] }]
    report.quotes = [{ attemptId: 'attempt-1', answerId: 'answer-1', text: '나무가 그늘을 만들어 줍니다.', verified: true }]
  }
  const calls: { path: string; method: string; body: Record<string, unknown> | null; proof?: string }[] = []
  let settings = { items: [{ type: 'REPORT_COMPLETED', enabled: true }] }
  const conversation: Conversation = { conversationId: 'conversation-1', childId, period, title: '학습 질문', createdAt: '2026-11-10T00:00:00Z', messages: [] }
  await context.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
  await context.route('**/api/v1/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname.replace('/api/v1', '')
    const body = request.postData() ? request.postDataJSON() : null
    calls.push({ path, method: request.method(), body, proof: request.headers()['x-reauth-token'] })
    const json = (value: unknown, status = 200) => route.fulfill({ status, json: value })
    if (path === '/auth/refresh') return json({ role: 'PARENT', accessToken: 'synthetic-parent', expiresIn: 900 })
    if (path === '/me') return json({ role: 'PARENT', authMethod: 'GOOGLE', name: '합성 보호자', email: 'parent@example.test', nextAction: 'READY', startPath: '/parent/journal' })
    if (path === '/children') return json({ items: children })
    if (path.endsWith('/sharing-preferences')) return json({ studentId: path.split('/')[2], parentSharingEnabled: true })
    if (path.endsWith('/entitlement')) return json({ ...entitlement, childId: path.split('/')[2] })
    if (path === '/notifications') return json({ items: [{ id: 'notification-1', childId, type: 'REPORT_COMPLETED', title: '리포트가 준비됐어요', link: `/parent/report?childId=${childId}`, readAt: null, createdAt: '2026-11-10T00:00:00Z' }], page: 0, size: 20, hasNext: false })
    if (path === '/notifications/stream') return route.abort('failed')
    if (path === '/notification-settings') {
      if (request.method() === 'PUT') settings = body
      return json(settings)
    }
    if (path === '/student-devices') return json({ items: [] })
    if (path === '/me/guardian-password') return json({ set: false, locked: false })
    if (path.endsWith('/pin') && request.method() === 'PUT') {
      children.find(child => child.id === path.split('/')[2])!.pinSet = true
      return route.fulfill({ status: 204 })
    }
    if (path === '/consent-documents' || path === '/me/consents') return json({ items: [] })
    if (path === `/children/${childId}/reports`) return json({ items: [report] })
    if (path === '/reports/report-1') return json({ ...report, revision: Number(url.searchParams.get('revision') ?? controls.latestRevision) })
    if (path === '/conversations') {
      if (request.method() === 'POST' && body.reportId) { conversation.reportId = body.reportId; conversation.reportRevision = controls.latestRevision }
      return json(request.method() === 'POST' ? conversation : { items: [] })
    }
    if (path.match(/^\/conversations\/conversation-1\/messages\/[^/]+\/evidence$/)) return controls.evidenceFails
      ? json({ status: 503, code: 'UNAVAILABLE', title: '현재 답변 근거를 불러오지 못했습니다.' }, 503)
      : json({ items: [{ attemptId: 'attempt-1', answerId: 'answer-1', kind: 'ANSWER', available: controls.evidenceAvailable, quote: controls.evidenceAvailable ? '나무가 그늘을 만들어 줍니다.' : null }] })
    if (path === '/conversations/conversation-1') return json(conversation)
    if (path === '/conversations/conversation-1/messages') {
      if (controls.waitForReply) await controls.waitForReply
      const result: ConversationMessage = { messageId: `message-${conversation.messages.length + 1}`, question: body.question, status: 'COMPLETED', answer: '합성 기록으로 확인한 답변입니다.', source: 'LLM',
        scope: { childId, ...period, changed: false }, recordCount: 6, metrics: withHighlights && !controls.omitSources ? [metric] : [], evidence: withHighlights && !controls.omitSources ? [{ attemptId: 'attempt-1', answerId: 'answer-1', available: false }] : [], verification: { numbersMatched: true, quotesMatched: true, contentAllowed: true } }
      conversation.messages.push(result)
      return route.fulfill({ contentType: 'text/event-stream', body: 'event: result\ndata: ' + JSON.stringify(result) + '\n\nevent: done\ndata: {}\n\n' })
    }
    if (path === '/agent/example-questions') return json({ items: [] })
    if (path.endsWith('/summary')) return json({ childId, period, state: 'NO_RECORD', metrics: [] })
    if (path.endsWith('/thinking-types')) return json({ childId, state: 'NO_RECORD', items: [] })
    if (path.endsWith('/attempts')) return json({ childId, items: [], page: 0, size: 20, totalElements: 0 })
    return json({ status: 404, code: 'NOT_FOUND', title: '합성 검사에 없는 요청입니다.' }, 404)
  })
  return { calls, period, controls, report, children, entitlement }
}

async function capture(page: Page, name: string) {
  const out = '.taste-skill/parent-navigation'
  await mkdir(out, { recursive: true })
  await page.evaluate(async () => Promise.all([...document.images].filter(img => new URL(img.src).origin === location.origin).map(async img => {
    const blob = await (await fetch(img.src)).blob()
    img.src = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = () => reject(reader.error); reader.readAsDataURL(blob) })
  })))
  const css = await page.evaluate(async () => Promise.all([...document.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"]')].filter(link => new URL(link.href).origin === location.origin).map(async link => (await fetch(link.href)).text())))
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
    const html = (await page.content()).replace(/<script\b[\s\S]*?<\/script>/gi, '').replace(/<link\b[^>]*rel="stylesheet"[^>]*>/gi, '').replace('<head>', '<head>' + css.map(value => '<style>' + value + '</style>').join(''))
    await writeFile(`${out}/${name}-${width}.html`, html)
    await page.screenshot({ path: `${out}/${name}-${width}.png`, fullPage: true })
  }
}

test('로고는 홈으로 연결하고 자녀 추가는 계정·자녀 설정에서만 연다', async ({ page, context }) => {
  await parentServer(context)
  await page.goto(`/parent/settings?childId=${childId}&from=2026-11-01&to=2026-11-09`)
  await expect(page.locator('.ws-header').getByRole('button', { name: '자녀 추가 등록', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '자녀 추가 등록', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '자녀 프로필 등록' })).toBeVisible()
  await page.getByRole('button', { name: '창 닫기' }).click()
  await page.getByRole('link', { name: '사고뭉치 홈', exact: true }).filter({ visible: true }).click()
  await expect(page).toHaveURL(/\/parent\/journal/)
  expect(new URL(page.url()).searchParams.get('from')).toBe('2026-11-01')
})

test('PIN 자녀는 알약으로 한 명만 고르고 Google 없이 선택한 자녀에게 저장한다', async ({ page, context }) => {
  const state = await parentServer(context)
  await page.goto(`/parent/devices?childId=${childId}`)
  const picker = page.getByRole('tablist', { name: 'PIN 설정할 자녀' })
  await expect(page.locator('.ws-header').getByLabel('자녀 선택')).toHaveCount(0)
  await expect(page.getByRole('form', { name: / PIN$/ })).toHaveCount(1)
  await page.getByLabel('별빛 새 PIN', { exact: true }).fill('5090')
  await picker.getByRole('tab', { name: '달빛' }).click()
  await expect(page.getByLabel('달빛 새 PIN', { exact: true })).toHaveValue('')
  const form = page.getByRole('form', { name: '달빛 PIN', exact: true })
  await form.getByLabel('달빛 새 PIN', { exact: true }).fill('4831')
  await form.getByLabel('달빛 새 PIN 확인', { exact: true }).fill('4831')
  await form.getByRole('button', { name: 'PIN 정하기', exact: true }).click()
  await expect(form.getByRole('status')).toContainText('달빛의 PIN을 저장했습니다.')
  const write = state.calls.find(call => call.path.endsWith('/pin') && call.method === 'PUT')!
  expect(write.path).toBe(`/children/${otherId}/pin`); expect(write.proof).toBeUndefined()
  expect(state.calls.some(call => call.path.includes('/reauth'))).toBe(false)
  await capture(page, 'pin')
})

test('상단 오른쪽 알림과 로그아웃 순서를 유지하고 수신 설정을 저장한다', async ({ page, context }) => {
  const state = await parentServer(context)
  await page.goto(`/parent/settings?childId=${childId}`)
  const bell = page.getByRole('button', { name: '알림 열기', exact: true })
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 900 })
    const box = await bell.boundingBox()
    const logout = await page.locator('.ws-header .ws-logout').boundingBox()
    expect(box!.x + box!.width).toBeLessThanOrEqual(logout!.x)
  }
  await bell.click()
  const dialog = page.getByRole('dialog', { name: '알림', exact: true })
  await dialog.getByRole('button', { name: '수신 설정', exact: true }).click()
  await dialog.getByRole('checkbox', { name: '리포트 생성 완료', exact: true }).uncheck()
  await dialog.getByRole('button', { name: '설정 저장', exact: true }).click()
  await expect(dialog.getByRole('status')).toHaveText('수신 설정을 저장했습니다.')
  expect(state.calls.find(call => call.path === '/notification-settings' && call.method === 'PUT')?.body).toEqual({ items: [{ type: 'REPORT_COMPLETED', enabled: false }] })
  await capture(page, 'notifications')
  await page.keyboard.press('Escape'); await expect(dialog).toHaveCount(0); await expect(bell).toBeFocused()
  await bell.click()
  await dialog.getByRole('button', { name: '수신 설정', exact: true }).click()
  await expect(dialog.getByRole('checkbox', { name: '리포트 생성 완료', exact: true })).not.toBeChecked()
  await dialog.getByRole('button', { name: '알림 목록', exact: true }).click()
  await dialog.getByRole('link', { name: '관련 내용 열기', exact: true }).click()
  await expect(dialog).toHaveCount(0); await expect(page).toHaveURL(/\/parent\/report/)
})

for (const periodType of ['DAILY', 'WEEKLY'] as const) test(`${periodType} 리포트에서 같은 챗봇에 자녀·기간을 연결하고 답변을 확인한다`, async ({ page, context }) => {
  const state = await parentServer(context, periodType)
  await page.goto(`/parent/report?childId=${childId}`)
  await expect(page.getByRole('link', { name: 'AI 챗봇', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '리포트 상세 보기', exact: true }).click()
  await page.getByRole('button', { name: '이 리포트로 질문하기', exact: true }).click()
  await expect(page.getByRole('button', { name: 'AI에게 질문하기', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await page.getByLabel('기록에 대한 질문', { exact: true }).fill('어떤 활동을 했나요?')
  await page.getByRole('button', { name: '질문 보내기', exact: true }).click()
  await expect(page.getByText('합성 기록으로 확인한 답변입니다.', { exact: true })).toBeVisible()
  const request = state.calls.find(call => call.path === '/conversations' && call.method === 'POST')!
  expect(request.body).toEqual(periodType === 'DAILY' ? { childId, reportId: 'report-1' } : { childId, ...state.period })
  await page.getByRole('button', { name: '리포트 보기', exact: true }).click()
  await expect(page.getByRole('heading', { name: /리포트 상세$/ })).toBeVisible()
  if (periodType === 'DAILY') {
    await capture(page, 'report')
    await page.getByRole('button', { name: 'AI에게 질문하기', exact: true }).click()
    await expect(page.getByText(/^질문할 기간 ·/)).not.toBeVisible()
    await page.getByRole('button', { name: '전체 기록으로 질문하기', exact: true }).click()
    await expect(page.getByText(/^질문할 기간 ·/)).toBeVisible()
  }
})

async function askReport(page: Page) {
  await page.goto(`/parent/report?childId=${childId}`)
  await page.getByRole('button', { name: '리포트 상세 보기', exact: true }).click()
  await page.getByRole('button', { name: '이 리포트로 질문하기', exact: true }).click()
  await page.getByLabel('기록에 대한 질문', { exact: true }).fill('어떤 활동을 했나요?')
  await page.getByRole('button', { name: '질문 보내기', exact: true }).click()
}

for (const periodType of ['DAILY', 'WEEKLY'] as const) test(`${periodType} 답변의 지표와 현재 열람 가능한 원문 위치만 초록 테두리로 연결한다`, async ({ page, context }) => {
  const state = await parentServer(context, periodType, true)
  await askReport(page)
  const marked = page.locator('[data-answer-highlight=true]')
  await expect(marked).toHaveCount(2)
  await expect(marked.filter({ hasText: '답변 제출 시도 수' })).toHaveCount(1)
  await expect(marked.filter({ hasText: '나무가 그늘을 만들어 줍니다.' })).toHaveCount(1)
  await expect(marked.filter({ hasText: '다른 활동' })).toHaveCount(0)
  await expect(marked.first()).toHaveCSS('outline-color', 'rgb(39, 112, 68)')
  expect(state.calls.some(call => call.path.endsWith('/message-1/evidence'))).toBe(true)
  if (periodType === 'DAILY') await capture(page, 'report-highlight')
  await page.getByRole('button', { name: '새 대화', exact: true }).click()
  await expect(marked).toHaveCount(0)
})

test('새 질문 처리 중 강조를 지우고 이전 답변 선택 시 그 근거만 다시 표시한다', async ({ page, context }) => {
  const { controls } = await parentServer(context, 'DAILY', true)
  await askReport(page)
  const marked = page.locator('[data-answer-highlight=true]')
  await expect(marked).toHaveCount(2)
  let release!: () => void
  controls.waitForReply = new Promise<void>(resolve => { release = resolve }); controls.omitSources = true
  await page.getByLabel('기록에 대한 질문', { exact: true }).fill('그밖에 확인할 내용은?')
  await page.getByRole('button', { name: '질문 보내기', exact: true }).click()
  await expect(marked).toHaveCount(0)
  release()
  await expect(page.getByText('이 답변과 직접 연결된 항목이 현재 리포트 판에는 없습니다.')).toBeVisible()
  const buttons = page.getByRole('button', { name: '리포트 근거 위치 보기', exact: true })
  await expect(buttons).toHaveCount(2)
  await page.setViewportSize({ width: 390, height: 900 })
  await buttons.first().click()
  await expect(marked).toHaveCount(2)
  await expect(marked.first()).toBeFocused()
  await buttons.last().click()
  await expect(marked).toHaveCount(0)
})

test('일일 대화가 고정한 최신 판을 열고 선택 당시의 옛 판에는 강조하지 않는다', async ({ page, context }) => {
  const { controls, calls } = await parentServer(context, 'DAILY', true)
  await page.goto(`/parent/report?childId=${childId}`)
  await page.getByRole('button', { name: '리포트 상세 보기', exact: true }).click()
  await page.getByRole('button', { name: '이 리포트로 질문하기', exact: true }).click()
  controls.latestRevision = 2
  await page.getByLabel('기록에 대한 질문', { exact: true }).fill('기록을 알려 주세요')
  await page.getByRole('button', { name: '질문 보내기', exact: true }).click()
  await expect(page.locator('[data-answer-highlight=true]')).toHaveCount(2)
  await expect(page.getByText(/실제 리포트 기간.*2판/)).toBeVisible()
  expect(calls.filter(call => call.path === '/conversations' && call.method === 'POST')).toHaveLength(1)
})

test('현재 열람 불가한 원문은 표시하지 않고 근거 조회 실패 때 이전 강조를 남기지 않는다', async ({ page, context }) => {
  const { controls } = await parentServer(context, 'DAILY', true)
  controls.evidenceAvailable = false
  await askReport(page)
  const marked = page.locator('[data-answer-highlight=true]')
  await expect(marked).toHaveCount(1)
  await expect(marked.first()).toContainText('답변 제출 시도 수')
  controls.evidenceFails = true
  await page.getByRole('button', { name: '리포트 근거 위치 보기', exact: true }).click()
  await expect(page.getByText('현재 답변 근거를 불러오지 못했습니다.', { exact: true })).toBeVisible()
  await expect(marked).toHaveCount(0)
  controls.evidenceFails = false; controls.evidenceAvailable = true
  await page.getByRole('button', { name: '다시 시도', exact: true }).click()
  await expect(marked).toHaveCount(2)
})

test('다른 자녀를 고르면 답변 선택과 연결한 리포트를 함께 초기화한다', async ({ page, context }) => {
  await parentServer(context, 'DAILY', true)
  await askReport(page)
  await expect(page.locator('[data-answer-highlight=true]')).toHaveCount(2)
  await page.locator('.ws-header').getByLabel('자녀 선택').selectOption(otherId)
  await expect(page.locator('[data-answer-highlight=true]')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: '질문에 연결한 리포트', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '리포트 근거 위치 보기', exact: true })).toHaveCount(0)
})

const explanation = { attemptId: 'attempt-explanation', answerId: 'answer-explanation', answerVersion: 1, missionTitle: '나무가 하는 일',
  thinkingType: 'ANALYZE' as const, quote: '나무가 그늘을 만들어 줍니다.', text: '나무의 역할을 그늘이라는 구체적인 예로 설명했습니다.' }

test('#479: 인용 없는 검증 설명은 요약 검증 실패와 독립적으로 표시한다', async ({ page, context }) => {
  const { report } = await parentServer(context, 'WEEKLY')
  report.explanations = { state: 'INCLUDED', items: [{ ...explanation, quote: null }] }
  report.verification = { numbersMatched: false, quotesMatched: false }
  await page.goto(`/parent/report?childId=${childId}`)
  await page.getByRole('button', { name: '리포트 상세 보기', exact: true }).click()
  const area = page.getByRole('region', { name: '대표 답변 설명', exact: true })
  await expect(area.getByRole('article')).toHaveCount(1)
  await expect(area.locator('blockquote')).toHaveCount(0)
  await expect(area.getByText(explanation.text, { exact: true })).toBeVisible()
})

test('#481: 주간 설명 카드의 미션·유형·인용·설명과 AI 관찰을 표시한다', async ({ page, context }) => {
  const { report, children } = await parentServer(context, 'WEEKLY')
  children[0].grade = 5
  report.explanations = { state: 'INCLUDED', items: [explanation, { ...explanation, answerId: 'answer-two', thinkingType: 'CREATE', missionTitle: '새로운 나무집' }] }
  await page.goto(`/parent/report?childId=${childId}`)
  await page.getByRole('button', { name: '리포트 상세 보기', exact: true }).click()
  const area = page.getByRole('region', { name: '대표 답변 설명', exact: true })
  await expect(area.getByRole('article')).toHaveCount(2)
  await expect(area.getByRole('heading', { name: explanation.missionTitle, exact: true })).toBeVisible()
  await expect(area.getByText('AI 관찰', { exact: true })).toHaveCount(2)
  await expect(area.getByText('분석하기 ·', { exact: false })).toBeVisible()
  await expect(area.locator('blockquote').first()).toHaveText(explanation.quote)
  await expect(area.getByText(explanation.text, { exact: true })).toHaveCount(2)
  await capture(page, 'report-explanations')
})

for (const [state, notice] of [
  ['NOT_INCLUDED', '설명 미포함'], ['NO_TARGET', '설명 대상 답변이 없어'], [null, '설명 정보가 제공되지 않았습니다.'], [undefined, '설명 정보가 제공되지 않았습니다.'],
] as const) test(`#481: 설명 상태 ${String(state)}는 수치 리포트 실패와 구분한다`, async ({ page, context }) => {
  const { report } = await parentServer(context, 'WEEKLY', true)
  report.explanations = state == null ? state : { state, items: [] }
  await page.goto(`/parent/report?childId=${childId}`)
  await page.getByRole('button', { name: '리포트 상세 보기', exact: true }).click()
  const area = page.getByRole('region', { name: '대표 답변 설명', exact: true })
  await expect(area.getByRole('note')).toContainText(notice)
  await expect(area.getByRole('article')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: '답변 제출 시도 수', exact: true })).toBeVisible()
  await expect(page.getByText('리포트 생성에 실패했습니다. 기록 없음과는 다릅니다.')).toHaveCount(0)
})

for (const kind of ['FREE', 'PRIVATE', 'DAILY', 'INVALID'] as const) test(`#481: ${kind} 응답에서는 설명 원문을 표시하지 않는다`, async ({ page, context }) => {
  const { report, entitlement } = await parentServer(context, kind === 'DAILY' ? 'DAILY' : 'WEEKLY')
  report.explanations = { state: 'INCLUDED', items: [explanation] }
  // 무료: 서버는 설명을 null로 보내고(api-spec 766행) entitlement로 프리미엄 안내를 고른다.
  if (kind === 'FREE') {
    Object.assign(entitlement, { status: 'FREE', conversationEnabled: false, narrativeEnabled: false })
    report.explanations = null as never
  }
  if (kind === 'PRIVATE') report.parentSharingEnabled = false
  if (kind === 'INVALID') report.explanations.items = []
  await page.goto(`/parent/report?childId=${childId}`)
  await page.getByRole('button', { name: '리포트 상세 보기', exact: true }).click()
  await expect(page.getByText(explanation.quote, { exact: true })).toHaveCount(0)
  await expect(page.getByText(explanation.text, { exact: true })).toHaveCount(0)
  const area = page.getByRole('region', { name: '대표 답변 설명', exact: true })
  if (kind === 'DAILY') await expect(area).toHaveCount(0)
  else await expect(area.getByRole('note')).toContainText(kind === 'FREE' ? '프리미엄' : kind === 'PRIVATE' ? '비공개' : '확인하지 못했습니다.')
})
