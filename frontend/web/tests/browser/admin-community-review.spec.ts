import { expect, test } from '@playwright/test'

test('관리자는 공유물 원문을 읽고 다시 공개한 뒤 같은 결과만 재전송할 수 있다 @responsive', async ({ page }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, (route) => route.abort())
  await page.goto('/admin/login')
  await page.getByRole('button', { name: '로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/admin\/home/)
  await page.evaluate(async () => {
    const fixture = '/src/mocks/fixtures/retention.ts'
    const { retentionState, seedFriendPosts, persistRetention } = await import(fixture)
    seedFriendPosts({ id: 'browser-community-review', title: '합성 미션' })
    const post = retentionState.posts.find((item: { missionId: string }) => item.missionId === 'browser-community-review')
    if (!post) throw new Error('합성 공유물이 없습니다.')
    post.answer = '공유물 원문입니다.\n두 번째 줄입니다.'
    post.status = 'HIDDEN_REPORT'
    for (const [id, targetId, comment] of [
      ['browser-review', post.postId, '공유물 확인 요청'],
      ['browser-destroyed', 'missing-post', '파기된 공유물 확인 요청'],
    ]) {
      retentionState.communityReports.unshift({
        reporterId: 'demo-student',
        key: id,
        report: { reportId: id, status: 'IN_REVIEW', targetType: 'COMMUNITY_POST', targetId, category: 'INAPPROPRIATE', comment, corrections: [] },
      })
    }
    persistRetention()
  })
  await page.goto('/admin/errors')
  await page.locator('article', { has: page.getByText('파기된 공유물 확인 요청', { exact: true }) })
    .getByRole('button', { name: '신고 상세·연결 기록 열람' }).click()
  const detail = page.getByRole('dialog', { name: '신고 연결 기록 검토' })
  await expect(detail.getByText('파기된 글입니다. 원문을 볼 수 없습니다.')).toBeVisible()
  await page.keyboard.press('Escape')

  await page.locator('article', { has: page.getByText('공유물 확인 요청', { exact: true }) })
    .getByRole('button', { name: '신고 상세·연결 기록 열람' }).click()
  await expect(detail.getByText('현재 공개 상태 · 신고되어 확인 중')).toBeVisible()
  await expect(detail.locator('blockquote')).toHaveText('공유물 원문입니다. 두 번째 줄입니다.')
  await expect(detail.getByRole('button', { name: '정정 이력 추가' })).toHaveCount(0)
  const decision = detail.getByLabel('공유물 처리 결과')
  await expect(decision).toHaveValue('REMOVED')
  await decision.selectOption('VISIBLE')
  await detail.getByRole('textbox', { name: '검토 사유' }).fill('다시 공개합니다.')
  const waitForReview = () => page.waitForRequest((request) =>
    request.url().endsWith('/api/v1/admin/error-reports/browser-review') && request.method() === 'PATCH')
  const save = waitForReview()
  await detail.getByRole('button', { name: '검토 결과 저장' }).click()
  expect((await save).postDataJSON()).toEqual({ status: 'RESOLVED', reviewReason: '다시 공개합니다.', reviewResult: 'VISIBLE' })
  await expect(detail.getByRole('heading', { name: '검토 완료 · 다시 공개' })).toBeVisible()
  await expect(decision).toHaveCount(0)
  await expect(detail.getByText('현재 공개 상태 · 공개 중')).toBeVisible()
  const repeat = waitForReview()
  await detail.getByRole('button', { name: '같은 결과 다시 적용' }).click()
  expect((await repeat).postDataJSON()).toEqual((await save).postDataJSON())
})
