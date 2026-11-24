import { useEffect, useState } from 'react'
import { ChevronDown, ImageOff, Sparkles } from 'lucide-react'
import { Link, useLocation, useNavigate } from 'react-router'
import { adminRetentionApi as api } from '../../data/admin/retentionApi.ts'
import { useAdminQuery } from '../../data/admin/queries.ts'
import { THEME_GRADE_LABELS } from '../../domain/admin/retention.ts'
import type { ThemeGrade } from '../../domain/admin/retention.ts'
import { themeDraftLabels } from '../../domain/admin/themeDrafts.ts'
import type { ThemeDraft } from '../../domain/admin/themeDrafts.ts'
import { reviewStageLabels } from '../../domain/admin/themeDraftReviews.ts'
import type { ThemeDraftReviewRow, ThemeReviewStage } from '../../domain/admin/themeDraftReviews.ts'
import { calendarPeriods } from '../../domain/classroom.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { date } from './adminFormatting.ts'
import { ThemeRequest } from './ThemeRequest.tsx'
import { TableScroll } from './AdminUi.tsx'
import { busyProps } from './busyButton.ts'

const PAGE_SIZE = 20
const stageColors: Record<ThemeReviewStage, string> = {
  review: 'amber', pair: 'purple', adopted: 'blue', closed: 'amber', ready: 'blue', published: 'green',
  discarded: 'muted', generating: 'blue', check_failed: 'red', failed: 'red',
}
const sources = { AUTO: '자동 생성', ADMIN: '직접 요청' } as const
type Params = Record<string, string | null>

function monday(value: string | null) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return ''
  const day = new Date(value + 'T00:00:00Z')
  if (!Number.isFinite(day.getTime()) || day.toISOString().slice(0, 10) !== value) return ''
  return calendarPeriods(day).thisWeek.from
}
function weekRange(value: string) {
  const monday = new Date(value + 'T00:00:00Z')
  if (!Number.isFinite(monday.getTime())) return value
  const friday = new Date(monday)
  friday.setUTCDate(monday.getUTCDate() + 4)
  const short = (day: Date) => (day.getUTCMonth() + 1) + '.' + String(day.getUTCDate()).padStart(2, '0')
  return short(monday) + ' – ' + short(friday)
}
function listUrl(params: URLSearchParams, updates: Params) {
  const next = new URLSearchParams(params)
  for (const [key, value] of Object.entries(updates)) {
    if (value) next.set(key, value)
    else next.delete(key)
  }
  return { pathname: '/admin/theme-drafts', search: next.toString() }
}
function rowUrl(row: ThemeDraftReviewRow, params: URLSearchParams) {
  if (row.themeId && (row.stage === 'ready' || row.stage === 'published' || row.stage === 'closed')) {
    const query = new URLSearchParams({ grade: row.grade, weekStart: row.appliedWeek, themeId: row.themeId })
    return { pathname: '/admin/themes', search: query.toString() }
  }
  const scene = row.stage === 'pair' ? row.comparisonScene : null
  return listUrl(params, { draftId: row.draftId, scene, view: scene ? 'compare' : null, request: null, generationId: null })
}
function Thumbnail({ url }: { url: string | null }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null)
  if (url && url !== failedUrl) return <img src={url} alt="" width={49} height={37} onError={() => setFailedUrl(url)}/>
  return <span className="theme-thumb-empty" role="img" aria-label={url ? '대표 그림을 불러올 수 없음' : '대표 그림 없음'}><ImageOff size={17} aria-hidden="true"/></span>
}
function Filter({ name, value, options, onChange }: {
  name: string; value: string; options: [string, string][]; onChange: (value: string) => void
}) {
  return <label className="filter-choice"><select aria-label={name} value={value} onChange={event => onChange(event.target.value)}>
    {options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}
  </select><ChevronDown size={14} aria-hidden="true"/></label>
}

