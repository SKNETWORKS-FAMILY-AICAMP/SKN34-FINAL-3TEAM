// npm run dev:qr로 실행한 서버. 서로 다른 저장소/쿠키를 가진 보호자와 태블릿을 검증한다.
import { createRequire } from 'node:module'
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'
const require = createRequire(process.env.PLAYWRIGHT_PACKAGE ?? import.meta.url)
const { chromium } = require('playwright')
const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || undefined })
const base = process.env.DEMO_URL ?? 'http://127.0.0.1:5196'
const out = process.env.QA_OUTPUT_DIR
if (out) await mkdir(out, { recursive: true })
const errors = []
const parentContext = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const tabletContext = await browser.newContext({ viewport: { width: 1194, height: 834 }, hasTouch: true })
const otherContext = await browser.newContext()
for (const context of [parentContext, tabletContext, otherContext]) {
  await context.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, (r) => r.abort())
  await context.route('**/login?reauthMock=1', (route) => route.fulfill({
    contentType: 'text/html', body: '<!doctype html><title>Google 재인증 대역</title><p>재확인 완료 후 원래 화면으로 돌아가세요.</p>',
  }))
  context.on('page', (p) => { p.setDefaultTimeout(15_000); p.on('pageerror', (e) => errors.push(e.message)) })
}
const parent = await parentContext.newPage(), tablet = await tabletContext.newPage(), other = await otherContext.newPage()
async function pin(page, value) {
  const pad = page.getByRole('group', { name: 'PIN 숫자 키패드', exact: true })
  for (const digit of value) await pad.getByRole('button', { name: digit, exact: true }).click()
  await pad.getByRole('button', { name: '확인', exact: true }).click()
}
try {
  await parent.goto(base + '/login')
  await parent.getByRole('button', { name: '시연 계정으로 로그인' }).click()
  await parent.waitForURL('**/parent/journal')
  await parent.goto(base + '/parent/devices')
  await parent.getByRole('button', { name: '서윤 Google 본인 확인', exact: true }).click()
  await parent.getByRole('button', { name: '서윤 완료 확인', exact: true }).click()
  await parent.getByText('재확인을 완료했습니다', { exact: false }).waitFor()
  await parent.getByLabel('서윤 새 PIN', { exact: true }).fill('4831')
  await parent.getByLabel('서윤 새 PIN 확인').fill('4831')
  await parent.getByRole('form', { name: '서윤 PIN', exact: true }).getByRole('button', { name: /PIN 정하기|PIN 바꾸기|PIN 설정·변경/ }).click()
  await parent.getByText('서윤의 PIN을 저장했습니다.', { exact: false }).waitFor()
  const contract = await parent.evaluate(async () => {
    const { parentApi } = await import('/src/data/parent/api.ts')
    const { studentDeviceApi: api } = await import('/src/data/studentDevice/api.ts')
    const rejected = async (run) => { try { await run(); return 'ACCEPTED' } catch (error) { return error.problem?.code } }
    const children = await parentApi.children()
    const noGrant = await rejected(() => api.setPin('demo-seoyun', '4831', ''))
    const challenge = await api.startPinReauth('demo-seoyun')
    const { reauthToken } = await api.finishPinReauth(challenge.challengeId)
    const otherChild = await rejected(() => api.setPin('demo-doyun', '4831', reauthToken))
    await api.setPin('demo-seoyun', '4831', reauthToken)
    const reuse = await rejected(() => api.setPin('demo-seoyun', '4831', reauthToken))
    return { children: children.items, noGrant, otherChild, reuse }
  })
  assert.equal(contract.noGrant, 'REAUTH_REQUIRED')
  assert.equal(contract.otherChild, 'REAUTH_REQUIRED')
  assert.equal(contract.reuse, 'REAUTH_REQUIRED')
  const child = contract.children.find((c) => c.id === 'demo-seoyun')
  assert.equal(child.guardianConsentRequired, false)
  assert.equal(child.recordState, 'AVAILABLE')
  assert.equal(typeof child.hasRecords, 'boolean')
  assert.equal(child.pinSet, true)
  console.log('PASS #104 자녀별 재인증·단회 소비 유지 / 공유 자녀 목록의 동의·기록·PIN 상태 계약')
  await parent.getByLabel('도윤 · 초5').uncheck()
  const address = parent.getByLabel('QR에서 열 주소')
  if (process.env.TABLET_ORIGIN) await address.selectOption(process.env.TABLET_ORIGIN)
  else await parent.waitForFunction(() => {
    const select = document.querySelector('select[aria-label="QR에서 열 주소"]')
    return select && !/localhost|127\.0\.0\.1/.test(select.value)
  })
  await parent.getByRole('button', { name: '등록 코드 만들기', exact: true }).click()
  await parent.getByRole('img', { name: /등록 QR 코드/ }).waitFor()
  const url = await parent.getByRole('link', { name: '등록 화면 열기', exact: true }).getAttribute('href')
  assert.ok(!url.includes('localhost'), 'QR은 태블릿이 접속할 주소여야 함')
  const pairing = new URL(url).searchParams.get('code')
  assert.match(pairing, /^[A-Z0-9]{8}$/)
  if (out) await parent.screenshot({ path: path.join(out, 'laptop-qr.jpg'), type: 'jpeg', fullPage: true })
  // 카메라가 읽은 QR URL로 이동하는 것과 동일한 진입. 보호자 로그인/스토리지 복사 없음.
  await tablet.goto(url)
  assert.equal(await tablet.evaluate(() => window.isSecureContext), false, 'LAN HTTP 시연 경로')
  await tablet.getByRole('heading', { name: '이 기기를 학습용으로 등록해요' }).waitFor()
  assert.equal(await tablet.getByLabel('등록 코드', { exact: true }).inputValue(), pairing)
  await tablet.getByLabel('기기 이름', { exact: true }).fill('QR 시연 태블릿')
  if (out) await tablet.screenshot({ path: path.join(out, 'tablet-register.jpg'), type: 'jpeg' })
  await tablet.getByRole('button', { name: '이 기기 등록하기', exact: true }).click()
  await tablet.getByRole('heading', { name: '서윤, 안녕하세요!' }).waitFor()
  assert.ok(!new URL(tablet.url()).searchParams.has('code'), '사용한 코드는 주소에서 제거')
  await tablet.getByText('기기 등록을 마쳤어요.', { exact: false }).waitFor()
  await parent.getByRole('cell', { name: 'QR 시연 태블릿', exact: true }).waitFor()
  if (out) await tablet.screenshot({ path: path.join(out, 'tablet-pin.jpg'), type: 'jpeg' })
  console.log('PASS 노트북 QR → 별도 태블릿 LAN HTTP → 코드 자동 입력 → 기기 등록 → 보호자 목록 자동 갱신')

  await other.goto(url)
  await other.getByRole('button', { name: '이 기기 등록하기', exact: true }).click()
  await other.getByText('PAIRING_CODE_INVALID', { exact: false }).waitFor()
  console.log('PASS 같은 QR의 다른 기기 재사용 거부')

  await pin(tablet, '9999')
  await tablet.getByText('남은 기회는 4번이에요.', { exact: false }).waitFor()
  await pin(tablet, '4831')
  await tablet.waitForURL('**/student/home')
  await tablet.getByRole('heading', { name: /^학습 홈/ }).waitFor()
  if (out) await tablet.screenshot({ path: path.join(out, 'tablet-home.jpg'), type: 'jpeg' })
  console.log('PASS 틀린 PIN 안내 → 올바른 PIN → 학생 학습 홈')

  await tablet.reload()
  await tablet.waitForURL('**/student/login')
  await tablet.getByRole('heading', { name: '서윤, 안녕하세요!' }).waitFor()
  assert.equal(await tablet.getByRole('heading', { name: '이 기기를 학습용으로 등록해요' }).count(), 0)
  console.log('PASS 새로고침해도 기기 등록 유지, PIN 재로그인')

  for (let left = 4; left >= 1; left--) {
    await pin(tablet, '9999')
    await tablet.getByText(`남은 기회는 ${left}번이에요.`, { exact: false }).waitFor()
  }
  await pin(tablet, '9999')
  await tablet.getByText('PIN이 잠겼어요. 보호자에게 PIN을 다시 정해 달라고 해 주세요.').waitFor()
  await tablet.reload()
  await tablet.getByText('PIN이 잠겼어요. 보호자에게 PIN을 다시 정해 달라고 해 주세요.').waitFor()
  assert.equal(await tablet.getByRole('group', { name: 'PIN 숫자 키패드' }).count(), 0)
  await parent.reload()
  const pinForm = parent.getByRole('form', { name: '서윤 PIN', exact: true })
  await pinForm.locator('[data-pin-state="locked"]').waitFor()
  await parent.getByRole('button', { name: '서윤 Google 본인 확인', exact: true }).click()
  await parent.getByRole('button', { name: '서윤 완료 확인', exact: true }).click()
  await parent.getByLabel('서윤 새 PIN', { exact: true }).fill('4831')
  await parent.getByLabel('서윤 새 PIN 확인').fill('4831')
  await pinForm.getByRole('button', { name: 'PIN 바꾸기', exact: true }).click()
  await pinForm.locator('[data-pin-state="set"]').waitFor()
  await tablet.reload()
  await tablet.getByRole('group', { name: 'PIN 숫자 키패드', exact: true }).waitFor()
  console.log('PASS 공유 PIN 5회 잠금·새로고침 후 잠금 유지·자녀별 Google 재확인 후 재설정')

  const card = parent.getByRole('row').filter({ has: parent.getByRole('cell', { name: 'QR 시연 태블릿', exact: true }) })
  await card.getByRole('button', { name: 'QR 시연 태블릿 등록 해제', exact: true }).click()
  await card.getByRole('button', { name: '해제', exact: true }).click()
  await pin(tablet, '4831')
  await tablet.getByRole('heading', { name: '이 기기를 학습용으로 등록해요' }).waitFor()
  console.log('PASS 보호자 기기 해제 후 태블릿 PIN 로그인 거부')
  assert.deepEqual(errors, [])
} catch (error) {
  console.error('PARENT', (await parent.locator('body').innerText()).slice(-2000))
  console.error('TABLET', (await tablet.locator('body').innerText()).slice(-2000))
  if (out) await tablet.screenshot({ path: path.join(out, 'failure.jpg'), type: 'jpeg' })
  throw error
} finally {
  await browser.close()
}
