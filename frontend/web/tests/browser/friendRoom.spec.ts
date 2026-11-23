import { waitForStudentHome } from './studentFixture.ts'
import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

// #709 친구 방 놀러 가기(FN-RET-14, core #708). 친구 생각 글 카드 "놀러 가기" → 같은 자리에 친구 방(주소 그대로).
// 내 뭉치는 문 앞에서 시작, 방 주인 뭉치는 방 가운데, 가까이 가면 인사, 액자는 누르면 크게(회차 상세 없음).
// 꾸미기 서랍·저장·가구 메뉴 발판은 없다. 볼 수 없는 방은 이유 없이 한 문장(404·409), 잠금(403)은 서버 문구.
test.beforeEach(async ({ page }) => {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
})

async function student(page: Page) {
  await page.goto('/student/login')
  await page.getByRole('button', { name: '가상 학생으로 PIN 로그인 준비', exact: true }).click()
  await expect(page.getByRole('button', { name: '5', exact: true })).toBeVisible()
  for (const digit of ['5', '0', '9', '0']) await page.getByRole('button', { name: digit, exact: true }).click()
  await page.getByRole('button', { name: /확인|들어가기/ }).click()
  await waitForStudentHome(page)
  // 월~목 마친 금요일(친구 생각은 마무리한 미션에서만 열림)
  await page.evaluate(async () => {
    const student = '/src/mocks/handlers/student.ts', state = '/src/mocks/fixtures/themeState.ts', cache = '/src/data/queryClient.ts'
    const { mockStudent } = await import(student)
    const { applyMockWeek } = await import(state)
    const { queryClient } = await import(cache)
    await applyMockWeek(mockStudent(), { weekday: 4, days: 'DDDD' }, false)
    await queryClient.invalidateQueries()
  })
  await expect(page.locator('.sh-title')).toBeVisible()
  await page.getByRole('navigation').getByRole('button', { name: '친구 생각', exact: true }).first().click()
  await expect(page.getByRole('heading', { name: /친구\s*생각/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /의 방에 놀러 가기$/ }).first()).toBeVisible()
}

/** 목업 친구 글을 바꾼다(작성자가 공개를 끔, 내가 안 마친 미션 글 등) */
async function editPosts(page: Page, nickname: string, change: 'hide' | 'lock') {
  await page.evaluate(async ({ nickname, change }) => {
    const fixtures = '/src/mocks/fixtures/retention.ts', student = '/src/mocks/handlers/student.ts'
    const { retentionState } = await import(fixtures)
    const { mockStudent, mockStudentHome } = await import(student)
    const open = (await mockStudentHome(mockStudent())).missions.find((m: { status: string }) => m.status !== 'COMPLETED')
    for (const post of retentionState.posts.filter((x: { nickname: string }) => x.nickname === nickname)) {
      if (change === 'hide') post.status = 'HIDDEN_SETTING'
      else post.missionId = open.id
    }
  }, { nickname, change })
}

const visit = (page: Page, nickname: string) => page.getByRole('button', { name: `${nickname}의 방에 놀러 가기` })
const back = (page: Page) => page.getByRole('button', { name: /친구 생각으로 돌아가기/ })

test('친구 생각 → 놀러 가기: 친구가 꾸민 방·방 주인 뭉치·액자, 꾸미기·메뉴는 없고 돌아오면 그대로 @responsive', async ({ page }) => {
  await student(page)
  const firstMission = page.getByRole('group', { name: '어떤 미션을 볼까요?' }).getByRole('button').first()
  await expect(firstMission).toHaveAttribute('aria-pressed', 'true')
  const order = await page.getByRole('button', { name: /의 방에 놀러 가기$/ }).evaluateAll((els) => els.map((e) => e.getAttribute('aria-label')))
  const box = await visit(page, '하늘별').boundingBox()
  expect(box!.height).toBeGreaterThanOrEqual(44)

  await visit(page, '하늘별').click()
  await expect(page.getByRole('heading', { name: '하늘별의 방에 놀러 왔어요' })).toBeVisible()
  const room = page.getByRole('region', { name: '하늘별의 방' })
  await expect(room).toBeVisible()
  await expect(room.locator('.st-friend-name')).toHaveText('하늘별')
  await expect(room.getByRole('button', { name: /^액자 크게 보기: / })).toHaveCount(2)
  // 내 방에만 있는 것: 꾸미기 서랍·저장, 가구 이름표·발판 메뉴, 추억 앨범 단추
  await expect(page.getByRole('button', { name: '방 꾸미기' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '저장' })).toHaveCount(0)
  await expect(room.getByRole('button', { name: /오늘 문제|옷 갈아입기|내 공책|추억 앨범|친구 생각 보기/ })).toHaveCount(0)
  await expect(room.locator('.st-room-bubble')).toHaveCount(0)
  // 친구 생각 화면은 숨겨 둘 뿐(돌아오면 그대로)
  await expect(page.getByRole('heading', { name: /친구\s*생각/ })).toBeHidden()
  // 친구가 놓은 방 소품(#705·#723): 목업 하늘별 방의 큰 화분·러그·쿠션 소파·줄 조명·시계
  await expect(room.locator('[data-decor]').first()).toBeAttached()
  expect(await room.locator('[data-decor]').count()).toBeGreaterThan(10)
  // 친구가 고른 색으로 그린다(#805, core #758): 왼쪽 벽 시계 분홍(기본 하늘), 동그란 러그 분홍(연한 분홍 %23FFE3EC, 기본 하늘이면 %23DDEEFB), 쿠션 소파 하늘
  const paint = await room.locator('[data-decor]').evaluateAll((els) => els.map((e) => `${getComputedStyle(e).backgroundColor} ${e.getAttribute('style') ?? ''}`).join(' | '))
  expect(paint).toContain('rgb(247, 174, 196)')
  expect(paint).toContain('%23FFE3EC')
  expect(paint).not.toContain('%23DDEEFB')
  expect(paint).toContain('rgb(156, 203, 239)')
  // 방 칸이 화면 폭을 넘지 않음
  const holder = await room.locator('.st-room-holder').boundingBox()
  expect(holder!.x + holder!.width).toBeLessThanOrEqual(page.viewportSize()!.width)

  await back(page).click()
  await expect(page.getByRole('heading', { name: /친구\s*생각/ })).toBeVisible()
  await expect(firstMission).toHaveAttribute('aria-pressed', 'true')
  expect(await page.getByRole('button', { name: /의 방에 놀러 가기$/ }).evaluateAll((els) => els.map((e) => e.getAttribute('aria-label')))).toEqual(order)
})

