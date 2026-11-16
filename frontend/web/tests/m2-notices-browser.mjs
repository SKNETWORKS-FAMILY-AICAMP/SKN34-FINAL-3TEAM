// #549 실제 빌드 화면의 글 정리 안내와 숫자 비노출 검증. 서버 응답만 합성 대역이다.
import { createRequire } from 'node:module'
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { resolve, extname, sep } from 'node:path'
import assert from 'node:assert/strict'

const require = createRequire(import.meta.url)
const { chromium } = require('playwright')
const root = resolve('dist')
const server = createServer(async (req, res) => {
  const path = resolve(root, '.' + decodeURIComponent(new URL(req.url, 'http://localhost').pathname))
  if (path !== root && !path.startsWith(root + sep)) return res.writeHead(403).end()
  try {
    let data, ext
    try { data = await readFile(path); ext = extname(path) }
    catch { data = await readFile(resolve(root, 'index.html')); ext = '.html' }
    res.setHeader('Content-Type', { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' }[ext] ?? 'application/octet-stream')
    res.end(data)
  } catch { res.writeHead(500).end() }
})
await new Promise((done) => server.listen(0, '127.0.0.1', done))
const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH })
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  const child = { id: 'student-549', nickname: '합성 학생', grade: 5, birthYear: 2015 }
  const mission = { id: 'mission-549', title: '우리 동네 시설', subject: '국어', grade: 5, gradeMax: 6, thinkingType: 'ARGUE', inputType: 'NARRATIVE', question: '동네에 필요한 시설은 무엇인가요?', hint: '', choices: [], categories: [], inputTemplate: [], sceneUri: '', staticSceneUri: '' }
  const feedback = { status: 'DONE', judgment: { judgmentId: 'j-549', result: 'CORRECT', trial: true, elements: [], heldReason: null, m2Notices: ['정리 후 남은 답변이 없어요'], modelScores: { m2: { scores: { hol: 999 } } } }, followup: null, nextActions: ['FINISH'] }
  const attempt = { attemptId: 'attempt-549', studentId: child.id, mission, status: 'IN_PROGRESS', helped: false, answers: [{ answerId: 'answer-549', version: 1, submittedAt: new Date().toISOString(), inputType: 'NARRATIVE', text: '몰라요', feedback }] }
  let role = 'STUDENT'
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const reply = (value) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(value) })
    if (path.endsWith('/auth/refresh')) return reply({ accessToken: 'test', role: 'PARENT' })
    if (path.endsWith('/me')) return reply({ role, child: role === 'STUDENT' ? child : undefined, nextAction: 'READY', startPath: role === 'PARENT' ? '/parent/journal' : '/student/home' })
    if (path.endsWith('/children')) return reply({ items: [child] })
    if (path.endsWith('/auth/student-sessions')) { role = 'STUDENT'; return reply({ role, accessToken: 'test', child }) }
    if (path.endsWith('/students/me/home')) return reply({ student: child, state: 'OK', missions: [mission], resume: attempt, period: { from: '2026-11-09', to: '2026-11-15' } })
    if (path.endsWith('/students/me/look')) return reply({ theme: 'lake', companion: 'mungchi', updatedAt: null })
    if (path.endsWith('/attempts/attempt-549')) return reply(attempt)
    return reply({ items: [], page: 0, size: 20, totalElements: 0 })
  })
  await page.goto(`http://127.0.0.1:${server.address().port}/oauth/complete`)
  await page.getByRole('button', { name: '이어서 작성하기' }).waitFor().catch(async (e) => {
    console.error(await page.locator('body').innerText())
    throw e
  })
  await page.getByRole('button', { name: '이어서 작성하기' }).click()
  for (const width of [1440, 1024, 768]) {
    await page.setViewportSize({ width, height: 900 })
    await page.getByText('정리 후 남은 답변이 없어요', { exact: true }).waitFor()
    assert.equal((await page.locator('body').innerText()).includes('999'), false)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false)
  }
  assert.deepEqual(errors, [])
  console.log('PASS: 3 widths, M2 notice visible, numeric scores hidden, no page errors')
} finally {
  await browser.close()
  await new Promise((done) => server.close(done))
}
