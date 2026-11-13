import { thinkingLabels } from '../../domain/classroom.ts'
import type { WeeklyReport } from '../../domain/parent.ts'
import { reportPeriodType } from '../../domain/parent.ts'

/** narrativeEnabled: entitlement 조회 값(#602). 조회 전·실패면 undefined이며 서버의 explanations만 따른다. */
export function ReportExplanations({ report, narrativeEnabled }: { report: WeeklyReport; narrativeEnabled?: boolean }) {
  if (reportPeriodType(report) === 'DAILY' || report.status !== 'COMPLETED') return null
  let notice = ''
  let items = report.explanations?.items
  if (report.parentSharingEnabled !== true) notice = '답변 원문이 비공개이거나 공개 여부를 확인하지 못해 AI 관찰 설명을 표시하지 않습니다.'
  else if (!report.explanations) notice = narrativeEnabled === false
    ? 'AI 관찰 설명은 프리미엄 이용권에서 제공합니다.'
    : '이 리포트에는 AI 관찰 설명 정보가 제공되지 않았습니다.'
  else if (report.explanations.state === 'NOT_INCLUDED') notice = '설명 미포함 · 설명을 제공하지 못했습니다. 아래 학습 수치와 기록은 계속 확인할 수 있습니다.'
  else if (report.explanations.state === 'NO_TARGET') notice = '설명 대상 답변이 없어 AI 관찰 설명이 포함되지 않았습니다.'
  else if (report.explanations.state !== 'INCLUDED' || !Array.isArray(items) || !items.length || items.length > 3 ||
    items.some(item => !item || !item.attemptId || !item.answerId || !Number.isSafeInteger(item.answerVersion) || item.answerVersion < 1 ||
      !Object.hasOwn(thinkingLabels, item.thinkingType) || typeof item.missionTitle !== 'string' || !item.missionTitle.trim() ||
      (item.quote !== null && (typeof item.quote !== 'string' || !item.quote.trim())) || typeof item.text !== 'string' || !item.text.trim())) {
    notice = 'AI 관찰 설명 정보를 확인하지 못했습니다. 학습 수치와 기록은 계속 확인할 수 있습니다.'
  }
  if (notice) items = undefined
  return <section className="report-explanations" aria-labelledby="report-explanations-title">
    <h3 id="report-explanations-title">대표 답변 설명</h3>
    {notice ? <p role="note">{notice}</p> : <div className="ws-stack">{items!.map(item => <article className="ws-card" key={`${item.answerId}:${item.answerVersion}`}>
      <h4>{item.missionTitle}</h4>
      <p>{thinkingLabels[item.thinkingType]} · <span className="ws-tag">AI 관찰</span></p>
      {item.quote !== null && <blockquote>{item.quote}</blockquote>}
      <p className="report-explanation-text">{item.text}</p>
    </article>)}</div>}
  </section>
}
