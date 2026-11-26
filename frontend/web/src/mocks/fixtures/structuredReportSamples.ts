/** UI preview and RunPod generation share the same committed synthetic source. */
import type { ThinkingType } from '../../domain/classroom.ts'
import demoData from './structuredReportSamples.json' with { type: 'json' }

export const structuredReportSamples = demoData.samples.map(sample => ({
  ...sample,
  key: sample.attemptId.replace('structured-report-demo-', ''),
  type: sample.type as ThinkingType,
}))
export const structuredReportSummaryLead = '세 글에서 생활 속 경험과 물건의 특징을 살펴봤어요.'
export const structuredReportSummaryDetail = '도서관 글에는 이동 시간과 이용할 사람을 덧붙였고, 스마트폰 글에는 장점과 시간 약속을 함께 적었어요. 필통 글은 소중한 이유를 더 이야기해 볼 수 있어요.'
export const structuredReportSummary = `${structuredReportSummaryLead} ${structuredReportSummaryDetail}`
