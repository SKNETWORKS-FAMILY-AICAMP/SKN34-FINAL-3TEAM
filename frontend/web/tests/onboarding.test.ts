import test from 'node:test'
import assert from 'node:assert/strict'
import { onboardingApi, readOnboarding } from '../src/data/onboarding/api.ts'
import { needsOnboarding } from '../src/data/onboarding/queries.ts'
import { setAccessToken } from '../src/data/apiClient.ts'

const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })

test('완료 기록 읽기: 문자열 시각만 완료로, 나머지는 미완료(null)', () => {
  assert.deepEqual(readOnboarding({ completedAt: '2026-11-25T00:00:00Z' }), { completedAt: '2026-11-25T00:00:00Z' })
  assert.deepEqual(readOnboarding({ completedAt: null }), { completedAt: null })
  assert.deepEqual(readOnboarding({ completedAt: 1 }), { completedAt: null })
  assert.deepEqual(readOnboarding(null), { completedAt: null })
})

test('역할별 경로·캐시 금지, PUT은 본문 없이 보낸다', async (t) => {
  setAccessToken('token', 'PARENT')
  t.after(() => setAccessToken(null))
  const calls: { url: string; init: RequestInit }[] = []
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    calls.push({ url, init })
    return json({ completedAt: init.method === 'PUT' ? '2026-11-25T00:00:00Z' : null })
  })
  assert.deepEqual(await onboardingApi.get('PARENT'), { completedAt: null })
  assert.deepEqual(await onboardingApi.complete('STUDENT'), { completedAt: '2026-11-25T00:00:00Z' })
  assert.deepEqual(calls.map(c => [c.url, c.init.method ?? 'GET', c.init.cache, c.init.body ?? null]), [
    ['/api/v1/me/onboarding', 'GET', 'no-store', null],
    ['/api/v1/students/me/onboarding', 'PUT', 'no-store', null],
  ])
})

test('안내 표시: 미완료로 확인된 때만, 조회 중·실패·완료면 띄우지 않는다', () => {
  assert.equal(needsOnboarding({ isSuccess: true, data: { completedAt: null } }), true)
  assert.equal(needsOnboarding({ isSuccess: true, data: { completedAt: '2026-11-25T00:00:00Z' } }), false)
  assert.equal(needsOnboarding({ isSuccess: false }), false)
  assert.equal(needsOnboarding({ isSuccess: false, data: undefined }), false)
})
