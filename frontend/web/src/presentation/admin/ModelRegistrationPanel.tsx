import { useId, useRef, useState } from 'react'
import { adminApi } from '../../data/admin/api.ts'
import { ApiError } from '../../data/apiClient.ts'
import { useAdminMutation } from '../../data/admin/queries.ts'
import type { ModelVersion } from '../../domain/admin/operations.ts'
import { EVIDENCE_LABELS, parseManifestFile, parseRegistrationFile, splitScopes, validateRegistration, withManifestLimitations } from '../../domain/admin/modelRegistration.ts'
import type { ManifestModel, ModelRegistration, RegistrationFile } from '../../domain/admin/modelRegistration.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'

const blank = (): ModelRegistration => ({ kind: 'PROMPT', name: '', version: '', evaluation: {
  datasetId: '', datasetVersion: '', baselineVersion: '', comparisonReport: '', trainingEvaluationSeparation: '',
  quoteAccuracy: '', calculationAccuracy: '', humanReview: '', evaluatedScopes: [], limitations: [],
} })
const paths = (v: ModelRegistration): Record<string, unknown> => ({ kind: v.kind, name: v.name, version: v.version,
  artifactUri: v.artifactUri, refId: v.refId, ...Object.fromEntries(Object.entries(v.evaluation).map(([key, value]) => [`evaluation.${key}`, value])) })

