import { test, expect } from '@playwright/test'
import type { BrowserContext, Locator } from '@playwright/test'
import { mkdir, readFile, writeFile } from 'node:fs/promises'

const id = '00000000-0000-4000-8000-000000000441'
const themeId = '00000000-0000-4000-8000-000000000395'
const days = ['MON', 'TUE', 'WED', 'THU', 'FRI']
const reviewListPath = '/admin/theme-drafts/review-list'
const nextWeek = new Date()
nextWeek.setUTCDate(nextWeek.getUTCDate() + 8 - (nextWeek.getUTCDay() || 7))
const requestWeek = nextWeek.toISOString().slice(0, 10)
const listRow = {
  draftId: id, title: '달의 지도', thumbnailUrl: null, grade: 'G4', source: 'AUTO', status: 'READY', stage: 'review',
  weekStart: '2026-11-23', appliedWeek: '2026-11-30', plannedWeek: '2026-11-30',
  updatedAt: '2026-11-20T03:00:00Z', themeId: null, comparisonScene: null,
}

async function expectBlueAction(action: Locator) {
  await action.page().mouse.move(0, 0)
  await expect(action).toHaveCSS('color', 'rgb(255, 255, 255)')
  await expect(action).toHaveCSS('background-color', 'rgb(50, 89, 217)')
  await action.hover()
  await expect(action).toHaveCSS('color', 'rgb(255, 255, 255)')
  await expect(action).toHaveCSS('background-color', 'rgb(33, 71, 189)')
}

/** core 확정 최소 응답만 고정 제공한다. #438 생성/검사/채택 파이프라인 대역은 만들지 않는다. */
async function confirmedResponses(context: BrowserContext, content = true, requestFails = false) {
  const calls: { path: string; method: string; body: unknown; search: string }[] = []
  await context.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
  await context.route('**/api/v1/**', async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname.replace('/api/v1', '')
    calls.push({ path, method: req.method(), body: req.postData() ? req.postDataJSON() : null, search: url.search })
    const json = (body: unknown, status = 200) => route.fulfill({ status, json: body })
    if (path === '/auth/refresh') return json({ role: 'ADMIN', accessToken: 'synthetic-admin', expiresIn: 900, nextAction: 'READY', startPath: '/admin/home' })
    if (path === '/me') return json({ role: 'ADMIN', userId: 'synthetic-admin', name: '합성 운영자', email: 'admin@example.test', permissions: content ? ['CONTENT'] : ['SERVICE_OPS'], nextAction: 'READY', startPath: '/admin/home' })
    if (path === '/notifications') return json({ items: [], page: 0, size: 20, hasNext: false })
    if (path === '/notifications/stream') return route.abort('failed')
    if (path === reviewListPath) return json({
      items: [listRow], page: 0, size: 20, totalElements: 1, weeks: ['2026-11-23', '2026-11-30'],
    })
    if (path === '/admin/theme-drafts') {
      if (req.method() === 'POST' && requestFails) return json({ status: 503, code: 'LEARNING_UNAVAILABLE', title: '요청 결과를 확인하지 못했습니다.' }, 503)
      return json(req.method() === 'GET' ? { items: [{ draftId: id, status: 'GENERATING' }] } : { draftId: id, status: 'GENERATING' }, req.method() === 'POST' ? 202 : 200)
    }
    if (path === '/admin/theme-drafts/' + id) return json({ draftId: id, status: 'GENERATING' })
    if (/\/scenes\/[A-Z]+\/versions$/.test(path)) {
      return json({scene:path.split('/').at(-2),rootDraftId:id,editable:true,selectedVersionId:null,versions:[]})
    }
    if (path === '/admin/weekly-themes') return json({ items: [] })
    if (path === '/admin/weekly-themes/' + themeId) return json({ themeId, title: '기존 테마', intro: '기존 도입 이야기', grade: 'G3', weekStart: '2026-11-16', status: 'DRAFT', updatedAt: '2026-11-10T00:00:00Z', days: days.map((day, n) => ({ day, missionId: `00000000-0000-4000-8000-00000000000${n + 1}` })) })
    if (path === '/admin/missions') return json({ items: [] })
    if (path === '/admin/achievement-standards') return json({ items: [{ code: '4과03-01', subject: '과학', gradeBand: '초3~4', area: '생명', statement: '합성 성취기준 표 행', levelScale: 3, levels: null, curriculumVersion: '2022', source: 'HTTP 검사 자료', note: null }], page: 0, size: 10, totalElements: 1 })
    return json({ code: 'NOT_FOUND' }, 404)
  })
  return calls
}

test('주간 테마 목록은 대표 그림과 진행 상태를 표시하고 해당 장면·게시 테마·버림 이력으로 연결한다', async ({ page, context }) => {
  const calls = await confirmedResponses(context)
  const thumbnail = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="49" height="37"><rect width="49" height="37" fill="navy"/></svg>')
  const pair = { ...listRow, title: '월요일의 두 장면', stage: 'pair', comparisonScene: 'MON', thumbnailUrl: thumbnail }
  const published = {
    ...listRow, draftId: '00000000-0000-4000-8000-000000000442', title: '게시된 테마', source: 'ADMIN',
    grade: 'G5', stage: 'published', status: 'ADOPTED', appliedWeek: '2026-12-07', plannedWeek: null, themeId,
  }
  const ready = { ...published, draftId: '00000000-0000-4000-8000-000000000444', title: '게시 대기 테마', stage: 'ready' }
  const closed = { ...published, draftId: '00000000-0000-4000-8000-000000000445', title: '게시 마감 테마', stage: 'closed' }
  const closedDraft = {
    ...listRow, draftId: '00000000-0000-4000-8000-000000000446', title: '미선정 초안', stage: 'closed',
  }
  const archived = {
    ...listRow, draftId: '00000000-0000-4000-8000-000000000443', title: '이전 초안', source: 'ADMIN',
    stage: 'discarded', status: 'DISCARDED', plannedWeek: null, appliedWeek: listRow.weekStart, thumbnailUrl: '/test-media/missing-thumb.png',
  }
  const requests: URLSearchParams[] = []
  await context.route('**/test-media/missing-thumb.png', route => route.fulfill({ status: 404, body: '' }))
  await context.route('**/api/v1/admin/theme-drafts/review-list?**', route => {
    const query = new URL(route.request().url()).searchParams
    requests.push(query)
    const source = query.get('stage') === 'discarded' ? [archived] : [pair, published, ready, closed, closedDraft]
    const rows = source.filter(row =>
      (!query.has('grade') || query.get('grade') === row.grade) &&
      (!query.has('stage') || query.get('stage') === row.stage) &&
      (!query.has('week') || query.get('week') === row.appliedWeek) &&
      (!query.has('source') || query.get('source') === row.source))
    return route.fulfill({ json: { items: rows, page: 0, size: 20, totalElements: rows.length, weeks: source.map(row => row.appliedWeek) } })
  })
  await page.goto('/admin/theme-drafts')
  const shelf = page.getByRole('region', { name: '주간 테마 목록', exact: true })
  await expect(shelf.getByRole('columnheader')).toHaveText(['테마명', '대상', '적용 주', '출처', '진행 상태', '상세 열기'])
  const pairRow = shelf.getByRole('row').filter({ hasText: pair.title })
  const publishedRow = shelf.getByRole('row').filter({ hasText: published.title })
  await expect(pairRow.getByText('영상 비교 대기')).toBeVisible()
  await expect(pairRow.locator('time')).toHaveAttribute('datetime', pair.appliedWeek)
  await expect(pairRow.locator('img')).toHaveAttribute('src', thumbnail)
  await expect.poll(() => pairRow.locator('img').evaluate(img => (img as HTMLImageElement).naturalWidth)).toBe(49)
  await expect(publishedRow.getByRole('img', { name: '대표 그림 없음' })).toBeVisible()
  const compare = new URL((await pairRow.getByRole('link', { name: pair.title + ' 상세 열기' }).getAttribute('href'))!, page.url())
  expect(compare.pathname).toBe('/admin/theme-drafts')
  expect(Object.fromEntries(compare.searchParams)).toMatchObject({ draftId: pair.draftId, scene: 'MON', view: 'compare' })
  for (const row of [published, ready, closed]) {
    const destination = new URL((await shelf.getByRole('link', { name: row.title + ' 상세 열기', exact: true }).getAttribute('href'))!, page.url())
    expect(destination.pathname).toBe('/admin/themes')
    expect(Object.fromEntries(destination.searchParams)).toMatchObject({ grade: row.grade, weekStart: row.appliedWeek, themeId: row.themeId })
  }
  const unselected = new URL((await shelf.getByRole('link', { name: closedDraft.title + ' 상세 열기' }).getAttribute('href'))!, page.url())
  expect(unselected.pathname).toBe('/admin/theme-drafts')
  expect(unselected.searchParams.get('draftId')).toBe(closedDraft.draftId)
  await shelf.getByLabel('학년 선택').selectOption('G4')
  await shelf.getByLabel('검수 상태 선택').selectOption('pair')
  await shelf.getByLabel('적용 주 선택').selectOption(pair.appliedWeek)
  await shelf.getByLabel('생성 출처 선택').selectOption('AUTO')
  await expect.poll(() => Object.fromEntries(requests.at(-1) ?? [])).toMatchObject({
    grade: 'G4', stage: 'pair', week: pair.appliedWeek, source: 'AUTO', hideDiscarded: 'true',
  })
  await expect(shelf.getByRole('row')).toHaveCount(2)
  await shelf.getByRole('button', { name: '초기화' }).click()
  await expect(shelf.getByRole('row')).toHaveCount(6)
  await page.getByRole('link', { name: '버림 이력', exact: true }).click()
  const history = page.getByRole('region', { name: '버림 이력', exact: true })
  await expect(history.getByRole('columnheader', { name: '버린 일시' })).toBeVisible()
  await history.getByLabel('생성 기준 주 선택').selectOption(archived.weekStart)
  const discarded = history.getByRole('row').filter({ hasText: archived.title })
  await expect(discarded.getByRole('img', { name: '대표 그림을 불러올 수 없음' })).toBeVisible()
  await expect(discarded.getByRole('link', { name: archived.title + ' 상세 열기' })).toHaveAttribute('href', new RegExp('draftId=' + archived.draftId))
  await expect.poll(() => Object.fromEntries(requests.at(-1) ?? [])).toMatchObject({ stage: 'discarded', week: archived.weekStart })
  expect(calls.filter(call => call.path.startsWith('/admin/theme-drafts/') && call.path !== reviewListPath)).toEqual([])
  await page.getByRole('link', { name: '검수 목록', exact: true }).click()
  await expect(shelf.getByRole('row')).toHaveCount(6)
  await publishedRow.getByRole('link', { name: published.title + ' 상세 열기', exact: true }).click()
  await expect(page.getByLabel('테마 제목', { exact: true })).toHaveValue('기존 테마')
  expect(calls.some(call => call.path === '/admin/weekly-themes/' + themeId && call.method === 'GET')).toBe(true)
  await page.goBack()
  await expect(shelf.getByRole('row')).toHaveCount(6)
})

