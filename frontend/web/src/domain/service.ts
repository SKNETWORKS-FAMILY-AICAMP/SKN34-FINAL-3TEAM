export type SupportTarget = 'FOLLOWUP' | 'JUDGMENT' | 'ANALYSIS' | 'REPORT'
export type InquiryCategory = 'ACCOUNT' | 'USAGE' | 'PAYMENT'
/** 본인 신고·문의 처리 결과 (core OpenAPI `SupportReport`·`SupportInquiry`에서 화면이 쓰는 필드). */
export type SupportReport = { reportId: string; status: string; targetType?: SupportTarget; targetId?: string; category?: string; comment: string | null; reviewReason: string | null; createdAt?: string }
export type SupportInquiry = { inquiryId: string; status: string; category?: InquiryCategory; title: string; body: string; answer: string | null; createdAt?: string }
/** 사용자 공지·도움말 (core OpenAPI `GET /notices`·`GET /help`). */
export type Notice = { noticeId: string; kind: 'NOTICE' | 'MAINTENANCE'; title: string; body: string; targetRoles: string[]; visibleFrom: string; visibleTo: string | null; endedAt: string | null }
export type HelpItem = { title: string; body: string }
export const notificationLabels = {
  REPORT_COMPLETED: '리포트 생성 완료', REPORT_FAILED: '리포트 생성 실패', ERROR_REPORT_RESOLVED: '오류 신고 처리',
  INQUIRY_ANSWERED: '문의 답변', PAYMENT_CHANGED: '결제 변경', SUBSCRIPTION_CHANGED: '구독 변경',
} as const
export type NotificationType = keyof typeof notificationLabels
export type NotificationItem = { id: string; childId: string | null; type: NotificationType; title: string; link: string; readAt: string | null; createdAt: string }
export type NotificationSettings = { items: { type: NotificationType; enabled: boolean }[] }
export type ReauthPurpose = 'PIN_CHANGE' | 'CHILD_UNLINK' | 'CHILD_DELETE' | 'WITHDRAWAL'
export type DeletionScope = 'PROFILE' | 'RECORDS'
export type DeletionRequest = { deletionRequestId: string; childId: string; scope: DeletionScope; status: string; completedServices: string[] }
/** 알림 링크도 같은 출처와 현재 역할의 화면만 허용한다. */
export function notificationPath(link: string, role: string, origin: string): string | null {
  try {
    const url = new URL(link, origin)
    if (url.origin !== origin || !url.pathname.startsWith('/' + role.toLowerCase() + '/')) return null
    if (url.pathname.includes('//') || url.username || url.password) return null
    return url.pathname + url.search
  } catch { return null }
}
