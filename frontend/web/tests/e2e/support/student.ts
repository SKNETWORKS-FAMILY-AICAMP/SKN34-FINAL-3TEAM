import { expect, type Browser, type BrowserContext, type Page } from '@playwright/test'

/**
 * 학부모 화면에서 PIN을 정하고 등록 코드로 새 학생 기기를 등록한 뒤 PIN으로 들어간다(#548).
 * 학생 토큰은 메모리에만 있으므로 돌려받은 학생 화면에서는 page.goto·새로고침 없이 화면 안에서만 이동한다.
 */
export async function loginStudent(browser: Browser, parentPage: Page, nickname: string, deviceName = 'E2E 학생 기기',
  { keepTour = false }: { keepTour?: boolean } = {}):
  Promise<{ context: BrowserContext; page: Page }> {
  await parentPage.getByRole('link', { name: '기기·PIN', exact: true }).click()
  await parentPage.getByRole('button', { name: `${nickname} PIN 관리`, exact: true }).click()
  const pinDialog = parentPage.getByRole('dialog', { name: `${nickname} PIN 관리`, exact: true })
  const pin = pinDialog.getByRole('form', { name: `${nickname} PIN`, exact: true })
  await pin.getByLabel(`${nickname} 새 PIN`, { exact: true }).fill('4831')
  await pin.getByLabel(`${nickname} 새 PIN 확인`, { exact: true }).fill('4831')
  await pin.getByRole('button', { name: 'PIN 정하기', exact: true }).click()
  await expect(pinDialog).toBeHidden()
  await expect(parentPage.getByRole('status')).toContainText(`${nickname}의 PIN을 저장했습니다.`)
  await expect(parentPage.getByRole('button', { name: `${nickname} PIN 관리`, exact: true })).toBeFocused()
  await parentPage.getByRole('button', { name: '기기 연결', exact: true }).click()
  const pairingDialog = parentPage.getByRole('dialog', { name: '새 학습 기기 연결', exact: true })
  const pairing = parentPage.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith('/student-devices/pairings'))
  await pairingDialog.getByRole('button', { name: '등록 코드 만들기', exact: true }).click()
  const { pairingCode } = await (await pairing).json()
  await pairingDialog.getByRole('button', { name: '창 닫기', exact: true }).click()
  const context = await browser.newContext({ baseURL: new URL(parentPage.url()).origin })
  const page = await context.newPage()
  await page.goto('/student/login?code=' + encodeURIComponent(pairingCode))
  await page.getByLabel('기기 이름', { exact: true }).fill(deviceName)
  await page.getByRole('button', { name: '이 기기 등록하기', exact: true }).click()
  for (const digit of ['4', '8', '3', '1']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: /확인|들어가기/ }).click()
  await page.waitForURL('**/student/home**')
  // 새 학생은 첫 홈 진입 때 화면 둘러보기가 뜬다(#1038). 둘러보기를 시험하는 spec만 keepTour로 남긴다
  if (!keepTour) await skipStudentTour(page)
  return { context, page }
}

export const studentTour = (page: Page) => page.getByRole('dialog', { name: /화면 둘러보기$/ })

/**
 * 첫 홈 진입의 화면 둘러보기(#1038)를 [그만 볼래]로 넘긴다(완료 기록이 남아 다시 뜨지 않음).
 * 홈이 자동 시작을 판단할 때까지(data-tour-home ≠ wait) 기다린 뒤, 시작했으면 닫는다
 */
export async function skipStudentTour(page: Page) {
  const home = page.locator('[data-tour-home]')
  await expect(home).toHaveAttribute('data-tour-home', /^(start|none)$/)
  const tour = studentTour(page)
  if ((await home.getAttribute('data-tour-home')) === 'start') await expect(tour).toBeVisible()
  if (await tour.isVisible()) {
    const saved = page.waitForResponse(r => r.request().method() === 'PUT' && new URL(r.url()).pathname.endsWith('/students/me/onboarding'))
    await tour.getByRole('button', { name: '그만 볼래', exact: true }).click()
    await expect(tour).toBeHidden()
    expect((await saved).status()).toBe(200)
  }
}

/** 둘러보기 n번 대사가 다 나온 뒤 대화창을 눌러 다음으로(앞 대사의 ▼를 보고 누르지 않게) */
export async function nextTourLine(page: Page, n: number) {
  const tour = studentTour(page)
  await expect(tour.locator('.st-tour-count')).toHaveText(`${n} / 8`)
  await expect(tour.locator('.st-tour-next')).toBeVisible()
  await tour.locator('.st-tour-box').click()
}

export const studentMenu = (page: Page, name: string) =>
  page.getByRole('navigation', { name: '학생 메뉴' }).getByRole('button', { name, exact: true }).click()

/**
 * 홈 "더 풀어 보기"(추가 문제 EXTRA, #648에서 메뉴 대신 홈으로 옮김)에서 미션을 열어 시작 화면까지. E2E 무료 상품은 시드에서 추가 문제를 켰다(seed/core.sql, #506)
 * #648: "더 풀어 보기"는 테마가 없는 학년의 홈("이번 주 테마를 준비하고 있어요")에도 있다(이 E2E에서 테마 있을 때만 있던 것을 발견해 고침).
 */
