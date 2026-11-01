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
test('동일 초안 ETag에서도 제출·마무리·돌아보기 후 상세 HTTP 캐시를 재사용하지 않는다', async (t) => {
  let current = { ...attempt, finishedAt: null as string | null, reflection: null as unknown }
  let cached: typeof current | undefined
  const reads: RequestInit[] = []
  t.mock.method(globalThis, 'fetch', async (path: string, init: RequestInit) => {
    if (path.endsWith('/answers')) return json({}, 201)
    if (path.endsWith('/finish')) {
      current = { ...current, finishedAt: '2026-10-30T08:09:12Z' }
      return json({})
    }
    if (path.endsWith('/reflection')) {
      current = { ...current, status: 'COMPLETED', reflection: { difficulty: '쉬웠어', text: '검증 돌아보기' } }
      return json({})
    }
    reads.push(init)
    // Model a browser holding the old representation with the same draft ETag.
    if (cached && init.cache !== 'no-store') return json(cached, 200, { ETag: '"2"' })
    cached ??= structuredClone(current)
    return json(current, 200, { ETag: '"2"' })
  })
  const api = createApiGateway()
  assert.equal((await api.attempt('a-1')).finishedAt, null)
  await api.submit('a-1', answer, 'cache-regression')
  assert.equal((await api.finish('a-1')).finishedAt, '2026-10-30T08:09:12Z')
  const completed = await api.reflect('a-1', { difficulty: '쉬웠어', text: '검증 돌아보기' })
  assert.equal(completed.status, 'COMPLETED')
  assert.equal(reads.length, 4)
  assert.ok(reads.every((init) => init.cache === 'no-store'))
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
          'event: delta\ndata: {"text":"확인 안 된 문장"}\n\nevent: result\ndata: {"source":"LLM","answer":"검증된 답","evidence":[],"verification":{"numbersMatched":true,"quotesMatched":true,"contentAllowed":true}}\n\nevent: done\ndata: {}\n\n',
          { headers: { 'Content-Type': 'text/event-stream' } },
        ),
  )
  const r = await createApiGateway().analyze(child, previousWeek, '질문')
  assert.equal(r.answer, '검증된 답')
})
const sse = (frames: string) => new Response(frames, { headers: { 'Content-Type': 'text/event-stream' } })
test('피드백 result의 null 필드·근거 없는 요소 sourceType null·versions를 받고 판정 ID를 그대로 (#82)', async (t) => {
  t.mock.method(globalThis, 'fetch', async () =>
    sse(
      'event: result\ndata: {"status":"DONE","judgment":{"judgmentId":"j-1","result":"PARTIAL","trial":true,' +
        '"elements":[{"elementId":"6f1c2b9e-0000-4000-8000-000000000001","label":"까닭","satisfied":false,"quote":null,"sourceType":null}],' +
        '"heldReason":null},"followup":null,"nextActions":["FINISH"],' +
        '"versions":{"mission":"M-1@1","rubric":"M-1@1","model":null,"prompt":null}}\n\nevent: done\ndata: {}\n\n',
    ),
  )
  const f = await createApiGateway().feedback('a-1', 'ans-1', () => {})
  assert.equal(f.judgment?.judgmentId, 'j-1')
  assert.equal(f.judgment?.elements?.[0].sourceType, null)
  assert.equal(f.judgment?.heldReason, null)
  assert.equal(f.followup, null)
  assert.equal(f.versions?.model, null)
})
test('처리 중 결과의 judgment·followup·versions null도 받음', async (t) => {
  t.mock.method(globalThis, 'fetch', async () =>
    sse('event: result\ndata: {"status":"RUNNING","judgment":null,"followup":null,"nextActions":[],"versions":null}\n\n'),
  )
  const f = await createApiGateway().feedback('a-1', 'ans-1', () => {})
  assert.equal(f.status, 'RUNNING')
  assert.equal(f.judgment, null)
})
test('판정에 judgmentId가 없거나 sourceType이 계약 밖이면 계약 오류', async (t) => {
  for (const judgment of [
    '{"result":"CORRECT","trial":false,"elements":[],"heldReason":null}',
    '{"judgmentId":"j-1","result":"CORRECT","trial":false,"elements":[{"elementId":"e","label":"l","satisfied":true,"quote":"q","sourceType":"GUESS"}],"heldReason":null}',
  ]) {
    t.mock.method(globalThis, 'fetch', async () =>
      sse(`event: result\ndata: {"status":"DONE","judgment":${judgment},"followup":null,"nextActions":["FINISH"],"versions":null}\n\n`),
    )
    await assert.rejects(createApiGateway().feedback('a-1', 'ans-1', () => {}), (e: Error & { problem?: { code: string } }) =>
      e.problem?.code === 'CONTRACT_NOT_READY')
  }
})
test('피드백 error의 retryable:false를 그대로 전달 (재시도 버튼 숨김 근거)', async (t) => {
  t.mock.method(globalThis, 'fetch', async () =>
    sse('event: status\ndata: {"state":"RUNNING"}\n\nevent: error\ndata: {"code":"AI_UNAVAILABLE","retryable":false}\n\nevent: done\ndata: {}\n\n'),
  )
  await assert.rejects(createApiGateway().feedback('a-1', 'ans-1', () => {}), (e: Error & { problem?: { retryable?: boolean; status: number } }) =>
    e.problem?.retryable === false && e.problem.status === 503)
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
