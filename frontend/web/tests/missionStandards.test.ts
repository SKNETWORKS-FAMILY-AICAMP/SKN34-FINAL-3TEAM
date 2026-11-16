import test from 'node:test'
import assert from 'node:assert/strict'
import type { AchievementStandard } from '../src/domain/admin/missionStandards.ts'
import {
  allowsLevel, bandFor, covers, defaultCode, draftRequestErrors, elementCodesFit, elementKind, isValidElementCode, kindsFor,
  levelOptions, nextUniqueCode,
} from '../src/domain/admin/missionStandards.ts'
import type { AdminMission } from '../src/domain/admin/operations.ts'
import { missingFieldLabel, missingMissionFields, rubricSaveErrors } from '../src/domain/admin/operations.ts'
import { missionWritePayload } from '../src/data/admin/api.ts'

const std = (code: string, gradeBand: AchievementStandard['gradeBand']): AchievementStandard => ({
  code, subject: '국어', gradeBand, area: '읽기', statement: '평가한다.', levelScale: gradeBand === '중1~3' ? 5 : 3,
  levels: null, curriculumVersion: '2022 개정', source: '고시', note: null,
})
const table = { '4국01-02': std('4국01-02', '초3~4'), '6국01-02': std('6국01-02', '초5~6'), '9국01-01': std('9국01-01', '중1~3') }

test('요소 code 모양·종류는 learning Standards.kt와 같다 (#262)', () => {
  for (const code of ['ANALYZE_RELATION', 'e1', 'e12', 'ANSWER_KEY', 'FINAL_ANSWER']) assert.ok(isValidElementCode(code), code)
  for (const code of ['', 'e0', 'e01', 'E1', 'STEPS', crypto.randomUUID(), 'analyze_relation']) assert.equal(isValidElementCode(code), false, code)
  assert.deepEqual(['EVALUATE_CLAIM', 'e3', 'ANSWER_KEY', 'x'].map(elementKind), ['COMMON', 'UNIQUE', 'ANSWER', null])
  assert.equal(nextUniqueCode(['e1', 'e7', 'ANALYZE_REASON']), 'e8')
  assert.equal(nextUniqueCode([]), 'e1')
  assert.deepEqual(kindsFor('CHOICE'), ['ANSWER'])
  assert.deepEqual(kindsFor('SOLUTION_STEPS'), ['COMMON', 'UNIQUE', 'ANSWER'])
  assert.equal(defaultCode('COMMON', 'ANALYZE', 'NARRATIVE', ['ANALYZE_RELATION']), 'ANALYZE_REASON')
  assert.equal(defaultCode('ANSWER', 'SOLVE', 'SOLUTION_STEPS', []), 'FINAL_ANSWER')
})

test('요소 code는 미션 유형·입력 방식에 맞아야 게시 (fits)', () => {
  assert.ok(elementCodesFit(['ANALYZE_RELATION', 'e1'], 'ANALYZE', 'NARRATIVE'))
  assert.equal(elementCodesFit(['EVALUATE_CLAIM'], 'ANALYZE', 'NARRATIVE'), false, '다른 유형 표준 코드')
  assert.ok(elementCodesFit(['ANSWER_KEY'], 'ANALYZE', 'CHOICE'))
  assert.equal(elementCodesFit(['ANSWER_KEY', 'e1'], 'ANALYZE', 'CHOICE'), false)
  assert.equal(elementCodesFit(['e1', 'ANSWER_KEY'], 'ANALYZE', 'NARRATIVE'), false)
  assert.equal(elementCodesFit(['EVALUATE_CLAIM', 'EVALUATE_EVIDENCE'], 'EVALUATE', 'ESSAY'), false, '논술은 세 논증 요소')
  assert.ok(elementCodesFit(['EVALUATE_CLAIM', 'EVALUATE_EVIDENCE', 'EVALUATE_PERSPECTIVE'], 'EVALUATE', 'ESSAY'))
})

test('학년군·성취수준 단계 (초 A~C, 중 A~E)', () => {
  assert.ok(covers(table['4국01-02'], 3, 4))
  assert.equal(covers(table['6국01-02'], 4, 6), false)
  assert.equal(covers(table['9국01-01'], 5, 6), false)
  assert.equal(bandFor(5, 6), '초5~6')
  assert.equal(bandFor(3, 6), '')
  assert.deepEqual(levelOptions(3), ['A', 'B', 'C'])
  assert.deepEqual(levelOptions(5), ['A', 'B', 'C', 'D', 'E'])
  assert.ok(allowsLevel(table['9국01-01'], 'E'))
  assert.equal(allowsLevel(table['6국01-02'], 'D'), false)
})

