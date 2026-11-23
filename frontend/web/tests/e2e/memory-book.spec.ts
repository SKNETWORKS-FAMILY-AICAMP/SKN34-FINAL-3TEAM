import { readFile } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { newParent, useGoogleIdentity } from './support/google.ts'
import { onboardParent } from './support/onboarding.ts'
import { loginStudent, studentMenu } from './support/student.ts'
import { bookStatus, pastRound, premiumShared, setSharing, studentIdOf, uploadSceneImages } from './support/memoryBook.ts'

// 추억 그림책 (docs/proposals/memory-book.md 13.2·13.3, 미도입 시험 구현, feature/memory-book 브랜치 전용).
// 학부모만 발급(2026-11-23 결정): 리포트 화면 회차 목록 → core 생성 명령 → report-worker가 learning 회차 조립·MinIO 테마 그림으로
// PDF 저장 → 완료 이벤트 → 학부모 받기. 학생 회차 화면에는 그림책 칸이 없다.
// 실행: compose.e2e 스택에 이 브랜치 이미지 + report-worker MEMORY_BOOK_ASSET_* 설정이 있어야 한다(14.6).
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
