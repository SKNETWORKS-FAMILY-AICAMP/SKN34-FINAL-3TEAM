import { BookOpen, ChartNoAxesColumn, ChevronRight, ListChecks, MessageCircle, MessageSquare, NotebookPen, RotateCcw, Smile, Sparkles } from 'lucide-react'
import type { WeeklyReport } from '../../domain/parent.ts'
import { dailyJudgments, dailyReportSummary } from '../../domain/dailyReportSummary.ts'
import type { DailyActivitySelection } from '../../domain/dailyReportNavigation.ts'
import './daily-report-summary.css'

export function DailyReportSummary({ report, highlighted, onOpenActivities }: {
  report: WeeklyReport
  highlighted: boolean
  onOpenActivities: (selection: DailyActivitySelection) => void
}) {
  const summary = dailyReportSummary(report)
  const problems = report.problems ?? []
  const count = (value: number | null) => value === null ? <span className="daily-unavailable">확인할 수 없음</span> : <><strong>{value}</strong><span>개</span></>
  const activity = (index: number) => {
    const p = problems[index]
    const judgment = dailyJudgments.find(j => j.key === (p.judgment ?? 'UNKNOWN'))!
    return <li key={`${p.attemptId ?? p.missionId}-${index}`}>
      <button className="daily-activity" onClick={() => onOpenActivities({ indices: [index], direct: true })}>
        <span className="daily-activity-copy"><strong>{p.title}</strong><small>{p.context === 'EXTRA' ? '추가 문제' : p.context === 'THEME_REVIEW' ? '되돌아보기 다시 풀기' : p.context === 'THEME_DAY' ? '주간 테마 오늘 문제' : '학습 활동'}</small></span>
        <span className={`daily-badge daily-tone-${judgment.tone}`}>{judgment.label}</span><ChevronRight size={15} aria-hidden="true" />
      </button>
    </li>
  }
  const slices = [...summary.difficulties, { label: '기록 없음', color: '#dfe5ec', count: summary.difficultyMissing, indices: summary.difficultyMissingIndices }]
  let start = 0
  const stops = slices.map(slice => {
    const from = start
    start += problems.length ? slice.count / problems.length * 100 : 0
    return `${slice.color} ${from}% ${start}%`
  }).join(', ')

  return <div className="daily-summary" aria-label="일일 리포트 요약">
    <div className="daily-summary-top">
      <section className="daily-summary-card daily-total report-highlight-target" data-answer-highlight={highlighted || undefined} tabIndex={highlighted ? -1 : undefined} aria-label="오늘 완료한 활동">
        <h4><BookOpen size={17} aria-hidden="true" />오늘 완료한 활동</h4>
        <div className="daily-number">{count(summary.total)}</div>
      </section>
      <section className="daily-summary-card daily-judgments" aria-label="오늘의 판정 결과">
        <h4><ChartNoAxesColumn size={17} aria-hidden="true" />오늘의 판정 결과</h4>
        {summary.available ? <dl>{summary.judgments.filter(j => j.count || ['CORRECT', 'PARTIAL', 'RETHINK'].includes(j.key)).map(j => <div key={j.key} className={`daily-tone-${j.tone}`}><dd>{j.count}<span>개</span></dd><dt>{j.label}</dt></div>)}</dl> : <p>문제별 판정 기록을 확인할 수 없어요.</p>}
      </section>
    </div>
    <div className="daily-summary-stats">
      {[
        { label: '되묻기가 있었던 활동', value: summary.followupActivities, Icon: MessageCircle },
        { label: '되묻기에 대한 답변 기록', value: summary.answeredActivities, Icon: MessageSquare },
        { label: '돌아보기를 작성한 활동', value: summary.reflections, Icon: NotebookPen },
      ].map(({ label, value, Icon }) => <section className="daily-summary-card daily-stat" key={label} aria-label={label}><h4><Icon size={16} aria-hidden="true" />{label}</h4><div className="daily-number">{count(value)}</div></section>)}
    </div>
    {summary.total === 0 ? <div className="daily-summary-empty"><BookOpen size={26} aria-hidden="true" /><h4>이날은 완료한 활동이 없어요.</h4></div> : !summary.available ? <p className="daily-summary-empty">이 리포트에는 문제별 상세 기록이 없어 추가 요약을 표시할 수 없어요.</p> : <div className="daily-summary-panels">
      <section className="daily-summary-card daily-review" aria-label="다시 살펴볼 활동">
        <header><h4><RotateCcw size={17} aria-hidden="true" />다시 살펴볼 활동</h4><span className="daily-panel-count">{summary.reviewIndices.length}개</span></header>
        {summary.reviewIndices.length ? <><ul className="daily-activity-list">{summary.reviewIndices.slice(0, 3).map(activity)}</ul>{summary.reviewIndices.length > 3 && <button className="daily-text-button" onClick={() => onOpenActivities({ indices: summary.reviewIndices, label: '다시 생각해 보기' })}>전체 {summary.reviewIndices.length}개 보기<ChevronRight size={14} aria-hidden="true" /></button>}</> : <p className="daily-empty-copy">다시 생각해 볼 활동이 없어요.</p>}
      </section>
      <section className="daily-summary-card daily-elements" aria-label="오늘 확인된 생각 요소">
        <header><h4><Sparkles size={17} aria-hidden="true" />오늘 확인된 생각 요소</h4></header>
        {summary.elements.length ? <ul>{summary.elements.slice(0, 5).map(element => <li key={element.label}><button onClick={() => onOpenActivities({ indices: element.indices, label: element.label })}><span>{element.label}</span><span className="daily-element-count">{element.indices.length}개 활동<ChevronRight size={14} aria-hidden="true" /></span></button></li>)}</ul> : <p className="daily-empty-copy">이날 기록에서 확인된 생각 요소가 없어요.</p>}
        {summary.elements.length > 5 && <button className="daily-text-button" onClick={() => onOpenActivities({ indices: [] })}>활동에서 모든 요소 보기<ChevronRight size={14} aria-hidden="true" /></button>}
      </section>
      <section className="daily-summary-card daily-activities" aria-label="오늘 푼 활동">
        <header><h4><ListChecks size={17} aria-hidden="true" />오늘 푼 활동</h4><button className="daily-text-button" onClick={() => onOpenActivities({ indices: [] })}>전체 {problems.length}개 보기<ChevronRight size={14} aria-hidden="true" /></button></header>
        <ul className="daily-activity-list">{problems.slice(0, 5).map((_, index) => activity(index))}</ul>
      </section>
      <section className="daily-summary-card daily-difficulty" aria-label="아이가 느낀 난이도">
        <header><h4><Smile size={17} aria-hidden="true" />아이가 느낀 난이도</h4></header>
        <div className="daily-difficulty-body">
          <div className="daily-donut" style={{ background: summary.difficultyRecorded ? `conic-gradient(${stops})` : '#e8edf2' }} aria-hidden="true"><div><strong>{summary.difficultyRecorded}</strong><span>난이도 기록</span></div></div>
          <dl className="daily-difficulty-legend">{slices.map(d => <div key={d.label}><dt><i style={{ background: d.color }} aria-hidden="true" />{d.label}</dt><dd>{d.count > 0 ? <button className="daily-difficulty-count" aria-label={`${d.label} ${d.count}개 활동 보기`} aria-haspopup="dialog" onClick={() => onOpenActivities({ indices: d.indices, label: d.label })}>{d.count}</button> : d.count}<span>개</span></dd></div>)}</dl>
        </div>
        {!summary.difficultyRecorded && <p className="daily-empty-copy">아직 선택한 난이도가 없어요.</p>}
      </section>
    </div>}
  </div>
}
