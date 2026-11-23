import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { Dispatch, ReactNode, RefObject, SetStateAction } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeftRight, Clock3, Film, Star } from 'lucide-react'
import { Link } from 'react-router'
import { adminRetentionApi as api } from '../../data/admin/retentionApi.ts'
import { useAdminMutation, useAdminQuery } from '../../data/admin/queries.ts'
import { ApiError } from '../../data/apiClient.ts'
import { sceneVideoLabel, versionName } from '../../domain/admin/sceneVersions.ts'
import type { SceneHistory, SceneVersion, VersionAnnotation } from '../../domain/admin/sceneVersions.ts'
import { themeDraftSourceLabels } from '../../domain/admin/themeDrafts.ts'
import type { ThemeDraft, ThemeDraftScene, ThemeSceneName } from '../../domain/admin/themeDrafts.ts'
import { ThemeMotionPlayer } from '../common/ThemeMotionPlayer.tsx'
import { useReducedMotion } from '../common/useReducedMotion.ts'
import { ThemePairPlayback } from './ThemePairPlayback.tsx'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import { date } from './adminFormatting.ts'
import { busyProps } from './busyButton.ts'
import type { reviewWeeks } from './adminFormatting.ts'
import './theme-review-media.css'

export type SceneView = 'scene' | 'mission' | 'missions' | 'compare' | 'week'
interface Props {
  weeks: ReturnType<typeof reviewWeeks>
  draft: ThemeDraft
  scene: ThemeSceneName
  view: SceneView
  open: (scene: ThemeSceneName, view: SceneView) => void
  still: boolean
  regenActions?: ReactNode
  regenReason: string
  regenSourceId: string
  pairs: ScenePairs
  setPairs: Dispatch<SetStateAction<ScenePairs>>
  settings: SceneSettings
  updateSettings: (patch: SceneSettings) => void
  generated?: { scene: ThemeSceneName; id: string } | null
  onComparedGeneration: (id: string) => void
}
type Side = 'left' | 'right'
type Source = 'ALL' | SceneVersion['source']
type Panel = { id: string; source: Source; remembered?: string }
type Pair = Record<Side, Panel>
export type ScenePairs = Partial<Record<ThemeSceneName, Pair>>
export type SceneSettings = { linked?: boolean; mode?: 'recent' | 'all' | 'starred'; search?: string; page?: number }
type PlaybackPosition = { time: number; rate: number; muted: boolean; playing: boolean }
function playbackPosition(video: HTMLVideoElement | null): PlaybackPosition | undefined {
  if (video && video.readyState >= HTMLMediaElement.HAVE_METADATA)
    return { time: video.currentTime, rate: video.playbackRate, muted: video.muted, playing: !video.paused && !video.ended }
}
type Write = { kind: 'select'; id: string; expected: string | null; count: number } | { kind: 'annotation'; id: string; patch: VersionAnnotation }

function matchesSource(version: SceneVersion, source: Source) {
  return source === 'ALL' || source === version.source
}
function pairFor(versions: SceneVersion[], current: SceneVersion | undefined, saved?: Pair): Pair {
  const left: Panel = saved?.left ?? { id: current?.versionId ?? '', source: 'ALL' }
  const right: Panel = saved?.right ?? { id: '', source: 'ALL' }
  const validId = (panel: Panel) => versions.find(v => v.versionId === panel.id && matchesSource(v, panel.source))?.versionId
  const otherId = (panel: Panel, exclude?: string) => versions.find(v => v.versionId !== exclude && matchesSource(v, panel.source))?.versionId ?? ''
  const leftId = validId(left) ?? otherId(left, validId(right))
  const rightId = validId(right)
  return {
    left: { ...left, id: leftId },
    right: { ...right, id: rightId && rightId !== leftId ? rightId : otherId(right, leftId) },
  }
}