test('목록 조회 오류를 다시 시도하고 페이지를 이동한 뒤 빈 필터와 버림 이력을 확인한다', async ({ page, context }) => {
  await confirmedResponses(context)
  let unavailable = true
  const rows = Array.from({ length: 21 }, (_, i) => ({ ...listRow, draftId: 'page-draft-' + i, title: '검수할 테마 ' + (i + 1) }))
  await context.route('**/api/v1/admin/theme-drafts/review-list?**', route => {
    if (unavailable) return route.fulfill({ status: 503, json: { code: 'LEARNING_UNAVAILABLE', status: 503, title: '검수 목록을 불러오지 못했습니다.' } })
    const filters = new URL(route.request().url()).searchParams
    const pageNumber = Number(filters.get('page')), size = Number(filters.get('size'))
    const filtered = filters.get('grade') === 'G6' || filters.get('stage') === 'discarded' ? [] : rows
    return route.fulfill({ json: { items: filtered.slice(pageNumber * size, (pageNumber + 1) * size), page: pageNumber, size,
      totalElements: filtered.length, weeks: [listRow.appliedWeek] } })
  })
  await page.goto('/admin/theme-drafts')
  const shelf = page.getByRole('region', { name: '주간 테마 목록' })
  await expect(shelf.getByRole('alert')).toContainText('검수 목록을 불러오지 못했습니다.')
  await expect(shelf.getByText(/조건에 맞는 테마/)).toHaveCount(0)
  unavailable = false
  await shelf.getByRole('button', { name: '다시 시도' }).click()
  const pager = shelf.getByRole('navigation', { name: '테마 초안 목록 페이지' })
  await expect(shelf.getByRole('row')).toHaveCount(21)
  await expect(pager.getByRole('button', { name: '이전 페이지' })).toBeDisabled()
  await pager.getByRole('button', { name: '다음 페이지' }).click()
  await expect(shelf.getByRole('link', { name: '검수할 테마 21 상세 열기' })).toBeVisible()
  await expect(shelf.getByRole('row')).toHaveCount(2)
  await expect(pager.getByRole('button', { name: '다음 페이지' })).toBeDisabled()
  await shelf.getByLabel('학년 선택').selectOption('G6')
  await expect(shelf.getByText(/조건에 맞는 테마가 없습니다/)).toBeVisible()
  expect(new URL(page.url()).searchParams.has('page')).toBe(false)
  await shelf.getByRole('button', { name: '초기화' }).click()
  await expect(shelf.getByRole('link', { name: '검수할 테마 1 상세 열기' })).toBeVisible()
  await shelf.getByLabel('검수 상태 선택').selectOption('discarded')
  await expect(page.getByRole('region', { name: '버림 이력' }).getByText('아직 버린 초안이 없습니다.')).toBeVisible()
})

test('운영 홈의 우선 검수 테마를 누르면 아직 비교하지 않은 실제 장면으로 들어간다', async ({ page, context }) => {
  await confirmedResponses(context)
  const pairId = '00000000-0000-4000-8000-000000000448'
  await context.route('**/api/v1/admin/theme-drafts/review-list?**', route => {
    const pair = new URL(route.request().url()).searchParams.get('stage') === 'pair'
    const item = pair ? { ...listRow, draftId: pairId, title: '목요일을 다시 만든 테마', stage: 'pair', comparisonScene: 'THU' } : listRow
    return route.fulfill({ json: { items: [item], page: 0, size: 1, totalElements: pair ? 2 : 3, weeks: [listRow.appliedWeek] } })
  })
  await context.route('**/api/v1/admin/theme-drafts/' + pairId, route => route.fulfill({ json: {
    draftId: pairId, status: 'READY', source: 'AUTO', grade: 'G4', weekStart: listRow.weekStart,
    draft: { theme: { title: '목요일을 다시 만든 테마', days: [] }, missions: [] }, scenes: [],
  } }))
  await page.goto('/admin/home')
  const queue = page.getByRole('region', { name: '테마 검수·게시' })
  await expect(queue.getByRole('link', { name: /초안 검수 대기/ })).toContainText('3건')
  await expect(queue.getByRole('link', { name: /재생성 장면 비교 대기/ })).toContainText('2건')
  await queue.getByRole('link', { name: '테마 검수 열기' }).click()
  await expect(page.getByRole('heading', { name: '목요일을 다시 만든 테마' })).toBeVisible()
  expect(Object.fromEntries(new URL(page.url()).searchParams)).toMatchObject({ draftId: pairId, scene: 'THU', view: 'compare' })
})

