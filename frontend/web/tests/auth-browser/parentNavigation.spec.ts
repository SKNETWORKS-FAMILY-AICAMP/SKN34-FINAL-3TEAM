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
  const controls = { originalVersion: 1, evidenceAvailable: true, evidenceFails: false, latestRevision: 1, omitSources: false, waitForReply: null as Promise<void> | null, extraReports: [] as WeeklyReport[] }
  const metric = { label: '답변 제출 시도 수', formula: '집계 대상 시도 수', period, count: 6, numerator: 6, denominator: 6, value: null, sourceType: 'RECORD' as const, state: 'OK' as const }
  if (withHighlights) {
    report.metrics = [metric, { ...metric, label: '다른 활동', formula: '다른 집계 기준' }]
    report.problems = [{ itemId: 'daily-item-1', missionId: 'mission-1', attemptId: 'attempt-1', title: '나무는 어떤 도움을 줄까요?', context: 'EXTRA', judgment: 'CORRECT',
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
    if (path === '/me') return json({ role: 'PARENT', authMethod: 'GOOGLE', loginId: 'parent@example.test', name: '합성 보호자', email: 'parent@example.test', nextAction: 'READY', startPath: '/parent/journal' })
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
    if (path === `/children/${childId}/reports`) return json({ items: [report, ...controls.extraReports] })
    if (path === '/reports/report-1') return json({ ...report, revision: Number(url.searchParams.get('revision') ?? controls.latestRevision) })
    if (path === '/reports/report-1/evidence/explanation-original') return json({ items: [{ attemptId: 'attempt-explanation', answerId: 'answer-explanation', answerVersion: controls.originalVersion, available: controls.evidenceAvailable, quote: '나무는 그늘을 만들어 줍니다. 더운 날 그늘에서 쉬면 시원합니다. 그래서 나무를 보호해야 합니다.' }] })
    const extraReport = controls.extraReports.find(item => path === `/reports/${item.reportId}`)
    if (extraReport) return json(extraReport)
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
    if (path.endsWith('/attempts')) return json({ childId, period, items: [], page: 0, size: 20, totalElements: 0 })
    return json({ status: 404, code: 'NOT_FOUND', title: '합성 검사에 없는 요청입니다.' }, 404)
  })
  return { calls, period, controls, report, children, entitlement }
}

async function openReport(page: Page) {
  await expect(page.getByRole('region', { name: '리포트 내용', exact: true })).toBeVisible()
}
test('일일 리포트가 문제 항목 ID로 해당 답변 근거를 연다', async ({page, context}) => {
  await parentServer(context, 'DAILY', true)
  await context.route('**/reports/report-1/evidence/daily-item-1', route => route.fulfill({json: {items: [{attemptId: 'attempt-1', answerId: 'answer-1', kind: 'ANSWER', available: true, quote: '해당 문제의 원문 근거'}]}}))
  await page.goto(`/parent/report?childId=${childId}`)
  await openReport(page)
  await page.locator('summary').getByText('나무는 어떤 도움을 줄까요?', {exact:true}).click()
  await page.getByRole('button', {name: '내용', exact: true}).click()
  await expect(page.getByText('해당 문제의 원문 근거', {exact: false})).toBeVisible()
})

