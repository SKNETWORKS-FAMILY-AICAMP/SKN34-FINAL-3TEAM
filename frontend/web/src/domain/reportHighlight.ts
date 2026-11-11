import type { Metric, Period } from './classroom.ts'
import { thinkingLabels } from './classroom.ts'
import type { ConversationMessage, Evidence, Scope, WeeklyReport } from './parent.ts'
import { reportPeriodType, validPeriod } from './parent.ts'

export interface ReportContext { reportId: string; revision: number; period: Period; periodType: 'DAILY' | 'WEEKLY' }
export interface ReportAnswer {
  conversationId: string
  message: ConversationMessage
  reportId?: string
  reportRevision?: number
}
export interface ReportHighlight extends ReportContext {
  childId: string; messageId: string; question: string; metrics: Metric[]; evidence: Evidence[]
}
export interface ReportTargets { metrics: number[]; problems: number[]; changes: number[]; reflections: number[]; quotes: number[]; thinking: number[] }
export const emptyReportTargets = (): ReportTargets => ({ metrics: [], problems: [], changes: [], reflections: [], quotes: [], thinking: [] })
export const samePeriod = (a: Period, b: Period) => a.from === b.from && a.to === b.to
export function verifiedReportAnswer(message: ConversationMessage, childId: string): message is ConversationMessage & { scope: Scope; metrics: Metric[] } {
  return message.status === 'COMPLETED' && !!message.answer && message.scope?.childId === childId &&
    message.verification?.numbersMatched === true && message.verification.quotesMatched === true && message.verification.contentAllowed === true &&
    Array.isArray(message.metrics) && validPeriod(message.scope)
}

// learning RecordService.summary와 report MetricsCalculator의 기존 집계 정의. 새 이름·식은 추정하지 않는다.
const families = [
  [['학습한 활동', '기간 내 답변 제출이 있는 시도 수'], ['답변 제출 시도 수', '집계 대상 시도 수']],
  [['도움 없이 시작한 활동', '최초 답변 전 생각 열기를 열지 않은 시도 수 / 집계 대상 시도 수'], ['도움 없이 시작한 비율', '최초 답변 전 도움 열람 없는 시도 수 / 집계 대상 시도 수']],
]
function validMetric(m: Metric) {
  return !!m && typeof m.label === 'string' && !!m.label.trim() && typeof m.formula === 'string' && !!m.formula.trim() &&
    !!m.period && validPeriod(m.period) &&
    [m.count, m.numerator, m.denominator].every(n => Number.isSafeInteger(n) && n >= 0) && m.count === m.numerator && m.numerator <= m.denominator &&
    (m.value === null || typeof m.value === 'number' && Number.isFinite(m.value)) &&
    ['RECORD', 'RULE', 'ANSWER_KEY', 'AI_OBSERVATION'].includes(m.sourceType) && ['OK', 'NO_RECORD', 'INSUFFICIENT_SAMPLE'].includes(m.state)
}
function sameMetric(a: Metric, b: Metric) {
  if (!validMetric(a) || !validMetric(b) || !samePeriod(a.period, b.period) || a.count !== b.count ||
    a.numerator !== b.numerator || a.denominator !== b.denominator || a.sourceType !== b.sourceType || a.state !== b.state) return false
  if (a.label === b.label && a.formula === b.formula && a.value === b.value) return true
  const family = (m: Metric) => families.findIndex(rows => rows.some(([label, formula]) => m.label === label && m.formula === formula))
  const ratio = (m: Metric) => m.value === null || m.denominator > 0 && Math.abs(m.value - m.numerator / m.denominator) < 1e-9
  return a.sourceType === 'RECORD' && family(a) >= 0 && family(a) === family(b) && ratio(a) && ratio(b)
}
const text = (value?: string | null) => value?.replace(/\s+/g, ' ').trim() ?? ''
const sameText = (a?: string | null, b?: string | null) => !!text(a) && text(a) === text(b)

export function reportTargets(report: WeeklyReport, highlight?: ReportHighlight | null): ReportTargets {
  const result = emptyReportTargets()
  if (!highlight || report.status !== 'COMPLETED' || report.parentSharingEnabled !== true ||
    report.verification.numbersMatched !== true || report.verification.quotesMatched !== true || report.childId !== highlight.childId ||
    report.reportId !== highlight.reportId || report.revision !== highlight.revision || reportPeriodType(report) !== highlight.periodType ||
    !samePeriod(report.period, highlight.period)) return result
  const refs = highlight.evidence.filter(e => e.available === true && typeof e.attemptId === 'string' && !!e.attemptId)
  const answerRefs = refs.filter(e => (e.kind === 'ANSWER' || e.kind === undefined) && typeof e.answerId === 'string' && !!e.answerId)
  const reflectionRefs = refs.filter(e => e.kind === 'REFLECTION')
  report.metrics.forEach((metric, i) => { if (highlight.metrics.some(m => sameMetric(metric, m))) result.metrics.push(i) })
  const daily = reportPeriodType(report) === 'DAILY'
  if (daily) report.problems?.forEach((problem, i) => {
    const visible = [problem.finalAnswer, ...problem.followups.map(f => f.answer)]
    // 일일 리포트의 finalAnswer에는 ID가 없다. 현재 원문 전체 또는 같은 답변 ID의 검증된 발췌를 대조한다.
    const answer = answerRefs.some(e => e.attemptId === problem.attemptId && (
      visible.some(t => sameText(t, e.quote)) ||
      problem.quotes.some(q => q.verified && q.answerId === e.answerId && !!text(q.text) && visible.some(t => text(t).includes(text(q.text))))
    ))
    const reflection = problem.reflection?.written && reflectionRefs.some(e => e.attemptId === problem.attemptId && sameText(e.quote, problem.reflection?.text))
    if (answer || reflection) result.problems.push(i)
  })
  if (daily) return result
  report.changes.forEach((change, i) => {
    if (answerRefs.some(e => e.attemptId === change.attemptId && [change.first, change.revised].some(a => a.answerId === e.answerId && !!a.text))) result.changes.push(i)
  })
  report.reflections.forEach((reflection, i) => {
    if (reflection.written && reflectionRefs.some(e => e.attemptId === reflection.attemptId && sameText(e.quote, reflection.text))) result.reflections.push(i)
  })
  report.quotes.forEach((quote, i) => {
    if (quote.verified && quote.text && answerRefs.some(e => e.attemptId === quote.attemptId && e.answerId === quote.answerId)) result.quotes.push(i)
  })
  report.thinkingTypes.forEach((thinking, i) => {
    const label = thinkingLabels[thinking.type]
    if (highlight.metrics.some(m => validMetric(m) && m.sourceType === 'RECORD' && samePeriod(m.period, report.period) &&
      m.label === `${label} 활동` && m.formula === `${label} 유형 시도 수` && m.count === thinking.missions.length && m.numerator === m.count && m.denominator === m.count && m.value === null)) result.thinking.push(i)
  })
  return result
}