test('테마 요청·생성 중 상태·필터 연결: 생성 중에는 채택·버리기·다시 생성을 보이지 않는다', async ({ page, context }) => {
  const calls = await confirmedResponses(context)
  await page.goto('/admin/theme-drafts')
  await expect(page.getByRole('heading', { name: '주간 테마 검수', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '테마 추가 생성 요청', exact: true }).click()
  await page.getByLabel('생성 학년').selectOption('G6')
  await page.getByLabel('생성 적용 주').fill(requestWeek)
  await page.getByLabel('테마 주제 키워드').fill('도서관')
  const request = page.getByRole('button', { name: '검수용 초안 만들기', exact: true })
  await expectBlueAction(request)
  await request.click()
  await expect(page.getByRole('status').filter({ hasText: '생성 요청을 접수했습니다.' })).toBeVisible()
  expect(calls.filter(c => c.method === 'POST' && c.path === '/admin/theme-drafts')).toEqual([expect.objectContaining({ path: '/admin/theme-drafts', body: { grade: 'G6', weekStart: requestWeek, topic: '도서관' } })])
  await expect(page.getByRole('status').filter({ hasText: '생성 중입니다' })).toBeVisible()
  await expect(page.getByRole('button', { name: /채택|버리기|다시 생성/ })).toHaveCount(0)
  await page.goBack()
  await expect(page.getByRole('region', { name: '주간 테마 목록', exact: true })).toBeVisible()
  await expect(page.getByRole('dialog', { name: '테마 추가 생성 요청' })).toHaveCount(0)
  await page.getByLabel('생성 출처 선택').selectOption('AUTO')
  await expect.poll(() => calls.some(c => c.path === '/admin/theme-drafts/review-list' && c.search.includes('source=AUTO'))).toBe(true)
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
    if (width <= 768) {
      const menu = page.getByRole('button', { name: '메뉴', exact: true })
      await menu.click()
      const navigation = page.getByRole('navigation', { name: '관리자 메뉴' })
      await expect(navigation.getByRole('link', { name: '주간 테마 검수', exact: true })).toHaveAttribute('aria-current', 'page')
      await page.keyboard.press('Escape')
      await expect(navigation).toBeHidden()
      await expect(menu).toBeFocused()
      await page.getByRole('button', { name: '테마 추가 생성 요청' }).click()
      const dialog = page.getByRole('dialog', { name: '테마 추가 생성 요청' })
      await expect(dialog.getByLabel('생성 학년')).toBeVisible()
      await dialog.getByRole('button', { name: '취소' }).click()
      await expect(dialog).toBeHidden()
      await expect(page.getByLabel('생성 출처 선택')).toHaveValue('AUTO')
    }
    const header = await page.locator('.ad-topbar').boundingBox()
    const logout = await page.locator('.ad-topbar').getByRole('button', { name: '로그아웃', exact: true }).boundingBox()
    expect(logout!.y).toBeGreaterThanOrEqual(header!.y)
    expect(logout!.y + logout!.height).toBeLessThanOrEqual(header!.y + header!.height)
    const out = '.taste-skill/theme441'
    await mkdir(out, { recursive: true })
    // 정적 검사 HTML에서도 실제 화면의 로고를 별도 서버 없이 볼 수 있게 포함한다.
    await page.evaluate(async () => Promise.all([...document.images].filter(img => new URL(img.src).origin === location.origin).map(async img => {
      const blob = await (await fetch(img.src)).blob()
      img.src = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result)); reader.onerror = () => reject(reader.error)
        reader.readAsDataURL(blob)
      })
    })))
    const css = await page.evaluate(async () => Promise.all([...document.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"]')]
      .filter(link => new URL(link.href).origin === location.origin).map(async link => (await fetch(link.href)).text())))
    const html = (await page.content()).replace(/<script\b[\s\S]*?<\/script>/gi, '').replace(/<link\b[^>]*rel="stylesheet"[^>]*>/gi, '')
      .replace('<head>', '<head><base href="http://127.0.0.1:5278/">' + css.map(text => '<style>' + text + '</style>').join(''))
    await writeFile(`${out}/request-${width}.html`, html)
    await page.screenshot({ path: `${out}/request-${width}.png`, fullPage: true })
  }
})

test('완료 초안 상세에서 채택하면 같은 초안의 요일별 미션이 열리고 채택한 테마 편집기로 연결된다', async ({ page, context }) => {
  const calls = await confirmedResponses(context)
  const ready = {
    draftId: id, status: 'READY', source: 'ADMIN', grade: 'G3', weekStart: '2026-11-16', plannedWeek: null, attempts: 2, maxAttempts: 3,
    input: { topic: '도서관', missions: [{ thinkingType: 'ANALYZE', inputType: 'NARRATIVE', standardCodes: ['4과03-01'] }] },
    checkResults: [{ attempt: 1, failures: [{ stage: 'LEARNING', reasons: ['WED QUESTION_LENGTH 합성 사유'] }] }],
    draft: { theme: { title: '합성 테마', world: '', characters: [], styleNote: '', outfit: '', intro: '합성 시작 이야기', outro: '합성 종료 이야기',
      bigQuestion: '합성 큰 질문', candidates: ['가', '나'], answer: '가', days: [{ day: 'MON', thinkingType: 'ANALYZE', place: '', sceneNote: '', clue: '합성 단서', rulesOut: ['나'] }] },
    missions: [{ day: 'MON', thinkingType: 'ANALYZE', draft: { title: '합성 월요일 문제', question: '합성 질문', guide: null } }],
    dialogues: [], warnings: [] },
    scenes: [], failureCode: null, versions: { prompt: 'p', model: 'm' }, themeId: null, requestedBy: null, createdAt: '2026-11-12T00:00:00Z', updatedAt: '2026-11-12T00:00:00Z',
  }
  let adoptedThemeId: string | null = null
  await context.route('**/api/v1/admin/theme-drafts/' + id, route => route.fulfill({ json: {
    ...ready, status: adoptedThemeId ? 'ADOPTED' : 'READY', themeId: adoptedThemeId,
  } }))
  await context.route('**/api/v1/admin/missions/*', route => route.fulfill({ json: {
    missionId: new URL(route.request().url()).pathname.split('/').at(-1), status: 'DRAFT', currentVersion: 1,
    versions: [{ version: 1, title: '채택된 미션', question: '채택된 질문' }],
  } }))
  await context.route('**/api/v1/admin/theme-drafts/' + id + '/adopt', route => {
    adoptedThemeId = themeId
    calls.push({ path: '/admin/theme-drafts/' + id + '/adopt', method: route.request().method(), body: route.request().postDataJSON(), search: '' })
    return route.fulfill({ status: 201, json: { themeId, grade: 'G3', weekStart: '2026-11-16', title: '합성 테마', intro: '', days: [], status: 'DRAFT', updatedAt: '2026-11-12T00:00:00Z' } })
  })
  await page.goto('/admin/theme-drafts?draftId=' + id)
  await expect(page.getByRole('heading', { name: '합성 테마', exact: true })).toBeVisible()
  const storyboard = page.getByRole('navigation', { name: '검수 장면 선택' })
  await storyboard.getByRole('button',{name:/^종료 영상/}).click()
  await page.getByText('검수 설정과 생성 정보', { exact: true }).click()
  await expect(page.locator('.tw-story').getByText('합성 종료 이야기', { exact: true })).toBeVisible()
  await expect(page.getByText('WED QUESTION_LENGTH 합성 사유', { exact: false })).toBeVisible()
  await storyboard.getByRole('button',{name:/^월요일/}).click()
  await page.getByRole('button',{name:'이 요일 미션 보기'}).click()
  await expect(page.getByRole('dialog').getByText('합성 질문')).toBeVisible()
  await page.getByRole('button',{name:'월요일 장면 보기'}).click()
  await page.getByRole('button', { name: /^(초안 채택|이 주차로 채택)$/ }).click()
  await expect(page.getByRole('dialog')).toContainText('적용 주 2026-11-16')
  await page.getByRole('dialog').getByRole('button', { name: '채택', exact: true }).click()
  await expect(page).toHaveURL(url => url.pathname === '/admin/theme-drafts' && url.searchParams.get('draftId') === id && url.searchParams.get('view') === 'missions')
  await expect(page.getByRole('status').filter({ hasText: '초안을 채택했습니다.' })).toBeVisible()
  await expect(page.getByRole('region', { name: '요일별 미션', exact: true }).getByRole('listitem')).toHaveCount(5)
  await page.getByRole('link', { name: '채택한 테마 편집' }).click()
  await expect(page).toHaveURL(new RegExp('/admin/themes\\?themeId=' + themeId))
  expect(calls.filter(c => c.path.endsWith('/adopt'))).toEqual([expect.objectContaining({ method: 'POST', body: { expectedPlannedWeek: null } })])
})

test('유형별 선택은 기존 성취기준 표를 사용하고 요청에 지정한 필드만 보낸다', async ({ page, context }) => {
  const calls = await confirmedResponses(context)
  await page.goto('/admin/theme-drafts')
  await page.getByRole('button', { name: '테마 추가 생성 요청', exact: true }).click()
  await page.getByLabel('생성 학년').selectOption('G3')
  await page.getByLabel('생성 적용 주').fill(requestWeek)
  await page.getByText('생각 유형별 성취기준·입력 방식 직접 지정', { exact: true }).click()
  await page.getByRole('checkbox', { name: '분석하기 직접 지정', exact: true }).check()
  await page.getByLabel('분석하기 입력 방식', { exact: true }).selectOption('NARRATIVE')
  await page.getByRole('button', { name: '4과03-01 고르기', exact: true }).click()
  await page.getByRole('button', { name: '검수용 초안 만들기', exact: true }).click()
  await expect.poll(() => calls.filter(c => c.method === 'POST' && c.path === '/admin/theme-drafts').length).toBe(1)
  expect(calls.find(c => c.method === 'POST' && c.path === '/admin/theme-drafts')?.body).toEqual({ grade: 'G3', weekStart: requestWeek, missions: [{ thinkingType: 'ANALYZE', standardCodes: ['4과03-01'], inputType: 'NARRATIVE' }] })
})

test('접수 결과가 불명확한 503은 성공 처리와 자동 재요청 없이 목록 확인을 안내한다', async ({ page, context }) => {
  const calls = await confirmedResponses(context, true, true)
  await page.goto('/admin/theme-drafts')
  await page.getByRole('button', { name: '테마 추가 생성 요청', exact: true }).click()
  await page.getByLabel('생성 학년').selectOption('G3')
  await page.getByLabel('생성 적용 주').fill(requestWeek)
  await page.getByRole('button', { name: '검수용 초안 만들기', exact: true }).click()
  await expect(page.getByRole('note').filter({ hasText: '새로 요청하기 전에 목록을 먼저 확인' })).toBeVisible()
  expect(calls.filter(c => c.method === 'POST' && c.path === '/admin/theme-drafts')).toHaveLength(1)
  await expect(page.getByText('생성 요청을 접수했습니다.', { exact: false })).toHaveCount(0)
})

