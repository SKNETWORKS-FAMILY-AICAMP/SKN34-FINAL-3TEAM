import { test, expect } from '@playwright/test'
import type { BrowserContext, Page } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'

const childId = '00000000-0000-4000-8000-000000000001'
const otherId = '00000000-0000-4000-8000-000000000002'

async function parentServer(context: BrowserContext, periodType: 'DAILY' | 'WEEKLY' = 'DAILY') {
  const children = [childId, otherId].map((id, index) => ({ id, nickname: index ? '달빛' : '별빛', grade: 3, birthYear: 2017, plan: 'PREMIUM', pinSet: false, pinLocked: false }))
  const period = { from: '2026-11-09', to: periodType === 'DAILY' ? '2026-11-09' : '2026-11-15' }
  const report = { reportId: 'report-1', childId, period, periodType, revision: 1, status: 'COMPLETED', state: 'OK', parentSharingEnabled: true,
    revisions: [{ revision: 1 }], inclusionRule: '합성 리포트 검증 자료', metrics: [], thinkingTypes: [], changes: [], reflections: [], quotes: [], problems: [], narrative: null, verification: { numbersMatched: true, quotesMatched: true } }
  const calls: { path: string; method: string; body: Record<string, unknown> | null; proof?: string }[] = []
  let settings = { items: [{ type: 'REPORT_COMPLETED', enabled: true }] }
  const conversation = { conversationId: 'conversation-1', childId, period, messages: [] as Record<string, unknown>[] }
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
    if (path.endsWith('/entitlement')) return json({ childId: path.split('/')[2], product: { id: 'premium', code: 'PREMIUM', name: '프리미엄', price: 14900, billingCycle: 'MONTHLY', childLimit: 1, active: true, features: {}, limits: { dailyMissions: 5 } }, status: 'ACTIVE', autoRenew: false, refundPending: false, conversationEnabled: true, narrativeEnabled: true })
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
    if (path === '/reports/report-1') return json(report)
    if (path === '/conversations') return json(request.method() === 'POST' ? conversation : { items: [] })
    if (path === '/conversations/conversation-1') return json(conversation)
    if (path === '/conversations/conversation-1/messages') {
      const result = { messageId: 'message-1', question: body.question, status: 'COMPLETED', answer: '합성 기록으로 확인한 답변입니다.', source: 'LLM',
        scope: { childId, ...period, changed: false }, recordCount: 1, metrics: [], evidence: [], verification: { numbersMatched: true, quotesMatched: true, contentAllowed: true } }
      conversation.messages = [result]
      return route.fulfill({ contentType: 'text/event-stream', body: 'event: result\ndata: ' + JSON.stringify(result) + '\n\nevent: done\ndata: {}\n\n' })
    }
    if (path === '/agent/example-questions') return json({ items: [] })
    if (path.endsWith('/summary')) return json({ childId, period, state: 'NO_RECORD', metrics: [] })
    if (path.endsWith('/thinking-types')) return json({ childId, state: 'NO_RECORD', items: [] })
    if (path.endsWith('/attempts')) return json({ childId, items: [], page: 0, size: 20, totalElements: 0 })
    return json({ status: 404, code: 'NOT_FOUND', title: '합성 검사에 없는 요청입니다.' }, 404)
  })
  return { calls, period }
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

test('상단 가장 오른쪽 알림 종에서 수신 설정을 저장한다', async ({ page, context }) => {
  const state = await parentServer(context)
  await page.goto(`/parent/settings?childId=${childId}`)
  const bell = page.getByRole('button', { name: '알림 열기', exact: true })
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 900 })
    const box = await bell.boundingBox()
    expect(box!.x + box!.width).toBeGreaterThan(width - 40)
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
