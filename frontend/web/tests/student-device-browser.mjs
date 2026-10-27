// #59 학생 기기 등록·PIN 로그인 브라우저 회귀. DEV 서버 + VITE_API_MOCK=true 필요.
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
async function check(name, run) {
  if (process.env.QA_FILTER && !name.includes(process.env.QA_FILTER)) return
  const context = await browser.newContext({ viewport: { width: 1024, height: 768 } })
  await context.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, (route) => route.abort())
  const p = await context.newPage()
  p.setDefaultTimeout(12000)
  p.on('pageerror', (e) => errors.push(name + ': ' + e.message))
  try {
    await run(p)
    checked.push(name)
    if (out) await p.screenshot({ path: path.join(out, `device-${checked.length}.jpg`), type: 'jpeg' })
    console.log('PASS ' + name)
  } catch (e) {
    if (out) await p.screenshot({ path: path.join(out, `failed-device-${checked.length}.jpg`), type: 'jpeg' })
    console.error((await p.locator('body').innerText()).slice(-3000))
    throw e
  } finally {
    await context.close()
  }
}

async function parentLogin(p) {
  await p.goto(base + '/login', { waitUntil: 'domcontentloaded' })
  await p.getByRole('button', { name: '시연 계정으로 로그인' }).click()
  await p.waitForURL(/\/parent\/journal/)
}
/** 학부모: PIN 설정 + 코드 발급. kids는 기기에 등록할 자녀 별명 */
async function parentIssue(p, kids = ['서윤'], pin = '4831') {
  await parentLogin(p)
  await p.goto(base + '/parent/devices', { waitUntil: 'domcontentloaded' })
  await p.getByRole('heading', { name: '자녀 PIN' }).waitFor()
  await p.getByLabel('PIN 재확인 비밀번호').fill('demo-only')
  await p.getByRole('button', { name: '본인 재확인' }).click()
  await p.getByText('재확인을 완료했습니다', { exact: false }).waitFor()
  for (const kid of kids) {
    await p.getByLabel(`${kid} 새 PIN`, { exact: true }).fill(pin)
    await p.getByLabel(`${kid} 새 PIN 확인`).fill(pin)
    await p.getByRole('form', { name: `${kid} PIN` }).getByRole('button').first().click()
    await p.getByText(`${kid}의 PIN을 저장했습니다.`, { exact: false }).waitFor()
  }
  for (const label of ['서윤 · 초3', '도윤 · 초5'])
    if (!kids.includes(label.split(' ')[0])) await p.getByLabel(label).uncheck()
  await p.getByRole('button', { name: '등록 코드 만들기' }).click()
  const code = (await p.locator('.pairing-code strong').innerText()).replace(/\s/g, '')
  assert.match(code, /^[A-Z0-9]{8}$/)
  await p.getByText(/남은 시간 \d+:\d\d/).waitFor()
  assert.equal(await p.getByRole('img', { name: /등록 QR 코드/ }).count(), 1, 'QR 표시')
  await p.getByRole('button', { name: '로그아웃' }).click()
  await p.waitForURL('**/login')
  return code
}
async function registerDevice(p, code, label = '거실 컴퓨터') {
  await p.goto(base + '/student-login', { waitUntil: 'domcontentloaded' })
  await p.getByRole('heading', { name: '이 기기를 학습용으로 등록해요' }).waitFor()
  await p.getByLabel('등록 코드').fill(code)
  await p.getByLabel('기기 이름').fill(label)
  await p.getByRole('button', { name: '이 기기 등록하기' }).click()
}
async function typePin(p, pin, pad = 'PIN 숫자 키패드') {
  const keys = p.getByRole('group', { name: pad, exact: true })
  for (const d of pin) await keys.getByRole('button', { name: d, exact: true }).click()
  await keys.getByRole('button', { name: '확인' }).click()
}