test('요청 창이 미입력 학년과 잘못된 주를 막고 이미 게시된 주의 오류에서 입력을 보존한다', async ({ page, context }) => {
  await confirmedResponses(context)
  const submitted: unknown[] = []
  await context.route('**/api/v1/admin/theme-drafts', route => {
    submitted.push(route.request().postDataJSON())
    return route.fulfill({ status: 409, json: { code: 'WEEK_LOCKED', status: 409, title: '이미 게시가 확정된 주차입니다.' } })
  })
  await page.goto('/admin/theme-drafts?request=1')
  const dialog = page.getByRole('dialog', { name: '테마 추가 생성 요청' })
  const submit = dialog.getByRole('button', { name: '검수용 초안 만들기' })
  const grade = dialog.getByLabel('생성 학년')
  const date = dialog.getByLabel('생성 적용 주')
  await expect(grade).toBeFocused()
  await submit.click()
  await expect(grade).toBeFocused()
  await expect(grade).toHaveAttribute('aria-invalid', 'true')
  await expect(dialog.getByText('대상 학년을 선택해 주세요.', { exact: true })).toBeVisible()
  await grade.selectOption('G4')
  const monday = (await date.getAttribute('min'))!
  const invalidDate = (delta: number) => new Date(Date.parse(monday + 'T00:00:00Z') + delta * 86400000).toISOString().slice(0, 10)
  for (const [offset, message] of [[-7, '이번 주 또는 이후 주의 월요일을 선택해 주세요.'], [1, '적용 주는 월요일 날짜로 선택해 주세요.']] as const) {
    await date.fill(invalidDate(offset))
    await submit.click()
    await expect(date).toBeFocused()
    await expect(date).toHaveAttribute('aria-invalid', 'true')
    await expect(date).toHaveAccessibleDescription(new RegExp(message.replaceAll('.', '\\.')))
  }
  expect(submitted).toEqual([])
  await date.fill(requestWeek)
  await dialog.getByLabel('테마 주제 키워드').fill('정원')
  await submit.click()
  await expect(dialog.getByRole('alert')).toContainText('이미 게시가 확정된 주차입니다.')
  await expect(dialog.getByLabel('테마 주제 키워드')).toHaveValue('정원')
  await expect(date).toHaveValue(requestWeek)
  await dialog.getByRole('button', { name: '취소' }).click()
  await expect(dialog).toBeHidden()
  expect(submitted).toEqual([{ grade: 'G4', weekStart: requestWeek, topic: '정원' }])
})

test('CONTENT 권한 없이 메뉴/요청 화면에 접근해도 테마 API를 호출하지 않는다', async ({ page, context }) => {
  const calls = await confirmedResponses(context, false)
  await page.goto('/admin/theme-drafts?request=1')
  await expect(page.getByRole('heading', { name: '접근 권한 확인', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: '주간 테마 검수', exact: true })).toHaveCount(0)
  await expect(page.getByRole('dialog')).toHaveCount(0)
  expect(calls.some(c => c.path.startsWith('/admin/theme-drafts'))).toBe(false)
})

test('기존 테마 식별자 링크로 편집기를 열고 연결된 미션 5개의 편집 링크를 보존한다', async ({ page, context }) => {
  await confirmedResponses(context)
  await page.goto('/admin/themes?themeId=' + themeId)
  await expect(page.getByRole('textbox', { name: '테마 제목', exact: true })).toHaveValue('기존 테마')
  await expect(page.getByRole('link', { name: /요일 미션 편집$/ })).toHaveCount(5)
  await expect(page.getByLabel('월요일 미션', { exact: true })).toHaveValue('00000000-0000-4000-8000-000000000001')
  await context.route('**/api/v1/admin/missions/00000000-0000-4000-8000-000000000003',route=>route.fulfill({status:404,json:{status:404,code:'NOT_FOUND',title:'미션 상세 응답 없음'}}))
  await page.getByRole('link',{name:'수요일 미션 편집'}).click()
  await expect(page).toHaveURL(/themeDay=WED/)
  await page.getByRole('button',{name:'수요일 테마 검수로'}).click()
  await expect(page).toHaveURL(new RegExp('themeId='+themeId+'&day=WED'))
  await expect(page.getByLabel('수요일 미션',{exact:true})).toBeFocused()
  await page.getByRole('button', { name: '닫기', exact: true }).click()
  await expect(page.getByRole('textbox', { name: '테마 제목', exact: true })).toHaveCount(0)
  expect(new URL(page.url()).searchParams.has('themeId')).toBe(false)
})

