import { useRef, useState } from 'react'
import { Info } from 'lucide-react'
import { adminRetentionApi as api } from '../../data/admin/retentionApi.ts'
import { useAdminMutation } from '../../data/admin/queries.ts'
import { ApiError } from '../../data/apiClient.ts'
import { THINKING_ORDER } from '../../domain/studentLook.ts'
import { calendarPeriods, inputLabels, thinkingLabels } from '../../domain/classroom.ts'
import type { InputType, ThinkingType } from '../../domain/classroom.ts'
import { THEME_GRADE_LABELS } from '../../domain/admin/retention.ts'
import type { ThemeGrade } from '../../domain/admin/retention.ts'
import { covers } from '../../domain/admin/missionStandards.ts'
import type { AchievementStandard } from '../../domain/admin/missionStandards.ts'
import { themeDraftRequestErrors } from '../../domain/admin/themeDrafts.ts'
import type { ThemeDraft, ThemeDraftRequest } from '../../domain/admin/themeDrafts.ts'
import { ErrorNotice, Modal } from '../shared/ClassroomParts.tsx'
import { StandardPicker } from './StandardPicker.tsx'
import { busyProps } from './busyButton.ts'

const nextMonday = () => {
  const day = new Date(Date.now() + 9 * 3600_000)
  day.setUTCDate(day.getUTCDate() + ((8 - day.getUTCDay()) % 7 || 7))
  return day.toISOString().slice(0, 10)
}

