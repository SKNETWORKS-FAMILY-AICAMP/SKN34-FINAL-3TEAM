/**
 * #805 방 소품 색 실서버 확인(1회 실행 기록, CI에 넣지 않음). 수행 구분: 모의(대역 compose — Google·LLM·M2·설명 sLLM·토스 대역, core·learning·DB 실제).
 *
 * 흐름: 작성 학생(커뮤니티 동의·친구 공개) 미션 마무리로 포인트 → 내 방 › 방 꾸미기 › 방 소품에서 시드 "E2E 작은 화분" 사기 → 놓기
 *  → 색 "하늘" → 저장(PUT 요청·응답 color) → 다른 메뉴 갔다 오기 → 새로 고침 뒤 PIN 다시 입력 → 내 방(GET color) → DB 행 color
 *  → 다른 학생이 같은 미션 마무리 뒤 친구 생각에서 그 방에 놀러 가기(친구 방 응답 decor[].color, 그림 색)
 *
 * 실행(저장소 루트, 2절 compose 스택이 떠 있을 때):
 *   cd frontend/web
 *   NODE_PATH=$PWD/node_modules OUT_DIR=../../docs/report/evidence/issue805-room-color \
 *     npx playwright test -c <playwright.e2e.config.ts를 펼치고 testDir만 이 폴더로 바꾼 설정>
 * 결과: OUT_DIR/result.json(학생 ID·닉네임·글 ID 없음)
 */
import { expect, test, type Browser, type Page, type Response } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { newParent, useGoogleIdentity as signInWithGoogle } from '../../../../frontend/web/tests/e2e/support/google.ts'
import { onboardParent } from '../../../../frontend/web/tests/e2e/support/onboarding.ts'
import { loginStudent, solveNarrative, startExtraMission, studentMenu } from '../../../../frontend/web/tests/e2e/support/student.ts'

const mission = '쉬는 시간을 늘린다면?' // demo_missions.sql 2번(초3 서술, 추가 문제라 요일과 무관)
const SKY = 'rgb(156, 203, 239)' // decorDraw.ts 하늘 #9CCBEF(입체 화분 몸통 CSS 색)
const ORANGE = 'rgb(242, 166, 90)' // 작은 화분 기본 색 주황 #F2A65A
const container = process.env.E2E_POSTGRES_CONTAINER ?? 'sagomungchi-e2e-postgres-1'
const psql = (db: string, sql: string) => execFileSync('docker', ['exec', '-i', container, 'sh', '-c', `psql -v ON_ERROR_STOP=1 -qAt -F '|' -U "$POSTGRES_USER" -d ${db}`],
  { input: sql, encoding: 'utf8' }).trim()

async function newStudent(browser: Browser, prefix: string, consent: boolean) {
  const nickname = `${prefix}${Date.now().toString(36)}`
  const parentContext = await browser.newContext()
  await signInWithGoogle(parentContext, newParent('room-color'))
  const parentPage = await parentContext.newPage()
  await onboardParent(parentPage, nickname)
  if (consent) {
    await parentPage.getByRole('button', { name: '참여 기록', exact: true }).click()
    await parentPage.getByRole('dialog').getByRole('region', { name: /참여 기록/ }).getByRole('link', { name: '커뮤니티 동의하기' }).click()
    const section = parentPage.locator('#community-consent')
    const state = section.getByRole('status').filter({ hasText: /^현재 / })
    await section.getByRole('button', { name: '커뮤니티 이용에 동의' }).click()
    await expect(state.getByText('동의함', { exact: true })).toBeVisible()
  }
  const student = await loginStudent(browser, parentPage, nickname, `색 확인 ${prefix}`)
  await parentContext.close()
  return { nickname, ...student }
}

/** 방 그림 면(놓인 방 소품) 배경 색 */
const decorPaint = (page: Page, scope: string) => page.locator(`${scope} [data-decor]`).evaluateAll((els) => els.map((e) => getComputedStyle(e).backgroundColor))
const isDecorSpots = (r: Response, method: string) => new URL(r.url()).pathname.endsWith('/students/me/room/decor-spots') && r.request().method() === method

