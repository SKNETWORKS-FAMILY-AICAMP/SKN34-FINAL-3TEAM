import { useState } from 'react'
import type { KeyboardEvent } from 'react'
import type { AchievementStandard } from '../../domain/admin/missionStandards.ts'
import { bandFor, gradeBands, levelOptions } from '../../domain/admin/missionStandards.ts'
import { adminApi } from '../../data/admin/api.ts'
import { useAdminQuery, useStandardsByCodes } from '../../data/admin/queries.ts'
import { QueryFeedback } from '../common/Workspace.tsx'

/**
 * 성취기준 표에서 고르기·성취기준별 성취수준 단계 (FN 1.5·FN-ADM-21, #356).
 * 표는 읽기 전용, 고른 코드 배열과 {코드: 단계}를 함께 돌려줌. 바깥 form 안에 들어가므로 form을 만들지 않음
 */
export function StandardPicker({ codes, levels, gradeMin, gradeMax, subject, onChange }: {
  codes: string[]
  levels: Record<string, string>
  gradeMin: number
  gradeMax: number
  subject: string
  onChange: (codes: string[], levels: Record<string, string>, rows: Record<string, AchievementStandard>) => void
}) {
  const saved = useStandardsByCodes(codes),
    [picked, setPicked] = useState<Record<string, AchievementStandard>>({}),
    known = { ...picked, ...(saved.error ? {} : saved.data) },
    [draft, setDraft] = useState({ subject, gradeBand: bandFor(gradeMin, gradeMax) as string, q: '' }),
    [filters, setFilters] = useState({ ...draft, page: 0 }),
    search = useAdminQuery(['standards', filters], (signal) =>
      adminApi.standards({ subject: filters.subject.trim(), gradeBand: filters.gradeBand, q: filters.q.trim(), page: String(filters.page), size: '10' }, signal))
  function apply() { setFilters({ ...draft, page: 0 }) }
  function enter(e: KeyboardEvent) { if (e.key === 'Enter') { e.preventDefault(); apply() } }
  function pick(s: AchievementStandard) {
    const rows = { ...known, [s.code]: s }
    setPicked({ ...picked, [s.code]: s })
    onChange([...codes, s.code], levels, rows)
  }
  function remove(code: string) {
    const { [code]: _removed, ...rest } = levels
    onChange(codes.filter((c) => c !== code), rest, known)
  }
  function level(code: string, value: string) {
    const { [code]: _old, ...rest } = levels
    onChange(codes, value ? { ...rest, [code]: value } : rest, known)
  }
  const rows = search.error ? [] : search.data?.items ?? []
  return (
    <fieldset className="ws-form" aria-label="성취기준 고르기">
      <legend>성취기준·성취수준</legend>
      {!codes.length && <p>성취기준 표에서 1개 이상 고르세요.</p>}
      <ul aria-label="고른 성취기준">
        {codes.map((code) => {
          const s = known[code]
          return (
            <li key={code}>
              <strong>{code}</strong>{' '}
              {s ? `${s.gradeBand} · ${s.subject} · ${s.area} · ${s.statement}`
                : saved.isFetching ? '표에서 확인 중' : '성취기준 표에 없는 코드입니다. 빼고 표에서 다시 고르세요.'}
              {s && (
                <label>
                  성취수준 단계
                  <select aria-label={`성취수준 ${code}`} value={levels[code] ?? ''} onChange={(e) => level(code, e.target.value)}>
                    <option value="">고르지 않음</option>
                    {levelOptions(s.levelScale).map((l) => <option key={l} value={l}>{l}</option>)}
                  </select>
                </label>
              )}
              <button type="button" className="cj-secondary" aria-label={`${code} 빼기`} onClick={() => remove(code)}>빼기</button>
            </li>
          )
        })}
      </ul>
      <div className="ws-grid">
        <label>
          교과
          <input aria-label="성취기준 교과" value={draft.subject} onKeyDown={enter} onChange={(e) => setDraft({ ...draft, subject: e.target.value })} />
        </label>
        <label>
          학년군
          <select aria-label="성취기준 학년군" value={draft.gradeBand} onChange={(e) => setDraft({ ...draft, gradeBand: e.target.value })}>
            <option value="">전체</option>
            {Object.keys(gradeBands).map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </label>
        <label>
          코드·문장 검색
          <input aria-label="성취기준 검색어" maxLength={100} value={draft.q} onKeyDown={enter} onChange={(e) => setDraft({ ...draft, q: e.target.value })} />
        </label>
      </div>
      <button type="button" className="cj-secondary" onClick={apply}>성취기준 조회</button>
      <QueryFeedback query={search} />
      {search.data && !search.error && (
        <>
          <div className="ad-table-wrap">
            <table className="ad-table">
              <caption>미션 학년 초{gradeMin}~{gradeMax}이 성취기준 학년군 안이어야 게시할 수 있습니다.</caption>
              <thead><tr><th>고르기</th><th>코드</th><th>학년군·영역</th><th>성취기준</th></tr></thead>
              <tbody>
                {rows.map((s) => (
                  <tr key={s.code}>
                    <td>
                      <button type="button" aria-label={`${s.code} 고르기`} disabled={codes.includes(s.code)} onClick={() => pick(s)}>
                        {codes.includes(s.code) ? '고름' : '고르기'}
                      </button>
                    </td>
                    <td>{s.code}</td>
                    <td>{s.gradeBand}<small>{s.subject} · {s.area}</small></td>
                    <td title={s.statement}>{s.statement}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!rows.length && <p>조건에 맞는 성취기준이 없습니다.</p>}
          <div className="ws-actions" aria-label="성취기준 표 페이지">
            <button type="button" className="cj-secondary" disabled={filters.page <= 0} onClick={() => setFilters({ ...filters, page: filters.page - 1 })}>이전</button>
            <span>{filters.page + 1}쪽 · 총 {search.data.totalElements}개</span>
            <button type="button" className="cj-secondary" disabled={(filters.page + 1) * search.data.size >= search.data.totalElements}
              onClick={() => setFilters({ ...filters, page: filters.page + 1 })}>다음</button>
          </div>
        </>
      )}
    </fieldset>
  )
}
