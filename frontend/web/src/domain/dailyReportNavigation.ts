import type { WeeklyReport } from './parent.ts'
import { STORY_THEMES } from './storyThemes.ts'

export interface DailyActivitySelection {
  indices: number[]
  label?: string
  direct?: boolean
}

interface DailyReportGroup {
  key: string
  label: string
  story: boolean
  indices: number[]
}

/** All story types → completed problems → records. Titles never determine story type. */
export function dailyReportGroups(report: Pick<WeeklyReport, 'problems' | 'themeSummary'>) {
  const groups = new Map<string, DailyReportGroup>(STORY_THEMES.map(t =>
    [t.key, { ...t, story: true, indices: [] }]))
  for (const [index, problem] of (report.problems ?? []).entries()) {
    const isThemeActivity = problem.context === 'THEME_DAY' || problem.context === 'THEME_REVIEW'
    const type = isThemeActivity && problem.theme?.themeId && problem.theme.versionId ? problem.theme.storyType : null
    const known = type ? groups.get(type) : undefined
    const key = known?.story ? known.key : problem.context === 'EXTRA' ? 'extra' : 'unclassified'
    const label = key === 'extra' ? '추가 문제' : '테마 미분류 기록'
    const group = groups.get(key) ?? { key, label, story: false, indices: [] }
    group.indices.push(index)
    groups.set(key, group)
  }
  return [...groups.values()]
}
