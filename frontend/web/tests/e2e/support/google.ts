import type { BrowserContext } from '@playwright/test'

export type GoogleIdentity = { sub: string; email: string; name: string }

export function newParent(prefix: string): GoogleIdentity {
  const sub = `e2e-${prefix}-${crypto.randomUUID()}`
  return { sub, email: `${sub}@example.test`, name: 'E2E 보호자' }
}

export const admin: GoogleIdentity = { sub: 'e2e-admin', email: 'e2e-admin@example.test', name: 'E2E 관리자' }

// google-stub은 상태가 없으므로 code에 신원·nonce·PKCE challenge·redirect_uri를 담는다.
function callback(authorizeUrl: string, identity: GoogleIdentity) {
  const url = new URL(authorizeUrl)
  const redirectUri = url.searchParams.get('redirect_uri') ?? ''
  const code = Buffer.from(JSON.stringify({
    ...identity, nonce: url.searchParams.get('nonce'), challenge: url.searchParams.get('code_challenge'), redirectUri,
  })).toString('base64url')
  const target = new URL(redirectUri)
  target.searchParams.set('state', url.searchParams.get('state') ?? '')
  target.searchParams.set('code', code)
  return target.href
}

/** 이 컨텍스트의 Google 로그인을 google-stub 신원으로 완료시키고 외부 호출을 막는다. */
export async function useGoogleIdentity(context: BrowserContext, identity: GoogleIdentity) {
  await context.route(/https:\/\/(fonts\.(googleapis|gstatic)\.com|js\.tosspayments\.com)\//, (route) => route.abort())
  // core의 실제 authorize 302(상태 쿠키 포함)는 유지하고 Location만 콜백으로 바꾼다.
  await context.route('**/api/v1/auth/google/authorize', async (route) => {
    const response = await route.fetch({ maxRedirects: 0 })
    const location = response.headers().location
    if (response.status() !== 302 || !location) throw new Error(`authorize 응답 확인 필요: ${response.status()}`)
    await route.fulfill({ response, headers: { ...response.headers(), location: callback(location, identity) } })
  })
  await context.route('https://accounts.google.com/**', (route) =>
    route.fulfill({ status: 302, headers: { location: callback(route.request().url(), identity) } }))
}
