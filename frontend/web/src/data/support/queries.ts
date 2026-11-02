import { useQuery } from '@tanstack/react-query'
import type { SupportInquiry, SupportReport } from '../../domain/service.ts'
import { supportApi } from './api.ts'

/** 내 신고·문의 목록과 선택한 한 건. 세션이 바뀌면 다른 키로 조회해 이전 사용자의 결과를 섞지 않는다. */
export function useSupportResults(session: unknown, reportId: string | null, inquiryId: string | null) {
  return {
    reports: useQuery({ queryKey: ['support', session, 'reports'], retry: false,
      queryFn: ({ signal }) => supportApi.reports(signal) }),
    inquiries: useQuery({ queryKey: ['support', session, 'inquiries'], retry: false,
      queryFn: ({ signal }) => supportApi.inquiries(signal) }),
    detail: useQuery<SupportReport | SupportInquiry>({ queryKey: ['support', session, reportId, inquiryId], retry: false,
      enabled: !!reportId || !!inquiryId,
      queryFn: ({ signal }) => reportId ? supportApi.report(reportId, signal) : supportApi.inquiry(inquiryId!, signal) }),
  }
}
