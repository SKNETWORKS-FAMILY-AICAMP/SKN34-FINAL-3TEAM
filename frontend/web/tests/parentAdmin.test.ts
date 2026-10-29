import test from 'node:test'
import assert from 'node:assert/strict'
import { reduceAnalysis, metricText, validPeriod, changeCounts } from '../src/domain/parent.ts'
import type { StreamState, MessageResult } from '../src/domain/parent.ts'
import type { AdminMission } from '../src/domain/admin/operations.ts'
import { hasPermission, missingMissionFields } from '../src/domain/admin/operations.ts'
import { createDemoGateway, demoMissions } from '../src/data/classroom/demoGateway.ts'
import { parentApi } from '../src/data/parent/api.ts'
import { adminApi } from '../src/data/admin/api.ts'
import { setAccessToken } from '../src/data/apiClient.ts'
const scope = { childId: 's1', from: '2026-10-19', to: '2026-10-25' }
const result: MessageResult = {
  messageId: 'm1',
  answer: '확정 답변',
  scope,
  metrics: [],
  evidence: [],
  recordCount: 0,
  source: 'TEMPLATE',
  fallback: { reason: 'AI_UNAVAILABLE', draftVerification: null },
  verification: { numbersMatched: true, quotesMatched: true, contentAllowed: true },
}
test('분석 delta는 임시·result로 교체·error/clarification에서 폐기', () => {
  const initial: StreamState = { phase: 'IDLE', temporary: '' }
  const running = reduceAnalysis(initial, { event: 'delta', data: { text: '검증 전 문장' } })
  assert.equal(running.temporary, '검증 전 문장')
  assert.equal(running.result, undefined)
  const done = reduceAnalysis(running, { event: 'result', data: result })
  assert.equal(done.temporary, '')
  assert.equal(done.result?.answer, '확정 답변')
  assert.equal(reduceAnalysis(running, { event: 'error', data: {} }).temporary, '')
  assert.equal(
    reduceAnalysis(running, { event: 'clarification', data: { question: '기간?', options: [] } })
      .temporary,
    '',
  )
  assert.throws(() =>
    reduceAnalysis(running, {
      event: 'result',
      data: { ...result, verification: { numbersMatched: false, quotesMatched: true } },
    }),
  )
})
test('Metric null은 개수만 표시·허용 권한 없는 상태는 fail closed', () => {
  assert.equal(
    metricText({
      label: '활동',
      value: null,
      count: 2,
      numerator: 2,
      denominator: 3,
      formula: 'a/b',
      period: scope,
      sourceType: 'RECORD',
      state: 'INSUFFICIENT_SAMPLE',
    }),
    '2건',
  )
  assert.equal(hasPermission(undefined, 'SERVICE_OPS'), false)
  assert.equal(hasPermission(['CONTENT'], 'SERVICE_OPS'), false)
  assert.equal(hasPermission(['CONTENT'], 'CONTENT'), true)
})
test('범위 검증·전후 변화는 글자/문장/고정 연결어만 센다', () => {
  assert.ok(validPeriod(scope))
  assert.equal(validPeriod({ ...scope, from: '2026-10-26' }), false)
  assert.equal(validPeriod({ ...scope, from: 'invalid' }), false)
  assert.deepEqual(changeCounts('왜냐하면 A.\n그래서 B!'), {
    chars: 14,
    sentences: 2,
    reasonConnectives: 2,
  })
})
const complete = (): AdminMission => ({
  missionId: 'm',
  status: 'REVIEW_REQUIRED',
  demoOnly: true,
  currentVersion: 1,
  currentRubricVersion: 1,
  publishedVersion: null,
  versions: [
    {
      version: 1,
      title: '자체 문항',
      subject: '국어',
      gradeMin: 3,
      gradeMax: 4,
      thinkingType: 'EVALUATE',
      inputType: 'NARRATIVE',
      question: '까닭을 설명해 주세요.',
      guide: '',
      scene: 'korean',
      sceneUri: '',
      staticSceneUri: '',
      achievementStandards: ['자체 기준'],
      createdAt: '2026-10-26T10:00:00+09:00',
    },
  ],
  rubrics: [
    {
      version: 1,
      elements: [
        {
          code: 'e1',
          label: '까닭',
          description: '',
          points: 1,
          commonErrors: [],
          goodThought: true,
          judgeVerified: false,
        },
      ],
      exampleAnswer: '자체 예시 답',
      forbiddenTerms: [],
      hints: [],
    },
  ],
  reviews: [
    {
      missionVersion: 1,
      rubricVersion: 1,
      result: 'APPROVED',
      comment: '확인',
      createdAt: '2026-10-26T10:00:00+09:00',
    },
  ],
})
test('게시 필수 누락·현재 버전 승인·논술 학년·정답 키 검증', () => {
  const m = complete()
  assert.deepEqual(missingMissionFields(m), [])
  m.currentVersion = 2
  m.versions.push({ ...m.versions[0], version: 2 })
  assert.ok(missingMissionFields(m).includes('현재 버전 검토 승인'))
  m.versions.at(-1)!.inputType = 'ESSAY'
  assert.ok(missingMissionFields(m).includes('논술 학년 5~6'))
  m.versions.at(-1)!.inputType = 'CHOICE'
  assert.ok(missingMissionFields(m).includes('선택 항목'))
  assert.ok(missingMissionFields(m).includes('정답 키'))
})
test('게시본 변경·중단은 진행 중 시도의 문항 스냅샷을 바꾸지 않음', async () => {
  const api = createDemoGateway()
  await api.login('parent@example.test', 'demo-only')
  const c = (await api.children())[0]
  await api.enterStudent(c)
  const old = { ...demoMissions(3)[0], id: 'new-content', title: '게시본 v1' }
  api.publishCatalog(old.id, old)
  const attempt = await api.start(old, c)
  api.publishCatalog(old.id, { ...old, title: '수정 게시본 v2' })
  assert.equal((await api.attempt(attempt.attemptId)).mission.title, '게시본 v1')
  api.publishCatalog(old.id, null)
  assert.equal(
    (await api.missions(c)).some((m) => m.id === old.id),
    false,
  )
  assert.equal((await api.attempt(attempt.attemptId)).mission.title, '게시본 v1')
})
test('학부모 API의 다른 자녀 응답 거부·실제 응답 기간 허용', async (t) => {
  t.mock.method(
    globalThis,
    'fetch',
    async () =>
      new Response(JSON.stringify({ childId: 'other', period: scope, state: 'OK', metrics: [] })),
  )
  await assert.rejects(parentApi.summary(scope), /자녀/)
  t.mock.method(
    globalThis,
    'fetch',
    async () =>
      new Response(
        JSON.stringify({
          childId: 's1',
          period: { from: '2026-10-01', to: '2026-10-02' },
          state: 'OK',
          metrics: [],
        }),
      ),
  )
  assert.equal((await parentApi.summary(scope)).period.from, '2026-10-01')
})
test('관리자 재처리 키 유지·자녀 정보 수정은 재확인 헤더 없이 (#97)', async (t) => {
  const calls: { url: string; init: RequestInit }[] = []
  setAccessToken('memory-test-token')
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    calls.push({ url, init })
    return new Response('{}')
  })
  await adminApi.retry('job1', 'stable-key')
  await adminApi.retry('job1', 'stable-key')
  await parentApi.updateChild('s1', { nickname: '예시', grade: 3 })
  assert.equal(new Headers(calls[0].init.headers).get('Idempotency-Key'), 'stable-key')
  assert.equal(new Headers(calls[1].init.headers).get('Idempotency-Key'), 'stable-key')
  assert.equal(new Headers(calls[2].init.headers).get('X-Reauth-Token'), null) // core 계약에 없는 헤더
  setAccessToken(null)
})
test('SSE 실패 재시도 경로·임시 출력 폐기·AbortSignal 전달', async (t) => {
  const states: StreamState[] = []
  let url = '',
    signal: AbortSignal | undefined
  t.mock.method(globalThis, 'fetch', async (path: string, init: RequestInit) => {
    url = path
    signal = init.signal as AbortSignal
    return new Response(
      'event: delta\ndata: {"text":"임시"}\n\nevent: error\ndata: {"status":503,"code":"VERIFICATION_FAILED","title":"대조 실패","retryable":true}\n\nevent: done\ndata: {}\n\n',
      { headers: { 'Content-Type': 'text/event-stream' } },
    )
  })
  const controller = new AbortController()
  await assert.rejects(
    parentApi.message('c1', '질문', scope, (s) => states.push(s), controller.signal, 'msg1'),
  )
  assert.equal(url, '/api/v1/conversations/c1/messages/msg1/retry')
  assert.equal(signal, controller.signal)
  assert.equal(states.at(-1)?.temporary, '')
  assert.equal(states.at(-1)?.result, undefined)
})
