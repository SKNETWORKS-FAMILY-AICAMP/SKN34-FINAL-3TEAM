// #134 MSW 학부모 응답이 core 계약과 같은 모양인지: 리포트 목록 {items}만, 자녀 수정은 선택 필드
import test from 'node:test'
import assert from 'node:assert/strict'
Object.defineProperty(globalThis, 'location', { value: new URL('http://localhost/'), configurable: true })
const { setupServer } = await import('msw/node')
const { parentHandlers } = await import('../src/mocks/handlers/parent.ts')
const { studentHandlers } = await import('../src/mocks/handlers/student.ts')
const server = setupServer(...parentHandlers, ...studentHandlers)
server.listen({ onUnhandledRequest: 'error' })
test.after(() => server.close())
const base = 'http://localhost/api/v1'

async function parent() {
  const login = await fetch(base + '/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'parent@example.test', password: 'demo-only' }),
  })
  const headers = { Authorization: `Bearer ${(await login.json()).accessToken}` }
  const children = (await (await fetch(base + '/children', { headers })).json()).items as { id: string; nickname: string; grade: number }[]
  return { headers, child: children[0] }
}

test('MSW 리포트 목록은 page 봉투 없이 {items}', async () => {
  const { headers, child } = await parent()
  const response = await fetch(`${base}/children/${child.id}/reports`, { headers })
  assert.equal(response.status, 200)
  const data = await response.json()
  assert.deepEqual(Object.keys(data), ['items'])
  assert.ok(Array.isArray(data.items))
})

test('MSW 자녀 수정은 nickname·grade 중 보낸 필드만 바꾸고 계약 밖 필드는 거부', async () => {
  const { headers, child } = await parent()
  const patch = (body: unknown) =>
    fetch(`${base}/children/${child.id}`, {
      method: 'PATCH',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  const graded = await (await patch({ grade: 4 })).json()
  assert.deepEqual([graded.nickname, graded.grade], [child.nickname, 4])
  const renamed = await (await patch({ nickname: ' 바꾼 별명 ' })).json()
  assert.deepEqual([renamed.nickname, renamed.grade], ['바꾼 별명', 4])
  for (const invalid of [{ nickname: ' ' }, { grade: 7 }, { birthYear: 2016 }])
    assert.equal((await patch(invalid)).status, 400, JSON.stringify(invalid))
})
