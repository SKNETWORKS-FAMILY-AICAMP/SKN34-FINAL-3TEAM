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
  await n.getByRole('checkbox', { name: narrativeScope, exact: true }).check()
  await n.getByLabel('모델 변경 사유', { exact: true }).fill('서술만 검토')
  await n.getByRole('checkbox', { name: '평가 근거와 선택 범위를 확인하고 활성화를 승인합니다.' }).check()
  await expect(e.getByRole('checkbox', { name: scopes[0], exact: true })).not.toBeChecked()
  await expect(e.getByLabel('모델 변경 사유', { exact: true })).toHaveValue('')
  await expect(e.getByRole('button', { name: '활성화', exact: true })).toBeDisabled()
  await n.getByRole('button', { name: '활성화', exact: true }).click()
  expect(state.writes).toHaveLength(0)
  await page.getByRole('button', { name: '확인 후 활성화', exact: true }).click()
  await expect(n.getByText('MODEL · ACTIVE · 승인자 synthetic-reviewer', { exact: true })).toBeVisible()
  expect(state.writes[0].body.scopes).toEqual([narrativeScope])
  const rollback = page.getByRole('article', { name: 'm2-klue-essay 2.0', exact: true })
  await expect(rollback.getByRole('checkbox', { name: scopes[1], exact: true })).toHaveCount(0)
  await rollback.getByRole('checkbox', { name: scopes[0], exact: true }).check()
  await rollback.getByLabel('모델 변경 사유', { exact: true }).fill('논술 복귀')
  await rollback.getByRole('button', { name: '이 버전으로 되돌리기', exact: true }).click()
  await page.getByRole('button', { name: '확인 후 이 버전으로 되돌리기' }).click()
  await expect(rollback.getByText('MODEL · ACTIVE · 승인자 original-reviewer', { exact: true })).toBeVisible()
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
  const manifest = process.env.MODEL_MANIFEST_FILE ? await readFile(process.env.MODEL_MANIFEST_FILE) : Buffer.from(JSON.stringify({ models: requests.map((r, i) => ({ name: r.name, version: r.version, scope: r.evaluation.evaluatedScopes, ...(i === 1 ? { 주의: '임시 경계' } : {}), files: [{ file: 'model.safetensors', bytes: 442539656, sha256: 'a'.repeat(64) }] })) }))
  await page.getByLabel('registration JSON', { exact: true }).setInputFiles({ name: 'registration_1103.json', mimeType: 'application/json', buffer: registration })
  const first = page.getByRole('form', { name: '가져온 모델 1', exact: true }), second = page.getByRole('form', { name: '가져온 모델 2', exact: true })
  await expect(first).toBeVisible()
  await page.getByLabel('manifest JSON (선택)', { exact: true }).setInputFiles({ name: 'manifest.json', mimeType: 'application/json', buffer: manifest })
  await expect(first.getByRole('button', { name: '버전 등록', exact: true })).toBeDisabled()
  await page.getByLabel('운영 버킷 이름', { exact: true }).fill('local-validation-models')
  await page.getByRole('button', { name: '모든 항목의 버킷 치환' }).click()
  return { first, second }
}
test('등록 JSON·manifest 가져오기와 버킷 치환·한계 표시·개별 등록 (실제 파일은 환경 변수)', async ({ page }, info) => {
  const state = await server(page)
  const { first, second } = await upload(page)
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
  await expect(card.getByText(/임시/)).toBeVisible()
  await mkdir('.taste-skill/models-after', { recursive: true })
  await first.scrollIntoViewIfNeeded(); await page.screenshot({ path: `.taste-skill/models-after/${info.project.name}-import.png` })
  if (process.env.MODEL_LOCAL_CORE_SESSION) {
    const session = JSON.parse(await readFile(process.env.MODEL_LOCAL_CORE_SESSION, 'utf8'))
    await writeFile(process.env.MODEL_LOCAL_CORE_SESSION.replace('session.json', 'done.json'), JSON.stringify({ nonce: session.nonce }))
  }
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
