import { useRef, useState } from 'react'
import { BookOpen, CalendarDays, Play } from 'lucide-react'
import { Link, useNavigate } from 'react-router'
import { ApiError } from '../../data/apiClient.ts'
import { useAdoptedTheme } from '../../data/admin/themeReviewQueries.ts'
import { adminApi } from '../../data/admin/api.ts'
import { useAdminMutation, useAdminQuery, useStandardsByCodes } from '../../data/admin/queries.ts'
import { adminRetentionApi } from '../../data/admin/retentionApi.ts'
import { missingFieldLabel, missingMissionFields } from '../../domain/admin/operations.ts'
import type { AdminMission, MissionVersion } from '../../domain/admin/operations.ts'
import { THEME_GRADE_LABELS, type AdminWeeklyTheme } from '../../domain/admin/retention.ts'
import { versionName } from '../../domain/admin/sceneVersions.ts'
import { sceneLabels } from '../../domain/admin/themeDrafts.ts'
import type { ThemeDraft, ThemeDraftMission, ThemeSceneName } from '../../domain/admin/themeDrafts.ts'
import { thinkingLabels } from '../../domain/classroom.ts'
import { DAY_LABELS, THEME_DAYS, type ThemeDay } from '../../domain/retention.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import { busyProps } from './busyButton.ts'
import './theme-week-missions.css'

type Props = {
  draft: ThemeDraft
  scene: ThemeSceneName
  detailOpen: boolean
  onOpen: (scene: ThemeSceneName, view: 'scene' | 'compare' | 'mission') => void
  onClose: () => void
  onPublished?: (message: string) => void
}

interface WeekMissionRow {
  day: ThemeDay
  mission?: MissionVersion | ThemeDraftMission
  linked?: AdminMission
  status: string
  title: string
}

const themeEditable = (theme?: AdminWeeklyTheme) => !!theme && !theme.weekLocked && (theme.status === 'DRAFT' || theme.status === 'UNPUBLISHED')

export function ThemeWeekMissions({ draft, scene, detailOpen, onOpen, onClose, onPublished }: Props) {
  const themeId = draft.themeId
  const adopted = useAdoptedTheme(themeId)
  const [notice, setNotice] = useState('')
  const live = adopted.error ? undefined : adopted.data?.missions
  const editable = !draft.weekLocked && draft.status === 'ADOPTED' && !adopted.error && themeEditable(adopted.data?.theme)
  const rows: WeekMissionRow[] = THEME_DAYS.map(day => {
    const linked = live?.find(row => row.day === day)?.mission
    const mission = linked
      ? linked.versions.find(v => v.version === linked.currentVersion)
      : draft.draft?.missions.find(m => m.day === day)
    const status = linked ? (linked.status === 'PUBLISHED' ? '게시 완료' : '검토 대기') : themeId
      ? (adopted.isPending ? '조회 중' : '상태 미확인') : draft.status === 'DISCARDED' ? '버림' : '채택 전'
    return { day, mission, linked, status, title: mission?.title || (linked ? '미션 버전 확인 필요' : '생성된 미션 없음') }
  })
  const active = rows.find(row => row.day === scene)
  const published = adopted.data?.published ?? 0
  return <>
    {notice && <p role="status">{notice}</p>}
    <section className="tw-day-missions" aria-label="요일별 미션">
      <header><div><small><BookOpen size={15} aria-hidden="true" />미션 검토</small><h2>요일별 미션</h2></div>
        {(!themeId || live) && <span className="tw-day-badge">{published} / {THEME_DAYS.length} 게시</span>}</header>
      {themeId && <QueryFeedback query={adopted} />}
      <ul>{rows.map(row => <li key={row.day}>
        <span aria-hidden="true" className="tw-day-token">{DAY_LABELS[row.day]}</span>
        <div className="tw-day-title"><strong>{row.title}</strong><small>{sceneLabels[row.day]} 미션</small></div>
        <span className="tw-day-badge" data-published={row.linked?.status === 'PUBLISHED'}>{row.status}</span>
        <button type="button" disabled={!row.mission} onClick={() => onOpen(row.day, 'mission')}>{editable && row.linked && row.linked.status !== 'PUBLISHED' ? '검토하기' : '내용 보기'}</button>
      </li>)}</ul>
    </section>
    {detailOpen && active && <MissionDialog key={active.day} draft={draft} active={active} editable={editable && active.linked?.status !== 'PUBLISHED'}
      onOpen={onOpen} onClose={onClose} refresh={() => adopted.refetch()}
      onPublished={() => { (onPublished ?? setNotice)(sceneLabels[scene] + ' 미션을 게시했습니다.'); onClose() }} />}
  </>
}

