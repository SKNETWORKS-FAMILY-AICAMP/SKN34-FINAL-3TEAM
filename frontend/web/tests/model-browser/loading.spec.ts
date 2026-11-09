import { test, expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'

test('Pod 2개 보고 결과와 실패 Pod를 화면에서 구분한다', async ({ page }) => {
  const base = '../../output/issue370-local/'
  const version = process.env.MODEL_LOADING_LOCAL ? JSON.parse(await readFile(base + 'version.json', 'utf8')) : {
    id: 'test', name: 'm2-local-test', version: 'current', kind: 'MODEL', status: 'ACTIVE', approvedBy: 'test-reviewer',
    evalResult: { evidence: { evaluatedScopes: [], limitations: [] }, activeScopes: [], revision: 2 },
  }
  const loading = process.env.MODEL_LOADING_LOCAL ? JSON.parse(await readFile(base + 'loading.json', 'utf8')) : {
    staleAfterSeconds: 120, populationSource: 'RECENT_REPORTS', observedAt: new Date().toISOString(),
    pods: ['fail', 'ok'].map((state, i) => ({ podId: `local-scoring-${state}`, instanceId: String(i), stale: false, reportedAt: new Date().toISOString(), models: [{ name: version.name, version: 'current', revision: 2, status: state === 'ok' ? 'LOADED' : 'FAILED', errorType: state === 'fail' ? 'ValueError' : null, loadedVersion: state === 'fail' ? 'old' : 'current', loadedRevision: state === 'fail' ? 1 : 2, previousModelRetained: state === 'fail' }] })),
    summaries: [{ name: version.name, version: 'current', revision: 2, observedPods: 2, loadedPods: 1, failedPods: ['local-scoring-fail'] }],
  }
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, r => r.abort())
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
    let body: unknown
    if(path === '/auth/refresh') body = { accessToken: 'local-test', role: 'ADMIN' }
    else if(path === '/me') body = { role: 'ADMIN', permissions: ['SERVICE_OPS'], nextAction: 'READY', startPath: '/admin/home' }
    else if(path === '/admin/model-versions') body = { items: [version], page: 0, size: 100, totalElements: 1 }
    else if(path === '/admin/model-loading') body = loading
    else body = { items: [] }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
  await page.goto('/admin/models')
  await page.getByText('운영 단계와 확인 방법', { exact: true }).click()
  const panel = page.getByLabel(`${version.name} Pod 로딩 상태`, { exact: true })
  await expect(panel.getByText('최근 보고 Pod 2개 중 로딩 완료 1개', { exact: true })).toBeVisible()
  await expect(panel.getByText('local-scoring-fail: 로딩 실패', { exact: true })).toBeVisible()
  await expect(panel.getByText('local-scoring-ok: 로딩 완료', { exact: true })).toBeVisible()
  await expect(panel).toContainText('ValueError · 기존 모델 유지 (old, revision 1)')
  await expect(panel).toContainText('품질 승인이나 추론 검증 완료를 뜻하지 않습니다')
  await expect(page.locator('body')).not.toContainText('synthetic failure')
  await page.screenshot({ path: `../../output/issue370-local/loading-${test.info().project.name}.png`, fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy()
})
