// 운영 빌드 화면 + HTTP 응답 대역. 실제 core/LLM 종단 검증과 구분한다.
import { createRequire } from 'node:module'
import { createServer } from 'node:http'
import { readFile, mkdir } from 'node:fs/promises'
import { extname, resolve, sep } from 'node:path'
import assert from 'node:assert/strict'
const require = createRequire(process.env.PLAYWRIGHT_PACKAGE ?? import.meta.url)
const { chromium } = require('playwright')
const root = resolve('dist')
const server = createServer(async (req, res) => {
  try {
    const target = resolve(root, '.' + new URL(req.url, 'http://localhost').pathname)
    if (!target.startsWith(root + sep) && target !== root) return res.writeHead(403).end()
    let data, extension
    try { data = await readFile(target); extension = extname(target) }
    catch { data = await readFile(resolve(root, 'index.html')); extension = '.html' }
    res.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' })[extension] ?? 'application/octet-stream')
    res.end(data)
  } catch { res.writeHead(500).end() }
})
await new Promise((done) => server.listen(0, '127.0.0.1', done))
const origin = `http://127.0.0.1:${server.address().port}`
const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || undefined })
const checked = [], errors = []
const defaults = { sectionOrder: ['thinkingTypes', 'changes', 'reflections', 'quotes', 'narrative', 'eveningQuestion'], highlightMetrics: [], tone: 'DEFAULT' }
const changed = { sectionOrder: ['reflections', 'thinkingTypes', 'changes', 'quotes', 'narrative', 'eveningQuestion'], highlightMetrics: ['ATTEMPTS'], tone: 'CONCISE' }
async function check(name, run, free = false) {
  const context = await browser.newContext({ serviceWorkers: 'block' })
  const state = { mode: 'normal', confirms: [], proposals: [], settings: defaults, revision: 0, conversations: [] }
  await context.route(/https:\/\/fonts\./, (route) => route.abort())
  const page = await context.newPage()
  page.setDefaultTimeout(10000)
  page.on('pageerror', (e) => errors.push(e.message))
  await context.route('**/api/v1/**', async (route) => {
    const req = route.request(), path = new URL(req.url()).pathname
    const reply = (value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) }).catch(() => {})
    if (path.endsWith('/auth/refresh')) return reply({ accessToken: 'fixture-parent', role: 'PARENT' })
    if (path.endsWith('/me')) return reply({ userId: 'parent', role: 'PARENT', permissions: [], nextAction: 'READY', startPath: '/parent/analysis' })
    if (path.endsWith('/children')) return reply({ items: [{ id: 'child', nickname: '합성학생', grade: 3, birthYear: 2017 }] })
    // 이용권은 entitlement로만 내려온다(#602).
    if (path.endsWith('/entitlement')) return reply({ childId: 'child', product: { id: free ? 'free' : 'premium', code: free ? 'FREE' : 'PREMIUM', name: free ? '무료' : '프리미엄', price: free ? 0 : 14900, billingCycle: free ? 'NONE' : 'MONTHLY', childLimit: 1, active: true, features: {}, limits: {} }, subscriptionId: null, status: free ? 'FREE' : 'ACTIVE', autoRenew: false, periodEnd: null, graceUntil: null, refundPending: false, conversationEnabled: !free, narrativeEnabled: !free })
    if (path.endsWith('/conversations')) {
      if (req.method() === 'POST') {
        const c = { conversationId: `conversation-${state.conversations.length}`, childId: 'child', period: { from: '2026-10-19', to: '2026-10-25' }, messages: [] }
        state.conversations.push(c); return reply(c, 201)
      }
      return reply({ items: state.conversations })
    }
    if (path.endsWith('/report-template/proposals')) {
      state.proposals.push(req.postDataJSON())
      if (state.mode === 'slow') await new Promise((done) => setTimeout(done, 700))
      if (state.mode === 'clarify') return reply({ clarification: '강조할 지표를 알려 주세요.' })
      if (state.mode === 'error') return reply({ title: '설정 요청 실패', status: 502, code: 'AI_UNAVAILABLE' }, 502)
      return reply({ proposalId: 'proposal-id', settings: changed, expiresAt: new Date(Date.now() + (state.mode === 'expired' ? -1000 : 600000)).toISOString() })
    }
    if (path.endsWith('/report-template/confirm')) {
      state.confirms.push(req.postDataJSON())
      if (state.mode === 'conflict') return reply({ title: '변경안을 다시 확인해 주세요.', code: 'TEMPLATE_PROPOSAL_EXPIRED', status: 409 }, 409)
      state.settings = changed; state.revision++
      return reply({ settings: state.settings, revision: state.revision })
    }
    if (path.endsWith('/report-template')) return reply({ settings: state.settings, revision: state.revision })
    const conversation = state.conversations.find((c) => path.endsWith('/' + c.conversationId))
    if (conversation) return reply(conversation)
    return reply({ items: [], unreadCount: 0 })
  })
  try {
    await page.goto(origin + '/parent/analysis?childId=child&from=2026-10-19&to=2026-10-25')
    await page.getByRole('heading', { name: '기록에 물어보기', exact: true }).waitFor()
    if (!free) {
      await page.getByRole('button', { name: '리포트 설정 대화 시작' }).click()
      await page.getByRole('heading', { name: '현재 설정' }).waitFor()
    }
    await run(page, state)
    checked.push(name); console.log('PASS ' + name)
    if (process.env.QA_OUTPUT_DIR) {
      await mkdir(process.env.QA_OUTPUT_DIR, { recursive: true })
      await page.screenshot({ path: resolve(process.env.QA_OUTPUT_DIR, `template-${checked.length}.png`), fullPage: true })
    }
  } catch (e) { console.error((await page.locator('body').innerText()).slice(-3500)); throw e }
  finally { await context.close() }
}
async function propose(page) {
  await page.getByLabel('리포트 변경 요청', { exact: true }).fill('돌아보기를 먼저 보여 주고 간결하게 설명해 주세요')
  await page.getByRole('button', { name: '변경안 확인하기' }).click()
}
try {
  await check('변경안 취소는 미저장이고 명시적 확인 후 다음 생성 적용 안내', async (p, s) => {
    await propose(p)
    await p.getByText('아직 저장되지 않았습니다.', { exact: false }).waitFor()
    assert.equal(s.confirms.length, 0)
    await p.getByRole('button', { name: '변경안 취소' }).click()
    assert.equal(await p.getByRole('button', { name: '확인하고 저장' }).count(), 0)
    assert.equal(s.revision, 0)
    await propose(p)
    await p.getByRole('button', { name: '확인하고 저장' }).click()
    await p.getByText('저장했습니다. 다음 리포트 생성부터 적용됩니다.', { exact: true }).waitFor()
    assert.deepEqual(s.confirms, [{ proposalId: 'proposal-id' }])
    assert.equal(s.revision, 1)
    await p.getByLabel('현재 리포트 설정', { exact: true }).getByText('간결형', { exact: true }).waitFor()
  })
  await check('모호한 요청은 확인 질문만 표시', async (p, s) => {
    s.mode = 'clarify'; await propose(p)
    await p.getByText('강조할 지표를 알려 주세요.', { exact: true }).waitFor()
    assert.equal(await p.getByRole('button', { name: '확인하고 저장' }).count(), 0)
    assert.equal(s.confirms.length, 0)
  })
  await check('만료된 변경안은 저장 차단', async (p, s) => {
    s.mode = 'expired'; await propose(p)
    await p.getByText('변경안이 만료되었습니다. 다시 요청해 주세요.').waitFor()
    assert.equal(await p.getByRole('button', { name: '확인하고 저장' }).isDisabled(), true)
    assert.equal(s.confirms.length, 0)
  })
  await check('요청 실패와 확정 충돌은 성공으로 표시하지 않음', async (p, s) => {
    s.mode = 'error'; await propose(p)
    await p.getByRole('alert').getByText('설정 요청 실패', { exact: true }).waitFor()
    s.mode = 'normal'; await propose(p)
    await p.getByRole('button', { name: '확인하고 저장' }).waitFor()
    s.mode = 'conflict'; await p.getByRole('button', { name: '확인하고 저장' }).click()
    await p.getByRole('alert').getByText('변경안을 다시 확인해 주세요.', { exact: true }).waitFor()
    assert.equal(await p.getByText('저장했습니다. 다음 리포트 생성부터 적용됩니다.', { exact: true }).count(), 0)
    assert.equal(s.revision, 0)
  })
  await check('입력 수정과 대화 전환은 이전 변경안 제거', async (p, s) => {
    await propose(p); await p.getByRole('button', { name: '확인하고 저장' }).waitFor()
    await p.getByLabel('리포트 변경 요청', { exact: true }).fill('다른 요청')
    assert.equal(await p.getByRole('button', { name: '확인하고 저장' }).count(), 0)
    s.mode = 'slow'; await propose(p)
    await p.getByRole('button', { name: '새 대화', exact: true }).click()
    await p.waitForTimeout(900)
    assert.equal(await p.getByRole('button', { name: '확인하고 저장' }).count(), 0)
    assert.equal(s.confirms.length, 0)
  })
  await check('무료 플랜은 설정 요청 입력 없음', async (p, s) => {
    assert.equal(await p.getByRole('button', { name: '리포트 설정 대화 시작' }).count(), 0)
    assert.equal(s.proposals.length, 0)
  }, true)
  assert.deepEqual(errors, [])
  console.log(JSON.stringify({ passed: checked.length, checks: checked }))
} finally { await browser.close(); await new Promise((done) => server.close(done)) }
