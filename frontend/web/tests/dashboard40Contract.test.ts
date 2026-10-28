import test from 'node:test'
import assert from 'node:assert/strict'
import { createApiGateway } from '../src/data/classroom/apiGateway.ts'
import { parentApi } from '../src/data/parent/api.ts'
import { recordReflection } from '../src/data/recordDto.ts'
import type { Child } from '../src/domain/classroom.ts'

const child: Child = { id: 'child-40', nickname: '가상 학생', grade: 3, birthYear: 2017 }
const period = { from: '2026-09-01', to: '2026-09-30' }
const scope = { childId: child.id, ...period }
const attempt = (id: number) => ({ attemptId: `attempt-${id}`, studentId: child.id,
  mission: { id: 'mission-40', title: '미션', inputType: 'NARRATIVE' }, status: 'COMPLETED',
  answers: [], helped: false, reflection: { difficulty: 'EASY', text: null } })
const response = (body: unknown) => new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })

test('학생 기록은 선택 기간을 서버로 전달하고 100건 뒤 페이지까지 소비한다', async (t) => {
  const urls: URL[] = []
  t.mock.method(globalThis, 'fetch', async (url: string) => {
    const parsed = new URL(url, 'http://localhost'); urls.push(parsed)
    const page = Number(parsed.searchParams.get('page'))
    return response({ studentId: child.id, state: 'OK', period, inclusionRule: 'P08', page, size: 100, totalElements: 101,
      items: page === 0 ? Array.from({ length: 100 }, (_, i) => attempt(i)) : [attempt(100)] })
  })
  const records = await createApiGateway().records(child, 'STUDENT', period)
  assert.equal(records.length, 101)
  assert.deepEqual(records[0].reflection, { difficulty: '쉬웠어', text: '' })
  assert.equal(urls.length, 2)
  for (const url of urls) {
    assert.equal(url.pathname, '/api/v1/students/me/attempts')
    assert.equal(url.searchParams.get('from'), period.from)
    assert.equal(url.searchParams.get('to'), period.to)
  }
  assert.equal(urls[1].searchParams.get('page'), '1')
})

test('조회 실패·처리 중·다른 학생·중복 페이지를 빈 기록으로 바꾸지 않는다', async (t) => {
  let body: unknown
  t.mock.method(globalThis, 'fetch', async () => response(body))
  const api = createApiGateway()
  const valid = { studentId: child.id, state: 'OK', period, page: 0, size: 1, totalElements: 2, items: [attempt(1)] }
  for (const state of ['FAILED', 'PROCESSING']) {
    body = { ...valid, state }
    await assert.rejects(api.records(child, 'STUDENT', period))
  }
  body = { ...valid, studentId: 'foreign' }
  await assert.rejects(api.records(child, 'STUDENT', period))
  body = valid // server repeats page 0 instead of advancing
  await assert.rejects(api.records(child, 'STUDENT', period))
})

test('학부모 페이지·상세 요청은 선택 기간을 유지하고 wire 돌아보기 DTO를 표시값으로 변환한다', async (t) => {
  const urls: URL[] = []
  t.mock.method(globalThis, 'fetch', async (url: string) => {
    const parsed = new URL(url, 'http://localhost'); urls.push(parsed)
    return response(parsed.pathname.endsWith('/attempts')
      ? { childId: child.id, state: 'OK', period, inclusionRule: 'P08', page: 2, size: 20, totalElements: 41, items: [attempt(40)] }
      : { ...attempt(40), state: 'OK', period })
  })
  const page = await parentApi.records(scope, undefined, 2)
  assert.equal(page.totalElements, 41)
  assert.equal(page.items[0].reflection?.difficulty, '쉬웠어')
  const detail = await parentApi.record(child.id, 'attempt-40', undefined, period)
  assert.deepEqual(detail.period, period)
  assert.equal(urls[0].searchParams.get('page'), '2')
  for (const url of urls) assert.equal(url.searchParams.get('from'), period.from)
})

test('학부모 상세는 타 자녀 응답과 알 수 없는 돌아보기 값을 거부한다', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => response({ ...attempt(1), studentId: 'foreign', state: 'OK', period }))
  await assert.rejects(parentApi.record(child.id, 'attempt-1', undefined, period))
  assert.throws(() => recordReflection({ difficulty: 'UNKNOWN', text: null }))
  assert.equal(recordReflection(null), undefined)
  assert.deepEqual(recordReflection({ difficulty: 'HARD', text: '원문 그대로' }), { difficulty: '어려웠어', text: '원문 그대로' })
})
