import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

// #728 표현 검토 라벨링 화면 (FN-ADM-24): 글만 보이고, 라벨 전/완료, 빈 목록·실패·권한 없음 구분
async function open(page: Page, email = 'ops@example.test') {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
  await page.goto('/admin/login')
  await page.getByLabel('로그인 ID', { exact: true }).fill(email)
  await page.getByRole('button', { name: '로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/admin\/home/)
  await expect(page.getByRole('heading', { name: '운영 요약', exact: true })).toBeVisible()
  const menuToggle = page.getByRole('button', { name: '메뉴', exact: true })
  if (await menuToggle.isVisible()) await menuToggle.click()
  const nav = page.getByRole('navigation', { name: '관리자 메뉴' })
  const design = nav.getByText('설계안', { exact: true })
  const link = nav.getByRole('link', { name: '표현 검토', exact: true })
  if (email === 'content@example.test') {
    await expect(design).toHaveCount(0)
    await expect(link).toHaveCount(0)
    await page.goto('/admin/expressions?tab=labels')
  } else {
    await expect(design).toBeVisible()
    await expect(link).toHaveCount(1)
    await link.click()
  }
}
async function scenario(page: Page, value: string) {
  await page.locator('.ad-demo-tools > summary').click()
  await page.getByRole('combobox', { name: '상태 시연', exact: true }).selectOption(value)
  await page.locator('.ad-demo-tools > summary').click()
}

test('라벨 전 글을 읽고 라벨을 붙이면 라벨 완료로 옮겨 간다 @responsive', async ({ page }) => {
  await open(page)
  await expect(page.getByRole('heading', { name: '표현 검토', level: 1, exact: true })).toBeVisible()
  const tabs = page.getByRole('navigation', { name: '표현 검토 보기' })
  const pending = page.getByRole('table', { name: '검토 대기', exact: true })
  const entries = pending.getByRole('button', { name: /상세 보기$/ })
  await expect(entries).toHaveCount(2)
  await expect(entries.first()).toHaveAccessibleName(/친구가 너무 답답하게 굴어서/)
  await expect(pending.getByRole('columnheader', { name: /학생|ID/i })).toHaveCount(0)
  await entries.nth(1).click()
  const dialog = page.getByRole('dialog')
  const multiline = dialog.getByRole('definition').filter({ hasText: '개발용 합성 공유물' })
  await expect(multiline).toBeVisible()
  expect(await multiline.textContent()).toBe('개발용 합성 공유물\n두 번째 줄')
  await expect(page).toHaveURL(/reviewId=00000000-0000-4000-8000-000007280002/)
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(entries.nth(1)).toBeFocused()
  await entries.first().click()
  await expect(dialog).toContainText('친구가 너무 답답하게 굴어서')
  await dialog.getByRole('button', { name: '막을 글', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: /저장했습니다/ })).toBeVisible()
  await expect(dialog).toHaveCount(0)
  await expect(entries).toHaveCount(1)
  await tabs.getByRole('link', { name: '라벨 이력', exact: true }).click()
  await expect(page).toHaveURL(/tab=labels/)
  const labeled = page.getByRole('table', { name: '라벨 이력', exact: true })
  const reviewed = labeled.getByRole('button', { name: /상세 보기$/ })
  await expect(reviewed).toHaveCount(2)
  await expect(reviewed.first()).toHaveAccessibleName(/친구가 너무 답답하게 굴어서/)
  await page.getByRole('combobox', { name: '상태 필터' }).selectOption('OFFENSIVE')
  await expect(reviewed).toHaveCount(1)
  await reviewed.first().click()
  await expect(dialog.getByRole('button', { name: '막을 글', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await dialog.getByRole('button', { name: '건너뜀', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await expect(page.getByText('조건에 맞는 기록이 없습니다.', { exact: true })).toBeVisible()
  await page.getByRole('combobox', { name: '상태 필터' }).selectOption('SKIP')
  await expect(reviewed).toHaveCount(1)
  await expect(labeled).toContainText('건너뜀')
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})

test('감사 이력은 대상 유형 "표현 검토"로 열람·라벨만 걸러 본다 (#907) @responsive', async ({ page }) => {
  await open(page)
  await page.getByRole('table', { name: '검토 대기' }).getByRole('button', { name: /상세 보기$/ }).first().click()
  await page.getByRole('dialog').getByRole('button', { name: '막을 글', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: '저장했습니다.' })).toBeVisible()
  await page.evaluate(async () => { // 걸러져야 하는 다른 유형
    const path = '/src/mocks/fixtures/admin/operations.ts'
    const { audits } = await import(path)
    audits.push({ id: 'test-audit-other', actorUserId: 'test-ops', action: 'MISSION_PUBLISH', targetType: 'MISSION',
      targetId: 'mission-1', result: 'SUCCESS', createdAt: new Date().toISOString() })
    history.pushState({}, '', '/admin/audit') // 새로 열면 목업 기록이 지워져 화면 안에서 이동
    dispatchEvent(new PopStateEvent('popstate'))
  })
  const rows = page.locator('.ad-audit-ledger tbody tr')
  await expect(rows.filter({ hasText: '미션 게시' }).first()).toBeVisible()
  await page.getByRole('combobox', { name: '감사 대상 유형', exact: true }).selectOption({ label: '표현 검토' })
  await expect(rows.filter({ hasText: '미션 게시' })).toHaveCount(0)
  await expect(rows.filter({ hasText: '표현 검토 목록 열람' }).first()).toBeVisible()
  await expect(rows.filter({ hasText: '표현 검토 라벨' })).toHaveCount(1)
  await expect(rows.filter({ hasNotText: '표현 검토' })).toHaveCount(0)
})

test('출처와 검색을 함께 적용하고 검색 조건을 지우면 대기 목록으로 돌아온다 @responsive', async ({ page }) => {
  await open(page)
  const source = page.getByRole('combobox', { name: '출처', exact: true })
  await source.selectOption('COMMUNITY_REPORT')
  const pending = page.getByRole('table', { name: '검토 대기', exact: true })
  const records = pending.getByRole('button', { name: /상세 보기$/ })
  await expect(records).toHaveCount(1)
  await expect(pending).toContainText('신고 숨김 공유물')
  const search = page.getByRole('searchbox', { name: '목록 검색' })
  await search.fill('두 번째')
  await expect(records).toHaveCount(1)
  await search.fill('찾을 수 없는 글')
  await expect(page.getByText('조건에 맞는 기록이 없습니다.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '검색 조건 지우기' }).click()
  await expect(search).toHaveValue('')
  await expect(source).toHaveValue('')
  await expect(records).toHaveCount(2)
})

test('현재 페이지 검색 결과가 없어도 다음 쪽에서 일치하는 글을 열 수 있다 @responsive', async ({ page }) => {
  await open(page)
  await page.evaluate(async () => {
    const path = '/src/mocks/fixtures/admin/operations.ts'
    const { expressionReviews } = await import(path)
    for (let day = 1; day <= 21; day++) {
      expressionReviews.push({
        id: '00000000-0000-4000-8000-' + String(day).padStart(12, '0'), source: 'GRAY_ZONE', text: day === 21 ? '다음 쪽의 검색어' : '페이지 자료 ' + day,
        modelVersion: null, label: null, labeledAt: null, createdAt: '2026-12-' + String(day).padStart(2, '0') + 'T00:00:00Z',
      })
    }
  })
  await page.getByRole('combobox', { name: '출처', exact: true }).selectOption('GRAY_ZONE')
  await expect(page.getByText('현재 페이지에서 검색과 상태 필터를 적용합니다.')).toBeVisible()
  await page.getByRole('searchbox', { name: '목록 검색' }).fill('다음 쪽의 검색어')
  await expect(page.getByText('조건에 맞는 기록이 없습니다.')).toBeVisible()
  const pager = page.getByRole('navigation', { name: '표현 검토 쪽' })
  await pager.getByRole('button', { name: '다음' }).click()
  await expect(pager).toContainText('2 / 2')
  await page.getByRole('button', { name: '다음 쪽의 검색어 상세 보기' }).click()
  await expect(page.getByRole('dialog')).toContainText('다음 쪽의 검색어')
  await page.goBack()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(pager).toContainText('2 / 2')
})

test('빈 목록·조회 실패·권한 없음을 구분한다 @responsive', async ({ page }) => {
  await open(page)
  await scenario(page, 'empty')
  await expect(page.getByText('검토할 글이 없습니다.', { exact: true })).toBeVisible()
  await scenario(page, 'query-fail')
  await expect(page.getByRole('alert')).toContainText('관리자 조회에 실패했습니다.')
  await expect(page.getByText('검토할 글이 없습니다.', { exact: true })).toHaveCount(0)
  await scenario(page, 'forbidden')
  await expect(page.getByRole('alert')).toContainText('권한')
  await expect(page.getByRole('region', { name: '표현 검토' }).getByRole('button', { name: /상세 보기$/ })).toHaveCount(0)
})

test('서비스 운영 권한이 없으면 메뉴에 없고 주소로 들어가도 막힌다 @responsive', async ({ page }) => {
  await open(page, 'content@example.test')
  await expect(page.getByText('FORBIDDEN · 필요한 관리자 권한이 없습니다.')).toBeVisible()
  await expect(page.getByRole('navigation', { name: '관리자 메뉴' }).getByRole('link', { name: '표현 검토', exact: true })).toHaveCount(0)
  await expect(page.getByRole('region', { name: '표현 검토' })).toHaveCount(0)
})
