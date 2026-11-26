/** Opt-in, synthetic UI data only. No model calls or production report writes. */
import type { Attempt, Child, ThinkingType } from '../../domain/classroom.ts'
import { mockAccountChildren } from './accounts.ts'
import { mockPremium, setMockSubscription } from './payments.ts'
import { fixtureStore, persistFixtureState } from './student.ts'
import { saveSharing } from './sharing.ts'
import { generatedReportDetails, makeWeekly, reports } from './parent.ts'
import demoData from './structuredReportSamples.json' with { type: 'json' }

export const structuredReportChild: Child = { id: 'demo-report-grade5', nickname: '리포트 예시', grade: demoData.grade, birthYear: 2015 }
export const structuredReportPeriod = { from: '2026-11-09', to: '2026-11-15' }
const owner = 'parent@example.test'
const prefix = 'structured-report-demo-'

export interface GemmaReportCache {
  model: string
  promptVersion: string
  items: { attemptId: string; answerVersion: number; sourceText: string; text: string }[]
}

export function seedStructuredReportDemo(cache?: GemmaReportCache) {
  const child = structuredReportChild
  const snapshot = fixtureStore.snapshot()
  const children = [...(snapshot.children ?? []).filter(c => c.id !== child.id), child]
  const attempts: Attempt[] = demoData.samples.map(sample => {
    const { attemptId } = sample
    return {
      attemptId, studentId: child.id, status: 'COMPLETED', helped: false,
      mission: { id: attemptId + '-mission', title: sample.title, grade: child.grade, subject: '국어',
        inputType: 'NARRATIVE', thinkingType: sample.type as ThinkingType, question: sample.question, hint: '실제 경험과 구체적인 까닭을 떠올려 보세요.', scene: 'korean' },
      answers: sample.texts.map((text, index) => ({ answerId: `${attemptId}-answer-${index + 1}`, version: index + 1,
        submittedAt: `${sample.day}T16:0${index}:00+09:00`, text, inputType: 'NARRATIVE',
        feedback: { status: 'DONE', judgment: null, nextActions: [], followup: index === 0 && sample.texts.length > 1
          ? { followupId: attemptId + '-followup', type: 'TELL_MORE', source: 'BANK', question: '도서관까지 가는 데 얼마나 걸리고, 도서관이 생기면 무엇을 하고 싶나요?' } : null } })),
      finishedAt: `${sample.day}T16:10:00+09:00`,
      reflection: { difficulty: '보통', text: sample.reflection, createdAt: `${sample.day}T16:09:00+09:00` },
    }
  })
  fixtureStore.restoreSnapshot({ ...snapshot, children,
    attempts: [...snapshot.attempts.filter(a => !a.attemptId.startsWith(prefix)), ...attempts] })
  // Only the opt-in synthetic child is added; existing children and their sharing stay untouched.
  const owned = mockAccountChildren.get(owner) ?? []
  mockAccountChildren.set(owner, [...owned.filter(c => c.id !== child.id), child])
  if (!mockPremium(child.id)) setMockSubscription(child.id, 'PREMIUM', owner)
  saveSharing(child.id, true)
  for (const attempt of attempts) {
    const answer = attempt.answers.at(-1)!
    const generated = cache?.items?.find(item => item.attemptId === attempt.attemptId && item.answerVersion === answer.version && item.sourceText === answer.text)
    generatedReportDetails.set(attempt.attemptId, generated && typeof generated.text === 'string' && generated.text.trim() && cache
      ? { ...generated, model: cache.model, prompt: cache.promptVersion } : null)
  }
  const report = makeWeekly(child, structuredReportPeriod)
  const items = report.explanations?.items ?? []
  report.inclusionRule = items.length
    ? '기간 내 학습 기록을 바탕으로 정리한 리포트입니다.'
    : '기간 내 학습 기록을 바탕으로 정리한 리포트입니다. 상세 설명을 아직 불러오지 못했습니다.'
  report.narrative = { text: '세 글에서 생활 속 경험과 물건의 특징을 살펴봤어요. 도서관 글에는 이동 시간과 이용할 사람을 덧붙였고, 스마트폰 글에는 장점과 시간 약속을 함께 적었어요. 필통 글은 소중한 이유를 더 이야기해 볼 수 있어요.', source: 'TEMPLATE', modelExplanation: null }
  report.generatedAt = report.revisions[0].generatedAt = '2026-11-16T00:00:00+09:00'
  report.versions = { prompt: cache?.promptVersion ?? 'structured-report-detail@2', model: items.length ? cache?.model ?? null : null }
  reports.set(report.reportId, [report])
  persistFixtureState()
  return report
}

export const structuredReportDemoRequested = () => new URLSearchParams(location.search).get('reportDemo') === 'structured'
export function rememberStructuredReportDemo() { sessionStorage.setItem('sagomungchi:structured-report-demo:v1', 'enabled') }
export const hasStructuredReportDemo = () => sessionStorage.getItem('sagomungchi:structured-report-demo:v1') === 'enabled'