test('#805 방 소품 색: 고르기 → 저장 → 다시 들어오기(PIN) → DB → 친구 방', async ({ browser }) => {
  test.setTimeout(600_000)
  const result: Record<string, unknown> = { run: new Date().toISOString(), kind: '모의(대역 compose)' }
  const author = await newStudent(browser, '색작성', true)
  const page = author.page
  try {
    // 친구 공개를 켜고 미션 마무리(+10, 공유 +5)
    await studentMenu(page, '설정')
    const sharing = page.getByRole('region', { name: '친구들에게 내 답 보여 주기' })
    await sharing.getByRole('radio', { name: /친구들에게 보여 줄게요/ }).click()
    await expect(sharing.getByText('친구 공개 켜짐')).toBeVisible()
    await startExtraMission(page, mission)
    await solveNarrative(page, '저는 찬성이에요. 쉬는 시간에 몸을 움직이면 다음 시간에 더 집중할 수 있기 때문이에요.')

    // 내 방 › 방 꾸미기 › 방 소품: 사기 → 놓기
    await studentMenu(page, '내 방')
    await page.getByRole('button', { name: '방 꾸미기', exact: true }).click()
    const drawer = page.getByRole('region', { name: '방 꾸미기' })
    await drawer.getByRole('button', { name: '방 소품', exact: true }).click()
    const card = drawer.locator('.st-decor-card').filter({ hasText: 'E2E 작은 화분' })
    await expect(card).toContainText('놓음 0/0')
    result.pointsBeforeBuy = await drawer.locator('.st-room-points').textContent()
    await card.getByRole('button', { name: /E2E 작은 화분 1개 사기/ }).click()
    await drawer.locator('section[aria-label="방 소품 사기 확인"]').getByRole('button', { name: '포인트로 사기' }).click()
    await expect(card).toContainText('놓음 0/1')
    result.pointsAfterBuy = await drawer.locator('.st-room-points').textContent()
    await card.getByRole('button', { name: 'E2E 작은 화분 놓기' }).click()

    // 색: 기본 주황이 눌린 상태 → 하늘
    const colors = drawer.getByRole('group', { name: 'E2E 작은 화분 색' })
    await expect(colors.getByRole('button')).toHaveCount(8)
    result.colorButtons = await colors.getByRole('button').evaluateAll((els) => els.map((e) => ({ name: e.getAttribute('aria-label'), pressed: e.getAttribute('aria-pressed') })))
    await expect(colors.getByRole('button', { name: '주황', exact: true })).toHaveAttribute('aria-pressed', 'true')
    await colors.getByRole('button', { name: '하늘', exact: true }).click()
    await expect(colors.getByRole('button', { name: '하늘', exact: true })).toHaveAttribute('aria-pressed', 'true')
    await drawer.getByRole('button', { name: '다 놓았어요' }).click()

    // 저장: PUT 요청·응답
    const putResponse = page.waitForResponse((r) => isDecorSpots(r, 'PUT'))
    await page.getByRole('button', { name: '저장', exact: true }).click()
    const put = await putResponse
    result.put = { status: put.status(), request: put.request().postDataJSON(), response: await put.json() }
    await expect(page.locator('.st-room-note')).toHaveText('내 방을 저장했어요.')
    expect((result.put as { request: { spots: { color: string }[] } }).request.spots[0].color).toBe('sky')
    expect((result.put as { response: { spots: { color: string }[] } }).response.spots[0].color).toBe('sky')

    // 다른 메뉴 갔다 오기
    await studentMenu(page, '홈')
    await studentMenu(page, '내 방')
    await expect.poll(() => decorPaint(page, '.st-mini-room')).toContain(SKY)
    result.afterMenuRoundTrip = { sky: (await decorPaint(page, '.st-mini-room')).includes(SKY), orange: (await decorPaint(page, '.st-mini-room')).includes(ORANGE) }

    // 새로 고침: 학생 토큰이 메모리에만 있어 PIN 화면 → PIN 다시 입력 → 내 방(GET)
    await page.reload()
    await expect(page.getByRole('button', { name: '4', exact: true })).toBeVisible()
    result.reloadUrl = new URL(page.url()).pathname
    for (const digit of ['4', '8', '3', '1']) await page.getByRole('button', { name: digit, exact: true }).click()
    await page.getByRole('button', { name: /확인|들어가기/ }).click()
    await page.waitForURL('**/student/**')
    const getResponse = page.waitForResponse((r) => isDecorSpots(r, 'GET'))
    await studentMenu(page, '내 방')
    const get = await getResponse
    result.getAfterReload = { status: get.status(), response: await get.json() }
    await expect.poll(() => decorPaint(page, '.st-mini-room')).toContain(SKY)
    result.afterReload = { sky: (await decorPaint(page, '.st-mini-room')).includes(SKY), orange: (await decorPaint(page, '.st-mini-room')).includes(ORANGE) }
    await page.getByRole('button', { name: '방 꾸미기', exact: true }).click()
    await drawer.getByRole('button', { name: '방 소품', exact: true }).click()
    await page.locator('.st-decor-hit').first().click({ force: true })
    result.reopenPressed = await colors.locator('[aria-pressed="true"]').getAttribute('aria-label')
    await page.getByRole('button', { name: '취소', exact: true }).click()

    // DB 행(학생 ID 빼고)
    const row = psql('core_db', `SELECT d.surface, d.cell_col, d.cell_row, d.color FROM room_decor_spot d JOIN student s ON s.id = d.student_id WHERE s.nickname = '${author.nickname}';`)
    result.dbRows = row.split('\n').filter(Boolean).map((l) => { const [surface, col, rowNo, color] = l.split('|'); return { surface, cell_col: Number(col), cell_row: Number(rowNo), color } })

    // 친구 방: 다른 학생이 같은 미션 마무리 → 친구 생각 → 놀러 가기
    const viewer = await newStudent(browser, '색구경', false)
    try {
      await startExtraMission(viewer.page, mission)
      await solveNarrative(viewer.page, '저는 반대예요. 쉬는 시간이 길면 하교 시간이 늦어지기 때문이에요.')
      await studentMenu(viewer.page, '친구 생각')
      await viewer.page.getByRole('group', { name: '어떤 미션을 볼까요?' }).getByRole('button', { name: mission }).click()
      const roomResponse = viewer.page.waitForResponse((r) => /\/community-posts\/[^/]+\/room$/.test(new URL(r.url()).pathname) && r.request().method() === 'GET')
      await viewer.page.getByRole('button', { name: `${author.nickname}의 방에 놀러 가기` }).click()
      const friend = await roomResponse
      const body = await friend.json() as { room?: { decor?: unknown[] } } & Record<string, unknown>
      // 학생 닉네임·ID가 들어갈 수 있는 칸은 키만 남기고 값은 지움
      result.friendRoom = { status: friend.status(), topKeys: Object.keys(body), roomKeys: Object.keys(body.room ?? {}), decor: body.room?.decor ?? null }
      const room = viewer.page.getByRole('region', { name: `${author.nickname}의 방` })
      await expect(room).toBeVisible()
      await expect.poll(() => decorPaint(viewer.page, `[aria-label="${author.nickname}의 방"]`)).toContain(SKY)
      result.friendPaint = { sky: (await decorPaint(viewer.page, `[aria-label="${author.nickname}의 방"]`)).includes(SKY) }
    } finally {
      await viewer.context.close()
    }
  } finally {
    const text = JSON.stringify(result, null, 2).replaceAll(author.nickname, '<작성 학생>')
    writeFileSync(join(process.env.OUT_DIR ?? '.', 'result.json'), text + '\n', 'utf8')
    await author.context.close()
  }
})
