// #93 관리자 모델 레지스트리: adminApi가 보내는 요청 본문이 core 계약(api-spec 5.2, core-service.yaml)과 같은지
import test from 'node:test'
import assert from 'node:assert/strict'
import { adminApi } from '../src/data/admin/api.ts'
import { setAccessToken } from '../src/data/apiClient.ts'
import type { EvaluationEvidence } from '../src/domain/admin/operations.ts'

const evaluation: EvaluationEvidence = {
  datasetId: '합성 평가셋',
  datasetVersion: 'v1',
  baselineVersion: 'judge@mock-1',
  comparisonReport: '합성 비교 기록',
  trainingEvaluationSeparation: '합성 분리 근거',
  quoteAccuracy: '합성 인용 기록',
  calculationAccuracy: '합성 계산 기록',
  humanReview: '합성 검토 기록',
  evaluatedScopes: ['judgment/grade-3/narrative'],
}

function capture(t: test.TestContext) {
  const sent: { url: string; method: string; body: unknown }[] = []
  setAccessToken('memory-test-token')
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    sent.push({ url: String(url), method: String(init.method), body: JSON.parse(String(init.body)) })
    return new Response('{}', { headers: { 'Content-Type': 'application/json' } })
  })
  return sent
}

test('등록 본문: kind·name·version·evaluation, refId는 RUBRIC만 (승인자는 보내지 않음)', async (t) => {
  const sent = capture(t)
  await adminApi.registerModel({ kind: 'PROMPT', name: 'judge', version: 'v9', evaluation })
  await adminApi.registerModel({
    kind: 'RUBRIC',
    name: 'mission-rubric',
    version: 'v2',
    refId: '6f1c2f8e-1f0a-4b5e-9c3d-2a7b8c9d0e1f',
    artifactUri: 's3://models/rubric-v2.json',
    evaluation,
  })
  assert.match(sent[0].url, /\/admin\/model-versions$/)
  assert.equal(sent[0].method, 'POST')
  assert.deepEqual(sent[0].body, { kind: 'PROMPT', name: 'judge', version: 'v9', evaluation })
  assert.deepEqual(Object.keys(sent[1].body as object).sort(), ['artifactUri', 'evaluation', 'kind', 'name', 'refId', 'version'])
  for (const s of sent) {
    assert.equal('evalResult' in (s.body as object), false) // 예전 문자열 계약
    assert.equal('approvedBy' in (s.body as object), false) // 승인자는 서버가 인증 계정으로 기록
  }
  setAccessToken(null)
})

test('활성화는 approved:true를 포함하고, 복귀에는 approved가 없다 (reanalyze 대신 reanalysisPlanned)', async (t) => {
  const sent = capture(t)
  const scopes = ['judgment/grade-3/narrative']
  await adminApi.modelAction('v-1', 'activate', '비교 후 승인', scopes, false)
  await adminApi.modelAction('v-1', 'rollback', '이전 버전으로', scopes, true)
  assert.match(sent[0].url, /\/admin\/model-versions\/v-1\/activate$/)
  assert.deepEqual(sent[0].body, { reason: '비교 후 승인', scopes, reanalysisPlanned: false, approved: true })
  assert.match(sent[1].url, /\/admin\/model-versions\/v-1\/rollback$/)
  assert.deepEqual(sent[1].body, { reason: '이전 버전으로', scopes, reanalysisPlanned: true })
  setAccessToken(null)
})

test('AI 사용량 조회는 기간과 호출 종류를 쿼리로 보낸다', async (t) => {
  const urls: string[] = []
  setAccessToken('memory-test-token')
  t.mock.method(globalThis, 'fetch', async (url: string) => {
    urls.push(String(url))
    return new Response(JSON.stringify({ period: { from: '2026-10-20', to: '2026-10-26' }, items: [] }), {
      headers: { 'Content-Type': 'application/json' },
    })
  })
  await adminApi.usage({ from: '2026-10-20', to: '2026-10-26' }, 'M1')
  const q = new URL(urls[0], 'http://localhost').searchParams
  assert.deepEqual([q.get('from'), q.get('to'), q.get('callType')], ['2026-10-20', '2026-10-26', 'M1'])
  setAccessToken(null)
})