test('문의 응답이 늦어도 신고 초안과 유형을 보존하고 오래된 접수 내역을 연다', async ({page, context}) => {
  await parentServer(context)
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  await context.route(/\/api\/v1\/(inquiries|error-reports)(\?|$)/, async route => {
    if (route.request().method() === 'POST') { await gate; return route.fulfill({status: 201, json: {}}) }
    const url = new URL(route.request().url())
    const index = Number(url.searchParams.get('page') ?? 0)
    const items = Array.from({length: index ? 1 : 20}, (_, n) => ({
      inquiryId: `inq-${index}-${n}`, reportId: `report-${index}-${n}`, status: 'RESOLVED', category: 'OTHER',
      title: `문의 ${20*index+n+1}`, comment: `신고 ${20*index+n+1}`, body: '문의 본문', answer: '처리한 답변', createdAt: '2026-11-19T15:30:00Z',
    }))
    return route.fulfill({json: {items, page:index, size:20, totalElements:21}})
  })
  await page.goto('/parent/support')
  await page.getByRole('textbox',{name:'제목'}).fill('제출할 문의')
  await page.getByRole('textbox',{name:'내용'}).fill('일반 문의 본문')
  await page.getByText('문의 21', {exact:true}).click()
  await expect(page.locator('details[open]').getByText('처리한 답변')).toBeVisible()
  await page.getByRole('button',{name:'접수하기'}).click()
  await page.getByRole('button',{name:'학습 결과가 이상해요'}).click()
  await expect(page.getByRole('textbox',{name:'내용'})).toHaveValue('')
  await page.getByRole('textbox',{name:'내용'}).fill('따로 작성한 신고 초안')
  const response = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/inquiries'))
  release()
  await response
  await page.getByRole('button',{name:'이용 중 궁금한 점이 있어요'}).click()
  await expect(page.getByText(/접수했습니다. 아래 목록/)).toBeVisible()
  await page.getByRole('button',{name:'학습 결과가 이상해요'}).click()
  await expect(page.getByRole('textbox',{name:'내용'})).toHaveValue('따로 작성한 신고 초안')
  await expect(page.getByRole('combobox',{name:'유형'})).toHaveValue('OTHER')
  await page.goto('/parent/support/results')
  await expect(page.getByRole('link',{name:/문의 21 ·/})).toBeVisible()
  await expect(page.getByRole('link',{name:/신고 21 ·/})).toBeVisible()
})

test('공개 설정 조회 오류는 원문을 가리고 재조회로 복구한다', async ({page,context}) => {
  await parentServer(context)
  let failed = true
  await context.route('**/sharing-preferences', route => failed
    ? route.fulfill({status:503,json:{title:'조회 실패',status:503,retryable:true}})
    : route.fulfill({json:{studentId:childId,parentSharingEnabled:true}}))
  await page.goto(`/parent/report?childId=${childId}`)
  await expect(page.getByText(/학생 답변의 공개 여부를 확인할 수 없습니다/)).toBeVisible()
  await expect(page.getByText(/아이가 답변 원문을 비공개로/)).toHaveCount(0)
  failed = false
  await page.getByRole('button',{name:'다시 시도'}).click()
  await expect(page.getByRole('region',{name:'리포트 내용',exact:true})).toBeVisible()
})

test('첫 자녀 생성 후 세션 갱신만 재시도하고 직접 고른 출생연도를 유지한다', async ({page,context}) => {
  await parentServer(context)
  let creates = 0, restored = false
  await context.route('**/api/v1/me', route => {
    if (creates && !restored) return route.fulfill({status:503,json:{status:503,title:'세션 조회 실패'}})
    return route.fulfill({json:{role:'PARENT',name:'보호자',nextAction: restored ? 'READY' : 'CHILD_REGISTRATION_REQUIRED',startPath: restored ? '/parent/journal' : '/parent/children/new'}})
  })
  await context.route('**/api/v1/children', async route => {
    if (route.request().method() !== 'POST') return route.fallback()
    creates++
    expect(route.request().postDataJSON().birthYear).toBe(2018)
    return route.fulfill({status:201,json:{id:childId,nickname:'첫 자녀',grade:4,birthYear:2018}})
  })
  await page.goto('/parent/children/new')
  const name = page.getByRole('textbox',{name:'자녀 별명'})
  await name.fill('가'.repeat(41))
  await expect(name).toHaveValue('가'.repeat(40))
  await page.getByLabel('출생연도',{exact:true}).selectOption('2018')
  await page.getByLabel('자녀 학년',{exact:true}).selectOption('4')
  await expect(page.getByLabel('출생연도',{exact:true})).toHaveValue('2018')
  const submit = page.getByRole('button',{name:'자녀 등록하기'})
  await submit.click()
  await expect(page.getByRole('button',{name:'저장 후 상태 다시 확인'})).toBeVisible()
  await expect(submit).toBeDisabled()
  restored = true
  await page.getByRole('button',{name:'저장 후 상태 다시 확인'}).click()
  await expect(page).toHaveURL(/parent\/journal/)
  expect(creates).toBe(1)
})