function MissionDialog({ draft, active, editable, refresh, onOpen, onClose, onPublished }: {
  draft: ThemeDraft; active: WeekMissionRow; editable: boolean; refresh: () => Promise<unknown>
  onOpen: Props['onOpen']; onClose: () => void; onPublished: () => void
}) {
  const scene = active.day, themeId = draft.themeId, linked = active.linked
  const history = useAdminQuery(['theme-scene-history', draft.draftId, scene], signal => adminRetentionApi.sceneVersions(draft.draftId, scene, signal))
  const sceneHistory = history.error ? undefined : history.data
  const selected = sceneHistory?.versions.find(v => v.versionId === sceneHistory.selectedVersionId)
  const lines = draft.draft?.dialogues.find(d => d.day === scene)?.lines ?? []
  const plan = draft.draft?.theme?.days.find(p => p.day === scene)
  const current = linked?.versions.find(v => v.version === linked.currentVersion)
  const standards = useStandardsByCodes(editable ? current?.achievementStandards ?? [] : [])
  const table = standards.error || standards.isFetching ? undefined : standards.data ?? {}
  const fields = linked ? missingMissionFields(linked, table).filter(f => f !== 'review') : []
  const [confirmed, setConfirmed] = useState<string | null>(null)
  const running = useRef(false)
  const versionKey = linked ? `${linked.missionId}:${linked.currentVersion}:${linked.currentRubricVersion}` : null
  async function approveAndPublish(shown: AdminMission) {
    const pair = { missionVersion: shown.currentVersion, rubricVersion: shown.currentRubricVersion }
    const checkVersion = (m: AdminMission) => {
      if (m.missionId !== shown.missionId || m.currentVersion !== pair.missionVersion || m.currentRubricVersion !== pair.rubricVersion)
        throw new Error('미션 또는 기준표 버전이 바뀌었습니다. 최신 내용을 다시 확인해 주세요.')
    }
    async function readCurrent() {
      const [theme, mission] = await Promise.all([adminRetentionApi.theme(themeId!), adminApi.mission(shown.missionId)])
      if (!themeEditable(theme) || !theme.days.some(day => day.day === scene && day.missionId === shown.missionId))
        throw new Error('테마 편성 또는 게시 상태가 바뀌었습니다. 현재 상태를 확인해 주세요.')
      checkVersion(mission)
      return mission
    }
    let m = await readCurrent()
    if (m.status !== shown.status || m.reviews.length !== shown.reviews.length)
      throw new Error('미션 검토 상태가 바뀌었습니다. 현재 내용을 다시 확인해 주세요.')
    const missing = missingMissionFields(m, table).filter(code => code !== 'review')
    if (missing.length) throw new Error('게시 전 확인할 항목 · ' + missing.map(missingFieldLabel).join(', '))
    if (m.status === 'DRAFT' || m.status === 'UNPUBLISHED') {
      m = await adminApi.action(m.missionId, 'review-request', pair)
      checkVersion(m)
    }
    if (m.status !== 'REVIEW_REQUIRED') throw new Error('검토 요청된 미션만 승인할 수 있습니다. 현재 상태를 확인해 주세요.')
    if (missingMissionFields(m, table).includes('review')) {
      m = await adminApi.action(m.missionId, 'review', { ...pair, result: 'APPROVED', comment: '' })
      checkVersion(m)
    }
    m = await readCurrent()
    const blocking = missingMissionFields(m, table)
    if (m.status !== 'REVIEW_REQUIRED' || blocking.length) throw new Error('게시 조건을 다시 확인해 주세요.' + (blocking.length ? ' ' + blocking.map(missingFieldLabel).join(', ') : ''))
    const published = await adminApi.action(m.missionId, 'publish')
    if (published.status !== 'PUBLISHED' || published.publishedVersion !== pair.missionVersion || published.publishedRubricVersion !== pair.rubricVersion)
      throw new Error('게시 응답의 미션·기준표 버전이 다릅니다. 현재 게시 상태를 확인해 주세요.')
  }
  const submit = useAdminMutation(async (shown: AdminMission) => {
    try { await approveAndPublish(shown) }
    catch (error) { await refresh(); throw error }
  })
  function publish() {
    if (running.current || !editable || !linked || !versionKey || confirmed !== versionKey || fields.length || standards.isFetching) return
    running.current = true
    setConfirmed(null)
    void submit.mutateAsync(linked).then(onPublished).catch(() => {}).finally(() => { running.current = false })
  }
  const actionError = submit.error instanceof ApiError && submit.error.problem.missingFields
    ? new ApiError({ ...submit.error.problem, missingFields: submit.error.problem.missingFields.map(missingFieldLabel) }) : submit.error
  const publishBusy = submit.isPending || standards.isFetching
  const needsConfirmation = !confirmed || confirmed !== versionKey || fields.length > 0
  return <Modal title={active.title} onClose={() => { if (!running.current) onClose() }}>
      <div className="tw-day-dialog">
        <div className="tw-day-meta"><strong>{sceneLabels[scene]} 미션 {editable && linked ? '검토' : '내용'}</strong>
          {draft.grade && <span className="tw-day-badge">{THEME_GRADE_LABELS[draft.grade]}</span>}
          {active.mission?.thinkingType && <span className="tw-day-badge">{thinkingLabels[active.mission.thinkingType]}</span>}
          <span className="tw-day-badge">{active.status}</span></div>
        <section className="tw-day-question"><h3>학생에게 보일 질문</h3><p>{active.mission?.question || '생성된 질문이 없습니다.'}</p></section>
        {active.mission?.guide && <section><h3>활동 안내</h3><p>{active.mission.guide}</p></section>}
        <button type="button" {...busyProps(submit.isPending)} className="tw-day-scene-link" aria-label={sceneLabels[scene] + ' 장면 보기'} onClick={() => onOpen(scene, 'scene')}>
          {selected?.imageUrl && <img alt="" src={selected.imageUrl} />}
          <span><strong>{sceneLabels[scene]} 장면 보기</strong>{selected && <small>현재 선택본 · {versionName(selected)}</small>}</span>
          <Play size={18} aria-hidden="true" /></button>
        <QueryFeedback query={history} />
        {lines.length > 0 && <details><summary>문제 전 대화</summary><ul>{lines.map((line, i) =>
          <li key={i}><b>{line.speaker}</b> {line.text}</li>)}</ul></details>}
        {plan?.clue && <details><summary>문제 마무리 뒤 단서</summary><p>{plan.clue}</p>
          {plan.rulesOut.length > 0 && <p>빠지는 후보 · {plan.rulesOut.join(', ')}</p>}</details>}
        {editable && linked && <section className="tw-day-approval"><p>미션 v{linked.currentVersion} · 기준표 {linked.currentRubricVersion ? 'v' + linked.currentRubricVersion : '미등록'}</p>
          {fields.length > 0 && <div><h3>게시 전 확인할 항목</h3><ul aria-label="게시 전 확인">{fields.map(code => <li key={code}>{missingFieldLabel(code)}</li>)}</ul></div>}
          <label><input type="checkbox" checked={confirmed !== null && confirmed === versionKey} disabled={submit.isPending || fields.length > 0}
            onChange={e => setConfirmed(e.target.checked ? versionKey : null)} /> 학생에게 보일 내용을 확인했습니다.</label></section>}
        <ErrorNotice error={actionError} />
        <footer><button type="button" {...busyProps(submit.isPending)} onClick={onClose}>닫기</button>
          {(sceneHistory?.versions.length ?? 0) > 1 && <button type="button" {...busyProps(submit.isPending)} onClick={() => onOpen(scene, 'compare')}>이 장면 비교 보기</button>}
          {editable && linked && themeId && !submit.isPending && <Link to={'/admin/missions?' + new URLSearchParams({ missionId: linked.missionId, themeId, themeDay: active.day })}>미션 검토·게시 화면</Link>}
          {editable && linked && <button className="cj-primary" {...busyProps(publishBusy, !publishBusy && needsConfirmation)} onClick={publish}>이 미션 승인·게시</button>}
        </footer>
      </div>
    </Modal>
}

