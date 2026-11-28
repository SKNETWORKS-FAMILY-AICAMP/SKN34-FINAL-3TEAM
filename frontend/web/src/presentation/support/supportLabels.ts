const statusLabels: Record<string, string> = { RECEIVED: '접수', IN_REVIEW: '검토 중', RESOLVED: '처리 완료' }
const categoryLabels: Record<string, string> = {
  ACCOUNT: '계정', USAGE: '이용 방법', PAYMENT: '결제', WRONG_JUDGMENT: '판정이 틀려요',
  ODD_QUESTION: '질문이 이상해요', MISMATCH: '숫자·인용이 달라요', INAPPROPRIATE: '부적절한 표현', OTHER: '기타',
}
const targetLabels: Record<string, string> = { JUDGMENT: '판정', FOLLOWUP: '되묻기', ANALYSIS: '기록에 물어보기', REPORT: '리포트', COMMUNITY_POST: '공유한 생각' }
export const supportStatusLabel = (value: string) => statusLabels[value] ?? '처리 상태 확인 필요'
export const supportCategoryLabel = (value?: string) => (value && categoryLabels[value]) || '문의·신고'
export const supportTargetLabel = (value?: string) => (value && targetLabels[value]) || '학습 결과'