test('마지막 미읽음 알림을 읽으면 남은 알림 페이지로 돌아간다', async ({page,context}) => {
  await parentServer(context)
  let count = 21
  await context.route('**/api/v1/notifications?**', route => {
    const p = Number(new URL(route.request().url()).searchParams.get('page'))
    const rows = Array.from({length:count},(_,i) => ({id:String(i),title:`알림 ${i+1}`,readAt:null,createdAt:'2026-11-19T15:30:00Z'}))
    return route.fulfill({json:{items:rows.slice(p*20,(p+1)*20),page:p,size:20,hasNext:(p+1)*20<count}})
  })
  await context.route('**/notifications/20/read', route => { count = 20; return route.fulfill({status:204}) })
  await page.goto('/parent/notifications')
  await page.getByLabel('읽지 않은 알림만').check()
  await page.getByRole('navigation',{name:'알림 페이지'}).getByRole('button',{name:'다음'}).click()
  await expect(page.getByRole('heading',{name:'알림 21',exact:true})).toBeVisible()
  await page.getByRole('button',{name:'읽음으로 표시'}).click()
  await expect(page.getByRole('heading',{name:'알림 1',exact:true})).toBeVisible()
  await expect(page.getByRole('navigation',{name:'알림 페이지'})).toContainText('1쪽')
})

test('프로필 초안과 QR 발급 당시 자녀를 보존한다', async ({page,context}) => {
  await parentServer(context)
  await context.route('**/student-devices/pairings', route => route.fulfill({json:{pairingCode:'12345678',expiresAt:new Date(Date.now()+600_000).toISOString()}}))
  await page.goto(`/parent/settings?childId=${otherId}`)
  await page.getByLabel('새 자녀 별명',{exact:true}).fill('작성 중인 별명')
  await page.getByRole('tab',{name:'공개·동의'}).click()
  await page.getByRole('tab',{name:'프로필'}).click()
  await expect(page.getByLabel('새 자녀 별명',{exact:true})).toHaveValue('작성 중인 별명')
  await page.goto(`/parent/devices?childId=${otherId}`)
  await page.getByRole('button',{name:'등록 코드 만들기'}).click()
  const targets = page.getByText(/이 코드로 등록할 자녀/)
  await expect(targets).toContainText('별빛, 달빛')
  await page.getByRole('checkbox',{name:/별빛/}).uncheck()
  await expect(targets).toContainText('별빛, 달빛')
  await page.getByRole('button',{name:'변경한 대상으로 새 코드 발급'}).click()
  await expect(targets).toHaveText('이 코드로 등록할 자녀 · 달빛')
})

test('모바일 지원 메뉴는 선택한 본문으로 초점을 옮긴다', async ({page,context}) => {
  await parentServer(context)
  await page.setViewportSize({width:390,height:844})
  await page.goto(`/parent/journal?childId=${childId}`)
  for (const [name,path] of [['도움말','help'],['문의·오류 신고','support'],['공지','notices']]) {
    await page.getByRole('button',{name:'학부모 메뉴 열기'}).click()
    await page.getByRole('dialog').getByRole('link',{name,exact:true}).click()
    await expect(page).toHaveURL(new RegExp('/parent/'+path))
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(page.locator('#parent-main')).toBeFocused()
  }
})

