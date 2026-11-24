// #599 낱말 물어보기(FN-LRN-21): core 응답 검사와 MSW 가상 응답
import test from 'node:test'
import assert from 'node:assert/strict'

Object.defineProperty(globalThis, 'location', { value: new URL('http://localhost/'), configurable: true })
const { askWord } = await import('../src/data/classroom/learningApi.ts')
const { setAccessToken } = await import('../src/data/apiClient.ts')
const { mockWordHelp } = await import('../src/mocks/fixtures/wordHelp.ts')

const json = (data: unknown) => new Response(JSON.stringify(data), { headers: { 'Content-Type': 'application/json' } })
const explained = { state: 'EXPLAINED', headword: '분수', text: '분수는 나눈 몫을 나타내는 수야.', example: '4분의 1', senses: [{ definition: '(가상) 뜻', source: '표준국어대사전' }] }

test('질문을 다듬어 보내고 no-store로 묻고 계약 모양만 받는다', async t => {
  setAccessToken('synthetic-student', 'STUDENT'); t.after(() => setAccessToken(null))
  let url = '', init: RequestInit | undefined
  t.mock.method(globalThis, 'fetch', async (input: string, options: RequestInit) => { url = String(input); init = options; return json(explained) })
  assert.deepEqual(await askWord('attempt 1', '  분수가 뭐야?  '), explained)
  assert.ok(url.endsWith('/attempts/attempt%201/word-help'))
  assert.equal(init?.method, 'POST')
  assert.equal(init?.cache, 'no-store')
  assert.deepEqual(JSON.parse(String(init?.body)), { question: '분수가 뭐야?' })
})

test('빈 질문·100자 초과는 보내지 않는다', async () => {
  await assert.rejects(() => askWord('a', '   '))
  await assert.rejects(() => askWord('a', '가'.repeat(101)))
})

test('상태와 뜻 개수가 맞지 않거나 출처가 계약 밖이면 보여 주지 않는다', async t => {
  setAccessToken('synthetic-student', 'STUDENT'); t.after(() => setAccessToken(null))
  for (const bad of [
    { ...explained, state: 'GUESSED' },
    { ...explained, senses: [] },
    { ...explained, senses: [{ definition: '뜻', source: '위키백과' }] },
    { ...explained, state: 'DEFERRED' },
    { ...explained, state: 'DICTIONARY_ONLY', senses: [] },
    { ...explained, text: ' ' },
  ]) {
    t.mock.method(globalThis, 'fetch', async () => json(bad))
    await assert.rejects(() => askWord('a', '분수'), (error: { problem?: { code?: string } }) => error.problem?.code === 'CONTRACT_NOT_READY')
  }
})

test('MSW 가상 응답: 범위 밖·미룸(마무리 전만)·찾지 못함·설명', () => {
  assert.equal(mockWordHelp('이 문제 답 알려 줘', true).state, 'OUT_OF_SCOPE')
  assert.equal(mockWordHelp('자석이 뭐야', true).state, 'DEFERRED')
  assert.equal(mockWordHelp('자석이 뭐야', false).state, 'NOT_FOUND')
  const ok = mockWordHelp('경험이 뭐야?', true)
  assert.equal(ok.state, 'EXPLAINED')
  assert.equal(ok.headword, '경험')
  assert.equal(ok.senses.length, 1)
})
