import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react'
import { validPeriod } from '../../domain/parent.ts'
import { calendarPeriods } from '../../domain/classroom.ts'
import { Modal } from '../shared/ClassroomParts.tsx'

type Period = { from: string; to: string }
const weekdays = ['일', '월', '화', '수', '목', '금', '토']
const parseDay = (value: string) => new Date(`${value}T12:00:00Z`)
const isoDay = (value: Date) => value.toISOString().slice(0, 10)
const labelDay = (value: string) => `${Number(value.slice(0, 4))}년 ${Number(value.slice(5, 7))}월 ${Number(value.slice(8, 10))}일`

export function PeriodPicker({ period, onApply }: { period: Period; onApply: (p: Period) => void }) {
  const [from, setFrom] = useState(period.from), [to, setTo] = useState(period.to)
  const [error, setError] = useState(''), [open, setOpen] = useState(false)
  const [source, setSource] = useState(period)
  if (source.from !== period.from || source.to !== period.to) {
    setSource(period); setFrom(period.from); setTo(period.to); setError('')
  }
  function apply(next: Period) {
    if (!validPeriod(next)) { setError('날짜를 YYYY-MM-DD로 입력하고 시작일과 종료일의 순서를 확인해 주세요.'); return }
    setFrom(next.from); setTo(next.to); setError(''); setOpen(false); onApply(next)
  }
  const initial = validPeriod({ from, to }) ? { from, to } : validPeriod(period) ? period : calendarPeriods().recentPeriod
  return <div className="ad-period-control">
    <form className="ad-period" onSubmit={e => { e.preventDefault(); apply({ from, to }) }}>
      <label><span className="ad-sr">집계 시작일 (YYYY-MM-DD)</span><input aria-label="집계 시작일" type="text" placeholder="YYYY-MM-DD" maxLength={10} autoComplete="off" spellCheck={false} value={from} onChange={e => setFrom(e.target.value)} /></label>
      <span className="ad-period-separator" aria-hidden="true">~</span>
      <label><span className="ad-sr">집계 종료일 (YYYY-MM-DD)</span><input aria-label="집계 종료일" type="text" placeholder="YYYY-MM-DD" maxLength={10} autoComplete="off" spellCheck={false} value={to} onChange={e => setTo(e.target.value)} /></label>
      <button type="button" className="ad-period-calendar" aria-label="집계 기간 달력 열기" aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}><CalendarDays size={19} aria-hidden="true" /></button>
      <button type="submit">기간 적용</button>
      {error && <p role="alert">{error}</p>}
    </form>
    {open && <RangeCalendar initial={initial} onConfirm={apply} onCancel={() => setOpen(false)} />}
  </div>
}

