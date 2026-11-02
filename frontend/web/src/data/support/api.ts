import { apiFetch } from '../apiClient.ts'
import { json } from '../parent/api.ts'
import type { InquiryCategory, SupportInquiry, SupportReport, SupportTarget } from '../../domain/service.ts'

const id = encodeURIComponent
/** 본인 신고·문의 결과 조회 (API 명세 2.7). 학생·학부모 모두 자기 세션의 건만 받는다. */
export const supportApi = {
  reports: (signal?: AbortSignal) => apiFetch<{ items: SupportReport[] }>('/error-reports', { signal }),
  inquiries: (signal?: AbortSignal) => apiFetch<{ items: SupportInquiry[] }>('/inquiries', { signal }),
  report: (reportId: string, signal?: AbortSignal) => apiFetch<SupportReport>(`/error-reports/${id(reportId)}`, { signal }),
  inquiry: (inquiryId: string, signal?: AbortSignal) => apiFetch<SupportInquiry>(`/inquiries/${id(inquiryId)}`, { signal }),
  /** 같은 신고를 다시 보낼 때는 같은 키를 써야 중복 접수되지 않는다. */
  submitReport: (data: { targetType: SupportTarget; targetId: string; category: string; comment: string }, key: string) =>
    apiFetch<SupportReport>('/error-reports', { ...json(data), headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key } }),
  submitInquiry: (data: { category: InquiryCategory; title: string; body: string }) => apiFetch<SupportInquiry>('/inquiries', json(data)),
}
