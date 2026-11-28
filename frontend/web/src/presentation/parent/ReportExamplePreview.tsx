import { thinkingLabels, type ThinkingType } from '../../domain/classroom.ts'
import { BookOpen, MessageCircle } from 'lucide-react'
import preview from '../../data/examples/reportPreview.json'
import { ReportExplanationBody } from './ReportExplanations.tsx'
import { ReportDialogNavigation } from './ReportDialogNavigation.tsx'
import { useReportDialogHistory } from './useReportDialogHistory.ts'
import './report-example-preview.css'

const structuredReportSamples = preview.samples.map(sample => ({ ...sample, key: sample.attemptId, type: sample.type as ThinkingType }))
const structuredReportSummaryLead = '세 글에서 생활 속 경험과 물건의 특징을 살펴봤어요.'
const structuredReportSummaryDetail = '도서관 글에는 이동 시간과 이용할 사람을 덧붙였고, 스마트폰 글에는 장점과 시간 약속을 함께 적었어요. 필통 글은 소중한 이유를 더 이야기해 볼 수 있어요.'

/** Self-contained illustrative content. Never used as a fallback for real report analysis. */
export default function ReportExamplePreview() {
  const history = useReportDialogHistory([structuredReportSamples[0].key], (a, b) => a === b)
  const activity = structuredReportSamples.find(item => item.key === history.current)!
  const explanation = JSON.stringify(activity.explanation)
  return <div className="report-example-preview">
    <p className="report-example-notice" role="note">{preview.notice}</p>
    <div className="report-dialog-topline"><ReportDialogNavigation {...history} /><p className="report-example-period">2026-11-09 ~ 2026-11-15 · 활동 {structuredReportSamples.length}개</p></div>
    <section className="report-week-overview" aria-labelledby="report-example-summary">
      <h3 id="report-example-summary"><BookOpen size={27} aria-hidden="true" />한 주의 기록</h3>
      <div className="report-week-overview-copy"><p className="report-week-lead">{structuredReportSummaryLead}</p><p>{structuredReportSummaryDetail}</p></div>
    </section>
    <section className="weekly-activity-records report-example-activities" aria-labelledby="report-example-activities">
      <div className="report-example-section-heading"><h3 id="report-example-activities">활동별 기록</h3><span>{structuredReportSamples.length}개 활동</span></div>
      <nav className="report-example-activity-nav" aria-label="예시 활동 선택">
        {structuredReportSamples.map(item => <button type="button" key={item.key} aria-pressed={history.current === item.key}
          onClick={() => history.navigate(item.key)}>
          <span className="report-example-activity-title">{item.title}</span>
          <span className="report-example-activity-meta">{item.day.slice(5).replace('-', '.')} · {thinkingLabels[item.type]}</span>
        </button>)}
      </nav>
      <div className="report-example-columns report-reader-layout" key={activity.key}>
        <div className="report-example-source report-reader-document">
          <h3 className="report-reader-document-title">{activity.title}</h3>
          <section><h4>처음 제시된 문제</h4><p>{activity.question}</p></section>
          <section className="report-explanation-evidence"><h4>학생 글 전체</h4><blockquote>{activity.texts.at(-1)}</blockquote></section>
          {activity.texts.length > 1 && <details><summary>처음 답변과 비교하기</summary><blockquote>{activity.texts[0]}</blockquote></details>}
        </div>
        <aside className="report-reader-feedback" aria-label="대표 답변 설명과 돌아보기">
        <section className="report-explanations" aria-label="대표 답변 설명 예시">
          <h4 className="report-explanation-title">대표 답변 설명</h4>
          <ReportExplanationBody text={explanation} studentName="" showSectionIcons />
        </section>
        <section className="report-example-reflection"><h4><MessageCircle size={18} aria-hidden="true" />돌아보기</h4><p>{activity.reflection}</p></section>
        </aside>
      </div>
    </section>
  </div>
}
