export type ItemList<T> = { items: T[] }
export interface Inquiry { inquiryId:string;category:string;title:string;body:string;status:string;answer:string|null;createdAt:string;answeredAt?:string|null }
export interface AdminNotice { noticeId:string;kind:'NOTICE'|'MAINTENANCE';title:string;body:string;targetRoles:('PARENT'|'STUDENT'|'ADMIN')[];visibleFrom:string;visibleTo:string|null;endedAt:string|null }
export type NoticeCommand = Omit<AdminNotice,'noticeId'|'endedAt'>
export interface AdminPayment { paymentId:string|null;orderId:string;childId:string;amount:number;status:string;entitlementStatus:string|null;approvedAt:string|null;failureCode:string|null }
export interface RefundRequest { id:string;paymentId:string;amount:number;reason:string;status:string;rejectReason:string|null;pgStatus:string|null;createdAt:string;usageVerifiedAt:string|null }
export interface ReconciliationItem { orderId:string;localStatus:string|null;pgStatus:string|null;result:string;entitlementStatus:string|null;source:string }
export const refundStatusLabel:Record<string,string>={REQUESTED:'승인 대기',APPROVED:'승인됨 · PG 확인 중',COMPLETED:'환불 완료',REJECTED:'반려',FAILED:'처리 실패'}