test('내 뭉치는 문 앞에서 시작하고, 방 주인에게 걸어가 멈추면 세 문구 중 하나로 인사한다', async ({ page }) => {
  await student(page)
  await visit(page, '구름빵').click()
  const room = page.getByRole('region', { name: '구름빵의 방' })
  const stage = room.getByRole('group', { name: /구름빵의 방 그림/ })
  await expect(stage).toBeVisible()
  await expect(room.locator('.st-room-bubble')).toHaveCount(0)
  // 방향키 왼쪽 = 문 앞에서 방 가운데 쪽(보는 각도 기준)
  await stage.focus()
  await page.keyboard.down('ArrowLeft')
  await page.waitForTimeout(1600)
  await page.keyboard.up('ArrowLeft')
  await expect(room.locator('.st-room-bubble')).toHaveText(/^(놀러 와 줘서 고마워!|내 방 어때\? 천천히 구경해!|액자도 구경해 봐! 내가 모은 거야\.)$/)
})

test('액자를 누르면 방 위에 크게, 회차 상세는 없고 Esc·바깥 누르기로 닫으면 초점이 액자로 @responsive', async ({ page }) => {
  await student(page)
  await visit(page, '하늘별').click()
  const frame = page.getByRole('button', { name: '액자 크게 보기: 잃어버린 지도 조각' })
  await frame.click()
  const dialog = page.getByRole('dialog', { name: '잃어버린 지도 조각' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('button', { name: '닫기' })).toBeFocused()
  await expect(dialog.locator('img')).toHaveAttribute('src', /past-map/)
  // 회차 상세(문제·답·정답)로 가는 것이 없다
  await expect(dialog.getByText(/문제|정답|답/)).toHaveCount(0)
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(frame).toBeFocused()

  await frame.click()
  await expect(dialog).toBeVisible()
  // 방 칸 모서리는 둥글게 잘려 있어 왼쪽 가장자리 가운데(창 바깥)를 누른다
  const backdrop = page.locator('.st-friend-frame-backdrop')
  const size = await backdrop.boundingBox()
  await backdrop.click({ position: { x: 5, y: size!.height / 2 } })
  await expect(dialog).toHaveCount(0)

  // 그림 없는 액자는 풍경 그림으로
  await back(page).click()
  await visit(page, '초록콩').click()
  await page.getByRole('button', { name: '액자 크게 보기: 숲속 발명 대회' }).click()
  await expect(page.getByRole('dialog', { name: '숲속 발명 대회' }).locator('svg.st-room-scene')).toBeVisible()
})

test('볼 수 없는 방은 이유 없이 한 문장, 돌아가면 그 글이 목록에서 빠진다. 잠긴 미션은 서버 문구 @responsive', async ({ page }) => {
  await student(page)
  await editPosts(page, '하늘별', 'hide')
  await visit(page, '하늘별').click()
  await expect(page.getByRole('alert')).toContainText('지금은 이 친구 방에 놀러 갈 수 없어요.')
  await expect(page.getByRole('alert')).not.toContainText(/공개|동의|숨김/)
  await expect(page.getByRole('region', { name: '하늘별의 방' })).toHaveCount(0)
  await back(page).click()
  await expect(visit(page, '하늘별')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /의 방에 놀러 가기$/ })).toHaveCount(2)

  await editPosts(page, '초록콩', 'lock')
  await visit(page, '초록콩').click()
  await expect(page.getByRole('alert')).toHaveText('이 미션을 마무리하면 친구들 생각을 볼 수 있어요.')
})
