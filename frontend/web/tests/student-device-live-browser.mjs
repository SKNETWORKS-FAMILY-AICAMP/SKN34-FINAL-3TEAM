// Real core/PostgreSQL/Redis and frontend; only Google and learning record lookup are HTTP doubles.
// Requires isolated fixtures (parent Google sub issue58-google, child nickname 검증학생).
// CORE: webOrigin=http://127.0.0.1:5189; token/jwk URLs point to this test's :18589 server.
import { createRequire } from 'node:module'
import { createServer } from 'node:http'
import { generateKeyPairSync, sign } from 'node:crypto'
import assert from 'node:assert/strict'

const require = createRequire(process.env.PLAYWRIGHT_PACKAGE ?? import.meta.url)
const { chromium } = require('playwright')
const base = process.env.DEMO_URL ?? 'http://127.0.0.1:5189'
const deviceLabel = `연결 검증 기기 ${Date.now()}`
const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 })
const jwk = { ...publicKey.export({ format: 'jwk' }), kid: crypto.randomUUID(), use: 'sig', alg: 'RS256' }
const codes = new Map()
let exchanges = 0
const json = (res, body, status = 200) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(body)) }
const server = createServer(async (req, res) => {
  if (req.url === '/jwks') return json(res, { keys: [jwk] })
  if (req.url?.match(/^\/internal\/records\/students\/[^/]+\/exists$/))
    return json(res, { studentId: req.url.split('/')[4], hasRecords: false })
  if (req.url === '/token' && req.method === 'POST') {
    let raw = ''; for await (const part of req) raw += part
    const form = new URLSearchParams(raw), proof = codes.get(form.get('code'))
    codes.delete(form.get('code'))
    if (!proof || form.get('redirect_uri') !== proof.redirectUri) return json(res, { error: 'invalid_grant' }, 400)
    const { createHash } = await import('node:crypto')
    if (createHash('sha256').update(form.get('code_verifier')).digest('base64url') !== proof.challenge)
      return json(res, { error: 'invalid_grant' }, 400)
    const now = Math.floor(Date.now() / 1000)
    const encode = (v) => Buffer.from(JSON.stringify(v)).toString('base64url')
    const message = `${encode({ alg: 'RS256', kid: jwk.kid })}.${encode({
      iss: 'https://accounts.google.com', aud: 'issue58-client', sub: 'issue58-google',
      email: 'issue58@example.test', email_verified: true, name: '검증 보호자', nonce: proof.nonce, iat: now, exp: now + 300,
    })}`
    exchanges++
    return json(res, { id_token: `${message}.${sign('RSA-SHA256', Buffer.from(message), privateKey).toString('base64url')}` })
  }
  return json(res, { status: 404, code: 'NOT_FOUND' }, 404)
})
await new Promise((resolve) => server.listen(18589, '0.0.0.0', resolve))
const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || undefined })
const parent = await browser.newContext()
const child = await browser.newContext()
for (const context of [parent, child])
  await context.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, (route) => route.abort())
