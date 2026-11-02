// #93 관리자 모델 레지스트리·AI 사용량 브라우저 회귀. DEV 서버 + VITE_API_MOCK=true 필요.
// 환경 변수: PLAYWRIGHT_PACKAGE, CHROME_PATH, DEMO_URL
import { createRequire } from 'node:module'
import assert from 'node:assert/strict'
const require = createRequire(process.env.PLAYWRIGHT_PACKAGE ?? import.meta.url)
const { chromium } = require('playwright')
const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || undefined })
const base = process.env.DEMO_URL ?? 'http://127.0.0.1:5175'
const errors = []
const evidence = ['평가셋 ID', '평가셋 버전', '비교 기준 버전', '비교 보고서', '학습·평가 분리 근거', '인용 정확성 근거', '계산 정확성 근거', '사람 검토 기록']
const scope = 'judgment/grade-3/narrative'
try {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  await ctx.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, (r) => r.abort())
  const p = await ctx.newPage()
  p.setDefaultTimeout(12000)
  p.on('pageerror', (e) => errors.push(e.message))
  const card = (name) => p.locator('article').filter({ has: p.getByRole('heading', { name, exact: true }) })

  await p.goto(base + '/login')
  await p.getByLabel('이메일', { exact: true }).fill('admin@example.test')
  await p.getByLabel('비밀번호', { exact: true }).fill('demo-only')
  await p.getByRole('button', { name: '시연 계정으로 로그인' }).click()
  await p.waitForURL(/\/admin\//)

  // 1. 평가 기록(객체)이 있는 버전 목록을 렌더 오류 없이 그린다
  await p.goto(base + '/admin/models')
  await p.getByRole('heading', { name: '모델·프롬프트 버전', exact: true }).waitFor()
  await card('judge · mock-1').getByText('평가셋 ID', { exact: true }).waitFor()
  await card('judge · mock-1').getByText(`평가 범위: ${scope}`, { exact: true }).waitFor()
  await card('judge · mock-1').getByText(`현재 범위: ${scope} · 변경 순번 2`, { exact: true }).waitFor()
  await card('judge · mock-2').getByText('현재 범위: 없음 · 변경 순번 1', { exact: true }).waitFor()
  console.log('PASS 평가 기록이 있는 버전 목록 렌더')

  // 2. 평가 근거 8항목·평가 범위로 등록 (승인자 입력칸 없음)
  assert.equal(await p.getByLabel('승인자', { exact: true }).count(), 0)
  await p.getByLabel('적용 범위', { exact: true }).fill(scope)
  await p.getByLabel('모델 이름', { exact: true }).fill('judge')
  await p.getByLabel('모델 버전', { exact: true }).fill('mock-3')
  for (const label of evidence) await p.getByLabel(label, { exact: true }).fill(`합성 ${label}`)
  await p.getByRole('button', { name: '버전 등록', exact: true }).click()
  await card('judge · mock-3').getByText('PROMPT · REGISTERED · 승인자 미승인', { exact: true }).waitFor()
  console.log('PASS 평가 근거와 함께 등록 · 승인 전 상태')

  // 3. 명시적 승인 후 활성화 → 승인자는 인증 계정, 이전 사용 버전은 사용 안 함
  await p.getByLabel('모델 변경 사유', { exact: true }).fill('비교 검토 후 승인')
  const activate = card('judge · mock-3').getByRole('button', { name: '활성화', exact: true })
  assert.equal(await activate.isDisabled(), true) // 승인 체크 전에는 활성화할 수 없음
  await p.getByLabel('평가 근거와 선택 범위를 확인하고 활성화를 승인합니다.').check()
  await activate.click()
  await card('judge · mock-3').getByText('PROMPT · ACTIVE · 승인자 mock-service-ops', { exact: true }).waitFor()
  await card('judge · mock-1').getByText('PROMPT · INACTIVE · 승인자 mock-reviewer', { exact: true }).waitFor()
  console.log('PASS 승인·활성화')

  // 4. 예전에 승인된 버전으로 되돌리기
  await card('judge · mock-1').getByRole('button', { name: '이 버전으로 되돌리기', exact: true }).click()
  await card('judge · mock-1').getByText('PROMPT · ACTIVE · 승인자 mock-reviewer', { exact: true }).waitFor()
  console.log('PASS 승인 범위 안 되돌리기')

  // 5. AI 사용량: 호출 종류 6가지
  await p.goto(base + '/admin/usage')
  const options = await p.getByLabel('호출 종류', { exact: true }).evaluate((e) => [...e.options].map((o) => o.value))
  for (const t of ['JUDGMENT', 'FOLLOWUP', 'ANALYSIS', 'REPORT_NARRATIVE', 'M2', 'M1']) assert.ok(options.includes(t), t)
  console.log('PASS AI 사용량 호출 종류 6가지')

  assert.deepEqual(errors, [])
  console.log('관리자 모델 브라우저 회귀 5건 통과')
} finally {
  await browser.close()
}
