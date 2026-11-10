import { test, expect } from '@playwright/test'
import type { BrowserContext, Page } from '@playwright/test'

async function authServer(context: BrowserContext) {
  const expires = Math.floor(Date.now() / 1000) + 7 * 86400
  const state = { rotation: 0, callbacks: 0, rejectedCookies: 0, refreshFailure: '' as '' | 'network' | 'server',
    expired: false, invalidSession: false, name: '합성 보호자', writes: [] as unknown[] }
  const origin = 'http://127.0.0.1:5279'
  const cookie = () => `sagomungchi_refresh=refresh-${state.rotation}; Path=/api/v1/auth; HttpOnly; SameSite=Strict; Expires=${new Date(expires * 1000).toUTCString()}`
  await context.addCookies([{ name: 'sagomungchi_refresh', value: 'refresh-0', domain: '127.0.0.1', path: '/api/v1/auth', httpOnly: true, sameSite: 'Strict', expires }])
  await context.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
  await context.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname.replace('/api/v1', '')
    const json = (body: unknown, status = 200) => route.fulfill({ status, json: body })
    if (path === '/auth/google/callback') {
      state.callbacks++
      return route.fulfill({ status: 302, headers: { location: origin + '/oauth/complete', 'set-cookie': cookie() } })
    }
    if (path === '/auth/refresh') {
      expect(request.method()).toBe('POST')
      expect(request.headers()['x-requested-with']).toBe('XMLHttpRequest')
      if (state.refreshFailure) {
        const failure = state.refreshFailure; state.refreshFailure = ''
        return failure === 'network' ? route.abort('failed') : json({ code: 'AUTH_UNAVAILABLE' }, 503)
      }
      if (state.invalidSession) return json({ code: 'UNAUTHENTICATED' }, 401)
      if (!request.headers().cookie?.split('; ').includes(`sagomungchi_refresh=refresh-${state.rotation}`)) {
        state.rejectedCookies++; return json({ code: 'REFRESH_REUSED' }, 401)
      }
      state.rotation++; state.expired = false
      // 동시 탭 요청에서 쿠키 회전이 끝나기 전에 다음 요청이 발송되는지 확인한다.
      await new Promise(resolve => setTimeout(resolve, 75))
      return route.fulfill({ json: { accessToken: `access-${state.rotation}`, expiresIn: 900, role: 'PARENT', nextAction: 'READY', startPath: '/parent/settings' },
        headers: { 'set-cookie': cookie(), 'cache-control': 'no-store' } })
    }
    if (path === '/notifications/stream') return route.abort('failed')
    if (state.expired || !request.headers().authorization?.startsWith('Bearer access-')) return json({ code: 'TOKEN_EXPIRED' }, 401)
    if (path === '/me') {
      if (request.method() === 'PATCH') { state.writes.push(request.postDataJSON()); state.name = request.postDataJSON().name }
      return json({ userId: 'synthetic-parent', name: state.name, email: 'parent@example.test', role: 'PARENT', permissions: [], nextAction: 'READY', startPath: '/parent/settings', child: null })
    }
    if (path === '/children') return json({ items: [] })
    if (path === '/notifications') return json({ items: [], page: 0, size: 20, hasNext: false })
    return json({ code: 'NOT_FOUND' }, 404)
  })
  return state
}

async function profile(page: Page) {
  await expect(page).toHaveURL(/\/parent\/settings/)
  await expect(page.getByRole('heading', { name: '본인 정보', exact: true })).toBeVisible()
}

test('Google 복귀는 한 번 확인하고 15분 접근 토큰 갱신·새로고침 뒤에도 로그인한다', async ({ page, context }) => {
  const state = await authServer(context)
  await page.goto('/api/v1/auth/google/callback?code=synthetic-one-use&state=synthetic')
  await profile(page)
  expect(state.rotation).toBe(1)
  expect(state.callbacks).toBe(1)
  state.expired = true
  await page.getByRole('textbox', { name: '새 이름', exact: true }).fill('계속 로그인한 보호자')
  await page.getByRole('button', { name: '이름 저장', exact: true }).click()
  await expect(page.getByText('본인 정보를 저장했습니다.', { exact: true })).toBeVisible()
  expect(state.writes).toEqual([{ name: '계속 로그인한 보호자' }])
  expect(state.rotation).toBe(2)
  await page.reload(); await profile(page)
  await expect(page.getByText('현재 이름: 계속 로그인한 보호자')).toBeVisible()
  expect(state.rotation).toBe(3)
  expect(state.callbacks).toBe(1)
  const cookies = await context.cookies()
  expect(cookies.find(cookie => cookie.name === 'sagomungchi_refresh')?.httpOnly).toBe(true)
  expect(await page.evaluate(() => [localStorage, sessionStorage].flatMap(store => Object.values(store)).some(value => /refresh-\d|access-\d/.test(value)))).toBe(false)
})

test('갱신 연결 장애는 입력과 로그인 화면을 유지하고 같은 동작을 다시 시도한다', async ({ page, context }) => {
  const state = await authServer(context)
  await page.goto('/parent/settings'); await profile(page)
  state.expired = true; state.refreshFailure = 'network'
  await page.getByRole('textbox', { name: '새 이름', exact: true }).fill('복구 후 보호자')
  await page.getByRole('button', { name: '이름 저장', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: '로그인 상태를 확인하지 못했습니다.' })).toBeVisible()
  await profile(page)
  await expect(page.getByRole('textbox', { name: '새 이름', exact: true })).toHaveValue('복구 후 보호자')
  expect(state.writes).toEqual([])
  await page.getByRole('button', { name: '이름 저장', exact: true }).click()
  await expect(page.getByText('본인 정보를 저장했습니다.', { exact: true })).toBeVisible()
  expect(state.writes).toEqual([{ name: '복구 후 보호자' }])
  expect(state.rotation).toBe(2)
})

test('Google 콜백 후 일시적인 서버 오류는 코드를 재사용하지 않고 원래 화면에서 복구한다', async ({ page, context }) => {
  const state = await authServer(context)
  state.refreshFailure = 'server'
  await page.goto('/api/v1/auth/google/callback?code=synthetic-one-use&state=synthetic')
  await expect(page.getByRole('button', { name: '로그인 상태 다시 확인', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '로그인 상태 다시 확인', exact: true }).click()
  await profile(page)
  expect(state.callbacks).toBe(1)
  expect(state.rotation).toBe(1)
})

test('동시 새 탭은 쿠키 회전을 직렬화하고 실제 세션 만료 때만 로그인으로 이동한다', async ({ page, context }) => {
  const state = await authServer(context), other = await context.newPage()
  await Promise.all([page.goto('/parent/settings'), other.goto('/parent/settings')])
  await Promise.all([profile(page), profile(other)])
  expect(state.rotation).toBe(2)
  expect(state.rejectedCookies).toBe(0)
  state.invalidSession = true
  await page.reload()
  await expect(page).toHaveURL(/\/login$/)
})