function RegistrationForm({ value, onChange, existing, listReady, manifest, siblings, original, title, onBusy }: {
  value: ModelRegistration; onChange: (value: ModelRegistration) => void; existing: ModelVersion[]; listReady: boolean
  manifest?: ManifestModel[]; siblings?: ModelRegistration[]; original?: ModelRegistration; title: string; onBusy?: (busy: boolean) => void
}) {
  const id = useId(), [saved, setSaved] = useState(false)
  const [scopeText, setScopeText] = useState(value.evaluation.evaluatedScopes.join('\n'))
  const mutation = useAdminMutation((snapshot: ModelRegistration) => adminApi.registerModel(snapshot))
  const validation = validateRegistration(value, existing, manifest, siblings)
  const conflict = mutation.error instanceof ApiError && mutation.error.problem.code === 'MODEL_VERSION_CONFLICT'
  const changed = original ? Object.keys(paths(value)).filter(key => JSON.stringify(paths(value)[key]) !== JSON.stringify(paths(original)[key])) : []
  const field = (path: string) => <>{changed.includes(path) && <small>수정됨</small>}
    {validation.errors.filter(e => e.path === path).map(e => <small className="model-error" key={e.message}>{e.message}</small>)}
    {conflict && ['name', 'version'].includes(path) && <small className="model-error">{mutation.error?.message}</small>}</>
  const locked = saved || mutation.isPending
  const evidence = (key: keyof ModelRegistration['evaluation'], data: string | string[]) => onChange({ ...value, evaluation: { ...value.evaluation, [key]: data } })
  return <form className="ws-card ws-form model-registration" aria-label={title} onSubmit={e => {
    e.preventDefault()
    if (validation.errors.length || !listReady || locked) return
    onBusy?.(true)
    void mutation.mutateAsync(structuredClone(value)).then(() => setSaved(true)).catch(() => {}).finally(() => onBusy?.(false))
  }}>
    <h3>{title}</h3><ErrorNotice error={mutation.error} />
    {saved && <p role="status">등록 완료 · REGISTERED · 활성화는 별도 승인입니다.</p>}
    <fieldset disabled={locked} className="ws-form"><legend>등록 정보와 평가 근거</legend>
      <label>종류<select aria-label="버전 종류" value={value.kind} onChange={e => onChange({ ...value, kind: e.target.value as ModelVersion['kind'], refId: undefined })}>{['PROMPT', 'MODEL', 'RUBRIC', 'GENERATION'].map(k => <option key={k}>{k}</option>)}</select>{field('kind')}</label>
      <p>기본값은 PROMPT입니다. M2 가중치 모델을 등록하려면 MODEL을 선택하세요.</p>
      {(['name', 'version'] as const).map(key => <label key={key}>{key === 'name' ? '이름' : '버전'}<input aria-label={key === 'name' ? '모델 이름' : '모델 버전'} aria-describedby={`${id}-${key}-error`} value={value[key]} onChange={e => onChange({ ...value, [key]: e.target.value })} /><span id={`${id}-${key}-error`}>{field(key)}</span></label>)}
      {value.kind === 'RUBRIC' && <label>기준표 원본 UUID<input value={value.refId ?? ''} onChange={e => onChange({ ...value, refId: e.target.value })} />{field('refId')}</label>}
      <label>아티팩트 주소 {value.kind === 'MODEL' ? '(필수)' : '(선택)'}<input value={value.artifactUri ?? ''} onChange={e => onChange({ ...value, artifactUri: e.target.value || undefined })} />{field('artifactUri')}</label>
      {Object.entries(EVIDENCE_LABELS).map(([key, label]) => <label key={key}>{label}<textarea aria-label={label} value={value.evaluation[key as keyof typeof EVIDENCE_LABELS]} onChange={e => evidence(key as keyof typeof EVIDENCE_LABELS, e.target.value)} />{field(`evaluation.${key}`)}</label>)}
      <label>평가 범위 (쉼표 또는 줄바꿈)<textarea aria-label="평가 범위" value={scopeText} onChange={e => { setScopeText(e.target.value); evidence('evaluatedScopes', splitScopes(e.target.value)) }} />{field('evaluation.evaluatedScopes')}</label>
      <label>한계·주의 (줄마다 한 항목)<textarea value={(value.evaluation.limitations ?? []).join('\n')} onChange={e => evidence('limitations', e.target.value.split('\n'))} />{field('evaluation.limitations')}</label>
    </fieldset>
    {manifest && <details><summary>manifest 파일 목록·해시</summary>{manifest.filter(m => m.name === value.name && m.version === value.version).flatMap(m => m.files).map(f => <p key={f.file}><strong>{f.file}</strong> · {f.bytes.toLocaleString()} bytes<br /><code>{f.sha256}</code></p>)}</details>}
    <ul>{validation.warnings.map((w, i) => <li key={i}>경고 · {w.message}</li>)}</ul>
    {field('manifest')}
    {!listReady && !saved && <p role="status">중복 검사를 위해 전체 모델 목록을 확인 중입니다. 조회 실패 시 다시 조회해 주세요.</p>}
    <button className="cj-primary" disabled={locked || !listReady || !!validation.errors.length}>{saved ? '등록 완료' : mutation.isPending ? '등록 중' : '버전 등록'}</button>
  </form>
}
async function readJson(file: File) {
  if (!file.name.toLowerCase().endsWith('.json') || file.size > 2 * 1024 * 1024) throw new Error('2MB 이하 JSON 파일을 선택해 주세요.')
  return file.text()
}
export function ModelRegistrationPanel({ existing, listReady }: { existing: ModelVersion[]; listReady: boolean }) {
  const [manual, setManual] = useState(blank), [file, setFile] = useState<RegistrationFile>()
  const [rows, setRows] = useState<ModelRegistration[]>([]), [originals, setOriginals] = useState<ModelRegistration[]>([])
  const [manifest, setManifest] = useState<ManifestModel[]>(), [hash, setHash] = useState('')
  const [bucket, setBucket] = useState(''), [error, setError] = useState<unknown>(), [busy, setBusy] = useState(0)
  const [reading, setReading] = useState(false), [manifestInvalid, setManifestInvalid] = useState(false)
  const seq = useRef(0)
  async function load(input: File, type: 'registration' | 'manifest') {
    const token = ++seq.current
    setReading(true); setError(undefined)
    try {
      const text = await readJson(input)
      if (token !== seq.current) return
      if (type === 'manifest') {
        const parsed = parseManifestFile(text)
        setManifest(parsed); setManifestInvalid(false)
        if (file) {
          const candidates = withManifestLimitations(file, parsed)
          setRows(before => before.map((r, i) => JSON.stringify(r.evaluation.limitations) === JSON.stringify(originals[i].evaluation.limitations)
            ? { ...r, evaluation: { ...r.evaluation, limitations: candidates[i].evaluation.limitations } } : r))
        }
      } else {
        const parsed = parseRegistrationFile(text)
        const digest = await crypto.subtle.digest('SHA-256', await input.arrayBuffer())
        if (token !== seq.current) return
        setHash(Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join(''))
        const initial = manifest ? withManifestLimitations(parsed, manifest) : parsed.requests
        setFile(parsed); setOriginals(structuredClone(initial)); setRows(initial); setBucket('')
      }
    } catch (e) {
      if (token !== seq.current) return
      setError(e)
      if (type === 'registration') { setFile(undefined); setRows([]) } else { setManifestInvalid(true); setManifest(undefined) }
    } finally { if (token === seq.current) setReading(false) }
  }
  const locked = busy > 0 || reading
  return <section className="ws-stack" aria-label="모델 버전 등록">
    <details className="ws-card"><summary>직접 새 버전 등록</summary><RegistrationForm title="새 버전 등록" value={manual} onChange={setManual} existing={existing} listReady={listReady} /></details>
    <section className="ws-card ws-form"><h2>등록 JSON 가져오기</h2>
      <p>브라우저에서 JSON을 읽어 각 항목을 검토합니다. 원본 파일은 업로드하지 않습니다. 파일당 최대 2MB.</p>
      <label>registration JSON<input type="file" accept=".json,application/json" disabled={locked} onChange={e => { const f = e.target.files?.[0]; if (f) void load(f, 'registration'); e.target.value = '' }} /></label>
      <label>manifest JSON (선택)<input type="file" accept=".json,application/json" disabled={locked} onChange={e => { const f = e.target.files?.[0]; if (f) void load(f, 'manifest'); e.target.value = '' }} /></label>
      {!manifest && <p>manifest 미첨부 · 파일 목록·해시 일치 여부는 확인 전입니다.</p>}
      <ErrorNotice error={error} />
      {file && <><p>가져온 JSON SHA-256: <code>{hash}</code></p>
        <details><summary>원본 설명·주의</summary><pre>{JSON.stringify(file.metadata, null, 2)}</pre></details>
        <label>운영 버킷 이름<input value={bucket} disabled={locked} onChange={e => setBucket(e.target.value)} /></label>
        <button disabled={locked || !bucket.trim() || /[<>\s/]/.test(bucket)} onClick={() => setRows(before => before.map(row => ({ ...row, artifactUri: row.artifactUri?.replaceAll('<버킷>', bucket.trim()) })))}>모든 항목의 버킷 치환</button>
        <p>{rows.length}개 항목 · 각 항목을 따로 등록합니다. 등록만으로 활성화되지 않습니다.</p>
      </>}
    </section>
    {rows.map((row, i) => <RegistrationForm key={`${hash}:${i}`} title={`가져온 모델 ${i + 1}`} value={row} original={originals[i]} existing={existing} listReady={listReady && !reading && !manifestInvalid}
      manifest={manifest} siblings={rows} onBusy={pending => setBusy(n => n + (pending ? 1 : -1))}
      onChange={value => setRows(before => before.map((r, index) => index === i ? value : r))} />)}
  </section>
}
