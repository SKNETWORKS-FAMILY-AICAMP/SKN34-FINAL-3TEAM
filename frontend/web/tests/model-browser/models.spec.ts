import { createHash } from 'node:crypto'
import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import type { ModelVersion } from '../../src/domain/admin/operations.ts'
import type { ModelRegistration } from '../../src/domain/admin/modelRegistration.ts'
const scopes = ['judgment/grade-5/essay', 'judgment/grade-6/essay']
const entry = (name = 'm2-klue-essay', version = '3.1', evaluatedScopes = scopes): ModelRegistration => ({ kind: 'MODEL', name, version, artifactUri: `s3://<버킷>/models/${name}/${version}/`, evaluation: {
  datasetId: '합성 평가셋', datasetVersion: '합성 2026', baselineVersion: '2.0', comparisonReport: '합성 비교 결과', trainingEvaluationSeparation: '분리 확인', quoteAccuracy: '해당 없음', calculationAccuracy: '해당 없음', humanReview: '합성 검토 기록', evaluatedScopes,
} })
const version = (r: ModelRegistration, id: string, status: ModelVersion['status'] = 'REGISTERED'): ModelVersion => ({ ...r, id, status, createdAt: '2026-11-09T00:00:00Z', evalResult: { evidence: r.evaluation, approval: null, activeScopes: [], revision: 0 } })
async function server(page: Page, models: ModelVersion[] = []) {
  const state = { models, writes: [] as { path: string; body: Record<string, unknown> }[], failure: 0, audits: [] as Record<string, unknown>[] }
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort())
  await page.route('**/api/v1/**', async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname.replace('/api/v1', '')
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (process.env.MODEL_LOCAL_CORE_SESSION && path === '/admin/model-versions') {
      const session = JSON.parse(await readFile(process.env.MODEL_LOCAL_CORE_SESSION, 'utf8'))
      const response = await route.fetch({ url: `http://127.0.0.1:58087/api/v1${path}${url.search}`, headers: { ...req.headers(), authorization: `Bearer ${session.token}` } })
      if (req.method() === 'POST') {
        state.writes.push({ path, body: req.postDataJSON() })
        if (response.status() === 201) state.models.push(await response.json())
      }
      return route.fulfill({ response })
    }
    if (path === '/admin/models/preflight') {
      state.writes.push({ path, body: req.postDataJSON() })
      const files = req.postDataJSON().files as { file: string }[]
      return json({ status: state.failure ? 'FAIL' : 'PASS', code: state.failure ? 'FILE_CHECK_FAILED' : 'FILES_AND_METADATA_VERIFIED',
        files: files.map(f => ({ file: f.file, status: state.failure ? 'FAIL' : 'PASS', code: state.failure ? 'HASH_MISMATCH' : 'OK' })) })
    }
    if (path === '/auth/refresh') return json({ accessToken: 'synthetic-admin', role: 'ADMIN' })
    if (path === '/me') return json({ role: 'ADMIN', permissions: ['SERVICE_OPS'], nextAction: 'READY', startPath: '/admin/home' })
    if (path === '/notifications' || path === '/admin/audit-logs') return json({ items: path.includes('audit') ? state.audits : [], page: 0, size: 100, totalElements: state.audits.length })
    if (path === '/admin/model-versions' && req.method() === 'GET') return json({ items: state.models, page: 0, size: 100, totalElements: state.models.length })
    if (path.startsWith('/admin/model-versions') && req.method() === 'POST') {
      const body = req.postDataJSON() as Record<string, unknown>
      state.writes.push({ path, body })
      if (state.failure) return json({ status: state.failure, code: state.failure === 409 ? 'MODEL_VERSION_CONFLICT' : 'MODEL_APPROVAL_REJECTED', title: state.failure === 409 ? '이미 등록된 버전입니다.' : '서버 평가 근거 검증 실패' }, state.failure)
      if (path === '/admin/model-versions') {
        const r = body as unknown as ModelRegistration, v = version(r, crypto.randomUUID())
        state.models.push(v); return json(v, 201)
      }
      const id = path.split('/').at(-2)!, v = state.models.find(m => m.id === id)!
      const previous = state.models.find(m => m.name === v.name && m.kind === v.kind && m.status === 'ACTIVE')
      if (previous) { previous.status = 'INACTIVE'; previous.evalResult!.activeScopes = [] }
      v.status = 'ACTIVE'; v.approvedBy = v.approvedBy ?? 'synthetic-reviewer'; v.evalResult!.activeScopes = body.scopes as string[]
      if (path.endsWith('/activate')) v.evalResult!.approval = { scopes: body.scopes as string[], reason: String(body.reason), approvedBy: v.approvedBy, approvedAt: '2026-11-09T00:00:00Z' }
      state.audits.push({ id: crypto.randomUUID(), actorUserId: 'synthetic-reviewer', action: 'MODEL_ACTIVATE', targetType: 'MODEL_VERSION', targetId: v.id, result: 'SUCCESS', createdAt: '2026-11-09T00:00:00Z', detail: { ...body, name: v.name, version: v.version, previousVersionId: previous?.id ?? null } })
      return json(v)
    }
    return json({ status: 404, code: 'NOT_FOUND' }, 404)
  })
  await page.goto('/admin/models')
  await expect(page.getByRole('heading', { name: '모델·프롬프트 버전', exact: true })).toBeVisible()
  return state
}
test('서술·논술 카드의 범위와 사유는 독립이고 복귀는 원 승인 범위만 허용한다', async ({ page }, info) => {
  const narrativeScope = 'judgment/grade-5/narrative'
  const narrative = version(entry('m2-klue-narrative', '3.0', [narrativeScope]), 'narrative')
  const essay = version(entry(), 'essay')
  const old = version(entry('m2-klue-essay', '2.0'), 'old', 'INACTIVE')
  old.approvedBy = 'original-reviewer'; old.evalResult!.approval = { scopes: [scopes[0]], reason: '원 승인', approvedBy: 'original-reviewer', approvedAt: '' }
  const state = await server(page, [narrative, essay, old])
  const n = page.getByRole('article', { name: 'm2-klue-narrative 3.0', exact: true }), e = page.getByRole('article', { name: 'm2-klue-essay 3.1', exact: true })
  await n.locator('.ad-version-disclosure > summary').click()
  await e.locator('.ad-version-disclosure > summary').click()
  await n.getByRole('checkbox', { name: narrativeScope, exact: true }).check()
  await n.getByLabel('모델 변경 사유', { exact: true }).fill('서술만 검토')
  await n.getByRole('checkbox', { name: '평가 근거와 선택 범위를 확인하고 활성화를 승인합니다.' }).check()
  await expect(e.getByRole('checkbox', { name: scopes[0], exact: true })).not.toBeChecked()
  await expect(e.getByLabel('모델 변경 사유', { exact: true })).toHaveValue('')
  await expect(e.getByRole('button', { name: '활성화', exact: true })).toBeDisabled()
  await n.getByRole('button', { name: '활성화', exact: true }).click()
  expect(state.writes).toHaveLength(0)
  await page.getByRole('button', { name: '확인 후 활성화', exact: true }).click()
  await n.locator('.ad-version-disclosure > summary').click()
  await expect(n.getByText('승인자 synthetic-reviewer', { exact: true })).toBeVisible()
  await expect(n.locator('summary .ad-badge')).toHaveText('활성')
  expect(state.writes[0].body.scopes).toEqual([narrativeScope])
  const rollback = page.getByRole('article', { name: 'm2-klue-essay 2.0', exact: true })
  await rollback.locator('.ad-version-disclosure > summary').click()
  await expect(rollback.getByRole('checkbox', { name: scopes[1], exact: true })).toHaveCount(0)
  await rollback.getByRole('checkbox', { name: scopes[0], exact: true }).check()
  await rollback.getByLabel('모델 변경 사유', { exact: true }).fill('논술 복귀')
  await rollback.getByRole('button', { name: '이 버전으로 되돌리기', exact: true }).click()
  await page.getByRole('button', { name: '확인 후 이 버전으로 되돌리기' }).click()
  await rollback.locator('.ad-version-disclosure > summary').click()
  await expect(rollback.getByText('승인자 original-reviewer', { exact: true })).toBeVisible()
  await expect(rollback.locator('summary .ad-badge')).toHaveText('활성')
  expect(state.writes[1].body.scopes).toEqual([scopes[0]])
  expect(state.writes[1].body).not.toHaveProperty('approved')
  await n.getByText('운영 단계와 확인 방법', { exact: true }).click()
  await expect(n.getByText('승인·활성화: core 활성화 완료, 로딩은 scoring에서 확인')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  await mkdir('.taste-skill/models-after', { recursive: true })
  await n.scrollIntoViewIfNeeded(); await page.screenshot({ path: `.taste-skill/models-after/${info.project.name}-card.png` })
  await writeFile(`.taste-skill/models-after/${info.project.name}.html`, (await page.content()).replace(/<script\b[\s\S]*?<\/script>/gi, ''))
  if (await page.getByRole('button', { name: '메뉴', exact: true }).isVisible()) await page.getByRole('button', { name: '메뉴', exact: true }).click()
  await page.getByRole('link', { name: '감사 이력', exact: true }).click()
  await page.getByText('모델 버전 조치 상세', { exact: true }).first().click()
  await expect(page.getByText('서술만 검토', { exact: true })).toBeVisible()
})
async function upload(page: Page) {
  const requests = [entry('m2-klue-narrative', '3.0', ['judgment/grade-5/narrative', 'judgment/grade-6/narrative']), entry()]
  const registration = process.env.MODEL_REGISTRATION_FILE ? await readFile(process.env.MODEL_REGISTRATION_FILE) : Buffer.from(JSON.stringify({ 주의: '품질 승인 근거가 아니라 평가 기록', requests }))
  const manifest = process.env.MODEL_MANIFEST_FILE ? await readFile(process.env.MODEL_MANIFEST_FILE) : Buffer.from(JSON.stringify({ models: requests.map((r, i) => ({ name: r.name, version: r.version, scope: r.evaluation.evaluatedScopes, ...(i === 1 ? { 주의: '임시 경계' } : {}), files: ['config.json', 'tokenizer.json', 'tokenizer_config.json', 'train_info.json', 'score_cuts.json', 'model.safetensors'].map(file => ({ file, bytes: 100, sha256: 'a'.repeat(64) })) })) }))
  const selection = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: '모델 등록 파일 선택', exact: true }).click()
  await (await selection).setFiles({ name: 'registration_1103.json', mimeType: 'application/json', buffer: registration })
  const first = page.getByRole('form', { name: '가져온 모델 1', exact: true }), second = page.getByRole('form', { name: '가져온 모델 2', exact: true })
  await expect(first).toBeVisible()
  await expect(page.getByText('registration_1103.json · 가져옴', { exact: true })).toBeVisible()
  await page.getByText('모델 파일 검사용 manifest (선택)', { exact: true }).click()
  await page.getByLabel('검사용 manifest 파일', { exact: true }).setInputFiles({ name: 'manifest.json', mimeType: 'application/json', buffer: manifest })
  await expect(first.getByRole('button', { name: '버전 등록', exact: true })).toBeDisabled()
  await page.getByLabel('운영 버킷 이름', { exact: true }).fill('local-validation-models')
  await page.getByRole('button', { name: '모든 항목의 버킷 치환' }).click()
  return { first, second }
}
test('등록 JSON·manifest 가져오기와 버킷 치환·한계 표시·개별 등록 (실제 파일은 환경 변수)', async ({ page }, info) => {
  const state = await server(page)
  const { first, second } = await upload(page)
  await expect(first.locator('dl').getByText('평가셋', { exact: true })).toBeVisible()
  await expect(first.getByLabel('모델 이름')).toBeHidden()
  await expect(page.getByLabel('운영 버킷 이름')).toHaveCount(0)
  for (const form of [first, second]) {
    await form.getByRole('button', { name: '상세 보기·수정' }).click()
    await form.getByText('추가 정보', { exact: true }).click()
  }
  await expect(first.getByLabel('한계·주의 (줄마다 한 항목)')).toHaveValue(/평가 기록/)
  await expect(second.getByLabel('한계·주의 (줄마다 한 항목)')).toHaveValue(/임시/)
  await first.getByRole('button', { name: '버전 등록', exact: true }).click()
  await expect(first.getByRole('status').filter({ hasText: '등록 완료' })).toContainText('등록 완료')
  await second.getByRole('button', { name: '버전 등록', exact: true }).click()
  await expect(second.getByRole('status').filter({ hasText: '등록 완료' })).toContainText('등록 완료')
  expect(state.writes).toHaveLength(2)
  for (const write of state.writes) {
    expect(write.path).toBe('/admin/model-versions')
    expect(write.body.artifactUri).toMatch(/^s3:\/\/local-validation-models\/models\//)
    expect(write.body).not.toHaveProperty('approved')
    expect(write.body.registration).toMatchObject({ source: 'JSON_IMPORT', modifiedFields: expect.arrayContaining(['artifactUri', 'evaluation.limitations']), artifactFiles: expect.any(Array) })
    const provenance = write.body.registration as { jsonSha256: string; manifestSha256: string }
    expect(provenance.jsonSha256).toMatch(/^[a-f0-9]{64}$/)
    expect(provenance.manifestSha256).toMatch(/^[a-f0-9]{64}$/)
    if (process.env.MODEL_REGISTRATION_FILE) expect(provenance.jsonSha256).toBe(createHash('sha256').update(await readFile(process.env.MODEL_REGISTRATION_FILE)).digest('hex'))
    if (process.env.MODEL_MANIFEST_FILE) expect(provenance.manifestSha256).toBe(createHash('sha256').update(await readFile(process.env.MODEL_MANIFEST_FILE)).digest('hex'))
  }
  expect(state.models.every(v => v.status === 'REGISTERED')).toBe(true)
  const card = page.getByRole('article', { name: 'm2-klue-essay 3.1', exact: true })
  await card.locator('.ad-version-disclosure > summary').click()
  await expect(card.getByText(/임시/)).toBeVisible()
  await mkdir('.taste-skill/models-after', { recursive: true })
  await first.scrollIntoViewIfNeeded(); await page.screenshot({ path: `.taste-skill/models-after/${info.project.name}-import.png` })
  if (process.env.MODEL_LOCAL_CORE_SESSION) {
    const session = JSON.parse(await readFile(process.env.MODEL_LOCAL_CORE_SESSION, 'utf8'))
    await writeFile(process.env.MODEL_LOCAL_CORE_SESSION.replace('session.json', 'done.json'), JSON.stringify({ nonce: session.nonce }))
  }
})
test('누락된 근거만 열어 보완하고 선택 범위와 직접 입력 범위를 함께 등록한다', async ({ page }) => {
  const state = await server(page)
  const request = entry()
  request.artifactUri = 's3://local/models/m2-klue-essay/3.1/'
  const { humanReview, ...evaluation } = request.evaluation
  await page.getByLabel('모델 등록 파일', { exact: true }).setInputFiles({
    name: 'incomplete.json', mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify({ requests: [{ ...request, evaluation }] })),
  })
  const row = page.getByRole('form', { name: '가져온 모델 1' })
  const register = row.getByRole('button', { name: '버전 등록' })
  await expect(register).toBeDisabled()
  await expect(row.getByLabel('평가셋 ID')).toBeHidden()
  await expect(row.getByRole('button', { name: '사전 검사' })).toHaveCount(0)
  await row.getByLabel('사람 검토 기록').pressSequentially(humanReview)
  await expect(row.getByLabel('사람 검토 기록')).toHaveValue(humanReview)
  await row.getByRole('button', { name: '상세 보기·수정' }).click()
  await row.getByText('기타 범위 및 코드 직접 편집').click()
  await row.getByLabel('평가 범위', { exact: true }).fill('custom/review')
  await row.getByRole('checkbox', { name: '답변 표현 필터' }).check()
  await row.getByRole('button', { name: '상세 접기' }).click()
  await expect(row.getByText('custom/review, 답변 표현 필터')).toBeVisible()
  await register.click()
  await expect(row.getByRole('status')).toContainText('등록 완료')
  expect(state.writes[0].body).toMatchObject({
    evaluation: { ...evaluation, humanReview, evaluatedScopes: ['custom/review', 'answer-filter'] },
    registration: { modifiedFields: expect.arrayContaining(['evaluation.humanReview', 'evaluation.evaluatedScopes']) },
  })
})

