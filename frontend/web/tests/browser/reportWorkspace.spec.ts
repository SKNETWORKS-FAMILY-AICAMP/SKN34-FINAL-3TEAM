import {test,expect} from '@playwright/test'
import demoData from '../../src/mocks/fixtures/structuredReportSamples.json' with { type: 'json' }

test('shows cached RunPod details for the matching mock answer @responsive', async ({ page, context }, info) => {
  const [library, phone] = demoData.samples
  const detail = JSON.stringify({
    analysis: '도서관 글에 이동 시간과 이용 목적이 담겨 있어요.',
    improvement_points: null,
    next_steps: ['도서관에서 함께 하고 싶은 일을 물어보세요.'],
  })
  await context.route('**/.taste-skill/structured-report-demo/gemma-explanations.json', route => route.fulfill({
    json: {
      model: 'explain',
      promptVersion: 'structured-report-detail@2',
      items: [{
        attemptId: library.attemptId,
        answerVersion: library.texts.length,
        sourceText: library.texts.at(-1),
        text: detail,
      }],
    },
  }))

  await page.goto('/parent/report?reportDemo=structured&childId=demo-report-grade5&reportId=demo-report-grade5-2026-11-09')
  await page.getByRole('button', { name: '돌아보기 기록 3개' }).click()
  const dialog = page.getByRole('dialog', { name: '주간 리포트 전체 보기' })
  await dialog.getByRole('button', { name: new RegExp(library.title) }).click()
  const picker = dialog.locator('.weekly-activity-picker > summary')
  const explanation = page.getByRole('region', { name: '대표 답변 설명' })
  await expect(explanation).toContainText('도서관 글에 이동 시간과 이용 목적이 담겨 있어요.')
  await expect(explanation).toContainText('도서관에서 함께 하고 싶은 일을 물어보세요.')
  await page.screenshot({ path: info.outputPath('weekly-answer-feedback.png') })
  await picker.click()
  await dialog.getByRole('list', { name: '활동 선택 목록' }).getByRole('button', { name: new RegExp(phone.title) }).click()
  await expect(explanation).toContainText('이 활동의 답변에 연결된 대표 답변 설명이 없습니다.')
})

test('long weekly explanations keep readable paragraphs and no horizontal overflow @responsive', async ({ page, context }, info) => {
  const library = demoData.samples[0]
  const sentence = '도서관까지 이동하는 시간과 함께 이용할 사람을 글에 적었어요. 친구들과 숙제를 하고 어른들은 신문을 읽을 수 있다는 까닭을 제시했어요. '
  await context.route('**/.taste-skill/structured-report-demo/gemma-explanations.json', route => route.fulfill({ json: {
    model: 'test-only', promptVersion: 'layout-test', items: [{ attemptId: library.attemptId, answerVersion: library.texts.length, sourceText: library.texts.at(-1), text: sentence.repeat(8) }],
  } }))
  await page.goto('/parent/report?reportDemo=structured&childId=demo-report-grade5')
  await page.getByRole('button', { name: '대표 답변 설명 1개' }).click()
  const dialog = page.getByRole('dialog', { name: '주간 리포트 전체 보기' })
  await dialog.getByRole('button', { name: /우리 동네에 필요한 시설/ }).click()
  const copy = dialog.locator('.report-explanation-copy')
  await expect(copy.locator('p').nth(1)).toBeAttached()
  expect((await copy.innerText()).replace(/\s/g, '')).toBe(sentence.repeat(8).replace(/\s/g, ''))
  const feedback = dialog.locator('.report-reader-feedback')
  await feedback.scrollIntoViewIfNeeded()
  expect(await dialog.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true)
  await page.screenshot({ path: info.outputPath('weekly-long-explanation.png') })
})

