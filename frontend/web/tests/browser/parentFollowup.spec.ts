import { test, expect, type Page } from '@playwright/test'

async function login(page: Page) {
  await page.goto('/login')
  await page.getByRole('button', { name: '시연 계정으로 로그인', exact: true }).click()
  await expect(page.getByRole('combobox', { name: '현재 자녀 선택' })).toBeVisible()
}

test('withdrawal cancellation sends nothing; failure stays open and one retry saves', async ({ page }) => {
  await page.addInitScript(() => {
    const original = window.fetch.bind(window)
    let calls = 0
    window.fetch = (input, init) => {
      const path = new URL(input instanceof Request ? input.url : String(input), location.href).pathname
      if (path.endsWith('/withdrawal')) {
        calls++
        if (calls === 1) return Promise.resolve(Response.json({ status: 503, title: '철회 저장에 실패했습니다.', code: 'RETRY_SYNTHETIC' }, { status: 503 }))
      }
      return original(input, init)
    }
    window.addEventListener('audit-withdrawal', () => document.documentElement.dataset.withdrawalCalls = String(calls))
  })
  await login(page)
  await page.goto('/parent/settings?childId=demo-seoyun&section=sharing')
  const trigger = page.getByRole('button', { name: '법정대리인 동의 철회', exact: true })
  const dialog = page.getByRole('dialog', { name: '동의를 철회할까요?', exact: true })
  await trigger.click()
  await expect(dialog.getByRole('button', { name: '취소하고 유지' })).toBeFocused()
  await dialog.getByRole('button', { name: '취소하고 유지' }).click()
  await trigger.click()
  await page.keyboard.press('Escape')
  await page.evaluate(() => dispatchEvent(new Event('audit-withdrawal')))
  await expect(page.locator('html')).toHaveAttribute('data-withdrawal-calls', '0')
  await trigger.click()
  await dialog.getByRole('button', { name: '동의 철회하기', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('철회 저장에 실패했습니다.')
  await expect(dialog).not.toContainText('RETRY_SYNTHETIC')
  await dialog.getByRole('button', { name: '동의 철회하기', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await expect(page.getByRole('heading', { name: '서윤 법정대리인 재동의' })).toBeVisible()
  await page.evaluate(() => dispatchEvent(new Event('audit-withdrawal')))
  await expect(page.locator('html')).toHaveAttribute('data-withdrawal-calls', '2')
  await page.getByRole('link', { name: '학습 현황', exact: true }).click()
  await expect(page.getByRole('region', { name: '법정대리인 재동의 안내' })).toBeVisible()
  await expect(page.getByRole('region', { name: '학습 요약' })).toHaveCount(0)
  await expect(page.getByRole('alert')).toHaveCount(1)
  await expect(page.locator('body')).not.toContainText('CHILD_NOT_LINKED')
})

test('current consent version is separate from old agreed and withdrawn history', async ({ page }, info) => {
  await page.addInitScript(() => {
    const original = window.fetch.bind(window)
    window.fetch = async (input, init) => {
      const path = new URL(input instanceof Request ? input.url : String(input), location.href).pathname
      const response = await original(input, init)
      if (!response.ok) return response
      if (path === '/api/v1/children') {
        const body = await response.json()
        return Response.json({ ...body, items: body.items.map((c: { id: string }) => c.id === 'demo-seoyun' ? { ...c, guardianConsentRequired: true } : c) })
      }
      if (path === '/api/v1/me/consents') {
        const body = await response.json()
        const items = body.items.map((entry: { studentId: string; document: { kind: string } }) => entry.studentId === 'demo-seoyun' && entry.document.kind === 'GUARDIAN'
          ? { ...entry, document: { ...entry.document, documentId: 'old-guardian', version: '1.1' } } : entry)
        const old = items.find((entry: { studentId: string }) => entry.studentId === 'demo-seoyun')
        return Response.json({ ...body, items: [...items, { ...old, consentId: 'withdrawn-guardian', status: 'WITHDRAWN', agreed: false, withdrawnAt: '2026-11-20T00:00:00Z', document: { ...old.document, documentId: 'older-guardian', version: '1.0' } }] })
      }
      return response
    }
  })
  await login(page)
  await page.goto('/parent/settings?childId=demo-seoyun&section=sharing')
  const current = page.getByRole('article').filter({ has: page.getByRole('heading', { name: '법정대리인 동의 v1.2', exact: true }) })
  await expect(current).toContainText('새 버전 동의 필요')
  await expect(current.getByRole('button', { name: /철회$/ })).toHaveCount(0)
  await page.getByText('전체 동의·철회 이력 (4건)', { exact: true }).click()
  const older = page.getByRole('article').filter({ has: page.getByRole('heading', { name: '법정대리인 동의 v1.1', exact: true }) })
  await expect(older).toContainText('이전 문서')
  await expect(older).toContainText('동의함')
  await expect(page.getByRole('article').filter({ has: page.getByRole('heading', { name: '법정대리인 동의 v1.0', exact: true }) })).toContainText('철회함')
  await current.scrollIntoViewIfNeeded()
  await page.screenshot({ path: info.outputPath('27-03-version-history.png') })
  await page.getByRole('link', { name: '법정대리인 재동의하기' }).click()
  await expect(page.locator('#guardian-consent')).toBeInViewport()
  await expect(page.locator('#guardian-consent')).toBeFocused()
})

for (const lockedCount of [0, 2]) test(`empty report and memory shelf distinguish ${lockedCount} older locked books @responsive`, async ({ page }, info) => {
  await page.addInitScript(locked => {
    const original = window.fetch.bind(window)
    window.fetch = async (input, init) => {
      const path = new URL(input instanceof Request ? input.url : String(input), location.href).pathname
      if (/\/children\/[^/]+\/reports$/.test(path)) return Response.json({ items: [] })
      if (path.endsWith('/memory-books/rounds')) return Response.json({ items: [], page: 0, size: 50, totalElements: 0, canCreate: false, lockedCount: locked })
      return original(input, init)
    }
  }, lockedCount)
  await login(page)
  await page.goto('/parent/journal?childId=demo-doyun')
  const guide = page.getByRole('dialog', { name: '학부모 첫 사용 안내' })
  if (await guide.isVisible()) await guide.getByRole('button', { name: '건너뛰기' }).click()
  const card = page.getByRole('region', { name: '최근 주간 리포트' })
  await expect(card).toContainText('다음 월요일부터')
  await card.getByRole('button', { name: '주간 리포트 예시 보기' }).click()
  await expect(page.getByRole('dialog', { name: '주간 리포트 예시', exact: true }).getByRole('note')).toContainText('실제 자녀 기록이나 AI 분석 결과가 아닙니다.')
  await page.keyboard.press('Escape')
  await page.goto('/parent/report?childId=demo-doyun')
  const shelf = page.getByRole('region', { name: '추억 그림책' })
  if (lockedCount) {
    await expect(shelf).toContainText('이전 회차의 액자 2개')
    await expect(shelf).not.toContainText('아직 받은 기념 액자가 없습니다.')
  } else {
    await expect(shelf.getByText('아직 받은 기념 액자가 없습니다. 한 주 테마 다섯 문제를 모두 마치면 생깁니다.', { exact: true })).toHaveCount(1)
    await expect(shelf).not.toContainText('최근 4주에는 새로 받은 액자가 없어요.')
  }
  await shelf.scrollIntoViewIfNeeded()
  await page.screenshot({ path: info.outputPath(`26-10-empty-${lockedCount}.png`) })
  await shelf.getByRole('link', { name: '프리미엄 혜택보기', exact: true }).click()
  await expect(page).toHaveURL(/childId=demo-doyun#plan-compare$/)
  await expect(page.locator('.premium-comparison')).toHaveAttribute('open', '')
})

test('refund pending never offers the free-plan upsell', async ({ page }) => {
  await page.addInitScript(() => {
    const original = window.fetch.bind(window)
    window.fetch = async (input, init) => {
      const path = new URL(input instanceof Request ? input.url : String(input), location.href).pathname
      const response = await original(input, init)
      if (response.ok && path.endsWith('/entitlement')) return Response.json({ ...await response.json(), refundPending: true, status: 'ACTIVE', conversationEnabled: false, narrativeEnabled: false })
      return response
    }
  })
  await login(page)
  await page.goto('/parent/report?childId=demo-doyun&view=chat')
  await expect(page.getByText(/환불 검토 중에는 기록에 물어보기/)).toBeVisible()
  await expect(page.getByRole('link', { name: /무료.*프리미엄/ })).toHaveCount(0)
  await page.goto('/parent/report?childId=demo-doyun')
  await expect(page.getByRole('note').filter({ hasText: '환불 검토 중에는' })).toBeVisible()
  await expect(page.locator('.report-premium-preview')).toHaveCount(0)
})
