import test from 'node:test'
import assert from 'node:assert/strict'
import { dailyReportSummary } from '../src/domain/dailyReportSummary.ts'
import type { DailyProblem } from '../src/domain/parent.ts'

const problem = (patch: Partial<DailyProblem> = {}): DailyProblem => ({
  missionId: 'mission', title: '문제', context: 'EXTRA', judgment: 'CORRECT',
  followups: [], finalAnswer: null, elements: [], reflection: null, quotes: [], ...patch,
})

test('counts activities, not follow-up messages or repeated element labels; preserves held and unknown judgments', () => {
  const problems = [
    problem({ followups: [{ question: '왜?', answer: '근거' }, { question: '또?', answer: '추가 근거' }], elements: [{ label: '근거', satisfied: true }, { label: '근거', satisfied: true }, { label: '주장', satisfied: false }], reflection: { written: true, difficulty: 'EASY', text: null } }),
    problem({ judgment: 'PARTIAL', followups: [{ question: '왜?', answer: '  ' }], elements: [{ label: '근거', satisfied: true }], reflection: { written: true, difficulty: '보통', text: null } }),
    problem({ judgment: 'RETHINK', reflection: { written: true, difficulty: 'HARD', text: null } }),
    problem({ judgment: 'HELD', reflection: { written: true, difficulty: 'unknown', text: null } }),
    problem({ judgment: null }),
  ]
  const result = dailyReportSummary({ problems, metrics: [] })
  assert.equal(result.total, 5)
  assert.equal(result.followupActivities, 2)
  assert.equal(result.answeredActivities, 1)
  assert.equal(result.reflections, 4)
  assert.deepEqual(result.judgments.map(j => j.count), [1, 1, 1, 1, 1])
  assert.deepEqual(result.reviewIndices, [2])
  assert.deepEqual(result.elements, [{ label: '근거', indices: [0, 1] }])
  assert.deepEqual(result.difficulties.map(d => d.count), [1, 1, 1])
  assert.deepEqual(result.difficulties.map(d => d.indices), [[0], [1], [2]])
  assert.equal(result.difficultyMissing, 2)
  assert.deepEqual(result.difficultyMissingIndices, [3, 4])
})

test('reports without a sharing preference retain follow-up counts and recorded difficulty', () => {
  const result = dailyReportSummary({ metrics: [], problems: [problem({ followups: [{ question: '왜?', answer: '내 생각' }], reflection: { written: true, difficulty: 'EASY', text: null } })] })
  assert.equal(result.followupActivities, 1)
  assert.equal(result.answeredActivities, 1)
  assert.equal(result.total, 1)
  assert.equal(result.reflections, 1)
  assert.equal(result.difficulties[0].count, 1)
  assert.deepEqual(result.difficulties[0].indices, [0])
})

test('missing details and no-record reports are distinct; unwritten reflections are not difficulty choices', () => {
  const unavailable = dailyReportSummary({ metrics: [] })
  assert.equal(unavailable.total, null)
  assert.equal(unavailable.reflections, null)
  assert.equal(unavailable.available, false)
  assert.equal(unavailable.followupActivities, null)
  assert.equal(unavailable.answeredActivities, null)
  const empty = dailyReportSummary({ problems: [], metrics: [] })
  assert.equal(empty.total, 0)
  assert.equal(empty.reflections, 0)
  const invalidReflection = dailyReportSummary({ metrics: [], problems: [problem({ reflection: { written: false, difficulty: 'EASY', text: null } })] })
  assert.equal(invalidReflection.difficultyRecorded, 0)
  assert.equal(invalidReflection.difficultyMissing, 1)
  assert.deepEqual(invalidReflection.difficultyMissingIndices, [0])
})
