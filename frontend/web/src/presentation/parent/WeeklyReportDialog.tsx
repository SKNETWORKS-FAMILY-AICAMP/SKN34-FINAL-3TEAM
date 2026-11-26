import { BookOpen, ChevronDown, ChevronRight } from 'lucide-react'
import { useEffect, useRef, type ReactNode } from 'react'
import { thinkingLabels } from '../../domain/classroom.ts'
import type { WeeklyReport } from '../../domain/parent.ts'
import { weeklyActivities, weeklyCategories, type WeeklyReportView } from '../../domain/weeklyReportNavigation.ts'
import { Modal } from '../shared/ClassroomParts.tsx'
import { ReportDialogNavigation } from './ReportDialogNavigation.tsx'
import { useReportDialogHistory } from './useReportDialogHistory.ts'
import './weekly-report-dialog.css'

export function WeeklyReportDialog({ report, initial, onClose, renderActivity, metrics, theme, children }: {
  report: WeeklyReport; initial: WeeklyReportView; onClose: () => void
  renderActivity: (id: string) => ReactNode; metrics: ReactNode; theme?: ReactNode; children: ReactNode
}) {
  const root: WeeklyReportView = { category: null, attemptId: null }
  const history = useReportDialogHistory(initial.category ? [root, { ...initial, attemptId: null }, ...(initial.attemptId ? [initial] : [])] : [root],
    (a, b) => a.category === b.category && a.attemptId === b.attemptId)
  const categories = weeklyCategories(report), activities = weeklyActivities(report)
  const category = categories.find(item => item.key === history.current.category)
  const activity = activities.find(item => item.id === history.current.attemptId)
  const title = activity?.title ?? category?.label ?? ({ narrative: '한 주의 기록', metrics: '학습 수치', theme: '이번 주 테마' }[history.current.category ?? ''] ?? '주간 기록 둘러보기')
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    heading.current?.focus({ preventScroll: true })
    heading.current?.scrollIntoView({ block: 'nearest' })
  }, [history.current.category, history.current.attemptId])
  const choose = (id: string) => history.navigate({ ...history.current, attemptId: id })
  return <Modal title="주간 리포트 전체 보기" onClose={onClose} scrollIndicator>
    <div className="report-body weekly-report-dialog">
      <div className="report-dialog-topline"><ReportDialogNavigation {...history} /><p className="daily-problems-date">{report.period.from} ~ {report.period.to} · {activities.length}개 활동</p></div>
      <nav className="daily-report-path" aria-label="주간 기록 탐색 경로">
        <button onClick={() => history.navigate(root)} aria-current={!history.current.category ? 'page' : undefined}>전체 리포트</button>
        {history.current.category && <><ChevronRight size={14} aria-hidden="true" /><button onClick={() => history.navigate({ ...history.current, attemptId: null })} aria-current={!activity ? 'page' : undefined}>{category?.label ?? title}</button></>}
        {activity && <><ChevronRight size={14} aria-hidden="true" /><span aria-current="page">상세 기록</span></>}
      </nav>
      <header className="report-reader-heading"><BookOpen size={26} aria-hidden="true" /><div>
        <h3 className="daily-navigation-heading" ref={heading} tabIndex={-1}>{title}</h3>
        {activity?.type && <p className="weekly-category-label">[{thinkingLabels[activity.type]}]</p>}
      </div></header>
      {!history.current.category ? <>
        <section className="weekly-dialog-section"><h4>생각 유형별 활동</h4><ul className="daily-navigation-list">{categories.filter(item => item.kind === 'thinking').map(item => <li key={item.key}><button className="daily-navigation-row" disabled={!item.ids.length} onClick={() => history.navigate({ category: item.key, attemptId: null })}><strong>{item.label}</strong><span>{item.ids.length}개</span><ChevronRight size={16} aria-hidden="true" /></button></li>)}</ul></section>
        <section className="weekly-dialog-section"><h4>기록별 보기</h4><ul className="daily-navigation-list">{categories.filter(item => item.kind === 'record').map(item => <li key={item.key}><button className="daily-navigation-row" disabled={!item.ids.length} onClick={() => history.navigate({ category: item.key, attemptId: null })}><strong>{item.label}</strong><span>{item.ids.length}개</span><ChevronRight size={16} aria-hidden="true" /></button></li>)}
          {report.narrative && <li><button className="daily-navigation-row" onClick={() => history.navigate({ category: 'narrative', attemptId: null })}><strong>한 주의 기록</strong><ChevronRight size={16} aria-hidden="true" /></button></li>}
          {theme && <li><button className="daily-navigation-row" onClick={() => history.navigate({ category: 'theme', attemptId: null })}><strong>이번 주 테마</strong><ChevronRight size={16} aria-hidden="true" /></button></li>}
          <li><button className="daily-navigation-row" onClick={() => history.navigate({ category: 'metrics', attemptId: null })}><strong>학습 수치 전체 보기</strong><span>{report.metrics.length}항목</span><ChevronRight size={16} aria-hidden="true" /></button></li>
        </ul></section>
      </> : category ? activity ? <>
        <WeeklyActivityPicker activities={activities.filter(item => category.ids.includes(item.id))} selected={activity.id} onSelect={choose} />
        {renderActivity(activity.id)}
      </> : <ul className="daily-navigation-list" aria-label={`${category.label} 활동 목록`}>{activities.filter(item => category.ids.includes(item.id)).map(item => <li key={item.id}><button className="daily-navigation-row weekly-problem-row" onClick={() => choose(item.id)}><strong>{item.title}</strong>{item.type && <span>[{thinkingLabels[item.type]}]</span>}<ChevronRight size={16} aria-hidden="true" /></button></li>)}</ul>
      : history.current.category === 'metrics' ? metrics
      : history.current.category === 'theme' ? theme
      : <section className="weekly-narrative-reader">{report.narrative?.text.split(/\n\s*\n/).map((text, index) => <p key={index}>{text}</p>)}{report.narrative && <details className="report-source"><summary>요약 출처</summary><p>{report.narrative.source}</p></details>}{report.eveningQuestion && <section><h4>[이번 주 저녁 질문]</h4><p>{report.eveningQuestion}</p></section>}</section>}
      {children}
    </div>
  </Modal>
}

function WeeklyActivityPicker({ activities, selected, onSelect }: { activities: ReturnType<typeof weeklyActivities>; selected: string; onSelect: (id: string) => void }) {
  const ref = useRef<HTMLDetailsElement>(null), trigger = useRef<HTMLElement>(null)
  const current = activities.find(item => item.id === selected)
  if (activities.length < 2) return null
  return <details className="weekly-activity-picker" ref={ref} onKeyDown={event => {
    if (event.key === 'Escape' && ref.current?.open) { event.stopPropagation(); ref.current.open = false; trigger.current?.focus() }
  }}>
    <summary ref={trigger} aria-label="주간 리포트 활동 선택"><span>{current?.title}{current?.type && <span className="weekly-picker-category">[{thinkingLabels[current.type]}]</span>}</span><ChevronDown size={18} aria-hidden="true" /></summary>
    <ul aria-label="활동 선택 목록">{activities.map(item => <li key={item.id}><button aria-current={item.id === selected ? 'true' : undefined} onClick={() => { if (ref.current) ref.current.open = false; trigger.current?.focus(); onSelect(item.id) }}><span>{item.title}</span>{item.type && <span className="weekly-picker-category">[{thinkingLabels[item.type]}]</span>}</button></li>)}</ul>
  </details>
}
