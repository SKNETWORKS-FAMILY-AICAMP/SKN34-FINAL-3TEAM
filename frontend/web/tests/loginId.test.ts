// #683 Google 학부모도 /me loginId(=Google 이메일)를 세션에 담는다
import test from 'node:test'
import assert from 'node:assert/strict'

Object.defineProperty(globalThis, 'location', { value: new URL('http://localhost/'), configurable: true })
const { createApiGateway } = await import('../src/data/classroom/apiGateway.ts')
const { setAccessToken } = await import('../src/data/apiClient.ts')
const json = (data: unknown) => new Response(JSON.stringify(data), { headers: { 'Content-Type': 'application/json' } })
const me = (extra: Record<string, unknown>) => ({ userId: 'u', name: '보호자', email: 'parent@example.test', permissions: [], nextAction: 'READY', startPath: '/parent/journal', ...extra })

test('학부모는 Google이든 ID·비밀번호든 loginId를 세션에 담고, 관리자는 담지 않는다', async t => {
  setAccessToken('synthetic', 'PARENT'); t.after(() => setAccessToken(null))
  for (const [body, expected] of [
    [me({ role: 'PARENT', authMethod: 'GOOGLE', loginId: 'parent@example.test' }), 'parent@example.test'],
    [me({ role: 'PARENT', authMethod: 'PASSWORD', email: null, loginId: 'parent01' }), 'parent01'],
    [me({ role: 'PARENT', authMethod: 'GOOGLE', loginId: null }), undefined],
    [me({ role: 'ADMIN', authMethod: 'PASSWORD', loginId: 'ops-kim' }), undefined],
  ] as const) {
    t.mock.method(globalThis, 'fetch', async () => json(body))
    const session = await createApiGateway().restore()
    assert.equal(session?.loginId, expected)
  }
})
