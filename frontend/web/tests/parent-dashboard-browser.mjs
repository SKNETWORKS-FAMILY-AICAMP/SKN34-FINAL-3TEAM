// 학부모 대시보드(시안 적용) 브라우저 회귀. DEV 서버 + VITE_API_MOCK=true 필요.
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
    if (out) await p.screenshot({ path: path.join(out, `parent-${checked.length}.jpg`), type: 'jpeg', fullPage: true })
    console.log('PASS ' + name)
  } catch (e) {
    if (out) await p.screenshot({ path: path.join(out, `failed-parent-${checked.length}.jpg`), type: 'jpeg' })
    console.error((await p.locator('body').innerText()).slice(-3000))
    throw e
  } finally {
    await context.close()
  }
}
async function parent(p) {
  await p.goto(base + '/login', { waitUntil: 'domcontentloaded' })
  await p.getByRole('button', { name: '시연 계정으로 로그인' }).click()
  await p.waitForURL(/\/parent\/journal/)
  await p.getByRole('heading', { name: '서윤의 학습 기록' }).waitFor()
}
const mode = (p, value) => p.getByLabel('상태 시연', { exact: true }).selectOption(value)

try {
  await check('왼쪽 메뉴·지표 3개·다섯 유형 미관찰·리포트 카드·기록 원문', async (p) => {
    await parent(p)
    const menu = p.getByRole('navigation', { name: '학부모 기록 공간 메뉴' })
    assert.equal(await menu.getByRole('link').count(), 5)
    assert.equal(await menu.getByRole('link', { name: '대시보드·공책' }).getAttribute('aria-current'), 'page')
    const kpis = p.getByRole('region', { name: '기간 요약' })
    for (const h of ['답을 남긴 활동', '생각을 덧붙인 활동', '관찰된 생각 유형'])
      await kpis.getByRole('heading', { name: h }).waitFor()
    const types = p.getByRole('region', { name: '다섯 가지 생각 활동' })
    assert.equal(await types.getByRole('listitem').count(), 5)
    await types.getByText('미관찰', { exact: true }).first().waitFor()
    await p.getByRole('region', { name: '주간 리포트' }).getByRole('button', { name: '리포트 열기' }).waitFor()
    const rows = p.getByRole('region', { name: '학습 기록' }).getByRole('row')
    assert.ok((await rows.count()) > 1)
    await p.getByRole('button', { name: /원문 보기$/ }).first().click()
    await p.getByRole('dialog', { name: '학습 기록 원문' }).getByText('돌아보기').first().waitFor()
  })

  await check('표본 부족·기록 없음 상태는 비율 없이 안내', async (p) => {
    await parent(p)
    await mode(p, 'small')
    await p.locator('[data-query-state="INSUFFICIENT_SAMPLE"]').waitFor()
    assert.equal(await p.getByRole('region', { name: '기간 요약' }).getByText('%').count(), 0)
    await mode(p, 'empty')
    await p.locator('[data-query-state="NO_RECORD"]').waitFor()
    await p.getByText('아직 기록이 없습니다. 첫 학습 후 답변이 여기에 연결됩니다.').waitFor()
  })

  await check('유형의 미션 바로가기와 리포트 열기는 같은 자녀·기간 유지', async (p) => {
    await parent(p)
    const before = new URL(p.url()).search
    await p.getByRole('region', { name: '다섯 가지 생각 활동' }).getByRole('button').first().click()
    await p.getByRole('dialog', { name: '학습 기록 원문' }).waitFor()
    await p.getByRole('button', { name: '창 닫기' }).click()
    await p.getByRole('region', { name: '주간 리포트' }).getByRole('button', { name: '리포트 열기' }).click()
    await p.waitForURL(/\/parent\/report/)
    assert.equal(new URL(p.url()).search, before)
  })

  await check(
    '휴대전화 폭: 메뉴가 위로 접히고 가로 스크롤 없음(표만 상자 안에서 넘김)',
    async (p) => {
      await parent(p)
      assert.equal(await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
    },
    { viewport: { width: 390, height: 844 } },
  )

  assert.deepEqual(errors, [])
  console.log(`학부모 대시보드 브라우저 회귀 ${checked.length}건 통과`)
} finally {
  await browser.close()
}
