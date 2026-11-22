// #728 모델 등록부 추천 태그 값: evalResult.evidence.recommendation(api-spec 5.2.3) → "추천"/"비추천"·비교 대상·이유·지표.
// 화면 표시(태그·펼쳐 보기·태그 없는 버전)는 tests/model-browser/models.spec.ts
import test from 'node:test'
import assert from 'node:assert/strict'
import { recommendationView } from '../src/domain/admin/modelRegistration.ts'
import type { EvaluationEvidence } from '../src/domain/admin/operations.ts'
import { modelVersions } from '../src/mocks/fixtures/admin/operations.ts'

const base: EvaluationEvidence = {
  datasetId: '합성 평가셋', datasetVersion: 'v1', baselineVersion: 'tox-kcelectra:1.0', comparisonReport: '합성 비교',
  trainingEvaluationSeparation: '분리', quoteAccuracy: '해당 없음', calculationAccuracy: '해당 없음', humanReview: '합성 검토',
  evaluatedScopes: ['answer-filter'],
}
test('태그 없는 기존 버전은 표시 값이 없다', () => {
  assert.equal(recommendationView(base), null)
  assert.equal(recommendationView(null), null)
  assert.equal(recommendationView(undefined), null)
})

test('RECOMMENDED는 "추천", NOT_RECOMMENDED는 "비추천", NONE은 처음 등록으로 풀어 쓴다', () => {
  const view = recommendationView({ ...base, recommendation: { tag: 'RECOMMENDED', comparedTo: 'tox-kcelectra:1.0-1119',
    reasons: ['놓친 글이 줄었다', '정상 글 오차단 같음'], metrics: { recall: 0.96, precision: 0.99 } } })
  assert.deepEqual(view, { tag: 'RECOMMENDED', label: '추천', comparedTo: 'tox-kcelectra:1.0-1119',
    reasons: ['놓친 글이 줄었다', '정상 글 오차단 같음'], metrics: [['precision', 0.99], ['recall', 0.96]] }) // 지표는 이름순
  const first = recommendationView({ ...base, recommendation: { tag: 'NOT_RECOMMENDED', comparedTo: 'NONE', reasons: ['비교 대상 없음'] } })
  assert.equal(first?.label, '비추천')
  assert.equal(first?.comparedTo, '처음 등록 (비교한 활성 버전 없음)')
  assert.deepEqual(first?.metrics, [])
})

test('형식이 틀린 태그는 표시하지 않고, 이상한 지표 값은 뺀다', () => {
  const odd = (recommendation: unknown) => recommendationView({ ...base, recommendation } as EvaluationEvidence)
  assert.equal(odd({ tag: 'MAYBE', comparedTo: 'x', reasons: [] }), null)
  assert.equal(odd({ tag: 'RECOMMENDED', reasons: [] }), null)
  assert.equal(odd({ tag: 'RECOMMENDED', comparedTo: 'x', reasons: 'text' }), null)
  assert.deepEqual(odd({ tag: 'RECOMMENDED', comparedTo: 'x', reasons: ['a'], metrics: { ok: 1, bad: 'x', inf: Infinity } })?.metrics, [['ok', 1]])
})

test('목 데이터: 재학습 자동 등록 버전에 추천 태그가 있고 기존 시연 버전에는 없다', () => {
  const tox = modelVersions.find(v => v.name === 'tox-kcelectra')
  assert.equal(tox?.status, 'REGISTERED')
  assert.equal(recommendationView(tox?.evalResult?.evidence)?.label, '추천')
  assert.equal(modelVersions.filter(v => v.name === 'judge').every(v => recommendationView(v.evalResult?.evidence) === null), true)
})
