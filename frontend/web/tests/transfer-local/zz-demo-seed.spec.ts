import { test, expect } from '@playwright/test'
import { actor, call, child, disposeActors, seedConversation, sql } from './api.ts'

test('수동 체험용 합성 계정 준비', async () => {
  for (const [key, name, count] of [['sender', '보내는 학부모', 2], ['receiver', '받는 학부모', 0], ['full', '자녀 3명 학부모', 3], ['spare', '추가 테스트 학부모', 0]] as const) {
    const parent = await actor(name, { sub: `trial-${key}`, email: `${key}@example.test`, name })
    const existing = (await (await call(parent, 'get', '/children')).json()).items as { id: string }[]
    for (let i = existing.length; i < count; i++) {
      const id = await child(parent, `${key === 'sender' ? '이관연습' : '한도확인'}${i + 1}`)
      if (key === 'sender') seedConversation(parent, id)
    }
    // No destructive reset: repeated execution leaves the user's trial progress intact.
    if (key === 'sender' && existing.length) {
      const id = existing[0].id
      if (sql('core_db', `SELECT count(*) FROM conversation WHERE student_id='${id}' AND parent_user_id='${parent.userId}'`) === '0') seedConversation(parent, id)
    }
  }
  await disposeActors()
})

test('수동 로그인 계정 선택과 재인증 팝업도 실제 stub으로 열린다', async ({ context, page }) => {
  await context.route(/https:\/\/(fonts\.(googleapis|gstatic)\.com|js\.tosspayments\.com)\//, route => route.abort())
  await page.goto('/login')
  await page.getByRole('link', { name: 'Google 계정으로 계속하기' }).click()
  await expect(page.getByRole('heading', { name: '로컬 테스트 계정 선택' })).toBeVisible()
  await page.getByLabel('학부모').selectOption('sender')
  await page.getByRole('button', { name: '선택한 계정으로 계속' }).click()
  await expect(page.getByRole('heading', { name: /의 학습 기록$/ })).toBeVisible()
  await page.goto('/parent/transfers')
  await page.getByLabel('받는 학부모의 가입 이메일').fill('receiver@example.test')
  await page.getByRole('button', { name: '학부모 찾기' }).click()
  await page.getByRole('button', { name: '이관 내용 확인' }).click()
  const dialog = page.getByRole('dialog', { name: '자녀 이관을 요청하시겠습니까?' })
  const opened = page.waitForEvent('popup')
  await dialog.getByRole('button', { name: 'Google 본인 확인' }).click()
  const popup = await opened
  await popup.getByLabel('학부모').selectOption('sender')
  await popup.getByRole('button', { name: '선택한 계정으로 계속' }).click()
  await expect(popup.locator('body')).toContainText('VERIFIED')
  await popup.close()
  await dialog.getByRole('button', { name: '완료 확인', exact: true }).click()
  await expect(dialog.getByRole('button', { name: '이관 요청', exact: true })).toBeEnabled()
  await page.screenshot({ path: 'test-results/transfer-demo-dialog.png', fullPage: true })
  await dialog.getByRole('button', { name: '취소', exact: true }).click()
})
