import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeftRight, Search, Star } from 'lucide-react'
import { Link } from 'react-router'
import { adminRetentionApi as api } from '../../data/admin/retentionApi.ts'
import { useAdminMutation, useAdminQuery } from '../../data/admin/queries.ts'
import { ApiError } from '../../data/apiClient.ts'
import { versionName } from '../../domain/admin/sceneVersions.ts'
import type { SceneHistory, SceneVersion, VersionAnnotation } from '../../domain/admin/sceneVersions.ts'
import { sceneLabels } from '../../domain/admin/themeDrafts.ts'
import type { ThemeDraft, ThemeSceneName } from '../../domain/admin/themeDrafts.ts'
import { ThemeMotionPlayer } from '../common/ThemeMotionPlayer.tsx'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import { date } from './adminFormatting.ts'

export type SceneView = 'scene' | 'mission' | 'missions' | 'compare'
interface Props {
  draft: ThemeDraft
  scene: ThemeSceneName
  view: SceneView
  open: (scene: ThemeSceneName, view: SceneView) => void
  still: boolean
}
type Pair = { left: string; right: string }
type Side = keyof Pair
type Write = { kind: 'select'; id: string; expected: string | null; count: number } | { kind: 'annotation'; id: string; patch: VersionAnnotation }

function pairFor(versions: SceneVersion[], current: SceneVersion, saved?: Pair): Pair {
  const has = (id: string | undefined) => !!id && versions.some(v => v.versionId === id)
  const left = saved && has(saved.left) ? saved.left : current.versionId
  const right = saved && has(saved.right) && saved.right !== left ? saved.right : versions.find(v => v.versionId !== left)?.versionId ?? ''
  return { left, right }
}

