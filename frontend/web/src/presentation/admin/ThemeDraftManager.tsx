import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { adminRetentionApi as api } from '../../data/admin/retentionApi.ts'
import { useAdminMutation, useAdminQuery } from '../../data/admin/queries.ts'
import { ApiError } from '../../data/apiClient.ts'
import { THINKING_ORDER } from '../../domain/studentLook.ts'
import { inputLabels, thinkingLabels } from '../../domain/classroom.ts'
import type { InputType, ThinkingType } from '../../domain/classroom.ts'
import { THEME_GRADE_LABELS } from '../../domain/admin/retention.ts'
import type { ThemeGrade } from '../../domain/admin/retention.ts'
import { covers } from '../../domain/admin/missionStandards.ts'
import type { AchievementStandard } from '../../domain/admin/missionStandards.ts'
import {
  failureStageLabels,
  sceneLabels,
  themeDraftActions,
  themeDraftLabels,
  themeDraftRequestErrors,
  themeDraftSourceLabels,
} from '../../domain/admin/themeDrafts.ts'
import type { ThemeDraft, ThemeDraftRequest, ThemeSceneName } from '../../domain/admin/themeDrafts.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ThemeMotionPlayer } from '../common/ThemeMotionPlayer.tsx'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import { Badge, Empty, Panel } from './AdminUi.tsx'
import { StandardPicker } from './StandardPicker.tsx'

const POLL_MS = 5_000
const PAGE_SIZE = 20
const nextMonday = () => {
  const day = new Date(Date.now() + 9 * 3600_000)
  day.setUTCDate(day.getUTCDate() + ((8 - day.getUTCDay()) % 7 || 7))
  return day.toISOString().slice(0, 10)
}
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', dateStyle: 'short', timeStyle: 'short' }) : '—')
const actionLabels = { adopt: '채택', discard: '버리기', regenerate: '다시 생성' } as const
type DraftAction = keyof typeof actionLabels

/**
 * 테마 초안 요청·목록·상세(#441, FN-ADM-22, api-spec 2.8). 채택은 게시가 아니다: 미션 5개 `DRAFT`·테마 `DRAFT`를 만들고
 * 테마 편집으로 넘어가 각각 검토·게시한다. 쓰기는 자동 재요청하지 않고, 불가 전이는 서버 409를 그대로 안내한다.
 */
