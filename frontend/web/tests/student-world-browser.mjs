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
  await p.getByRole('region', { name: /^우리 집/ }).waitFor() // #648 새 홈
}
const theme = (p) => p.locator('.st-world').getAttribute('data-theme')

try {
  await check('생각 지도: 다섯 곳·오늘 여기·곳을 누르면 그 유형 미션만', async (p) => {
    await student(p)
    const places = p.locator('.st-islands > li')
    assert.equal(await places.count(), 5)
    assert.equal(await p.locator('.st-island[data-today]').count(), 1)
    await p.getByRole('button', { name: /^꼼꼼히 살펴보기/ }).click()
    await p.waitForURL(/\/student\/missions\?type=ANALYZE/)
    assert.equal(await p.getByRole('button', { name: '꼼꼼히 살펴보기', exact: true }).getAttribute('aria-pressed'), 'true')
    const kinds = await p.locator('.st-card .st-kicker').allInnerTexts()
    assert.ok(kinds.length > 0 && kinds.every((k) => k.includes('꼼꼼히 살펴보기')), kinds.join('/'))
    await p.getByRole('button', { name: '전체', exact: true }).click()
    await p.waitForURL(/\/student\/missions$/)
    await p.waitForFunction((n) => document.querySelectorAll('.st-card').length > n, kinds.length)
  })

  await check('꾸미기: 첫 화면에서 열고, 바꾸면 바로 반영되고 새로고침 뒤에도 유지', async (p) => {
    await student(p)
    assert.equal(await theme(p), 'lake')
    assert.equal(await p.getByRole('navigation', { name: '학생 메뉴' }).getByRole('button', { name: '꾸미기' }).count(), 0)
    // #648 꾸미기는 전체 화면(/student/customize): 설정 → 내 포인트 보기 → "꾸미기 해금하러 가기"
    await p.getByRole('button', { name: '설정', exact: true }).click()
    await p.getByRole('button', { name: '내 포인트 보기', exact: true }).click()
    await p.getByRole('button', { name: '꾸미기 해금하러 가기', exact: true }).click()
    await p.getByRole('heading', { name: '나만의 꾸미기', exact: true }).waitFor()
    const saved = p.waitForResponse((r) => r.url().endsWith('/students/me/preferences') && r.request().method() === 'PUT')
    await p.getByRole('button', { name: /^생각 숲/ }).click() // #648 카드는 미리 보기, 아래 버튼이 저장
    await p.getByRole('button', { name: '이 테마 쓰기', exact: true }).click()
    assert.deepEqual((await saved).request().postDataJSON(), { theme: 'forest', companion: 'mungchi' })
    assert.equal(await theme(p), 'forest')
    await p.getByRole('tab', { name: '캐릭터', exact: true }).click()
    await p.getByRole('button', { name: /^솔방울뭉치/ }).click() // #648 토리 → 솔방울뭉치(대응 친구 이름)
    await p.getByRole('button', { name: '함께 다니기', exact: true }).click()
    await p.getByText('골랐어요!', { exact: true }).waitFor()
    await p.getByRole('button', { name: '내 방', exact: true }).click()
    await p.waitForURL('**/student/room')
    await p.getByRole('button', { name: '홈', exact: true }).click()
    await p.getByText('나는 솔방울뭉치!', { exact: false }).waitFor()
    // 학생 화면은 로고 없이 고른 테마의 문구만 보인다
    await p.getByText('생각이 자라는 숲', { exact: true }).waitFor()
    assert.equal(await p.locator('.app-brand').count(), 0)
    // 학생은 새로고침하면 다시 로그인한다(#61). 다시 들어와도 서버에 저장한 설정이 그대로인지 본다.
    await p.reload({ waitUntil: 'domcontentloaded' })
    await p.waitForURL('**/student/login')
    await student(p)
    assert.equal(await theme(p), 'forest')
    await p.getByText('나는 솔방울뭉치!', { exact: false }).waitFor()
  })

  await check('미션 단계: 내 생각 쓰기 → 한 걸음 더, 질문은 캐릭터 말풍선', async (p) => {
    await student(p)
    await p.getByRole('button', { name: '홈', exact: true }).click() // #648: 미션 고르기는 홈 "더 풀어 보기"로
    await p.getByRole('button', { name: /더 풀어 보기/ }).click()
    await p
      .getByRole('article')
      .filter({ has: p.getByRole('heading', { name: '도서관에 만화책을 더 둘까요?', exact: true }) })
      .getByRole('button', { name: '미션 열기' })
      .click()
    await p.getByRole('button', { name: '미션 시작하기' }).click()
    await p.waitForURL('**/student/attempts/*')
    // 단계 칩은 미션 안내에만(문제 푸는 화면에서는 뺌, #807 D안)
    assert.equal(await p.getByRole('list', { name: '미션 진행 단계' }).count(), 0)
    assert.equal(await p.getByRole('navigation', { name: '학생 메뉴' }).count(), 0, '작성 중에는 메뉴를 숨김')
    await p.locator('.sw-question').waitFor()
    await p.getByLabel('내 생각과 이유').fill('그림이 있으면 이야기를 더 잘 이해할 수 있어요.')
    await p.getByText('저장했어요(모의)', { exact: true }).waitFor()
    await p.getByRole('button', { name: '다 썼어요', exact: true }).click()
    await p.getByRole('button', { name: '마무리 보기' }).waitFor()
  })

  await check(
    '휴대전화 폭: 지도는 목록으로 접히고 가로 스크롤 없음',
    async (p) => {
      await student(p)
      assert.equal(await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
      assert.equal(await p.locator('.st-map-path').isVisible(), false)
      await p.getByRole('button', { name: '설정', exact: true }).click()
      await p.getByRole('button', { name: '내 포인트 보기', exact: true }).click()
      await p.getByRole('button', { name: '꾸미기 해금하러 가기', exact: true }).click()
      await p.getByRole('heading', { name: '나만의 꾸미기', exact: true }).waitFor()
      assert.equal(await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
    },
    { viewport: { width: 390, height: 844 } },
  )

  await check('PIN 로그인 화면도 기본 테마 위에 표시', async (p) => {
    await p.goto(base + '/student/login', { waitUntil: 'domcontentloaded' })
    await p.getByRole('heading', { name: '이 기기를 학습용으로 등록해요' }).waitFor()
    assert.equal(await theme(p), 'lake')
  })

  assert.deepEqual(errors, [])
  console.log(`학생 테마 브라우저 회귀 ${checked.length}건 통과`)
} finally {
  await browser.close()
}