export function ThemeSceneReview({ draft, scene, view, weeks, open, still, regenActions, regenReason, regenSourceId, pairs, setPairs, settings, updateSettings, generated, onComparedGeneration }: Props) {
  const cache = useQueryClient()
  const query = useAdminQuery(['theme-scene-history', draft.draftId, scene], signal => api.sceneVersions(draft.draftId, scene, signal))
  const leftVideo = useRef<HTMLVideoElement>(null), rightVideo = useRef<HTMLVideoElement>(null)
  const positions = useRef<Partial<Record<Side, PlaybackPosition | undefined>> | null>(null)
  const reducedMotion = useReducedMotion()
  const [failedVideos, setFailedVideos] = useState<Set<string>>(() => new Set())
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
  const pair = pairFor(versions, preview, pairs[scene])
  const regenSource = versions.find(v => v.versionId === regenSourceId)
  const sourceInPair = pair.left.id === regenSourceId || pair.right.id === regenSourceId
  const regenRow = regenActions && <div className="tw-regen-block">
    <div className="tw-regen-row"><strong>{!compare && !current && preview?.versionId === regenSourceId && '선택 전 · '}
      {regenSource ? versionName(regenSource) : '현재 초안'}</strong>{regenActions}</div>
    {regenReason && <p className="tw-regen-reason" id="scene-regen-reason">{regenReason}</p>}
  </div>
  const pairUrls = [pair.left, pair.right].map(p => versions.find(v => v.versionId === p.id)?.videoUrl)
  const pairFailed = pairUrls.some(url => url && failedVideos.has(url))
  useLayoutEffect(() => {
    const pending = positions.current
    positions.current = null
    if (!pending) return
    const events = new AbortController()
    for (const side of ['left', 'right'] as const) {
      const position = pending[side], video = side === 'left' ? leftVideo.current : rightVideo.current
      if (!position || !video) continue
      const restore = () => {
        if (Number.isFinite(video.duration)) video.currentTime = Math.min(position.time, video.duration)
        video.playbackRate = position.rate
        video.muted = position.muted
        if (position.playing) void video.play().catch(error => {
          if (!events.signal.aborted && !(error instanceof DOMException && error.name === 'AbortError')) {
            setFailedScene(scene)
            setMessage('재생 위치를 복원했습니다. 재생 버튼을 눌러 계속 확인하세요.')
          }
        })
      }
      if (video.readyState >= HTMLMediaElement.HAVE_METADATA) restore()
      else video.addEventListener('loadedmetadata', restore, { once: true, signal: events.signal })
    }
    return () => events.abort()
  }, [scene, pair.left.id, pair.right.id])
  useEffect(() => {
    if (!generated || generated.scene !== scene || (view !== 'scene' && view !== 'compare') || !history) return
    const candidate = history.versions.find(v => v.versionId === generated.id)
    const previous = history.versions.find(v => v.versionId === pair.left.id && v.versionId !== generated.id) ??
      history.versions.find(v => v.versionId !== generated.id)
    if (!candidate || !previous) return
    setPairs(before => ({ ...before, [scene]: {
      left: { id: previous.versionId, source: 'ALL' }, right: { id: candidate.versionId, source: 'ALL' },
    } }))
    onComparedGeneration(generated.id)
    if (view !== 'compare') open(scene, 'compare')
  }, [generated, scene, view, history, pair.left.id, setPairs, onComparedGeneration, open])
  const day = scene !== 'INTRO' && scene !== 'OUTRO'
  const sceneLabel = sceneVideoLabel(scene)
  const editable = draft.status === 'READY' && !draft.weekLocked && history?.editable === true
  const stored = draft.scenes.find(s => s.scene === scene)
  const media = preview ?? stored
  function renderPlayer(item: SceneVersion | ThemeDraftScene | undefined, label: string, key: string, ref?: RefObject<HTMLVideoElement | null>) {
    const url = item?.videoUrl
    if (url && failedVideos.has(url) && (!(still || reducedMotion) || !item?.imageUrl)) {
      return <div className="tw-film-empty" role="alert"><strong>{label}</strong><p>영상 파일을 불러오지 못했습니다.</p>
        <button onClick={() => setFailedVideos(previous => {
          const next = new Set(previous)
          next.delete(url)
          return next
        })}>다시 불러오기</button></div>
    }
    return <ThemeMotionPlayer key={key} videoRef={ref} autoPlay={false} imageUrl={item?.imageUrl ?? null} videoUrl={url ?? null}
      motion={item?.motion} label={label} still={still} showSpots={day} onVideoError={() => {
        if (!url) return
        leftVideo.current?.pause()
        rightVideo.current?.pause()
        setFailedVideos(previous => new Set(previous).add(url))
      }}/>
  }
  function changeSide(side: Side, id: string) {
    const other = side === 'left' ? 'right' : 'left'
    if (pair[other].id === id) {
      swapPair()
      return
    }
    const chosen = versions.find(v => v.versionId === id)
    const source = chosen && matchesSource(chosen, pair[side].source) ? pair[side].source : 'ALL'
    if (pair[side].id !== id) rememberPositions()
    setPairs(previous => ({ ...previous, [scene]: { ...pair, [side]: { ...pair[side], id, source } } }))
  }
  function rememberPositions(swap = false) {
    const left = playbackPosition(leftVideo.current), right = playbackPosition(rightVideo.current)
    positions.current = swap ? { left: right, right: left } : { left, right }
  }
  function swapPair() {
    rememberPositions(true)
    setPairs(previous => ({ ...previous, [scene]: { left: pair.right, right: pair.left } }))
  }
  function changeSource(side: Side, source: Source) {
    const old = pair[side], opposite = pair[side === 'left' ? 'right' : 'left']
    const candidates = versions.filter(v => matchesSource(v, source) && v.versionId !== opposite.id)
    const remembered = old.source === 'ALL' ? old.id : old.remembered
    const preferred = source === 'ALL' ? remembered : old.id
    const id = (candidates.find(v => v.versionId === preferred) ?? candidates.find(v => v.versionId === old.id) ?? candidates[0])?.versionId ?? ''
    if (old.id !== id) rememberPositions()
    setPairs(previous => ({ ...previous, [scene]: { ...pair, [side]: { source, id, remembered } } }))
  }
  function compareWith(id: string) {
    const baseline = current ?? versions.find(v => v.versionId !== id)
    if (!baseline || baseline.versionId === id) return
    setPairs(previous => ({ ...previous, [scene]: {
      left: { id: baseline.versionId, source: 'ALL' }, right: { id, source: 'ALL' },
    } }))
    open(scene, 'compare')
  }
  if (view === 'missions' || view === 'mission' || view === 'week') return null
  return <div className="tw-review tw-review-media" aria-label="장면 검수">
    <section className="tw-film-panel">
    <header className="tw-film-header"><div><small className="tw-film-kicker">
      {compare ? <ArrowLeftRight size={15} aria-hidden="true"/> : <Film size={15} aria-hidden="true"/>}
      {compare ? '버전 비교' : '영상 검수'}</small><h3>{sceneLabel}</h3>
      {compare && <div className="tw-film-scope">{draft.grade && <span>{draft.grade.slice(1)}학년</span>}
        {weeks.map(w=><span key={w.label}>{w.label} <time dateTime={w.date}>{w.range}</time></span>)}<span>{sceneLabel}</span></div>}</div>
      {compare ? <button onClick={() => open(scene, 'scene')}>단일 보기</button>
        : current && <span className="tw-film-badge is-blue">현재 선택본</span>}
    </header>
    {compare ? <><div className="tw-pair-toolbar"><strong>버전 {versions.length}개</strong><span>비교할 영상 선택</span>
      <button disabled={!pair.left.id || !pair.right.id} onClick={swapPair}><ArrowLeftRight size={14} aria-hidden="true"/>좌우 바꾸기</button></div>
    <div className="tw-pair" aria-label="장면 버전 비교">{(['left', 'right'] as const).map(side => {
      const panel = pair[side], other = pair[side === 'left' ? 'right' : 'left']
      const version = versions.find(v => v.versionId === panel.id)
      const options = versions.filter(v => matchesSource(v, panel.source))
      const label = side === 'left' ? '왼쪽' : '오른쪽'
      const selected = !!version && version.versionId === current?.versionId
      const confirmText = selected ? '이 선택본 확정' : '이 버전 사용'
      return <section className="tw-pair-side" key={side} aria-label={label + ' 비교본'}>
        <div className="tw-film-badges"><span className={'tw-film-badge' + (side === 'right' ? ' is-blue' : '')}>{label} 영상</span>
          {selected && <span className="tw-film-badge is-selected">현재 선택본</span>}</div>
        <div className="tw-film-selectors"><label>출처<select aria-label={label + ' 생성 출처'} value={panel.source} onChange={e => changeSource(side, e.target.value as Source)}>
          <option value="ALL">전체 출처</option><option value="ORIGINAL">최초 생성</option><option value="REGENERATED">관리자 재생성</option></select></label>
        <label>비교할 버전<select aria-label={label + ' 비교본'} value={panel.id} disabled={!options.some(v => v.versionId !== other.id)} onChange={e => changeSide(side, e.target.value)}>
          {!version && <option value="">선택할 버전 없음</option>}
          {options.map(v => <option value={v.versionId} key={v.versionId} disabled={v.versionId === other.id}>{versionName(v)}{v.versionId === other.id ? ' · 반대쪽 영상' : ''}</option>)}</select></label></div>
        {version ? <>
        {renderPlayer(version, label + ' ' + sceneLabel, version.versionId, side === 'left' ? leftVideo : rightVideo)}
        <div className="tw-pair-foot"><div className="tw-film-name">
          {regenRow && version.versionId === regenSourceId ? regenRow : <strong>{versionName(version)}</strong>}
          {editable && version.selectable && <button {...busyProps(write.isPending)} aria-label={label + ' 영상 ' + confirmText}
            onClick={() => send({ kind: 'select', id: version.versionId, expected: current?.versionId ?? null, count: versions.length })}>{confirmText}</button>}</div>
          <div className="tw-version-facts"><span>{version.source === 'REGENERATED' ? '관리자 재생성' : draft.source ? themeDraftSourceLabels[draft.source] : '최초 생성'}</span>
            <span>{date(version.createdAt)}</span></div></div></>
          : <div className="tw-film-empty"><p>이 출처에서 비교할 다른 영상이 없습니다.</p><button onClick={() => changeSource(side, 'ALL')}>전체 출처 보기</button></div>}
      </section>
    })}</div>
    {!still && !reducedMotion && pairUrls.every(Boolean) &&
      <div className="tw-film-sync"><ThemePairPlayback key={[scene, pair.left.id, pair.right.id, ...pairUrls, pairFailed].join(':')}
        left={leftVideo} right={rightVideo} disabled={pairFailed} linked={settings.linked ?? true}
        setLinked={linked => updateSettings({ linked })} /></div>}
    {!sourceInPair && regenRow ? <div className="tw-film-selection">{current ? '현재 선택본' : '재생성 기준'} {regenRow}</div>
      : current && <div className="tw-film-selection">현재 선택본 <strong>{versionName(current)}</strong></div>}
    </> : <div className="tw-single" aria-label="현재 선택본 미리보기">
      {renderPlayer(media, sceneLabel, scene + (current?.versionId ?? ''))}
      <div className="tw-film-footer"><div>
        {preview && <>{preview.versionId === regenSourceId && regenRow ? regenRow : <strong>{current ? '' : '선택 전 · '}{versionName(preview)}</strong>}
          <small><Clock3 size={13} aria-hidden="true"/>{date(preview.createdAt)}</small></>}
        {preview?.versionId !== regenSourceId && regenRow}
        {versions.length === 1 && <small>생성본 1개 · 두 번째 버전부터 비교 가능</small>}</div>
        <div className="ws-actions">
          {!current && preview?.selectable && editable && <button {...busyProps(write.isPending)} onClick={() =>
            send({kind:'select', id:preview.versionId, expected:null, count:versions.length})}>이 버전 선택</button>}
          {versions.length > 1 && <button onClick={() => open(scene, 'compare')}><ArrowLeftRight size={15} aria-hidden="true"/>버전 비교</button>}
        </div></div>
    </div>}
    </section>
    <QueryFeedback query={query} />
    {failedScene === scene && <><ErrorNotice error={write.error}/>{message && <p role="status">{message}</p>}</>}
    {history && <SceneHistoryList key={scene} history={history} current={current} editable={editable} busy={write.isPending}
      send={send} pair={compare ? pair : undefined} compareWith={compareWith} changeSide={changeSide} settings={settings} updateSettings={updateSettings} />}
  </div>
}

