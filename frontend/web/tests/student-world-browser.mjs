// 학생 화면 테마(생각 지도·꾸미기·미션 단계) 브라우저 회귀. DEV 서버 + VITE_API_MOCK=true 필요.
// 환경 변수: PLAYWRIGHT_PACKAGE, CHROME_PATH, DEMO_URL, (선택) QA_OUTPUT_DIR, QA_FILTER
import { createRequire } from 'node:module'
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'
const require = createRequire(process.env.PLAYWRIGHT_PACKAGE ?? import.meta.url)
const { chromium } = require('playwright')
const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || undefined })
const base = process.env.DEMO_URL ?? 'http://127.0.0.1:5175',
  out = process.env.QA_OUTPUT_DIR
if (out) await mkdir(out, { recursive: true })
const checked = [],
  errors = []
async function check(name, run, options = {}) {
  if (process.env.QA_FILTER && !name.includes(process.env.QA_FILTER)) return
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, ...options })
  await context.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, (route) => route.abort())
  const p = await context.newPage()
  p.setDefaultTimeout(12000)
  p.on('pageerror', (e) => errors.push(name + ': ' + e.message))
  try {
    await run(p)
    checked.push(name)
    if (out) await p.screenshot({ path: path.join(out, `world-${checked.length}.jpg`), type: 'jpeg', fullPage: true })
    console.log('PASS ' + name)
  } catch (e) {
    if (out) await p.screenshot({ path: path.join(out, `failed-world-${checked.length}.jpg`), type: 'jpeg' })
    console.error((await p.locator('body').innerText()).slice(-3000))
    throw e
  } finally {
    await context.close()
  }
}
async function student(p) {
  await p.goto(base + '/login', { waitUntil: 'domcontentloaded' })
  await p.getByRole('button', { name: '시연 계정으로 로그인' }).click()
  await p.waitForURL(/\/parent\/journal/)
  await p.getByRole('button', { name: '이 자녀로 학습 시작' }).click()
  await p.waitForURL('**/student/home')
  await p.getByRole('heading', { name: '생각 지도', exact: true }).waitFor()
}
const theme = (p) => p.locator('.st-world').getAttribute('data-theme')

try {
  await check('생각 지도: 다섯 곳·오늘 여기·곳을 누르면 그 유형 미션만', async (p) => {
    await student(p)
    const places = p.locator('.st-islands > li')
    assert.equal(await places.count(), 5)
    assert.equal(await p.locator('.st-island[data-today]').count(), 1)
    await p.getByRole('button', { name: /^분석하기/ }).click()
    await p.waitForURL(/\/student\/missions\?type=ANALYZE/)
    assert.equal(await p.getByRole('button', { name: '분석하기', exact: true }).getAttribute('aria-pressed'), 'true')
    const kinds = await p.locator('.st-card .st-kicker').allInnerTexts()
    assert.ok(kinds.length > 0 && kinds.every((k) => k.includes('분석하기')), kinds.join('/'))
    await p.getByRole('button', { name: '전체', exact: true }).click()
    await p.waitForURL(/\/student\/missions$/)
    await p.waitForFunction((n) => document.querySelectorAll('.st-card').length > n, kinds.length)
  })

  await check('꾸미기: 첫 화면에서 열고, 바꾸면 바로 반영되고 새로고침 뒤에도 유지', async (p) => {
    await student(p)
    assert.equal(await theme(p), 'lake')
    assert.equal(await p.getByRole('navigation', { name: '학생 메뉴' }).getByRole('button', { name: '꾸미기' }).count(), 0)
    await p.getByRole('button', { name: '꾸미기', exact: true }).click()
    await p.getByRole('dialog', { name: '내 생각 지도 꾸미기' }).waitFor()
    const saved = p.waitForResponse((r) => r.url().endsWith('/students/me/preferences') && r.request().method() === 'PUT')
    await p.getByRole('button', { name: /^숲/ }).click()
    assert.deepEqual((await saved).request().postDataJSON(), { theme: 'forest', companion: 'mungchi' })
    assert.equal(await theme(p), 'forest')
    await p.getByRole('button', { name: /^토리/ }).click()
    await p.getByText('골랐어요. 다른 기기에서도 그대로 보여요.').waitFor()
    await p.getByRole('button', { name: '다 골랐어요' }).click()
    await p.getByRole('dialog').waitFor({ state: 'detached' })
    await p.getByText('나는 토리!', { exact: false }).waitFor()
    await p.getByText('서윤의 생각 숲', { exact: false }).waitFor()
    await p.reload({ waitUntil: 'domcontentloaded' })
    await p.getByRole('heading', { name: '생각 지도', exact: true }).waitFor()
    assert.equal(await theme(p), 'forest')
  })

  await check('미션 단계: 내 생각 쓰기 → 한 걸음 더, 질문은 캐릭터 말풍선', async (p) => {
    await student(p)
    await p.getByRole('button', { name: '미션 고르기', exact: true }).click()
    await p
      .getByRole('article')
      .filter({ has: p.getByRole('heading', { name: '도서관에 만화책을 더 둘까요?', exact: true }) })
      .getByRole('button', { name: '미션 열기' })
      .click()
    await p.getByRole('button', { name: '작성하기 · 진행 중이면 이어서' }).click()
    await p.waitForURL('**/student/attempts/*')
    const steps = p.getByRole('list', { name: '미션 진행 단계' })
    assert.equal(await steps.locator('[aria-current="step"]').innerText(), '내 생각 쓰기')
    assert.equal(await p.getByRole('navigation', { name: '학생 메뉴' }).count(), 0, '작성 중에는 메뉴를 숨김')
    await p.locator('.st-say h2').waitFor()
    await p.getByLabel('내 생각과 까닭').fill('그림이 있으면 이야기를 더 잘 이해할 수 있어요.')
    await p.getByText('초안 저장 완료(모의)', { exact: true }).waitFor()
    await p.getByRole('button', { name: '다 썼어요', exact: true }).click()
    await p.getByRole('button', { name: '이대로 돌아보기' }).waitFor()
    assert.equal(await steps.locator('[aria-current="step"]').innerText(), '한 걸음 더')
  })

  await check(
    '휴대전화 폭: 지도는 목록으로 접히고 가로 스크롤 없음',
    async (p) => {
      await student(p)
      assert.equal(await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
      assert.equal(await p.locator('.st-map-path').isVisible(), false)
      await p.getByRole('button', { name: '꾸미기', exact: true }).click()
      await p.getByRole('dialog', { name: '내 생각 지도 꾸미기' }).waitFor()
      assert.equal(await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
    },
    { viewport: { width: 390, height: 844 } },
  )

  await check('PIN 로그인 화면도 기본 테마 위에 표시', async (p) => {
    await p.goto(base + '/student-login', { waitUntil: 'domcontentloaded' })
    await p.getByRole('heading', { name: '이 기기를 학습용으로 등록해요' }).waitFor()
    assert.equal(await theme(p), 'lake')
  })

  assert.deepEqual(errors, [])
  console.log(`학생 테마 브라우저 회귀 ${checked.length}건 통과`)
} finally {
  await browser.close()
}
