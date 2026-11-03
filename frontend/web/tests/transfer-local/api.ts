import { request, expect, type APIRequestContext } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import type { GoogleIdentity } from '../e2e/support/google.ts'

const origin = process.env.TRANSFER_WEB_ORIGIN || 'http://127.0.0.1:5195'
const postgresContainer = process.env.E2E_POSTGRES_CONTAINER || 'guardian-transfer-289-postgres-1'
if (!/^guardian-transfer-(local|289)-postgres-1$/.test(postgresContainer))
  throw new Error('이관 테스트 전용 PostgreSQL 컨테이너만 사용할 수 있습니다.')
const contexts: APIRequestContext[] = []
type Doc = { documentId: string; version: string; kind: string }
export type Actor = { identity: GoogleIdentity; context: APIRequestContext; token: string; userId: string }
export function callback(address: string, identity: GoogleIdentity) {
  const url = new URL(address), target = new URL(url.searchParams.get('redirect_uri')!)
  const code = Buffer.from(JSON.stringify({ ...identity, nonce: url.searchParams.get('nonce'), challenge: url.searchParams.get('code_challenge'), redirectUri: target.href })).toString('base64url')
  target.searchParams.set('state', url.searchParams.get('state')!); target.searchParams.set('code', code)
  return target.href
}
export async function actor(name = 'API 테스트 학부모', predefined?: GoogleIdentity): Promise<Actor> {
  const sub = `transfer-${randomUUID()}`, identity = predefined ?? { sub, email: `${sub}@example.test`, name }
  const context = await request.newContext({ baseURL: origin, extraHTTPHeaders: { Origin: origin, 'X-Requested-With': 'XMLHttpRequest' } })
  contexts.push(context)
  const started = await context.get('/api/v1/auth/google/authorize', { maxRedirects: 0 })
  expect(started.status()).toBe(302)
  const completed = await context.get(callback(started.headers().location, identity), { maxRedirects: 0 })
  expect(completed.status()).toBe(302)
  const refresh = await context.post('/api/v1/auth/refresh'); expect(refresh.ok()).toBeTruthy()
  const token = (await refresh.json()).accessToken as string
  const me = await context.get('/api/v1/me', { headers: { Authorization: `Bearer ${token}` } })
  const result = { identity, context, token, userId: (await me.json()).userId }
  const saved = await call(result, 'post', '/me/consents', { consents: await choices(result, false) }); expect(saved.ok()).toBeTruthy()
  return result
}
export async function disposeActors() { await Promise.all(contexts.splice(0).map(c => c.dispose())) }
export function call(actor: Actor, method: 'get' | 'post' | 'put' | 'delete', path: string, data?: unknown, proof?: string) {
  return actor.context.fetch(`/api/v1${path}`, { method: method.toUpperCase(), data,
    headers: { Authorization: `Bearer ${actor.token}`, ...(proof ? { 'X-Reauth-Token': proof } : {}) } })
}
export async function choices(actor: Actor, guardian: boolean) {
  const response = await actor.context.get('/api/v1/consent-documents')
  return ((await response.json()).items as Doc[]).filter(d => (d.kind === 'GUARDIAN') === guardian).map(d => ({ documentId: d.documentId, version: d.version, agreed: true }))
}
export async function child(actor: Actor, nickname = '이관 테스트 자녀'): Promise<string> {
  const response = await call(actor, 'post', '/children', { nickname, grade: 3, birthYear: 2017, consents: await choices(actor, true) })
  expect(response.status(), await response.text()).toBe(201)
  return (await response.json()).id
}
export async function reauth(actor: Actor, purpose: string, childId?: string) {
  const started = await call(actor, 'post', '/me/reauth', { purpose, ...(childId ? { childId } : {}) })
  expect(started.ok(), await started.text()).toBeTruthy()
  const body = await started.json()
  const completed = await actor.context.get(callback(body.authorizationUrl, actor.identity)); expect(completed.ok()).toBeTruthy()
  const issued = await call(actor, 'post', '/me/reauth', { challengeId: body.challengeId }); expect(issued.ok()).toBeTruthy()
  return (await issued.json()).reauthToken as string
}
export async function transfer(from: Actor, to: Actor, childId: string, includeConversations = false): Promise<string> {
  const response = await call(from, 'post', '/guardian-transfers', { childId, recipientId: to.userId, includeConversations }, await reauth(from, 'CHILD_TRANSFER', childId))
  expect(response.ok(), await response.text()).toBeTruthy()
  return (await response.json()).id
}
export function sql(database: 'core_db' | 'learning_db' | 'report_db', statement: string) {
  // Only the two isolated transfer projects are allowed, never the team's default database.
  return execFileSync('docker', ['exec', '-i', postgresContainer, 'sh', '-c', `psql -v ON_ERROR_STOP=1 -qAt -U "$POSTGRES_USER" -d ${database}`], { input: statement, encoding: 'utf8' }).trim()
}
export function seedConversation(owner: Actor, childId: string) {
  const id = randomUUID(), message = randomUUID()
  sql('core_db', `INSERT INTO conversation(id,parent_user_id,student_id,period_from,period_to,created_at,updated_at) VALUES('${id}','${owner.userId}','${childId}',CURRENT_DATE,CURRENT_DATE,now(),now());
    INSERT INTO conversation_message(id,conversation_id,seq,question,answer,scope_student_id,scope_changed,status,retry_count,created_at) VALUES('${message}','${id}',1,'학습에 대해 알려 주세요','합성 상담 답변','${childId}',false,'COMPLETED',0,now());`)
  return id
}