test('opens the weekly report inline before opening history or chat @responsive', async ({ page }, info) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/parent/report?reportDemo=structured&childId=demo-report-grade5')
  const detail = page.getByRole('region', { name: '리포트 내용' })
  await expect(detail.getByRole('heading', { name: '주간 리포트', exact: true })).toBeVisible()
  await expect(detail.locator('.report-narrative-text')).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(detail.locator('.weekly-key-metrics dd').first()).toContainText('3')
  await expect(detail.locator('.weekly-thinking-chart li')).toHaveCount(5)
  await expect(detail.getByRole('heading', { name: '이번 주 테마', exact: true })).toHaveCount(0)
  await page.screenshot({ path: info.outputPath('weekly-overview-full.png'), fullPage: true })
  if (info.project.name === 'laptop') {
    await page.setViewportSize({ width: 1706, height: 750 })
    await page.screenshot({ path: info.outputPath('weekly-overview-user-1706.png'), fullPage: true })
    await page.setViewportSize({ width: 1440, height: 900 })
  }
  expect(new URL(page.url()).searchParams.has('reportId')).toBe(false)

  const period = detail.locator('.report-period-picker > summary')
  await period.click()
  const dates = detail.getByRole('list', { name: '리포트 일자' })
  await expect(dates.locator('[aria-current=date]')).toBeVisible()
  await expect(page.getByText('생성 상태', { exact: true })).toHaveCount(0)
  await page.keyboard.press('Escape')
  await expect(dates).toBeHidden()
  await expect(period).toBeFocused()

  await expect(detail.getByRole('region', { name: '활동별 기록' })).toHaveCount(0)
  const content = detail.getByRole('button', { name: /내용 보기$/ }).first()
  await content.click()
  const modal = page.getByRole('dialog', { name: '리포트 항목 내용' })
  await expect(modal).toBeVisible()
  await expect(modal.locator('.report-evidence-heading').first()).toBeVisible()
  await expect(modal.getByRole('heading', { name: '아이의 답변', exact: true }).first()).toBeVisible()
  await page.screenshot({ path: info.outputPath('report-evidence-reader.png') })
  await expect(modal).toHaveCSS('overflow-y', 'hidden')
  await expect(modal.getByRole('region')).toHaveCSS('scrollbar-width', 'none')
  await expect(modal.locator('.cj-modal-scroll-marker')).toHaveCSS('opacity', '0')
  await modal.getByRole('button', { name: '창 닫기' }).click()
  await expect(content).toBeFocused()
  await expect(detail.getByRole('combobox', { name: '근거 항목 선택' })).toHaveCount(0)
  await expect(detail.getByRole('combobox', { name: '리포트 판' })).toHaveCount(0)
  await expect(detail.getByRole('navigation', { name: '리포트 상세 항목' })).toHaveCount(0)
  await expect(detail.getByRole('button', { name: '리포트 다운로드', exact: true })).toBeEnabled()
  await page.screenshot({ path: info.outputPath('weekly-report-inline.png') })
  await detail.getByRole('button', { name: '이 리포트로 질문하기', exact: true }).click()
  await expect(page.getByRole('heading', { name: '질문에 연결한 리포트', exact: true })).toBeVisible()
  const fullScreen = page.locator('.ws-parent-fullscreen')
  await expect(fullScreen).toBeVisible()
  const viewport = page.viewportSize()!
  expect(await fullScreen.boundingBox()).toEqual({ x: 0, y: 0, width: viewport.width, height: viewport.height })
  await expect(page.getByRole('textbox', { name: '기록에 대한 질문' })).toBeInViewport()
  const workspace = page.locator('.pc-layout')
  await expect(workspace).toBeVisible()
  const panel = (await workspace.boundingBox())!
  expect(panel.y + panel.height).toBeCloseTo(viewport.height, 0)
  await expect(page.locator('.pc-thread')).toHaveCSS('max-height', 'none')
  await page.screenshot({ path: info.outputPath('full-screen-chat.png') })
  await page.getByRole('link', { name: '학부모 대시보드로 돌아가기' }).click()
  await expect(page).toHaveURL(/\/parent\/journal\?childId=demo-report-grade5/)
  expect(errors).toEqual([])
})

test('weekly records keep reflection and quote in the selected activity @responsive',async({page,context},info)=>{
 await context.route('**/.taste-skill/structured-report-demo/gemma-explanations.json', route => route.fulfill({ status: 404 }))
 await page.goto('/parent/report?reportDemo=structured&childId=demo-report-grade5&reportId=demo-report-grade5-2026-11-09')
 await page.getByRole('button',{name:'돌아보기 기록 3개'}).click()
 const modal=page.getByRole('dialog',{name:'주간 리포트 전체 보기'})
 await expect(modal).toBeVisible()
 await modal.getByRole('button',{name:/우리 동네에 필요한 시설/}).click()
 const picker=modal.locator('.weekly-activity-picker > summary')
 await picker.click()
 const choices=modal.getByRole('list',{name:'활동 선택 목록'})
 await expect(choices.getByRole('button')).toHaveCount(3)
 const buttonBox=(await picker.boundingBox())!
 const listBox=(await choices.boundingBox())!
 expect(listBox.y).toBeGreaterThanOrEqual(buttonBox.y+buttonBox.height)
 await choices.getByRole('button',{name:/우리 동네에 필요한 시설/}).click()
 const pair=modal.locator('.weekly-activity-pair')
 await expect(pair).toContainText('멀리 간다고만 쓰지 않고')
 await expect(pair).toContainText('우리 동네에는 도서관이 필요하다')
 await expect(pair).not.toContainText('밤늦게까지 영상을')
 await picker.click()
 await choices.getByRole('button',{name:/스마트폰 사용 시간을/}).click()
 await expect(pair).toContainText('좋은 점도 있다는 생각')
 await expect(pair).toContainText('밤늦게까지 영상을')
 await expect(pair).not.toContainText('우리 동네에는 도서관')
 await pair.scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath('weekly-selected-activity.png')})
 expect(await modal.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true)
 await modal.getByRole('button',{name:'뒤로 가기',exact:true}).click()
 await expect(pair).toContainText('우리 동네에는 도서관이 필요하다')
 await modal.getByRole('button',{name:'앞으로 가기',exact:true}).click()
 await expect(pair).toContainText('밤늦게까지 영상을')
 await picker.click()
 await page.keyboard.press('Escape')
 await expect(choices).toBeHidden()
 await expect(picker).toBeFocused()
 await modal.getByRole('button',{name:'창 닫기'}).click()
 await expect(page.getByRole('button',{name:'돌아보기 기록 3개'})).toBeFocused()
 await page.getByRole('button',{name:'따져 보기 1개 활동 보기'}).click()
 await expect(page.getByRole('list',{name:'따져 보기 활동 목록'}).getByRole('button')).toHaveCount(1)
 await page.screenshot({path:info.outputPath('weekly-category-dialog.png')})
})

