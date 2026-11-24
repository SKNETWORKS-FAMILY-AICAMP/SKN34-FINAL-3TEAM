import { useId, useRef, useState } from 'react'
import { Check, FileJson, FolderOpen } from 'lucide-react'
import { adminApi } from '../../data/admin/api.ts'
import { ApiError } from '../../data/apiClient.ts'
import { useAdminMutation } from '../../data/admin/queries.ts'
import type { ModelVersion } from '../../domain/admin/operations.ts'
import { supportsPreflight, preflightMessage, changedRegistrationFields, registrationRequest, EVIDENCE_LABELS, KNOWN_MODEL_SCOPES, parseManifestFile, parseRegistrationFile, splitScopes, validateRegistration, withManifestLimitations } from '../../domain/admin/modelRegistration.ts'
import type { PreflightResult, ManifestModel, ModelRegistration, RegistrationFile } from '../../domain/admin/modelRegistration.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import { busyProps } from './busyButton.ts'
import { modelKindLabel, modelScopeLabel } from './adminFormatting.ts'

function ScopePicker({ scopes, onChange }: { scopes: string[]; onChange: (scopes: string[]) => void }) {
  const [draft, setDraft] = useState<string>()
  return <fieldset><legend>평가 범위</legend>
    <div className="model-scope-options">{KNOWN_MODEL_SCOPES.map(scope =>
      <label className="ws-check" key={scope}><input type="checkbox" checked={scopes.includes(scope)} onChange={e =>
        onChange(e.target.checked ? [...scopes, scope] : scopes.filter(s => s !== scope))} />{modelScopeLabel(scope)}</label>)}</div>
    <details><summary>기타 범위 및 코드 직접 편집</summary>
      <label>전체 범위 코드 (쉼표 또는 줄바꿈)<textarea aria-label="평가 범위" value={draft ?? scopes.join('\n')}
        onChange={e => { setDraft(e.target.value); onChange(splitScopes(e.target.value)) }} onBlur={() => setDraft(undefined)} /></label>
    </details>
  </fieldset>
}

