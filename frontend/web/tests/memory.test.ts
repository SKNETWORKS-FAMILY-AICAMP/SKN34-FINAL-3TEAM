import test from 'node:test'
import assert from 'node:assert/strict'
import {
  explanationAttempts,
  explanationSentences,
  memoryFailure,
  memoryQuery,
  readMemoryExplanation,
  readMemorySearch,
} from '../src/domain/memory.ts'
import { ApiError } from '../src/data/apiClient.ts'

// 추억 검색·설명 응답 읽기·규칙(P27, API 명세 2.12, #567). 가상 값만 쓴다.

const mission = (n: number) => ({ missionId: `m${n}`, title: `문제 ${n}`, attemptId: `a${n}`, answerExcerpt: `답 ${n}` })
const card = (n: number, missions = [mission(n)]) => ({ themeId: `t${n}`, weekStart: '2026-11-02', title: `테마 ${n}`, imageUrl: null, missions, score: 0.5 })

test('검색 결과는 세 상태와 카드 3개까지만 받고, 상태와 카드 수가 어긋나면 성공으로 바꾸지 않는다', () => {
  const ok = readMemorySearch({ state: 'RESULTS', cards: [card(1, [mission(1), mission(2)]), { ...card(2), imageUrl: 'https://img.test/2.png', extra: 1 }] })
  assert.equal(ok.cards.length, 2)
  assert.deepEqual(ok.cards[0].missions.map((m) => m.attemptId), ['a1', 'a2'])
  assert.equal(ok.cards[1].imageUrl, 'https://img.test/2.png')
  assert.deepEqual(readMemorySearch({ state: 'NO_RESULTS', cards: [] }), { state: 'NO_RESULTS', cards: [] })
  assert.deepEqual(readMemorySearch({ state: 'NO_RECORDS', cards: [] }), { state: 'NO_RECORDS', cards: [] })
  for (const bad of [
    null,
    { state: 'FOUND', cards: [] },
    { state: 'RESULTS', cards: [] },
    { state: 'NO_RESULTS', cards: [card(1)] },
    { state: 'RESULTS', cards: [card(1), card(2), card(3), card(4)] },
    { state: 'RESULTS', cards: [{ ...card(1), missions: [] }] },
    { state: 'RESULTS', cards: [{ ...card(1), weekStart: '11/02' }] },
    { state: 'RESULTS', cards: [{ ...card(1), score: '0.5' }] },
    { state: 'RESULTS', cards: [card(1, [{ ...mission(1), attemptId: '' }])] },
  ]) assert.throws(() => readMemorySearch(bad), /확인하지 못/)
})

test('질문은 앞뒤 공백을 빼고 1~200자일 때만 보낸다', () => {
  assert.equal(memoryQuery('  고양이 얘기  '), '고양이 얘기')
  assert.equal(memoryQuery('   '), null)
  assert.equal(memoryQuery('가'.repeat(200)), '가'.repeat(200))
  assert.equal(memoryQuery('가'.repeat(201)), null)
})

test('설명에는 카드마다 가장 관련 높은 문제 1개씩, 최대 3개를 보낸다(근거는 카드 단위)', () => {
  const { cards } = readMemorySearch({ state: 'RESULTS', cards: [card(1, [mission(1), mission(9)]), card(2), card(3)] })
  assert.deepEqual(explanationAttempts(cards), ['a1', 'a2', 'a3'])
  assert.deepEqual(explanationAttempts(cards.slice(0, 1)), ['a1'])
})

test('설명은 보낸 시도만 근거로 받고, 근거 부족·실패는 글을 버린다', () => {
  const sent = ['a1', 'a2']
  const citations = [{ no: 1, themeId: 't1', weekStart: '2026-11-02', attemptId: 'a1' }, { no: 2, themeId: 't2', weekStart: '2026-10-26', attemptId: 'a2' }]
  const ok = readMemoryExplanation({ state: 'GENERATED', text: '첫 문장[1]. 둘째 문장[1][2].', citations }, sent)
  assert.equal(ok.citations.length, 2)
  assert.deepEqual(readMemoryExplanation({ state: 'FAILED', text: '대체 문장', citations }, sent), { state: 'FAILED', text: null, citations: [] })
  assert.deepEqual(readMemoryExplanation({ state: 'INSUFFICIENT' }, sent), { state: 'INSUFFICIENT', text: null, citations: [] })
  for (const bad of [
    { state: 'DONE' },
    { state: 'GENERATED', text: '', citations },
    { state: 'GENERATED', text: '문장[1].', citations: [] },
    { state: 'GENERATED', text: '문장[1].', citations: [{ ...citations[0], attemptId: 'other' }] },
    { state: 'GENERATED', text: '문장[1].', citations: [{ ...citations[0], no: 3 }] },
    { state: 'GENERATED', text: '문장[1].', citations: [citations[0], { ...citations[1], no: 1 }] },
    { state: 'GENERATED', text: '문장[3].', citations },
  ]) assert.throws(() => readMemoryExplanation(bad, sent), /확인하지 못/)
})

test('설명 글을 문장으로 나누고 문장 끝 번호를 근거 카드에 잇는다', () => {
  const citations = [{ no: 1, themeId: 't1', weekStart: '2026-11-02', attemptId: 'a1' }, { no: 2, themeId: 't2', weekStart: '2026-10-26', attemptId: 'a2' }]
  const e = readMemoryExplanation({ state: 'GENERATED', text: '"소리"라고 썼어요[1]. 두 회차 모두 까닭을 들었어요[1][2]! 끝[2]', citations }, ['a1', 'a2'])
  assert.deepEqual(explanationSentences(e).map((s) => [s.text, s.citations.map((c) => c.attemptId)]), [
    ['"소리"라고 썼어요.', ['a1']],
    ['두 회차 모두 까닭을 들었어요!', ['a1', 'a2']],
    ['끝', ['a2']],
  ])
  assert.deepEqual(explanationSentences({ state: 'FAILED', text: null, citations: [] }), [])
})

test('오류는 한도·장애·입력 오류로 나누고 장애는 횟수를 줄이지 않는다(결정 기록 9.1·13.1)', () => {
  const err = (status: number, detail?: string) => new ApiError({ status, code: 'X', title: 't', ...(detail ? { detail } : {}) })
  assert.deepEqual(memoryFailure(err(429, '내일 0시(KST)에 초기화돼요.')), { kind: 'LIMIT', usageCounted: false, detail: '내일 0시(KST)에 초기화돼요.' })
  for (const s of [502, 503, 504]) assert.equal(memoryFailure(err(s)).kind, 'UNAVAILABLE')
  assert.equal(memoryFailure(err(503)).usageCounted, false)
  assert.deepEqual(memoryFailure(err(400)), { kind: 'INVALID', usageCounted: false, detail: null })
  assert.deepEqual(memoryFailure(err(422)), { kind: 'INVALID', usageCounted: true, detail: null })
  assert.equal(memoryFailure(new TypeError('Failed to fetch')).kind, 'UNAVAILABLE')
  assert.equal(memoryFailure(err(403)).kind, 'OTHER')
})