function RangeCalendar({ initial, onConfirm, onCancel }: { initial: Period; onConfirm: (p: Period) => void; onCancel: () => void }) {
  const [range, setRange] = useState(initial), [selecting, setSelecting] = useState<'from' | 'to'>('from')
  const [month, setMonth] = useState(initial.from.slice(0, 7)), [hovered, setHovered] = useState('')
  const [focused, setFocused] = useState(initial.from)
  const grid = useRef<HTMLDivElement>(null), keyboardFocus = useRef(false)
  const first = parseDay(`${month}-01`), year = first.getUTCFullYear(), monthIndex = first.getUTCMonth()
  const last = new Date(first); last.setUTCMonth(monthIndex + 1, 0)
  const offset = first.getUTCDay(), count = last.getUTCDate()
  const today = calendarPeriods().recentPeriod.to
  const preview = selecting === 'to' && hovered ? { from: hovered < range.from ? hovered : range.from, to: hovered > range.from ? hovered : range.from } : range
  useEffect(() => {
    if (keyboardFocus.current) { grid.current?.querySelector<HTMLButtonElement>(`[data-day="${focused}"]`)?.focus(); keyboardFocus.current = false }
  }, [focused, month])
  function pick(day: string) {
    setHovered(''); setFocused(day)
    if (selecting === 'from') { setRange({ from: day, to: '' }); setSelecting('to') }
    else { setRange({ from: day < range.from ? day : range.from, to: day < range.from ? range.from : day }); setSelecting('from') }
  }
  function moveMonth(delta: number) {
    const next = new Date(first); next.setUTCMonth(monthIndex + delta)
    setMonth(isoDay(next).slice(0, 7)); setFocused(isoDay(next)); setHovered('')
  }
  function moveFocus(event: KeyboardEvent<HTMLButtonElement>, day: string) {
    const next = parseDay(day)
    const delta: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7, Home: -next.getUTCDay(), End: 6 - next.getUTCDay() }
    if (!(event.key in delta)) return
    event.preventDefault(); next.setUTCDate(next.getUTCDate() + delta[event.key])
    keyboardFocus.current = true; setFocused(isoDay(next)); setMonth(isoDay(next).slice(0, 7))
  }
  return <div className="ad-period-dialog"><Modal title="집계 기간 선택" onClose={onCancel}>
    <div className="ad-range-summary">
      <button type="button" className={selecting === 'from' ? 'is-selecting' : ''} aria-pressed={selecting === 'from'} onClick={() => { setSelecting('from'); setMonth(range.from.slice(0, 7)); setFocused(range.from) }}><span>시작일</span><strong>{range.from}</strong></button>
      <span aria-hidden="true">~</span>
      <button type="button" className={selecting === 'to' ? 'is-selecting' : ''} aria-pressed={selecting === 'to'} onClick={() => { setSelecting('to'); setMonth((range.to || range.from).slice(0, 7)); setFocused(range.to || range.from) }}><span>종료일</span><strong>{range.to || '날짜 선택'}</strong></button>
    </div>
    <div className="ad-calendar-heading">
      <button type="button" aria-label="이전 달" disabled={month === '0001-01'} onClick={() => moveMonth(-1)}><ChevronLeft size={19} aria-hidden="true" /></button>
      <h3 aria-live="polite">{year}년 {monthIndex + 1}월</h3>
      <button type="button" aria-label="다음 달" disabled={month === '9999-12'} onClick={() => moveMonth(1)}><ChevronRight size={19} aria-hidden="true" /></button>
    </div>
    <div className="ad-calendar-weekdays" aria-hidden="true">{weekdays.map(day => <span key={day}>{day}</span>)}</div>
    <div className="ad-calendar-days" role="group" aria-label={`${year}년 ${monthIndex + 1}월 날짜`} ref={grid} onMouseLeave={() => setHovered('')}>
      {Array.from({ length: 42 }, (_, i) => {
        const number = i - offset + 1
        if (number < 1 || number > count) return <span key={i} aria-hidden="true" />
        const day = `${month}-${String(number).padStart(2, '0')}`
        const start = day === preview.from, end = day === preview.to
        const inside = preview.to && day >= preview.from && day <= preview.to
        return <button key={i} type="button" data-day={day} tabIndex={focused === day ? 0 : -1} aria-label={labelDay(day)} aria-current={day === today ? 'date' : undefined} aria-pressed={Boolean(inside || start)} className={`${inside ? 'in-range' : ''}${start ? ' is-start' : ''}${end ? ' is-end' : ''}`} onClick={() => pick(day)} onMouseEnter={() => setHovered(day)} onKeyDown={event => moveFocus(event, day)}>{number}</button>
      })}
    </div>
    <div className="ad-calendar-footer"><p role="status">{!range.to ? '종료일을 선택하세요.' : `${range.from} ~ ${range.to}`}</p><div><button type="button" onClick={onCancel}>취소</button><button type="button" className="cj-primary" disabled={!validPeriod(range)} onClick={() => onConfirm(range)}>확인</button></div></div>
  </Modal></div>
}