const blank = (): ModelRegistration => ({ kind: 'PROMPT', name: '', version: '', evaluation: {
  datasetId: '', datasetVersion: '', baselineVersion: '', comparisonReport: '', trainingEvaluationSeparation: '',
  quoteAccuracy: '', calculationAccuracy: '', humanReview: '', evaluatedScopes: [], limitations: [],
} })
function RegistrationForm({ value, onChange, existing, listReady, manifest, siblings, original, title, onBusy, jsonSha256, manifestSha256 }: {
  value: ModelRegistration; onChange: (value: ModelRegistration) => void; existing: ModelVersion[]; listReady: boolean
  jsonSha256?: string; manifestSha256?: string
  manifest?: ManifestModel[]; siblings?: ModelRegistration[]; original?: ModelRegistration; title: string; onBusy?: (busy: boolean) => void
}) {
  const id = useId(), [saved, setSaved] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editingPaths, setEditingPaths] = useState<string[]>([])
  const mutation = useAdminMutation((snapshot: ModelRegistration) => adminApi.registerModel(registrationRequest(snapshot, original, jsonSha256, manifestSha256, manifest)))
  const validation = validateRegistration(value, existing, manifest, siblings)
  const conflict = mutation.error instanceof ApiError && mutation.error.problem.code === 'MODEL_VERSION_CONFLICT'
  const errors = new Set(saved ? [] : validation.errors.map(error => error.path))
  if (conflict) { errors.add('name'); errors.add('version') }
  if (errors.has('manifest')) {
    errors.add('name'); errors.add('version'); errors.add('evaluation.evaluatedScopes')
  }
  const needsAttention = (path: string) => errors.has(path) || editingPaths.includes(path)
  const show = (path: string) => !original || editing || needsAttention(path)
  const changed = original ? changedRegistrationFields(value, original) : []
  const field = (path: string) => <>{changed.includes(path) && <small>수정됨</small>}
    {!saved && validation.errors.filter(e => e.path === path).map(e => <small className="model-error" key={e.message}>{e.message}</small>)}
    {conflict && ['name', 'version'].includes(path) && <small className="model-error">{mutation.error?.message}</small>}</>
  const preflight = useAdminMutation(adminApi.preflightModel)
  const candidate = manifest?.find(m => m.name === value.name && m.version === value.version)
  const preflightBody = { name: value.name, version: value.version, artifactUri: value.artifactUri ?? '', files: candidate?.files ?? [] }
  const preflightKey = JSON.stringify(preflightBody)
  const [checked, setChecked] = useState<{ key: string; result?: PreflightResult; error?: unknown }>()
  const pending = mutation.isPending || preflight.isPending
  const locked = saved || pending
  const evidence = (key: keyof ModelRegistration['evaluation'], data: string | string[]) => onChange({ ...value, evaluation: { ...value.evaluation, [key]: data } })
  const artifact = <label data-field="artifactUri">아티팩트 주소 {value.kind === 'MODEL' ? '(필수)' : '(선택)'}<input aria-label="아티팩트 주소" value={value.artifactUri ?? ''} onChange={e => onChange({ ...value, artifactUri: e.target.value || undefined })} />{field('artifactUri')}</label>
  const optionalError = needsAttention('evaluation.limitations') || (value.kind !== 'MODEL' && needsAttention('artifactUri'))
  return <form className="ws-card ws-form model-registration" aria-label={title} onSubmit={e => {
    e.preventDefault()
    if (validation.errors.length || !listReady || locked) return
    onBusy?.(true)
    void mutation.mutateAsync(structuredClone(value)).then(() => setSaved(true)).catch(() => {}).finally(() => onBusy?.(false))
  }}>
    <h3>{original ? [value.name, value.version].filter(Boolean).join(' · ') || title : title}</h3><ErrorNotice error={mutation.error} />
    {saved && <p role="status">등록 완료 · REGISTERED · 활성화는 별도 승인입니다.</p>}
    {original && <>
      <dl className="model-evidence"><div><dt>종류</dt><dd>{Object.hasOwn(modelKindLabel, value.kind) ? modelKindLabel[value.kind] : '미지정'}</dd></div>
        <div><dt>평가셋</dt><dd>{[value.evaluation.datasetId, value.evaluation.datasetVersion].filter(Boolean).join(' · ') || '미입력'}</dd></div>
        <div><dt>평가 범위</dt><dd>{value.evaluation.evaluatedScopes.map(modelScopeLabel).join(', ') || '미선택'}</dd></div>
      </dl>
      <button type="button" aria-expanded={editing} aria-controls={id} onClick={() => { setEditing(!editing); setEditingPaths([]) }}>{editing ? '상세 접기' : '상세 보기·수정'}</button>
    </>}
    <fieldset id={id} disabled={locked} hidden={!!original && !editing && !errors.size && !editingPaths.length} className="ws-form" onFocusCapture={e => {
      const path = e.target.closest<HTMLElement>('[data-field]')?.dataset.field
      if (original && !editing && path && !editingPaths.includes(path)) setEditingPaths(paths => [...paths, path])
    }}><legend>{original && !editing ? '항목 수정' : '등록 정보와 평가 근거'}</legend>
      {show('kind') && <label data-field="kind">종류<select aria-label="버전 종류" value={value.kind} onChange={e => onChange({ ...value, kind: e.target.value as ModelVersion['kind'], refId: undefined })}>
        {!Object.hasOwn(modelKindLabel, value.kind) && <option value={value.kind}>종류 선택</option>}
        {Object.entries(modelKindLabel).map(([key, label]) => <option key={key} value={key}>{label} ({key})</option>)}</select>{field('kind')}</label>}
      {(['name', 'version'] as const).filter(show).map(key => <label key={key} data-field={key}>{key === 'name' ? '이름' : '버전'}<input aria-label={key === 'name' ? '모델 이름' : '모델 버전'} aria-describedby={`${id}-${key}-error`} value={value[key]} onChange={e => onChange({ ...value, [key]: e.target.value })} /><span id={`${id}-${key}-error`}>{field(key)}</span></label>)}
      {(value.kind === 'RUBRIC' || value.refId) && show('refId') && <label data-field="refId">기준표 원본 UUID<input value={value.refId ?? ''} onChange={e => onChange({ ...value, refId: e.target.value || undefined })} />{field('refId')}</label>}
      {value.kind === 'MODEL' && show('artifactUri') && artifact}
      {Object.entries(EVIDENCE_LABELS).filter(([key]) => show(`evaluation.${key}`)).map(([key, label]) => <label key={key} data-field={`evaluation.${key}`}>{label}<textarea aria-label={label} value={value.evaluation[key as keyof typeof EVIDENCE_LABELS]} onChange={e => evidence(key as keyof typeof EVIDENCE_LABELS, e.target.value)} />{field(`evaluation.${key}`)}</label>)}
      {show('evaluation.evaluatedScopes') && <div data-field="evaluation.evaluatedScopes"><ScopePicker scopes={value.evaluation.evaluatedScopes} onChange={scopes => evidence('evaluatedScopes', scopes)} />{field('evaluation.evaluatedScopes')}</div>}
      {(!original || editing || optionalError) && <details open={optionalError || undefined}><summary>추가 정보</summary>
        {value.kind !== 'MODEL' && show('artifactUri') && artifact}
        {show('evaluation.limitations') && <label data-field="evaluation.limitations">한계·주의 (줄마다 한 항목)<textarea value={(value.evaluation.limitations ?? []).join('\n')} onChange={e => evidence('limitations', e.target.value ? e.target.value.split('\n') : [])} />{field('evaluation.limitations')}</label>}
      </details>}
    </fieldset>
    {value.kind === 'MODEL' && candidate && supportsPreflight(value.name, candidate.files) && <section aria-label="모델 사전 검사">
      <button type="button" {...busyProps(pending, saved || !listReady || !!validation.errors.length)} onClick={() => {
        const key = preflightKey
        setChecked(undefined); onBusy?.(true)
        void preflight.mutateAsync(preflightBody).then(result => setChecked({ key, result }))
          .catch(error => setChecked({ key, error })).finally(() => onBusy?.(false))
      }}>{preflight.isPending ? '사전 검사 중' : '사전 검사'}</button>
      <p>manifest에 기록된 모델 파일의 형식과 해시를 확인합니다.</p>
      {checked && checked.key !== preflightKey && <p role="status">입력이 변경되었습니다. 사전 검사를 다시 실행해 주세요.</p>}
      {checked?.key === preflightKey && <><ErrorNotice error={checked.error} />{checked.result && <div role="status">
        <strong>{preflightMessage(checked.result.code)}</strong>
        <ul>{checked.result.files.map(f => <li key={f.file}>{f.file}: {preflightMessage(f.code)}</li>)}</ul>
      </div>}</>}
    </section>}
    {manifest && <details><summary>manifest 파일 목록·해시</summary>{manifest.filter(m => m.name === value.name && m.version === value.version).flatMap(m => m.files).map(f => <p key={f.file}><strong>{f.file}</strong> · {f.bytes.toLocaleString()} bytes<br /><code>{f.sha256}</code></p>)}</details>}
    <ul>{validation.warnings.map((w, i) => <li key={i}>경고 · {w.message}</li>)}</ul>
    {field('manifest')}
    {!listReady && !saved && <p role="status">중복 검사를 위해 전체 모델 목록을 확인 중입니다. 조회 실패 시 다시 조회해 주세요.</p>}
    <button className="cj-primary" {...busyProps(pending, saved || !listReady || !!validation.errors.length)}>{saved ? '등록 완료' : mutation.isPending ? '등록 중' : '버전 등록'}</button>
  </form>
}
async function readJson(file: File) {
  if (!file.name.toLowerCase().endsWith('.json') || file.size > 2 * 1024 * 1024) throw new Error('2MB 이하 JSON 파일을 선택해 주세요.')
  return file.text()
}
type ImportKind = 'registration' | 'manifest'
type ImportFeedback = { name: string; error?: unknown }

