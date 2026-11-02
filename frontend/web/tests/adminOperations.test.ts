import test from 'node:test'
import assert from 'node:assert/strict'
import { adminApi } from '../src/data/admin/api.ts'

test('운영 API는 빈 필터를 생략하고 서버의 확정 응답을 그대로 사용한다', async (t) => {
  const requests: string[] = []
  t.mock.method(globalThis, 'fetch', async (url: string) => {
    requests.push(String(url))
    return new Response(JSON.stringify({ items: [], page: 0, size: 20, totalElements: 0 }), { headers: { 'Content-Type': 'application/json' } })
  })
  await adminApi.jobs('', '')
  await adminApi.audits({ from: '2026-01-01', to: '2026-01-07' }, '')
  await adminApi.missions({ status: '', grade: '', thinkingType: '' })
  assert.equal(new URL(requests[2], 'http://test').search, '')
  assert.equal(new URL(requests[0], 'http://test').searchParams.has('type'), false)
  assert.equal(new URL(requests[0], 'http://test').searchParams.has('status'), false)
  assert.equal(new URL(requests[1], 'http://test').searchParams.has('targetType'), false)
})
