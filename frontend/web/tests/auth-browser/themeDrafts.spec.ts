import { test, expect } from '@playwright/test'
import type { BrowserContext } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'

const id = '00000000-0000-4000-8000-000000000441'
const themeId = '00000000-0000-4000-8000-000000000395'
const days = ['MON', 'TUE', 'WED', 'THU', 'FRI']

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
    if (path === '/admin/theme-drafts') {
      if (req.method() === 'POST' && requestFails) return json({ status: 503, code: 'LEARNING_UNAVAILABLE', title: '요청 결과를 확인하지 못했습니다.' }, 503)
      return json(req.method() === 'GET' ? { items: [{ draftId: id, status: 'GENERATING' }] } : { draftId: id, status: 'GENERATING' }, req.method() === 'POST' ? 202 : 200)
    }
    if (path === '/admin/theme-drafts/' + id) return json({ draftId: id, status: 'GENERATING' })
    if (path === '/admin/weekly-themes') return json({ items: [] })
    if (path === '/admin/weekly-themes/' + themeId) return json({ themeId, title: '기존 테마', intro: '기존 도입 이야기', grade: 'G3', weekStart: '2026-11-16', status: 'DRAFT', updatedAt: '2026-11-10T00:00:00Z', days: days.map((day, n) => ({ day, missionId: `00000000-0000-4000-8000-00000000000${n + 1}` })) })
    if (path === '/admin/missions') return json({ items: [] })
    if (path === '/admin/achievement-standards') return json({ items: [{ code: '4과03-01', subject: '과학', gradeBand: '초3~4', area: '생명', statement: '합성 성취기준 표 행', levelScale: 3, levels: null, curriculumVersion: '2022', source: 'HTTP 검사 자료', note: null }], page: 0, size: 10, totalElements: 1 })
    return json({ code: 'NOT_FOUND' }, 404)
  })
  return calls
}