export function ThemeDraftManager() {
  const [params, setParams] = useSearchParams()
  const selected = params.get('draftId') ?? ''
  const [status, setStatus] = useState(''), [source, setSource] = useState(''), [page, setPage] = useState(0)
  const list = useAdminQuery(['theme-drafts', status, source, page], signal => api.themeDrafts({ status, source, page: String(page), size: String(PAGE_SIZE) }, signal),
    true, data => data?.items.some(d => d.status === 'GENERATING') ? POLL_MS : false)
  const rows = list.error ? [] : list.data?.items ?? []
  const total = list.data?.totalElements ?? null
  const hasNext = total === null ? rows.length >= PAGE_SIZE : (page + 1) * PAGE_SIZE < total
  function choose(draftId: string) {
    const next = new URLSearchParams(params); next.set('draftId', draftId); setParams(next)
  }
  return <div className="ad-theme-drafts">
    <p>주간 테마 생성을 요청하고 결과를 확인합니다. 검사 통과는 게시 승인이 아니며, 채택하면 미션 5개와 테마가 작성 중으로 만들어지고 각각 검토·게시합니다.</p>
    <ThemeRequest onRequested={draft => { setPage(0); setStatus(''); setSource(''); choose(draft.draftId) }} />
    <Panel title="테마 초안 목록" action={<button onClick={() => void list.refetch()}>목록 다시 확인</button>}>
      <div className="ad-toolbar">
        <label>상태<select aria-label="테마 초안 상태" value={status} onChange={e => { setStatus(e.target.value); setPage(0) }}>
          <option value="">전체</option>{Object.entries(themeDraftLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select></label>
        <label>출처<select aria-label="테마 초안 출처" value={source} onChange={e => { setSource(e.target.value); setPage(0) }}>
          <option value="">전체</option>{Object.entries(themeDraftSourceLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select></label>
      </div>
      <QueryFeedback query={list} />
      <div className="ad-table-wrap"><table className="ad-table"><thead><tr><th>학년</th><th>적용 주</th><th>출처</th><th>처리 상태</th><th>시도</th><th>요청 시각</th><th>확인</th></tr></thead>
        <tbody>{rows.map(d => <tr key={d.draftId} className={selected === d.draftId ? 'is-selected' : ''}>
          <td>{d.grade ? THEME_GRADE_LABELS[d.grade] : '—'}</td><td>{d.weekStart ?? '—'}</td>
          <td>{d.source ? themeDraftSourceLabels[d.source] : '—'}</td>
          <td><Badge active={d.status === 'READY'}>{themeDraftLabels[d.status]}</Badge></td>
          <td>{d.maxAttempts ? `${d.attempts}/${d.maxAttempts}` : d.attempts}</td><td>{when(d.createdAt)}</td>
          <td><button aria-label={`${d.weekStart ?? d.draftId} ${d.grade ? THEME_GRADE_LABELS[d.grade] : ''} 초안 열기`} onClick={() => choose(d.draftId)}>열기</button></td>
        </tr>)}</tbody></table></div>
      {list.data && !list.error && !rows.length && <Empty>조건에 맞는 테마 초안이 없습니다.</Empty>}
      {list.data && !list.error && <nav className="ws-actions" aria-label="테마 초안 목록 페이지">
        <button disabled={page === 0 || list.isFetching} onClick={() => setPage(page - 1)}>이전 페이지</button><span>{page + 1}쪽</span>
        <button disabled={!hasNext || list.isFetching} onClick={() => setPage(page + 1)}>다음 페이지</button>
      </nav>}
    </Panel>
    {selected ? <ThemeDraftDetail key={selected} draftId={selected} onOpen={choose} />
      : <Panel title="초안 상세"><Empty>목록에서 초안을 열어 주세요.</Empty></Panel>}
  </div>
}

function ThemeDraftDetail({ draftId, onOpen }: { draftId: string; onOpen: (draftId: string) => void }) {
  const navigate = useNavigate()
  const detail = useAdminQuery(['theme-draft', draftId], signal => api.themeDraft(draftId, signal), true,
    data => data?.status === 'GENERATING' ? POLL_MS : false)
  const [still, setStill] = useState(false)
  const [confirm, setConfirm] = useState<DraftAction | null>(null)
  const [notice, setNotice] = useState('')
  const act = useAdminMutation(async (action: DraftAction) => {
    if (action === 'adopt') return { kind: action, themeId: (await api.adoptThemeDraft(draftId)).themeId }
    return { kind: action, draft: await api.themeDraftAction(draftId, action) }
  })
  const d = detail.error ? undefined : detail.data
  const conflict = act.error instanceof ApiError && act.error.problem.status === 409
  const uncertain = act.error && (!(act.error instanceof ApiError) || act.error.problem.status >= 500)
  function run(action: DraftAction) {
    setNotice(''); setConfirm(null)
    void act.mutateAsync(action).then(result => {
      if ('themeId' in result && result.themeId) { navigate('/admin/themes?themeId=' + encodeURIComponent(result.themeId)); return }
      if (result.kind === 'regenerate' && 'draft' in result && result.draft) { setNotice('같은 입력으로 새 초안을 요청했습니다. 새 초안을 엽니다.'); onOpen(result.draft.draftId); return }
      setNotice('초안을 버렸습니다.')
    }).catch(() => {})
  }
  if (!d) return <Panel title="초안 상세"><QueryFeedback query={detail} /></Panel>
  const allowed = themeDraftActions(d.status)
  const theme = d.draft?.theme ?? null
  const sceneOf = (name: ThemeSceneName) => d.scenes.find(s => s.scene === name) ?? null
  const failures = d.checkResults.flatMap(r => r.failures.map(f => ({ attempt: r.attempt, ...f })))
  return <Panel title={theme?.title ? `초안 상세 · ${theme.title}` : '초안 상세'} action={<button disabled={detail.isFetching} onClick={() => void detail.refetch()}>다시 확인</button>}>
    <dl className="ad-draft-meta">
      <dt>처리 상태</dt><dd><Badge active={d.status === 'READY'}>{themeDraftLabels[d.status]}</Badge></dd>
      <dt>학년·적용 주</dt><dd>{d.grade ? THEME_GRADE_LABELS[d.grade] : '—'} · {d.weekStart ?? '—'}</dd>
      <dt>출처</dt><dd>{d.source ? themeDraftSourceLabels[d.source] : '—'}</dd>
      <dt>생성 시도</dt><dd>{d.attempts}{d.maxAttempts ? ` / ${d.maxAttempts}` : ''}{d.failureCode ? ` · 마지막 실패 ${d.failureCode}` : ''}</dd>
      <dt>주제</dt><dd>{d.input.topic ?? '자동'}</dd>
      <dt>생성 버전</dt><dd>{[d.versions.prompt, d.versions.model].filter(Boolean).join(' · ') || '—'}</dd>
      <dt>초안 식별자</dt><dd className="ad-draft-id">{d.draftId}</dd>
    </dl>
    {d.status === 'GENERATING' && <p role="status">생성 중입니다. 5초마다 다시 확인합니다.</p>}
    {d.status === 'ADOPTED' && d.themeId && <p role="note">채택한 초안입니다. <Link to={'/admin/themes?themeId=' + encodeURIComponent(d.themeId)}>만든 테마 편집으로 이동</Link></p>}
    <details className="ad-draft-input"><summary>요청 입력 (유형별 성취기준·입력 방식)</summary>
      <ul>{d.input.missions.map((m, i) => <li key={i}>{m.thinkingType ? thinkingLabels[m.thinkingType] : '유형 미확인'} · {m.inputType ? inputLabels[m.inputType] : '입력 방식 미확인'} · {m.standardCodes.join(', ') || '성취기준 없음'}</li>)}</ul>
    </details>
    {(failures.length > 0 || (d.draft?.warnings.length ?? 0) > 0) && <section className="ad-note" aria-label="실패·경고">
      {failures.length > 0 && <><h3>검사 실패</h3><ul>{failures.map((f, i) => <li key={i}>{f.attempt}회차 · {failureStageLabels[f.stage] ?? f.stage}: {f.reasons.join(' / ') || '사유 없음'}</li>)}</ul></>}
      {(d.draft?.warnings.length ?? 0) > 0 && <><h3>경고</h3><ul>{d.draft!.warnings.map((w, i) => <li key={i}>{failureStageLabels[w.stage] ?? w.stage}{w.item ? ` · ${w.item}` : ''}: {w.reason}</li>)}</ul></>}
    </section>}
    {d.draft && <>
      <label className="ad-inline"><input type="checkbox" checked={still} onChange={e => setStill(e.target.checked)} />움직임 끄기 (정지 그림만)</label>
      <div className="ad-story">
        {(['INTRO', 'OUTRO'] as const).map(name => {
          const s = sceneOf(name)
          return <section key={name} aria-label={sceneLabels[name]}>
            <h3>{sceneLabels[name]}</h3>
            <ThemeMotionPlayer imageUrl={s?.imageUrl ?? null} videoUrl={s?.videoUrl ?? null} motion={s?.motion} label={sceneLabels[name]} still={still} />
            <p className="ad-story-text">{(name === 'INTRO' ? theme?.intro : theme?.outro) || '이야기 없음'}</p>
          </section>
        })}
      </div>
      {theme && <section aria-label="큰 질문"><h3>큰 질문</h3><p>{theme.bigQuestion || '—'}</p>
        <p>후보: {theme.candidates.join(', ') || '—'} · <strong>정답: {theme.answer || '—'}</strong> (학생에게는 엔딩 뒤에만 보임)</p></section>}
      <h3>요일별 문제</h3>
      <div className="ad-days">
        {(['MON', 'TUE', 'WED', 'THU', 'FRI'] as const).map(day => {
          const m = d.draft!.missions.find(x => x.day === day), plan = theme?.days.find(x => x.day === day)
          const lines = d.draft!.dialogues.find(x => x.day === day)?.lines ?? [], s = sceneOf(day)
          const type = m?.thinkingType ?? plan?.thinkingType ?? null
          return <section key={day} className="ad-day" aria-label={`${sceneLabels[day]} 문제`}>
            <h4>{sceneLabels[day]} · {type ? thinkingLabels[type] : '유형 없음'}</h4>
            <ThemeMotionPlayer imageUrl={s?.imageUrl ?? null} videoUrl={s?.videoUrl ?? null} motion={s?.motion} label={`${sceneLabels[day]} 문제`} still={still} showSpots />
            {m ? <><p><b>{m.title || '제목 없음'}</b></p><p>{m.question || '질문 없음'}</p>{m.guide && <p className="ad-muted">{m.guide}</p>}</> : <p role="note">이 요일 문제가 만들어지지 않았습니다.</p>}
            {lines.length > 0 && <details><summary>문제 전 대화 {lines.length}줄</summary><ul>{lines.map((l, i) => <li key={i}><b>{l.speaker}</b> {l.text}</li>)}</ul></details>}
            {plan?.clue && <p className="ad-muted">단서(문제 마무리 뒤): {plan.clue}{plan.rulesOut.length ? ` · 빠지는 후보 ${plan.rulesOut.join(', ')}` : ''}</p>}
          </section>
        })}
      </div>
    </>}
    {!d.draft && d.status !== 'GENERATING' && <p role="note">생성 결과가 없습니다. 실패 사유를 확인하고 다시 생성해 주세요.</p>}
    {confirm && <div className="ad-note" role="alertdialog" aria-label={`${actionLabels[confirm]} 확인`}>
      <p>{confirm === 'adopt' ? '채택하면 미션 5개와 테마가 작성 중으로 만들어집니다. 게시는 각각 검토한 뒤 따로 합니다. 채택할까요?'
        : confirm === 'discard' ? '이 초안을 버릴까요? 버린 초안은 채택할 수 없습니다.' : '같은 입력으로 새 초안을 요청할까요? 지금 초안은 그대로 남습니다.'}</p>
      <div className="ws-actions"><button onClick={() => setConfirm(null)}>취소</button><button className={confirm === 'discard' ? 'ad-danger' : 'cj-primary'} disabled={act.isPending} onClick={() => run(confirm)}>{actionLabels[confirm]}</button></div>
    </div>}
    <div className="ws-actions">
      {allowed.adopt && <button className="cj-primary" disabled={act.isPending} onClick={() => setConfirm('adopt')}>채택해서 테마 만들기</button>}
      {allowed.regenerate && <button disabled={act.isPending} onClick={() => setConfirm('regenerate')}>다시 생성</button>}
      {allowed.discard && <button className="ad-danger" disabled={act.isPending} onClick={() => setConfirm('discard')}>버리기</button>}
    </div>
    {conflict ? <p role="alert">초안 상태가 바뀌어 처리하지 못했습니다. 다시 확인한 뒤 진행해 주세요.</p> : <ErrorNotice error={act.error} />}
    {uncertain && <p role="note">처리됐을 수 있습니다. 다시 누르기 전에 목록과 상태를 먼저 확인해 주세요.</p>}
    {notice && <p role="status">{notice}</p>}
  </Panel>
}

type Override = { standardCodes: string[]; inputType: InputType | '' }
function ThemeRequest({ onRequested }: { onRequested: (draft: ThemeDraft) => void }) {
  const [grade, setGrade] = useState<ThemeGrade>('G3'), [weekStart, setWeekStart] = useState(nextMonday), [topic, setTopic] = useState('')
  const [overrides, setOverrides] = useState<Partial<Record<ThinkingType, Override>>>({})
  const [known, setKnown] = useState<Record<string, AchievementStandard>>({}), [errors, setErrors] = useState<string[]>([]), [notice, setNotice] = useState('')
  const request = useAdminMutation(api.requestThemeDraft)
  const gradeMin = Number(grade.slice(1)), gradeMax = gradeMin
  const uncertain = request.error && (!(request.error instanceof ApiError) || request.error.problem.status >= 500)
  function toggle(type: ThinkingType, on: boolean) {
    if (on) setOverrides(before => ({ ...before, [type]: { standardCodes: [], inputType: '' } }))
    else setOverrides(before => { const next = { ...before }; delete next[type]; return next })
  }
  function update(type: ThinkingType, value: Partial<Override>) { setOverrides(before => ({ ...before, [type]: { ...before[type]!, ...value } })) }
  return <Panel title="새 테마 초안 요청">
    <form className="ws-form" aria-label="테마 초안 생성 요청" onSubmit={event => {
      event.preventDefault(); setNotice('')
      const entries = Object.entries(overrides) as [ThinkingType, Override][]
      const missing = entries.filter(([, value]) => !value.inputType).map(([type]) => `${thinkingLabels[type]}의 입력 방식을 선택해 주세요.`)
      const missions = entries.map(([thinkingType, value]) => ({ thinkingType, standardCodes: value.standardCodes, inputType: value.inputType as InputType }))
      const body: ThemeDraftRequest = { grade, weekStart, ...(topic.trim() ? { topic: topic.trim() } : {}), ...(missions.length ? { missions } : {}) }
      const outside = missions.flatMap(m => m.standardCodes.filter(code => !known[code] || !covers(known[code], gradeMin, gradeMax)))
      const problems = [...missing, ...themeDraftRequestErrors(body), ...(outside.length ? ['고른 성취기준의 학년군을 확인해 주세요.'] : [])]
      setErrors(problems)
      if (problems.length) return
      void request.mutateAsync(body).then(draft => { setNotice('생성 요청을 접수했습니다. 처리 상태를 확인해 주세요.'); onRequested(draft) }).catch(() => {})
    }}>
      <div className="ad-toolbar">
        <label>학년<select aria-label="생성 학년" value={grade} onChange={e => { setGrade(e.target.value as ThemeGrade); setOverrides({}); setKnown({}); setErrors([]) }}>
          {Object.entries(THEME_GRADE_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select></label>
        <label>적용 주의 월요일<input aria-label="생성 적용 주" type="date" required value={weekStart} onChange={e => setWeekStart(e.target.value)} /></label>
        <label>주제 키워드 (선택)<input aria-label="테마 주제 키워드" value={topic} onChange={e => setTopic(e.target.value)} /></label>
      </div>
      <details><summary>생각 유형별 성취기준·입력 방식 직접 지정</summary>
        <p>직접 지정할 유형만 선택해 주세요. 학년을 바꾸면 기존 선택을 비웁니다.</p>
        {THINKING_ORDER.map(type => <fieldset key={type}>
          <legend><label><input type="checkbox" checked={!!overrides[type]} onChange={e => toggle(type, e.target.checked)} />{thinkingLabels[type]} 직접 지정</label></legend>
          {overrides[type] && <>
            <label>입력 방식<select aria-label={`${thinkingLabels[type]} 입력 방식`} value={overrides[type].inputType} onChange={e => update(type, { inputType: e.target.value as InputType })}>
              <option value="">선택해 주세요</option>{Object.entries(inputLabels).filter(([key]) => key !== 'ESSAY' || gradeMin >= 5).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select></label>
            <StandardPicker key={`${grade}:${type}`} codes={overrides[type].standardCodes} levels={{}} gradeMin={gradeMin} gradeMax={gradeMax} subject="" showLevels={false}
              onChange={(codes, _levels, rows) => { update(type, { standardCodes: codes }); setKnown(before => ({ ...before, ...rows })) }} />
          </>}
        </fieldset>)}
      </details>
      {errors.length > 0 && <ul role="alert">{errors.map(error => <li key={error}>{error}</li>)}</ul>}
      <ErrorNotice error={request.error} />
      {uncertain && <p role="note">요청이 접수됐을 수 있습니다. 새로 요청하기 전에 목록을 먼저 확인해 주세요.</p>}
      {notice && <p role="status">{notice}</p>}
      <div className="ws-actions"><button className="cj-primary" disabled={request.isPending}>{request.isPending ? '요청 중…' : '테마 초안 생성 요청'}</button></div>
    </form>
  </Panel>
}