export function ThemeSceneReview({ draft, scene, view, open, still }: Props) {
  const cache = useQueryClient()
  const query = useAdminQuery(['theme-scene-history', draft.draftId, scene], signal => api.sceneVersions(draft.draftId, scene, signal))
  const [pairs, setPairs] = useState<Partial<Record<ThemeSceneName, Pair>>>({})
  const [message, setMessage] = useState('')
  const [failedScene, setFailedScene] = useState<ThemeSceneName>()
  const write = useAdminMutation(async ({ action, at }: { action: Write; at: ThemeSceneName }) => {
    const id = draft.draftId
    return action.kind === 'select'
      ? api.chooseSceneVersion(id, at, action.id, action.expected, action.count)
      : api.annotateSceneVersion(id, at, action.id, action.patch)
  })
  const lock = useRef(false)
  async function send(action: Write) {
    if (lock.current) return false
    lock.current = true; setFailedScene(scene); setMessage('')
    try {
      const result = await write.mutateAsync({ action, at: scene })
      cache.setQueryData(['admin', 'theme-scene-history', draft.draftId, scene], result)
      setMessage(action.kind === 'select' ? '이 장면의 선택본을 저장했습니다.' : '이력에 저장했습니다.')
      return true
    } catch (error) {
      if (error instanceof ApiError && error.problem.status === 409) {
        void query.refetch()
        void cache.invalidateQueries({ queryKey: ['admin', 'theme-draft', draft.draftId] })
      }
      return false
    } finally { lock.current = false }
  }
  const history = query.error ? undefined : query.data
  const current = history?.versions.find(v => v.versionId === history.selectedVersionId)
  const versions = history?.versions ?? []
  const preview = current ?? versions.find(v => v.selectable) ?? versions[0]
  const compare = view === 'compare' && versions.length > 1
  const pair = preview ? pairFor(versions, preview, pairs[scene]) : { left: '', right: '' }
  const day = scene !== 'INTRO' && scene !== 'OUTRO'
  const editable = draft.status === 'READY' && !draft.weekLocked && history?.editable === true
  const stored = draft.scenes.find(s => s.scene === scene)
  const media = preview ?? stored
  function changeSide(side: Side, id: string) {
    const other = side === 'left' ? 'right' : 'left'
    setPairs(previous => ({ ...previous, [scene]: { ...pair, [side]: id, [other]: pair[other] === id ? pair[side] : pair[other] } }))
  }
  function compareWith(id: string) {
    if (id !== pair.left) changeSide('right', id)
    open(scene, 'compare')
  }
  if (view === 'missions' || view === 'mission') return null
  return <div className="tw-review" aria-label="장면 검수">
    <div className="tw-review-heading"><div><small>장면 검수</small><h3>{sceneLabels[scene]}</h3></div>
      <div className="ws-actions">
        {day && <button onClick={() => open(scene, 'mission')}>이 요일 미션 보기</button>}
        {versions.length > 1 && <button aria-pressed={compare} onClick={() => open(scene, compare ? 'scene' : 'compare')}>
          <ArrowLeftRight size={15} aria-hidden="true" />{compare ? '선택본 단독 보기' : '두 버전 비교'}</button>}
      </div>
    </div>
    {compare ? <div className="tw-pair" aria-label="장면 버전 비교">{(['left', 'right'] as const).map(side => {
      const version = versions.find(v => v.versionId === pair[side])!
      const label = side === 'left' ? '왼쪽' : '오른쪽'
      return <section className="tw-pair-side" key={side} aria-label={label + ' 비교본'}>
        <label>{label} 비교본<select value={version.versionId} onChange={e => changeSide(side, e.target.value)}>
          {versions.map(v => <option value={v.versionId} key={v.versionId}>{versionName(v)}{v.versionId === current?.versionId ? ' · 현재 선택본' : ''}</option>)}</select></label>
        <ThemeMotionPlayer key={version.versionId} imageUrl={version.imageUrl} videoUrl={version.videoUrl} motion={version.motion} label={label + ' ' + sceneLabels[scene]} still={still} showSpots={day}/>
        <div className="tw-pair-foot"><small>{date(version.createdAt)} · {version.videoUrl ? '영상' : '그림·움직임'}</small>
          {editable && version.selectable && <button disabled={write.isPending} onClick={() => send({ kind: 'select', id: version.versionId, expected: current?.versionId ?? null, count: versions.length })}>
            {version.versionId === current?.versionId ? '현재 선택본 유지' : label + ' 버전 선택'}</button>}</div>
      </section>
    })}</div> : <div className="tw-single" aria-label="현재 선택본 미리보기">
      <ThemeMotionPlayer key={scene + (current?.versionId ?? '')} imageUrl={media?.imageUrl ?? null} videoUrl={media?.videoUrl ?? null}
        motion={media?.motion} label={sceneLabels[scene]} still={still} showSpots={day}/>
      {current && <span>현재 선택본 · {versionName(current)}</span>}
      {!current && preview && <span>선택 전 · {versionName(preview)} {editable && preview.selectable && <button disabled={write.isPending}
        onClick={() => send({ kind:'select',id:preview.versionId,expected:null,count:versions.length })}>이 버전 선택</button>}</span>}
    </div>}
    <QueryFeedback query={query} />
    {failedScene === scene && <><ErrorNotice error={write.error}/>{message && <p role="status">{message}</p>}</>}
    {history && <SceneHistoryList key={scene} history={history} current={current} editable={editable} busy={write.isPending}
      send={send} compare={compare} compareWith={compareWith} changeSide={changeSide} />}
  </div>
}