test('잘못된 파일은 해당 이름과 오류를 표시하고 선택 사항인 manifest를 제외해 재개한다', async ({ page }) => {
  const state = await server(page)
  const { second } = await upload(page)
  const manifest = page.getByLabel('검사용 manifest 파일', { exact: true })
  await manifest.setInputFiles({ name: '잘못된-목록.txt', mimeType: 'text/plain', buffer: Buffer.from('invalid') })
  await expect(page.getByText('잘못된-목록.txt · 가져오기 실패')).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('2MB 이하 JSON')
  await expect(second.getByRole('button', { name: '버전 등록', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'manifest 제외' }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await second.getByRole('button', { name: '버전 등록', exact: true }).click()
  await expect(second.getByRole('status')).toContainText('등록 완료')
  expect(state.writes[0].body.registration).toMatchObject({ artifactFiles: [] })
  expect(state.writes[0].body.registration).not.toHaveProperty('manifestSha256')
  expect(state.writes[0].body.evaluation).toMatchObject({ limitations: ['품질 승인 근거가 아니라 평가 기록'] })
})

test('직접 등록은 추가 정보를 접고 종류별 필수 입력과 한글 범위를 표시한다', async ({ page }) => {
  await server(page)
  await page.getByText('직접 새 버전 등록', { exact: true }).click()
  const form = page.getByRole('form', { name: '새 버전 등록' })
  await expect(form.getByLabel('아티팩트 주소')).toBeHidden()
  await expect(form.getByRole('button', { name: '사전 검사' })).toHaveCount(0)
  await form.getByRole('checkbox', { name: '초등 5학년 · 논술형 판정' }).check()
  await form.getByLabel('버전 종류').selectOption('MODEL')
  await expect(form.getByLabel('아티팩트 주소')).toBeVisible()
  await form.getByLabel('버전 종류').selectOption('RUBRIC')
  await expect(form.getByLabel('기준표 원본 UUID')).toBeVisible()
  await form.getByText('추가 정보', { exact: true }).click()
  await expect(form.getByLabel('아티팩트 주소')).toBeVisible()
  await expect(form.getByRole('checkbox', { name: '초등 5학년 · 논술형 판정' })).toBeChecked()
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
})

test('등록 422·409는 각 항목에 남고 다른 항목은 등록할 수 있다', async ({ page }) => {
  const state = await server(page)
  const { first, second } = await upload(page)
  state.failure = 422
  await first.getByRole('button', { name: '버전 등록', exact: true }).click()
  await expect(first.getByRole('alert')).toContainText('서버 평가 근거 검증 실패')
  await expect(second.getByRole('alert')).toHaveCount(0)
  state.failure = 409
  await first.getByRole('button', { name: '버전 등록', exact: true }).click()
  await expect(first.getByLabel('모델 이름')).toHaveAccessibleDescription('이미 등록된 버전입니다.')
  await expect(first.getByLabel('모델 버전')).toHaveAccessibleDescription('이미 등록된 버전입니다.')
  state.failure = 0
  await second.getByRole('button', { name: '버전 등록', exact: true }).click()
  await expect(second.getByRole('status').filter({ hasText: '등록 완료' })).toContainText('등록 완료')
  await expect(first.getByRole('button', { name: '버전 등록', exact: true })).toBeEnabled()
})

test('사전 검사는 파일 확인만 표시하고 입력 변경 시 결과를 만료한다', async ({ page }) => {
  const state = await server(page)
  const { first } = await upload(page)
  const check = first.getByRole('button', { name: '사전 검사', exact: true })
  await check.click()
  await expect(first.getByText('파일·형식 확인 완료', { exact: true })).toBeVisible()
  expect(state.writes).toHaveLength(1)
  expect(state.writes[0].path).toBe('/admin/models/preflight')
  expect(state.models).toHaveLength(0)
  await first.getByRole('button', { name: '상세 보기·수정' }).click()
  await first.getByLabel('아티팩트 주소', { exact: true }).fill('s3://local-validation-models/models/changed/3.0/')
  await expect(first.getByText('입력이 변경되었습니다. 사전 검사를 다시 실행해 주세요.')).toBeVisible()
  await expect(first.getByText('파일·형식 확인 완료', { exact: true })).toHaveCount(0)
  state.failure = 1
  await check.click()
  await expect(first.getByText('파일 검사 실패', { exact: true })).toBeVisible()
  expect(state.models).toHaveLength(0)
  expect(state.writes.every(w => w.path === '/admin/models/preflight')).toBe(true)
})
test('재학습 추천 태그는 추천·비추천으로 보이고 근거는 펼쳐 본다, 태그 없는 버전은 표시 없음 (#728)', async ({ page }) => {
  const tagged = (name: string, ver: string, recommendation: NonNullable<ModelRegistration['evaluation']['recommendation']>) => {
    const r = entry(name, ver, ['answer-filter']); r.evaluation.recommendation = recommendation; return version(r, `${name}-${ver}`)
  }
  await server(page, [
    tagged('tox-kcelectra', '2.0', { tag: 'RECOMMENDED', comparedTo: 'tox-kcelectra:1.0-1119', reasons: ['놓친 글이 줄었다', '정상 글 오차단 같음'], metrics: { recall: 0.96, precision: 0.99 } }),
    tagged('tox-kcelectra', '2.1', { tag: 'NOT_RECOMMENDED', comparedTo: 'NONE', reasons: ['막은 정상 글이 늘었다'] }),
    version(entry(), 'plain'),
  ])
  const good = page.getByRole('article', { name: 'tox-kcelectra 2.0', exact: true })
  const bad = page.getByRole('article', { name: 'tox-kcelectra 2.1', exact: true })
  const plain = page.getByRole('article', { name: 'm2-klue-essay 3.1', exact: true })
  await expect(good.locator('.ad-version-disclosure > summary .model-recommendation-tag')).toHaveText('추천')
  await expect(bad.locator('.ad-version-disclosure > summary .model-recommendation-tag')).toHaveText('비추천')
  await expect(plain.locator('.model-recommendation-tag, .model-recommendation')).toHaveCount(0)
  await good.locator('.ad-version-disclosure > summary').click()
  const details = good.locator('details.model-recommendation')
  await expect(details).toBeVisible()
  await expect(details.getByText('비교 대상 버전: tox-kcelectra:1.0-1119')).toBeHidden() // 펼치기 전
  await details.locator('summary').click()
  await expect(details.getByText('비교 대상 버전: tox-kcelectra:1.0-1119')).toBeVisible()
  await expect(details.getByRole('listitem')).toHaveText(['놓친 글이 줄었다', '정상 글 오차단 같음'])
  await expect(details.locator('dt')).toHaveText(['precision', 'recall'])
  await expect(details.locator('dd')).toHaveText(['0.99', '0.96'])
  await bad.locator('.ad-version-disclosure > summary').click()
  await bad.locator('details.model-recommendation > summary').click()
  await expect(bad.getByText('비교 대상 버전: 처음 등록 (비교한 활성 버전 없음)')).toBeVisible()
  await expect(bad.locator('details.model-recommendation dl')).toHaveCount(0)
  await plain.locator('.ad-version-disclosure > summary').click()
  await expect(plain.locator('details.model-recommendation')).toHaveCount(0)
})