export function ThemeDraftList({ params, change, onRequested }: {
  params: URLSearchParams; change: (update: Params, replace?: boolean) => void; onRequested: (draft: ThemeDraft) => void
}) {
  const location = useLocation(), navigate = useNavigate()
  function openRequest() {
    void navigate(listUrl(params, { request: '1' }), { state: { openedFromReviewList: true } })
  }
  function closeRequest() {
    if (location.state?.openedFromReviewList) void navigate(-1)
    else change({ request: null }, true)
  }
  const grade = (Object.keys(THEME_GRADE_LABELS) as ThemeGrade[]).find(key => key === params.get('grade')) ?? ''
  const source = (Object.keys(sources) as (keyof typeof sources)[]).find(key => key === params.get('source')) ?? ''
  const week = monday(params.get('week')), generatedWeek = week ? '' : monday(params.get('weekStart'))
  const stage = (Object.keys(reviewStageLabels) as ThemeReviewStage[]).find(key => key === params.get('stage')) ?? ''
  const status = (Object.keys(themeDraftLabels) as (keyof typeof themeDraftLabels)[]).find(key => key === params.get('status')) ?? ''
  const comparisonPending = params.get('comparisonPending') === 'true'
  const rawPage = Number(params.get('page')), page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 0
  const archive = stage === 'discarded' || status === 'DISCARDED'
  const filters = { grade, source, week, weekStart: generatedWeek, stage, status, comparisonPending: comparisonPending ? 'true' : '',
    hideDiscarded: archive ? '' : 'true', page: String(page), size: String(PAGE_SIZE) }
  const list = useAdminQuery(['theme-draft-review-list', filters], signal => api.themeDraftReviews(filters, signal),
    true, data => data?.items.some(row => row.status === 'GENERATING') ? 5000 : false)
  const data = list.isError ? undefined : list.data
  const lastPage = data ? Math.max(0, Math.ceil(data.totalElements / PAGE_SIZE) - 1) : null
  useEffect(() => {
    if (lastPage !== null && page > lastPage) change({ page: lastPage ? String(lastPage) : null }, true)
  }, [lastPage, page, change])
  const activeWeek = week || generatedWeek
  const weeks = [...new Set([...(data?.weeks ?? []), ...(activeWeek ? [activeWeek] : [])])].sort()
  const selectedStatus = stage || (comparisonPending ? 'pair' : archive ? 'discarded' : status)
  const statusOptions: [string, string][] = Object.entries(reviewStageLabels)
  if (status && selectedStatus === status) statusOptions.push([status, themeDraftLabels[status]])
  const reset = { grade: null, stage: null, status: null, comparisonPending: null, week: null, weekStart: null, source: null, page: null }
  const title = archive ? '버림 이력' : '주간 테마 목록'
  return <div className="page-pad tw-desk rv-draft-list">
    <header className="page-intro"><div><h1>주간 테마 검수</h1><p>학년과 적용 주를 확인하고 검수할 테마를 선택하세요.</p></div>
      <div className="studio-commands"><Link className="btn" to={listUrl(params, { ...reset, stage: archive ? null : 'discarded', request: null })}>{archive ? '검수 목록' : '버림 이력'}</Link>
        <button type="button" className="btn primary rv-primary" onClick={openRequest}><Sparkles size={17} aria-hidden="true"/>테마 추가 생성 요청</button></div></header>
    <section className="panel shelf" aria-label={title}><div className="shelf-head"><div className="section-title"><h2>{title}</h2>
      {data && <span className="total" aria-live="polite">{data.totalElements}</span>}</div>
      <div className="filters"><Filter name="학년 선택" value={grade} options={[['', '전체 학년'], ...Object.entries(THEME_GRADE_LABELS)]} onChange={value => change({ grade: value, page: null })}/>
        <Filter name="검수 상태 선택" value={selectedStatus} options={[['', '전체 상태'], ...statusOptions]} onChange={value =>
          change({ stage: value, status: null, comparisonPending: null, page: null })}/>
        <Filter name={archive ? '생성 기준 주 선택' : '적용 주 선택'} value={activeWeek} options={[
          ['', archive ? '전체 생성 기준 주' : '전체 적용 주'], ...weeks.map((w): [string,string] => [w, (generatedWeek === w && !archive ? '생성 기준 주 ' : '') + weekRange(w)]),
        ]} onChange={value => change({ week: value, weekStart: null, page: null })}/>
        <Filter name="생성 출처 선택" value={source} options={[['', '전체 출처'], ...Object.entries(sources)]} onChange={value => change({ source: value, page: null })}/>
        {(grade || selectedStatus || activeWeek || source) && <button type="button" className="filter-reset" onClick={() => change(reset)}>초기화</button>}</div></div>
      <QueryFeedback query={list}/>
      <TableScroll label="테마 초안 목록 표" className="scroll-table"><table className="themes-table" aria-label={title}><thead><tr>
        <th scope="col">테마명</th><th scope="col">대상</th><th scope="col">{archive ? '버린 일시' : '적용 주'}</th><th scope="col">출처</th><th scope="col">진행 상태</th>
        <th scope="col"><span className="sr-only">상세 열기</span></th></tr></thead>
        <tbody>{data?.items.map(row => {
          const link = rowUrl(row, params)
          return <tr key={row.draftId}><td><Link className="theme-name" to={link}><Thumbnail url={row.thumbnailUrl}/><strong>{row.title}</strong></Link></td>
            <td>{THEME_GRADE_LABELS[row.grade]}</td><td className="num">{archive ? (row.updatedAt ? date(row.updatedAt) : '기록 없음') :
              <><time dateTime={row.appliedWeek}>{weekRange(row.appliedWeek)}</time>{row.plannedWeek && row.status !== 'ADOPTED' ? ' 편성' : ''}</>}</td>
            <td>{sources[row.source]}</td><td><span className={'tag ' + stageColors[row.stage]}>{reviewStageLabels[row.stage]}</span></td>
            <td><Link className="open-row" to={link} aria-label={row.title + ' 상세 열기'}>열기</Link></td></tr>
        })}</tbody></table></TableScroll>
      {data && !data.items.length && <p className="list-empty">{archive && !grade && !activeWeek && !source ? '아직 버린 초안이 없습니다.' : '조건에 맞는 테마가 없습니다. 필터를 바꿔 보세요.'}</p>}
      {data && (page > 0 || data.totalElements > PAGE_SIZE) && <nav className="rv-list-pagination" aria-label="테마 초안 목록 페이지">
        <button {...busyProps(list.isFetching, page === 0)} onClick={() => change({ page: String(page - 1) })}>이전 페이지</button>
        <span>{page + 1} / {Math.max(1, Math.ceil(data.totalElements / PAGE_SIZE))}</span>
        <button {...busyProps(list.isFetching, (page + 1) * PAGE_SIZE >= data.totalElements)} onClick={() => change({ page: String(page + 1) })}>다음 페이지</button></nav>}
    </section>
    {params.get('request') === '1' && <ThemeRequest initialGrade={grade} initialWeek={activeWeek} onClose={closeRequest} onRequested={onRequested}/>}
  </div>
}
