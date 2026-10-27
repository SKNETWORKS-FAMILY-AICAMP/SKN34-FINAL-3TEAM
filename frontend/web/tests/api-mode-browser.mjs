import { createRequire } from 'node:module'
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { extname, resolve, sep } from 'node:path'
import assert from 'node:assert/strict'
const require = createRequire(process.env.PLAYWRIGHT_PACKAGE ?? import.meta.url)
const { chromium } = require('playwright')
const root = resolve('dist')
const server = createServer(async (request, response) => {
  try {
    const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname)
    const target = resolve(root, '.' + pathname)
    if (target !== root && !target.startsWith(root + sep)) { response.writeHead(403).end(); return }
    let data, extension
    try { data = await readFile(target); extension = extname(target) }
    catch { data = await readFile(resolve(root, 'index.html')); extension = '.html' }
    response.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' })[extension] ?? 'application/octet-stream')
    response.end(data)
  } catch { response.writeHead(500).end() }
})
await new Promise((done) => server.listen(0, '127.0.0.1', done))
const origin = `http://127.0.0.1:${server.address().port}`
let browser
try {
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || undefined })
  const context = await browser.newContext()
  let loggedIn = false, role = 'PARENT', activeRefreshes = 0, maxRefreshes = 0, onboarded = false, refreshes = 0
  const errors = [], paths = []
  context.on('page', (page) => page.on('pageerror', (error) => errors.push(error.message)))
  const child = { id: 'fixture-child', nickname: '가상 학생', grade: 3, birthYear: 2017 }
  await context.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    paths.push(path)
    const reply = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (path.endsWith('/auth/refresh')) {
      refreshes++; activeRefreshes++; maxRefreshes = Math.max(maxRefreshes, activeRefreshes)
      await new Promise((done) => setTimeout(done, 35))
      activeRefreshes--
      assert.equal(route.request().headers()['x-requested-with'], 'XMLHttpRequest')
      return loggedIn && role !== 'STUDENT' ? reply({ accessToken: `fixture-${role}`, role }) : reply({ code: 'UNAUTHENTICATED', status: 401, title: '로그인 필요' }, 401)
    }
    if (path.endsWith('/me')) return reply({ userId: 'fixture-parent', role, child: role === 'STUDENT' ? child : undefined,
      permissions: [], nextAction: role === 'PARENT' && !onboarded ? 'CONSENT_REQUIRED' : 'READY', startPath: role === 'PARENT' ? (onboarded ? '/parent/journal' : '/parent/onboarding') : '/student/home' })
    if (path.endsWith('/auth/student-sessions')) {
      loggedIn = false; role = 'STUDENT'
      return reply({ accessToken: 'fixture-STUDENT', role, child, nextAction: 'READY', startPath: '/student/home' })
    }
    if (path.endsWith('/children')) return reply({ items: [{ ...child, childId: child.id, plan: 'FREE' }], page: 0, size: 20, totalElements: 1 })
    if (path.endsWith('/students/me/home')) return reply({ student: child, state: 'NO_RECORD', period: { from: '2026-10-21', to: '2026-10-27' }, resume: null, missions: [] })
    if (path.endsWith('/missions') || path.endsWith('/attempts')) return reply({ items: [], page: 0, size: 20, totalElements: 0 })
    return reply({ status: 404, code: 'NOT_FOUND', title: '미구현 API 대역' }, 404)
  })
  const a = await context.newPage(), b = await context.newPage()
  await Promise.all([a.goto(origin + '/login'), b.goto(origin + '/signup')])
  await a.getByRole('link', { name: 'Google 계정으로 계속하기' }).waitFor()
  await b.getByRole('link', { name: 'Google 계정으로 계속하기' }).waitFor()
  assert.equal(await a.getByLabel('비밀번호', { exact: true }).count(), 0)
  assert.equal(await b.getByLabel('가입 비밀번호').count(), 0)
  assert.equal(await a.getByRole('link', { name: 'Google 계정으로 계속하기' }).getAttribute('href'), '/api/v1/auth/google/authorize')
  loggedIn = true
  await Promise.all([a.goto(origin + '/oauth/complete'), b.goto(origin + '/oauth/complete')])
  await Promise.all([a.waitForURL('**/parent/onboarding'), b.waitForURL('**/parent/onboarding')])
  await a.getByRole('heading', { name: '이용 안내·필수 동의' }).waitFor()
  onboarded = true
  await Promise.all([a.goto(origin + '/parent/journal'), b.goto(origin + '/parent/journal')])
  await a.getByRole('button', { name: '이 자녀로 학습 시작' }).waitFor()
  await b.getByRole('button', { name: '이 자녀로 학습 시작' }).waitFor()
  const beforeStudent = refreshes
  await a.getByRole('button', { name: '이 자녀로 학습 시작' }).click()
  await Promise.all([a.waitForURL('**/student/home'), b.waitForURL('**/student/login')])
  await b.getByRole('heading', { name: '학생 로그인', exact: true }).waitFor()
  assert.equal(refreshes, beforeStudent, 'Student transition must not refresh into parent credentials')
  await a.reload()
  await a.waitForURL('**/student/login')
  assert.equal(refreshes, beforeStudent, 'Student reload must require entry without refresh')
  assert.equal(maxRefreshes, 1, 'Parent cookie rotation must serialize across tabs')
  assert.equal(await a.locator('[data-role-layout]').count(), 0)
  assert.equal(await a.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).length), 0)
  const stored = await a.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))
  assert.equal(stored.includes('fixture-STUDENT') || stored.includes('fixture-PARENT'), false)
  assert.deepEqual(errors, [])
  console.log(JSON.stringify({ passed: true, maxConcurrentRefreshes: maxRefreshes, paths: [...new Set(paths)], pageErrors: errors,
    realBackendIntegration: false, note: 'Production build + two real Chrome tabs; Google/API are fixtures; students never refresh.' }, null, 2))
} finally { if (browser) await browser.close(); await new Promise((done) => server.close(done)) }
