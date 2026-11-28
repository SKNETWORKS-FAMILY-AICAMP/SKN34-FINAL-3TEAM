import { readFile } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { newParent, useGoogleIdentity } from './support/google.ts'
import { onboardParent } from './support/onboarding.ts'
import { loginStudent, studentMenu } from './support/student.ts'
import { allowParentOriginals, bookStatus, pastRound, premium, readTogetherOf, studentIdOf, uploadSceneImages } from './support/memoryBook.ts'

/** 오늘 KST 날짜: 화면 표시(MM/DD)와 DB(YYYY-MM-DD) */
const kstToday = () => new Date(Date.now() + 9 * 3600_000).toISOString().slice(0, 10)

// 추억 그림책 (docs/proposals/memory-book.md 13.2·13.3, #975).
// 학부모만 발급(2026-11-23 결정): 리포트 화면 회차 목록 → core 생성 명령 → report-worker가 learning 회차 조립·MinIO 테마 그림으로
// PDF 저장 → 완료 이벤트 → 학부모 받기. 학생 회차 화면에는 그림책 칸이 없다.
// 공용 E2E 스택(compose.e2e.yaml)에 learning 그림 버킷·report-worker 그림 받기 주소가 있어 원격 CI에서도 돈다.
test('학부모: 유료 자녀의 회차로 그림책 발급 → 실제 PDF 받기 → 같이 읽었어요, 학생 화면에는 칸 없음, 비공개 안내 없음',
  async ({ browser, context, page: parentPage }, testInfo) => {
    const nickname = `책${Date.now().toString(36)}`
    const title = 'E2E 사라진 등대 불빛'
    await useGoogleIdentity(context, newParent('book'))
    await onboardParent(parentPage, nickname)
    const studentId = studentIdOf(nickname)
    premium(studentId)
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
    await parentPage.getByRole('link', { name: '리포트·기록에 물어보기', exact: true }).click()
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

    // 같이 읽었어요(#1026, core #1025): 단추가 사라지고 표지에 오늘(KST) 날짜, core에 처음 시각 저장
    const today = kstToday()
    await row.getByRole('button', { name: '같이 읽었어요' }).click()
    await expect(row.getByText(`같이 읽음 ${today.slice(5, 7)}/${today.slice(8, 10)}`, { exact: true })).toBeVisible()
    await expect(row.getByRole('button', { name: '같이 읽었어요' })).toHaveCount(0)
    expect(readTogetherOf(studentId)).toBe(today)

    // 원문 공개 설정·차단은 없어졌다(#1064): 다시 열어도 비공개 안내 없이 책장이 그대로다
    await parentPage.reload()
    await expect(parentPage.getByRole('region', { name: '추억 그림책' }).getByText(/답 보여 주기/)).toHaveCount(0)
  })

// 책장(#1000, core #999): 무료 자녀는 서버가 끝난 최근 4주 회차만 보내고 오래된 회차는 숫자(lockedCount)로만 알린다.
// 4주 경계(−21일·−28일)와 다른 시험이 채운 주에 흔들리지 않게, 확실히 오래된(8주 이상 전) 회차 하나만 만들어 잠금만 본다.
test('학부모: 무료 자녀는 오래된 회차가 잠긴 수로만 보이고 발급 단추 없이 비교표로 이어진다', async ({ context, page }) => {
  const nickname = `잠${Date.now().toString(36)}`
  const title = 'E2E 오래된 등대'
  await useGoogleIdentity(context, newParent('shelf'))
  await onboardParent(page, nickname)
  const studentId = studentIdOf(nickname)
  allowParentOriginals(studentId) // 임시: core #1061 전
  const prefix = `memorybook-shelf-${Date.now().toString(36)}`
  uploadSceneImages(prefix)
  pastRound(studentId, prefix, title, 8)

  await page.getByRole('link', { name: '리포트·기록에 물어보기', exact: true }).click()
  const books = page.getByRole('region', { name: '추억 그림책' })
  await expect(books.getByRole('note')).toContainText(/지난 그림책 \d+권은 프리미엄에서 볼 수 있어요/)
  await expect(books.getByText(title)).toHaveCount(0)
  await expect(books.getByRole('button', { name: '그림책 발급' })).toHaveCount(0)
  await books.getByRole('link', { name: '프리미엄 혜택보기' }).click()
  await expect(page).toHaveURL(/\/parent\/billing\?childId=.+#plan-compare$/)
})
