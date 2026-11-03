import test from 'node:test'
import assert from 'node:assert/strict'
import { getResponse } from 'msw'
import { adminHandlers } from '../src/mocks/handlers/admin.ts'
import { studentHandlers } from '../src/mocks/handlers/student.ts'
import { setWorkspaceScenario } from '../src/mocks/fixtures/accounts.ts'
import { audits } from '../src/mocks/fixtures/admin/operations.ts'

const handlers = [...adminHandlers, ...studentHandlers]
let token = ''
async function call(path: string, body?: unknown, method = body === undefined ? 'GET' : 'POST', key?: string) {
  const response = await getResponse(handlers, new Request('http://localhost/api/v1' + path, {
    method, headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json', ...(key ? { 'Idempotency-Key': key } : {}) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  }), { baseUrl: 'http://localhost' })
  assert.ok(response, path)
  return { status: response.status, data: await response.json() }
}
async function login(email = 'ops@example.test') {
  setWorkspaceScenario('normal')
  const r = await call('/auth/login', { email, password: 'demo-only' })
  assert.equal(r.status, 200)
  token = r.data.accessToken
}
const scopes = ['judgment/grade-3/narrative']
function registration(name: string, version: string) {
  return { kind: 'PROMPT', name, version, evaluation: {
    datasetId: 'synthetic', datasetVersion: 'v1', baselineVersion: 'baseline', comparisonReport: '합성 비교',
    trainingEvaluationSeparation: '분리 확인', quoteAccuracy: '인용 대조', calculationAccuracy: '수치 대조',
    humanReview: '합성 검토', evaluatedScopes: scopes,
  } }
}

test('관리자 MSW는 일반 보호자·결제 전용 계정의 운영 API를 거부', async () => {
  for (const email of ['parent@example.test', 'payment@example.test']) {
    await login(email)
    const r = await call('/admin/model-versions')
    assert.equal(r.status, 403)
    assert.equal(r.data.code, 'FORBIDDEN')
  }
  await login()
  assert.equal((await call('/admin/model-versions')).status, 200)
})

test('모델 등록·승인·새 버전·복귀는 평가 범위와 감사 이력을 유지', async () => {
  await login()
  const name = 'test-' + crypto.randomUUID()
  const first = await call('/admin/model-versions', registration(name, 'v1'))
  assert.equal(first.status, 201)
  assert.equal(first.data.status, 'REGISTERED')
  const action = (id: string, kind: string, extra = {}) => call(`/admin/model-versions/${id}/${kind}`,
    { reason: '합성 검토 후 적용', scopes, reanalysisPlanned: false, ...(kind === 'activate' ? { approved: true } : {}), ...extra })
  assert.equal((await action(first.data.id, 'activate', { scopes: ['outside-scope'] })).status, 422)
  assert.equal((await action(first.data.id, 'activate', { approved: false })).status, 422)
  const active = await action(first.data.id, 'activate')
  assert.equal(active.data.status, 'ACTIVE')
  assert.ok(active.data.evalResult.approval.approvedBy)
  const second = await call('/admin/model-versions', registration(name, 'v2'))
  assert.equal((await action(second.data.id, 'activate')).status, 200)
  const reverted = await action(first.data.id, 'rollback')
  assert.equal(reverted.status, 200)
  assert.equal(reverted.data.status, 'ACTIVE')
  assert.equal(reverted.data.evalResult.revision, 3)
  const versions = (await call('/admin/model-versions')).data.items.filter((v: { name: string }) => v.name === name)
  assert.equal(versions.filter((v: { status: string }) => v.status === 'ACTIVE').length, 1)
  for (const event of ['MODEL_REGISTER', 'MODEL_ACTIVATE', 'MODEL_ROLLBACK'])
    assert.ok(audits.some(a => a.targetId === first.data.id && a.action === event))
  assert.equal((await call('/admin/model-versions', registration(name, 'v1'))).status, 409)
})

test('평가 근거 누락·중복 범위·부적절한 refId는 등록할 수 없다', async () => {
  await login()
  const good = registration('validation-' + crypto.randomUUID(), 'v1')
  for (const bad of [
    { ...good, evaluation: { ...good.evaluation, humanReview: '' } },
    { ...good, evaluation: { ...good.evaluation, evaluatedScopes: [...scopes, ...scopes] } },
    { ...good, refId: 'rubric-on-prompt' },
    { ...good, kind: 'RUBRIC' },
  ]) assert.equal((await call('/admin/model-versions', bad)).status, 422)
})

test('작업 재처리는 같은 멱등 키로 한 번만 실행하고 실행 이력을 남긴다', async () => {
  await login()
  const failed = (await call('/admin/jobs?status=FAILED')).data.items.find((j: { retryable: boolean }) => j.retryable)
  assert.ok(failed)
  const key = crypto.randomUUID()
  const first = await call(`/admin/jobs/${failed.jobId}/retry`, {}, 'POST', key)
  const second = await call(`/admin/jobs/${failed.jobId}/retry`, {}, 'POST', key)
  assert.equal(first.status, 200)
  assert.deepEqual(second.data, first.data)
  const job = (await call(`/admin/jobs/${failed.jobId}`)).data
  assert.equal(job.retryCount, 1)
  assert.equal(job.executions.length, 2)
  assert.equal(audits.filter(a => a.targetId === job.jobId && a.action === 'JOB_RETRY').length, 1)
})

test('목록 필터와 무관한 전체 미션 counts·조회 장애·권한 거부 구분', async () => {
  await login('admin@example.test')
  const all = await call('/admin/missions')
  const filtered = await call('/admin/missions?status=PUBLISHED&page=0&size=1')
  assert.deepEqual(filtered.data.counts, all.data.counts)
  assert.ok(filtered.data.items.length <= 1)
  assert.ok(filtered.data.items.every((m: { status: string }) => m.status === 'PUBLISHED'))
  setWorkspaceScenario('query-fail')
  assert.equal((await call('/admin/missions')).status, 503)
  setWorkspaceScenario('forbidden')
  assert.equal((await call('/admin/missions')).status, 403)
  setWorkspaceScenario('normal')
})

test('기준표 저장은 화면에서 편집하지 않는 keywords·essayType을 그대로 다시 보낸다 (#306)', async () => {
  const { rubricWritePayload } = await import('../src/data/admin/api.ts')
  await login('admin@example.test')
  const list = await call('/admin/missions')
  const withRubric = list.data.items.find((m: { rubrics: { keywords?: string[] }[] }) => m.rubrics.some((r) => r.keywords?.length))
  assert.ok(withRubric, '핵심어가 있는 시연 기준표')
  const mission = (await call('/admin/missions/' + withRubric.missionId)).data
  const { version: _version, ...current } = mission.rubrics.find((r: { version: number }) => r.version === mission.currentRubricVersion)
  const body = rubricWritePayload({ ...current, hints: [...current.hints, '새 생각 열기 질문'] })
  assert.deepEqual(body.keywords, current.keywords)
  assert.equal(body.essayType, current.essayType ?? null)
  const saved = (await call('/admin/missions/' + mission.missionId + '/rubric', body, 'PUT')).data
  const latest = saved.rubrics.find((r: { version: number }) => r.version === saved.currentRubricVersion)
  assert.equal(saved.currentRubricVersion, mission.currentRubricVersion + 1)
  assert.deepEqual(latest.keywords, current.keywords)
  assert.equal(latest.essayType, current.essayType ?? null)
  // 값이 없던 기준표도 learning 계약대로 [] · null을 명시해 보낸다.
  const empty = rubricWritePayload({ elements: [], answerKey: null, exampleAnswer: '', forbiddenTerms: [], hints: [] })
  assert.deepEqual([empty.keywords, empty.essayType], [[], null])
  assert.equal((await call('/admin/missions/' + mission.missionId + '/rubric', { ...body, essayType: '일기' }, 'PUT')).status, 400)
})
