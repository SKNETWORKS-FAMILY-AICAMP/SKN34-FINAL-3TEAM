import { useState } from 'react'
import { adminRetentionApi as api } from '../../data/admin/retentionApi.ts'
import { useAdminMutation } from '../../data/admin/queries.ts'
import { ApiError } from '../../data/apiClient.ts'
import { THINKING_ORDER } from '../../domain/studentLook.ts'
import { inputLabels, thinkingLabels } from '../../domain/classroom.ts'
import type { InputType, ThinkingType } from '../../domain/classroom.ts'
import { THEME_GRADE_LABELS } from '../../domain/admin/retention.ts'
import type { ThemeGrade } from '../../domain/admin/retention.ts'
import { covers } from '../../domain/admin/missionStandards.ts'
import type { AchievementStandard } from '../../domain/admin/missionStandards.ts'
import { themeDraftRequestErrors } from '../../domain/admin/themeDrafts.ts'
import type { ThemeDraft, ThemeDraftRequest } from '../../domain/admin/themeDrafts.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import { StandardPicker } from './StandardPicker.tsx'

const nextMonday = () => {
  const day = new Date(Date.now() + 9 * 3600_000)
  day.setUTCDate(day.getUTCDate() + ((8 - day.getUTCDay()) % 7 || 7))
  return day.toISOString().slice(0, 10)
}

type Override = { standardCodes: string[]; inputType: InputType | '' }
export function ThemeRequest({ initialGrade, initialWeek, expanded, onRequested }: { initialGrade: ThemeGrade; initialWeek: string; expanded: boolean; onRequested: (draft: ThemeDraft) => void }) {
  const [open, setOpen] = useState(expanded)
  const [grade, setGrade] = useState<ThemeGrade>(initialGrade), [weekStart, setWeekStart] = useState(initialWeek || nextMonday()), [topic, setTopic] = useState('')
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
  return <details className="ad-request-panel" open={open} onToggle={e => setOpen(e.currentTarget.open)}><summary>새 테마 초안 요청</summary><div>
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
        <label>주제 키워드 (선택)<input aria-label="테마 주제 키워드" maxLength={100} value={topic} onChange={e => setTopic(e.target.value)} /></label>
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
  </div></details>
}