type Override = { standardCodes: string[]; inputType: InputType | '' }
export function ThemeRequest({ initialGrade, initialWeek, onClose, onRequested }: { initialGrade: ThemeGrade | ''; initialWeek: string; onClose: () => void; onRequested: (draft: ThemeDraft) => void }) {
  const thisMonday = calendarPeriods().thisWeek.from
  const [grade, setGrade] = useState(initialGrade), [weekStart, setWeekStart] = useState(initialWeek >= thisMonday ? initialWeek : nextMonday()), [topic, setTopic] = useState('')
  const [overrides, setOverrides] = useState<Partial<Record<ThinkingType, Override>>>({})
  const [known, setKnown] = useState<Record<string, AchievementStandard>>({}), [errors, setErrors] = useState<string[]>([])
  const [fields, setFields] = useState({ grade: '', week: '' })
  const gradeField = useRef<HTMLSelectElement>(null), weekField = useRef<HTMLInputElement>(null)
  const inFlight = useRef(false)
  const request = useAdminMutation(api.requestThemeDraft)
  const gradeMin = Number(grade.slice(1)), gradeMax = gradeMin
  const uncertain = request.error && (!(request.error instanceof ApiError) || request.error.problem.status >= 500)
  function toggle(type: ThinkingType, on: boolean) {
    if (on) setOverrides(before => ({ ...before, [type]: { standardCodes: [], inputType: '' } }))
    else setOverrides(before => { const next = { ...before }; delete next[type]; return next })
  }
  function update(type: ThinkingType, value: Partial<Override>) { setOverrides(before => ({ ...before, [type]: { ...before[type]!, ...value } })) }
  return <Modal title="테마 추가 생성 요청" onClose={() => { if (!inFlight.current) onClose() }}>
    <form className="ws-form rv-request-dialog" aria-label="테마 초안 생성 요청" noValidate onSubmit={event => {
      event.preventDefault()
      if (inFlight.current) return
      let weekError = ''
      if (!weekStart || weekField.current?.validity.badInput) weekError = '적용할 주의 월요일 날짜를 입력해 주세요.'
      else if (new Date(weekStart + 'T00:00:00Z').getUTCDay() !== 1) weekError = '적용 주는 월요일 날짜로 선택해 주세요.'
      else if (weekStart < thisMonday) weekError = '이번 주 또는 이후 주의 월요일을 선택해 주세요.'
      setFields({ grade: grade ? '' : '대상 학년을 선택해 주세요.', week: weekError })
      if (!grade || weekError) {
        ;(grade ? weekField.current : gradeField.current)?.focus()
        return
      }
      const entries = Object.entries(overrides) as [ThinkingType, Override][]
      const missing = entries.filter(([, value]) => !value.inputType).map(([type]) => `${thinkingLabels[type]}의 입력 방식을 선택해 주세요.`)
      const missions = entries.map(([thinkingType, value]) => ({ thinkingType, standardCodes: value.standardCodes, inputType: value.inputType as InputType }))
      const body: ThemeDraftRequest = { grade, weekStart, ...(topic.trim() ? { topic: topic.trim() } : {}), ...(missions.length ? { missions } : {}) }
      const outside = missions.flatMap(m => m.standardCodes.filter(code => !known[code] || !covers(known[code], gradeMin, gradeMax)))
      const problems = [...missing, ...themeDraftRequestErrors(body), ...(outside.length ? ['고른 성취기준의 학년군을 확인해 주세요.'] : [])]
      setErrors(problems)
      if (problems.length) return
      inFlight.current = true
      void request.mutateAsync(body).then(onRequested).catch(() => {}).finally(() => { inFlight.current = false })
    }}>
      <div className="request-fields">
        <label className="request-field">대상 학년 <span>필수</span><select ref={gradeField} data-dialog-initial-focus aria-label="생성 학년" aria-invalid={!!fields.grade} aria-describedby={fields.grade ? 'request-grade-error' : undefined} required value={grade} onChange={e => { setGrade(e.target.value as ThemeGrade | ''); setFields(before => ({ ...before, grade: '' })); setOverrides({}); setKnown({}); setErrors([]) }}>
          <option value="">학년 선택</option>
          {Object.keys(THEME_GRADE_LABELS).map(key => <option key={key} value={key}>초등 {key.slice(1)}학년</option>)}
        </select></label>
        {fields.grade && <p className="request-field-error" id="request-grade-error" role="alert">{fields.grade}</p>}
        <label className="request-field">적용 주 <span>필수</span><input ref={weekField} aria-label="생성 적용 주" aria-invalid={!!fields.week} aria-describedby={fields.week ? 'request-week-error request-week-hint' : 'request-week-hint'} type="date" required min={thisMonday} step={7} value={weekStart} onChange={e => { setWeekStart(e.target.value); setFields(before => ({ ...before, week: '' })) }} /></label>
        {fields.week && <p className="request-field-error" id="request-week-error" role="alert">{fields.week}</p>}
        <p className="request-hint" id="request-week-hint">이번 주 또는 이후 주의 월요일을 선택해 주세요.</p>
        <label className="request-field">주제 키워드 <span>선택</span><input aria-label="테마 주제 키워드" maxLength={100} placeholder="예: 달빛 숲의 보물 지도" value={topic} onChange={e => setTopic(e.target.value)} /></label>
        <div className="request-topic-meta"><small>최대 100자</small><span>{topic.trim().length}/100</span></div>
      </div>
      <details><summary>생각 유형별 성취기준·입력 방식 직접 지정</summary>
        <p>직접 지정할 유형만 선택해 주세요. 학년을 바꾸면 기존 선택을 비웁니다.</p>
        {THINKING_ORDER.map(type => <fieldset key={type} disabled={!grade}>
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
      <p className="request-preview"><Info size={17} aria-hidden="true"/>요청한 학년과 적용 주로 테마 영상과 요일별 미션을 생성합니다.</p>
      <footer className="request-actions"><button type="button" className="btn ghost" {...busyProps(request.isPending)} onClick={onClose}>취소</button>
        <button type="submit" className="btn primary cj-primary" {...busyProps(request.isPending)}>{request.isPending ? '요청 중…' : '검수용 초안 만들기'}</button></footer>
    </form>
  </Modal>
}
