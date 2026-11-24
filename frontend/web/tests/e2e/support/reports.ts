import { expect, type Page } from '@playwright/test'

export async function openCompletedReport(page: Page, kind: '일일' | '주간', dateLabel: string) {
  const period = page.locator('.report-period-picker > summary')
  await expect(async () => {
    await page.reload()
    await period.click({ timeout: 5_000 })
    await page.getByRole('button', { name: kind, exact: true }).click()
    await page.getByRole('list', { name: '리포트 일자' }).getByRole('button', { name: dateLabel, exact: true }).click({ timeout: 5_000 })
  }).toPass({ timeout: 180_000, intervals: [3_000] })
  await expect(period).toHaveText(`${kind} 리포트`)
  await expect(page.locator('.report-period-heading > p')).toHaveText(dateLabel)
}
