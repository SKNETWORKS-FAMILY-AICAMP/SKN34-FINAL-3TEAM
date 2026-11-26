import type { ReactNode } from 'react'
import { ArrowUpRight, ChartNoAxesColumnIncreasing } from 'lucide-react'
import { thinkingLabels } from '../../domain/classroom.ts'
import type { WeeklyReport } from '../../domain/parent.ts'
import './weekly-report-overview.css'

const primaryLabels = new Set(['답변 제출 시도 수', '완료한 시도 수', '도움 없이 시작한 비율', '도움 없이 시작한 활동', '답을 남긴 활동', '생각을 덧붙인 활동'])

/** Existing report counts only. Bar length compares activity counts, never ability scores. */
export function WeeklyReportOverview({ report, highlighted, thinkingHighlights, onProof, theme, onCategory }: {
  report: WeeklyReport; highlighted: number[]; thinkingHighlights: number[]; onProof: (id: string) => void; theme?: ReactNode; onCategory: (key: string) => void
}) {
  const primary = report.metrics.map((metric, index) => ({ metric, index })).filter(({ metric }) => primaryLabels.has(metric.label)).slice(0, 3)
  const maximum = Math.max(1, ...report.thinkingTypes.map(type => type.missions.length))
  return <div className="weekly-insights">
    {!!primary.length && <section aria-label="이번 주 주요 수치">
      <dl className="weekly-key-metrics">{primary.map(({ metric, index }) => {
        const label = metric.label === '도움 없이 시작한 비율' ? '도움 없이 시작한 활동' : metric.label
        return <div key={index} className="report-highlight-target" data-answer-highlight={highlighted.includes(index) || undefined} tabIndex={-1}>
          <dt>{label}</dt><dd><strong>{Number.isFinite(metric.numerator) ? metric.numerator.toLocaleString() : '—'}</strong><span>건</span></dd>
          <div className="weekly-key-context"><span>{metric.state === 'NO_RECORD' ? '기록 없음' : `전체 ${metric.denominator.toLocaleString()}건 중`}</span>
            {report.parentSharingEnabled === true && <button type="button" aria-label={`${label} 내용 보기`} onClick={() => onProof(metric.itemId ?? `metric-${index}`)}>내용<ArrowUpRight size={14} aria-hidden="true" /></button>}
          </div>
        </div>
      })}</dl>
    </section>}
    <div className="weekly-insight-panels">
      <section className="weekly-thinking-chart" aria-labelledby="weekly-thinking-chart-title">
        <header><h3 id="weekly-thinking-chart-title"><ChartNoAxesColumnIncreasing size={20} aria-hidden="true" />생각 유형별 활동</h3><span>활동 수</span></header>
        {!report.thinkingTypes.length ? <p>확인할 활동 기록이 없습니다.</p> : <ul>{report.thinkingTypes.map((type, index) => <li key={type.type} className="report-highlight-target" data-answer-highlight={thinkingHighlights.includes(index) || undefined} tabIndex={-1}>
          <button className="weekly-type-button" disabled={!type.missions.length || report.parentSharingEnabled === false} onClick={() => onCategory(type.type)} aria-label={`${thinkingLabels[type.type]} ${type.missions.length}개 활동 보기`}><span>{thinkingLabels[type.type]}</span><span className="weekly-type-track" aria-hidden="true"><span style={{ width: `${type.missions.length / maximum * 100}%` }} /></span><strong>{type.missions.length}<small>개</small></strong><ArrowUpRight size={14} aria-hidden="true" /></button>
        </li>)}</ul>}
      </section>
      {theme && <section className="weekly-theme-panel">{theme}</section>}
    </div>
  </div>
}
