import { readFile } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { newParent, useGoogleIdentity } from './support/google.ts'
import { onboardParent } from './support/onboarding.ts'
import { loginStudent, studentMenu } from './support/student.ts'
import { bookStatus, pastRound, premiumShared, setSharing, studentIdOf, uploadSceneImages } from './support/memoryBook.ts'

// 추억 그림책 (docs/proposals/memory-book.md 13.2·13.3, #975).
// 학부모만 발급(2026-11-23 결정): 리포트 화면 회차 목록 → core 생성 명령 → report-worker가 learning 회차 조립·MinIO 테마 그림으로
// PDF 저장 → 완료 이벤트 → 학부모 받기. 학생 회차 화면에는 그림책 칸이 없다.
// 공용 E2E 스택(compose.e2e.yaml)에 learning 그림 버킷·report-worker 그림 받기 주소가 있어 원격 CI에서도 돈다.
test('학부모: 유료·원문 공개 자녀의 회차로 그림책 발급 → 실제 PDF 받기, 학생 화면에는 칸 없음, 비공개로 바꾸면 막힘',
  async ({ browser, context, page: parentPage }, testInfo) => {
    const nickname = `책${Date.now().toString(36)}`
    const title = 'E2E 사라진 등대 불빛'
    await useGoogleIdentity(context, newParent('book'))
    await onboardParent(parentPage, nickname)
    const studentId = studentIdOf(nickname)
    premiumShared(studentId)
    const prefix = `memorybook-e2e-${Date.now().toString(36)}`
    uploadSceneImages(prefix)
    pastRound(studentId, prefix, title)

    // 학생 회차 화면: 그림책 칸이 없다(발급은 학부모만)
    const { context: studentContext, page } = await loginStudent(browser, parentPage, nickname, '그림책 E2E')
    try {
      await studentMenu(page, '내 방')
      await page.getByRole('button', { name: '추억 앨범 열기' }).click()
      await page.getByRole('list', { name: '보유한 기념 액자' }).getByRole('button').first().click()
      await expect(page.getByRole('heading', { name: title })).toBeVisible()
      await expect(page.getByRole('region', { name: '추억 그림책' })).toHaveCount(0)
    } finally {
      await studentContext.close()
    }

    // 학부모: 리포트 화면의 회차 목록에서 발급 → 만드는 중 → 받기
    await parentPage.getByRole('link', { name: '리포트·AI 챗봇', exact: true }).click()
    const books = parentPage.getByRole('region', { name: '추억 그림책' })
    const row = books.getByRole('list', { name: '그림책을 발급할 수 있는 회차' }).getByRole('listitem').filter({ hasText: title })
    await row.getByRole('button', { name: '그림책 발급' }).click()
    await expect(row.getByRole('status')).toContainText('만드는 중')
    const save = row.getByRole('button', { name: '받기' })
    await expect(save).toBeVisible({ timeout: 90_000 })
    expect(bookStatus(studentId)).toMatch(/^READY \d+$/)

    const [download] = await Promise.all([parentPage.waitForEvent('download'), save.click()])
    const file = testInfo.outputPath('memory-book.pdf')
    await download.saveAs(file)
    const body = await readFile(file)
    expect(body.subarray(0, 5).toString()).toBe('%PDF-')
    // 테마 그림 7장(JPEG)이 들어가 표본(단색 PNG)보다 훨씬 크다
    expect(body.length).toBeGreaterThan(200_000)
    await testInfo.attach('memory-book.pdf', { path: file, contentType: 'application/pdf' })

    // 원문 비공개로 바꾸면 발급·받기 모두 막힌다(D2)
    setSharing(studentId, false)
    await parentPage.reload()
    await expect(parentPage.getByRole('region', { name: '추억 그림책' }).getByRole('alert')).toContainText('답 보여 주기를 켜야')
  })

// 책장(#1000, core #999): 무료 자녀는 서버가 끝난 최근 4주 회차만 보내고 오래된 회차는 숫자(lockedCount)로만 알린다.
// 4주 경계(−21일·−28일)와 다른 시험이 채운 주에 흔들리지 않게, 확실히 오래된(8주 이상 전) 회차 하나만 만들어 잠금만 본다.
test('학부모: 무료·원문 공개 자녀는 오래된 회차가 잠긴 수로만 보이고 발급 단추 없이 비교표로 이어진다', async ({ context, page }) => {
  const nickname = `잠${Date.now().toString(36)}`
  const title = 'E2E 오래된 등대'
  await useGoogleIdentity(context, newParent('shelf'))
  await onboardParent(page, nickname)
  const studentId = studentIdOf(nickname)
  setSharing(studentId, true)
  const prefix = `memorybook-shelf-${Date.now().toString(36)}`
  uploadSceneImages(prefix)
  pastRound(studentId, prefix, title, 8)

  await page.getByRole('link', { name: '리포트·AI 챗봇', exact: true }).click()
  const books = page.getByRole('region', { name: '추억 그림책' })
  await expect(books.getByRole('note')).toContainText(/지난 그림책 \d+권은 프리미엄에서 볼 수 있어요/)
  await expect(books.getByText(title)).toHaveCount(0)
  await expect(books.getByRole('button', { name: '그림책 발급' })).toHaveCount(0)
  await books.getByRole('link', { name: '무료와 프리미엄 비교 보기' }).click()
  await expect(page).toHaveURL(/\/parent\/billing\?childId=.+#plan-compare$/)
})
