import { expect, type APIRequestContext, type Browser } from '@playwright/test'
// useGoogleIdentity는 React 훅이 아니라 이름만 바꿔 쓴다(oxlint rules-of-hooks)
import { admin, useGoogleIdentity as signInWithGoogle } from './google.ts'

export interface AdminApi { request: APIRequestContext; headers: { authorization: string } }

/**
 * 시드 관리자(google-stub sub e2e-admin)로 로그인해 관리자 API를 부른다.
 * 관리자 토큰은 메모리에만 있어 관리자 화면이 보내는 요청의 Authorization 헤더를 그대로 쓴다.
 */
export async function withAdminApi<T>(browser: Browser, baseURL: string, run: (api: AdminApi) => Promise<T>): Promise<T> {
  const context = await browser.newContext({ baseURL })
  try {
    await signInWithGoogle(context, admin)
    const page = await context.newPage()
    const authorized = page.waitForRequest(r => new URL(r.url()).pathname.startsWith('/api/v1/admin/') && !!r.headers().authorization)
    await page.goto('/admin/login')
    await page.getByRole('link', { name: 'Google 계정으로 계속하기' }).click()
    await page.waitForURL('**/admin/home**')
    return await run({ request: context.request, headers: { authorization: (await authorized).headers().authorization } })
  } finally {
    await context.close()
  }
}

const EXPLANATION_SCOPE = 'explanation/grade-5/narrative'

/**
 * 리포트 설명 모델(MODEL report-explanation)을 초5 서술 범위에 등록·활성화한다(api-spec 5.2 모델 레지스트리, 4.2.3).
 * ai는 이 범위가 활성일 때만 설명 sLLM(E2E는 llm-stub)을 부르고, 아니면 {active:false}라 리포트가 "설명 미포함"이 된다.
 * 활성화는 model.version.activated 이벤트로 ai에 전달되므로 리포트 생성보다 먼저 부른다. 이미 활성이면 그대로 둔다.
 */
export async function ensureExplanationModel(browser: Browser, baseURL: string) {
  await withAdminApi(browser, baseURL, async ({ request, headers }) => {
    const path = '/api/v1/admin/model-versions'
    const listed = await request.get(`${path}?kind=MODEL&size=100`, { headers })
    expect(listed.ok(), await listed.text()).toBe(true)
    const { items } = await listed.json() as { items: { id: string; name: string; status: string; evalResult?: { activeScopes?: string[] } }[] }
    if (items.some((item) => item.name === 'report-explanation' && item.status === 'ACTIVE' && item.evalResult?.activeScopes?.includes(EXPLANATION_SCOPE))) return

    const evidence = 'E2E 합성 기록: llm-stub 고정 응답이라 품질 평가 대상 아님(#625)'
    const created = await request.post(path, {
      headers,
      data: {
        kind: 'MODEL', name: 'report-explanation', version: `e2e-${Date.now().toString(36)}`, artifactUri: 's3://e2e-models/report-explanation',
        evaluation: {
          datasetId: 'e2e-synthetic', datasetVersion: '1', baselineVersion: 'none', comparisonReport: evidence,
          trainingEvaluationSeparation: evidence, quoteAccuracy: evidence, calculationAccuracy: evidence, humanReview: evidence,
          evaluatedScopes: [EXPLANATION_SCOPE], limitations: ['실서버 E2E 전용 합성 등록'],
        },
      },
    })
    expect(created.status(), await created.text()).toBe(201)
    const { id } = await created.json() as { id: string }
    const activated = await request.post(`${path}/${id}/activate`, {
      headers, data: { approved: true, scopes: [EXPLANATION_SCOPE], reason: 'E2E 리포트 설명 경로 확인', reanalysisPlanned: false },
    })
    expect(activated.ok(), await activated.text()).toBe(true)
  })
}
