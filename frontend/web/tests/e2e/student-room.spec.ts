import { expect, test } from '@playwright/test'
import { newParent, useGoogleIdentity } from './support/google.ts'
import { onboardParent } from './support/onboarding.ts'
import { loginStudent, studentMenu } from './support/student.ts'

// 내 방 → 추억 앨범(FN-RET-09·11). 앨범은 지난주에 다섯 문제를 모두 끝낸 회차만 보여 주므로 새 학생은 빈 앨범이다.
// 지난 회차가 있는 앨범·회차 상세는 지난주 기록 준비 방식(#624)이 정해진 뒤 추가한다.
test('내 방 진입 → 추억 앨범(빈 상태) → 내 방으로', async ({ browser, context, page: parentPage }) => {
  const nickname = `방${Date.now().toString(36)}`
  await useGoogleIdentity(context, newParent('room'))
  await onboardParent(parentPage, nickname)
  const { context: studentContext, page } = await loginStudent(browser, parentPage, nickname, '내 방 E2E')
  try {
    await studentMenu(page, '내 방')
    await expect(page.getByRole('heading', { name: '내 방', exact: true })).toBeVisible()
    for (const spot of ['추억의 벽', '학습 책상', '옷장']) await expect(page.getByRole('button', { name: spot, exact: true })).toBeVisible()

    await page.getByRole('button', { name: '추억 앨범 열기' }).click()
    await expect(page.getByRole('heading', { name: '추억 앨범', exact: true })).toBeVisible()
    await expect(page.getByRole('region', { name: '빈 앨범 안내' })).toBeVisible()
    await expect(page.getByRole('list', { name: '보유한 기념 액자' })).toHaveCount(0)

    await page.getByRole('button', { name: '내 방으로' }).click()
    await expect(page.getByRole('heading', { name: '내 방', exact: true })).toBeVisible()
  } finally {
    await studentContext.close()
  }
})
