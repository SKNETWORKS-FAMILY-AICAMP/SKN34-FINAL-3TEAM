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