test('switches between completed daily and weekly reports from the title @responsive', async ({ page }) => {
  await page.goto('/parent/report?reportDemo=structured&childId=demo-report-grade5')
  const detail = page.getByRole('region', { name: '리포트 내용' })
  const period = detail.locator('.report-period-picker > summary')
  await period.click()
  await detail.getByRole('button', { name: '일일', exact: true }).click()
  const dates = detail.getByRole('list', { name: '리포트 일자' })
  const daily = dates.getByRole('button').first()
  await expect(daily).toHaveText(/^\d{4}-\d{2}-\d{2}$/)
  const date = await daily.innerText()
  await daily.click()
  await expect(period).toHaveText('일일 리포트')
  await expect(detail.locator('.report-period-heading > p')).toHaveText(date)
  await expect(dates).toBeHidden()
  await period.click()
  await detail.getByRole('button', { name: '주간', exact: true }).click()
  await dates.getByRole('button', { name: '2026-11-09 ~ 2026-11-15', exact: true }).click()
  await expect(period).toHaveText('주간 리포트')
  await expect(detail.locator('.report-narrative-text')).toBeVisible()
})

test('chat period and composer leave space for verified answers @responsive', async ({ page }) => {
  await page.goto('/parent/report?view=chat&reportDemo=structured&childId=demo-report-grade5&from=2026-11-01&to=2026-11-07')
  const period = page.getByRole('button', { name: /^질문 기간 변경/ })
  await period.click()
  const picker = page.getByRole('dialog', { name: '질문 기간 선택' })
  await picker.getByRole('button', { name: '2026-11-01', exact: true }).click()
  await expect(picker.getByLabel('시작 날짜')).toHaveValue('2026-10-26')
  await expect(picker.getByLabel('종료 날짜')).toHaveValue('2026-11-01')
  await picker.getByRole('button', { name: '2026-11-11', exact: true }).click()
  await expect(picker.getByLabel('시작 날짜')).toHaveValue('2026-11-09')
  await expect(picker.getByLabel('종료 날짜')).toHaveValue('2026-11-15')
  await expect(picker.locator('.pd-calendar-grid button[aria-pressed=true]')).toHaveCount(7)
  await picker.getByRole('button', { name: '확인', exact: true }).click()
  await expect(picker).toHaveCount(0)
  await expect(period).toContainText('2026-11-09 ~ 2026-11-15')
  await expect(page.getByText('선택 기간', { exact: false })).toHaveCount(0)
  await expect(page.getByText('리포트 표시 설정 변경', { exact: true })).toHaveCount(0)

  await page.evaluate(() => window.dispatchEvent(new CustomEvent('sagomungchi:workspace-scenario', { detail: 'analysis-slow' })))
  const input = page.getByRole('textbox', { name: '기록에 대한 질문' })
  await input.fill('이번 주 학습 기록을 알려주세요.')
  await page.getByRole('button', { name: '질문 보내기' }).click()
  const progress = page.locator('.pc-progress')
  await expect(progress).toHaveText('답변을 준비하고 있어요')
  await expect(progress).toHaveCSS('background-color', 'rgb(255, 255, 255)')
  await expect(page.getByText('대조 전 임시 문장', { exact: false })).toHaveCount(0)
  const composer = (await page.locator('.pc-composer').boundingBox())!
  const transcript = (await page.locator('.pc-thread').boundingBox())!
  expect(composer.height).toBeLessThan(72)
  expect(transcript.height).toBeGreaterThan(4 * composer.height)
  await expect(page.getByRole('heading', { name: '기록을 바탕으로 한 답변' })).toBeVisible()
  await expect(progress).toHaveCount(0)
  await expect(page.locator('.pc-answer-footer')).toContainText('조회 기록')
  await expect(page.getByText(/출처 (LLM|TEMPLATE)/)).toHaveCount(0)
  await expect(page.getByText(/연결된 리포트를 선택해야/)).toHaveCount(0)
  await expect(page.locator('.pc-message .ws-metrics')).toHaveCount(0)
  await expect(page.locator('.pc-history-list button[aria-current=true]')).toContainText('이번 주 학습 기록을')
})
