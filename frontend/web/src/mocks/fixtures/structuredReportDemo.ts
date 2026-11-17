/** Opt-in, synthetic UI data only. No model calls or production report writes. */
import type { Attempt, Child, ThinkingType } from '../../domain/classroom.ts'
import { mockAccountChildren } from './accounts.ts'
import { mockPremium, setMockSubscription } from './payments.ts'
import { fixtureStore, persistFixtureState } from './student.ts'
import { saveSharing } from './sharing.ts'
import { generatedReportDetails, makeWeekly, reports } from './parent.ts'

export const structuredReportChild: Child = { id: 'demo-report-grade5', nickname: '리포트 예시', grade: 5, birthYear: 2015 }
export const structuredReportPeriod = { from: '2026-11-09', to: '2026-11-15' }
const owner = 'parent@example.test'
const prefix = 'structured-report-demo-'
export const structuredReportSamples: { key: string; title: string; question: string; type: ThinkingType; day: string; texts: string[];
  reflection: string }[] = [
  {
    key: 'library', title: '우리 동네에 필요한 시설', type: 'EVALUATE', day: '2026-11-10',
    question: '우리 동네에 필요한 시설을 고르고, 그렇게 생각한 까닭을 써 보세요.',
    texts: [
      '우리 동네에는 도서관이 필요하다. 책을 빌리려면 버스를 타고 멀리 가야 하기 때문이다. 도서관에서 친구들과 숙제도 하고 싶다.',
      '우리 동네에는 도서관이 필요하다. 왜냐하면 지금은 책을 빌리려면 버스를 타고 30분이나 가야 하기 때문이다. 도서관이 생기면 친구들과 같이 숙제도 할 수 있고 어른들도 신문을 읽을 수 있다. 그래서 나는 도서관이 꼭 생겼으면 좋겠다.',
    ],
    reflection: '멀리 간다고만 쓰지 않고 걸리는 시간과 도서관에서 할 일을 덧붙였다.',
  },
  {
    key: 'phone', title: '스마트폰 사용 시간을 정할까요?', type: 'ANALYZE', day: '2026-11-12',
    question: '스마트폰 사용 시간을 정하는 것에 대한 의견과 이유를 써 보세요.',
    texts: ['나는 스마트폰 사용 시간을 정하는 것이 좋다고 생각한다. 밤늦게까지 영상을 보다가 아침에 늦게 일어난 적이 있다. 숙제를 하다가도 알림이 오면 휴대폰을 보게 된다. 스마트폰으로 모르는 내용을 찾아볼 수는 있지만, 영상과 공부를 스스로 나누기는 어렵다. 그래서 부모님과 숙제 뒤에 쓸 시간을 함께 정하고 싶다.'],
    reflection: '좋은 점도 있다는 생각을 쓴 뒤 내 의견으로 돌아오는 부분을 생각했다.',
  },
  {
    key: 'pencil', title: '내가 아끼는 물건', type: 'REFLECT', day: '2026-11-14',
    question: '가장 아끼는 물건의 모습과 소중하게 생각하는 이유를 써 보세요.',
    texts: ['나는 할머니가 주신 필통을 가장 아낀다. 필통은 파란색이고 곰 그림이 있다. 학교에 갈때마다 가지고 간다. 좋다.'],
    reflection: '물건의 모습은 썼지만 왜 아끼는지 더 생각해 보고 싶다.',
  },
]

export interface GemmaReportCache {
  model: string
  promptVersion: string
  items: { attemptId: string; answerVersion: number; sourceText: string; text: string }[]
}

export function seedStructuredReportDemo(cache?: GemmaReportCache) {
  const child = structuredReportChild
  const snapshot = fixtureStore.snapshot()
  const children = [...(snapshot.children ?? []).filter(c => c.id !== child.id), child]
  const attempts: Attempt[] = structuredReportSamples.map(sample => {
    const attemptId = prefix + sample.key
    return {
      attemptId, studentId: child.id, status: 'COMPLETED', helped: false,
      mission: { id: attemptId + '-mission', title: sample.title, grade: child.grade, subject: '국어',
        inputType: 'NARRATIVE', thinkingType: sample.type, question: sample.question, hint: '실제 경험과 구체적인 까닭을 떠올려 보세요.', scene: 'korean' },
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