try {
  await check('미등록 기기: 코드 등록 화면만, PIN 키패드 없음', async (p) => {
    await p.goto(base + '/student-login', { waitUntil: 'domcontentloaded' })
    await p.getByRole('heading', { name: '이 기기를 학습용으로 등록해요' }).waitFor()
    assert.equal(await p.getByRole('group', { name: 'PIN 숫자 키패드' }).count(), 0)
    await p.getByLabel('등록 코드').fill('ZZZZ9999')
    await p.getByRole('button', { name: '이 기기 등록하기' }).click()
    await p.getByText('PAIRING_CODE_INVALID').waitFor()
    assert.equal(await p.getByRole('group', { name: 'PIN 숫자 키패드' }).count(), 0)
  })

  await check('학부모 등록 → 자녀 1명은 선택 생략 → PIN → 학생 홈 → 미션 시작', async (p) => {
    const code = await parentIssue(p, ['서윤'])
    await registerDevice(p, code)
    await p.getByRole('heading', { name: '서윤, 안녕하세요!' }).waitFor()
    await typePin(p, '4831')
    await p.waitForURL('**/student/home')
    await p.getByRole('heading', { name: /^학습 홈/ }).waitFor()
    await p.getByRole('button', { name: '미션 고르기', exact: true }).click()
    await p.getByRole('button', { name: '미션 열기' }).first().click()
    await p.getByRole('button', { name: '작성하기 · 진행 중이면 이어서' }).click()
    await p.waitForURL('**/student/attempts/*')
    await p.getByRole('region', { name: '미션 작성기' }).waitFor()
  })

  await check('자녀 2명 기기: 프로필 선택, PIN 미설정 자녀는 동석 안내', async (p) => {
    const code = await parentIssue(p, ['서윤', '도윤'])
    // 도윤은 PIN을 같이 정했으므로 서윤만 시연하고, 미설정은 상태 선택기로 확인
    await registerDevice(p, code)
    await p.getByRole('heading', { name: '누가 공부할까요?' }).waitFor()
    await p.getByRole('button', { name: /서윤/ }).click()
    await p.getByRole('group', { name: 'PIN 숫자 키패드' }).waitFor()
    await p.getByRole('button', { name: '다른 친구 고르기' }).click()
    await p.getByLabel('기기 상태 시연').selectOption('pin-not-set')
    await p.getByRole('button', { name: /PIN이 아직 없어요/ }).first().waitFor()
    await p.getByRole('button', { name: /도윤/ }).click()
    await p.getByText('아직 PIN이 없어요. 보호자와 함께 로그인해서 시작해 주세요.').waitFor()
    assert.equal(await p.getByRole('group', { name: 'PIN 숫자 키패드' }).count(), 0)
  })

  await check('5회 실패: 남은 기회 안내 후 잠금, 키패드 숨김', async (p) => {
    const code = await parentIssue(p, ['서윤'])
    await registerDevice(p, code)
    for (let left = 4; left >= 1; left--) {
      await typePin(p, '9999')
      await p.getByText(`남은 기회는 ${left}번이에요.`, { exact: false }).waitFor()
    }
    await typePin(p, '9999')
    await p.getByText('PIN이 잠겼어요. 보호자에게 PIN을 다시 정해 달라고 해 주세요.').waitFor()
    assert.equal(await p.getByRole('group', { name: 'PIN 숫자 키패드' }).count(), 0)
    // 학부모 화면에 잠금 상태가 보인다
    await parentLogin(p)
    await p.goto(base + '/parent/devices', { waitUntil: 'domcontentloaded' })
    await p.locator('[data-pin-state="locked"]').first().waitFor()
  })

  await check('학생 access 만료 후 새로고침: refresh 없이 로그인 화면으로', async (p) => {
    const code = await parentIssue(p, ['서윤'])
    await registerDevice(p, code)
    await typePin(p, '4831')
    await p.waitForURL('**/student/home')
    await p.getByRole('button', { name: '미션 고르기', exact: true }).click()
    await p.getByRole('button', { name: '미션 열기' }).first().click()
    await p.getByRole('button', { name: '작성하기 · 진행 중이면 이어서' }).click()
    await p.waitForURL('**/student/attempts/*')
    await p.getByLabel('상태 시연').selectOption('token-expired')
    await p.reload({ waitUntil: 'domcontentloaded' }).catch(() => {})
    // 새로고침하면 refresh가 없으므로 다시 PIN 로그인으로 돌아가야 한다
    await p.waitForURL(/\/login|\/student-login/)
  })

  await check('만료 이벤트: 화면을 떠나지 않고 PIN 재입력 모달', async (p) => {
    const code = await parentIssue(p, ['서윤'])
    await registerDevice(p, code)
    await typePin(p, '4831')
    await p.waitForURL('**/student/home')
    const url = p.url()
    // 첫 화면 조회가 끝난 뒤 만료시킨다(진행 중인 요청과 겹치지 않게)
    await p.getByRole('heading', { name: '생각 지도', exact: true }).waitFor()
    await p.getByLabel('상태 시연').selectOption('token-expired')
    const dialog = p.getByRole('dialog', { name: 'PIN을 다시 눌러 주세요' })
    await dialog.waitFor()
    await typePin(p, '4831', '다시 확인 PIN 숫자 키패드')
    await dialog.waitFor({ state: 'detached' })
    assert.ok(p.url().startsWith(base + '/student/'), url)
  })

  await check('학생 → 학부모 전환은 학부모 로그인 요구', async (p) => {
    const code = await parentIssue(p, ['서윤'])
    await registerDevice(p, code)
    await typePin(p, '4831')
    await p.waitForURL('**/student/home')
    await p.getByRole('button', { name: '학부모 로그인으로' }).click()
    await p.waitForURL('**/login')
    await p.goto(base + '/parent/journal', { waitUntil: 'domcontentloaded' })
    await p.waitForURL('**/login')
    await p.getByRole('heading', { name: '학부모 로그인' }).waitFor()
  })

  await check('해제·만료 기기: PIN 대신 다시 등록 화면', async (p) => {
    const code = await parentIssue(p, ['서윤'])
    await registerDevice(p, code)
    await p.getByRole('group', { name: 'PIN 숫자 키패드' }).waitFor()
    await p.getByLabel('기기 상태 시연').selectOption('device-revoked')
    await p.getByRole('heading', { name: '이 기기를 학습용으로 등록해요' }).waitFor()
    assert.equal(await p.getByRole('group', { name: 'PIN 숫자 키패드' }).count(), 0)
  })

  await check('학부모 기기 목록: 이름·자녀·마지막 사용 표시 후 해제', async (p) => {
    const code = await parentIssue(p, ['서윤'])
    await registerDevice(p, code, '공부방 노트북')
    await typePin(p, '4831')
    await p.waitForURL('**/student/home')
    await p.getByRole('button', { name: '학부모 로그인으로' }).click()
    await parentLogin(p)
    await p.goto(base + '/parent/devices', { waitUntil: 'domcontentloaded' })
    const row = p.getByRole('row', { name: /공부방 노트북/ })
    await row.waitFor()
    assert.ok((await row.innerText()).includes('서윤'))
    assert.equal((await row.innerText()).includes('아직 사용 전'), false)
    await row.getByRole('button', { name: '공부방 노트북 등록 해제' }).click()
    await row.getByRole('button', { name: '해제', exact: true }).click()
    await p.getByText('아직 등록된 기기가 없습니다.').waitFor()
  })

  assert.deepEqual(errors, [])
  console.log(`학생 기기 브라우저 회귀 ${checked.length}건 통과`)
} finally {
  await browser.close()
}
