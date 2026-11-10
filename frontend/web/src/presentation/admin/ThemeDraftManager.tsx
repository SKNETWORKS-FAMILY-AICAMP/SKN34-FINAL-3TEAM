import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
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
import { themeDraftLabels, themeDraftRequestErrors, themeDraftSourceLabels } from '../../domain/admin/themeDrafts.ts'
import type { ThemeDraft, ThemeDraftRequest } from '../../domain/admin/themeDrafts.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import { Badge, Empty, Panel } from './AdminUi.tsx'
import { StandardPicker } from './StandardPicker.tsx'

const POLL_MS = 5_000
const nextMonday = () => {
  const day = new Date(Date.now() + 9 * 3600_000)
  day.setUTCDate(day.getUTCDate() + ((8 - day.getUTCDay()) % 7 || 7))
  return day.toISOString().slice(0, 10)
}

/** #441: 확정된 core 중계 계약으로 요청·상태 확인만 제공한다. #438 상세·상태 전이는 만들지 않는다. */
export function ThemeDraftManager() {
  const [params, setParams] = useSearchParams()
  const selected = params.get('draftId') ?? ''
  const [status, setStatus] = useState(''), [source, setSource] = useState(''), [page, setPage] = useState(0)
  const list = useAdminQuery(['theme-drafts', status, source, page], signal => api.themeDrafts({ status, source, page: String(page), size: '20' }, signal),
    true, data => data?.items.some(d => d.status === 'GENERATING') ? POLL_MS : false)
  const rows = list.error ? [] : list.data?.items ?? []
  const detail = useAdminQuery(['theme-draft', selected], signal => api.themeDraft(selected, signal), !!selected,
    data => data?.status === 'GENERATING' ? POLL_MS : false)
  function choose(draft: ThemeDraft) {
    const next = new URLSearchParams(params); next.set('draftId', draft.draftId); setParams(next)
  }
  return <div className="ad-theme-drafts">
    <p>주간 테마 생성을 요청하고 처리 상태를 확인합니다. 검사 통과는 게시 승인이 아니며, 내용을 확인한 뒤 미션과 테마를 각각 검토·게시합니다.</p>
    <ThemeRequest onRequested={draft => { setPage(0); setStatus(''); setSource(''); choose(draft) }} />
    <div className="ad-split">
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
        <div className="ad-table-wrap"><table className="ad-table"><thead><tr><th>초안 식별자</th><th>처리 상태</th><th>확인</th></tr></thead>
          <tbody>{rows.map(d => <tr key={d.draftId} className={selected === d.draftId ? 'is-selected' : ''}>
            <td className="ad-draft-id">{d.draftId}</td><td><Badge active={d.status === 'READY'}>{themeDraftLabels[d.status]}</Badge></td>
            <td><button aria-label={`${d.draftId} 상태 확인`} onClick={() => choose(d)}>열기</button></td>
          </tr>)}</tbody></table></div>
        {list.data && !list.error && !rows.length && <Empty>조건에 맞는 테마 초안이 없습니다.</Empty>}
        {list.data && !list.error && <nav className="ws-actions" aria-label="테마 초안 목록 페이지">
          <button disabled={page === 0 || list.isFetching} onClick={() => setPage(page - 1)}>이전 페이지</button><span>{page + 1}쪽</span>
          <button disabled={rows.length < 20 || list.isFetching} onClick={() => setPage(page + 1)}>다음 페이지</button>
        </nav>}
      </Panel>
      <Panel title="선택한 초안 상태">
        {!selected ? <Empty>목록에서 초안을 선택해 주세요.</Empty> : <>
          <QueryFeedback query={detail} />
          {detail.data && !detail.error && <><dl><dt>초안 식별자</dt><dd className="ad-draft-id">{detail.data.draftId}</dd><dt>처리 상태</dt><dd>{themeDraftLabels[detail.data.status]}</dd></dl>
            <p role="note">초안 내용을 확인할 수 없어 이 화면에서는 채택을 진행할 수 없습니다.</p>
            <button disabled={detail.isFetching} onClick={() => void detail.refetch()}>상태 다시 확인</button></>}
        </>}
        <p><Link to="/admin/themes">주간 테마 관리로 이동</Link></p>
      </Panel>
    </div>
  </div>
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
