import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Search, ChevronLeft, ChevronRight } from 'lucide-react'
import type { Scope } from '../../domain/parent.ts'
import { validPeriod } from '../../domain/parent.ts'
import { thinkingLabels } from '../../domain/classroom.ts'
import { parentApi } from '../../data/parent/api.ts'
import { useParentQuery } from '../../data/parent/queries.ts'
import { QueryFeedback } from '../common/Workspace.tsx'
import { ThinkingIcon } from './ThinkingIcon.tsx'

const kstDay = (iso: string) => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(iso))

export function ActivityExplorer({ scope, initialType, onOpen }: { scope: Scope; initialType: string; onOpen: (id: string, scope: Scope) => void }) {
  const [period, setPeriod] = useState(scope)
  const [type, setType] = useState(initialType), [search, setSearch] = useState(''), [page, setPage] = useState(0)
  const [popup, setPopup] = useState<'date' | 'type' | null>(null)
  const host = useRef<HTMLDivElement>(null)
  const query = useParentQuery(['explorer', period], async signal => {
    const first = await parentApi.records(period, signal)
    if (['FAILED', 'PROCESSING'].includes(first.state)) throw new Error('활동 기록을 불러오지 못했습니다.')
    const records = [...first.items]
    for (let n = 1; n * first.size < first.totalElements; n++) {
      const next = await parentApi.records(period, signal, n)
      if (['FAILED', 'PROCESSING'].includes(next.state)) throw new Error('일부 활동 기록을 불러오지 못했습니다.')
      records.push(...next.items)
    }
    return records.map(a => ({ id: a.attemptId, title: a.mission.title, type: a.mission.thinkingType,
      date: a.answers.length ? kstDay([...a.answers].sort((x, y) => x.version - y.version)[0].submittedAt) : '' }))
  })
  useEffect(() => {
    if (!popup) return
    const click = (event: PointerEvent) => { if (!(event.target instanceof Element) || !event.target.closest('.pd-column-filter')) setPopup(null) }
    const key = (event: KeyboardEvent) => { if (event.key === 'Escape') { event.stopImmediatePropagation(); setPopup(null); host.current?.querySelector<HTMLButtonElement>(`[data-filter="${popup}"]`)?.focus() } }
    document.addEventListener('pointerdown', click); document.addEventListener('keydown', key, true)
    return () => { document.removeEventListener('pointerdown', click); document.removeEventListener('keydown', key, true) }
  }, [popup])
  // Keep the picker in the top layer so the scrollable table cannot clip it.
  useLayoutEffect(() => {
    if (!popup) return
    const trigger = host.current?.querySelector<HTMLButtonElement>(`[data-filter="${popup}"]`)
    const box = host.current?.querySelector<HTMLElement>('.pd-column-popover')
    if (!trigger || !box) return
    box.showPopover()
    const position = () => {
      const rect = trigger.getBoundingClientRect()
      box.style.maxHeight = `${window.innerHeight - 24}px`
      box.style.left = `${Math.max(12, Math.min(rect.left, window.innerWidth - box.offsetWidth - 12))}px`
      const below = rect.bottom + 8
      box.style.top = `${Math.max(12, Math.min(below, window.innerHeight - box.offsetHeight - 12))}px`
    }
    position()
    window.addEventListener('resize', position)
    document.addEventListener('scroll', position, true)
    return () => { box.hidePopover(); window.removeEventListener('resize', position); document.removeEventListener('scroll', position, true) }
  }, [popup])
  const rows = (query.data ?? []).filter(r => (!type || r.type === type) && r.title.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()))
  const currentPage = Math.min(page, Math.max(0, Math.ceil(rows.length / 10) - 1))
  return <div ref={host} className="pd-activity-explorer">
    <header className="pd-explorer-heading"><div><h2>생각 활동</h2><p>활동별 기록과 답변을 확인하세요.</p></div>
      <div className="pd-activity-search"><span>활동</span><Search size={16} aria-hidden="true" /><input aria-label="활동 검색" placeholder="활동명 검색" value={search} onChange={e => { setSearch(e.target.value); setPage(0) }} /></div>
    </header>
    <div className="pd-filter-summary"><span>{period.from} — {period.to}</span><span>{type ? thinkingLabels[type as keyof typeof thinkingLabels] : '전체 유형'}</span><span aria-live="polite">{query.isPending ? '불러오는 중' : `${rows.length}개 활동`}</span>{(search || type) && <button type="button" className="pd-reset-filter" onClick={() => { setSearch(''); setType(''); setPage(0) }}>검색·유형 초기화</button>}</div>
    <QueryFeedback query={query} />
    <div className="pd-table-scroll" role="region" aria-label="생각 활동 목록" tabIndex={0}><table className="pd-explorer-table pd-activity-table"><thead><tr><th>번호</th><th>활동</th>
      <th><div className="pd-column-filter">유형 <button type="button" data-filter="type" aria-label="유형 필터" aria-expanded={popup === 'type'} onClick={() => setPopup(popup === 'type' ? null : 'type')}>▾</button>
        {popup === 'type' && <div popover="manual" className="pd-column-popover pd-type-options" role="group" aria-label="유형 선택">{[['', '전체'], ...Object.entries(thinkingLabels)].map(([value, label]) => <button key={value} type="button" aria-pressed={type === value} onClick={() => { setType(value); setPage(0); setPopup(null) }}>{label}</button>)}</div>}
      </div></th>
      <th><div className="pd-column-filter">날짜 <button type="button" data-filter="date" aria-label="날짜 필터" aria-expanded={popup === 'date'} onClick={() => setPopup(popup === 'date' ? null : 'date')}>▾</button>
        {popup === 'date' && <DateFilter initial={period} onCancel={() => setPopup(null)} onApply={range => { setPeriod({ ...scope, ...range }); setPage(0); setPopup(null) }} />}
      </div></th><th>원문</th></tr></thead><tbody>
      {!query.error && rows.slice(currentPage * 10, currentPage * 10 + 10).map((r, i) => <tr key={r.id}><td>{String(currentPage * 10 + i + 1).padStart(2, '0')}</td><td>{r.title}</td><td><span className="pd-explorer-type" data-thinking={r.type}><ThinkingIcon type={r.type} />{thinkingLabels[r.type]}</span></td><td className="pd-date-cell" title="최초 답변 제출일 · 한국 시간">{r.date ? r.date.slice(2) : '—'}</td><td><button type="button" onClick={() => onOpen(r.id, period)}>원문 보기 ↗</button></td></tr>)}
    </tbody></table></div>
    {!query.isPending && !query.error && !rows.length && <p>조건에 맞는 활동이 없습니다.</p>}
    <nav className="pd-explorer-pagination" aria-label="생각 활동 페이지"><span>{rows.length ? currentPage * 10 + 1 : 0}–{Math.min(rows.length, (currentPage + 1) * 10)} / {rows.length}</span><button type="button" disabled={!currentPage} onClick={() => setPage(currentPage - 1)}>이전</button><span>{currentPage + 1}</span><button type="button" disabled={(currentPage + 1) * 10 >= rows.length} onClick={() => setPage(currentPage + 1)}>다음</button></nav>
    <p className="pd-date-note">날짜는 최초 답변 제출일입니다. 선택 기간에 답변한 활동을 조회합니다.</p>
  </div>
}