function SceneHistoryList({ history, current, editable, busy, send, compare, compareWith, changeSide }: {
  history: SceneHistory; current?: SceneVersion; editable: boolean; busy: boolean; send: (action: Write) => Promise<boolean>
  compare: boolean; compareWith: (id: string) => void; changeSide: (side: Side, id: string) => void
}) {
  const [mode, setMode] = useState<'recent' | 'all' | 'starred'>('recent')
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState<SceneVersion | null>(null)
  const [note, setNote] = useState('')
  const [noteError, setNoteError] = useState(false)
  const [page, setPage] = useState(0)
  const keyword = search.trim().toLocaleLowerCase('ko')
  const filtered = history.versions.filter(v => {
    if (mode === 'starred' && !v.starred) return false
    const text = [versionName(v), 'v' + v.number, v.createdAt.slice(0, 10), date(v.createdAt), v.note].join(' ').toLocaleLowerCase('ko')
    return !keyword || text.includes(keyword)
  })
  const pageSize = mode === 'recent' ? 3 : 8
  const index = mode === 'recent' ? 0 : Math.max(0, Math.min(page, Math.ceil(filtered.length / pageSize) - 1))
  const rows = filtered.slice(index * pageSize, (index + 1) * pageSize)
  return <section className="tw-history" aria-label="장면 생성 이력">
    <h3>생성 이력 <small>{history.versions.length}개</small></h3>
    {current && <div className="tw-pinned"><div><small>현재 선택본</small><strong>{versionName(current)}</strong></div>
      <div><Link to={'/admin/theme-drafts?' + new URLSearchParams({ draftId: history.rootDraftId, scene: history.scene })}>원본 초안</Link>
      <Link to={'/admin/theme-drafts?' + new URLSearchParams({ draftId: current.versionId, scene: history.scene })}>미디어 출처 초안</Link></div></div>}
    <div className="tw-history-tools"><div className="ws-actions" aria-label="이력 범위">
      {(['recent','all','starred'] as const).map(m => <button key={m} aria-pressed={mode === m} onClick={() => { setMode(m); setPage(0); if (m === 'recent') setSearch('') }}>
        {{ recent: '최근 3개', all: '전체 이력', starred: '별표' }[m]}</button>)}</div>
      <label className="tw-search"><Search size={16} aria-hidden="true"/><input aria-label="생성 이력 검색" placeholder="버전, 날짜, 메모 검색" value={search}
        onChange={e => { setSearch(e.target.value); setPage(0); if (mode === 'recent' && e.target.value.trim()) setMode('all') }}/></label></div>
    {!rows.length && <p>{history.versions.length ? '조건에 맞는 이력이 없습니다.' : '생성된 미디어 이력이 없습니다.'}</p>}
    <ol className="tw-history-list">{rows.map(v => <li key={v.versionId}><div className="tw-history-info">
      <strong>{versionName(v)}</strong><small>{date(v.createdAt)}{v.versionId === current?.versionId ? ' · 현재 선택본' : ''}{v.starred ? ' · 별표' : ''}</small>
      {v.note && <p>{v.note}</p>}</div><div className="ws-actions">
      {history.versions.length > 1 && (compare ? <><button onClick={() => changeSide('left', v.versionId)}>왼쪽에 보기</button><button onClick={() => changeSide('right', v.versionId)}>오른쪽에 보기</button></> : <button onClick={() => compareWith(v.versionId)}>비교</button>)}
      {editable && v.selectable && <><button aria-label={versionName(v) + ' 별표'} aria-pressed={v.starred} disabled={busy} onClick={() => send({kind:'annotation',id:v.versionId,patch:{starred:!v.starred}})}><Star size={15} fill={v.starred ? 'currentColor' : 'none'} aria-hidden="true"/></button>
      <button disabled={busy} onClick={() => {setEditing(v);setNote(v.note);setNoteError(false)}}>메모</button></>}
      </div></li>)}</ol>
    {mode !== 'recent' && filtered.length > pageSize && <nav className="ws-actions" aria-label="생성 이력 페이지"><button disabled={!index} onClick={() => setPage(index - 1)}>이전</button><span>{index + 1} / {Math.ceil(filtered.length / pageSize)}</span><button disabled={(index + 1) * pageSize >= filtered.length} onClick={() => setPage(index + 1)}>다음</button></nav>}
    {editing && editable && <Modal title={versionName(editing) + ' 메모'} onClose={() => {if(!busy)setEditing(null)}}>
      <label className="ws-form">검수 메모<textarea value={note} onChange={e => setNote(e.target.value)} rows={3}/></label>
      <small>{[...note].length} / 160자</small>{noteError && <p role="alert">메모를 저장하지 못했습니다. 이력을 다시 확인해 주세요.</p>}
      <div className="ws-actions"><button disabled={busy} onClick={() => setEditing(null)}>취소</button>
      <button disabled={busy || [...note].length > 160} onClick={async () => {
        setNoteError(false)
        if(await send({kind:'annotation',id:editing.versionId,patch:{note}}))setEditing(null)
        else setNoteError(true)
      }}>메모 저장</button></div></Modal>}
  </section>
}