test('채택한 초안에서 미션 5개 게시 후 검토를 요청하고 해당 학년과 주의 편성표로 이동한다', async ({ page, context }) => {
  await confirmedResponses(context)
  const theme = {
    themeId, title: '채택한 합성 테마', grade: 'G3', weekStart: '2026-11-16', status: 'DRAFT', version: 2,
    days: days.map((day, n) => ({ day, missionId: `00000000-0000-4000-8000-00000000000${n + 1}` })),
  }
  const tuesdayId = theme.days[1].missionId
  let tuesdayStatus = 'DRAFT'
  let approved = false
  const versionPair = { missionVersion: 2, rubricVersion: 1 }
  const missionWrites: { action: string; body: unknown }[] = []
  function missionDetail(missionId: string) {
    const index = Number(missionId.slice(-1))
    const status = missionId === tuesdayId ? tuesdayStatus : 'PUBLISHED'
    return {
      missionId, status, currentVersion: 2, currentRubricVersion: 1,
      publishedVersion: status === 'PUBLISHED' ? 2 : null, publishedRubricVersion: status === 'PUBLISHED' ? 1 : null,
      versions: [{
        version: 2, title: '개정 미션 ' + index, question: '개정 질문 ' + index, thinkingType: 'ANALYZE',
        subject: '과학', gradeMin: 3, gradeMax: 4, inputType: 'NARRATIVE', achievementStandards: ['4과03-01'],
      }],
      rubrics: [{ version: 1, elements: [{ code: 'e1', label: '이유', points: 1 }], exampleAnswer: '단서의 이유를 설명한다.' }],
      reviews: missionId === tuesdayId && !approved ? [] : [{ ...versionPair, result: 'APPROVED' }],
    }
  }
  const reviews: unknown[] = []
  await context.route('**/api/v1/admin/weekly-themes/' + themeId, route => route.fulfill({ json: theme }))
  await context.route('**/api/v1/admin/weekly-themes/' + themeId + '/review-request', route => {
    expect(route.request().method()).toBe('POST')
    reviews.push(route.request().postDataJSON())
    theme.version++
    if (reviews.length === 1) {
      return route.fulfill({ status: 409, json: { code: 'VERSION_CONFLICT', status: 409, title: '테마 버전이 변경됐습니다.' } })
    }
    theme.status = 'REVIEW_REQUIRED'
    return route.fulfill({ json: theme })
  })
  await context.route('**/api/v1/admin/theme-drafts/' + id, route => route.fulfill({ json: {
    draftId: id, themeId, status: 'ADOPTED', grade: 'G3',
    draft: { theme: { title: '채택한 합성 테마', days: [] }, missions: [
      { day: 'TUE', draft: { title: '수정 전 제목', question: '수정 전 질문' } },
    ], warnings: [] },
  } }))
  await context.route('**/api/v1/admin/missions/*', route => {
    const missionId = new URL(route.request().url()).pathname.split('/').at(-1)!
    return route.fulfill({ json: missionDetail(missionId) })
  })
  await context.route('**/api/v1/admin/missions/' + tuesdayId + '/*', route => {
    const action = new URL(route.request().url()).pathname.split('/').at(-1)!
    expect(route.request().method()).toBe('POST')
    missionWrites.push({ action, body: route.request().postDataJSON() })
    if (action === 'review-request') tuesdayStatus = 'REVIEW_REQUIRED'
    else if (action === 'review') approved = true
    else if (action === 'publish') tuesdayStatus = 'PUBLISHED'
    else return route.fulfill({ status: 404 })
    return route.fulfill({ json: missionDetail(tuesdayId) })
  })
  const missionUrl = '/admin/theme-drafts?' + new URLSearchParams({ draftId: id, view: 'missions' })
  await page.goto(missionUrl)
  const missions = page.getByRole('region', { name: '요일별 미션', exact: true })
  const review = page.getByRole('button', { name: '테마 검토 요청', exact: true })
  await expect(missions).toContainText('4 / 5 게시')
  await expect(page.getByText('미션 4 / 5개 게시 완료', { exact: true })).toBeVisible()
  await expect(review).toBeDisabled()
  await expect(missions.getByRole('listitem').first()).toContainText('게시 완료')
  const tuesday = missions.getByRole('listitem').filter({ hasText: '화요일 미션' })
  await expect(tuesday).toContainText('개정 미션 2')
  await tuesday.getByRole('button', { name: '검토하기' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('개정 질문 2')
  await expect(dialog.getByRole('link', { name: '미션 검토·게시 화면' })).toHaveAttribute('href',
    '/admin/missions?' + new URLSearchParams({ missionId: tuesdayId, themeId, themeDay: 'TUE' }))
  const publish = dialog.getByRole('button', { name: '이 미션 승인·게시' })
  await expect(publish).toBeDisabled()
  await dialog.getByRole('checkbox', { name: '학생에게 보일 내용을 확인했습니다.' }).check()
  await publish.click()
  await expect(dialog).toHaveCount(0)
  await expect(tuesday).toContainText('게시 완료')
  expect(missionWrites).toEqual([
    { action: 'review-request', body: versionPair },
    { action: 'review', body: { ...versionPair, result: 'APPROVED', comment: '' } },
    { action: 'publish', body: {} },
  ])
  await expect(page.getByText('미션 5 / 5개 게시 완료', { exact: true })).toBeVisible()
  const selectedMissionUrl = page.url()
  await expectBlueAction(review)
  await review.click()
  await expect(dialog).toContainText('v2')
  await dialog.getByRole('button', { name: '취소' }).click()
  expect(reviews).toEqual([])
  await review.click()
  await dialog.getByRole('button', { name: '검토 요청', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: '테마 버전이 변경됐습니다.' })).toBeVisible()
  await expect(page).toHaveURL(selectedMissionUrl)
  await review.click()
  await expect(dialog).toContainText('v3')
  await dialog.getByRole('button', { name: '검토 요청', exact: true }).click()
  const boardUrl = '/admin/themes?' + new URLSearchParams({ grade: theme.grade, weekStart: theme.weekStart })
  await expect(page).toHaveURL(new URL(boardUrl, page.url()).href)
  await page.goto(missionUrl)
  const planner = page.getByRole('link', { name: '주차별 편성·게시로' })
  await expect(planner).toHaveAttribute('href', boardUrl)
  await expectBlueAction(planner)
  expect(reviews).toEqual([{ expectedVersion: 2 }, { expectedVersion: 3 }])
  theme.status = 'PUBLISHED'
  await page.reload()
  await expect(page.getByRole('link', { name: '게시 내용 보기' })).toHaveAttribute('href', '/admin/themes?themeId=' + themeId)
  await context.route('**/api/v1/admin/missions/' + theme.days[2].missionId, route =>
    route.fulfill({ status: 503, json: { status: 503, code: 'UNAVAILABLE', title: '미션 게시 상태를 조회할 수 없습니다.' } }))
  await page.reload()
  await expect(missions.getByRole('alert')).toContainText('미션 게시 상태를 조회할 수 없습니다.')
  await expect(missions.getByText(/\d \/ 5 게시/)).toHaveCount(0)
  await expect(review).toHaveCount(0)
})

test('학년 네 개로 요청하고 논술 선택은 초5·초6에서만 제공하며 성취기준은 학년군으로 조회한다', async ({ page, context }) => {
  const calls = await confirmedResponses(context)
  await page.goto('/admin/theme-drafts')
  await page.getByRole('button', { name: '테마 추가 생성 요청', exact: true }).click()
  const grade = page.getByLabel('생성 학년', { exact: true })
  await expect(grade).toHaveValue('')
  await expect(grade.locator('option')).toHaveText(['학년 선택', '초등 3학년', '초등 4학년', '초등 5학년', '초등 6학년'])
  await page.getByLabel('생성 적용 주').fill(requestWeek)
  await page.getByText('생각 유형별 성취기준·입력 방식 직접 지정', { exact: true }).click()
  for (const value of ['G3', 'G4', 'G5', 'G6']) {
    await grade.selectOption(value)
    const checkbox = page.getByRole('checkbox', { name: '따져 보기 직접 지정', exact: true })
    await expect(checkbox).not.toBeChecked()
    await checkbox.check()
    const input = page.getByLabel('따져 보기 입력 방식', { exact: true })
    await expect(input.locator('option[value=ESSAY]')).toHaveCount(value === 'G3' || value === 'G4' ? 0 : 1)
    await expect(page.getByLabel('성취기준 학년군', { exact: true })).toHaveValue(value === 'G3' || value === 'G4' ? '초3~4' : '초5~6')
    await checkbox.uncheck()
    await page.getByRole('button', { name: '검수용 초안 만들기', exact: true }).click()
    await expect.poll(() => calls.filter(c => c.path === '/admin/theme-drafts' && c.method === 'POST').at(-1)?.body).toEqual({ grade: value, weekStart: requestWeek })
    await page.getByRole('button', {name:'검수함',exact:true}).click()
    await page.getByRole('button', { name: '테마 추가 생성 요청',exact:true}).click()
    await page.getByLabel('생성 적용 주').fill(requestWeek)
    await page.getByText('생각 유형별 성취기준·입력 방식 직접 지정',{exact:true}).click()
  }
  const standardCalls = calls.filter(c => c.path === '/admin/achievement-standards')
  expect(standardCalls.some(c => new URLSearchParams(c.search).get('gradeBand') === '초3~4')).toBe(true)
  expect(standardCalls.some(c => new URLSearchParams(c.search).get('gradeBand') === '초5~6')).toBe(true)
})

test('테마 목록 필터·기존 테마 편집도 학년 하나를 전송한다', async ({ page, context }) => {
  const calls = await confirmedResponses(context)
  const grades:string[]=[]
  await context.route('**/api/v1/admin/weekly-themes/planner?**',route=>{
    const q=new URL(route.request().url()).searchParams
    grades.push(q.get('grade')!)
    return route.fulfill({json:{grade:q.get('grade'),weekStart:q.get('weekStart'),weeks:[],candidates:[]}})
  })
  await page.goto('/admin/themes?grade=G3')
  const filter = page.getByLabel('테마 학년', { exact: true })
  await expect(filter.locator('option')).toHaveText(['초3', '초4', '초5', '초6'])
  await filter.selectOption('G4')
  await expect.poll(()=>grades).toContain('G4')
  await page.goto('/admin/themes?themeId=' + themeId)
  await expect(page.getByLabel('학년', { exact: true })).toHaveValue('G3')
  await page.getByLabel('학년', { exact: true }).selectOption('G4')
  await page.getByRole('button', { name: '테마 저장', exact: true }).click()
  await expect.poll(() => calls.find(c => c.path === '/admin/weekly-themes/' + themeId && c.method === 'PUT')?.body).toEqual(expect.objectContaining({ grade: 'G4' }))
  expect(calls.find(c => c.path === '/admin/weekly-themes/' + themeId && c.method === 'PUT')?.body).not.toHaveProperty('gradeBand')
})

test('#537 부분 다시 생성: 활성 장면의 대상만 요청하고 검수 위치에서 처리 상태와 원래 초안을 확인한다', async ({ page, context }) => {
  const calls = await confirmedResponses(context)
  const next = '00000000-0000-4000-8000-000000000537'
  const selectedSource = '00000000-0000-4000-8000-000000000536'
  const ready = {
    draftId: id, status: 'READY', source: 'ADMIN', grade: 'G3', weekStart: '2026-11-16', attempts: 1, maxAttempts: 3,
    input: { topic: '도서관', missions: [], regenerate: null }, checkResults: [],
    draft: { theme: { title: '합성 테마', intro: '합성 시작 이야기', outro: '합성 종료 이야기', bigQuestion: '합성 큰 질문', candidates: ['가', '나'], answer: '가',
      days: days.map(day => ({ day, thinkingType: 'ANALYZE', place: '', clue: '', rulesOut: [] })) },
    missions: days.map(day => ({ day, thinkingType: 'ANALYZE', draft: { title: `합성 ${day} 문제`, question: '합성 질문', guide: null } })),
    dialogues: [], warnings: [] },
    scenes: [], regenerableTargets: ['IMAGE:INTRO', 'IMAGE:MON', 'MISSION:MON'],
    failureCode: null, versions: { prompt: 'p', model: 'm' }, themeId: null, requestedBy: null, createdAt: '2026-11-17T00:00:00Z', updatedAt: '2026-11-17T00:00:00Z',
  }
  await context.route('**/api/v1/admin/theme-drafts/' + id, route => route.fulfill({ json: ready }))
  await context.route('**/api/v1/admin/theme-drafts/' + selectedSource, route => route.fulfill({ json: {
    ...ready, draftId: selectedSource, regenerableTargets: ['VIDEO:INTRO', 'IMAGE:INTRO'],
  } }))
  await context.route('**/api/v1/admin/theme-drafts/' + id + '/scenes/INTRO/versions', route => route.fulfill({ json: {
    rootDraftId: id, scene: 'INTRO', selectedVersionId: selectedSource, editable: true,
    versions: [selectedSource, id].map((versionId, index) => ({
      versionId, number: 2 - index, source: index ? 'ORIGINAL' : 'REGENERATED', createdAt: ready.updatedAt, status: 'READY',
      starred: false, note: '', selectable: true, motion: null, imageUrl: null, videoUrl: null,
    })),
  } }))
  await context.route('**/api/v1/admin/theme-drafts/' + next, route => route.fulfill({ json: {
    draftId: next, status: 'GENERATING', source: 'ADMIN', grade: 'G3', weekStart: '2026-11-16',
    input: { topic: '도서관', missions: [], regenerate: { baseDraftId: selectedSource, targets: ['VIDEO:INTRO'] } }, regenerableTargets: [] } }))
  await context.route('**/api/v1/admin/theme-drafts/' + selectedSource + '/regenerate', route => {
    calls.push({ path: '/admin/theme-drafts/' + selectedSource + '/regenerate', method: route.request().method(), body: route.request().postDataJSON(), search: '' })
    return route.fulfill({ status: 202, json: { draftId: next, status: 'GENERATING', input: { regenerate: { baseDraftId: selectedSource, targets: ['VIDEO:INTRO'] } } } })
  })
  await page.goto('/admin/theme-drafts?draftId=' + id)
  const controls = page.locator('.tw-regen-row').filter({ has: page.getByRole('button', { name: /^(영상|그림) 다시 생성$/ }) })
  const video = controls.getByRole('button', { name: '영상 다시 생성', exact: true })
  const image = controls.getByRole('button', { name: '그림 다시 생성', exact: true })
  await expect(controls).toHaveCount(1)
  await expect(controls.getByText('재생성 1차', { exact: true })).toBeVisible()
  await expectBlueAction(video)
  await expect(image).toBeEnabled()
  await expect(image).not.toHaveClass(/rv-primary/)
  await expect(page.locator('.rv-settings')).not.toHaveAttribute('open', '')
  const storyboard = page.getByRole('navigation', { name: '검수 장면 선택' })
  await storyboard.getByRole('button',{name:/^월요일/}).click()
  await expectBlueAction(image)
  await expect(controls.getByRole('button', { name: '미션 다시 생성', exact: true })).toBeEnabled()
  await storyboard.getByRole('button',{name:/^화요일/}).click()
  await expect(image).toBeDisabled()
  await expect(page.locator('.tw-regen-reason')).toBeVisible()
  await expect(image).toHaveAccessibleDescription(/재생성 자료가 없습니다/)
  await expect(image).toHaveCSS('color', 'rgb(71, 85, 105)')
  await expect(image).toHaveCSS('background-color', 'rgb(229, 234, 242)')
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  }
  await storyboard.getByRole('button',{name:/^시작 영상/}).click()
  await video.focus()
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog', { name: '시작 영상 다시 만들기 확인' })
  await expect(dialog).toContainText('시작 영상만 다시 만들까요? 그림·글은 그대로 둡니다.')
  await page.keyboard.press('Escape')
  await expect(video).toBeFocused()
  expect(calls.filter(c => c.path.endsWith('/regenerate'))).toEqual([])
  await video.click()
  const confirm = dialog.getByRole('button', { name: '다시 만들기', exact: true })
  await expectBlueAction(confirm)
  await confirm.click()
  await expect(page).toHaveURL(new RegExp('draftId=' + id))
  await expect(page.getByText('부분 생성 · 생성 중')).toBeVisible()
  await page.getByRole('button',{name:'요청한 초안 열기'}).click()
  await expect(page).toHaveURL(new RegExp('draftId=' + next))
  expect(calls.filter(c => c.path.endsWith('/regenerate'))).toEqual([expect.objectContaining({
    path: '/admin/theme-drafts/' + selectedSource + '/regenerate', method: 'POST', body: { targets: ['VIDEO:INTRO'] },
  })])
  await expect(page.getByText('시작 영상만 다시 만듦', { exact: false })).toBeVisible()
  await expect(page.getByRole('button', { name: /다시 만들기|다시 생성/ })).toHaveCount(0) // 생성 중에는 장면·전체 다시 생성 모두 없음
  await page.getByRole('button', { name: '원래 초안 열기', exact: true }).click()
  await expect(page).toHaveURL(new RegExp('draftId=' + selectedSource))
  await expect(page.getByRole('heading', { name: '합성 테마', exact: true })).toBeVisible()
})

