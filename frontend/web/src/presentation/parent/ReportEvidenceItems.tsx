import { BookOpen } from 'lucide-react'
import type { Evidence } from '../../domain/parent.ts'
import { evidenceQuoteBlocks } from '../../domain/reportEvidence.ts'
import { formatKoreanDateTime } from '../common/dateTime.ts'

export function ReportEvidenceItems({ items }: { items: Evidence[] }) {
  return <div className="report-evidence-items">
    {!items.length && <p>연결된 근거가 없습니다.</p>}
    {items.map((item, index) => <article className="report-evidence-item" key={index}>
      <header className="report-evidence-heading"><BookOpen size={22} aria-hidden="true" /><h3>{item.missionTitle ?? '관련 미션'}</h3></header>
      <div className="report-evidence-meta"><span>{item.kind === 'REFLECTION' ? '돌아보기' : `답변 ${item.answerVersion ?? '확인 전'}`}</span><span>{item.submittedAt ? formatKoreanDateTime(item.submittedAt) : '시점 정보 없음'}</span></div>
      {item.available ? <section className="report-evidence-response">
        <h4>{item.kind === 'REFLECTION' ? '아이의 돌아보기' : '아이의 답변'}</h4>
        <blockquote>{evidenceQuoteBlocks(item.quote ?? '인용 정보 없음').map((block, blockIndex) =>
          <div className="report-evidence-step" data-final={block.final || undefined} key={blockIndex}>
            {block.label && <p className="report-evidence-prompt">{block.label}</p>}
            <p className="report-evidence-answer">{block.text}</p>
          </div>)}
        </blockquote>
      </section> : <p role="status">이용 불가 · 삭제된 근거입니다. 다른 기록으로 대체하지 않습니다.</p>}
    </article>)}
  </div>
}
