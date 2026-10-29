import test from 'node:test'
import assert from 'node:assert/strict'
import { createApiGateway } from '../src/data/classroom/apiGateway.ts'
import { DraftConflictError, demoMissions } from '../src/data/classroom/demoGateway.ts'
import { blankAnswer, previousWeek } from '../src/domain/classroom.ts'
import { setAccessToken } from '../src/data/apiClient.ts'
import type { Child } from '../src/domain/classroom.ts'

const child: Child = {
  id: 'child-1',
  nickname: '가상 학생',
  grade: 3,
  birthYear: 2017,
  plan: 'PREMIUM',
}
const answer = { ...blankAnswer('NARRATIVE'), text: '원문' }
const attempt = {
  attemptId: 'a-1',
  studentId: child.id,
  mission: demoMissions(3)[2],
  answers: [],
  status: 'IN_PROGRESS',
  helped: false,
}
const json = (data: unknown, status = 200, headers = {}) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
test('공개 core 경로만 호출, 메모리 토큰·ETag·If-Match·멱등 키', async (t) => {
  const calls: { path: string; init: RequestInit }[] = []
  t.mock.method(globalThis, 'fetch', async (path: string, init: RequestInit) => {
    calls.push({ path, init })
    if (path.endsWith('/draft')) return json({ version: '2' }, 200, { ETag: '"2"' })
    return json(attempt)
  })
  setAccessToken('memory-only')
  const api = createApiGateway()
  const draft = await api.saveDraft('a-1', { answer, memo: '내 메모', version: '"1"' })
  assert.equal(draft.version, '"2"')
  await api.submit('a-1', answer, 'stable-key')
  assert.equal(
    calls.every((c) => c.path.startsWith('/api/v1/') && !c.path.includes('/internal/')),
    true,
  )
  assert.equal(new Headers(calls[0].init.headers).get('If-Match'), '"1"')
  assert.equal(new Headers(calls[0].init.headers).get('Authorization'), 'Bearer memory-only')
  assert.equal(new Headers(calls[1].init.headers).get('Idempotency-Key'), 'stable-key')
  assert.equal(JSON.parse(String(calls[1].init.body)).memo, undefined)
  setAccessToken(null)
})
test('404는 예시나 빈 배열로 대체하지 않음', async (t) => {
  let requests = 0
  t.mock.method(globalThis, 'fetch', async () => {
    requests++
    return json({ title: '미구현', code: 'NOT_FOUND', status: 404 }, 404)
  })
  const api = createApiGateway()
  assert.equal(api.login, undefined) // 실제 모드는 Google 인증만 (#97)
  await assert.rejects(api.children())
  await assert.rejects(
    api.submit(
      'a-1',
      { ...blankAnswer('SOLUTION_STEPS'), finalAnswer: '6', steps: ['3+3'] },
      'no-contract',
    ),
  )
  assert.equal(requests, 2) // 자녀 목록·풀이 제출(3.8과 같은 API 경로) 모두 404를 그대로 실패로
})
test('실제 API의 초안 충돌도 명시적으로 비교 가능', async (t) => {
  t.mock.method(globalThis, 'fetch', async () =>
    json(
      {
        code: 'ATTEMPT_DRAFT_CONFLICT',
        status: 409,
        latest: { version: 2, content: { answer: { text: '서버 초안' }, memo: '서버 메모' } },
      },
      409,
    ),
  )
  await assert.rejects(
    createApiGateway().saveDraft('a-1', { answer, memo: '', version: '"1"' }),
    (error) =>
      error instanceof DraftConflictError &&
      error.latest.version === '"2"' &&
      error.latest.answer.text === '서버 초안',
  )
})
test('분석 SSE의 검증 전 delta는 버리고 대조 완료 result만 사용', async (t) => {
  t.mock.method(globalThis, 'fetch', async (path: string) =>
    path.endsWith('/conversations')
      ? json({ conversationId: 'c-1' })
      : new Response(
          'event: delta\ndata: {"text":"확인 안 된 문장"}\n\nevent: result\ndata: {"source":"LLM","answer":"검증된 답","evidence":[],"verification":{"numbersMatched":true,"quotesMatched":true}}\n\nevent: done\ndata: {}\n\n',
          { headers: { 'Content-Type': 'text/event-stream' } },
        ),
  )
  const r = await createApiGateway().analyze(child, previousWeek, '질문')
  assert.equal(r.answer, '검증된 답')
})
test('숫자/인용 대조 실패를 성공 결과로 표시하지 않음', async (t) => {
  t.mock.method(globalThis, 'fetch', async (path: string) =>
    path.endsWith('/conversations')
      ? json({ conversationId: 'c-1' })
      : new Response(
          'event: result\ndata: {"verification":{"numbersMatched":false,"quotesMatched":true}}\n\n',
        ),
  )
  await assert.rejects(createApiGateway().analyze(child, previousWeek, '질문'))
})
