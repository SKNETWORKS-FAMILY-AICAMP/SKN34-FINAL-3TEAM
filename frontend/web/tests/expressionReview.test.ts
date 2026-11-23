// #728 관리자 표현 검토 (FN-ADM-24, api-spec 2.8): 요청 모양·목 서버 규칙(SERVICE_OPS, 글만, 라벨 전/완료, 빈 목록·실패·권한 없음)
import test from 'node:test'
import assert from 'node:assert/strict'
import { getResponse } from 'msw'
import { adminApi } from '../src/data/admin/api.ts'
import { setAccessToken } from '../src/data/apiClient.ts'
import { expressionReviewQuery, hasNextPage } from '../src/domain/admin/expressionReview.ts'
import { adminHandlers } from '../src/mocks/handlers/admin.ts'
import { studentHandlers } from '../src/mocks/handlers/student.ts'
import { setWorkspaceScenario } from '../src/mocks/fixtures/accounts.ts'
import { audits, expressionReviews } from '../src/mocks/fixtures/admin/operations.ts'
const [r1, r2, r3] = expressionReviews.map(r => r.id) // core처럼 UUID

test('조회 쿼리: labeled는 항상, source는 고를 때만, 쪽은 0부터', () => {
  assert.equal(expressionReviewQuery({ labeled: false, page: 0, size: 20 }), 'labeled=false&page=0&size=20')
  assert.equal(expressionReviewQuery({ labeled: true, source: 'COMMUNITY_REPORT', page: 2, size: 20 }), 'labeled=true&source=COMMUNITY_REPORT&page=2&size=20')
  assert.equal(hasNextPage(0, 20, 20), false)
  assert.equal(hasNextPage(0, 20, 21), true)
  assert.equal(hasNextPage(1, 20, 40), false)
})

test('adminApi: 목록은 GET, 라벨은 PUT {label}만 보낸다', async (t) => {
  const sent: { url: string; method: string; body?: unknown }[] = []
  setAccessToken('memory-test-token')
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    sent.push({ url: String(url), method: String(init.method ?? 'GET'), body: init.body ? JSON.parse(String(init.body)) : undefined })
    return new Response('{"items":[],"page":0,"size":20,"totalElements":0}', { headers: { 'Content-Type': 'application/json' } })
  })
  await adminApi.expressionReviews({ labeled: false, source: 'GRAY_ZONE', page: 1, size: 20 })
  await adminApi.labelExpressionReview('review/1', 'OFFENSIVE')
  assert.match(sent[0].url, /\/admin\/expression-reviews\?labeled=false&source=GRAY_ZONE&page=1&size=20$/)
  assert.equal(sent[0].method, 'GET')
  assert.match(sent[1].url, /\/admin\/expression-reviews\/review%2F1\/label$/)
  assert.equal(sent[1].method, 'PUT')
  assert.deepEqual(sent[1].body, { label: 'OFFENSIVE' })
  setAccessToken(null)
})

const handlers = [...adminHandlers, ...studentHandlers]
let token = ''
async function call(path: string, body?: unknown, method = body === undefined ? 'GET' : 'PUT') {
  const response = await getResponse(handlers, new Request('http://localhost/api/v1' + path, {
    method, headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  }), { baseUrl: 'http://localhost' })
  assert.ok(response, path)
  return { status: response.status, data: await response.json() }
}
async function login(email: string) {
  setWorkspaceScenario('normal')
  const r = await call('/auth/login', { email, password: 'demo-only' }, 'POST')
  assert.equal(r.status, 200)
  token = r.data.accessToken
}

test('목 서버: 라벨 전은 오래된 순, 글만 있고 학생 ID 없음, 라벨하면 라벨 완료로 옮겨 간다', async () => {
  const backup = structuredClone(expressionReviews)
  try {
    await login('ops@example.test')
    const before = audits.length
    const list = await call('/admin/expression-reviews?labeled=false&page=0&size=20')
    assert.equal(list.status, 200)
    assert.deepEqual(list.data.items.map((r: { id: string }) => r.id), [r1, r2])
    for (const item of list.data.items) assert.deepEqual(Object.keys(item).sort(), ['createdAt', 'id', 'label', 'labeledAt', 'modelVersion', 'source', 'text'])
    assert.equal(audits.length, before + 1) // 열람 감사
    assert.equal(audits[0].targetId, null) // 목록 열람은 대상 ID 없음(core와 같음)
    const only = await call('/admin/expression-reviews?labeled=false&source=COMMUNITY_REPORT&page=0&size=20')
    assert.deepEqual(only.data.items.map((r: { id: string }) => r.id), [r2])
    const saved = await call(`/admin/expression-reviews/${r1}/label`, { label: 'OFFENSIVE' })
    assert.equal(saved.status, 200)
    assert.equal(saved.data.label, 'OFFENSIVE')
    assert.deepEqual((await call('/admin/expression-reviews?labeled=false&page=0&size=20')).data.items.map((r: { id: string }) => r.id), [r2])
    assert.deepEqual((await call('/admin/expression-reviews?labeled=true&page=0&size=20')).data.items.map((r: { id: string }) => r.id), [r1, r3]) // 최근 라벨 순
    assert.equal((await call(`/admin/expression-reviews/${r1}/label`, { label: 'BAD' })).status, 400)
    assert.equal((await call(`/admin/expression-reviews/${r1}/label`, { label: 'CLEAN', extra: 1 })).status, 400)
    const invalid = await call('/admin/expression-reviews/review-1/label', { label: 'CLEAN' })
    assert.equal(invalid.status, 400) // UUID가 아닌 ID
    assert.equal(invalid.data.code, 'VALIDATION_FAILED')
    const missing = await call('/admin/expression-reviews/00000000-0000-4000-8000-000000000000/label', { label: 'CLEAN' })
    assert.equal(missing.status, 404)
    assert.equal(missing.data.code, 'EXPRESSION_REVIEW_NOT_FOUND')
    assert.equal((await call('/admin/expression-reviews?size=0')).status, 400)
  } finally {
    expressionReviews.splice(0, expressionReviews.length, ...backup)
  }
})

test('목 서버: 빈 목록·조회 실패·권한 없음은 서로 다르게 응답한다', async () => {
  await login('ops@example.test')
  setWorkspaceScenario('empty')
  const empty = await call('/admin/expression-reviews?labeled=false&page=0&size=20')
  assert.equal(empty.status, 200)
  assert.deepEqual(empty.data.items, [])
  setWorkspaceScenario('query-fail')
  assert.equal((await call('/admin/expression-reviews?labeled=false&page=0&size=20')).status, 503)
  setWorkspaceScenario('normal')
  await login('content@example.test')
  const forbidden = await call('/admin/expression-reviews?labeled=false&page=0&size=20')
  assert.equal(forbidden.status, 403)
  assert.equal(forbidden.data.code, 'FORBIDDEN')
  assert.equal((await call(`/admin/expression-reviews/${r1}/label`, { label: 'CLEAN' })).status, 403)
  setWorkspaceScenario('normal')
})
