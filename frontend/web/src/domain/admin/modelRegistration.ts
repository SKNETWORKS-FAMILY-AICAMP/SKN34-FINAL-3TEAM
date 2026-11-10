import type { EvaluationEvidence, ModelVersion } from './operations.ts'

export const EVIDENCE_LABELS = {
  datasetId: '평가셋 ID', datasetVersion: '평가셋 버전', baselineVersion: '비교 기준 버전', comparisonReport: '비교 보고서',
  trainingEvaluationSeparation: '학습·평가 분리 근거', quoteAccuracy: '인용 정확성 근거',
  calculationAccuracy: '계산 정확성 근거', humanReview: '사람 검토 기록',
} as const
export const KNOWN_MODEL_SCOPES = [
  ...[4, 5, 6].flatMap(grade => ['narrative', 'essay'].map(type => `judgment/grade-${grade}/${type}`)),
  ...['judgment', 'followup', 'analysis', 'report-narrative', 'report-template', 'mission-draft'].map(name => `ai/${name}`),
]
export const splitScopes = (value: string) => value.split(/[\n,]/).map(s => s.trim()).filter(Boolean)
export const validModelScopes = (values: string[]) => values.length > 0 && values.length <= 100 &&
  new Set(values).size === values.length && values.every(s => /^[a-z0-9][a-z0-9._:/-]{0,199}$/.test(s))
export interface ModelRegistration {
  kind: ModelVersion['kind']; name: string; version: string; artifactUri?: string; refId?: string
  evaluation: EvaluationEvidence
}
export interface RegistrationProvenance {
  source: 'JSON_IMPORT'; jsonSha256: string; manifestSha256?: string
  modifiedFields: string[]; artifactFiles: ManifestModel['files']
}
export type RegistrationRequest = ModelRegistration & { registration?: RegistrationProvenance }
const registrationPaths = (v: ModelRegistration): Record<string, unknown> => ({
  kind: v.kind, name: v.name, version: v.version, refId: v.refId, artifactUri: v.artifactUri,
  ...Object.fromEntries(Object.entries(v.evaluation).map(([key, value]) => [`evaluation.${key}`, value])),
})
export function changedRegistrationFields(value: ModelRegistration, original: ModelRegistration) {
  const a = registrationPaths(value), b = registrationPaths(original)
  return [...new Set([...Object.keys(a), ...Object.keys(b)])].filter(key => JSON.stringify(a[key]) !== JSON.stringify(b[key]))
}
export function registrationRequest(value: ModelRegistration, original?: ModelRegistration,
  jsonSha256?: string, manifestSha256?: string, manifest?: ManifestModel[]): RegistrationRequest {
  const result: RegistrationRequest = structuredClone(value)
  if (original && jsonSha256) result.registration = {
    source: 'JSON_IMPORT', jsonSha256, ...(manifestSha256 ? { manifestSha256 } : {}),
    modifiedFields: changedRegistrationFields(value, original),
    artifactFiles: manifest?.find(m => m.name === value.name && m.version === value.version)?.files.map(f => ({ ...f, sha256: f.sha256.toLowerCase() })) ?? [],
  }
  return result
}
export interface FieldIssue { path: string; message: string }
export interface ManifestModel {
  name: string; version: string; scope: string[]; limitations: string[]
  files: { file: string; bytes: number; sha256: string }[]
}
export interface RegistrationFile { requests: ModelRegistration[]; metadata: Record<string, unknown>; explicitLimitations: boolean[] }
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
const fail = (path: string, message: string): never => { throw new Error(`${path}: ${message}`) }
const notice = (value: unknown): string[] => typeof value === 'string' ? [value].filter(s => s.trim())
  : Array.isArray(value) && value.every(v => typeof v === 'string') ? value.filter(s => s.trim()) : []
