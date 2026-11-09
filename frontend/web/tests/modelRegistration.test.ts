import test from 'node:test'
import assert from 'node:assert/strict'
import { registrationRequest, parseRegistrationFile, parseManifestFile, validateRegistration, withManifestLimitations, actionBlockers, EVIDENCE_LABELS } from '../src/domain/admin/modelRegistration.ts'
import type { ModelRegistration } from '../src/domain/admin/modelRegistration.ts'
import type { ModelVersion } from '../src/domain/admin/operations.ts'
import { adminApi } from '../src/data/admin/api.ts'
const request = (): ModelRegistration => ({ kind: 'MODEL', name: 'm2-klue-essay', version: '3.1', artifactUri: 's3://<버킷>/models/m2-klue-essay/3.1/', evaluation: {
  datasetId: '합성 평가셋', datasetVersion: '1', baselineVersion: '2.0', comparisonReport: '합성 비교', trainingEvaluationSeparation: '분리', quoteAccuracy: '해당 없음', calculationAccuracy: '해당 없음', humanReview: '검토', evaluatedScopes: ['judgment/grade-5/essay'],
} })
const manifest = () => ({ models: [{ name: 'm2-klue-essay', version: '3.1', scope: ['judgment/grade-5/essay'], 주의: '임시 경계', files: [{ file: 'model.safetensors', bytes: 442539656, sha256: 'a'.repeat(64) }] }] })
const parse = (r = request()) => parseRegistrationFile(JSON.stringify({ 주의: '평가 기록', requests: [r] }))
test('registration과 manifest는 기존 11/03 구조로 읽고 주의 후보를 모은다', () => {
  const file = parse(), models = parseManifestFile(JSON.stringify(manifest()))
  const [row] = withManifestLimitations(file, models)
  assert.deepEqual(row.evaluation.limitations, ['평가 기록', '임시 경계'])
  assert.ok(validateRegistration(row, [], models).errors.some(e => e.path === 'artifactUri'))
  row.artifactUri = row.artifactUri!.replace('<버킷>', 'local-models')
  assert.deepEqual(validateRegistration(row, [], models), { errors: [], warnings: [] })
  assert.equal(models[0].files[0].sha256, 'a'.repeat(64))
})
test('명시한 limitations는 빈 목록도 주의 후보보다 우선한다', () => {
  const r = request(); r.evaluation.limitations = []
  assert.deepEqual(withManifestLimitations(parse(r), parseManifestFile(JSON.stringify(manifest())))[0].evaluation.limitations, [])
})
test('등록 JSON에 승인 정보·알 수 없는 평가 필드·잘못된 타입이 있으면 거부한다', () => {
  assert.throws(() => parseRegistrationFile('{'))
  for (const key of ['approved', 'scopes', 'reason', 'reanalysisPlanned', 'approvedBy', 'unknown'])
    assert.throws(() => parseRegistrationFile(JSON.stringify({ requests: [{ ...request(), [key]: true }] })), /등록 API에 없는 필드/)
  for (const key of ['approved', 'approval', 'scopes', 'activeScopes', 'reason', 'reanalysisPlanned', 'approvedBy', 'status'])
    assert.throws(() => parseRegistrationFile(JSON.stringify({ [key]: true, requests: [request()] })), /승인·활성화 정보/)
  assert.throws(() => parseRegistrationFile(JSON.stringify({ requests: [{ ...request(), evaluation: { ...request().evaluation, activeScopes: [] } }] })), /알 수 없는 평가/)
  assert.throws(() => parseRegistrationFile(JSON.stringify({ requests: [{ ...request(), evaluation: { ...request().evaluation, limitations: [null] } }] })), /문자열 목록/)
})
test('필수 근거 8칸·범위·중복·manifest 불일치는 차단한다', () => {
  const r = request(); r.artifactUri = 's3://local/models/m2-klue-essay/3.1/'
  for (const key of Object.keys(EVIDENCE_LABELS) as (keyof typeof EVIDENCE_LABELS)[]) {
    const invalid = structuredClone(r); invalid.evaluation[key] = '  '
    assert.ok(validateRegistration(invalid, []).errors.some(e => e.path === `evaluation.${key}`))
  }
  for (const scopes of [[], ['bad scope'], ['ai/judgment', 'ai/judgment']]) {
    const invalid = structuredClone(r); invalid.evaluation.evaluatedScopes = scopes
    assert.ok(validateRegistration(invalid, []).errors.some(e => e.path === 'evaluation.evaluatedScopes'))
  }
  assert.ok(validateRegistration(r, [{ ...r } as unknown as ModelVersion]).errors.some(e => e.path === 'name'))
  assert.ok(validateRegistration(r, [], undefined, [r, structuredClone(r)]).errors.length)
  const models = parseManifestFile(JSON.stringify(manifest())); models[0].scope = ['judgment/grade-6/essay']
  assert.ok(validateRegistration(r, [], models).errors.some(e => e.path === 'manifest'))
  assert.throws(() => parseManifestFile(JSON.stringify({ models: [{ ...manifest().models[0], files: [{ file: 'x', bytes: 1, sha256: 'bad' }] }] })))
})
test('미등록 범위·모델 이름·경로·버전 관례는 경고만 낸다', () => {
  const r = request(); r.name = 'm1-new'; r.version = 'v3'; r.artifactUri = 's3://local/custom/'; r.evaluation.evaluatedScopes = ['future/scope']
  const result = validateRegistration(r, [])
  assert.equal(result.errors.length, 0); assert.equal(result.warnings.length, 4)
})
test('활성화와 복귀는 해당 카드의 평가·원 승인 범위와 조건 여섯 가지를 검사한다', () => {
  const r = request()
  const v: ModelVersion = { ...r, id: 'a', status: 'REGISTERED', createdAt: '', evalResult: { evidence: r.evaluation, approval: null, activeScopes: [], revision: 0 } }
  assert.deepEqual(actionBlockers(v, 'activate', ['judgment/grade-5/essay'], '검토', true, false), [])
  assert.equal(actionBlockers({ ...v, status: 'ACTIVE', evalResult: null }, 'activate', [], '', false, true).length, 6)
  v.status = 'INACTIVE'; v.evalResult!.approval = { scopes: ['judgment/grade-5/essay'], reason: '이전 승인', approvedBy: 'a', approvedAt: '' }
  assert.ok(actionBlockers(v, 'rollback', ['judgment/grade-6/essay'], '복귀', false, false).length)
  assert.deepEqual(actionBlockers(v, 'rollback', ['judgment/grade-5/essay'], '복귀', false, false), [])
})
test('중복 검사는 첫 페이지를 넘어 전체 모델 목록을 대조한다', async () => {
  const original = globalThis.fetch, urls: string[] = []
  globalThis.fetch = async input => {
    const url = String(input); urls.push(url)
    const page = Number(new URL(url, 'http://local').searchParams.get('page'))
    return Response.json({ items: [{ id: String(page) }], page, size: 1, totalElements: 2 })
  }
  try { assert.equal((await adminApi.allModels()).items.length, 2); assert.ok(urls[1].includes('page=1')) } finally { globalThis.fetch = original }
})


test('가져오기 감사 정보는 원본 대비 변경과 모델별 파일만 전달하고 수동 등록은 생략한다', () => {
  const original = request()
  const current = structuredClone(original)
  current.artifactUri = current.artifactUri!.replace('<버킷>', 'local')
  current.evaluation.limitations = ['검토 필요']
  const result = registrationRequest(current, original, 'a'.repeat(64), 'b'.repeat(64), parseManifestFile(JSON.stringify(manifest())))
  assert.deepEqual(result.registration?.modifiedFields, ['artifactUri', 'evaluation.limitations'])
  assert.equal(result.registration?.source, 'JSON_IMPORT')
  assert.equal(result.registration?.artifactFiles.length, 1)
  assert.equal(registrationRequest(current).registration, undefined)
  assert.equal(original.evaluation.limitations, undefined)
  assert.ok(validateRegistration({ ...current, evaluation: { ...current.evaluation, limitations: [' '] } }, []).errors.some(e => e.path === 'evaluation.limitations'))
})