function SceneHistoryList({ history, current, editable, busy, send, pair, compareWith, changeSide, settings, updateSettings }: {
  history: SceneHistory; current?: SceneVersion; editable: boolean; busy: boolean; send: (action: Write) => Promise<boolean>
  pair?: Pair; compareWith: (id: string) => void; changeSide: (side: Side, id: string) => void
  settings: SceneSettings; updateSettings: (patch: SceneSettings) => void
}) {
  const { mode = 'recent', search = '', page = 0 } = settings
  const [editing, setEditing] = useState<SceneVersion | null>(null)
  const [note, setNote] = useState('')
  const [noteError, setNoteError] = useState(false)
  const keyword = search.trim().toLocaleLowerCase('ko')
  const normalize = (text: string) => text.toLocaleLowerCase('ko').replace(/[.\-/\s:]+/g, ' ').trim()
  const words = normalize(keyword).split(' ').filter(Boolean)
  const filtered = history.versions.filter(v => {
    if (mode === 'starred' && !v.starred) return false
    const text = normalize([versionName(v), 'v' + v.number, v.createdAt.slice(0, 10), date(v.createdAt), v.note].join(' '))
    return words.every(word => text.includes(word))
  })
  const pageSize = mode === 'recent' ? 3 : 8
  const index = mode === 'recent' ? 0 : Math.max(0, Math.min(page, Math.ceil(filtered.length / pageSize) - 1))
  const rows = filtered.slice(index * pageSize, (index + 1) * pageSize)
  return <section className="tw-history" aria-label="장면 생성 이력">
    <header className="tw-record-header"><h3>생성 이력</h3>
      {current && <div className="tw-pinned"><span>현재 선택본</span><strong>{versionName(current)}</strong><small>{date(current.createdAt)}</small></div>}
    </header>
    <div className="tw-history-tools"><div className="tw-history-modes" role="group" aria-label="이력 표시 범위">
      {(['recent','starred','all'] as const).map(m => <button key={m} aria-pressed={mode === m} onClick={() => updateSettings({ mode: m, page: 0, search: m === 'recent' ? '' : search })}>
        {{ recent: '최근 3개만 보기', all: `전체 ${history.versions.length}개 보기`, starred: '별표' }[m]}</button>)}</div>
      <input type="search" aria-label="생성 이력 검색" placeholder="버전·메모·날짜 검색" value={search}
        onChange={e => updateSettings({ search: e.target.value, page: 0, mode: mode === 'recent' && e.target.value.trim() ? 'all' : mode })}/></div>
    {(keyword || mode === 'starred') && <p className="tw-record-count" role="status">{keyword ? '검색 결과' : '별표'} {filtered.length}개</p>}
    {!rows.length && <p className="tw-record-count">{keyword ? '검색 결과가 없습니다.' : mode === 'starred' ? '별표를 표시한 버전이 없습니다.' : '표시할 버전이 없습니다.'}</p>}
    <ol className="tw-history-list">{rows.map(v => {
      const side = v.versionId === pair?.left.id ? '왼쪽' : v.versionId === pair?.right.id ? '오른쪽' : null
      return <li key={v.versionId}><div className="tw-history-info">
      <div className="tw-record-name"><span>v{v.number}</span><strong>{versionName(v)}</strong>
        {v.versionId === current?.versionId && <span className="tw-film-badge is-selected">현재 선택</span>}
        {side && <span className="tw-film-badge is-blue">{side} 영상</span>}</div>
      <small>{date(v.createdAt)}</small>
      {v.note && <p>{v.note}</p>}</div><div className="tw-record-actions">
      {editable && v.selectable ? <><button className="tw-record-star" aria-label={versionName(v) + ' 별표'} aria-pressed={v.starred} {...busyProps(busy)} onClick={() => send({kind:'annotation',id:v.versionId,patch:{starred:!v.starred}})}><Star size={17} fill={v.starred ? 'currentColor' : 'none'} aria-hidden="true"/></button>
      <button className="tw-record-note" {...busyProps(busy)} aria-label={versionName(v) + ' 메모 편집'} onClick={() => {setEditing(v);setNote(v.note);setNoteError(false)}}>{v.note ? '메모 수정' : '메모'}</button></> :
        v.starred && <span aria-label="별표">★</span>}
      {pair ? <><button disabled={!!side} aria-label={versionName(v) + ' 왼쪽에 놓기'} onClick={() => changeSide('left', v.versionId)}>왼쪽</button>
        <button disabled={!!side} aria-label={versionName(v) + ' 오른쪽에 놓기'} onClick={() => changeSide('right', v.versionId)}>오른쪽</button></>
        : history.versions.length > 1 && v.versionId !== current?.versionId &&
          <button onClick={() => compareWith(v.versionId)} aria-label={versionName(v) + ' 선택본과 비교'}>비교</button>}
      </div></li>
    })}</ol>
    {mode !== 'recent' && filtered.length > pageSize && <nav className="ws-actions" aria-label="생성 이력 페이지"><button disabled={!index} onClick={() => updateSettings({ page: index - 1 })}>이전</button><span>{index + 1} / {Math.ceil(filtered.length / pageSize)}</span><button disabled={(index + 1) * pageSize >= filtered.length} onClick={() => updateSettings({ page: index + 1 })}>다음</button></nav>}
    {current && <details className="tw-record-sources"><summary>선택본 출처</summary>
      <Link to={'/admin/theme-drafts?' + new URLSearchParams({ draftId: history.rootDraftId, scene: history.scene })}>원본 초안</Link>
      <Link to={'/admin/theme-drafts?' + new URLSearchParams({ draftId: current.versionId, scene: history.scene })}>미디어 출처 초안</Link></details>}
    {editing && editable && <Modal title={versionName(editing) + ' 메모'} onClose={() => {if(!busy)setEditing(null)}}>
      <label className="ws-form">검수 메모<textarea value={note} onChange={e => setNote(e.target.value)} rows={3}/></label>
      <small>{[...note].length} / 160자</small>{noteError && <p role="alert">메모를 저장하지 못했습니다. 이력을 다시 확인해 주세요.</p>}
      <div className="ws-actions"><button {...busyProps(busy)} onClick={() => setEditing(null)}>취소</button>
      <button {...busyProps(busy, [...note].length > 160)} onClick={async () => {
        setNoteError(false)
        if(await send({kind:'annotation',id:editing.versionId,patch:{note}}))setEditing(null)
        else setNoteError(true)
      }}>메모 저장</button></div></Modal>}
  </section>
}