const allowedRequest = ['kind', 'name', 'version', 'refId', 'artifactUri', 'evaluation']
const allowedEvidence = [...Object.keys(EVIDENCE_LABELS), 'evaluatedScopes', 'limitations']
export function parseRegistrationFile(text: string): RegistrationFile {
  const raw: unknown = JSON.parse(text)
  if (!object(raw) || !Array.isArray(raw.requests) || !raw.requests.length || raw.requests.length > 100)
    return fail('requests', '1~100개 모델 등록 목록이 필요합니다.')
  for (const key of ['approved', 'approval', 'scopes', 'activeScopes', 'reason', 'reanalysisPlanned', 'approvedBy', 'activatedAt', 'status'])
    if (Object.hasOwn(raw, key)) fail(key, '등록 파일에 승인·활성화 정보는 넣을 수 없습니다.')
  const requests = raw.requests.map((entry: unknown, index: number) => {
    const path = `requests[${index}]`
    if (!object(entry)) return fail(path, 'JSON 객체여야 합니다.')
    for (const key of Object.keys(entry)) if (!allowedRequest.includes(key)) fail(`${path}.${key}`, '등록 API에 없는 필드입니다. 승인·활성화 정보는 가져올 수 없습니다.')
    if (!object(entry.evaluation)) return fail(`${path}.evaluation`, '평가 근거 객체가 필요합니다.')
    for (const key of Object.keys(entry.evaluation)) if (!allowedEvidence.includes(key)) fail(`${path}.evaluation.${key}`, '알 수 없는 평가 필드입니다.')
    for (const key of ['name', 'version', 'kind']) if (typeof entry[key] !== 'string') fail(`${path}.${key}`, '문자열이어야 합니다.')
    for (const key of Object.keys(EVIDENCE_LABELS)) if (typeof entry.evaluation[key] !== 'string') fail(`${path}.evaluation.${key}`, '문자열이어야 합니다.')
    if (!Array.isArray(entry.evaluation.evaluatedScopes) || entry.evaluation.evaluatedScopes.some(v => typeof v !== 'string'))
      return fail(`${path}.evaluation.evaluatedScopes`, '문자열 목록이어야 합니다.')
    if (entry.evaluation.limitations !== undefined && (!Array.isArray(entry.evaluation.limitations) || entry.evaluation.limitations.some(v => typeof v !== 'string')))
      return fail(`${path}.evaluation.limitations`, '문자열 목록이어야 합니다.')
    for (const key of ['artifactUri', 'refId']) if (entry[key] !== undefined && typeof entry[key] !== 'string') fail(`${path}.${key}`, '문자열이어야 합니다.')
    const cloned = structuredClone(entry) as unknown as ModelRegistration
    if (entry.evaluation.limitations === undefined) cloned.evaluation.limitations = notice(raw['주의'])
    return cloned
  })
  return { requests, metadata: Object.fromEntries(Object.entries(raw).filter(([key]) => key !== 'requests')),
    explicitLimitations: raw.requests.map(entry => object(entry) && object(entry.evaluation) && entry.evaluation.limitations !== undefined) }
}
export function parseManifestFile(text: string): ManifestModel[] {
  const raw: unknown = JSON.parse(text)
  if (!object(raw) || !Array.isArray(raw.models) || !raw.models.length) return fail('manifest.models', '모델별 목록이 필요합니다.')
  return raw.models.map((entry: unknown, index: number) => {
    const path = `manifest.models[${index}]`
    if (!object(entry) || typeof entry.name !== 'string' || typeof entry.version !== 'string' ||
        !Array.isArray(entry.scope) || entry.scope.some(v => typeof v !== 'string') || !Array.isArray(entry.files))
      return fail(path, 'name·version·scope·files를 확인해 주세요.')
    const files = entry.files.map((file: unknown, i: number) => {
      if (!object(file) || typeof file.file !== 'string' || !Number.isSafeInteger(file.bytes) || Number(file.bytes) < 0 ||
          typeof file.sha256 !== 'string' || !/^[a-f0-9]{64}$/i.test(file.sha256)) return fail(`${path}.files[${i}]`, '파일 이름·크기·SHA-256을 확인해 주세요.')
      return { file: file.file, bytes: Number(file.bytes), sha256: file.sha256.toLowerCase() }
    })
    if (files.length > 100 || files.some(f => !f.file.trim() || f.file.length > 255 || /[\\:]/.test(f.file) || f.file.split('/').some(s => !s || s === '.' || s === '..'))) return fail(`${path}.files`, '유효한 상대 파일 경로를 최대 100개까지 입력해 주세요.')
    if (!files.length || new Set(files.map(f => f.file)).size !== files.length) return fail(`${path}.files`, '파일 목록이 비었거나 중복됐습니다.')
    return { name: entry.name, version: entry.version, scope: entry.scope as string[], limitations: notice(entry['주의']), files }
  })
}
export function validateRegistration(value: ModelRegistration, existing: ModelVersion[], manifest?: ManifestModel[], siblings: ModelRegistration[] = []): { errors: FieldIssue[]; warnings: FieldIssue[] } {
  const errors: FieldIssue[] = [], warnings: FieldIssue[] = []
  const error = (path: string, message: string) => errors.push({ path, message })
  if (!['RUBRIC', 'MODEL', 'PROMPT', 'GENERATION'].includes(value.kind)) error('kind', '지원하는 종류를 선택해 주세요.')
  for (const key of ['name', 'version'] as const) if (!value[key].trim() || value[key].length > 100) error(key, '1~100자로 입력해 주세요.')
  for (const [key, label] of Object.entries(EVIDENCE_LABELS)) if (!value.evaluation[key as keyof typeof EVIDENCE_LABELS]?.trim()) error(`evaluation.${key}`, `${label}가 없습니다.`)
  if (!validModelScopes(value.evaluation.evaluatedScopes)) error('evaluation.evaluatedScopes', '범위는 1~100개, 중복 없이 올바른 키 형식으로 입력해 주세요.')
  if (value.kind === 'MODEL' && !value.artifactUri?.trim()) error('artifactUri', 'MODEL은 아티팩트 주소가 필요합니다.')
  if (value.artifactUri !== undefined && !value.artifactUri.trim()) error('artifactUri', '선택 주소는 비워 두거나 공백 없는 값을 입력해 주세요.')
  if ((value.kind === 'RUBRIC') !== Boolean(value.refId)) error('refId', 'RUBRIC만 기준표 원본 UUID를 필수로 사용합니다.')
  if (value.refId && !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(value.refId)) error('refId', 'UUID 형식이 아닙니다.')
  if (value.artifactUri && (/[<>]|\$\{|\{\{/.test(value.artifactUri) || value.artifactUri.length > 2048)) error('artifactUri', '자리표시자를 바꾸고 2048자 이내로 입력해 주세요.')
  if ([...existing, ...siblings].some(v => v !== value && v.kind === value.kind && v.name === value.name && v.version === value.version)) {
    error('name', '같은 종류·이름·버전이 이미 있습니다.'); error('version', '새 버전으로 등록해 주세요.')
  }
  if ((value.evaluation.limitations ?? []).length > 100 || (value.evaluation.limitations ?? []).some(s => !s.trim() || s.length > 4000)) error('evaluation.limitations', '주의사항은 빈 줄 없이 항목당 4000자, 최대 100개로 입력해 주세요.')
  const matched = manifest?.filter(m => m.name === value.name && m.version === value.version)
  if (manifest && (!matched || matched.length !== 1 || [...matched[0].scope].sort().join('\n') !== [...value.evaluation.evaluatedScopes].sort().join('\n')))
    error('manifest', 'manifest의 이름·버전·scope와 일치하지 않습니다.')
  for (const scope of value.evaluation.evaluatedScopes) if (!KNOWN_MODEL_SCOPES.includes(scope)) warnings.push({ path: 'evaluation.evaluatedScopes', message: `알려진 목록 밖 범위입니다: ${scope}` })
  if (/^m[12]-/.test(value.name) && !['m2-klue-narrative', 'm2-klue-essay'].includes(value.name)) warnings.push({ path: 'name', message: 'scoring의 알려진 모델 이름이 아닙니다. 소비자 구현을 확인해 주세요.' })
  if (!/^\d+\.\d+$/.test(value.version)) warnings.push({ path: 'version', message: '버전이 X.Y 형식이 아닙니다.' })
  if (value.artifactUri && !value.artifactUri.endsWith(`/models/${value.name}/${value.version}/`)) warnings.push({ path: 'artifactUri', message: '권장 models/{name}/{version}/ 경로와 다릅니다.' })
  return { errors, warnings }
}
export function withManifestLimitations(file: RegistrationFile, manifest: ManifestModel[]): ModelRegistration[] {
  return file.requests.map((request, i) => ({ ...request, evaluation: { ...request.evaluation,
    limitations: file.explicitLimitations[i] ? request.evaluation.limitations : [...new Set([
      ...(request.evaluation.limitations ?? []), ...manifest.filter(m => m.name === request.name && m.version === request.version).flatMap(m => m.limitations),
    ])],
  } }))
}
export function actionBlockers(v: ModelVersion, action: 'activate' | 'rollback', scopes: string[], reason: string, approved: boolean, pending: boolean): string[] {
  const result: string[] = [], record = v.evalResult
  if (!record || Object.keys(EVIDENCE_LABELS).some(k => !record.evidence[k as keyof typeof EVIDENCE_LABELS]?.trim())) result.push('평가 근거가 없습니다.')
  const allowed = action === 'activate' ? record?.evidence.evaluatedScopes : record?.approval?.scopes
  if (!validModelScopes(scopes) || scopes.some(s => !allowed?.includes(s))) result.push('해당 버전의 허용 범위에서 적용 범위를 선택해 주세요.')
  if (!reason.trim()) result.push('변경 사유가 없습니다.')
  if (pending) result.push('이 버전의 요청을 처리 중입니다.')
  if (action === 'activate' ? v.status !== 'REGISTERED' || !!v.approvedBy : v.status !== 'INACTIVE' || !record?.approval)
    result.push(action === 'activate' ? '최초 등록 상태에서만 활성화할 수 있습니다. 이전 승인 버전은 되돌리기를 사용하세요.' : '이전 승인 이력이 있는 비활성 버전만 되돌릴 수 있습니다.')
  if (action === 'activate' && !approved) result.push('평가 근거와 선택 범위를 확인한 사람의 승인 체크가 필요합니다.')
  return result
}

export interface PreflightRequest { name: string; version: string; artifactUri: string; files: ManifestModel['files'] }
export interface PreflightResult { status: 'PASS' | 'FAIL'; code: string; files: { file: string; status: 'PASS' | 'FAIL'; code: string }[] }
export const preflightMessage = (code: string) => ({
  FILES_AND_METADATA_VERIFIED: '파일·형식 확인 완료', FILE_CHECK_FAILED: '파일 검사 실패',
  INVALID_ARTIFACT_URI: '허용된 모델 버킷·경로가 아닙니다', UNSUPPORTED_MODEL: '사전 검사를 지원하지 않는 모델입니다',
  PREFLIGHT_TIMEOUT: '검사 시간이 초과되었습니다', OUTPUT_MISMATCH: '모델 출력 수·회귀 설정 불일치',
  INVALID_METADATA: '학습 설정·점수 경계 형식 불일치', OK: '확인', SIZE_MISMATCH: '파일 크기 불일치',
  HASH_MISMATCH: 'SHA-256 불일치', CHECKSUM_UNAVAILABLE: '전체 파일 SHA-256을 조회할 수 없음',
  JSON_TOO_LARGE: '메타데이터 JSON 크기 초과', FILE_MISSING: '파일 없음', ACCESS_DENIED: '읽기 권한 없음',
  OBJECT_CHANGED: '검사 중 파일이 변경됨', STORAGE_UNAVAILABLE: '저장소 응답 확인 불가',
}[code] ?? '검사 결과를 확인해 주세요')

export const PREFLIGHT_FILES = ['config.json', 'tokenizer.json', 'tokenizer_config.json', 'train_info.json', 'score_cuts.json', 'model.safetensors']
export const supportsPreflight = (files: ManifestModel['files']) => files.length === 6 && new Set(files.map(f => f.file)).size === 6 && files.every(f => PREFLIGHT_FILES.includes(f.file))

export type ModelLoadingState = { name: string; version: string; revision: number; status: 'LOADING' | 'LOADED' | 'FAILED'; errorType: string | null; loadedVersion: string | null; loadedRevision: number | null; previousModelRetained: boolean }
export type LoadingReport = { observedAt: string; staleAfterSeconds: number; populationSource: 'RECENT_REPORTS'; pods: { podId: string; instanceId: string; reportedAt: string; stale: boolean; models: ModelLoadingState[] }[]; summaries: { name: string; version: string; revision: number; observedPods: number; loadedPods: number; failedPods: string[] }[] }
