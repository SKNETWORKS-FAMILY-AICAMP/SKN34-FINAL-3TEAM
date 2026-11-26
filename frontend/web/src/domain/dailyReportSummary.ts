import { difficultyText, type WeeklyReport } from './parent.ts'

export const dailyJudgments = [
  { key: 'CORRECT', label: '맞게 썼어요', tone: 'green' },
  { key: 'PARTIAL', label: '일부 확인', tone: 'amber' },
  { key: 'RETHINK', label: '다시 생각해 보기', tone: 'rose' },
  { key: 'HELD', label: '판정 보류', tone: 'slate' },
  { key: 'UNKNOWN', label: '판정 없음', tone: 'slate' },
] as const

/** Only facts in this report revision. Missing data is not a zero. */
export function dailyReportSummary(report: Pick<WeeklyReport, 'problems' | 'metrics'>) {
  const problems = report.problems ?? []
  const available = Array.isArray(report.problems)
  const metric = report.metrics.find(m => m.label === '완료한 활동')
  const total = available ? problems.length : metric?.count ?? null
  const judgments = dailyJudgments.map(j => ({ ...j, count: problems.filter(p => (p.judgment ?? 'UNKNOWN') === j.key).length }))
  const elements = new Map<string, number[]>()
  problems.forEach((problem, index) => {
    for (const label of new Set(problem.elements.filter(e => e.satisfied && e.label.trim()).map(e => e.label.trim()))) {
      elements.set(label, [...(elements.get(label) ?? []), index])
    }
  })
  const difficulties = [
    { label: '쉬웠어요', tone: 'green', color: '#2c9b73' },
    { label: '보통', tone: 'blue', color: '#5486d8' },
    { label: '어려웠어요', tone: 'amber', color: '#e8a53b' },
  ].map(d => {
    const indices = problems.flatMap((p, index) => p.reflection?.written && difficultyText(p.reflection.difficulty) === d.label ? [index] : [])
    return { ...d, count: indices.length, indices }
  })
  const difficultyRecorded = difficulties.reduce((sum, d) => sum + d.count, 0)
  const recordedIndices = new Set(difficulties.flatMap(d => d.indices))
  const difficultyMissingIndices = problems.flatMap((_, index) => recordedIndices.has(index) ? [] : [index])
  return {
    total, available, judgments,
    followupActivities: available ? problems.filter(p => p.followups.length > 0).length : null,
    answeredActivities: available ? problems.filter(p => p.followups.some(f => f.answer?.trim())).length : null,
    reflections: available ? problems.filter(p => p.reflection?.written).length : null,
    reviewIndices: problems.flatMap((p, index) => p.judgment === 'RETHINK' ? [index] : []),
    elements: [...elements].map(([label, indices]) => ({ label, indices })).sort((a, b) => b.indices.length - a.indices.length || a.label.localeCompare(b.label, 'ko')),
    difficulties, difficultyRecorded,
    difficultyMissing: difficultyMissingIndices.length, difficultyMissingIndices,
  }
}
