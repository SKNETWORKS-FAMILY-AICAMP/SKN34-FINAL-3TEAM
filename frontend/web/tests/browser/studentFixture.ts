import { expect } from '@playwright/test'
import type { Page } from '@playwright/test'

/** Set up the retained guardian-session API for tests of consent/return behaviour.
 * #548 removes its UI entry; this helper does not claim a visible navigation path.
 */
export async function enterStudentFixture(page: Page) {
  await page.evaluate(async () => {
    const gatewayPath = '/src/data/classroom/apiGateway.ts'
    const parentPath = '/src/data/parent/api.ts'
    const { createApiGateway } = await import(gatewayPath)
    const { parentApi } = await import(parentPath)
    const children = (await parentApi.children()).items
    const selected = new URLSearchParams(location.search).get('childId')
    const child = children.find((value: { id: string }) => value.id === selected) ?? children[0]
    if (!child) throw new Error('Student fixture requires a linked child')
    await createApiGateway().enterStudent(child)
    window.dispatchEvent(new Event('sagomungchi:session-changed'))
  })
  await waitForStudentHome(page)
}

/**
 * 학생 진입 뒤 홈이 그려질 때까지 기다린다(테마 응답을 받은 뒤 홈 제목이 그려짐). 시작 이야기(/student/theme/intro)는
 * 홈에서 자동으로 뜨지 않고 그 주 처음 문제를 열 때 나온다(#440, user-flow 사용자 결정 2026-11-13·14).
 */
export async function waitForStudentHome(page: Page) {
  await expect(page).toHaveURL(/\/student\/home/)
  // 홈 제목은 이번 주 테마 조회 뒤에 그려진다. 여러 시험이 함께 돌 때 5초가 모자란 적이 있어 10초(2026-11-16)
  await expect(page.locator('.sh-title')).toBeVisible({ timeout: 10_000 })
}
