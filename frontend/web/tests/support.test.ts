import test from 'node:test'
import assert from 'node:assert/strict'
import { adminApi } from '../src/data/admin/api.ts'
import { setAccessToken } from '../src/data/apiClient.ts'

test('정정 재시도는 동일한 Idempotency-Key와 enum 결과를 전달한다', async () => {
  const original = globalThis.fetch
  const requests: RequestInit[] = []
  setAccessToken('support-token', 'ADMIN')
  globalThis.fetch = async (_input, init) => {
    requests.push(init!)
    return new Response(JSON.stringify({ reportId: 'r', status: 'RESOLVED', corrections: [] }), { headers: { 'Content-Type': 'application/json' } })
  }
  try {
    const key = crypto.randomUUID()
    await adminApi.correction('r', '근거 확인', 'CORRECT', key)
    await adminApi.correction('r', '근거 확인', 'CORRECT', key)
    for (const req of requests) {
      assert.equal(new Headers(req.headers).get('Idempotency-Key'), key)
      assert.deepEqual(JSON.parse(req.body as string), { reason: '근거 확인', corrected: 'CORRECT' })
    }
  } finally { globalThis.fetch = original; setAccessToken(null) }
})