test('일일 기록이 더 최신이어도 홈에는 주간 기록을 연결하고 공지 검색은 21번째까지 찾는다', async ({page,context}) => {
  const {report,controls} = await parentServer(context)
  controls.extraReports.push({...report,reportId:'weekly-previous',periodType:'WEEKLY',period:{from:'2026-11-02',to:'2026-11-08'}})
  await page.goto(`/parent/journal?childId=${childId}`)
  const card = page.getByRole('region',{name:'최근 주간 리포트'})
  await expect(card).toContainText('2026-11-02 ~ 2026-11-08')
  await card.getByRole('button',{name:'리포트 보기'}).click()
  await expect(page).toHaveURL(/reportId=weekly-previous/)
  await context.route(/\/api\/v1\/notices(\?|$)/, route => {
    const p = Number(new URL(route.request().url()).searchParams.get('page'))
    const items = Array.from({length:p ? 1 : 20},(_,i)=>({noticeId:`notice-${p}-${i}`,title:`확인할 공지 ${p*20+i+1}`,body:'공지 본문',kind:'NOTICE',visibleFrom:'2026-11-19T15:30:00Z'}))
    return route.fulfill({json:{items,page:p,size:20,totalElements:21}})
  })
  await page.goto('/parent/notices')
  await page.getByLabel('공지 제목 검색').fill('공지 21')
  await page.getByText('확인할 공지 21',{exact:true}).click()
  await expect(page.getByText('공지 본문',{exact:true})).toBeVisible()
})

