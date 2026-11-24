import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

// Real browser storage, input and BroadcastChannel with the production auth module.
// Only the HTTP server is synthetic; backend authorization is covered by StudentDeviceAuthTest.
test('student reload, copied tab, activity renewal, idle expiry and session-scoped logout', async ({ page, context }) => {
  let now = Date.now()
  let renewals = 0
  const revoked = new Set<string>()
  const token = (sid: string) => `test.${Buffer.from(JSON.stringify({ role: 'STUDENT', sid,
    iat: Math.floor(now / 1000), exp: Math.floor(now / 1000) + 120 })).toString('base64url')}.test`
  await context.route('**/session-test', route => route.fulfill({ contentType: 'text/html', body:
    `<button id="activity">학습 조작</button><script type="module">
      import * as auth from '/data/apiClient.ts'; window.auth = auth;
      auth.watchStudentActivity(); window.ready = true;
    </script>` }))
  for (const name of ['apiClient', 'studentSession']) {
    const source = readFileSync(new URL(`../../src/data/${name}.ts`, import.meta.url), 'utf8')
    const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
    await context.route(`**/data/${name}.ts`, route => route.fulfill({ contentType: 'text/javascript', body: code }))
  }
  await context.route('**/api/v1/**', async route => {
    const bearer = route.request().headers().authorization?.replace('Bearer ', '') ?? ''
    let claims: { sid: string; exp: number } | undefined
    try { claims = JSON.parse(Buffer.from(bearer.split('.')[1], 'base64url').toString()) } catch { /* no credentials */ }
    if (!claims || claims.exp * 1000 <= now || revoked.has(claims.sid))
      return route.fulfill({ status: 401, json: { code: 'TOKEN_EXPIRED' } })
    if (route.request().url().endsWith('/renew')) {
      renewals++
      return route.fulfill({ json: { accessToken: token(claims.sid), expiresIn: 120 } })
    }
    if (route.request().url().endsWith('/logout')) revoked.add(claims.sid)
    return route.fulfill({ json: { ok: true } })
  })
  await page.clock.install({ time: now })
  await page.goto('/session-test')
  await page.waitForFunction('window.ready')
  await page.evaluate(t => { sessionStorage.setItem('sagomungchi:student-access', t) }, token('same'))
  await page.reload()
  await page.waitForFunction('window.ready')
  expect(await page.evaluate('window.auth.isStudentSession() && window.auth.hasAccessToken()')).toBe(true)
  expect(await page.evaluate('window.auth.apiFetch("/me")')).toEqual({ ok: true })
  expect(renewals).toBe(0)

  const popupPromise = page.waitForEvent('popup')
  await page.evaluate('window.open("/session-test")')
  const copy = await popupPromise
  await copy.clock.install({ time: now })
  await copy.waitForFunction('window.ready')
  expect(await copy.evaluate('window.auth.hasAccessToken()')).toBe(true)
  now += 61_000
  await page.clock.setFixedTime(now)
  await copy.clock.setFixedTime(now)
  await copy.bringToFront()
  await copy.locator('#activity').click()
  await expect.poll(() => renewals).toBe(1)
  await expect.poll(() => page.evaluate('sessionStorage.getItem("sagomungchi:student-access")')).toBe(token('same'))
  await copy.locator('#activity').click()
  expect(renewals).toBe(1)

  const closingPromise = copy.waitForEvent('popup')
  await copy.evaluate('window.open("/session-test")')
  const closing = await closingPromise
  await closing.waitForFunction('window.ready')
  await closing.close()
  expect(await copy.evaluate('window.auth.apiFetch("/me")')).toEqual({ ok: true })
  expect(revoked.has('same')).toBe(false)

  // A different student's tab must not be logged out by this session's explicit logout.
  const other = await context.newPage()
  await other.goto('/session-test'); await other.waitForFunction('window.ready')
  await other.evaluate(t => { sessionStorage.setItem('sagomungchi:student-access', t) }, token('other'))
  await other.reload(); await other.waitForFunction('window.ready')
  await copy.evaluate('window.auth.apiFetch("/auth/student/logout", {method:"POST"}).then(() => { window.auth.notifyStudentLogout(); window.auth.setAccessToken(null) })')
  await expect.poll(() => page.evaluate('window.auth.hasAccessToken()')).toBe(false)
  expect(await other.evaluate('window.auth.hasAccessToken()')).toBe(true)

  // Inactivity is enforced on the next request.
  await copy.close()
  now += 121_000
  await other.clock.install({ time: now })
  expect(await other.evaluate('window.auth.apiFetch("/me").catch(e => e.problem.code)')).toBe('STUDENT_REAUTH_REQUIRED')
  expect(await other.evaluate('window.auth.hasAccessToken()')).toBe(false)
  expect(renewals).toBe(1)
})
