import { expect, type Browser, type BrowserContext, type Page } from '@playwright/test'

/**
 * 학부모 화면에서 PIN을 정하고 등록 코드로 새 학생 기기를 등록한 뒤 PIN으로 들어간다(#548).
 * 학생 토큰은 메모리에만 있으므로 돌려받은 학생 화면에서는 page.goto·새로고침 없이 화면 안에서만 이동한다.
 */
export async function loginStudent(browser: Browser, parentPage: Page, nickname: string, deviceName = 'E2E 학생 기기'):
  Promise<{ context: BrowserContext; page: Page }> {
  await parentPage.getByRole('link', { name: '기기·PIN', exact: true }).click()
  const pin = parentPage.getByRole('form', { name: `${nickname} PIN`, exact: true })
  await pin.getByLabel(`${nickname} 새 PIN`, { exact: true }).fill('4831')
  await pin.getByLabel(`${nickname} 새 PIN 확인`, { exact: true }).fill('4831')
  await pin.getByRole('button', { name: 'PIN 정하기', exact: true }).click()
  await expect(pin.getByRole('status')).toContainText('PIN을 저장했습니다.')
  const pairing = parentPage.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith('/student-devices/pairings'))
  await parentPage.getByRole('button', { name: '등록 코드 만들기', exact: true }).click()
  const { pairingCode } = await (await pairing).json()
  const context = await browser.newContext({ baseURL: new URL(parentPage.url()).origin })
  const page = await context.newPage()
  await page.goto('/student/login?code=' + encodeURIComponent(pairingCode))
  await page.getByLabel('기기 이름', { exact: true }).fill(deviceName)
  await page.getByRole('button', { name: '이 기기 등록하기', exact: true }).click()
  for (const digit of ['4', '8', '3', '1']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: /확인|들어가기/ }).click()
  await page.waitForURL('**/student/home**')
  return { context, page }
}

export const studentMenu = (page: Page, name: string) =>
  page.getByRole('navigation', { name: '학생 메뉴' }).getByRole('button', { name, exact: true }).click()

/** 미션 고르기(추가 문제 EXTRA)에서 미션을 열어 시작 화면까지. E2E 무료 상품은 시드에서 추가 문제를 켰다(seed/core.sql, #506) */
export async function startExtraMission(page: Page, mission: string) {
  await studentMenu(page, '미션 고르기')
  await page.locator('article', { has: page.getByRole('heading', { name: mission }) })
    .getByRole('button', { name: '미션 열기' }).click()
  await page.getByRole('button', { name: '미션 시작하기' }).click()
  await page.waitForURL('**/student/attempts/**')
}

/**
 * 서술형 미션 화면에서 답 제출 → (선택) 되묻기 답 → 마무리 → 돌아보기 저장.
 * llm-stub이 모든 요소를 답변 원문 인용으로 돌려주므로 정답 판정, 되묻기 질문은 llm-stub GeneratedQuestion 고정 문장이다.
 */
export async function solveNarrative(page: Page, answer: string, { followup }: { followup?: string } = {}) {
  const checked = page.getByText('정답을 확인했어요.')
  await page.getByLabel('내 생각과 까닭').fill(answer)
  await page.getByRole('button', { name: '다 썼어요' }).click()
  await expect(checked).toBeVisible({ timeout: 60_000 })
  if (followup) {
    await page.getByRole('button', { name: '질문에 답하기' }).click()
    await expect(page.getByText('한 걸음 더', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('그렇게 생각한 까닭을 한 가지 더 이야기해 줄래요?').first()).toBeVisible()
    await page.getByLabel('내 생각과 까닭').fill(followup)
    await page.getByRole('button', { name: '더해서 보내기' }).click()
    // 피드백 상태 칸은 마지막 답 하나만 보여 준다: 덧붙인 답이 생긴 뒤 다시 정답 확인
    await expect(page.getByText(/덧붙인 답 1/)).toBeVisible()
    await expect(checked).toBeVisible({ timeout: 60_000 })
  }
  await page.getByRole('button', { name: '이대로 돌아보기' }).click()
  await expect(page.getByRole('heading', { name: /(정답|예시 답)과 비교해 보세요\./ })).toBeVisible()
  await expect(page.getByRole('list', { name: '마무리 체크리스트' })).toBeVisible()
  await page.getByRole('button', { name: '돌아보기 남기기' }).click()
  await page.getByRole('button', { name: '보통이에요' }).click()
  await page.getByRole('button', { name: '돌아보기 저장하고 완료' }).click()
}