export async function startExtraMission(page: Page, mission: string) {
  // 옛 메뉴 "미션 고르기"는 어느 화면에서나 눌렀지만 "더 풀어 보기"는 홈에만 있어 홈부터 간다(설정에서 바로 부르는 spec이 있음)
  await studentMenu(page, '홈')
  await page.getByRole('button', { name: /더 풀어 보기/ }).click()
  await page.waitForURL('**/student/missions**')
  await page.locator('article', { has: page.getByRole('heading', { name: mission }) })
    .getByRole('button', { name: '미션 열기' }).click()
  await page.getByRole('button', { name: '미션 시작하기' }).click()
  await page.waitForURL('**/student/attempts/**')
}

/**
 * 테마 문제를 연 뒤 답변 작성까지(#807): 테마 문제는 미션 안내 대신 오늘 장면을 거친다. 그날 대화가 있으면 대화 상자를
 * 마지막 대사까지 눌러 넘기고, 대화가 없는 테마(관리자가 직접 만든 E2E 테마 등)는 장면 없이 바로 답변 작성으로 간다
 */
export async function throughTodayScene(page: Page) {
  await expect(async () => {
    if (page.url().includes('/student/attempts/')) return
    const box = page.locator('.ts-box')
    if (await box.isVisible()) await box.click()
    expect(page.url()).toContain('/student/attempts/')
  }).toPass({ timeout: 30_000, intervals: [300] })
}

/**
 * 답 칸을 채우고 자동 저장(입력 600ms 뒤 초안 저장)이 끝날 때까지 기다린다. 예전에는 저장 중 보내기 버튼이 잠겨
 * 그 사이 누른 클릭이 사라졌다(2026-11-16 로컬 실서버 실행에서 발견). 지금은 저장 중에 누르면 저장 뒤 보내지만(StudentWorkPage),
 * 시험은 저장 완료를 기다려 요청 순서를 고정한다
 */
async function writeAnswer(page: Page, text: string) {
  await page.getByLabel('내 생각과 이유').fill(text)
  await expect(page.getByRole('group', { name: '작성 도구' }).getByRole('status')).toContainText('저장했어요')
}

/**
 * 서술형 미션 화면에서 답 제출 → (선택) 되묻기 답 → 마무리 → 돌아보기 저장.
 * llm-stub이 모든 요소를 답변 원문 인용으로 돌려주므로 정답 판정, 되묻기 질문은 llm-stub GeneratedQuestion 고정 문장이다.
 */
export async function solveNarrative(page: Page, answer: string, { followup }: { followup?: string } = {}) {
  const checked = page.getByText('정답을 확인했어요.')
  await writeAnswer(page, answer)
  await page.getByRole('button', { name: '다 썼어요' }).click()
  await expect(checked).toBeVisible({ timeout: 60_000 })
  if (followup) {
    await page.getByRole('button', { name: '질문에 답하기' }).click()
    await expect(page.getByText('한 걸음 더', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('그렇게 생각한 까닭을 한 가지 더 이야기해 줄래요?').first()).toBeVisible()
    await writeAnswer(page, followup)
    await page.getByRole('button', { name: '더해서 보내기' }).click()
    // 피드백 상태 칸은 마지막 답 하나만 보여 준다: 덧붙인 답이 생긴 뒤 다시 정답 확인
    await expect(page.getByText(/덧붙인 답 1/)).toBeVisible()
    await expect(checked).toBeVisible({ timeout: 60_000 })
  }
  await page.getByRole('button', { name: /^마무리( 보기|하기)$/ }).click()
  // 마무리 화면 제목은 화면 읽기용으로만 남음(D안 #807): "마무리 · 정답과 비교해 보세요"
  await expect(page.getByRole('heading', { name: /(정답|예시 답)과 비교해 보세요/ })).toBeAttached()
  await expect(page.getByRole('group', { name: '마무리 체크리스트' })).toBeVisible()
  await page.getByRole('button', { name: '보통이에요' }).click()
  await page.getByRole('button', { name: '미션 완료하기' }).click()
  // 미션 완료 화면(#807)에서 내 공책으로
  await page.getByRole('dialog', { name: '미션 완료!' }).getByRole('button', { name: '내 공책 보기' }).click()
  await page.waitForURL('**/student/journal**')
}

/**
 * 돌아보기를 저장하면 내 공책으로 온다. #648 내 공책은 기록 카드(article "국어 · 제목") 대신 주별 한 줄이고,
 * 줄에 제목·생각 유형과 상태(돌아보기까지 끝나면 '마무리')가 보인다. 과목은 국어 우선 결정(P15)으로 목록에서 뺐다(2026-11-16).
 */
export async function expectJournalDone(page: Page, mission: string) {
  const row = page.getByRole('listitem').filter({ has: page.getByText(mission, { exact: true }) })
  await expect(row).toBeVisible()
  await expect(row.getByText('마무리', { exact: true })).toBeVisible()
}