export function DateFilter({ initial, onApply, onCancel, embedded = false, week = false }: { embedded?: boolean; week?: boolean; initial: { from: string; to: string }; onApply: (range: { from: string; to: string }) => void; onCancel: () => void }) {
  const [range, setRange] = useState(initial), [mode, setMode] = useState<'day' | 'range'>('range'), [selectEnd, setSelectEnd] = useState(false)
  const [month, setMonth] = useState(initial.from.slice(0, 7)), [error, setError] = useState('')
  const startInput = useRef<HTMLInputElement>(null), endInput = useRef<HTMLInputElement>(null)
  const startInvalid = !validPeriod({ from: range.from, to: range.from })
  const [year, number] = month.split('-').map(Number)
  const weekday = new Date(Date.UTC(year, number - 1, 1)).getUTCDay()
  const offset = week ? (weekday + 6) % 7 : weekday
  const weekdays = week ? ['월','화','수','목','금','토','일'] : ['일','월','화','수','목','금','토']
  const days = new Date(Date.UTC(year, number, 0)).getUTCDate()
  const move = (delta: number) => { const d = new Date(Date.UTC(year, number - 1 + delta, 1)); setMonth(d.toISOString().slice(0, 7)) }
  const pick = (day: string) => {
    setError('')
    if (week) { const d = new Date(day + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() - (d.getUTCDay()+6)%7); const from=d.toISOString().slice(0,10); d.setUTCDate(d.getUTCDate()+6); setRange({from,to:d.toISOString().slice(0,10)}) }
    else if (mode === 'day') setRange({ from: day, to: day })
    else if (!selectEnd) { setRange({ from: day, to: day }); setSelectEnd(true) }
    else { setRange({ from: day < range.from ? day : range.from, to: day > range.from ? day : range.from }); setSelectEnd(false) }
  }
  return <div popover={embedded ? undefined : "manual"} className={`pd-column-popover pd-date-picker${embedded ? " report-inline-calendar" : ""}`} role="group" aria-label="날짜 선택">
    {!week && <div className="pd-date-mode"><button type="button" aria-pressed={mode === 'day'} onClick={() => { setMode('day'); setSelectEnd(false); setRange({ from: range.from, to: range.from }) }}>하루</button><button type="button" aria-pressed={mode === 'range'} onClick={() => { setMode('range'); setSelectEnd(false) }}>기간</button></div>}
    <div className="pd-date-inputs"><input aria-label="시작 날짜" ref={startInput} aria-invalid={!!error && startInvalid} type="date" value={range.from} onChange={e => { if (week && /^\d{4}-\d{2}-\d{2}$/.test(e.target.value)) pick(e.target.value); else setRange({ from: e.target.value, to: mode === 'day' ? e.target.value : range.to }); if (/^\d{4}-\d{2}-\d{2}$/.test(e.target.value)) setMonth(e.target.value.slice(0, 7)) }} />{mode === 'range' && <><span>—</span><input aria-label="종료 날짜" ref={endInput} aria-invalid={!!error && !startInvalid} readOnly={week} type="date" value={range.to} onChange={e => setRange({ ...range, to: e.target.value })} /></>}</div>
    <div className="pd-calendar-head"><button type="button" aria-label="이전 달" onClick={() => move(-1)}><ChevronLeft size={16} /></button><strong>{year}년 {number}월</strong><button type="button" aria-label="다음 달" onClick={() => move(1)}><ChevronRight size={16} /></button></div>
    <div className="pd-calendar-grid">{weekdays.map(d => <span key={d}>{d}</span>)}{Array.from({length:offset},(_,i)=><span key={`empty-${i}`} />)}{Array.from({length:days},(_,i)=>{const day=`${month}-${String(i+1).padStart(2,'0')}`;return <button key={day} type="button" aria-label={day} aria-pressed={day>=range.from && day<=range.to} data-edge={day===range.from || day===range.to || undefined} onClick={()=>pick(day)}>{i+1}</button>})}</div>
    <p role="status">{error || (selectEnd ? '종료일을 선택하세요.' : week ? '날짜를 고르면 월요일부터 일요일까지 선택됩니다.' : '날짜를 선택하거나 직접 입력하세요.')}</p>
    <footer><button type="button" onClick={onCancel}>취소</button><button type="button" className="pd-date-confirm" onClick={() => { if (!validPeriod(range)) { setError(startInvalid ? '시작 날짜를 입력하세요.' : '종료 날짜를 시작 날짜와 같거나 이후로 입력하세요.'); (startInvalid || week ? startInput : endInput).current?.focus(); return } if (week) { const d=new Date(range.from+'T00:00:00Z'); d.setUTCDate(d.getUTCDate()-(d.getUTCDay()+6)%7); const from=d.toISOString().slice(0,10); d.setUTCDate(d.getUTCDate()+6); onApply({from,to:d.toISOString().slice(0,10)}) } else onApply(range) }}>확인</button></footer>
  </div>
}
