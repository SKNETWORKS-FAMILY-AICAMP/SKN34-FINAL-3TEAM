import { expect, test } from '@playwright/test'
import { newParent, useGoogleIdentity } from './support/google.ts'
import { onboardParent } from './support/onboarding.ts'
import { loginStudent, nextTourLine, studentTour } from './support/student.ts'

// #1038 학생 화면 둘러보기(실서버 core #1035 `/students/me/onboarding`): 새 학생은 첫 로그인 홈에서 둘러보기가 자동으로 뜨고,
// 끝까지 보면 완료를 기록해 다시 로그인해도 뜨지 않는다. 도움말 "화면 둘러보기 다시 하기"는 기록을 그대로 두고 1번부터 다시
test('첫 로그인 둘러보기 끝까지 → 재로그인 미표시 → 도움말에서 다시 하기', async ({ browser, context, page: parentPage }) => {
  const nickname = `둘러보기${Date.now().toString(36)}`
  await useGoogleIdentity(context, newParent('tour'))
  await onboardParent(parentPage, nickname)
  const { context: studentContext, page } = await loginStudent(browser, parentPage, nickname, '둘러보기 E2E', { keepTour: true })
  try {
    const tour = studentTour(page)
    await expect(tour).toBeVisible()
    const pages = ['home', 'home', 'home', 'journal', 'activities', 'community', 'room', 'home']
    const saved = page.waitForResponse(r => r.request().method() === 'PUT' && new URL(r.url()).pathname.endsWith('/students/me/onboarding'))
    for (const [i, name] of pages.entries()) {
      await expect(page).toHaveURL(new RegExp(`/student/${name}\\?tour=${i + 1}$`))
      await nextTourLine(page, i + 1)
    }
    await expect(tour).toBeHidden()
    await expect(page).toHaveURL(/\/student\/home$/)
    const response = await saved
    expect(response.status()).toBe(200)
    const first = (await response.json()).completedAt
    expect(typeof first).toBe('string')

    // 다시 로그인(학생 토큰은 메모리에만 있어 새로 고침하면 PIN으로 다시 들어온다)
    await page.reload()
    await expect(async () => {
      if (page.url().includes('/student/home')) return
      const pad = page.getByRole('button', { name: '4', exact: true })
      if (await pad.isVisible()) {
        for (const digit of ['4', '8', '3', '1']) await page.getByRole('button', { name: digit, exact: true }).click()
        await page.getByRole('button', { name: /확인|들어가기/ }).click()
      }
      expect(page.url()).toContain('/student/home')
    }).toPass({ timeout: 30_000, intervals: [500] })
    await expect(page.locator('[data-tour-home]')).toHaveAttribute('data-tour-home', 'none')
    await expect(tour).toHaveCount(0)

    // 도움말에서 다시 하기: 1번부터, 닫아도 서버 기록은 그대로
    const puts: string[] = []
    page.on('request', r => { if (r.method() === 'PUT' && new URL(r.url()).pathname.endsWith('/students/me/onboarding')) puts.push(r.url()) })
    await page.locator('.st-support-menu summary').click()
    await page.getByRole('link', { name: '이용 도움말', exact: true }).click()
    await page.getByRole('link', { name: '화면 둘러보기 다시 하기', exact: true }).click()
    await expect(page).toHaveURL(/\/student\/home\?tour=1$/)
    await expect(tour).toBeVisible()
    await tour.getByRole('button', { name: '그만 볼래', exact: true }).click()
    await expect(tour).toBeHidden()
    expect(puts).toEqual([])
    const kept = await page.evaluate(async () => {
      const { onboardingApi } = await import('/src/data/onboarding/api.ts' as string)
      return (await onboardingApi.get('STUDENT')).completedAt
    })
    expect(kept).toBe(first)
  } finally {
    await studentContext.close()
  }
})
