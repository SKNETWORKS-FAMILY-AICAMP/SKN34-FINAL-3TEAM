import { Link } from 'react-router'
import { ArrowRight, MessageSquareText } from 'lucide-react'

export function PremiumFeaturePreview({ childId, feature }: { childId: string; feature: 'report' | 'conversation' }) {
  const report = feature === 'report'
  return <section className="premium-feature-preview" aria-label={report ? '프리미엄 리포트 안내' : '기록에 물어보기 이용 안내'}>
    <h3><MessageSquareText size={20} aria-hidden="true" />{report ? '프리미엄으로 한 주의 생각을 더 자세히 읽어 보세요' : '아이의 기록에서 궁금한 점을 물어보세요'}</h3>
    <p>{report ? '무료로 학습 수치를 확인하고, 프리미엄에서는 기록의 요약과 대표 답변의 근거 설명까지 함께 볼 수 있어요.' : '기록에 물어보기는 선택한 자녀와 기간의 학습 기록을 바탕으로 답하고, 답변의 근거를 함께 보여 주는 프리미엄 기능이에요.'}</p>
    {report ? <ul><li>한 주의 기록 · 이번 주 저녁 질문</li><li>대표 답변 설명 · 설명에 사용된 원문 근거</li></ul>
      : <div className="premium-question-example" role="note" aria-label="예시 질문">
        <span className="premium-question-label">예시 질문</span>
        <p>“아이가 생각을 덧붙인 활동을 알려 줘.”</p>
      </div>}
    <Link className="cj-secondary premium-compare-link" to={`/parent/billing?childId=${encodeURIComponent(childId)}#plan-compare`}>무료·프리미엄 비교 및 이용권 보기 <ArrowRight size={16} aria-hidden="true" /></Link>
  </section>
}
