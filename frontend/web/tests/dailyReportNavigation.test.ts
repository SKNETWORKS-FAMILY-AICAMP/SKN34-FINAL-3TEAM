import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dailyReportGroups } from '../src/domain/dailyReportNavigation.ts'
import { STORY_THEMES } from '../src/domain/storyThemes.ts'
import type { DailyProblem } from '../src/domain/parent.ts'

const problem = (patch: Partial<DailyProblem> = {}): DailyProblem => ({
  missionId: 'same-mission', title: '같은 제목', context: 'EXTRA', judgment: null,
  followups: [], finalAnswer: null, elements: [], reflection: null, quotes: [], ...patch,
})

test('all eleven story types remain in the service order even without completed problems', () => {
  const source = readFileSync(new URL('../../../backend/learning-service/src/main/kotlin/com/sagomungchi/learning/theme/domain/ThemeTopicSeeds.kt', import.meta.url), 'utf8')
  const canonical = [...source.matchAll(/^\s+([A-Z_]+)\("([^"]+)",/gm)].map(m => ({ key: m[1], label: m[2] }))
  assert.equal(canonical.length, 11)
  assert.deepEqual(STORY_THEMES, canonical)
  const groups = dailyReportGroups({ problems: [] })
  assert.deepEqual(groups.map(g => ({ key: g.key, label: g.label })), canonical)
  assert.ok(groups.every(g => g.story && g.indices.length === 0))
})

test('counts use explicit story classification and retain repeated attempts across theme versions', () => {
  const theme = { themeId: 'theme', versionId: 'v1', title: '제목으로 분류하지 않음', storyType: 'SOUND' }
  const groups = dailyReportGroups({ problems: [
    problem({ context: 'THEME_DAY', theme, attemptId: 'first' }),
    problem({ context: 'THEME_REVIEW', theme: { ...theme, versionId: 'v2' }, attemptId: 'retry' }),
    problem({ context: 'THEME_DAY', theme: { ...theme, themeId: 'second-theme', storyType: 'LOST' } }),
    problem({ theme }),
  ] })
  assert.deepEqual(groups.find(g => g.key === 'SOUND')?.indices, [0, 1])
  assert.deepEqual(groups.find(g => g.key === 'LOST')?.indices, [2])
  assert.deepEqual(groups.find(g => g.key === 'extra')?.indices, [3])
  assert.equal(groups.filter(g => g.story && !g.indices.length).length, 9)
  assert.deepEqual(groups.flatMap(g => g.indices).sort(), [0, 1, 2, 3])
})

test('missing or unknown types are unclassified; matching titles and the current weekly theme prove nothing', () => {
  const theme = { themeId: 'theme', versionId: 'v1', title: '소리 탐정' }
  const groups = dailyReportGroups({ problems: [
    problem({ context: 'THEME_DAY', theme }),
    problem({ context: 'THEME_REVIEW', theme: { ...theme, storyType: 'FUTURE_TYPE' } }),
    problem({ context: null, theme: { ...theme, storyType: 'SOUND' } }),
    problem({ context: 'THEME_DAY', theme: { ...theme, versionId: '', storyType: 'SOUND' } }),
    problem(),
  ], themeSummary: { themeId: 'theme', title: '소리 탐정', completed: false, days: [], reviewRetries: [] } })
  assert.ok(groups.filter(g => g.story).every(g => g.indices.length === 0))
  assert.deepEqual(groups.find(g => g.key === 'unclassified')?.indices, [0, 1, 2, 3])
  assert.deepEqual(groups.find(g => g.key === 'extra')?.indices, [4])
})