async function startReportConversation(page: Page) {
  await page.getByRole('button', { name: '이 리포트로 질문하기', exact: true }).click()
  // URL 전환과 모달 정리가 끝나기 전에는 배경 입력창에 포커스를 줄 수 없다.
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.locator('#parent-ai-conversation')).toHaveJSProperty('inert', false)
  await expect(page.getByRole('button', { name: '전체 기록으로 질문하기', exact: true })).toBeVisible()
}
async function capture(page: Page, name: string) {
  const out = 'test-results/parent-navigation'
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

test('학습 기록이 없으면 실제 기기·PIN 진입 경로를 안내한다 (#715)', async ({ page, context }) => {
  await parentServer(context)
  await page.goto(`/parent/journal?childId=${childId}`)
  const status = page.locator('[data-query-state="NO_RECORD"]')
  await expect(status).toContainText('선택한 기간에 답변을 제출한 활동이 없습니다.')
  await status.getByRole('button', { name: '조회 기간 바꾸기' }).click()
  await expect(page.getByLabel('조회 시작일')).toBeFocused()
  await expect(page.getByText('이 자녀로 학습 시작', { exact: false })).toHaveCount(0)
  await status.getByRole('link', { name: /기기·PIN 설정/ }).click()
  await expect(page).toHaveURL(/\/parent\/devices/)
  expect(new URL(page.url()).searchParams.get('childId')).toBe(childId)
})

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

test('PIN 자녀는 상단 선택기로 한 명만 고르고 Google 없이 선택한 자녀에게 저장한다', async ({ page, context }) => {
  const state = await parentServer(context)
  await page.goto(`/parent/devices?childId=${childId}`)
  const picker = page.getByRole('combobox', { name: '현재 자녀' })
  await expect(page.getByRole('group', { name: '자녀 선택' })).toHaveCount(0)
  await expect(page.getByRole('form', { name: / PIN$/ })).toHaveCount(1)
  await page.getByLabel('별빛 새 PIN', { exact: true }).fill('5090')
  await picker.selectOption(otherId)
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
    if (width > 600) expect(box!.x + box!.width).toBeLessThanOrEqual(logout!.x)
    else { await expect(page.locator('.ws-header .ws-logout')).toBeHidden(); expect(box!.x + box!.width).toBeLessThanOrEqual(width) }
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
  await openReport(page)
  await startReportConversation(page)
  await expect(page.getByLabel('기록에 대한 질문', { exact: true })).toBeVisible()
  await page.getByLabel('기록에 대한 질문', { exact: true }).fill('어떤 활동을 했나요?')
  await expect(page.getByLabel('기록에 대한 질문', { exact: true })).toHaveValue('어떤 활동을 했나요?')
  await page.getByRole('button', { name: '질문 보내기', exact: true }).click()
  await expect(page.getByText('합성 기록으로 확인한 답변입니다.', { exact: true })).toBeVisible()
  const request = state.calls.find(call => call.path === '/conversations' && call.method === 'POST')!
  expect(request.body).toEqual(periodType === 'DAILY' ? { childId, reportId: 'report-1' } : { childId, ...state.period })
  await expect(page.getByRole('heading', { name: '질문에 연결한 리포트' })).toBeVisible()
  if (periodType === 'DAILY') {
    await expect(page.getByRole('button', { name: /^질문 기간 변경/ })).toHaveCount(0)
    await page.getByRole('button', { name: '전체 기록으로 질문하기' }).click()
    await expect(page.getByRole('button', { name: /^질문 기간 변경/ })).toBeVisible()
  }
  await page.getByRole('link', { name: '학부모 대시보드로 돌아가기' }).click()
  await expect(page).toHaveURL(/\/parent\/journal/)
})

async function askReport(page: Page) {
  await page.goto(`/parent/report?childId=${childId}`)
  await openReport(page)
  await startReportConversation(page)
  await page.getByLabel('기록에 대한 질문', { exact: true }).fill('어떤 활동을 했나요?')
  await page.getByRole('button', { name: '질문 보내기', exact: true }).click()
  await expect(page.getByText('합성 기록으로 확인한 답변입니다.', { exact: true })).toBeVisible()
}

for (const periodType of ['DAILY', 'WEEKLY'] as const) test(`${periodType} 챗봇은 답변에 연결된 원문만 근거 모달에 표시한다`, async ({ page, context }) => {
  const { calls } = await parentServer(context, periodType, true)
  await askReport(page)
  await expect(page.getByText(/출처 LLM/)).toHaveCount(0)
  await page.getByRole('button', { name: '답변 근거 보기', exact: true }).click()
  const evidence = page.getByRole('dialog', { name: '답변 근거', exact: true })
  await expect(evidence.getByText('나무가 그늘을 만들어 줍니다.', { exact: true })).toBeVisible()
  await expect(evidence.getByText('다른 활동', { exact: true })).toHaveCount(0)
  expect(calls.filter(call => call.path.endsWith('/message-1/evidence')).length).toBeGreaterThan(0)
  await evidence.getByRole('button', { name: '창 닫기' }).click()
  await expect(evidence).toHaveCount(0)
})

test('현재 열람할 수 없는 답변 원문은 근거 모달에서 숨긴다', async ({ page, context }) => {
  const { controls } = await parentServer(context, 'DAILY', true)
  controls.evidenceAvailable = false
  await askReport(page)
  await page.getByRole('button', { name: '답변 근거 보기', exact: true }).click()
  const evidence = page.getByRole('dialog', { name: '답변 근거', exact: true })
  await expect(evidence).toBeVisible()
  await expect(evidence.getByText('나무가 그늘을 만들어 줍니다.', { exact: true })).toHaveCount(0)
})

test('근거가 없는 후속 답변에는 근거 버튼을 추가하지 않는다', async ({ page, context }) => {
  const { controls } = await parentServer(context, 'DAILY', true)
  await askReport(page)
  controls.omitSources = true
  await page.getByLabel('기록에 대한 질문', { exact: true }).fill('그밖에 확인할 내용은?')
  await page.getByRole('button', { name: '질문 보내기' }).click()
  await expect(page.getByText('합성 기록으로 확인한 답변입니다.', { exact: true })).toHaveCount(2)
  await expect(page.getByRole('button', { name: '답변 근거 보기', exact: true })).toHaveCount(1)
})

const explanation = { itemId: 'explanation-original', attemptId: 'attempt-explanation', answerId: 'answer-explanation', answerVersion: 1, missionTitle: '나무가 하는 일',
  thinkingType: 'ANALYZE' as const, quote: '나무가 그늘을 만들어 줍니다.', text: '나무의 역할을 그늘이라는 구체적인 예로 설명했습니다.' }

test('리포트 제목에서 완료된 일일 리포트 날짜를 고른다 @responsive', async ({ page, context }) => {
  const { report, controls } = await parentServer(context, 'WEEKLY')
  controls.extraReports.push({ ...report, reportId: 'daily-report', periodType: 'DAILY', period: { from: '2026-11-09', to: '2026-11-09' } })
  await page.goto(`/parent/report?childId=${childId}`)
  await openReport(page)
  const period = page.locator('.report-period-picker > summary')
  await expect(period).toHaveText('주간 리포트')
  await period.click()
  await page.getByRole('button', { name: '일일', exact: true }).click()
  await page.getByRole('button', { name: '2026-11-09', exact: true }).click()
  await expect(period).toHaveText('일일 리포트')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.goBack()
  await expect(period).toHaveText('주간 리포트')
})

test('일일·주간 리포트에서 돌아보기 난이도를 화면 문구로 표시한다 (#860)', async ({ page, context }) => {
  const { report, controls } = await parentServer(context, 'DAILY', true)
  const problem = report.problems![0]
  const reflection = { written: true, difficulty: 'NORMAL', text: '까닭을 한 문장 더 적었어요.' }
  problem.reflection = reflection
  report.problems!.push({ ...problem, missionId: 'legacy', attemptId: 'legacy', title: '이전 형식',
    reflection: { ...reflection, difficulty: 'UNKNOWN_LEVEL', text: '다시 생각했어요.' } })
  controls.extraReports.push({ ...report, reportId: 'weekly-report', periodType: 'WEEKLY',
    period: { from: '2026-11-09', to: '2026-11-15' }, problems: [],
    reflections: [{ ...reflection, attemptId: 'weekly-1' },
      { ...reflection, difficulty: '쉬웠어요', text: '이유가 떠올랐어요.', attemptId: 'weekly-2' }] })

  await page.goto(`/parent/report?childId=${childId}&view=reports&reportId=report-1`)
  const problems = page.locator('details.report-answer-comparison > summary')
  await expect(problems).toHaveCount(2)
  for (const item of await problems.all()) await item.click()
  await expect(page.getByText('보통', { exact: true })).toBeVisible()
  await expect(page.getByText('까닭을 한 문장 더 적었어요.', { exact: true })).toBeVisible()
  await expect(page.getByText('다시 생각했어요.', { exact: true })).toBeVisible()
  await expect(page.getByText(/NORMAL|UNKNOWN_LEVEL/)).toHaveCount(0)
  await page.locator('.report-period-picker > summary').click()
  await page.getByRole('button', { name: '주간', exact: true }).click()
  await page.getByRole('button', { name: '2026-11-09 ~ 2026-11-15', exact: true }).click()
  await expect(page.getByText('보통', { exact: true })).toBeVisible()
  await expect(page.getByText('까닭을 한 문장 더 적었어요.', { exact: true })).toBeVisible()
  await page.getByLabel('주간 리포트 활동 선택').selectOption('weekly-2')
  await expect(page.getByText('쉬웠어요', { exact: true })).toBeVisible()
  await expect(page.getByText('이유가 떠올랐어요.', { exact: true })).toBeVisible()
  await expect(page.getByText(/NORMAL/)).toHaveCount(0)
})

test('상세 설명 구역과 개선 목록을 화면 폭에 맞춰 읽고 보완점이 없으면 생략한다 @responsive', async ({ page, context }) => {
  const { report } = await parentServer(context, 'WEEKLY')
  const content = { analysis: '나무가 그늘을 만든다는 구체적인 역할을 설명했어요.\n\n그늘에서 어떤 활동을 할 수 있는지 덧붙이면 생각을 더 자세히 전달할 수 있어요.',
    improvement_points: '그늘이 필요한 상황을 조금 더 풀어 볼 수 있어요.',
    next_steps: ['그늘에서 쉬었던 경험을 함께 이야기해 보세요.', '그 경험을 글의 이유와 연결하는 문장을 써 보세요.'] }
  report.explanations = { state: 'INCLUDED', items: [{ ...explanation, text: JSON.stringify(content) },
    { ...explanation, answerId: 'no-difficulty', attemptId: 'no-difficulty', missionTitle: '이유를 연결한 글', text: JSON.stringify({ ...content, improvement_points: null }) }] }
  await page.goto(`/parent/report?childId=${childId}`)
  await openReport(page)
  const area = page.getByRole('region', { name: '젬마 설명', exact: true })
  const first = area.getByRole('article').first()
  await expect(first.getByRole('heading', { name: '상세 분석', exact: true })).toBeVisible()
  await expect(first.getByRole('heading', { name: '보완할 지점', exact: true })).toBeVisible()
  await expect(first.getByRole('heading', { name: '개선 방안', exact: true })).toBeVisible()
  await expect(first.getByRole('listitem')).toHaveText(content.next_steps)
  await expect(first.getByRole('list')).toHaveCSS('list-style-type', 'disc')
  await expect(first.locator('blockquote')).toBeVisible()
  await expect(first.locator('.report-explanation-section').first().locator('p')).toHaveCount(2)
  expect(parseFloat(await first.locator('.report-explanation-copy').first().evaluate(el => getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16)
  await page.getByLabel('주간 리포트 활동 선택').selectOption('no-difficulty')
  await expect(area.getByRole('heading', { name: '보완할 지점', exact: true })).toHaveCount(0)
  await page.getByLabel('주간 리포트 활동 선택').selectOption(explanation.attemptId)
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 900 })
    await first.scrollIntoViewIfNeeded()
    await expect(first.getByRole('heading', { name: '개선 방안', exact: true })).toBeVisible()
    expect(await first.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true)
  }
  await capture(page, 'report-explanation-sections')
  await first.screenshot({ path: 'test-results/parent-navigation/report-explanation-card.png' })
})

