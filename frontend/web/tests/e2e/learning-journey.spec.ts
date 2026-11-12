import { expect, test, type BrowserContext } from '@playwright/test'
import { newParent, useGoogleIdentity, type GoogleIdentity } from './support/google.ts'
import { onboardParent } from './support/onboarding.ts'
import { queueWeeklyReport } from './support/db.ts'

const mission = '쉬는 시간을 늘린다면?' // backend/learning-service/db/seed/demo_missions.sql 2번 (초3·NARRATIVE)

test.describe.serial('학생 미션 → 학부모 대시보드·리포트', () => {
  let parent: GoogleIdentity, nickname: string, studentContext: BrowserContext | undefined
  test.afterEach(async () => { await studentContext?.close(); studentContext = undefined })
  test.beforeAll(() => {
    parent = newParent('journey')
    nickname = `학생${Date.now().toString(36)}`
  })

  // 학생 토큰은 메모리에만 있으므로 학생 단계에서는 page.goto·새로고침 없이 화면 안에서만 이동한다.
  test('학생 미션 제출 → 피드백 → 돌아보기 완료 → 답 공개',async ({ context, page: parentPage, browser }) => {
    await useGoogleIdentity(context, parent)
    await onboardParent(parentPage, nickname)
    // #548: students enter through a registered device and PIN, not a parent-page button.
    await parentPage.getByRole('link', { name: '기기·PIN', exact: true }).click()
    const pin = parentPage.getByRole('form', { name: `${nickname} PIN`, exact: true })
    await pin.getByLabel(`${nickname} 새 PIN`, { exact: true }).fill('4831')
    await pin.getByLabel(`${nickname} 새 PIN 확인`, { exact: true }).fill('4831')
    await pin.getByRole('button', { name: 'PIN 정하기', exact: true }).click()
    await expect(pin.getByRole('status')).toContainText('PIN을 저장했습니다.')
    const pairing = parentPage.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith('/student-devices/pairings'))
    await parentPage.getByRole('button', { name: '등록 코드 만들기', exact: true }).click()
    const { pairingCode } = await (await pairing).json()
    studentContext = await browser.newContext({ baseURL: new URL(parentPage.url()).origin })
    const page = await studentContext.newPage()
    await page.goto('/student/login?code=' + encodeURIComponent(pairingCode))
    await page.getByLabel('기기 이름', { exact: true }).fill('학습 여정 E2E')
    await page.getByRole('button', { name: '이 기기 등록하기', exact: true }).click()
    for (const digit of ['4','8','3','1']) await page.getByRole('button', { name: digit, exact: true }).click()
    await page.getByRole('button', { name: /확인|들어가기/ }).click()
    await page.waitForURL('**/student/home**')

    // 미션 고르기는 추가 문제(EXTRA)라 무료는 프리미엄 전용이지만, E2E 무료 상품은 시드에서 명시적으로 켰다(seed/core.sql, #506)
    await page.getByRole('navigation', { name: '학생 메뉴' }).getByRole('button', { name: '미션 고르기' }).click()
    await page.locator('article', { has: page.getByRole('heading', { name: mission }) })
      .getByRole('button', { name: '미션 열기' }).click()
    await page.getByRole('button', { name: '미션 시작하기' }).click()
    await page.waitForURL('**/student/attempts/**')

    await page.getByLabel('내 생각과 까닭').fill('저는 찬성이에요. 쉬는 시간이 길면 친구들과 더 오래 놀 수 있기 때문이에요.')
    await page.getByRole('button', { name: '다 썼어요' }).click()
    // llm-stub이 모든 요소를 답변 원문 인용으로 돌려주므로 정답 판정
    await expect(page.getByText('정답을 확인했어요.')).toBeVisible({ timeout: 60_000 })

    await page.getByRole('button', { name: '이대로 돌아보기' }).click()
    await expect(page.getByRole('heading', { name: /(정답|예시 답)과 비교해 보세요\./ })).toBeVisible()
    await expect(page.getByRole('list', { name: '마무리 체크리스트' })).toBeVisible()

    await page.getByRole('button', { name: '돌아보기 남기기' }).click()
    await page.getByRole('button', { name: '보통이에요' }).click()
    await page.getByRole('button', { name: '돌아보기 저장하고 완료' }).click()
    const record = page.locator('article', { hasText: `국어 · ${mission}` })
    await expect(record).toBeVisible()
    await expect(record.getByText('완료', { exact: false })).toBeVisible()

    // 답변 원문은 기본 비공개라 학부모 공책에 보이도록 학생이 공개로 바꾼다.
    await page.getByRole('navigation', { name: '학생 메뉴' }).getByRole('button', { name: '설정', exact: true }).click()
    await page.getByRole('radio', { name: '학부모님께 공개할게요' }).click()
    await expect(page.getByRole('status').filter({ hasText: '지금은 공개예요.' })).toBeVisible()
  })

  // 학생 기기와 별개인 새 보호자 컨텍스트에서 로그인해 공개한 기록을 확인한다.
  test('학부모 대시보드 → 주간 리포트', async ({ context, page }) => {
    await useGoogleIdentity(context, parent)
    await page.goto('/login')
    await page.getByRole('link', { name: 'Google 계정으로 계속하기' }).click()
    await page.waitForURL('**/parent/journal**')
    await expect(page.getByRole('heading', { name: `${nickname}의 학습 현황`, exact: true })).toBeVisible()
    const row = page.getByRole('row', { name: new RegExp(mission.replace('?', '\\?')) })
    await expect(row.getByText('완료', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: `${mission} 원문 보기` })).toBeVisible()

    const [from, to] = queueWeeklyReport(nickname).split(' ')
    await page.getByRole('link', { name: '리포트·AI 챗봇', exact: true }).click()
    await page.waitForURL('**/parent/report**')
    const card = page.locator('article', { has: page.getByRole('heading', { name: `${from} ~ ${to}` }) })
    await expect(async () => {
      await page.reload()
      await expect(card.getByText('생성 완료')).toBeVisible({ timeout: 5_000 })
    }).toPass({ timeout: 120_000, intervals: [3_000] })

    await card.getByRole('button', { name: '리포트 상세 보기' }).click()
    await expect(page.getByRole('heading', { name: '리포트 상세' })).toBeVisible()
    await expect(page.getByText(`실제 리포트 기간 · ${from} ~ ${to}`, { exact: false })).toBeVisible()
    await expect(page.getByText('수치 리포트입니다. 이 자녀의 플랜에는 서술 요약이 포함되지 않습니다.')).toBeVisible()
  })
})
