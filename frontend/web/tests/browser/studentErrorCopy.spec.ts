import { waitForStudentHome } from './studentFixture.ts'
import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

// #1093 학생 화면 오류 안내: 코드·확인 번호(개발·문의용)는 학생에게 보이지 않고 안내만(학부모 통합은 serviceRoleCopy.spec),
// 추가 문제가 막히면 이용권·프리미엄 같은 말 없이 아이 말로, 답변 화면 체크박스는 이름으로 읽힌다(MSW 목업만, 실서버·외부 호출 없음)
test.beforeEach(async ({ page }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
})

async function student(page: Page) {
  await page.goto('/student/login')
  await page.getByRole('button', { name: '가상 학생으로 PIN 로그인 준비', exact: true }).click()
  await expect(page.getByRole('button', { name: '5', exact: true })).toBeVisible()
  for (const digit of ['5', '0', '9', '0']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: /확인|들어가기/ }).click()
  await waitForStudentHome(page)
}
const navigate = (page: Page, path: string) =>
  page.evaluate(path => { history.pushState({}, '', path); dispatchEvent(new PopStateEvent('popstate')) }, path)

/** 서술형 시연 미션으로 답변 쓰기 화면을 연다(목업 저장소에만 시도를 만든다) */
async function work(page: Page) {
  await student(page)
  const attemptId = await page.evaluate(async () => {
    const { fixtureStore, persistFixtureState } = await import('/src/mocks/fixtures/student.ts' as string)
    const data = fixtureStore.snapshot(), child = data.session.child
    const sample = data.attempts.find((a: { mission: { inputType: string } }) => a.mission.inputType === 'NARRATIVE')
    if (!sample) throw new Error('Missing synthetic narrative mission')
    const attempt = await fixtureStore.start({ ...sample.mission, grade: child.grade }, child)
    persistFixtureState()
    return attempt.attemptId as string
  })
  await navigate(page, `/student/attempts/${attemptId}`)
  await expect(page.locator('.st-work h1')).toBeFocused()
}

const CODE = /[A-Z]{2,}_[A-Z_]{2,}/
const NO_PAYMENT = /결제|구매|이용권|프리미엄/

test('학생 오류 상자에는 "문제 자세히 보기"·코드·확인 번호가 없다 @responsive', async ({ page }) => {
  await student(page)
  await navigate(page, '/student/attempts/missing-1093-fixture')
  const alert = page.locator('.ux-error[role="alert"]').first()
  await expect(alert).toBeVisible()
  await expect(alert).not.toContainText('문제 자세히 보기')
  await expect(alert).not.toContainText('확인 번호')
  await expect(alert).not.toContainText(CODE)
  await expect(alert.locator('details')).toHaveCount(0)
})

test('빈 칸으로 내면 ANSWER_INCOMPLETE 없이 안내가 보이고, 그 칸 바로 아래에도 안내가 있다', async ({ page }) => {
  await work(page)
  await page.getByRole('button', { name: '다 썼어요' }).click()
  const alert = page.locator('.ux-error[role="alert"]').first()
  await expect(alert).toContainText('내 생각을 먼저 적어 주세요.')
  await expect(page.getByText('ANSWER_INCOMPLETE')).toHaveCount(0)
  await expect(alert).not.toContainText('문제 자세히 보기')
  const hint = page.locator('.cj-field .sw-field-empty')
  await expect(hint).toHaveText('‘내 생각과 이유’ 칸을 채워 주세요.')
  // 칸에 쓰면 그 칸 아래 안내는 바로 사라진다
  await page.getByLabel('내 생각과 이유').fill('그림이 있으면 이해하기 쉬워요.')
  await expect(hint).toHaveCount(0)
})

test('무료 학생이 추가 문제를 시작하면 이용권·프리미엄 말 없이 아이 말로 안내한다', async ({ page }) => {
  await student(page)
  await page.getByRole('button', { name: /더 풀어 보기/ }).click()
  await page.getByRole('button', { name: '미션 열기', exact: true }).first().click()
  await page.getByRole('button', { name: '미션 시작하기' }).click()
  await expect(page.getByRole('status').filter({ hasText: '이 문제는 지금은 열 수 없어요. 오늘 문제를 먼저 풀어 봐요!' })).toBeVisible()
  await expect(page.locator('.mg-page')).not.toContainText(NO_PAYMENT)
  await expect(page.locator('.mg-page')).not.toContainText(CODE)
  await expect(page.getByRole('button', { name: '닫기', exact: true })).toBeVisible()
})

test('답변 쓰기 화면 체크박스는 화면 읽기에서 이름으로 읽힌다(on 아님)', async ({ page }) => {
  await work(page)
  const boxes = page.getByRole('checkbox')
  await expect(boxes.first()).toBeVisible()
  for (const box of await boxes.all()) await expect(box).toHaveAccessibleName(/[가-힣]/)
  await expect(page.getByRole('checkbox', { name: '보호자가 아이의 말을 그대로 적었어요.', exact: true })).toHaveCount(1)
})
