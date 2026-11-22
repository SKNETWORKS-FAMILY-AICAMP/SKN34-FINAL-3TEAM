import { test, expect } from '@playwright/test'

test('초안 채택 후 학년·적용 주를 고정하고 작성 중인 테마 내용은 저장한다', async ({ page }) => {
  await page.goto('/admin/login')
  await page.getByLabel('로그인 ID', { exact: true }).fill('content@example.test')
  await page.getByLabel('비밀번호', { exact: true }).fill('demo-only')
  await page.getByRole('button', { name: '로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/admin\/home/)
  await page.goto('/admin/theme-drafts?grade=G4&source=AUTO')
  await page.getByRole('button', { name: /초안 열기/ }).first().click()
  await page.getByRole('button', { name: '채택해서 테마 만들기' }).click()
  await page.getByRole('dialog').getByRole('button', { name: '채택', exact: true }).click()
  const schedule = page.getByRole('group', { name: '채택 시 확정된 편성' })
  await expect(schedule).toContainText('초4 · 적용 주')
  await expect(page.getByLabel('학년', { exact: true })).toHaveCount(0)
  await expect(page.getByLabel('주 시작일', { exact: true })).toHaveCount(0)
  await page.getByLabel('테마 제목').fill('검수 후 수정한 제목')
  await page.getByRole('button', { name: '테마 저장' }).click()
  await expect(page.getByText('테마를 저장했습니다.', { exact: true })).toBeVisible()

  const errors = await page.evaluate(async () => {
    const { adminRetentionApi: api }: typeof import('../../src/data/admin/retentionApi.ts') = await import('/src/data/admin/retentionApi.ts' as string)
    const id = new URL(location.href).searchParams.get('themeId')!
    const theme = await api.theme(id)
    const later = new Date(theme.weekStart + 'T00:00:00Z')
    later.setUTCDate(later.getUTCDate() + 7)
    const problems = []
    for (const change of [{ grade: 'G5' as const }, { weekStart: later.toISOString().slice(0, 10) }]) {
      try {
        await api.saveTheme(id, { ...theme, ...change })
        problems.push(null)
      } catch (err) {
        const { status, code } = (err as import('../../src/data/apiClient.ts').ApiError).problem
        problems.push({ status, code })
      }
    }
    return problems
  })
  expect(errors).toEqual(Array(2).fill({ status: 409, code: 'THEME_SCHEDULE_LOCKED' }))
  await page.reload()
  await expect(schedule).toContainText('초4 · 적용 주')
  await expect(page.getByLabel('테마 제목')).toHaveValue('검수 후 수정한 제목')
})

test('#882 같은 검수 화면에서 부분 생성한 세 장면 비교, 미션 연결과 선택 저장', async ({ page }) => {
  test.setTimeout(60_000)
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
  await page.goto('/admin/login')
  await page.getByLabel('로그인 ID', { exact:true }).fill('content@example.test')
  await page.getByLabel('비밀번호', { exact:true }).fill('demo-only')
  await page.getByRole('button',{name:'로그인',exact:true}).click()
  await expect(page).toHaveURL(/\/admin\/home/)
  await page.goto('/admin/theme-drafts?grade=G4&source=AUTO')
  await page.getByRole('button',{name:/초안 열기/}).first().click()
  const root = new URL(page.url()).searchParams.get('draftId')
  await page.getByRole('button',{name:'월요일',exact:true}).click()
  const rows = page.locator('.tw-history-list li')
  await expect(rows).toHaveCount(1)
  for(const count of [2,3]){
    await page.getByRole('button',{name:'월요일 미션 다시 만들기'}).click()
    await page.getByRole('dialog').getByRole('button',{name:'다시 만들기',exact:true}).click()
    await expect(rows).toHaveCount(count,{timeout:15_000})
    expect(new URL(page.url()).searchParams.get('draftId')).toBe(root)
  }
  await page.getByRole('button',{name:'두 버전 비교'}).click()
  await page.getByRole('combobox',{name:'왼쪽 비교본'}).selectOption({label:'재생성본 v2'})
  await page.getByRole('combobox',{name:'오른쪽 비교본'}).selectOption({label:'재생성본 v3'})
  const media=page.locator('.tw-pair .tm-stage img')
  await expect(media).toHaveCount(2)
  expect(await media.first().getAttribute('src')).not.toBe(await media.last().getAttribute('src'))
  await expect(page.locator('.tw-pinned')).toContainText('최초 생성본')
  await page.getByRole('button',{name:'오른쪽 버전 선택'}).click()
  await expect(page.locator('.tw-pinned')).toContainText('재생성본 v3')
  await page.reload()
  await page.getByRole('button',{name:'이 요일 미션 보기'}).click()
  await expect(page.getByRole('dialog')).toContainText('다시 만듦 2')
  await page.getByRole('button',{name:'월요일 장면 보기'}).click()
  await expect(page.locator('.tw-single')).toContainText('재생성본 v3')
})