test('#479: 인용 없는 검증 설명은 요약 검증 실패와 독립적으로 표시한다', async ({ page, context }) => {
  const { report } = await parentServer(context, 'WEEKLY')
  report.explanations = { state: 'INCLUDED', items: [{ ...explanation, quote: null }] }
  report.verification = { numbersMatched: false, quotesMatched: false }
  await page.goto(`/parent/report?childId=${childId}`)
  await openReport(page)
  const area = page.getByRole('region', { name: '젬마 설명', exact: true })
  await expect(area.getByRole('article')).toHaveCount(1)
  await expect(area.locator('blockquote')).toHaveText('나무는 그늘을 만들어 줍니다. 더운 날 그늘에서 쉬면 시원합니다. 그래서 나무를 보호해야 합니다.')
  await expect(area.getByText(explanation.text, { exact: true })).toBeVisible()
})

test('#481: 주간 설명 카드의 미션·유형·인용·설명과 AI 관찰을 표시한다', async ({ page, context }) => {
  const { report, children } = await parentServer(context, 'WEEKLY')
  children[0].grade = 5
  report.explanations = { state: 'INCLUDED', items: [explanation, { ...explanation, answerId: 'answer-two', attemptId: 'answer-two', thinkingType: 'CREATE', missionTitle: '새로운 나무집' }] }
  await page.goto(`/parent/report?childId=${childId}`)
  await openReport(page)
  const area = page.getByRole('region', { name: '젬마 설명', exact: true })
  await expect(page.getByLabel('주간 리포트 활동 선택').locator('option')).toHaveCount(2)
  await expect(area.getByRole('article')).toHaveCount(1)
  await expect(page.locator('.weekly-activity-heading')).toContainText(explanation.missionTitle)
  await expect(area.getByRole('heading', { name: '젬마 설명', exact: true })).toBeVisible()
  await expect(page.locator('.weekly-activity-heading')).toContainText('분석하기')
  await expect(area.getByRole('heading', { name: '학생 글 전체', exact: true })).toHaveCount(1)
  await expect(area.locator('blockquote').first()).toHaveText('나무는 그늘을 만들어 줍니다. 더운 날 그늘에서 쉬면 시원합니다. 그래서 나무를 보호해야 합니다.')
  await expect(area.getByText(explanation.text, { exact: true })).toHaveCount(1)
  await page.getByLabel('주간 리포트 활동 선택').selectOption('answer-two')
  await expect(page.locator('.weekly-activity-heading')).toContainText('새로운 나무집')
  await capture(page, 'report-explanations')
})