test('제목 옆에서 전체 재생성을 확인하면 새 초안이 열리고 원본과 읽기 전용 장면은 보존된다', async ({ page, context }) => {
  const calls = await confirmedResponses(context)
  const copyId = '00000000-0000-4000-8000-000000000538'
  const original = {
    draftId: id, status: 'READY', grade: 'G3', weekStart: '2026-11-16', weekLocked: false, themeId: null as string | null,
    draft: { theme: { title: '별빛 도서관', intro: '보존할 원래 시작 이야기' }, missions: [] },
    regenerableTargets: ['VIDEO:INTRO', 'IMAGE:INTRO'],
  }
  const copies: unknown[] = []
  await context.route('**/api/v1/admin/theme-drafts/' + id, route => route.fulfill({ json: original }))
  await context.route('**/api/v1/admin/theme-drafts/' + copyId, route => route.fulfill({ json: { draftId: copyId, status: 'GENERATING' } }))
  await context.route('**/api/v1/admin/theme-drafts/' + id + '/regenerate', route => {
    expect(route.request().method()).toBe('POST')
    copies.push(route.request().postDataJSON())
    return route.fulfill({ status: 202, json: { draftId: copyId, status: 'GENERATING' } })
  })
  const originalUrl = '/admin/theme-drafts?draftId=' + id
  await page.goto(originalUrl)
  const header = page.locator('.rv-title-line')
  const whole = header.getByRole('button', { name: '초안 전체 다시 생성', exact: true })
  await expect(header.getByRole('heading', { name: '별빛 도서관' })).toBeVisible()
  await expectBlueAction(whole)
  await whole.click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('별도의 새 초안')
  await dialog.getByRole('button', { name: '취소' }).click()
  expect(copies).toEqual([])
  await whole.click()
  await dialog.getByRole('button', { name: '새 초안 생성', exact: true }).click()
  await expect(page).toHaveURL(new RegExp('draftId=' + copyId))
  await expect(page.getByRole('status').filter({ hasText: '생성 중입니다.' })).toBeVisible()
  expect(copies).toEqual([{}])
  await page.goto(originalUrl)
  await expect(header.getByRole('heading', { name: '별빛 도서관' })).toBeVisible()
  await page.getByText('검수 설정과 생성 정보', { exact: true }).click()
  await expect(page.getByText('보존할 원래 시작 이야기', { exact: true })).toBeVisible()

  for (const state of [
    { status: 'ADOPTED', locked: false, reason: /채택한 초안/ },
    { status: 'READY', locked: true, reason: /확정된 주차/ },
    { status: 'DISCARDED', locked: false, reason: /버린 초안/ },
  ]) {
    original.status = state.status
    original.weekLocked = state.locked
    original.themeId = state.status === 'ADOPTED' ? themeId : null
    await page.reload()
    const scene = page.locator('.tw-regen-row').getByRole('button', { name: '영상 다시 생성', exact: true })
    await expect(scene).toBeDisabled()
    await expect(scene).toHaveAccessibleDescription(state.reason)
    await expect(page.locator('.tw-regen-reason')).toBeVisible()
    await expect(whole).toHaveCount(0)
    if (state.status === 'DISCARDED') await expect(header.getByRole('button', { name: '이 초안으로 새 초안 생성' })).toBeEnabled()
  }
  expect(copies).toEqual([{}])
  expect(calls.filter(c => ['PATCH', 'PUT', 'DELETE'].includes(c.method))).toEqual([])
})