function googleCallback(raw) {
  const url = new URL(raw), code = crypto.randomUUID()
  codes.set(code, { nonce: url.searchParams.get('nonce'), redirectUri: url.searchParams.get('redirect_uri'), challenge: url.searchParams.get('code_challenge') })
  const callback = new URL(url.searchParams.get('redirect_uri'))
  callback.searchParams.set('state', url.searchParams.get('state')); callback.searchParams.set('code', code)
  return callback.href
}
await parent.route('**/api/v1/auth/google/authorize', async (route) => {
  const response = await route.fetch({ maxRedirects: 0 })
  assert.equal(response.status(), 302)
  await route.fulfill({ response, headers: { ...response.headers(), location: googleCallback(response.headers().location) } })
})
await parent.route('https://accounts.google.com/**', async (route) => {
  await route.fulfill({ status: 302, headers: { Location: googleCallback(route.request().url()) } })
})
let parentAccess = '', studentAccess = ''
const p = await parent.newPage(), k = await child.newPage()
p.setDefaultTimeout(30000); k.setDefaultTimeout(30000)
p.on('response', async (response) => {
  if (response.url().endsWith('/api/v1/auth/refresh') && response.ok()) parentAccess = (await response.json()).accessToken
})
k.on('response', async (response) => {
  if (response.url().endsWith('/api/v1/auth/student/login') && response.ok()) studentAccess = (await response.json()).accessToken
})
const authHeaders = () => ({ Authorization: `Bearer ${parentAccess}`, Origin: base, 'X-Requested-With': 'XMLHttpRequest' })
async function reauthenticate() {
  const popupPromise = p.waitForEvent('popup')
  await p.getByRole('button', { name: '검증학생 Google 본인 확인' }).click()
  const popup = await popupPromise
  await popup.waitForURL('**/api/v1/auth/google/reauth/callback?**')
  await popup.getByText('VERIFIED', { exact: false }).waitFor()
  await p.getByRole('button', { name: '검증학생 완료 확인' }).click()
  await p.getByText('재확인을 완료했습니다', { exact: false }).waitFor()
  await popup.close()
}
async function savePin(pin) {
  await reauthenticate()
  await p.getByLabel('검증학생 새 PIN', { exact: true }).fill(pin)
  await p.getByLabel('검증학생 새 PIN 확인').fill(pin)
  await p.getByRole('form', { name: '검증학생 PIN' }).getByRole('button', { name: /PIN 정하기|PIN 바꾸기/ }).click()
  await p.getByText('검증학생의 PIN을 저장했습니다.', { exact: false }).waitFor()
}
async function enterPin(pin) {
  const keys = k.getByRole('group', { name: 'PIN 숫자 키패드', exact: true })
  for (const digit of pin) await keys.getByRole('button', { name: digit, exact: true }).click()
  await keys.getByRole('button', { name: '확인' }).click()
}
try {
  await p.goto(base + '/api/v1/auth/google/authorize')
  await p.waitForURL('**/parent/journal', { waitUntil: 'domcontentloaded' })
  await p.goto(base + '/parent/devices')
  await p.getByRole('heading', { name: '자녀 PIN', exact: true }).waitFor()
  await savePin('4831')
  assert.ok(parentAccess)
  let children = await (await parent.request.get(base + '/api/v1/children', { headers: authHeaders() })).json()
  assert.equal(children.items[0].pinSet, true)
  assert.equal(children.items[0].pinLocked, false)
  assert.equal(children.items[0].recordState, 'AVAILABLE')
  assert.equal(children.items[0].hasRecords, false)
  await p.getByRole('button', { name: '등록 코드 만들기' }).click()
  const code = (await p.locator('.pairing-code strong').innerText()).replace(/\s/g, '')
  await k.goto(base + '/student/login')
  await k.getByLabel('등록 코드').fill(code)
  await k.getByLabel('기기 이름').fill(deviceLabel)
  await k.getByRole('button', { name: '이 기기 등록하기' }).click()
  await k.getByRole('group', { name: 'PIN 숫자 키패드' }).waitFor()
  const credential = (await child.cookies()).find((c) => c.name === 'student_device')
  assert.ok(credential?.httpOnly); assert.equal(credential.sameSite, 'Strict'); assert.equal(credential.path, '/api/v1/auth/student')
  assert.equal((await child.cookies()).some((c) => c.name === 'sagomungchi_refresh'), false)
  assert.equal(await k.evaluate(() => document.cookie.includes('student_device')), false)
  for (let left = 4; left >= 1; left--) {
    await enterPin('9999'); await k.getByText(`남은 기회는 ${left}번이에요.`, { exact: false }).waitFor()
  }
  await enterPin('9999')
  await k.getByText('PIN이 잠겼어요. 보호자에게 PIN을 다시 정해 달라고 해 주세요.').waitFor()
  await p.reload()
  await p.getByText('잠김 · 다시 정해야 풀려요', { exact: true }).waitFor()
  await savePin('5729')
  await k.reload()
  const loginResponse = k.waitForResponse((response) => response.url().endsWith('/api/v1/auth/student/login') && response.ok())
  await enterPin('5729')
  studentAccess = (await (await loginResponse).json()).accessToken
  await k.waitForURL('**/student/home', { waitUntil: 'domcontentloaded' })
  assert.ok(studentAccess)
  const studentHeaders = { Authorization: `Bearer ${studentAccess}` }
  assert.equal((await child.request.get(base + '/api/v1/me', { headers: studentHeaders })).status(), 200)
  assert.equal((await child.request.get(base + '/api/v1/student-devices', { headers: studentHeaders })).status(), 403)
  assert.equal((await child.request.post(base + '/api/v1/auth/refresh', { headers: { Origin: base, 'X-Requested-With': 'XMLHttpRequest' } })).status(), 401)
  assert.equal((await parent.request.get(base + '/api/v1/me', { headers: authHeaders() })).status(), 200)
  await p.reload()
  await p.getByRole('button', { name: `${deviceLabel} 등록 해제` }).click()
  const revoked = p.waitForResponse((response) => response.request().method() === 'DELETE' && response.url().includes('/student-devices/'))
  await p.getByRole('group', { name: `${deviceLabel} 해제 확인` }).getByRole('button', { name: '해제', exact: true }).click()
  assert.equal((await revoked).status(), 204)
  assert.equal((await child.request.get(base + '/api/v1/me', { headers: studentHeaders })).status(), 200)
  assert.equal((await child.request.get(base + '/api/v1/auth/student/profiles')).status(), 401)
  assert.equal(exchanges, 3, 'login plus two child-specific Google reauth proofs')
  console.log('PASS real core + PostgreSQL + Redis + browser: Google HTTP/JWKS double, PIN set/lock/reset, pairing cookie, no refresh, parent preserved, revoke semantics')
} catch (error) {
  console.error('parent path', new URL(p.url()).pathname, 'student path', k.url() === 'about:blank' ? 'blank' : new URL(k.url()).pathname)
  console.error((await p.locator('body').innerText()).slice(-2000))
  throw error
} finally {
  await browser.close()
  await new Promise((resolve) => server.close(resolve))
}
