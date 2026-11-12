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
  await expect(page).toHaveURL(/\/student\/home/)
}
