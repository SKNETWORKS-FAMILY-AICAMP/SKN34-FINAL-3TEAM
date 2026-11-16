import { test, expect } from '@playwright/test'
import type { BrowserContext, Page } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import type { Permission } from '../../src/domain/admin/operations.ts'

const counts = [
  { status: 'DRAFT', count: 23 }, { status: 'REVIEW_REQUIRED', count: 5 },
  { status: 'PUBLISHED', count: 7 }, { status: 'UNPUBLISHED', count: 0 },
]
async function adminServer(context: BrowserContext, permissions: Permission[] = ['CONTENT', 'SERVICE_OPS']) {
  const controls = { counts: counts as unknown, missionsFail: false, overviewFails: false, waitForMissions: null as Promise<void> | null }
  const calls: { path: string; search: URLSearchParams }[] = []
  await context.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
  await context.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname.replace('/api/v1', '')
    calls.push({ path, search: url.searchParams })
    const json = (body: unknown, status = 200) => route.fulfill({ status, json: body })
    if (path === '/auth/refresh') return json({ role: 'ADMIN', accessToken: 'synthetic-admin', expiresIn: 900 })
    if (path === '/me') return json({ role: 'ADMIN', userId: 'synthetic-admin', name: '합성 운영자', email: 'admin@example.test', permissions, nextAction: 'READY', startPath: '/admin/home' })
    if (path === '/notifications') return json({ items: [], page: 0, size: 20, hasNext: false })
    if (path === '/notifications/stream') return route.abort('failed')
    if (path === '/admin/overview') return controls.overviewFails ? json({ status: 503, code: 'UNAVAILABLE', title: '운영 집계를 불러오지 못했습니다.' }, 503) : json({
      period: { from: url.searchParams.get('from'), to: url.searchParams.get('to') }, inclusionRule: '합성 운영 집계',
      learning: { attempts: 6, completedAttempts: 3, students: 2, inclusionRule: '합성 학습 집계' },
      jobCounts: [{ type: 'CONVERSATION', status: 'COMPLETED', count: 3 }, { type: 'REPORT', status: 'FAILED', count: 2 }, { type: 'NOTIFICATION', status: 'QUEUED', count: 1 }],
    })
    if (path === '/admin/missions') {
      if (controls.waitForMissions) await controls.waitForMissions
      if (controls.missionsFail) return json({ status: 503, code: 'LEARNING_UNAVAILABLE', title: '미션 현황을 불러오지 못했습니다.' }, 503)
      const status = url.searchParams.get('status') ?? 'DRAFT'
      const current = Array.isArray(controls.counts) ? controls.counts as typeof counts : counts
      const total = url.searchParams.has('status') ? current.find(c => c.status === status)?.count ?? 0 : current.reduce((sum, c) => sum + c.count, 0)
      const mission = { missionId: 'mission-1', status, demoOnly: false, currentVersion: 1, currentRubricVersion: null, publishedVersion: null, publishedRubricVersion: null, rubrics: [], reviews: [],
        versions: [{ version: 1, title: '합성 검증 미션', subject: '국어', gradeMin: 3, gradeMax: 4, thinkingType: 'ANALYZE', inputType: 'NARRATIVE',
          question: '까닭을 말해 주세요.', guide: null, sceneUri: null, staticSceneUri: null, achievementStandards: [], createdAt: '2026-11-10T00:00:00Z' }] }
      return json({ items: total ? [mission] : [], page: 0, size: Number(url.searchParams.get('size') ?? 20), totalElements: total, counts: controls.counts })
    }
    if (path === '/admin/jobs') return json({ items: [], page: 0, size: 20, totalElements: 0 })
    return json({ status: 404, code: 'NOT_FOUND' }, 404)
  })
  return { controls, calls }
}

async function capture(page: Page) {
  const out = '.taste-skill/admin-overview'
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
    await writeFile(`${out}/screen-${width}.html`, html)
    await page.screenshot({ path: `${out}/screen-${width}.png`, fullPage: true })
  }
}

test('#460: 첫 페이지 미션 수 대신 서버의 전체 집계를 표시하고 해당 상태로 이동한다', async ({ page, context }) => {
  const { calls } = await adminServer(context)
  await page.goto('/admin/home?from=2026-11-01&to=2026-11-09')
  const summary = page.getByRole('region', { name: '미션 공개 현황', exact: true })
  for (const [label, status, count] of [['작성 중', 'DRAFT', 23], ['검토 필요', 'REVIEW_REQUIRED', 5], ['공개', 'PUBLISHED', 7], ['비공개', 'UNPUBLISHED', 0]] as const) {
    await expect(summary.getByRole('link', { name: `${label} ${count}개`, exact: true })).toHaveAttribute('href', `/admin/missions?status=${status}`)
  }
  const request = calls.find(c => c.path === '/admin/missions')!
  expect(Object.fromEntries(request.search)).toEqual({ page: '0', size: '1' })
  await expect(page.getByText('미션 공개 현황은 관리자 미션 공급자 연결 후 조회할 수 있습니다.')).toHaveCount(0)
  await capture(page)
  await summary.getByRole('link', { name: '공개 7개', exact: true }).click()
  await expect(page.getByLabel('미션 운영 상태', { exact: true })).toHaveValue('PUBLISHED')
  await expect.poll(() => calls.some(c => c.path === '/admin/missions' && c.search.get('status') === 'PUBLISHED')).toBe(true)
})