test('비교 대기 장면은 가로로 열리고 두 영상의 오류 복구, 동시 재생과 독립 탐색을 지원한다', async ({ page, context }) => {
  await confirmedResponses(context)
  await context.route('**/api/v1/admin/theme-drafts/' + id, route => route.fulfill({ json: {
    draftId: id, status: 'READY', grade: 'G3', draft: { theme: { title: '시간 맞춰 보기' }, missions: [] },
  } }))
  const versions = ['original', 'new'].map((versionId, index) => ({
    versionId, number: index + 1, source: index ? 'REGENERATED' : 'ORIGINAL', status: 'READY', createdAt: '2026-11-16T10:00:00Z',
    starred: false, note: '', selectable: true, motion: null, imageUrl: null, videoUrl: '/test-media/' + versionId + '.webm',
  }))
  await context.route('**/api/v1/admin/theme-drafts/' + id + '/scenes/*/versions', route => {
    const scene = new URL(route.request().url()).pathname.split('/').at(-2)
    return route.fulfill({ json: { scene, rootDraftId: id, editable: true, selectedVersionId: 'original', versions,
      ...(scene === 'INTRO' ? { comparisonPending: true } : scene === 'MON' ? { comparisonPending: false } : {}),
    } })
  })
  // Eight seconds of synthetic VP8 frames. The browser decodes both videos and runs its own media clocks.
  const clip = await readFile(new URL('./fixtures/scene-playback.webm', import.meta.url))
  let unavailable = true
  await context.route('**/test-media/*.webm', route => {
    if (unavailable && route.request().url().endsWith('/new.webm')) return route.fulfill({ status: 503, body: '' })
    const range = /^bytes=(\d+)-(\d*)$/.exec(route.request().headers().range ?? '')
    const begin = range ? Number(range[1]) : 0
    const end = range?.[2] ? Math.min(Number(range[2]), clip.length - 1) : clip.length - 1
    return route.fulfill({ status: range ? 206 : 200, contentType: 'video/webm', body: clip.subarray(begin, end + 1),
      headers: { 'Accept-Ranges': 'bytes', ...(range ? { 'Content-Range': `bytes ${begin}-${end}/${clip.length}` } : {}) },
    })
  })
  await page.goto('/admin/theme-drafts?draftId=' + id)
  const left = page.getByRole('region', { name: '왼쪽 비교본' }).locator('video')
  const rightCard = page.getByRole('region', { name: '오른쪽 비교본' })
  const right = rightCard.locator('video')
  const start = page.getByRole('button', { name: '함께 재생', exact: true })
  const stop = page.getByRole('button', { name: '함께 일시정지', exact: true })
  const linked = page.getByRole('checkbox', { name: '재생 위치 연결' })
  await expect(rightCard.getByRole('alert')).toContainText('영상 파일을 불러오지 못했습니다.')
  await expect(start).toBeDisabled()
  unavailable = false
  await rightCard.getByRole('button', { name: '다시 불러오기' }).click()
  await expect.poll(() => right.evaluate((video: HTMLVideoElement) => video.readyState)).toBeGreaterThanOrEqual(3)
  await expect.poll(() => left.evaluate((video: HTMLVideoElement) => video.readyState)).toBeGreaterThanOrEqual(3)
  await expect.poll(() => left.evaluate((video: HTMLVideoElement) => video.seekable.length ? video.seekable.end(0) : 0)).toBeGreaterThan(4)
  await expect(linked).toBeChecked()
  await left.evaluate((video: HTMLVideoElement) => { video.currentTime = 2 })
  await expect.poll(() => right.evaluate((video: HTMLVideoElement) => video.currentTime)).toBeCloseTo(2, 1)
  await start.click()
  await expect.poll(() => left.evaluate((video: HTMLVideoElement) => video.currentTime)).toBeGreaterThan(2.15)
  await stop.click()
  await expect.poll(() => left.evaluate((video: HTMLVideoElement) => video.paused)).toBe(true)
  await expect.poll(() => right.evaluate((video: HTMLVideoElement) => video.paused)).toBe(true)
  const leftTime = await left.evaluate((video: HTMLVideoElement) => video.currentTime)
  expect(Math.abs(leftTime - await right.evaluate((video: HTMLVideoElement) => video.currentTime))).toBeLessThan(0.2)
  await linked.uncheck()
  await right.evaluate((video: HTMLVideoElement) => { video.currentTime = 4 })
  await expect.poll(() => right.evaluate((video: HTMLVideoElement) => video.seeking)).toBe(false)
  await start.click()
  await expect.poll(() => right.evaluate((video: HTMLVideoElement) => video.currentTime)).toBeGreaterThan(4.15)
  await stop.click()
  expect(await right.evaluate((video: HTMLVideoElement) => video.currentTime) - await left.evaluate((video: HTMLVideoElement) => video.currentTime)).toBeGreaterThan(1)

  // Swapping the cards keeps each clip's own paused position and the scene's link preference.
  const beforeSwap = await Promise.all([left, right].map(card => card.evaluate((video: HTMLVideoElement) => video.currentTime)))
  await page.getByRole('button', { name: '좌우 바꾸기' }).click()
  await expect(linked).not.toBeChecked()
  await expect.poll(() => left.evaluate((video: HTMLVideoElement) => video.currentTime)).toBeCloseTo(beforeSwap[1], 1)
  await expect.poll(() => right.evaluate((video: HTMLVideoElement) => video.currentTime)).toBeCloseTo(beforeSwap[0], 1)
  await expect.poll(() => left.evaluate((video: HTMLVideoElement) => video.paused)).toBe(true)

  const board = page.getByRole('navigation', { name: '검수 장면 선택' })
  for (const label of ['월요일', '화요일']) {
    await board.getByRole('button', { name: new RegExp('^' + label) }).click()
    await expect(page.locator('.tw-single')).toBeVisible()
    await expect(rightCard).toHaveCount(0)
  }
  await board.getByRole('button', { name: /^시작 영상/ }).click()
  await expect(rightCard).toBeVisible()
  await expect(linked).not.toBeChecked()
  await page.getByRole('button', { name: '단일 보기' }).click()
  await expect(page.locator('.tw-single')).toBeVisible()
})

