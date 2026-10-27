import { createRequire } from 'node:module'
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
const require = createRequire(process.env.PLAYWRIGHT_PACKAGE ?? import.meta.url)
const { chromium } = require('playwright')
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || undefined,
})
const base = process.env.DEMO_URL ?? 'http://127.0.0.1:5175',
  out = process.env.QA_OUTPUT_DIR
if (out) await mkdir(out, { recursive: true })
const checked = [],
  errors = []
async function check(name, run, options = {}) {
  if (process.env.QA_FILTER && !name.includes(process.env.QA_FILTER)) return
  const context = await browser.newContext({ viewport: { width: 1024, height: 768 }, ...options })
  await context.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, (route) => route.abort())
  const p = await context.newPage()
  p.setDefaultTimeout(12000)
  p.on('pageerror', (e) => errors.push(e.message))
  try {
    await run(p)
    checked.push(name)
    console.log('PASS ' + name)
  } catch (e) {
    if (out)
      await p.screenshot({
        path: path.join(out, 'failed-' + checked.length + '.jpg'),
        type: 'jpeg',
      })
    console.error((await p.locator('body').innerText()).slice(-5000))
    throw e
  } finally {
    await context.close()
  }
}
async function parent(p, admin = false) {
  // 로그인 없이 학생 경로를 열면 학생 로그인(기기·PIN)으로 보낸다(#61·#59). 학부모는 /login에서 들어온다.
  await p.goto(base + '/student/missions', { waitUntil: 'domcontentloaded' })
  await p.waitForURL('**/student/login')
  await p.goto(base + '/login', { waitUntil: 'domcontentloaded' })
  if (admin) await p.getByLabel('이메일', { exact: true }).fill('admin@example.test')
  await p.getByRole('button', { name: '시연 계정으로 로그인' }).click()
  await p.waitForURL(admin ? /\/admin\/home(?:\?|$)/ : /\/parent\/journal(?:\?|$)/)
}
async function student(p, grade5 = false) {
  await parent(p)
  if (grade5) await p.getByLabel('자녀 선택', { exact: true }).selectOption('demo-doyun')
  await p.getByRole('button', { name: '이 자녀로 학습 시작' }).click()
  await p.waitForURL('**/student/home')
  await p.getByRole('heading', { name: /^학습 홈/ }).waitFor()
}
async function open(p, title) {
  await p.getByRole('button', { name: '미션 고르기', exact: true }).click()
  const card = p
    .getByRole('article')
    .filter({ has: p.getByRole('heading', { name: title, exact: true }) })
  await card.getByRole('button', { name: '미션 열기' }).click()
  await p.getByRole('button', { name: '작성하기 · 진행 중이면 이어서' }).click()
  await p.waitForURL('**/student/attempts/*')
  await p.getByRole('region', { name: '미션 작성기' }).waitFor()
}
async function saved(p) {
  await p.getByText('초안 저장 완료(모의)', { exact: true }).waitFor()
}
async function submit(p) {
  await saved(p)
  await p.getByRole('button', { name: '다 썼어요', exact: true }).click()
}
async function finish(p) {
  await p.getByRole('button', { name: '이대로 돌아보기', exact: true }).click()
  await p.getByRole('button', { name: '돌아보기 남기기' }).waitFor()
  await p.getByRole('button', { name: '돌아보기 남기기' }).click()
  await p.getByRole('button', { name: '보통이에요' }).click()
  await p.getByRole('button', { name: '돌아보기 저장하고 완료' }).click()
  await p.waitForURL('**/student/journal')
}
try {
  await check('미인증·역할 가드·학부모/관리자 시작 URL', async (p) => {
    await parent(p)
    await p.goto(base + '/admin/home', { waitUntil: 'domcontentloaded' })
    await p.waitForURL(/\/parent\/journal(?:\?|$)/)
    assert.equal(await p.locator('[data-role-layout="admin"]').count(), 0)
    await p.getByRole('button', { name: '로그아웃', exact: true }).click()
    await p.waitForURL('**/login')
    await p.getByLabel('이메일', { exact: true }).fill('admin@example.test')
    await p.getByRole('button', { name: '시연 계정으로 로그인' }).click()
    await p.waitForURL('**/admin/home')
    await p.getByRole('heading', { name: '관리자 운영 화면' }).waitFor()
    // 주소를 직접 열면(새로고침) 학생 경로는 학생 로그인으로 보낸다(#61). 관리자 세션으로 학생 화면을 열지 않는다.
    await p.goto(base + '/student/home', { waitUntil: 'domcontentloaded' })
    await p.waitForURL('**/student/login')
    assert.equal(await p.getByRole('navigation', { name: '학생 메뉴' }).count(), 0)
  })
  await check('학생 홈 QueryState 5종과 retryable 재시도', async (p) => {
    await student(p)
    for (const [scenario, state] of [
      ['home-empty', 'NO_RECORD'],
      ['home-small', 'INSUFFICIENT_SAMPLE'],
      ['home-processing', 'PROCESSING'],
      ['home-fail', 'FAILED'],
    ]) {
      await p.getByLabel('상태 시연').selectOption(scenario)
      await p.locator(`[data-query-state="${state}"]`).waitFor()
      if (state === 'FAILED') {
        await p.getByRole('button', { name: '다시 시도', exact: true }).click()
        await p.getByText('QUERY_FAILED', { exact: true }).waitFor()
      }
    }
    await p.getByLabel('상태 시연').selectOption('normal')
    await p.getByRole('heading', { name: '생각 지도', exact: true }).waitFor()
  })
  await check('초안만 있는 시도 이어하기·새로고침 복원·학생 메모·브라우저 뒤로가기', async (p) => {
    await student(p)
    await open(p, '도서관에 만화책을 더 둘까요?')
    await p.getByLabel('내 생각과 까닭').fill('새로고침 후에도 유지할 초안입니다.')
    await saved(p)
    await p.getByRole('button', { name: '생각 메모', exact: true }).click()
    await p.getByTestId('private-memo').fill('나만 보는 메모')
    await saved(p)
    await p.getByRole('button', { name: '공책으로', exact: true }).click()
    await p.getByRole('button', { name: '생각 지도', exact: true }).click()
    await p.getByRole('button', { name: '이어서 작성하기' }).click()
    await p.getByLabel('내 생각과 까닭').waitFor()
    assert.equal(
      await p.getByLabel('내 생각과 까닭').inputValue(),
      '새로고침 후에도 유지할 초안입니다.',
    )
    // 학생은 새로고침하면 다시 로그인한다(#61). 다시 들어와 이어 쓰면 서버의 초안이 그대로 있어야 한다.
    await p.reload()
    await p.waitForURL('**/student/login')
    await student(p)
    await p.getByRole('button', { name: '이어서 작성하기' }).click()
    await p.getByLabel('내 생각과 까닭').waitFor()
    assert.equal(
      await p.getByLabel('내 생각과 까닭').inputValue(),
      '새로고침 후에도 유지할 초안입니다.',
    )
    await p.getByRole('button', { name: '생각 메모', exact: true }).click()
    assert.equal(await p.getByTestId('private-memo').inputValue(), '나만 보는 메모')
    await p.getByRole('button', { name: '답변 쓰기', exact: true }).click()
    assert.equal(
      await p.evaluate(() =>
        Object.values(sessionStorage).some(
          (s) => s.includes('msw-access-') || s.includes('demo-only'),
        ),
      ),
      false,
    )
    await p.getByLabel('상태 시연').selectOption('draft-fail')
    await p.getByLabel('내 생각과 까닭').fill('저장 실패 상태의 입력도 보존합니다.')
    await p.getByText('초안 저장 실패 · 입력은 유지됩니다.', { exact: true }).waitFor()
    await p.goBack()
    await p.getByRole('dialog', { name: '아직 저장하지 못한 입력이 있어요.' }).waitFor()
    await p.getByRole('button', { name: '계속 작성', exact: true }).click()
    assert.equal(
      await p.getByLabel('내 생각과 까닭').inputValue(),
      '저장 실패 상태의 입력도 보존합니다.',
    )
  })
  for (const [type, title, field, target] of [
    ['NARRATIVE', '도서관에 만화책을 더 둘까요?', '내 생각과 까닭', 'text'],
    ['SOLUTION_STEPS', '같은 수를 다르게 세기', '풀이 2', 'step:1'],
    ['ESSAY', '도서관에 만화책을 더 둘까요?', '까닭 2', 'reason:1'],
  ]) await check(type + ' 메모 대상 선택·기존 답 덧붙이기·원본 보존', async (p) => {
    await student(p, type === 'ESSAY')
    await open(p, title)
    await p.getByLabel(field, { exact: true }).fill('기존에 쓴 답')
    await saved(p)
    await p.getByRole('button', { name: '생각 메모', exact: true }).click()
    assert.equal(await p.getByRole('button', { name: '글 메모 전체를 답변으로 옮기기' }).isDisabled(), true)
    await p.getByTestId('private-memo').fill('이 부분을 덧붙입니다.')
    await saved(p)
    await p.getByLabel('옮길 답변 칸', { exact: true }).selectOption(target)
    await p.getByRole('button', { name: '글 메모 전체를 답변으로 옮기기' }).click()
    assert.equal(await p.getByLabel(field, { exact: true }).inputValue(), '기존에 쓴 답\n이 부분을 덧붙입니다.')
    if (type === 'ESSAY') assert.equal(await p.getByLabel('까닭 1', { exact: true }).inputValue(), '')
    if (type === 'SOLUTION_STEPS') assert.equal(await p.getByLabel('풀이 1', { exact: true }).inputValue(), '')
    await saved(p)
    await p.getByRole('button', { name: '생각 메모', exact: true }).click()
    assert.equal(await p.getByTestId('private-memo').inputValue(), '이 부분을 덧붙입니다.')
  })
  await check('메모 길이 초과 거부·빈 답 보존·선택형 자동 변환 없음', async (p) => {
    await student(p)
    await open(p, '같은 수를 다르게 세기')
    await p.getByRole('button', { name: '생각 메모', exact: true }).click()
    await p.getByTestId('private-memo').fill('긴 메모입니다.'.repeat(20))
    await saved(p)
    await p.getByLabel('옮길 답변 칸').selectOption('finalAnswer')
    await p.getByRole('button', { name: '글 메모 전체를 답변으로 옮기기' }).click()
    await p.getByRole('alert').filter({ hasText: '120자까지' }).waitFor()
    assert.equal(await p.getByTestId('private-memo').inputValue(), '긴 메모입니다.'.repeat(20))
    await p.getByRole('button', { name: '답변 쓰기', exact: true }).click()
    assert.equal(await p.getByLabel('최종 답', { exact: true }).inputValue(), '')
    await p.getByRole('button', { name: '공책으로', exact: true }).click()
    await open(p, '같은 날 심었는데')
    await p.getByRole('button', { name: '생각 메모', exact: true }).click()
    await p.getByText('글 메모를 선택 답으로 자동 변환하지 않습니다.', { exact: false }).waitFor()
    assert.equal(await p.getByRole('button', { name: '글 메모 전체를 답변으로 옮기기' }).count(), 0)
  })
  await check('제출 뒤 메모로 제출 답을 변경할 수 없음', async (p) => {
    await student(p)
    await open(p, '도서관에 만화책을 더 둘까요?')
    await p.getByLabel('내 생각과 까닭').fill('그림과 글을 함께 읽으면 내용을 이해하기 쉬워요.')
    await p.getByRole('button', { name: '생각 메모', exact: true }).click()
    await p.getByTestId('private-memo').fill('아직 제출하지 않은 별도 생각')
    await saved(p)
    await p.getByRole('button', { name: '답변 쓰기', exact: true }).click()
    await submit(p)
    await p.getByRole('button', { name: '이대로 돌아보기', exact: true }).waitFor()
    await p.getByRole('button', { name: '생각 메모', exact: true }).click()
    assert.equal(await p.getByRole('button', { name: '글 메모 전체를 답변으로 옮기기' }).isDisabled(), true)
  })
  const cases = [
    ['NARRATIVE', '도서관에 만화책을 더 둘까요?'],
    ['SOLUTION_STEPS', '같은 수를 다르게 세기'],
    ['CHOICE', '같은 날 심었는데'],
    ['ORDERING', '씨앗의 자라는 순서'],
    ['CLASSIFICATION', '이 물건은 어디에 넣을까요?'],
    ['ESSAY', '도서관에 만화책을 더 둘까요?'],
  ]
  for (const [type, title] of cases)
    await check(type + ' 작성·제출·근거·마무리·돌아보기', async (p) => {
      await student(p, type === 'ESSAY')
      if (['ORDERING', 'CLASSIFICATION'].includes(type))
        await p.getByLabel('상태 시연').selectOption('input-fixtures')
      await open(p, title)
      await p.getByLabel('상태 시연').selectOption('partial')
      await p.getByRole('button', { name: '다 썼어요', exact: true }).click()
      await p.getByText('ANSWER_INCOMPLETE', { exact: true }).waitFor()
      if (type === 'NARRATIVE')
        await p.getByLabel('내 생각과 까닭').fill('그림과 글이 함께 있으면 이해하기 쉬워요.')
      if (type === 'SOLUTION_STEPS') {
        await p.getByLabel('최종 답', { exact: true }).fill('6')
        await p.getByLabel('풀이 1', { exact: true }).fill('3+3으로 구했어요.')
      }
      if (type === 'CHOICE')
        await p.getByRole('button', { name: '잎의 색과 크기', exact: true }).click()
      if (type === 'ORDERING')
        for (const label of ['씨앗을 심어요', '싹이 나요', '잎이 자라요'])
          await p.getByRole('button', { name: label, exact: true }).click()
      if (type === 'CLASSIFICATION')
        for (const [label, group] of [
          ['철 못', 'magnetic'],
          ['종이', 'other'],
          ['철 클립', 'magnetic'],
        ])
          await p.getByLabel(label, { exact: true }).selectOption(group)
      if (type === 'ESSAY')
        for (const [label, text] of [
          ['내 주장', '만화책을 늘리면 좋겠어요.'],
          ['까닭 1', '그림으로 이해할 수 있어요.'],
          ['까닭 2', '책을 좋아하게 될 수 있어요.'],
          ['다른 의견에 답하기', '글책도 함께 두면 좋겠어요.'],
        ])
          await p.getByLabel(label, { exact: true }).fill(text)
      await p.getByLabel('보호자가 아이의 말을 그대로 적었어요.').check()
      await saved(p)
      const response = p.waitForResponse(
        (r) =>
          r.url().endsWith('/answers') && r.request().method() === 'POST' && r.status() === 201,
      )
      await submit(p)
      const submitted = await response
      assert.equal(submitted.request().postDataJSON().inputType, type)
      assert.equal(submitted.request().postDataJSON().dictatedByGuardian, true)
      assert.equal('memo' in submitted.request().postDataJSON(), false)
      await p.locator('[data-evidence-verified="true"]').waitFor()
      await p.getByRole('button', { name: '이대로 돌아보기' }).waitFor()
      assert.equal(await p.getByRole('list', { name: '마무리 체크리스트' }).count(), 0)
      if (out && type === 'NARRATIVE')
        await p.screenshot({
          path: path.join(out, 'tablet-feedback.jpg'),
          type: 'jpeg',
          quality: 88,
        })
      await finish(p)
      assert.equal(await p.locator('.ux-answer-fields').count(), 0)
    })
  for (const scenario of [
    'correct',
    'rethink',
    'held',
    'running',
    'finish-unmet',
    'submit-fail',
    'ai-fail',
  ])
    await check('상태 시나리오 ' + scenario, async (p) => {
      await student(p)
      await open(p, '도서관에 만화책을 더 둘까요?')
      await p.getByLabel('상태 시연').selectOption(scenario)
      const calls = []
      p.on('request', (r) => {
        if (r.url().endsWith('/answers'))
          calls.push({ key: r.headers()['idempotency-key'], body: r.postData() })
      })
      await p.getByLabel('내 생각과 까닭').fill('근거를 덧붙여 적은 내 생각입니다.')
      await submit(p)
      if (scenario === 'submit-fail') {
        await p.getByText('ANSWER_SAVE_FAILED', { exact: true }).waitFor()
        await p.getByRole('button', { name: '다시 시도', exact: true }).click()
      }
      if (scenario === 'ai-fail') {
        await p.getByRole('button', { name: '피드백만 다시 요청' }).waitFor()
        await p.getByRole('button', { name: '피드백만 다시 요청' }).click()
      }
      await p.getByRole('button', { name: '이대로 돌아보기' }).waitFor()
      if (scenario === 'submit-fail') {
        assert.equal(calls.length, 2)
        assert.equal(calls[0].key, calls[1].key)
        assert.equal(calls[0].body, calls[1].body)
      } else assert.equal(calls.length, 1)
      if (scenario === 'finish-unmet') {
        await p.getByRole('button', { name: '이대로 돌아보기' }).click()
        await p.getByText('REVEAL_CONDITION_UNMET', { exact: true }).waitFor()
        assert.equal(await p.getByRole('list', { name: '마무리 체크리스트' }).count(), 0)
        assert.equal(await p.getByRole('button', { name: '돌아보기 남기기' }).count(), 0)
      }
      if (scenario === 'rethink')
        assert.ok((await p.locator('.ux-evidence').innerText()).includes('다시 생각'))
      if (scenario === 'held')
        await p.getByText('판정 보류 · 답변은 기록했어요.', { exact: true }).waitFor()
      if (scenario === 'correct') await p.getByText('정답을 확인했어요.', { exact: true }).waitFor()
    })
  await check(
    '움직임 줄이기 정적 대체·모바일 제출 버튼 접근',
    async (p) => {
      await student(p)
      await open(p, '같은 수를 다르게 세기')
      assert.equal(await p.locator('.ux-scene').getAttribute('data-motion'), 'static')
      await p.getByLabel('최종 답', { exact: true }).fill('6')
      await p.getByLabel('풀이 1', { exact: true }).fill('풀이')
      await saved(p)
      await p.getByLabel('풀이 1', { exact: true }).focus()
      await p.evaluate(() => scrollTo(0, document.body.scrollHeight))
      const b = await p.getByRole('button', { name: '다 썼어요', exact: true }).boundingBox()
      assert.ok(b.y >= 0 && b.y + b.height <= 500)
      assert.equal(await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
    },
    { viewport: { width: 390, height: 500 }, reducedMotion: 'reduce' },
  )
  await check('학생 토큰 만료는 갱신 없이 학생 로그인으로·보호 화면 가드', async (p) => {
    await student(p)
    // 학생 세션은 refresh를 쓰지 않는다(#61, API 명세 3.11). 만료되면 학생 로그인으로 보낸다.
    await p.getByLabel('상태 시연').selectOption('token-expired')
    await p.waitForURL('**/student/login')
    assert.equal(await p.getByRole('navigation', { name: '학생 메뉴' }).count(), 0)
    await p.goto(base + '/student/journal', { waitUntil: 'domcontentloaded' })
    await p.waitForURL('**/student/login')
  })
  assert.deepEqual(errors, [])
  if (out)
    await writeFile(
      path.join(out, 'results.json'),
      JSON.stringify({ checked, pageErrors: errors }, null, 2),
    )
  console.log(JSON.stringify({ passed: checked.length, pageErrors: errors }, null, 2))
} finally {
  await browser.close()
}
