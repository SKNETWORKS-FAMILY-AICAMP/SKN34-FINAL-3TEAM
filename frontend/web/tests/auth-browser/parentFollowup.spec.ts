import { test, expect } from '@playwright/test'

test('Google signup link retains readable contrast and keyboard focus', async ({ page }, info) => {
  await page.route('**/api/v1/**', route => route.fulfill({ status: 401, json: { code: 'UNAUTHORIZED', title: '로그인이 필요합니다.', status: 401 } }))
  await page.goto('/signup')
  const link = page.getByRole('link', { name: 'Google 계정으로 계속하기', exact: true })
  await expect(link).toBeVisible()
  for (const state of ['default', 'hover', 'focus']) {
    if (state === 'hover') await link.hover()
    if (state === 'focus') await link.focus()
    const contrast = await link.evaluate(element => {
      const style = getComputedStyle(element)
      const luminance = (color: string) => {
        const rgb = color.match(/[\d.]+/g)!.slice(0, 3).map(Number).map(v => { const c = v / 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4 })
        return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722
      }
      const a = luminance(style.color), b = luminance(style.backgroundColor)
      return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
    })
    expect(contrast, state).toBeGreaterThanOrEqual(4.5)
  }
  await expect(link).toBeFocused()
  await page.screenshot({ path: info.outputPath('27-04-google-signup.png') })
})