function JsonPicker({ title, hint, feedback, pending, disabled, onSelect }: {
  title: string; hint: string; feedback?: ImportFeedback; pending: boolean; disabled: boolean; onSelect: (file: File) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  const id = useId()
  const loaded = feedback && !pending && !feedback.error
  return <div className="model-file-picker">
    <span className="model-file-icon" aria-hidden="true"><FileJson size={22} /></span>
    <div className="model-file-copy">
      <strong>{title}</strong><small id={id}>{hint}</small>
      <div role="status">{feedback && <span className={loaded ? 'model-file-loaded' : undefined}>
        {loaded && <Check size={15} aria-hidden="true" />}{feedback.name} · {pending ? '읽는 중' : loaded ? '가져옴' : '가져오기 실패'}
      </span>}</div>
      {feedback?.error != null && <ErrorNotice error={feedback.error} />}
    </div>
    <input hidden ref={input} aria-label={title} type="file" accept=".json,application/json" disabled={disabled} onChange={e => {
      const selected = e.target.files?.[0]
      e.target.value = ''
      if (selected) onSelect(selected)
    }} />
    <button type="button" aria-label={title + (feedback ? ' 다시 선택' : ' 선택')} aria-describedby={id} {...busyProps(disabled)} onClick={() => input.current?.click()}>
      <FolderOpen size={16} aria-hidden="true" />{feedback ? '다시 선택' : '파일 선택'}
    </button>
  </div>
}
export function ModelRegistrationPanel({ existing, listReady }: { existing: ModelVersion[]; listReady: boolean }) {
  const [manual, setManual] = useState(blank), [file, setFile] = useState<RegistrationFile>()
  const [rows, setRows] = useState<ModelRegistration[]>([]), [originals, setOriginals] = useState<ModelRegistration[]>([])
  const [manifest, setManifest] = useState<ManifestModel[]>(), [hash, setHash] = useState('')
  const [manifestHash, setManifestHash] = useState('')
  const [bucket, setBucket] = useState(''), [busy, setBusy] = useState(0)
  const [reading, setReading] = useState<ImportKind>()
  const [feedback, setFeedback] = useState<Partial<Record<ImportKind, ImportFeedback>>>({})
  const seq = useRef(0)
  function applyManifest(next: ManifestModel[] | undefined, nextHash: string) {
    setManifest(next); setManifestHash(nextHash)
    if (!file) return
    const previous = manifest ? withManifestLimitations(file, manifest) : file.requests
    const updated = next ? withManifestLimitations(file, next) : file.requests
    setRows(before => before.map((row, i) => JSON.stringify(row.evaluation.limitations) === JSON.stringify(previous[i].evaluation.limitations)
      ? { ...row, evaluation: { ...row.evaluation, limitations: updated[i].evaluation.limitations } } : row))
  }
  async function load(input: File, type: ImportKind) {
    const token = ++seq.current
    setReading(type); setFeedback(before => ({ ...before, [type]: { name: input.name } }))
    try {
      const text = await readJson(input)
      const digest = await crypto.subtle.digest('SHA-256', await input.arrayBuffer())
      const fileHash = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('')
      if (token !== seq.current) return
      if (type === 'manifest') {
        applyManifest(parseManifestFile(text), fileHash)
      } else {
        const parsed = parseRegistrationFile(text)
        if (token !== seq.current) return
        setHash(fileHash)
        const initial = manifest ? withManifestLimitations(parsed, manifest) : parsed.requests
        setFile(parsed); setOriginals(JSON.parse(text).requests); setRows(initial); setBucket('')
      }
    } catch (e) {
      if (token !== seq.current) return
      setFeedback(before => ({ ...before, [type]: { name: input.name, error: e } }))
      if (type === 'registration') { setFile(undefined); setRows([]) } else { applyManifest(undefined, '') }
    } finally { if (token === seq.current) setReading(undefined) }
  }
  const locked = busy > 0 || !!reading
  return <section className="ws-stack" aria-label="모델 버전 등록">
    <section className="ws-card ws-form model-import"><h2>등록 JSON 가져오기</h2>
      <JsonPicker title="모델 등록 파일" hint="모델 정보와 평가 근거가 담긴 JSON · 최대 2MB" feedback={feedback.registration}
        pending={reading === 'registration'} disabled={locked} onSelect={input => void load(input, 'registration')} />
      <details className="model-manifest"><summary>모델 파일 검사용 manifest {feedback.manifest ? `· ${feedback.manifest.name}` : '(선택)'}</summary>
        <JsonPicker title="검사용 manifest 파일" hint="모델 파일 목록과 해시가 담긴 JSON · 최대 2MB" feedback={feedback.manifest}
          pending={reading === 'manifest'} disabled={locked} onSelect={input => void load(input, 'manifest')} />
        {feedback.manifest && <button type="button" {...busyProps(locked)} onClick={() => {
          applyManifest(undefined, ''); setFeedback(before => ({ ...before, manifest: undefined }))
        }}>manifest 제외</button>}
      </details>
      {file && <>
        <details><summary>원본 설명·주의 및 파일 해시</summary><pre>{JSON.stringify(file.metadata, null, 2)}</pre><p>SHA-256 <code>{hash}</code></p></details>
        {rows.some(row => row.artifactUri?.includes('<버킷>')) && <><label>운영 버킷 이름<input value={bucket} disabled={locked} onChange={e => setBucket(e.target.value)} /></label>
          <button {...busyProps(locked, !bucket.trim() || /[<>\s/]/.test(bucket))} onClick={() => setRows(before => before.map(row => ({ ...row, artifactUri: row.artifactUri?.replaceAll('<버킷>', () => bucket.trim()) })))}>모든 항목의 버킷 치환</button></>}
        <p role="status">{rows.length}개 항목을 읽었습니다. 아래에서 내용을 확인한 뒤 각 버전을 등록하세요.</p>
      </>}
    </section>
    {rows.map((row, i) => <RegistrationForm key={`${hash}:${i}`} title={`가져온 모델 ${i + 1}`} value={row} original={originals[i]} existing={existing} listReady={listReady && !reading && !feedback.manifest?.error}
      jsonSha256={hash} manifestSha256={manifestHash || undefined} manifest={manifest} siblings={rows} onBusy={pending => setBusy(n => n + (pending ? 1 : -1))}
      onChange={value => setRows(before => before.map((r, index) => index === i ? value : r))} />)}
    <details className="model-manual"><summary>직접 새 버전 등록</summary><RegistrationForm title="새 버전 등록" value={manual} onChange={setManual} existing={existing} listReady={listReady} /></details>
  </section>
}