export function ThemeAdoptedFooter({ draft }: { draft: ThemeDraft }) {
  const navigate = useNavigate()
  const adopted = useAdoptedTheme(draft.themeId)
  const [confirmVersion, setConfirmVersion] = useState<number | null>(null)
  const review = useAdminMutation(async (expectedVersion: number) => {
    const result = await adminRetentionApi.themeAction(draft.themeId!, 'review-request', { expectedVersion })
    if (result.themeId !== draft.themeId || result.status !== 'REVIEW_REQUIRED' || !result.grade || !result.weekStart)
      throw new Error('검토 요청 결과의 테마와 적용 주를 확인하지 못했습니다. 테마 상태를 다시 확인해 주세요.')
    return result
  })
  const data = adopted.error ? undefined : adopted.data
  if (!draft.themeId) return <p role="alert">채택된 테마의 식별자를 확인할 수 없습니다.</p>
  const editor = '/admin/themes?' + new URLSearchParams({ themeId: draft.themeId })
  if (!data) return <><QueryFeedback query={adopted} />{adopted.isError && <Link to={editor}>채택한 테마 열기</Link>}</>
  const { theme, published } = data
  const allPublished = published === THEME_DAYS.length
  const board = '/admin/themes?' + new URLSearchParams({ grade: theme.grade, weekStart: theme.weekStart })
  const live = theme.status === 'PUBLISHED'
  const locked = (theme.weekLocked || draft.weekLocked) && !live
  const waiting = theme.status === 'REVIEW_REQUIRED'
  const headline = live ? '학생에게 공개된 주간 테마' : locked ? '이 주차는 최종 게시되었습니다.' : waiting ? '최종 게시할 수 있습니다.'
    : `미션 ${published} / ${THEME_DAYS.length}개 게시 완료`
  const canRequest = allPublished && (theme.status === 'DRAFT' || theme.status === 'UNPUBLISHED') && theme.version != null
  return <>
    <footer className="rv-decision"><div>{live ? <span className="tw-day-badge" data-published="true">게시 완료</span>
      : locked ? <CalendarDays size={21} aria-hidden="true" /> : waiting ? <span className="tw-day-badge">검토 요청 완료</span> : <BookOpen size={21} aria-hidden="true" />}
      <span><strong>{headline}</strong>{!live && !waiting && !locked && <small>{allPublished ? '모든 미션을 게시했습니다. 테마 검토를 요청할 수 있습니다.' : '요일별 미션을 확인한 뒤 각각 승인·게시하세요.'}</small>}</span></div>
      <div className="ws-actions">{!locked && themeEditable(theme) && <Link className="tw-day-board-link" to={editor}>채택한 테마 편집</Link>}
        {live ? <Link className="tw-day-board-link" to={editor}>게시 내용 보기</Link>
        : locked ? <Link className="tw-day-board-link" to={board}>주차별 편성·게시 보기</Link>
        : waiting ? <Link className="tw-day-board-link is-primary" to={board}>주차별 편성·게시로</Link>
        : <button className="rv-primary" {...busyProps(adopted.isFetching || review.isPending, !canRequest)}
          onClick={() => { review.reset(); setConfirmVersion(theme.version!) }}>테마 검토 요청</button>}</div>
    </footer>
    {theme.version == null && !live && !locked && !waiting && <p role="alert">검토할 테마 버전을 확인할 수 없습니다.</p>}
    <ErrorNotice error={review.error} />
    {confirmVersion !== null && <Modal title="테마 검토를 요청할까요?" onClose={() => { if (!review.isPending) setConfirmVersion(null) }}>
      <p>{theme.title} · {THEME_GRADE_LABELS[theme.grade]} · {theme.weekStart} · v{confirmVersion}</p>
      <p>요일별 미션을 모두 게시했습니다. 요청 후 편성표에서 최종 게시할 수 있습니다.</p>
      <div className="ws-actions"><button {...busyProps(review.isPending)} onClick={() => setConfirmVersion(null)}>취소</button>
        <button className="cj-primary" {...busyProps(review.isPending, !canRequest || locked || theme.version !== confirmVersion)}
          onClick={() => void review.mutateAsync(confirmVersion).then(updated => {
            setConfirmVersion(null)
            navigate('/admin/themes?' + new URLSearchParams({ grade: updated.grade, weekStart: updated.weekStart }))
          }).catch((err: unknown) => {
            setConfirmVersion(null)
            if (err instanceof ApiError && err.problem.status === 409) void adopted.refetch()
          })}>검토 요청</button></div>
    </Modal>}
  </>
}
