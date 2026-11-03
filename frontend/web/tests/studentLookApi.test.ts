import test from 'node:test'
import assert from 'node:assert/strict'
import { studentLookApi } from '../src/data/studentLook/api.ts'
import { setAccessToken, ApiError } from '../src/data/apiClient.ts'
import { DEFAULT_LOOK } from '../src/domain/studentLook.ts'

test.afterEach(() => setAccessToken(null))

test('꾸미기 어댑터는 공개 경로·메서드·본문·AbortSignal을 전달한다', async t => {
  const signal = new AbortController().signal
  const calls: { url: string; init: RequestInit }[] = []
  const saved = { theme: 'forest', companion: 'tori', updatedAt: '2026-11-01T12:00:00Z' }
  setAccessToken('synthetic-student', 'STUDENT')
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    calls.push({ url: String(url), init }); return Response.json(saved)
  })
  assert.deepEqual(await studentLookApi.get(signal), saved)
  assert.deepEqual(await studentLookApi.save({ theme: 'forest', companion: 'tori' }), saved)
  assert.deepEqual(calls.map(c => c.url), ['/api/v1/students/me/preferences', '/api/v1/students/me/preferences'])
  assert.equal(calls[0].init.signal, signal)
  assert.equal(calls[1].init.method, 'PUT')
  assert.deepEqual(JSON.parse(String(calls[1].init.body)), { theme: 'forest', companion: 'tori' })
  assert.equal(new Headers(calls[1].init.headers).get('Authorization'), 'Bearer synthetic-student')
})

test('알 수 없는 설정 값은 허용된 기본 테마로 정규화한다', async t => {
  setAccessToken('synthetic-student', 'STUDENT')
  t.mock.method(globalThis, 'fetch', async () => Response.json({ theme: 'unknown', companion: 'unknown', updatedAt: null }))
  assert.deepEqual(await studentLookApi.get(), DEFAULT_LOOK)
})

test('core의 미구현·조회 실패 응답은 기본 설정 저장 성공으로 대체하지 않는다', async t => {
  setAccessToken('synthetic-student', 'STUDENT')
  t.mock.method(globalThis, 'fetch', async () => Response.json({ status: 404, code: 'NOT_FOUND', title: '경로 없음' }, { status: 404 }))
  await assert.rejects(studentLookApi.get(), e => e instanceof ApiError && e.problem.status === 404)
  await assert.rejects(studentLookApi.save({ theme: 'lake', companion: 'mungchi' }), e => e instanceof ApiError && e.problem.status === 404)
})