test('테마 요청·생성 중 상태·필터 연결: 생성 중에는 채택·버리기·다시 생성을 보이지 않는다', async ({ page, context }) => {
  const calls = await confirmedResponses(context)
  await page.goto('/admin/theme-drafts')
  await expect(page.getByRole('heading', { name: '테마 초안 요청·상태', exact: true })).toBeVisible()
  await page.getByLabel('생성 학년').selectOption('G6')
  await page.getByLabel('생성 적용 주').fill('2026-11-16')
  await page.getByLabel('테마 주제 키워드').fill('도서관')
  await page.getByRole('button', { name: '테마 초안 생성 요청', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '생성 요청을 접수했습니다.' })).toBeVisible()
  expect(calls.filter(c => c.method === 'POST' && c.path === '/admin/theme-drafts')).toEqual([expect.objectContaining({ path: '/admin/theme-drafts', body: { grade: 'G6', weekStart: '2026-11-16', topic: '도서관' } })])
  await expect(page.getByRole('status').filter({ hasText: '생성 중입니다' })).toBeVisible()
  await expect(page.getByRole('button', { name: /채택|버리기|다시 생성/ })).toHaveCount(0)
  await page.getByLabel('테마 초안 출처').selectOption('AUTO')
  await expect.poll(() => calls.some(c => c.path === '/admin/theme-drafts' && c.search.includes('source=AUTO'))).toBe(true)
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
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

test('완료 초안 상세: 이야기·요일 문제·실패를 보이고 채택하면 core 채택 경로를 한 번 불러 만든 테마 편집으로 간다', async ({ page, context }) => {
  const calls = await confirmedResponses(context)
  const ready = {
    draftId: id, status: 'READY', source: 'ADMIN', grade: 'G3', weekStart: '2026-11-16', attempts: 2, maxAttempts: 3,
    input: { topic: '도서관', missions: [{ thinkingType: 'ANALYZE', inputType: 'NARRATIVE', standardCodes: ['4과03-01'] }] },
    checkResults: [{ attempt: 1, failures: [{ stage: 'LEARNING', reasons: ['WED QUESTION_LENGTH 합성 사유'] }] }],
    draft: { theme: { title: '합성 테마', world: '', characters: [], styleNote: '', outfit: '', intro: '합성 시작 이야기', outro: '합성 종료 이야기',
      bigQuestion: '합성 큰 질문', candidates: ['가', '나'], answer: '가', days: [{ day: 'MON', thinkingType: 'ANALYZE', place: '', sceneNote: '', clue: '합성 단서', rulesOut: ['나'] }] },
    missions: [{ day: 'MON', thinkingType: 'ANALYZE', draft: { title: '합성 월요일 문제', question: '합성 질문', guide: null } }],
    dialogues: [], warnings: [] },
    scenes: [], failureCode: null, versions: { prompt: 'p', model: 'm' }, themeId: null, requestedBy: null, createdAt: '2026-11-12T00:00:00Z', updatedAt: '2026-11-12T00:00:00Z',
  }
  await context.route('**/api/v1/admin/theme-drafts/' + id, route => route.fulfill({ json: ready }))
  await context.route('**/api/v1/admin/theme-drafts/' + id + '/adopt', route => {
    calls.push({ path: '/admin/theme-drafts/' + id + '/adopt', method: route.request().method(), body: route.request().postDataJSON(), search: '' })
    return route.fulfill({ status: 201, json: { themeId, grade: 'G3', weekStart: '2026-11-16', title: '합성 테마', intro: '', days: [], status: 'DRAFT', updatedAt: '2026-11-12T00:00:00Z' } })
  })
  await page.goto('/admin/theme-drafts?draftId=' + id)
  await expect(page.getByRole('heading', { name: '초안 상세 · 합성 테마' })).toBeVisible()
  await expect(page.getByText('합성 종료 이야기')).toBeVisible()
  await expect(page.getByText('WED QUESTION_LENGTH 합성 사유', { exact: false })).toBeVisible()
  await expect(page.getByRole('region', { name: '월요일 문제' }).getByText('합성 월요일 문제')).toBeVisible()
  await page.getByRole('button', { name: '채택해서 테마 만들기', exact: true }).click()
  await page.getByRole('alertdialog').getByRole('button', { name: '채택', exact: true }).click()
  await expect(page).toHaveURL(new RegExp('/admin/themes\\?themeId=' + themeId))
  expect(calls.filter(c => c.path.endsWith('/adopt'))).toEqual([expect.objectContaining({ method: 'POST', body: {} })])
})

test('유형별 선택은 기존 성취기준 표를 사용하고 요청에 지정한 필드만 보낸다', async ({ page, context }) => {
  const calls = await confirmedResponses(context)
  await page.goto('/admin/theme-drafts')
  await page.getByLabel('생성 적용 주').fill('2026-11-16')
  await page.getByText('생각 유형별 성취기준·입력 방식 직접 지정', { exact: true }).click()
  await page.getByRole('checkbox', { name: '분석하기 직접 지정', exact: true }).check()
  await page.getByLabel('분석하기 입력 방식', { exact: true }).selectOption('NARRATIVE')
  await page.getByRole('button', { name: '4과03-01 고르기', exact: true }).click()
  await page.getByRole('button', { name: '테마 초안 생성 요청', exact: true }).click()
  await expect.poll(() => calls.filter(c => c.method === 'POST' && c.path === '/admin/theme-drafts').length).toBe(1)
  expect(calls.find(c => c.method === 'POST' && c.path === '/admin/theme-drafts')?.body).toEqual({ grade: 'G3', weekStart: '2026-11-16', missions: [{ thinkingType: 'ANALYZE', standardCodes: ['4과03-01'], inputType: 'NARRATIVE' }] })
})

test('접수 결과가 불명확한 503은 성공 처리와 자동 재요청 없이 목록 확인을 안내한다', async ({ page, context }) => {
  const calls = await confirmedResponses(context, true, true)
  await page.goto('/admin/theme-drafts')
  await page.getByLabel('생성 적용 주').fill('2026-11-16')
  await page.getByRole('button', { name: '테마 초안 생성 요청', exact: true }).click()
  await expect(page.getByRole('note').filter({ hasText: '새로 요청하기 전에 목록을 먼저 확인' })).toBeVisible()
  expect(calls.filter(c => c.method === 'POST' && c.path === '/admin/theme-drafts')).toHaveLength(1)
  await expect(page.getByText('생성 요청을 접수했습니다.', { exact: false })).toHaveCount(0)
})

test('CONTENT 권한 없이 메뉴/요청 화면에 접근해도 테마 API를 호출하지 않는다', async ({ page, context }) => {
  const calls = await confirmedResponses(context, false)
  await page.goto('/admin/theme-drafts')
  await expect(page.getByRole('heading', { name: '접근 권한 확인', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: '테마 초안', exact: true })).toHaveCount(0)
  expect(calls.some(c => c.path.startsWith('/admin/theme-drafts'))).toBe(false)
})

test('기존 테마 식별자 링크로 편집기를 열고 연결된 미션 5개의 편집 링크를 보존한다', async ({ page, context }) => {
  await confirmedResponses(context)
  await page.goto('/admin/themes?themeId=' + themeId)
  await expect(page.getByRole('textbox', { name: '테마 제목', exact: true })).toHaveValue('기존 테마')
  await expect(page.getByRole('link', { name: /요일 미션 편집$/ })).toHaveCount(5)
  await expect(page.getByLabel('월요일 미션', { exact: true })).toHaveValue('00000000-0000-4000-8000-000000000001')
  await page.getByRole('button', { name: '닫기', exact: true }).click()
  await expect(page.getByRole('textbox', { name: '테마 제목', exact: true })).toHaveCount(0)
  expect(new URL(page.url()).searchParams.has('themeId')).toBe(false)
})

test('학년 네 개로 요청하고 논술 선택은 초5·초6에서만 제공하며 성취기준은 학년군으로 조회한다', async ({ page, context }) => {
  const calls = await confirmedResponses(context)
  await page.goto('/admin/theme-drafts')
  const grade = page.getByLabel('생성 학년', { exact: true })
  await expect(grade.locator('option')).toHaveText(['초3', '초4', '초5', '초6'])
  await page.getByLabel('생성 적용 주').fill('2026-11-16')
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
    await page.getByRole('button', { name: '테마 초안 생성 요청', exact: true }).click()
    await expect.poll(() => calls.filter(c => c.path === '/admin/theme-drafts' && c.method === 'POST').at(-1)?.body).toEqual({ grade: value, weekStart: '2026-11-16' })
    await expect(page.getByRole('button', { name: '테마 초안 생성 요청', exact: true })).toBeEnabled()
    await checkbox.check()
  }
  const standardCalls = calls.filter(c => c.path === '/admin/achievement-standards')
  expect(standardCalls.some(c => new URLSearchParams(c.search).get('gradeBand') === '초3~4')).toBe(true)
  expect(standardCalls.some(c => new URLSearchParams(c.search).get('gradeBand') === '초5~6')).toBe(true)
})

