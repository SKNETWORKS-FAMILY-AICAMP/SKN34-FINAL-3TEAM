import {
  counts,
  eligibleRecords,
  thinkingLabels,
  previousWeek,
  thisWeek,
} from '../../domain/classroom.ts'
import { changeCounts } from '../../domain/parent.ts'
import type { Child, Period, PublicAttempt } from '../../domain/classroom.ts'
import type { Conversation, Evidence, WeeklyReport } from '../../domain/parent.ts'
import { fixtureStore } from './student.ts'
import { workspaceScenario } from './accounts.ts'
export const inclusionRule =
  '기간 내 답변 제출이 있는 시도(미완료 포함), 처리 실패만 있는 시도·삭제 기록 제외'
export const conversations = new Map<string, Conversation>()
export const reports = new Map<string, WeeklyReport[]>()
export const regenerateCounts = new Map<string, number>()
export const pendingReports = new Map<string, number>()
export function scopedRows(c: Child, p: Period): PublicAttempt[] {
  if (workspaceScenario === 'empty') return []
  const rows = eligibleRecords(
    fixtureStore
      .snapshot()
      .attempts.filter((a) => a.studentId === c.id)
      .map((a) => {
        const { draft: _private, ...visible } = a
        return visible
      }),
    p,
  )
  return workspaceScenario === 'small' ? rows.slice(0, 1) : rows
}
export function evidence(rows: PublicAttempt[]): Evidence[] {
  return rows.flatMap((a) =>
    a.answers.map((v) => ({
      attemptId: a.attemptId,
      missionTitle: a.mission.title,
      answerId: v.answerId,
      answerVersion: v.version,
      submittedAt: v.submittedAt,
      quote: workspaceScenario === 'deleted-evidence' ? undefined : v.text,
      available: workspaceScenario !== 'deleted-evidence',
    })),
  )
}
export function thinking(c: Child, p: Period) {
  const rows = scopedRows(c, p)
  return Object.keys(thinkingLabels).map((type) => ({
    type: type as keyof typeof thinkingLabels,
    state: rows.some((a) => a.mission.thinkingType === type)
      ? ('OK' as const)
      : ('NO_RECORD' as const),
    missions: rows
      .filter((a) => a.mission.thinkingType === type)
      .map((a) => ({ attemptId: a.attemptId, title: a.mission.title })),
    summary: c.plan === 'PREMIUM' ? '실제 작성된 기록만 관찰합니다.' : undefined,
  }))
}
export function makeWeekly(c: Child, p: Period, revision = 1): WeeklyReport {
  const rows = scopedRows(c, p),
    metrics = counts(rows, p)
  const report: WeeklyReport = {
    reportId: `${c.id}-${p.from}`,
    childId: c.id,
    period: p,
    revision,
    revisions: [{ revision, generatedAt: '2026-10-26T07:00:00+09:00' }],
    status: 'COMPLETED',
    state: metrics[0].state,
    inclusionRule,
    metrics: metrics.map((m, i) => ({ ...m, itemId: `metric-${i}` })),
    thinkingTypes: thinking(c, p),
    changes: rows
      .filter((a) => a.answers.length > 1)
      .map((a) => {
        const first = a.answers[0],
          last = a.answers.at(-1)!
        const f = changeCounts(first.text),
          l = changeCounts(last.text)
        return {
          itemId: `change-${a.attemptId}`,
          attemptId: a.attemptId,
          followup: first.feedback.followup?.question ?? '추가 생각을 적어 보세요.',
          first: { answerId: first.answerId, text: first.text },
          revised: { answerId: last.answerId, text: last.text },
          counts: {
            chars: [f.chars, l.chars],
            sentences: [f.sentences, l.sentences],
            reasonConnectives: [f.reasonConnectives, l.reasonConnectives],
          },
        }
      }),
    reflections: rows.map((a) => ({
      attemptId: a.attemptId,
      difficulty: a.reflection?.difficulty ?? '',
      text: a.reflection?.text ?? '',
      written: !!a.reflection,
    })),
    quotes: rows
      .filter((a) => a.answers.length)
      .map((a) => ({
        itemId: `quote-${a.attemptId}`,
        attemptId: a.attemptId,
        answerId: a.answers.at(-1)!.answerId,
        text: a.answers.at(-1)!.text,
        verified: true,
      })),
    narrative:
      c.plan === 'PREMIUM'
        ? {
            text: rows.length
              ? '답변 전후를 나란히 읽고, 덧붙인 생각을 확인해 보세요. 능력이나 향상을 진단하는 결과는 아닙니다.'
              : '이번 주 집계할 기록이 없습니다.',
            source: 'TEMPLATE',
          }
        : null,
    eveningQuestion:
      c.plan === 'PREMIUM' && rows.length ? '어떤 생각을 더 적고 싶었나요?' : undefined,
    verification: { numbersMatched: true, quotesMatched: true },
    versions: { prompt: 'mock-report@1', model: null },
    generatedAt: '2026-10-26T07:00:00+09:00',
  }
  return c.plan === 'FREE'
    ? { ...report, thinkingTypes: [], changes: [], reflections: [], quotes: [] }
    : report
}
export function ensureReports(c: Child) {
  for (const p of [previousWeek, thisWeek, { from: '2026-10-12', to: '2026-10-18' }]) {
    const r = makeWeekly(c, p)
    if (!reports.has(r.reportId)) reports.set(r.reportId, [r])
  }
  return [...reports.values()].filter((v) => v[0].childId === c.id).map((v) => v.at(-1)!)
}
