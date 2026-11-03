// Google OAuth 대역 (로컬·CI E2E 전용, #246). core의 token·JWKS 호출만 받는다.
// authorize는 Playwright가 가로채 code에 {sub,email,name,nonce,challenge,redirectUri}를 base64url JSON으로 담는다.
import { createServer } from 'node:http'
import { createHash, generateKeyPairSync, randomUUID, sign } from 'node:crypto'

const clientId = process.env.GOOGLE_CLIENT_ID
const clientSecret = process.env.GOOGLE_CLIENT_SECRET
if (!clientId || !clientSecret) throw new Error('GOOGLE_CLIENT_ID·GOOGLE_CLIENT_SECRET 필요')

const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 })
const jwk = { ...publicKey.export({ format: 'jwk' }), kid: randomUUID(), use: 'sig', alg: 'RS256' }
const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url')
const json = (res, body, status = 200) => {
  res.writeHead(status, { 'Content-Type': 'application/json' })
  res.end(JSON.stringify(body))
}

function idToken(form) {
  if (form.get('grant_type') !== 'authorization_code') return null
  if (form.get('client_id') !== clientId || form.get('client_secret') !== clientSecret) return null
  let code
  try { code = JSON.parse(Buffer.from(form.get('code') ?? '', 'base64url').toString()) } catch { return null }
  if (!code.sub || !code.email || !code.nonce || form.get('redirect_uri') !== code.redirectUri) return null
  const verifier = form.get('code_verifier') ?? ''
  if (createHash('sha256').update(verifier).digest('base64url') !== code.challenge) return null
  const now = Math.floor(Date.now() / 1000)
  const message = `${encode({ alg: 'RS256', kid: jwk.kid, typ: 'JWT' })}.${encode({
    iss: 'https://accounts.google.com', aud: clientId, sub: code.sub, email: code.email, email_verified: true,
    name: code.name ?? code.email, nonce: code.nonce, iat: now, exp: now + 300,
  })}`
  return `${message}.${sign('RSA-SHA256', Buffer.from(message), privateKey).toString('base64url')}`
}

createServer(async (req, res) => {
  // Opt-in interactive login for the isolated transfer trial. Never enabled in production/E2E defaults.
  const url = new URL(req.url, 'http://stub')
  if (process.env.LOCAL_TRANSFER_TRIAL === 'true' && req.method === 'GET' && url.pathname === '/authorize') {
    const redirect = new URL(url.searchParams.get('redirect_uri') || 'http://invalid')
    if (redirect.origin !== process.env.TRIAL_WEB_ORIGIN || !['/api/v1/auth/google/callback', '/api/v1/auth/google/reauth/callback'].includes(redirect.pathname)) return json(res, { error: 'invalid_redirect' }, 400)
    const identities = { sender: ['trial-sender', 'sender@example.test', '보내는 학부모'], receiver: ['trial-receiver', 'receiver@example.test', '받는 학부모'], full: ['trial-full', 'full@example.test', '자녀 3명 학부모'], spare: ['trial-spare', 'spare@example.test', '추가 테스트 학부모'] }
    const identity = identities[url.searchParams.get('trial_identity')]
    if (identity) {
      redirect.searchParams.set('state', url.searchParams.get('state') || '')
      redirect.searchParams.set('code', encode({ sub: identity[0], email: identity[1], name: identity[2], nonce: url.searchParams.get('nonce'), challenge: url.searchParams.get('code_challenge'), redirectUri: url.searchParams.get('redirect_uri') }))
      res.writeHead(302, { Location: redirect.href }); return res.end()
    }
    const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
    const fields = [...url.searchParams].filter(([key]) => key !== 'trial_identity').map(([key, value]) => `<input type="hidden" name="${escape(key)}" value="${escape(value)}">`).join('')
    const options = Object.entries(identities).map(([key, value]) => `<option value="${key}">${value[2]} — ${value[1]}</option>`).join('')
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' })
    return res.end(`<!doctype html><html lang="ko"><meta charset="utf-8"><title>로컬 테스트 계정</title><body style="font:18px system-ui;max-width:600px;margin:60px auto;padding:24px"><h1>로컬 테스트 계정 선택</h1><p>합성 계정만 사용합니다. 본인 확인 중에는 현재 로그인한 계정을 선택하세요.</p><form><label>학부모 <select name="trial_identity">${options}</select></label>${fields}<p><button>선택한 계정으로 계속</button></p></form></body></html>`)
  }
  if (req.method === 'GET' && req.url === '/health') return json(res, { status: 'UP' })
  if (req.method === 'GET' && req.url === '/jwks') return json(res, { keys: [jwk] })
  if (req.method === 'POST' && req.url === '/token') {
    let raw = ''
    for await (const part of req) raw += part
    const token = idToken(new URLSearchParams(raw))
    return token ? json(res, { id_token: token }) : json(res, { error: 'invalid_grant' }, 400)
  }
  return json(res, { error: 'not_found' }, 404)
}).listen(8080, '0.0.0.0')
