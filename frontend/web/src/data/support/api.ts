import { apiFetch } from '../apiClient.ts'
import type { SupportInquiry, SupportReport } from '../../domain/service.ts'

const id = encodeURIComponent
/** 본인 신고·문의 결과 조회 (API 명세 2.7). 학생·학부모 모두 자기 세션의 건만 받는다. */
export const supportApi = {
  reports: (signal?: AbortSignal) => apiFetch<{ items: SupportReport[] }>('/error-reports', { signal }),
  inquiries: (signal?: AbortSignal) => apiFetch<{ items: SupportInquiry[] }>('/inquiries', { signal }),
  report: (reportId: string, signal?: AbortSignal) => apiFetch<SupportReport>(`/error-reports/${id(reportId)}`, { signal }),
  inquiry: (inquiryId: string, signal?: AbortSignal) => apiFetch<SupportInquiry>(`/inquiries/${id(inquiryId)}`, { signal }),
}