for (const [state, notice] of [
  ['NOT_INCLUDED', '설명이 포함되지 않았습니다'], ['NO_TARGET', '해당하는 답변 기록이 없습니다'], [null, '설명 정보가 제공되지 않았습니다.'], [undefined, '설명 정보가 제공되지 않았습니다.'],
] as const) test(`#481: 설명 상태 ${String(state)}는 수치 리포트 실패와 구분한다`, async ({ page, context }) => {
  const { report } = await parentServer(context, 'WEEKLY', true)
  report.explanations = state == null ? state : { state, items: [] }
  await page.goto(`/parent/report?childId=${childId}`)
  await openReport(page)
  const area = page.getByRole('region', { name: '젬마 설명', exact: true })
  await expect(area.getByRole('note')).toContainText(notice)
  await expect(area.getByRole('article')).toHaveCount(0)
  await expect(page.locator('.report-count-list').getByText('답변 제출 시도 수', { exact: true })).toBeVisible()
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
  await openReport(page)
  await expect(page.getByText(explanation.quote, { exact: true })).toHaveCount(0)
  await expect(page.getByText(explanation.text, { exact: true })).toHaveCount(0)
  const area = page.getByRole('region', { name: '젬마 설명', exact: true })
  if (kind === 'DAILY') await expect(area).toHaveCount(0)
  else await expect(area.getByRole('note')).toContainText(kind === 'FREE' ? '프리미엄' : kind === 'PRIVATE' ? '비공개' : '확인하지 못했습니다.')
})

