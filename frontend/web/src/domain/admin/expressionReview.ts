/** 관리자 표현 검토 (FN-ADM-24, api-spec 2.8·4.1.5, #728). 글만 보이고 학생 이름·ID는 없다(P07) */
export type ExpressionReviewSource = 'GRAY_ZONE' | 'COMMUNITY_REPORT'
export type ExpressionReviewLabel = 'OFFENSIVE' | 'CLEAN' | 'SKIP'
export interface ExpressionReview {
  id: string
  source: ExpressionReviewSource
  /** 그 답변의 학생이 쓴 칸을 줄바꿈으로 이은 글 */
  text: string
  modelVersion: string | null
  label: ExpressionReviewLabel | null
  labeledAt: string | null
  createdAt: string
}
export interface ExpressionReviewFilter { labeled: boolean; source?: ExpressionReviewSource; page: number; size: number }
export const EXPRESSION_REVIEW_SOURCES: Record<ExpressionReviewSource, string> = { GRAY_ZONE: '경계 구간 답변', COMMUNITY_REPORT: '신고 숨김 공유물' }
export const EXPRESSION_REVIEW_LABELS: Record<ExpressionReviewLabel, string> = { OFFENSIVE: '막을 글', CLEAN: '정상', SKIP: '건너뜀' }
export const expressionReviewQuery = (f: ExpressionReviewFilter) => new URLSearchParams({
  labeled: String(f.labeled), ...(f.source ? { source: f.source } : {}), page: String(f.page), size: String(f.size),
}).toString()
/** 다음 쪽이 있는지 (page는 0부터) */
export const hasNextPage = (page: number, size: number, total: number) => (page + 1) * size < total
