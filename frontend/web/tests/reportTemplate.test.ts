import test from 'node:test'
import assert from 'node:assert/strict'
import { templateProposal, templateSnapshot, sectionLabels } from '../src/domain/reportTemplate.ts'
import { parentApi } from '../src/data/parent/api.ts'

const settings = { sectionOrder: Object.keys(sectionLabels), highlightMetrics: ['ATTEMPTS'], tone: 'EASY' }
test('표시 설정은 전체 순서와 허용 지표 및 톤만 받는다', () => {
  assert.equal(templateSnapshot({ settings, revision: 1 }).settings.tone, 'EASY')
  for (const change of [
    { sectionOrder: ['quotes'] }, { sectionOrder: Array(6).fill('quotes') },
    { highlightMetrics: ['SCORE'] }, { highlightMetrics: ['ATTEMPTS', 'ATTEMPTS'] },
    { tone: 'CUSTOM' }, { showOriginalText: true }, { memo: true },
  ]) assert.throws(() => templateSnapshot({ settings: { ...settings, ...change }, revision: 1 }))
  for (const revision of [-1, '1', true]) assert.throws(() => templateSnapshot({ settings, revision }))
})
test('확인 질문과 변경안 및 만료 시각 응답을 구분한다', () => {
  assert.deepEqual(templateProposal({ clarification: '어떤 지표인가요?' }), { clarification: '어떤 지표인가요?' })
  assert.throws(() => templateProposal({ clarification: ' ', settings: null }))
  assert.throws(() => templateProposal({ proposalId: 'id', settings, expiresAt: 'invalid' }))
  assert.throws(() => templateProposal({ proposalId: 'id', settings, expiresAt: new Date().toISOString(), clarification: '질문' }))
})
test('제안에는 질문만 확인에는 proposalId만 보내며 오류를 성공으로 바꾸지 않는다', async () => {
  const original = globalThis.fetch
  const calls: { url: string; body: unknown }[] = []
  globalThis.fetch = async (input, init) => {
    const url = String(input)
    calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null })
    return new Response(JSON.stringify(url.endsWith('/proposals')
      ? { proposalId: 'server-id', settings, expiresAt: new Date(Date.now() + 600000).toISOString() }
      : { settings, revision: 1 }), { headers: { 'Content-Type': 'application/json' } })
  }
  try {
    await parentApi.reportTemplate('conversation/id')
    await parentApi.proposeReportTemplate('conversation/id', '쉽게 설명해 주세요')
    await parentApi.confirmReportTemplate('conversation/id', 'server-id')
    assert.equal(calls[0].url, '/api/v1/conversations/conversation%2Fid/report-template')
    assert.deepEqual(calls[1].body, { question: '쉽게 설명해 주세요' })
    assert.deepEqual(calls[2].body, { proposalId: 'server-id' })
    globalThis.fetch = async () => new Response(JSON.stringify({ status: 409, title: '변경안 만료', code: 'TEMPLATE_PROPOSAL_EXPIRED' }), { status: 409 })
    await assert.rejects(parentApi.confirmReportTemplate('id', 'expired'))
  } finally { globalThis.fetch = original }
})