test('테마 목록 필터·기존 테마 편집도 학년 하나를 전송한다', async ({ page, context }) => {
  const calls = await confirmedResponses(context)
  await page.goto('/admin/themes?themeId=' + themeId)
  const filter = page.getByLabel('테마 학년', { exact: true })
  await expect(filter.locator('option')).toHaveText(['전체', '초3', '초4', '초5', '초6'])
  await filter.selectOption('G4')
  await expect.poll(() => calls.some(c => c.path === '/admin/weekly-themes' && new URLSearchParams(c.search).get('grade') === 'G4')).toBe(true)
  expect(calls.filter(c => c.path === '/admin/weekly-themes').every(c => !new URLSearchParams(c.search).has('gradeBand'))).toBe(true)
  await expect(page.getByLabel('학년', { exact: true })).toHaveValue('G3')
  await page.getByLabel('학년', { exact: true }).selectOption('G4')
  await page.getByRole('button', { name: '테마 저장', exact: true }).click()
  await expect.poll(() => calls.find(c => c.path === '/admin/weekly-themes/' + themeId && c.method === 'PUT')?.body).toEqual(expect.objectContaining({ grade: 'G4' }))
  expect(calls.find(c => c.path === '/admin/weekly-themes/' + themeId && c.method === 'PUT')?.body).not.toHaveProperty('gradeBand')
})
