import { thinkingLabels } from '../../domain/classroom.ts'
import { Lightbulb, PencilLine, TextSearch } from 'lucide-react'
import { parentApi } from '../../data/parent/api.ts'
import { useParentQuery } from '../../data/parent/queries.ts'
import type { ReportExplanation, WeeklyReport } from '../../domain/parent.ts'
import { reportPeriodType } from '../../domain/parent.ts'
import { explanationBlocks, explanationSections, personalizeExplanation } from '../../domain/reportExplanation.ts'

const sectionIcons = { '상세 분석': TextSearch, '보완할 지점': PencilLine, '개선 방안': Lightbulb }

/** Add reading breaks only; keep the model's sentences and their order unchanged. */
function readableParagraphs(text: string) {
  if (text.length < 320) return [text]
  const sentences = Array.from(new Intl.Segmenter('ko', { granularity: 'sentence' }).segment(text), item => item.segment)
  const paragraphs: string[] = []
  let current = ''
  for (const sentence of sentences) {
    if (current.length >= 180 && current.length + sentence.length > 280) { paragraphs.push(current.trim()); current = '' }
    current += sentence
  }
  if (current.trim()) paragraphs.push(current.trim())
  return paragraphs
}

export function ReportExplanationBody({ text, studentName, showSectionIcons = false }: { text: string; studentName: string; showSectionIcons?: boolean }) {
  return <div className="report-explanation-sections">{explanationSections(text).map((section, index) =>
    <div className="report-explanation-section" key={index}>
      <h5>{showSectionIcons && <ExplanationSectionIcon title={section.title} />}{section.title}</h5>
      <div className="report-explanation-copy">{explanationBlocks(personalizeExplanation(section.body, studentName)).map((block, blockIndex) => {
        if (block.kind === 'paragraph') return readableParagraphs(block.text).map((text, paragraphIndex) => <p key={`${blockIndex}-${paragraphIndex}`}>{text}</p>)
        const List = block.ordered ? 'ol' : 'ul'
        return <List key={blockIndex}>{block.items.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</List>
      })}</div>
    </div>)}</div>
}

function ExplanationSectionIcon({ title }: { title: string }) {
  const Icon = sectionIcons[title as keyof typeof sectionIcons]
  return Icon ? <Icon size={19} aria-hidden="true" /> : null
}

function OriginalAnswer({ report, item }: { report: WeeklyReport; item: ReportExplanation }) {
  const query = useParentQuery(
    ['report-original', report.childId, report.reportId, report.revision, item.itemId, item.answerId, item.answerVersion],
    (signal) => parentApi.reportEvidence(report.reportId, item.itemId!, signal),
    !!item.itemId,
  )
  const original = !query.error && query.data?.items.find(source => source.available === true &&
    source.attemptId === item.attemptId && source.answerId === item.answerId && source.answerVersion === item.answerVersion &&
    typeof source.quote === 'string' && source.quote.trim())
  return <div className="report-explanation-evidence">
    <h4>학생 글 전체</h4>
    {original ? <blockquote>{original.quote}</blockquote>
      : item.itemId && query.isPending ? <p role="status">원문 전체를 불러오고 있습니다.</p>
      : <p role="status">이 설명에 연결된 원문 전체를 확인할 수 없습니다.</p>}
  </div>
}

export function reportExplanationItems(report: WeeklyReport): ReportExplanation[] {
  if (reportPeriodType(report) === 'DAILY' || report.status !== 'COMPLETED' ||
      report.parentSharingEnabled !== true || report.explanations?.state !== 'INCLUDED') return []
  const items = report.explanations.items
  if (!Array.isArray(items) || !items.length) return []
  return items.filter(item => item && item.attemptId && item.answerId &&
    Number.isSafeInteger(item.answerVersion) && item.answerVersion >= 1 &&
    Object.hasOwn(thinkingLabels, item.thinkingType) &&
    typeof item.missionTitle === 'string' && item.missionTitle.trim() &&
    (item.quote === null || typeof item.quote === 'string' && item.quote.trim()) &&
    typeof item.text === 'string' && item.text.trim())
}

export function ReportExplanations({ report, attemptId, narrativeEnabled, studentName }: {
  report: WeeklyReport
  studentName: string
  attemptId?: string
  narrativeEnabled?: boolean
}) {
  if (reportPeriodType(report) === 'DAILY' || report.status !== 'COMPLETED') return null
  const items = reportExplanationItems(report)
  const matching = items.filter(item => item.attemptId === attemptId)
  let notice = ''
  if (report.parentSharingEnabled !== true) notice = '답변 원문이 비공개이거나 공개 여부를 확인하지 못해 대표 답변 설명을 표시하지 않습니다.'
  else if (narrativeEnabled === false) notice = '대표 답변 설명은 프리미엄 이용권에서 제공합니다.'
  else if (!report.explanations) notice = '이 리포트에는 대표 답변 설명 정보가 제공되지 않았습니다.'
  else if (report.explanations.state === 'NOT_INCLUDED') notice = '이 리포트에 대표 답변 설명이 포함되지 않았습니다.'
  else if (report.explanations.state === 'NO_TARGET') notice = '대표 답변 설명에 해당하는 답변 기록이 없습니다.'
  else if (!items.length) notice = '대표 답변 설명 정보를 확인하지 못했습니다.'
  else if (!matching.length) notice = '이 활동의 답변에 연결된 대표 답변 설명이 없습니다.'

  return <section className="report-explanations" aria-label="대표 답변 설명">
    {notice ? <p role="note">{notice}</p> : matching.map(item =>
      <article className="report-explanation-card report-reader-layout" key={item.itemId ?? item.answerId}>
        <div className="report-reader-document"><OriginalAnswer report={report} item={item} /></div>
        <aside className="report-reader-feedback" aria-label="대표 답변 설명 내용">
        <h4 className="report-explanation-title">대표 답변 설명</h4>
        <ReportExplanationBody text={item.text} studentName={studentName} showSectionIcons />
        </aside>
      </article>)}
  </section>
}