test('#882 이력의 최근 3개와 별표·메모 검색, 독립 비교 및 요일 선택본 복원', async({page,context})=>{
  await confirmedResponses(context)
  const ids = [id, ...['102','103','104'].map(n=>'00000000-0000-4000-8000-000000000'+n)]
  const versions = ids.map((versionId,i)=>({ versionId, number:i+1, source:i?'REGENERATED':'ORIGINAL',
    createdAt:'2026-11-'+(10+i)+'T03:00:00Z',status:'READY',starred:false,note:'',selectable:true,
    imageUrl:'data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="160" height="90"><rect width="160" height="90" fill="'+['coral','gold','skyblue','gray'][i]+'"/></svg>'),
    videoUrl:null,motion:null })).reverse()
  let selected: string | null = ids[0], selections = 0
  const ready={ draftId:id,status:'READY',grade:'G4',source:'AUTO',weekStart:'2026-11-23',plannedWeek:null,
    regenerableTargets:['IMAGE:MON'],
    draft:{theme:{title:'숲속 발자국',intro:'시작',outro:'끝',days:[{day:'MON',clue:'커다란 발자국'}]},
      missions:[{day:'MON',draft:{title:'월요일의 흔적',question:'어느 발자국이 더 클까요?'}}],dialogues:[{day:'MON',lines:[{speaker:'뭉치',text:'발자국을 확인하자!'}]}],warnings:[]}}
  await context.route('**/api/v1/admin/theme-drafts/'+id,route=>route.fulfill({json:ready}))
  await context.route('**/api/v1/admin/theme-drafts/'+ids[2],route=>route.fulfill({json:{...ready,draftId:ids[2]}}))
  await context.route(new RegExp('/api/v1/admin/theme-drafts/'+id+'/scenes/[A-Z]+/versions(?:/[^/?]+)?$'),async route=>{
    const req=route.request(), path=new URL(req.url()).pathname, scene=path.split('/scenes/')[1].split('/')[0]
    const body=req.postData()?req.postDataJSON():{}
    if(req.method()==='PUT'){
      expect(body.expectedVersionId).toBe(selected);expect(body.expectedVersionCount).toBe(4)
      selected=body.versionId;selections++
    }else if(req.method()==='PATCH'){
      Object.assign(versions.find(v=>v.versionId===path.split('/').at(-1))!,body)
    }
    return route.fulfill({json:{rootDraftId:id,editable:true,scene,selectedVersionId:scene==='MON'?selected:ids[0],versions:scene==='MON'?versions:[versions.at(-1)]}})
  })
  await page.setViewportSize({ width: 1600, height: 1000 })
  await page.goto('/admin/theme-drafts?draftId='+id)
  await expect(page.getByRole('button',{name:'버전 비교',exact:true})).toHaveCount(0)
  await page.getByRole('navigation', { name: '검수 장면 선택' }).getByRole('button',{name:/^월요일/}).click()
  const pinned=page.locator('.tw-pinned'), history=page.locator('.tw-history-list li')
  await expect(history).toHaveCount(3);await expect(pinned).toContainText('최초 생성본')
  const regenerate = page.getByRole('button', { name: '그림 다시 생성', exact: true })
  const sourceRow = page.locator('.tw-regen-row').filter({ has: regenerate })
  async function expectRegenBeside(container: Locator, label: string) {
    await expect(regenerate).toHaveCount(1)
    await expect(regenerate).toBeEnabled()
    await expect(container.getByRole('button', { name: '그림 다시 생성', exact: true })).toBeVisible()
    const title = sourceRow.getByText(label, { exact: true })
    await expect(title).toBeVisible()
    const nameBox = (await title.boundingBox())!, buttonBox = (await regenerate.boundingBox())!
    expect(buttonBox.x).toBeGreaterThanOrEqual(nameBox.x + nameBox.width - 1)
    expect(buttonBox.y).toBeLessThan(nameBox.y + nameBox.height)
    expect(buttonBox.y + buttonBox.height).toBeGreaterThan(nameBox.y)
  }
  await expectRegenBeside(page.locator('.tw-single'), '최초 생성본')
  await page.getByRole('button',{name:'버전 비교',exact:true}).click()
  const leftSelect=page.getByRole('combobox',{name:'왼쪽 비교본',exact:true}), rightSelect=page.getByRole('combobox',{name:'오른쪽 비교본',exact:true})
  const leftCard = page.getByRole('region', { name: '왼쪽 비교본', exact: true })
  const rightCard = page.getByRole('region', { name: '오른쪽 비교본', exact: true })
  const swap = page.getByRole('button', { name: '좌우 바꾸기' })
  await expectRegenBeside(leftCard, '최초 생성본')
  await swap.click()
  await expectRegenBeside(rightCard, '최초 생성본')
  await swap.click()
  const rightSource = page.getByRole('combobox', { name: '오른쪽 생성 출처', exact: true })
  await rightSource.selectOption('ORIGINAL')
  await expect(rightSelect).toBeDisabled()
  await expect(page.getByText('이 출처에서 비교할 다른 영상이 없습니다.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '전체 출처 보기' }).click()
  await expect(rightSource).toHaveValue('ALL')
  await leftSelect.selectOption(ids[1]);await rightSelect.selectOption(ids[2])
  await expectRegenBeside(page.locator('.tw-film-selection'), '최초 생성본')
  await swap.click()
  await expect(leftSelect).toHaveValue(ids[2]);await expect(rightSelect).toHaveValue(ids[1])
  await swap.click()
  await expect(pinned).toContainText('최초 생성본');expect(selections).toBe(0)
  await page.getByRole('button',{name:'오른쪽 영상 이 버전 사용',exact:true}).click()
  await expect(pinned).toContainText('재생성 2차');expect(selections).toBe(1)
  await expectRegenBeside(rightCard, '재생성 2차')
  await page.getByRole('button',{name:'전체 4개 보기',exact:true}).click();await expect(history).toHaveCount(4)
  const first=history.filter({hasText:'최초 생성본'})
  await first.getByRole('button',{name:'최초 생성본 별표'}).click()
  await first.getByRole('button',{name:'최초 생성본 메모 편집',exact:true}).click()
  await page.getByLabel('검수 메모').fill('발자국 윤곽')
  await page.getByRole('button',{name:'메모 저장'}).click()
  await page.getByRole('button',{name:'별표',exact:true}).click()
  await expect(history).toHaveCount(1);await expect(first).toContainText('발자국 윤곽')
  await page.getByLabel('생성 이력 검색').fill('윤곽');await expect(history).toHaveCount(1)
  await page.getByRole('button',{name:'이 요일 미션 보기'}).click()
  const mission = page.getByRole('dialog')
  await mission.getByText('문제 전 대화', { exact: true }).click()
  await expect(mission.getByText('발자국을 확인하자!')).toBeVisible()
  await mission.getByText('문제 마무리 뒤 단서', { exact: true }).click()
  await expect(mission.getByText('커다란 발자국', { exact: true })).toBeVisible()
  await page.getByRole('button',{name:'월요일 장면 보기'}).click()
  await expect(page.locator('.tw-single')).toContainText('재생성 2차')
  await page.getByRole('button',{name:'버전 비교',exact:true}).click()
  await expect(leftSelect).toHaveValue(ids[1]);await expect(rightSelect).toHaveValue(ids[2])
  await page.reload();await expect(pinned).toContainText('재생성 2차')
  await page.getByRole('button',{name:'단일 보기',exact:true}).click()
  await page.getByLabel('생성 이력 검색').fill('2026-11-10');await expect(history).toHaveCount(1)
  await expect(history).toContainText('발자국 윤곽')
  await page.setViewportSize({width:390,height:844})
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  selected = null
  await page.reload()
  const single = page.locator('.tw-single')
  await expect(single.getByText('선택 전 · 재생성 3차', { exact: true })).toBeVisible()
  await expect(sourceRow.getByText('최초 생성본', { exact: true })).toBeVisible()
  await expect(regenerate).toHaveCount(1)
  await expect(regenerate).toBeEnabled()
})

test('#882 학년·생성 주 필터, 편성된 초안의 버림 확인과 읽기 전용 이력',async({page,context})=>{
  const calls=await confirmedResponses(context)
  const plannedWeek='2026-11-30'
  let record={draftId:id,status:'READY',source:'ADMIN',grade:'G4',weekStart:'2026-11-23',plannedWeek:plannedWeek as string|null,
    draft:{theme:{title:'달의 지도',intro:'달빛 숲',days:[]},missions:[{day:'MON',draft:{title:'첫 단서',question:'무엇이 보이나요?'}}]}}
  let expected:unknown
  await context.route('**/api/v1/admin/theme-drafts/review-list?**', route => {
    const { search, searchParams } = new URL(route.request().url())
    calls.push({ path: reviewListPath, method: 'GET', body: null, search })
    const discarded = record.status === 'DISCARDED'
    const row = { ...listRow, source: record.source, status: record.status, stage: discarded ? 'discarded' : 'pair',
      plannedWeek: record.plannedWeek, appliedWeek: record.plannedWeek ?? record.weekStart, comparisonScene: discarded ? null : 'INTRO' }
    const archive = searchParams.get('stage') === 'discarded' || searchParams.get('status') === 'DISCARDED'
    const items = archive === discarded && (!searchParams.has('week') || searchParams.get('week') === row.appliedWeek) ? [row] : []
    return route.fulfill({ json: { items, page: 0, size: 20, totalElements: items.length, weeks: [row.appliedWeek] } })
  })
  await context.route('**/api/v1/admin/theme-drafts/'+id,route=>route.fulfill({json:record}))
  await context.route('**/api/v1/admin/theme-drafts/'+id+'/discard',route=>{
    expected=route.request().postDataJSON()
    record={...record,status:'DISCARDED',plannedWeek:null}
    return route.fulfill({json:record})
  })
  await page.goto('/admin/theme-drafts?grade=G4&weekStart=2026-11-23&status=READY&comparisonPending=true')
  await expect(page.getByLabel('학년 선택')).toHaveValue('G4')
  await expect(page.getByLabel('검수 상태 선택')).toHaveValue('pair')
  await expect.poll(()=>calls.some(c=>c.search.includes('comparisonPending=true')&&c.search.includes('weekStart=2026-11-23')&&c.search.includes('grade=G4'))).toBeTruthy()
  await page.getByLabel('적용 주 선택').selectOption('2026-11-30')
  await expect(page.getByLabel('적용 주 선택')).toHaveValue('2026-11-30')
  await expect.poll(()=>calls.some(c=>c.path===reviewListPath && new URLSearchParams(c.search).get('week')==='2026-11-30')).toBeTruthy()
  await page.getByRole('link',{name:'달의 지도 상세 열기'}).click()
  await page.getByRole('button',{name:'초안 버리기',exact:true}).click()
  await expect(page.getByRole('dialog')).toContainText(plannedWeek)
  await page.getByRole('button',{name:'취소',exact:true}).click()
  expect(expected).toBeUndefined()
  await page.getByRole('button',{name:'초안 버리기',exact:true}).click()
  await page.getByRole('dialog').getByRole('button',{name:'초안 버리기',exact:true}).click()
  await expect(page.getByText('버린 초안입니다.',{exact:false})).toBeVisible()
  expect(expected).toEqual({expectedPlannedWeek:plannedWeek})
  await page.reload()
  await expect(page.getByRole('button',{name:/^(초안 채택|이 주차로 채택)$/})).toHaveCount(0)
  await expect(page.locator('.rv-title-line').getByRole('button',{name:'이 초안으로 새 초안 생성'})).toBeVisible()
  await page.getByRole('button',{name:'버림 이력 보기',exact:true}).click()
  await expect(page.getByRole('region', { name: '버림 이력' })).toBeVisible()
  await expect(page.getByLabel('검수 상태 선택')).toHaveValue('discarded')
  await expect(page.getByLabel('학년 선택')).toHaveValue('')
  await expect(page.getByLabel('생성 기준 주 선택')).toHaveValue('')
  await expect(page.getByRole('region', { name: '버림 이력' }).getByRole('link', { name: '달의 지도 상세 열기' })).toBeVisible()
})
