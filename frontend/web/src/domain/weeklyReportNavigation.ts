import type { ThinkingType } from './classroom.ts'
import { thinkingLabels } from './classroom.ts'
import type { WeeklyReport } from './parent.ts'

export type WeeklyReportView = { category: string | null; attemptId: string | null }
export function weeklyActivities(report: WeeklyReport) {
  const explanations = report.explanations?.state === 'INCLUDED' ? report.explanations.items : []
  const missions = report.thinkingTypes.flatMap(group => group.missions.map(mission => ({ ...mission, type: group.type })))
  const ids = [...new Set([...missions.map(item => item.attemptId), ...explanations.map(item => item.attemptId),
    ...report.changes.map(item => item.attemptId), ...report.reflections.map(item => item.attemptId), ...report.quotes.filter(item => item.verified).map(item => item.attemptId)])]
  return ids.map((id, index) => {
    const mission = missions.find(item => item.attemptId === id)
    const explanation = explanations.find(item => item.attemptId === id)
    return { id, title: mission?.title ?? explanation?.missionTitle ?? `활동 ${index + 1}`, type: mission?.type ?? explanation?.thinkingType }
  })
}
export function weeklyCategories(report: WeeklyReport) {
  const activities = weeklyActivities(report)
  const unique = (ids: string[]) => [...new Set(ids)]
  return [
    ...Object.entries(thinkingLabels).map(([type, label]) => ({ key: type, label, ids: activities.filter(item => item.type === type as ThinkingType).map(item => item.id), kind: 'thinking' })),
    { key: 'explanations', label: '대표 답변 설명', ids: unique((report.explanations?.state === 'INCLUDED' ? report.explanations.items : []).map(item => item.attemptId)), kind: 'record' },
    { key: 'reflections', label: '돌아보기 기록', ids: unique(report.reflections.map(item => item.attemptId)), kind: 'record' },
    { key: 'changes', label: '답변 전후 변화', ids: unique(report.changes.map(item => item.attemptId)), kind: 'record' },
  ]
}