test('초안 요청 전 검사는 learning 400 규칙과 같다', () => {
  const ok = { standardCodes: ['6국01-02'], achievementLevels: { '6국01-02': 'B' }, thinkingType: 'EVALUATE' as const, gradeMin: 5, gradeMax: 6, inputType: 'ESSAY' as const }
  assert.deepEqual(draftRequestErrors(ok, table), [])
  assert.equal(draftRequestErrors({ ...ok, standardCodes: [] }, table).length, 1)
  assert.ok(draftRequestErrors({ ...ok, gradeMin: 3, gradeMax: 4 }, table).some((e) => e.includes('논술')))
  assert.ok(draftRequestErrors({ ...ok, inputType: 'NARRATIVE', gradeMin: 3, gradeMax: 4 }, table).some((e) => e.includes('학년군 밖')))
  assert.ok(draftRequestErrors({ ...ok, standardCodes: ['없는코드'] }, table).some((e) => e.includes('표에 없는')))
  assert.ok(draftRequestErrors({ ...ok, achievementLevels: { '6국01-02': 'D' } }, table).some((e) => e.includes('성취수준')))
})

const mission = (): AdminMission => ({
  missionId: 'm', status: 'REVIEW_REQUIRED', demoOnly: true, currentVersion: 1, currentRubricVersion: 1,
  publishedVersion: null, publishedRubricVersion: null,
  versions: [{
    version: 1, title: '제목', subject: '국어', gradeMin: 5, gradeMax: 6, thinkingType: 'EVALUATE', inputType: 'NARRATIVE',
    question: '질문', guide: '', sceneUri: '', staticSceneUri: '', achievementStandards: ['6국01-02'],
    achievementLevels: { '6국01-02': 'B' }, createdAt: '2026-11-09T00:00:00Z',
  }],
  rubrics: [{
    version: 1, exampleAnswer: '예시', forbiddenTerms: [], hints: [],
    elements: [{ code: 'EVALUATE_CLAIM', label: '주장', description: '', points: 1, commonErrors: [], goodThought: true, judgeVerified: false, standardCode: '6국01-02' }],
  }],
  reviews: [{ missionVersion: 1, rubricVersion: 1, result: 'APPROVED', comment: null, createdAt: '2026-11-09T00:00:00Z' }],
})

test('게시 전 확인: 성취기준 표·학년군·단계·요소 code·연결 성취기준 (#356)', () => {
  const m = mission(), v = m.versions[0], e = m.rubrics[0].elements[0]
  assert.deepEqual(missingMissionFields(m, table), [])
  v.achievementStandards = ['[6국01-02]']
  assert.deepEqual(missingMissionFields(m), ['achievementLevels', 'rubric.elements.standardCode'], '표 없이도 단계 키·연결 성취기준은 확인')
  assert.ok(missingMissionFields(m, table).includes('achievementStandards'), '대괄호 코드는 표에 없음')
  v.achievementStandards = ['6국01-02']; v.gradeMin = 3; v.gradeMax = 4
  assert.ok(missingMissionFields(m, table).includes('achievementStandards'), '학년군 밖')
  v.gradeMin = 5; v.gradeMax = 6; v.achievementLevels = { '6국01-02': 'E' }
  assert.deepEqual(missingMissionFields(m, table), ['achievementLevels'], '초등은 A~C')
  v.achievementLevels = null
  assert.deepEqual(missingMissionFields(m, table), [], '성취수준은 고르지 않아도 됨')
  e.code = 'ANALYZE_RELATION'
  assert.deepEqual(missingMissionFields(m, table), ['rubric.elements.code'])
  e.code = 'ANSWER_KEY'
  assert.ok(missingMissionFields(m, table).includes('rubric.elements.standardCode'), '정답 요소는 연결 성취기준을 비움')
  for (const code of ['achievementLevels', 'rubric.elements.code', 'rubric.elements.standardCode'])
    assert.ok(!missingFieldLabel(code).startsWith('확인이 필요한 항목'), code)
})

test('기준표 저장 전 code 모양·중복·연결 성취기준 공백을 막는다', () => {
  const e = mission().rubrics[0].elements[0]
  assert.deepEqual(rubricSaveErrors([e, { ...e, code: 'e1' }]), [])
  assert.equal(rubricSaveErrors([{ ...e, code: crypto.randomUUID() }]).length, 1)
  assert.ok(rubricSaveErrors([e, e]).some((m) => m.includes('같은 code')))
  assert.equal(rubricSaveErrors([{ ...e, standardCode: ' ' }]).length, 1)
})

test('미션 저장 본문은 성취수준을 함께 보낸다 (지워짐 방지)', () => {
  const { version: _v, createdAt: _c, ...v } = mission().versions[0]
  assert.deepEqual(missionWritePayload({ ...v, demoOnly: true }).achievementLevels, { '6국01-02': 'B' })
  assert.equal(missionWritePayload({ ...v, achievementLevels: undefined, demoOnly: true }).achievementLevels, null)
})
