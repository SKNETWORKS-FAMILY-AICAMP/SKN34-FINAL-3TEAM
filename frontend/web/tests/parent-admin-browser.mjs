import { createRequire } from 'node:module'
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
const require = createRequire(process.env.PLAYWRIGHT_PACKAGE ?? import.meta.url),
  { chromium } = require('playwright')
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || undefined,
})
const base = process.env.DEMO_URL ?? 'http://127.0.0.1:5175',
  out = process.env.QA_OUTPUT_DIR,
  checked = [],
  errors = [],
  responses = []
if (out) await mkdir(out, { recursive: true })
async function check(name, run, options = {}) {
  if (process.env.QA_FILTER && !name.includes(process.env.QA_FILTER)) return
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 }, ...options }),
    p = await context.newPage()
  // 외부 웹폰트 지연과 무관하게 시스템 대체 글꼴에서도 화면을 검증합니다.
  await context.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, (route) => route.abort())
  p.setDefaultTimeout(12000)
  p.on('pageerror', (e) => errors.push(e.message))
  p.on('response', (r) => {
    if (r.url().includes('/api/v1/'))
      responses.push({
        path: new URL(r.url()).pathname,
        status: r.status(),
        msw: r.fromServiceWorker(),
      })
  })
  try {
    await run(p)
    checked.push(name)
    console.log('PASS ' + name)
  } catch (e) {
    console.error((await p.locator('body').innerText()).slice(-6500))
    if (out)
      await p.screenshot({ path: path.join(out, `failed-${checked.length}.jpg`), type: 'jpeg' })
    throw e
  } finally {
    await context.close()
  }
}
async function login(p, email = 'parent@example.test') {
  await p.goto(base + '/login', { waitUntil: 'domcontentloaded' })
  await p.getByLabel('이메일', { exact: true }).fill(email)
  await p.getByLabel('비밀번호', { exact: true }).fill('demo-only')
  await p.getByRole('button', { name: '시연 계정으로 로그인' }).click()
  await p.waitForURL(/\/(parent\/journal|admin\/home)(\?|$)/)
  if (email === 'parent@example.test')
    await p.getByRole('heading', { name: '서윤의 학습 기록' }).waitFor()
}
const mode = (p, value) => p.getByLabel('상태 시연', { exact: true }).selectOption(value)
const nav = (p, name) => p.getByRole('navigation').getByRole('link', { name, exact: true }).click()
async function ask(p) {
  await p
    .getByLabel('기록에 대한 질문', { exact: true })
    .fill('되묻기를 받고 달라진 점을 보여 주세요.')
  await p.getByRole('button', { name: '기록으로 답변 받기' }).click()
}
try {
  await check('가입 동의 버전·자녀 없음·법정대리인 동의 등록·첫 학습 안내', async (p) => {
    await p.goto(base + '/signup', { waitUntil: 'domcontentloaded' })
    await p.getByLabel('가입 이메일').fill('new-parent@example.test')
    await p.getByLabel('가입 이름').fill('시연 보호자')
    const request = p.waitForRequest((r) => r.url().endsWith('/auth/signup'))
    for (const label of ['이용 안내에 동의합니다.', '개인정보 처리 동의에 동의합니다.'])
      await p.getByLabel(label, { exact: true }).check()
    await p.getByRole('button', { name: '동의하고 등록하기' }).click()
    const body = (await request).postDataJSON()
    assert.equal(body.consents.length, 2)
    assert.ok(body.consents.every((c) => c.agreed && c.version === '1.0'))
    await p.getByRole('button', { name: '로그인하기' }).click()
    await p.getByLabel('이메일', { exact: true }).fill('new-parent@example.test')
    await p.getByRole('button', { name: '시연 계정으로 로그인' }).click()
    await p.getByRole('heading', { name: '먼저 자녀를 등록해 주세요.' }).waitFor()
    await p.getByLabel('자녀 별명', { exact: true }).fill('새싹')
    await p.getByLabel('법정대리인 동의에 동의합니다.', { exact: true }).check()
    await p.getByRole('button', { name: '자녀 등록하기' }).click()
    await p.getByRole('heading', { name: '새싹의 학습 기록' }).waitFor()
    await p.getByText('아직 집계할 기록이 없습니다.', { exact: false }).first().waitFor()
    await p.getByRole('button', { name: '로그아웃', exact: true }).click()
    await p.getByLabel('이메일', { exact: true }).fill('parent@example.test')
    await p.getByLabel('비밀번호', { exact: true }).fill('demo-only')
    await p.getByRole('button', { name: '시연 계정으로 로그인' }).click()
    await p.getByRole('heading', { name: '서윤의 학습 기록' }).waitFor()
    assert.equal(
      await p
        .getByLabel('자녀 선택', { exact: true })
        .getByRole('option', { name: '새싹 · 초3' })
        .count(),
      0,
    )
  })
  await check('신규 가입부터 학습·무료 제한·프리미엄 목업 분석·리포트 다운로드 연속 흐름', async (p) => {
    const email = 'full-flow@example.test',
      answer = '그림과 글을 함께 읽으면 내용을 이해하기 쉬워요.',
      privateMemo = '제출하지 않은 비공개 메모'
    await p.goto(base + '/signup', { waitUntil: 'domcontentloaded' })
    await p.getByLabel('가입 이메일').fill(email)
    await p.getByLabel('가입 이름').fill('연속 시연 보호자')
    await p.getByLabel('이용 안내에 동의합니다.', { exact: true }).check()
    await p.getByLabel('개인정보 처리 동의에 동의합니다.', { exact: true }).check()
    await p.getByRole('button', { name: '동의하고 등록하기' }).click()
    await p.getByRole('button', { name: '로그인하기' }).click()
    await p.getByLabel('이메일', { exact: true }).fill(email)
    await p.getByRole('button', { name: '시연 계정으로 로그인' }).click()
    await p.getByRole('heading', { name: '먼저 자녀를 등록해 주세요.' }).waitFor()
    await p.getByLabel('자녀 별명', { exact: true }).fill('연두')
    await p.getByLabel('법정대리인 동의에 동의합니다.', { exact: true }).check()
    const created = p.waitForResponse((r) => r.url().endsWith('/api/v1/children') && r.request().method() === 'POST')
    await p.getByRole('button', { name: '자녀 등록하기' }).click()
    const child = await (await created).json()
    assert.equal(child.plan, 'FREE')
    await p.getByRole('heading', { name: '연두의 학습 기록' }).waitFor()
    await p.getByRole('button', { name: '이 자녀로 학습 시작' }).click()
    await p.getByRole('button', { name: '미션 고르기', exact: true }).click()
    await p.getByRole('article').filter({ has: p.getByRole('heading', { name: '도서관에 만화책을 더 둘까요?', exact: true }) })
      .getByRole('button', { name: '미션 열기' }).click()
    await p.getByRole('button', { name: '작성하기 · 진행 중이면 이어서' }).click()
    await p.getByLabel('내 생각과 까닭').fill(answer)
    await p.getByRole('button', { name: '생각 메모', exact: true }).click()
    await p.getByTestId('private-memo').fill(privateMemo)
    await p.getByText('초안 저장 완료(모의)', { exact: true }).waitFor()
    await p.getByRole('button', { name: '답변 쓰기', exact: true }).click()
    const submitted = p.waitForRequest((r) => /\/attempts\/[^/]+\/answers$/.test(r.url()) && r.method() === 'POST')
    await p.getByRole('button', { name: '다 썼어요', exact: true }).click()
    assert.equal(JSON.stringify((await submitted).postDataJSON()).includes(privateMemo), false)
    await p.getByRole('button', { name: '이대로 돌아보기', exact: true }).click()
    await p.getByRole('button', { name: '돌아보기 남기기' }).click()
    await p.getByRole('button', { name: '보통이에요' }).click()
    await p.getByRole('button', { name: '돌아보기 저장하고 완료' }).click()
    await p.waitForURL('**/student/journal')
    await p.getByRole('button', { name: '학부모 로그인으로', exact: true }).click()
    await p.getByLabel('이메일', { exact: true }).fill(email)
    await p.getByRole('button', { name: '시연 계정으로 로그인' }).click()
    await p.getByRole('heading', { name: '연두의 학습 기록' }).waitFor()
    await p.getByRole('button', { name: /원문 보기$/ }).click()
    await p.getByRole('dialog').getByText(answer, { exact: true }).waitFor()
    assert.equal((await p.getByRole('dialog').innerText()).includes(privateMemo), false)
    await p.getByRole('button', { name: '창 닫기' }).click()
    await nav(p, '기록에 물어보기')
    await p.getByText('무료 플랜에는 분석 대화가 포함되지 않습니다.', { exact: false }).waitFor()
    // 명시적인 DEV 테스트 설정입니다. 결제 성공이나 무료 체험을 시뮬레이션하지 않습니다.
    assert.equal(await p.evaluate((childId) => {
      let applied = false
      window.addEventListener('sagomungchi:test-child-plan-result', (e) => { applied = e.detail.applied }, { once: true })
      window.dispatchEvent(new CustomEvent('sagomungchi:test-child-plan', { detail: { childId, plan: 'PREMIUM' } }))
      return applied
    }, child.id), true)
    // 정상 조회 재실행으로 서버 fixture의 현재 플랜을 읽습니다. UI 캐시를 직접 조작하지 않습니다.
    await mode(p, 'small')
    await mode(p, 'normal')
    await p.getByLabel('기록에 대한 질문', { exact: true }).waitFor()
    const scope = new URL(p.url()).search
    assert.equal(new URL(p.url()).searchParams.get('childId'), child.id)
    await ask(p)
    await p.getByRole('button', { name: '답변 근거 보기' }).click()
    await p.getByRole('dialog').getByText(answer, { exact: true }).waitFor()
    assert.equal((await p.getByRole('dialog').innerText()).includes(privateMemo), false)
    await p.getByRole('button', { name: '창 닫기' }).click()
    await nav(p, '주간 리포트')
    assert.equal(new URL(p.url()).search, scope)
    await p.locator('article.ws-card').filter({ has: p.getByRole('heading', { name: '2026-10-26 ~ 2026-11-01', exact: true }) })
      .getByRole('button', { name: '리포트 상세 보기' }).click()
    await p.getByRole('heading', { name: '아이의 말', exact: true }).waitFor()
    await p.locator('blockquote').getByText(answer, { exact: true }).waitFor()
    await p.getByRole('button', { name: /근거$/ }).first().click()
    await p.getByRole('dialog', { name: '리포트 항목 근거' }).getByText(answer, { exact: true }).waitFor()
    await p.getByRole('button', { name: '창 닫기' }).click()
    for (const label of ['Markdown 다운로드', 'PDF 다운로드']) {
      const wait = p.waitForEvent('download')
      await p.getByRole('button', { name: label, exact: true }).click()
      const download = await wait
      const stream = await download.createReadStream(), chunks = []
      for await (const chunk of stream) chunks.push(chunk)
      const content = Buffer.concat(chunks).toString('utf8')
      assert.ok(content.startsWith(label.startsWith('PDF') ? '%PDF-1.4' : 'SAGOMUNGCHI - MOCK REPORT ONLY'))
      assert.ok(content.includes(child.id))
      assert.equal(content.includes(privateMemo), false)
    }
  })
  await check('P02 자녀 3명 제한·다른 보호자 기록 거부·기존 학생 연결 미노출', async (p) => {
    await login(p)
    await p.getByRole('button', { name: '자녀 등록', exact: true }).click()
    await p.getByText('다른 보호자가 등록한 학생 연결은 지원하지 않습니다.', { exact: false }).waitFor()
    assert.equal(await p.getByRole('button', { name: '기존 학생 연결', exact: true }).count(), 0)
    const result = await p.evaluate(async () => {
      const { parentApi } = await import('/src/data/parent/api.ts')
      const docs = await parentApi.documents(), consents = docs.items.filter((d) => d.kind === 'GUARDIAN')
        .map((d) => ({ documentId: d.documentId, version: d.version, agreed: true }))
      const third = await parentApi.register({ nickname: '세 번째', grade: 3, birthYear: 2017, consents })
      let limit, foreign
      try { await parentApi.register({ nickname: '네 번째', grade: 3, birthYear: 2017, consents }) }
      catch (e) { limit = { status: e.problem?.status, code: e.problem?.code } }
      try { await parentApi.summary({ childId: 'other-guardian-child', from: '2026-10-20', to: '2026-10-26' }) }
      catch (e) { foreign = { status: e.problem?.status, code: e.problem?.code } }
      return { plan: third.plan, count: (await parentApi.children()).items.length, limit, foreign }
    })
    assert.deepEqual(result, { plan: 'FREE', count: 3,
      limit: { status: 409, code: 'CHILD_LIMIT_REACHED' },
      foreign: { status: 403, code: 'CHILD_NOT_LINKED' } })
  })
  await check('대시보드 Metric·유형 미관찰·기록 원문·자녀 기간 URL 유지', async (p) => {
    await login(p)
    await p.getByText('실제 조회 기간', { exact: false }).waitFor()
    await p.getByText('미관찰', { exact: true }).first().waitFor()
    await p.getByRole('button', { name: /원문 보기$/ }).first().click()
    await p.getByRole('dialog', { name: '학습 기록 원문' }).waitFor()
    await p.getByText('최초 답변', { exact: false }).first().waitFor()
    assert.equal(await p.getByTestId('private-memo').count(), 0)
    await p.getByRole('button', { name: '창 닫기' }).click()
    await p.getByLabel('조회 시작일').fill('2026-10-19')
    await p.getByLabel('조회 종료일').fill('2026-10-25')
    await p.getByRole('button', { name: '기간 적용' }).click()
    await nav(p, '기록에 물어보기')
    assert.ok(p.url().includes('childId=demo-seoyun') && p.url().includes('from=2026-10-19'))
    await p.getByLabel('자녀 선택', { exact: true }).selectOption('demo-doyun')
    await p.getByText('무료 플랜에는 분석 대화가 포함되지 않습니다.', { exact: false }).waitFor()
    assert.equal(await p.getByRole('button', { name: '답변 근거 보기' }).count(), 0)
    await nav(p, '주간 리포트')
    assert.ok(p.url().includes('childId=demo-doyun'))
    await p.getByRole('button', { name: '리포트 상세 보기' }).first().click()
    await p
      .getByText('수치 리포트입니다. 이 자녀의 플랜에는 서술 요약이 포함되지 않습니다.', {
        exact: true,
      })
      .waitFor()
    assert.equal(await p.getByRole('heading', { name: '아이의 말', exact: true }).count(), 0)
    if (out)
      await p.screenshot({ path: path.join(out, 'parent-laptop.jpg'), type: 'jpeg', quality: 88 })
  })
  for (const scenario of ['empty', 'small', 'query-fail', 'unlinked'])
    await check('학부모 상태 ' + scenario, async (p) => {
      await login(p)
      await mode(p, scenario)
      if (scenario === 'query-fail')
        await p.getByText('QUERY_FAILED', { exact: true }).first().waitFor()
      else if (scenario === 'unlinked')
        await p.getByText('CHILD_NOT_LINKED', { exact: true }).first().waitFor()
      else
        await p
          .locator(
            `[data-query-state="${scenario === 'empty' ? 'NO_RECORD' : 'INSUFFICIENT_SAMPLE'}"]`,
          )
          .first()
          .waitFor()
    })
  await check('분석 result 교체·대화 이력·근거 endpoint·삭제/410 이용 불가', async (p) => {
    await login(p)
    await nav(p, '기록에 물어보기')
    await ask(p)
    await p.getByRole('button', { name: '답변 근거 보기' }).waitFor()
    assert.equal(
      await p
        .getByText('대조 전 임시 문장입니다. 아직 확정되지 않았습니다.', { exact: true })
        .count(),
      0,
    )
    await p.getByRole('button', { name: '답변 근거 보기' }).click()
    await p.getByRole('dialog', { name: '분석 답변의 근거' }).waitFor()
    await p.locator('[role=dialog] blockquote').first().waitFor()
    await p.getByRole('button', { name: '창 닫기' }).click()
    await mode(p, 'deleted-evidence')
    await p.getByRole('button', { name: '답변 근거 보기' }).click()
    await p
      .getByText('이용 불가 · 삭제된 근거입니다. 다른 기록으로 대체하지 않습니다.', { exact: true })
      .first()
      .waitFor()
    assert.equal(await p.locator('[role=dialog] blockquote').count(), 0)
    await p.getByRole('button', { name: '창 닫기' }).click()
    await mode(p, 'gone-evidence')
    await p.getByRole('button', { name: '답변 근거 보기' }).click()
    await p.getByText('DATA_UNAVAILABLE', { exact: true }).waitFor()
  })
  await check('clarification 선택 scope·변경된 실제 범위·후속 질문', async (p) => {
    await login(p)
    await nav(p, '기록에 물어보기')
    await mode(p, 'clarification')
    await ask(p)
    await p.getByRole('button', { name: '지난주', exact: true }).click()
    await p.getByRole('button', { name: '답변 근거 보기' }).waitFor()
    await p.getByText('범위가 변경되었습니다.', { exact: false }).waitFor()
    await mode(p, 'normal')
    const followup = p.waitForRequest((r) => /\/conversations\/[^/]+\/messages$/.test(r.url()))
    await ask(p)
    assert.equal((await followup).postDataJSON().scope.from, '2026-10-19')
    await p.getByRole('button', { name: '답변 근거 보기' }).nth(1).waitFor()
  })
  for (const scenario of ['analysis-fail', 'verification-error', 'verification-fallback'])
    await check('분석 예외 ' + scenario, async (p) => {
      await login(p)
      await nav(p, '기록에 물어보기')
      await mode(p, scenario)
      await ask(p)
      if (scenario === 'verification-fallback') {
        await p.getByText('규칙 응답 모드(TEMPLATE)', { exact: false }).waitFor()
      } else {
        await p.getByRole('button', { name: '실패 메시지 재시도', exact: true }).waitFor()
        assert.equal(
          await p
            .getByText('대조 전 임시 문장입니다. 아직 확정되지 않았습니다.', { exact: true })
            .count(),
          0,
        )
        await mode(p, 'normal')
        const request = p.waitForRequest((r) => /\/messages\/[^/]+\/retry$/.test(r.url()))
        await p.getByRole('button', { name: '실패 메시지 재시도', exact: true }).click()
        await request
        await p.getByRole('button', { name: '답변 근거 보기' }).waitFor()
      }
    })
  await check('분석 스트림 이탈 AbortSignal·다른 자녀 결과 비혼합', async (p) => {
    await login(p)
    await p.evaluate(() => {
      window.__analysisAborts = 0
      const original = window.fetch
      window.fetch = (input, init) => {
        if (String(input).match(/\/conversations\/[^/]+\/messages$/))
          init?.signal?.addEventListener(
            'abort',
            () => {
              window.__analysisAborts++
            },
            { once: true },
          )
        return original(input, init)
      }
    })
    await nav(p, '기록에 물어보기')
    await mode(p, 'analysis-slow')
    await ask(p)
    await p
      .getByText('대조 전 임시 문장입니다. 아직 확정되지 않았습니다.', { exact: true })
      .waitFor()
    await p.getByLabel('자녀 선택', { exact: true }).selectOption('demo-doyun')
    await p.waitForFunction(() => window.__analysisAborts > 0)
    await p.getByText('무료 플랜에는 분석 대화가 포함되지 않습니다.', { exact: false }).waitFor()
    assert.equal(await p.getByRole('button', { name: '답변 근거 보기' }).count(), 0)
    await nav(p, '대시보드·공책')
    await p.getByRole('heading', { name: '도윤의 학습 기록' }).waitFor()
  })
  await check('리포트 상세 3.4·항목 근거·재생성 새 판/이전 판·md/pdf 다운로드', async (p) => {
    await login(p)
    await nav(p, '주간 리포트')
    await p.getByRole('button', { name: '리포트 상세 보기' }).first().click()
    await p.getByRole('heading', { name: '리포트 상세', exact: true }).waitFor()
    await p.getByRole('button', { name: /근거$/ }).first().click()
    await p.getByRole('dialog', { name: '리포트 항목 근거' }).waitFor()
    await p.locator('[role=dialog] blockquote').first().waitFor()
    await p.getByRole('button', { name: '창 닫기' }).click()
    await p.getByRole('button', { name: '새 판으로 재생성' }).click()
    await p.getByText('리포트를 생성하고 있습니다.', { exact: false }).waitFor()
    await p
      .getByLabel('리포트 판')
      .getByRole('option', { name: '2판', exact: true })
      .waitFor({ state: 'attached' })
    await p.getByRole('button', { name: 'Markdown 다운로드' }).waitFor()
    await p.getByLabel('리포트 판').selectOption('1')
    await p.getByText(/실제 리포트 기간.*1판/).waitFor()
    await p.getByLabel('리포트 판').selectOption('latest')
    await p.getByRole('button', { name: '새 판으로 재생성' }).click()
    await p.getByText('REPORT_REGENERATION_LIMIT', { exact: true }).waitFor()
    for (const button of ['Markdown 다운로드', 'PDF 다운로드']) {
      const wait = p.waitForEvent('download')
      await p.getByRole('button', { name: button, exact: true }).click()
      const download = await wait
      assert.ok(download.suggestedFilename().endsWith(button === 'PDF 다운로드' ? '.pdf' : '.md'))
    }
  })
  for (const scenario of ['report-running', 'report-failed'])
    await check('리포트 상태 ' + scenario, async (p) => {
      await login(p)
      await nav(p, '주간 리포트')
      await mode(p, scenario)
      await p.getByRole('button', { name: '리포트 상세 보기' }).first().click()
      await p
        .getByText(
          scenario === 'report-running'
            ? '리포트를 생성하고 있습니다. 완료 전 내용을 표시하지 않습니다.'
            : '리포트 생성에 실패했습니다. 기록 없음과는 다릅니다.',
          { exact: true },
        )
        .waitFor()
      assert.equal(await p.getByRole('button', { name: 'PDF 다운로드' }).count(), 0)
    })
  await check('본인·자녀 수정·중요 변경 재확인', async (p) => {
    await login(p)
    await nav(p, '정보 관리')
    await p.getByLabel('새 이름', { exact: true }).fill('수정 보호자')
    await p.getByRole('button', { name: '이름 저장' }).click()
    await p.getByText('현재 이름: 수정 보호자', { exact: true }).waitFor()
    assert.equal(await p.getByRole('button', { name: '자녀 정보 저장' }).isDisabled(), true)
    await p.getByLabel('재확인 비밀번호').fill('demo-only')
    await p.getByRole('button', { name: '본인 재확인' }).click()
    await p.getByRole('button', { name: '자녀 정보 저장' }).isEnabled()
    await p.getByLabel('새 자녀 별명').fill('새 별명')
    await p.getByRole('button', { name: '자녀 정보 저장' }).click()
    await p
      .getByLabel('자녀 선택', { exact: true })
      .getByRole('option', { name: '새 별명 · 초3' })
      .waitFor({ state: 'attached' })
  })
  for (const [account, show, hide] of [
    ['content', '미션 관리', '작업 재처리'],
    ['ops', '작업 재처리', '미션 관리'],
    ['payment', '운영 현황', '오류 신고'],
    ['refund', '운영 현황', '미션 관리'],
  ])
    await check('관리자 권한 ' + account, async (p) => {
      await login(p, account + '@example.test')
      await p.getByRole('navigation').getByRole('link', { name: show, exact: true }).waitFor()
      assert.equal(
        await p.getByRole('navigation').getByRole('link', { name: hide, exact: true }).count(),
        0,
      )
      if (account === 'content') {
        assert.equal(
          await p.evaluate(async () => {
            const { adminApi } = await import('/src/data/admin/api.ts')
            try {
              await adminApi.jobs('', '')
              return 'unexpected-success'
            } catch (e) {
              return e.problem?.code
            }
          }),
          'FORBIDDEN',
        )
        await p.goto(base + '/admin/jobs', { waitUntil: 'domcontentloaded' })
        await p.getByText('FORBIDDEN · 필요한 관리자 권한이 없습니다.', { exact: true }).waitFor()
      }
    })
  await check('운영 요약→실패 목록·재처리 실패/성공·큐·감사·403', async (p) => {
    await login(p, 'ops@example.test')
    await p.getByRole('link', { name: 'REPORT · 실패 1건', exact: false }).click()
    await p.getByRole('button', { name: '작업 상세' }).click()
    await mode(p, 'retry-fail')
    await p.getByRole('button', { name: '작업 재처리', exact: true }).click()
    await p.getByText('재처리 실패 · 완료로 표시하지 않습니다.', { exact: true }).waitFor()
    await mode(p, 'normal')
    await p.getByRole('button', { name: '작업 재처리', exact: true }).click()
    await p.getByText('서버에서 재처리 완료를 확인했습니다.', { exact: true }).waitFor()
    await p.getByRole('button', { name: '창 닫기' }).click()
    await nav(p, '큐·DLQ')
    await p.getByText('report.generate', { exact: true }).waitFor()
    await nav(p, '감사 이력')
    await p.getByText('JOB_RETRY · 성공', { exact: true }).waitFor()
    await mode(p, 'forbidden')
    await p.getByText('FORBIDDEN', { exact: true }).waitFor()
  })
  for (const scenario of ['empty', 'query-fail'])
    await check('관리자 목록 상태 ' + scenario, async (p) => {
      await login(p, 'ops@example.test')
      await nav(p, '작업 재처리')
      await mode(p, scenario)
      if (scenario === 'empty')
        await p.getByText('조건에 맞는 작업이 없습니다.', { exact: true }).waitFor()
      else await p.getByText('QUERY_FAILED', { exact: true }).waitFor()
    })
  await check(
    '미션 작성·기준표 새 버전·미리보기·검토·게시422/성공·중단',
    async (p) => {
      await login(p, 'content@example.test')
      await nav(p, '미션 관리')
      await p.getByRole('button', { name: '새 미션 작성' }).click()
      await p.getByLabel('미션 제목', { exact: true }).fill('새 정원 관찰')
      await p.getByLabel('미션 질문', { exact: true }).fill('두 잎의 차이를 관찰해 설명해 주세요.')
      await p.getByLabel('성취기준', { exact: true }).fill('자체 시연 기준')
      await p.getByRole('button', { name: '미션 초안 저장' }).click()
      await p.getByRole('button', { name: '게시', exact: true }).click()
      await p.getByRole('list', { name: '게시 누락 항목' }).waitFor()
      await p.getByRole('button', { name: '기준표 요소 추가' }).click()
      await p.getByLabel('요소 1 이름', { exact: true }).fill('관찰한 차이')
      await p.getByLabel('예시 답', { exact: true }).fill('한 잎은 넓고 다른 잎은 길쭉합니다.')
      await p.getByLabel('생각 열기 질문', { exact: true }).fill('모양과 크기를 살펴보세요.')
      await p.getByRole('button', { name: '새 기준표 버전 저장' }).click()
      await p.getByRole('button', { name: '검토 요청', exact: true }).click()
      await p.getByRole('button', { name: '현재 버전 검토 승인' }).click()
      await p.getByRole('button', { name: '학생 화면 미리보기' }).click()
      await p.getByRole('dialog', { name: '학생 화면 미리보기' }).waitFor()
      await p.getByLabel('내 생각과 까닭').fill('미리보기 답변')
      await p.getByRole('button', { name: '창 닫기' }).click()
      await p.getByRole('button', { name: '게시', exact: true }).click()
      await p.getByRole('button', { name: '신규 제공 중단' }).waitFor()
      await p.getByRole('button', { name: '신규 제공 중단' }).click()
      await p.getByText('서버 응답 · 비공개', { exact: true }).waitFor()
      if (out)
        await p.screenshot({ path: path.join(out, 'admin-tablet.jpg'), type: 'jpeg', quality: 88 })
    },
    { viewport: { width: 1024, height: 768 } },
  )
  await check('모델 등록·활성화·되돌리기·AI 미측정·신고 열람/정정 감사', async (p) => {
    await login(p, 'ops@example.test')
    await nav(p, '모델·프롬프트')
    await p.getByLabel('모델 버전', { exact: true }).fill('mock-3')
    await p.getByLabel('평가 근거', { exact: true }).fill('고정 평가 자료 비교 시연')
    await p.getByLabel('승인자', { exact: true }).fill('mock-reviewer')
    await p.getByRole('button', { name: '버전 등록', exact: true }).click()
    await p.getByRole('heading', { name: 'judge@mock-3' }).waitFor()
    await p.getByLabel('버전 변경 사유').fill('평가 비교 후 시연 활성화')
    await p
      .locator('article')
      .filter({ has: p.getByRole('heading', { name: 'judge@mock-3' }) })
      .getByRole('button', { name: '활성화', exact: true })
      .click()
    await p
      .getByText('서버에서 활성화를 확인했습니다. 기존 결과는 유지됩니다.', { exact: true })
      .waitFor()
    await p
      .locator('article')
      .filter({ has: p.getByRole('heading', { name: 'judge@mock-1' }) })
      .getByRole('button', { name: '이 버전으로 되돌리기' })
      .click()
    await nav(p, 'AI 사용량')
    await p.getByText('입력 토큰 미측정', { exact: false }).first().waitFor()
    await nav(p, '오류 신고')
    await p.getByRole('button', { name: '신고 상세·연결 기록 열람' }).click()
    await p.getByText('신고 연결 답변 v1', { exact: true }).waitFor()
    await p.getByLabel('검토 사유').fill('자체 예시 판정 검토')
    await p.getByRole('button', { name: '검토 결과 저장' }).click()
    await p.getByLabel('정정 결과').fill('근거 확인 항목 수정')
    await p.getByRole('button', { name: '정정 이력 추가' }).click()
    await p
      .getByText('대화·집계·리포트 반영 확인 대기(목업). 원본 답변은 변경하지 않음.', {
        exact: true,
      })
      .waitFor()
    await p.getByRole('button', { name: '창 닫기' }).click()
    await nav(p, '감사 이력')
    await p.getByText('ERROR_REPORT_VIEW · 성공', { exact: true }).first().waitFor()
    await p.getByText('JUDGMENT_CORRECTION · 성공', { exact: true }).waitFor()
  })
  assert.deepEqual(errors, [])
  assert.ok(responses.length > (process.env.QA_FILTER ? 0 : 80))
  assert.ok(responses.every((r) => r.msw))
  if (out)
    await writeFile(
      path.join(out, 'results.json'),
      JSON.stringify({ checked, errors, responses }, null, 2),
    )
  console.log(
    JSON.stringify(
      { passed: checked.length, pageErrors: errors, apiResponses: responses.length },
      null,
      2,
    ),
  )
} finally {
  await browser.close()
}
