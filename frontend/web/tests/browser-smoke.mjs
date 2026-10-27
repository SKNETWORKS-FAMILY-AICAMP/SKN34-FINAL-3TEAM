// 실행 환경에 Playwright와 Chromium이 있어야 합니다. 단위 테스트와 별도 실행합니다.
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import assert from 'node:assert/strict'
const require = createRequire(process.env.PLAYWRIGHT_PACKAGE ?? import.meta.url)
const { chromium } = require('playwright')
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || undefined,
})
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = [],
  checked = []
page.on('pageerror', (e) => errors.push(e.message))
const apiResponses = []
page.on('response', (response) => {
  const path = new URL(response.url()).pathname
  if (path.startsWith('/api/v1/'))
    apiResponses.push({
      path,
      method: response.request().method(),
      msw: response.fromServiceWorker(),
    })
})
const out = process.env.QA_OUTPUT_DIR
if (out) await mkdir(out, { recursive: true })
const shot = async (name) => {
  if (out) await page.screenshot({ path: path.join(out, name + '.jpg'), type: 'jpeg', quality: 88 })
}
const noOverflow = async () =>
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
const login = async () => {
  await page.getByRole('button', { name: '시연 계정으로 로그인' }).click()
  await page.getByRole('button', { name: '이 자녀로 학습 시작' }).waitFor()
}
const start = async (title) => {
  await page.getByRole('button', { name: '미션 고르기', exact: true }).click()
  await page
    .locator('.cj-activity')
    .filter({ has: page.getByRole('heading', { name: title, exact: true }) })
    .getByRole('button', { name: '미션 열기' })
    .click()
  await page.getByRole('button', { name: '작성하기 · 진행 중이면 이어서' }).click()
  await page.getByRole('region', { name: '미션 작성기' }).waitFor()
}
try {
  await page.goto(process.env.DEMO_URL ?? 'http://127.0.0.1:5173')
  await login()
  await noOverflow()
  await shot('01-laptop-parent-journal')
  await page.getByRole('button', { name: '이 자녀로 학습 시작' }).click()
  await page.getByRole('button', { name: '미션 고르기', exact: true }).waitFor()
  await start('도서관에 만화책을 더 둘까요?')
  await page.getByRole('button', { name: '생각 메모', exact: true }).click()
  await page.getByTestId('private-memo').fill('학부모에게 공유하지 않을 비밀 메모')
  await page.getByText('초안 저장 완료(모의)', { exact: true }).waitFor()
  await page.getByRole('button', { name: '답변 쓰기', exact: true }).click()
  await page
    .getByLabel('내 생각과 까닭')
    .fill('만화책을 더 두면 좋겠어요. 그림으로 내용을 이해할 수 있기 때문이에요.')
  await page.getByText('초안 저장 완료(모의)', { exact: true }).waitFor()
  await shot('02-laptop-student-editor')
  await page.getByLabel('상태 시연').selectOption('ai-fail')
  await page.getByRole('button', { name: '답변 제출', exact: true }).click()
  await page.getByRole('button', { name: '피드백만 다시 요청' }).waitFor()
  assert.equal(await page.locator('.ux-answer-version').count(), 1)
  await page.getByRole('button', { name: '피드백만 다시 요청' }).click()
  await page.getByRole('button', { name: '질문에 답하기' }).waitFor()
  assert.equal(await page.locator('.ux-answer-version').count(), 1)
  checked.push('답변 보존 / AI 실패 후 동일 답변 피드백 재시도')
  await page.getByLabel('상태 시연').selectOption('normal')
  for (const [i, text] of [
    '그림 덕분에 과학 내용을 이해한 경험이 있어요.',
    '글책도 함께 두고 원하는 책을 고르면 좋겠어요.',
  ].entries()) {
    await page.getByRole('button', { name: '질문에 답하기' }).click()
    await page.getByLabel('내 생각과 까닭').fill(text)
    await page.getByText('초안 저장 완료(모의)', { exact: true }).waitFor()
    await page.getByRole('button', { name: '답변 제출', exact: true }).click()
    await page
      .locator('.ux-answer-version')
      .nth(i + 1)
      .waitFor()
    await page.getByText('판정 보류 · 답변은 기록했어요.', { exact: true }).waitFor()
  }
  await page.getByRole('button', { name: '마무리하기', exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: '질문에 답하기' }).count(), 0)
  assert.equal(await page.locator('.ux-answer-version').count(), 3)
  await page.getByRole('button', { name: '마무리하기', exact: true }).click()
  await page.getByRole('button', { name: '돌아보기 남기기' }).waitFor()
  assert.equal(await page.getByRole('button', { name: '답변 제출', exact: true }).count(), 0)
  await page.getByRole('button', { name: '돌아보기 남기기' }).click()
  await page.getByRole('button', { name: '돌아보기 저장하고 완료' }).click()
  await page.getByText('이번 활동이 어땠는지 하나 골라 주세요.', { exact: true }).waitFor()
  await page.getByRole('button', { name: '보통이에요' }).click()
  await page.getByRole('button', { name: '돌아보기 저장하고 완료' }).click()
  await page.getByRole('heading', { name: '나의 공책' }).waitFor()
  checked.push('추가 답변 최대 2회 / 마무리 후 잠금 / 필수 난이도 / 공책 복귀')
  await page.getByRole('button', { name: '학부모 로그인으로', exact: true }).click()
  await login()
  assert.equal((await page.locator('body').innerText()).includes('공유하지 않을 비밀 메모'), false)
  await page.getByRole('button', { name: '주간 리포트', exact: true }).click()
  await page.getByRole('heading', { name: '서윤의 한 주' }).waitFor()
  await shot('03-laptop-parent-report')
  await page.getByRole('button', { name: '원문·질문·돌아보기' }).first().click()
  await page.getByRole('dialog', { name: '인용한 학습 원문' }).waitFor()
  assert.equal(
    (await page.getByRole('dialog').innerText()).includes('공유하지 않을 비밀 메모'),
    false,
  )
  await page.getByRole('button', { name: '창 닫기', exact: true }).click()
  await page.getByRole('button', { name: '이 자녀·이 기간으로 물어보기' }).click()
  await page.getByRole('button', { name: '기록 확인하기', exact: true }).click()
  await page.locator('.ux-analysis-result').waitFor()
  assert.equal((await page.locator('.ux-analysis-result').innerText()).includes('화면 시연'), true)
  checked.push('주간 리포트→원문→같은 자녀/기간 분석 / 메모 비공개')
  await page.getByLabel('자녀 선택', { exact: true }).selectOption('demo-doyun')
  await page.getByText(/분석 대화는 프리미엄에서 이용할 수 있습니다/).waitFor()
  assert.equal(await page.locator('.ux-analysis-result').count(), 0)
  checked.push('자녀 변경 시 기존 분석 제거 / 무료 이용 잠금')
  await page.getByLabel('자녀 선택', { exact: true }).selectOption('demo-seoyun')
  await page.getByRole('button', { name: '아이의 공책', exact: true }).click()
  for (const [width, height] of [
    [1024, 768],
    [768, 1024],
    [390, 844],
  ]) {
    await page.setViewportSize({ width, height })
    await noOverflow()
    await shot(`04-journal-${width}x${height}`)
  }
  checked.push('1440×900 / 1024×768 / 768×1024 / 390×844 수평 넘침 없음')
  await page.setViewportSize({ width: 1024, height: 768 })
  await page.getByRole('button', { name: '이 자녀로 학습 시작' }).click()
  await start('다시 해 본 경험')
  await page.getByLabel('상태 시연').selectOption('draft-conflict')
  await page.getByLabel('내 생각과 까닭').fill('내 입력은 충돌해도 보존합니다.')
  const conflict = page.getByRole('dialog', { name: '다른 화면에 더 최신 초안이 있어요.' })
  await conflict.waitFor()
  assert.ok((await conflict.innerText()).includes('내 입력은 충돌해도 보존합니다.'))
  await page.getByRole('button', { name: '현재 입력으로 저장', exact: true }).click()
  await page.getByText('초안 저장 완료(모의)', { exact: true }).waitFor()
  await shot('05-tablet-student-editor')
  await page.getByLabel('상태 시연').selectOption('draft-fail')
  await page.getByLabel('내 생각과 까닭').fill('실패한 입력도 확인 없이 지우지 않습니다.')
  await page.getByText('초안 저장 실패 · 입력은 유지됩니다.', { exact: true }).waitFor()
  await page.getByRole('button', { name: '공책으로', exact: true }).click()
  await page.getByRole('dialog', { name: '아직 저장하지 못한 입력이 있어요.' }).waitFor()
  await page.getByRole('button', { name: '계속 작성', exact: true }).click()
  assert.equal(
    await page.getByLabel('내 생각과 까닭').inputValue(),
    '실패한 입력도 확인 없이 지우지 않습니다.',
  )
  await page.getByRole('button', { name: '다시 시도', exact: true }).click()
  await page.getByText('초안 저장 완료(모의)', { exact: true }).waitFor()
  checked.push('태블릿 작성기 / 409 초안 비교 / 저장 실패 재시도 / 나가기 전 입력 보존 확인')
  if (process.env.API_URL) {
    const apiPage = await browser.newPage()
    apiPage.on('pageerror', (e) => errors.push(e.message))
    // 실제 서버 통합 검증이 아닌, 공개 Controller 미구현(404) 응답 UI 검증입니다.
    await apiPage.route('**/api/v1/auth/login', (route) =>
      route.fulfill({
        status: 404,
        contentType: 'application/problem+json',
        body: JSON.stringify({ status: 404, code: 'NOT_FOUND', title: '공개 로그인 API 미구현' }),
      }),
    )
    await apiPage.goto(process.env.API_URL)
    assert.ok((await apiPage.locator('body').innerText()).includes('API 연결 모드'))
    await apiPage.getByLabel('이메일', { exact: true }).fill('parent@example.test')
    await apiPage.getByLabel('비밀번호', { exact: true }).fill('test-only')
    await apiPage.getByRole('button', { name: '로그인', exact: true }).click()
    await apiPage.getByRole('alert').waitFor()
    assert.equal(await apiPage.locator('.cj-post').count(), 0)
    assert.equal(await apiPage.getByRole('button', { name: '시연 계정으로 로그인' }).count(), 0)
    checked.push('기본 API 빌드에서 404 표시 / 시연 데이터 자동 대체 없음 (응답 스텁 검증)')
    await apiPage.close()
  }
  if (process.env.EXPECT_MSW === 'true') {
    assert.ok(apiResponses.length > 10)
    assert.equal(
      apiResponses.every((r) => r.msw),
      true,
    )
    assert.ok(apiResponses.some((r) => r.path.endsWith('/feedback') && r.method === 'POST'))
    checked.push(`API 요청 ${apiResponses.length}건이 실제 MSW Service Worker 응답임을 확인`)
  }
  assert.deepEqual(errors, [])
  console.log(JSON.stringify({ checked, pageErrors: errors }, null, 2))
  if (out)
    await writeFile(
      path.join(out, 'browser-results.json'),
      JSON.stringify({ checked, pageErrors: errors }, null, 2),
    )
} catch (error) {
  await shot('failed')
  console.error((await page.locator('body').innerText()).slice(-5000))
  throw error
} finally {
  await browser.close()
}
