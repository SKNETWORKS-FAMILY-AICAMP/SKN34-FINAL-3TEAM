import test from 'node:test'
import assert from 'node:assert/strict'
import { apiFetch, ApiError, setAccessToken, withAuth } from '../src/data/apiClient.ts'
import { streamSse } from '../src/data/sse.ts'
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const expired = () => json({ code: 'TOKEN_EXPIRED', title: '만료', status: 401 }, 401)

test('동시 만료 요청은 refresh 1회 공유, 재시도 시 키·본문 보존', async (t) => {
  let refreshes = 0
  const requests: RequestInit[] = []
  setAccessToken('expired')
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    if (url.endsWith('/auth/refresh')) {
      refreshes++
      await new Promise((r) => setTimeout(r, 30))
      return json({ accessToken: 'new-token' })
    }
    requests.push(init)
    return new Headers(init.headers).get('Authorization') === 'Bearer new-token'
      ? json({ ok: true })
      : expired()
  })
  const init = {
    method: 'POST',
    body: '{"text":"원문"}',
    headers: { 'Idempotency-Key': 'same-key' },
  }
  await Promise.all([apiFetch('/attempts/a/answers', init), apiFetch('/attempts/b/answers', init)])
  assert.equal(refreshes, 1)
  assert.equal(requests.length, 4)
  assert.equal(
    requests.every(
      (r) => r.body === init.body && new Headers(r.headers).get('Idempotency-Key') === 'same-key',
    ),
    true,
  )
  setAccessToken(null)
})
test('refresh 실패는 세션 제거·재로그인 안내, 무한 재시도 없음', async (t) => {
  let calls = 0
  setAccessToken('expired')
  t.mock.method(globalThis, 'fetch', async (url: string) => {
    calls++
    return url.endsWith('/auth/refresh')
      ? json({ code: 'UNAUTHENTICATED', status: 401, title: '재인증' }, 401)
      : expired()
  })
  await assert.rejects(
    apiFetch('/children'),
    (e) =>
      e instanceof ApiError &&
      e.problem.code === 'UNAUTHENTICATED' &&
      e.message.includes('다시 로그인'),
  )
  assert.equal(calls, 2)
  assert.equal(withAuth().has('Authorization'), false)
})
test('SSE도 같은 refresh 경로 사용, 원래 스트림 요청 본문 유지', async (t) => {
  let refreshes = 0
  setAccessToken('expired')
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    if (url.endsWith('/auth/refresh')) {
      refreshes++
      return json({ accessToken: 'new-token' })
    }
    if (new Headers(init.headers).get('Authorization') !== 'Bearer new-token') return expired()
    assert.equal(init.body, '{"question":"질문"}')
    return new Response('event: result\ndata: {"ok":true}\n\nevent: done\ndata: {}\n\n')
  })
  const events: string[] = []
  await streamSse('/conversations/c/messages', {
    body: { question: '질문' },
    onEvent: (e) => events.push(e.event),
  })
  assert.equal(refreshes, 1)
  assert.deepEqual(events, ['result', 'done'])
  setAccessToken(null)
})
test('로그인 실패는 refresh하지 않음, 갱신 뒤 다시 만료되어도 요청당 1회만 재시도', async (t) => {
  let calls = 0
  t.mock.method(globalThis, 'fetch', async (url: string) => {
    calls++
    return url.endsWith('/auth/refresh') ? json({ accessToken: 'still-expired' }) : expired()
  })
  await assert.rejects(apiFetch('/auth/login', { method: 'POST' }))
  assert.equal(calls, 1)
  calls = 0
  setAccessToken('expired')
  await assert.rejects(apiFetch('/children'))
  assert.equal(calls, 3)
  setAccessToken(null)
})
test('로그아웃 이후 도착한 refresh는 토큰을 되살리지 않음', async (t) => {
  let release!: () => void
  const wait = new Promise<void>((r) => {
    release = r
  })
  setAccessToken('expired')
  t.mock.method(globalThis, 'fetch', async (url: string) => {
    if (url.endsWith('/auth/refresh')) {
      await wait
      return json({ accessToken: 'late-token' })
    }
    return expired()
  })
  const request = apiFetch('/children')
  await new Promise((r) => setTimeout(r, 10))
  setAccessToken(null)
  release()
  await assert.rejects(request)
  assert.equal(withAuth().has('Authorization'), false)
})