test('#460: 작업 종류는 한글로 보이고 이동·필터의 코드는 유지한다', async ({ page, context }) => {
  await adminServer(context)
  await page.goto('/admin/home?from=2026-11-01&to=2026-11-09')
  await expect(page.getByRole('link', { name: 'AI 대화 · 완료 3건', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: '알림 · 대기 1건', exact: true })).toBeVisible()
  await page.getByRole('link', { name: '리포트 · 실패 2건', exact: true }).click()
  expect(new URL(page.url()).searchParams.get('type')).toBe('REPORT')
  await expect(page.getByLabel('작업 유형', { exact: true })).toHaveValue('REPORT')
  await expect(page.getByLabel('작업 유형', { exact: true }).locator('option:checked')).toHaveText('리포트')
})

test('#460: CONTENT 권한이 없으면 미션 현황을 표시하거나 조회하지 않는다', async ({ page, context }) => {
  const { calls } = await adminServer(context, ['SERVICE_OPS'])
  await page.goto('/admin/home')
  await expect(page.getByRole('heading', { name: '처리 현황', exact: true })).toBeVisible()
  await expect(page.getByRole('region', { name: '미션 공개 현황', exact: true })).toHaveCount(0)
  expect(calls.some(c => c.path === '/admin/missions')).toBe(false)
})

test('#460: 미션 조회 실패를 0개로 바꾸지 않고 독립적으로 재시도한다', async ({ page, context }) => {
  const { controls } = await adminServer(context)
  controls.missionsFail = true
  await page.goto('/admin/home')
  const summary = page.getByRole('region', { name: '미션 공개 현황', exact: true })
  await expect(summary.getByText('미션 현황을 불러오지 못했습니다.', { exact: true })).toBeVisible()
  await expect(summary.getByRole('link')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: '학습 완료', exact: true })).toBeVisible()
  controls.missionsFail = false
  await summary.getByRole('button', { name: '다시 시도', exact: true }).click()
  await expect(summary.getByRole('link', { name: '작성 중 23개', exact: true })).toBeVisible()
})

test('#460: 집계 응답이 빠지면 0개 링크를 만들지 않는다', async ({ page, context }) => {
  const { controls } = await adminServer(context)
  controls.counts = undefined
  await page.goto('/admin/home')
  const summary = page.getByRole('region', { name: '미션 공개 현황', exact: true })
  await expect(summary.getByRole('alert').locator('strong')).toHaveText('미션 공개 현황의 집계를 확인하지 못했습니다.')
  await expect(summary.getByRole('link')).toHaveCount(0)
})

test('#460: 네 상태의 실제 0개는 정상 값으로 표시한다', async ({ page, context }) => {
  const { controls } = await adminServer(context)
  controls.counts = counts.map(c => ({ ...c, count: 0 }))
  await page.goto('/admin/home')
  const summary = page.getByRole('region', { name: '미션 공개 현황', exact: true })
  await expect(summary.getByRole('link')).toHaveCount(4)
  await expect(summary.getByText('0개', { exact: true })).toHaveCount(4)
  await expect(summary.getByRole('alert')).toHaveCount(0)
})

test('#460: 운영 집계가 실패해도 현재 미션 집계는 볼 수 있다', async ({ page, context }) => {
  const { controls } = await adminServer(context)
  controls.overviewFails = true
  await page.goto('/admin/home')
  await expect(page.getByText('운영 집계를 불러오지 못했습니다.', { exact: true })).toBeVisible()
  await expect(page.getByRole('region', { name: '미션 공개 현황', exact: true }).getByRole('link', { name: '작성 중 23개', exact: true })).toBeVisible()
})

test('#460: 조회 중에는 임시 0개를 표시하지 않는다', async ({ page, context }) => {
  const { controls } = await adminServer(context)
  let release!: () => void
  controls.waitForMissions = new Promise<void>(resolve => { release = resolve })
  await page.goto('/admin/home')
  const summary = page.getByRole('region', { name: '미션 공개 현황', exact: true })
  await expect(summary.getByRole('status')).toHaveText('불러오고 있습니다.')
  await expect(summary.getByRole('link')).toHaveCount(0)
  release()
  await expect(summary.getByRole('link', { name: '작성 중 23개', exact: true })).toBeVisible()
})
