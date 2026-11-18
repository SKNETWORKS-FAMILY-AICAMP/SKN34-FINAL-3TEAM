export const jobTypeLabel: Record<string, string> = { CONVERSATION: '분석 대화', REPORT: '주간 리포트', NOTIFICATION: '알림' }
export const reportStatusLabel: Record<string, string> = { RECEIVED: '접수', IN_REVIEW: '검토 중', RESOLVED: '처리 완료' }
export const modelKindLabel: Record<string, string> = { RUBRIC: '판정 기준', MODEL: '판정 모델', PROMPT: '프롬프트', GENERATION: '생성 설정' }
export const number = (v: number) => v.toLocaleString('ko-KR')
export { formatKoreanDateTime as date } from '../common/dateTime.ts'
