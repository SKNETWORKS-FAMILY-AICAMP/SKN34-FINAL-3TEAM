import { apiFetch } from '../apiClient.ts'
import { json } from '../parent/api.ts'
import type { Period } from '../../domain/classroom.ts'
import type { ItemList, Inquiry, AdminNotice, NoticeCommand, AdminPayment, RefundRequest, ReconciliationItem } from '../../domain/admin/service.ts'
const id=encodeURIComponent
// Public core contracts: SupportController / PaymentController. No fallback to demo on errors.
export const adminServiceApi={
 inquiries:(page=0,signal?:AbortSignal)=>apiFetch<ItemList<Inquiry>&{totalElements:number}>(`/admin/inquiries?page=${page}&size=20`,{signal}),
 answer:(key:string,answer:string)=>apiFetch<Inquiry>(`/admin/inquiries/${id(key)}/answer`,json({answer})),
 notices:(page=0,signal?:AbortSignal)=>apiFetch<ItemList<AdminNotice>&{totalElements:number}>(`/notices?page=${page}&size=20`,{signal}),
 saveNotice:(data:NoticeCommand,key?:string)=>apiFetch<AdminNotice>(`/admin/notices${key?'/'+id(key):''}`,json(data,key?'PATCH':'POST')),
 endNotice:(key:string)=>apiFetch<AdminNotice>(`/admin/notices/${id(key)}`,{method:'DELETE'}),
 payments:(period:Period,page=0,signal?:AbortSignal)=>apiFetch<ItemList<AdminPayment>>(`/admin/payments?${new URLSearchParams({...period,page:String(page),size:'20'})}`,{signal}),
 refunds:(page=0,signal?:AbortSignal)=>apiFetch<ItemList<RefundRequest>>(`/admin/refund-requests?page=${page}&size=20`,{signal}),
 approve:(key:string,receipt:string)=>apiFetch<RefundRequest>(`/admin/refund-requests/${id(key)}/approve`,{method:'POST',headers:{'Idempotency-Key':receipt}}),
 reject:(key:string,reason:string)=>apiFetch<RefundRequest>(`/admin/refund-requests/${id(key)}/reject`,json({reason})),
 reconciliation:(period:Period,page=0,signal?:AbortSignal)=>apiFetch<ItemList<ReconciliationItem>>(`/admin/payments/reconciliation?${new URLSearchParams({...period,page:String(page),size:'20'})}`,{signal}),
}
