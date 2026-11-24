import { useState } from 'react'
import { thinkingLabels } from '../../domain/classroom.ts'
import { parentApi } from '../../data/parent/api.ts'
import { useParentQuery } from '../../data/parent/queries.ts'
import type { ReportExplanation, WeeklyReport } from '../../domain/parent.ts'
import { reportPeriodType } from '../../domain/parent.ts'
import { explanationBlocks, explanationSections } from '../../domain/reportExplanation.ts'

function ExplanationBody({ text }: { text: string }) {
  return <div className="report-explanation-sections">{explanationSections(text).map((section, index) =>
    <div className="report-explanation-section" key={index}>
      <h5>{section.title}</h5>
      <div className="report-explanation-copy">{explanationBlocks(section.body).map((block, blockIndex) => {
        if (block.kind === 'paragraph') return <p key={blockIndex}>{block.text}</p>
        const List = block.ordered ? 'ol' : 'ul'
        return <List key={blockIndex}>{block.items.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</List>
      })}</div>
    </div>)}</div>
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
    <h5>학생 글 전체</h5>
    {original ? <blockquote>{original.quote}</blockquote>
      : item.itemId && query.isPending ? <p role="status">원문 전체를 불러오고 있습니다.</p>
      : <p role="status">이 설명에 연결된 원문 전체를 확인할 수 없습니다.</p>}
  </div>
}

/** narrativeEnabled: entitlement 조회 값(#602). 조회 전·실패면 undefined이며 서버의 explanations만 따른다. */
export function ReportExplanations({ report, narrativeEnabled }: { report: WeeklyReport; narrativeEnabled?: boolean }) {
  const [selected,setSelected] = useState('')
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
    {notice ? <p role="note">{notice}</p> : <div className="report-explanation-reader"><label>답변 선택<select aria-label="설명할 답변 선택" value={items!.some(x=>x.answerId===selected) ? selected : items![0].answerId} onChange={e=>setSelected(e.target.value)}>{items!.map(item=><option key={item.answerId} value={item.answerId}>{item.missionTitle} · {thinkingLabels[item.thinkingType]}</option>)}</select></label>{items!.filter(item=>item.answerId===(items!.some(x=>x.answerId===selected) ? selected : items![0].answerId)).map(item => <article className="report-explanation-card" key={`${item.answerId}:${item.answerVersion}`}>
      <h4>{item.missionTitle}</h4>
      <p>{thinkingLabels[item.thinkingType]} · <span className="ws-tag">AI 관찰</span></p>
      <details className="report-original-disclosure"><summary>학생 글 전체 보기</summary><OriginalAnswer report={report} item={item} /></details>
      <ExplanationBody text={item.text} />
    </article>)}</div>}
  </section>
}