for (const mode of ['unavailable', 'version', 'failure'] as const) test(`원문 전체는 ${mode} 상태에서 발췌문으로 대체하지 않는다`, async ({ page, context }) => {
  const { report, controls } = await parentServer(context, 'WEEKLY')
  report.explanations = { state: 'INCLUDED', items: [explanation] }
  if (mode === 'unavailable') controls.evidenceAvailable = false
  if (mode === 'version') controls.originalVersion = 99
  if (mode === 'failure') await context.route('**/reports/report-1/evidence/explanation-original', route => route.fulfill({ status: 503, json: { code: 'UNAVAILABLE', title: '원문 조회 실패' } }))
  await page.goto(`/parent/report?childId=${childId}`)
  await openReport(page)
  const area = page.getByRole('region', { name: '젬마 설명', exact: true })
  await expect(area.getByText('이 설명에 연결된 원문 전체를 확인할 수 없습니다.')).toBeVisible()
  await expect(area.locator('blockquote')).toHaveCount(0)
  await expect(area.getByText(explanation.text, { exact: true })).toBeVisible()
})

test('Google 이메일 아이디를 계정 관리에 표시한다 (#683)', async ({ page, context }) => {
  await parentServer(context)
  await page.goto(`/parent/settings?childId=${childId}&section=account`)
  const card = page.getByRole('region', { name: '로그인 아이디', exact: true })
  await expect(card.getByText('parent@example.test', { exact: true })).toBeVisible()
  await expect(card.getByText('Google 계정으로 로그인합니다. 아이디는 Google 이메일입니다.')).toBeVisible()
})
