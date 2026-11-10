import { test, expect } from '@playwright/test'
import type { BrowserContext } from '@playwright/test'

// 실제 Google 인증은 대체하지 않는다. 운영 웹에서 콜백 HTML 계약과 새 탭 자동 복귀를 검사한다.
async function reauthServer(context: BrowserContext) {
  const child = { id: '00000000-0000-4000-8000-000000000001', nickname: '합성 자녀', grade: 3, birthYear: 2017, pinSet: false, pinLocked: false }
  const challengeId = '00000000-0000-4000-8000-000000000425'
  let release!: () => void
  const verified = new Promise<void>(resolve => { release = resolve })
  const state = { starts: [] as Record<string, unknown>[], finishes: 0, release, writes: [] as { path: string; body: unknown; proof: string | undefined }[] }
  await context.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
  await context.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname.replace('/api/v1', '')
    const json = (body: unknown, status = 200) => route.fulfill({ status, json: body })
    if (path === '/auth/refresh') return json({ accessToken: 'synthetic-parent', expiresIn: 900, role: 'PARENT', nextAction: 'READY', startPath: '/parent/devices' })
    if (path === '/me') return json({ userId: 'synthetic-parent', name: '합성 보호자', email: 'parent@example.test', role: 'PARENT', permissions: [], nextAction: 'READY', startPath: '/parent/devices', child: null })
    if (path === '/children') return json({ items: [child] })
    if (path === '/notifications' || path === '/student-devices') return json({ items: [], page: 0, size: 20, hasNext: false })
    if (path === '/me/reauth') {
      const body = request.postDataJSON()
      if (body.challengeId) {
        expect(body).toEqual({ challengeId }); state.finishes++
        return json({ reauthToken: 'synthetic-proof', expiresAt: new Date(Date.now() + 300_000).toISOString() })
      }
      state.starts.push(body)
      return json({ challengeId, authorizationUrl: '/api/v1/auth/google/reauth/callback', expiresAt: new Date(Date.now() + 600_000).toISOString() })
    }
    if (path === '/auth/google/reauth/callback') {
      await verified
      return route.fulfill({ contentType: 'text/html', headers: { 'cache-control': 'no-store' }, body: `<!doctype html><html lang="ko"><body><p>합성 재인증 완료</p><script>const channel = new BroadcastChannel('sagomungchi-reauth'); channel.postMessage({type:'REAUTH_VERIFIED',challengeId:'${challengeId}'}); channel.close(); setTimeout(() => window.close(), 300)</script></body></html>` })
    }
    if (path === '/me/guardian-password' || path.endsWith('/pin')) {
      if (request.method() === 'PUT') state.writes.push({ path, body: request.postDataJSON(), proof: request.headers()['x-reauth-token'] })
      return json({ set: state.writes.length > 0, locked: false })
    }
    if (path.endsWith('/deletion-impact')) return json({ childId: child.id, actions: [], retainedTransactionsYears: 5, deviceCleanupPending: false })
    if (path === '/notifications/stream') return route.abort('failed')
    return json({ code: 'NOT_FOUND' }, 404)
  })
  return state
}

for (const guardian of [true, false]) {
  test(`${guardian ? '보호자 비밀번호' : '자녀 PIN'}: 새 탭 확인 후 입력을 보존하고 자동으로 저장 가능해진다`, async ({ page, context }) => {
    const state = await reauthServer(context)
    await page.goto('/parent/devices')
    const form = page.getByRole('form', { name: guardian ? '보호자 비밀번호 설정' : '합성 자녀 PIN', exact: true })
    const inputs = form.locator('input[type="password"]')
    await inputs.nth(0).fill('5090'); await inputs.nth(1).fill('5090')
    const save = form.getByRole('button', { name: guardian ? '보호자 비밀번호 정하기' : 'PIN 정하기', exact: true })
    await expect(save).toBeDisabled()
    const opened = page.waitForEvent('popup')
    await form.getByRole('button', { name: guardian ? '보호자 비밀번호 Google 본인 확인' : '합성 자녀 Google 본인 확인', exact: true }).click()
    const popup = await opened
    await expect(form.getByRole('status')).toContainText('자동으로 완료')
    state.release()
    await expect(save).toBeEnabled()
    await expect.poll(() => popup.isClosed()).toBe(true)
    await expect(inputs.nth(0)).toHaveValue('5090')
    await expect(inputs.nth(1)).toHaveValue('5090')
    expect(state.finishes).toBe(1)
    expect(state.starts).toEqual([guardian ? { purpose: 'GUARDIAN_PASSWORD' } : { purpose: 'PIN_CHANGE', childId: '00000000-0000-4000-8000-000000000001' }])
    await save.click()
    await expect.poll(() => state.writes.length).toBe(1)
    expect(state.writes[0].proof).toBe('synthetic-proof')
    expect(state.writes[0].body).toEqual(guardian ? { password: '5090' } : { pin: '5090' })
  })
}

test('계정 관리 공통 Google 재확인도 원래 탭에서 자동 완료하고 작업은 실행하지 않는다', async ({ page, context }) => {
  const state = await reauthServer(context)
  await page.goto('/parent/settings?section=account')
  const opened = page.waitForEvent('popup')
  await page.getByRole('button', { name: 'Google 본인 확인', exact: true }).click()
  const popup = await opened
  await expect(page.getByRole('status').filter({ hasText: '자동으로 완료' })).toBeVisible()
  state.release()
  await expect(page.getByRole('status').filter({ hasText: '재확인을 마쳤습니다.' })).toBeVisible()
  await expect.poll(() => popup.isClosed()).toBe(true)
  expect(state.starts).toEqual([{ purpose: 'CHILD_UNLINK', childId: '00000000-0000-4000-8000-000000000001' }])
  expect(state.finishes).toBe(1)
  expect(state.writes).toEqual([])
  await expect(page.getByRole('button', { name: '선택한 작업 요청', exact: true })).toBeDisabled()
})
