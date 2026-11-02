import { http } from 'msw/http'
import { guard, respond } from './student.ts'
import { fail } from './parent.ts'
import { cases, notices, answerCase } from './service.ts'
import { fixtureStore as store } from '../fixtures/student.ts'
import { workspaceScenario } from '../fixtures/accounts.ts'
import type { AdminNotice, AdminPayment, RefundRequest, NoticeCommand } from '../../domain/admin/service.ts'
const stamp=new Date().toISOString()
const seedInquiry={id:'demo-admin-inquiry',owner:'parent@example.test:PARENT:',kind:'inquiries',category:'USAGE',comment:'학습 기록은 어디서 확인하나요?',status:'RECEIVED' as const,createdAt:stamp}
if(!cases.some(c=>c.id===seedInquiry.id))cases.push(seedInquiry)
export const demoRefunds:RefundRequest[]=[
 {id:'demo-refund-1',paymentId:'demo-payment-1',amount:14900,reason:'이용 전 환불을 요청합니다.',status:'REQUESTED',rejectReason:null,pgStatus:null,createdAt:stamp,usageVerifiedAt:stamp},
 {id:'demo-refund-2',paymentId:'demo-payment-2',amount:14900,reason:'가상 환불 완료 사례',status:'COMPLETED',rejectReason:null,pgStatus:'CANCELED',createdAt:stamp,usageVerifiedAt:stamp},
]
const demoPayments:AdminPayment[]=demoRefunds.map((r,i)=>({paymentId:r.paymentId,orderId:'DEMO-ORDER-'+(i+1),childId:'가상 자녀 '+(i+1),amount:r.amount,status:i===1?'REFUNDED':'APPROVED',entitlementStatus:i===1?'REVOKED':'APPLIED',approvedAt:stamp,failureCode:null}))
const receipts=new Map<string,{requestId:string;data:RefundRequest}>()
function admin(request:Request,permission:string){guard(request);const s=store.snapshot().session;if(s?.role!=='ADMIN'||!s.permissions?.includes(permission as 'SERVICE_OPS'))fail('FORBIDDEN','필요한 관리자 권한이 없습니다.',403);if(workspaceScenario==='forbidden')fail('FORBIDDEN','권한 시연',403);if(workspaceScenario==='query-fail')fail('SERVICE_UNAVAILABLE','조회 실패 시연',503)}
function list<T>(request:Request,rows:T[]){const q=new URL(request.url).searchParams,p=Number(q.get('page')??0),size=Number(q.get('size')??20);if(!Number.isInteger(p)||p<0||!Number.isInteger(size)||size<1||size>100)fail('VALIDATION_FAILED','페이지를 확인해 주세요.',400);const data=workspaceScenario==='empty'?[]:rows;return {items:data.slice(p*size,(p+1)*size),page:p,size,totalElements:data.length}}
function noticeView(n:typeof notices[number]):AdminNotice{return {noticeId:n.id,kind:(n as unknown as AdminNotice).kind??'NOTICE',title:n.title,body:n.content,targetRoles:n.roles as AdminNotice['targetRoles'],visibleFrom:n.startsAt,visibleTo:n.endsAt,endedAt:(n as unknown as AdminNotice).endedAt??null}}
function inquiryView(c:typeof cases[number]){return {...c,inquiryId:c.id,title:c.comment.slice(0,60),body:c.comment,answer:c.answer??null}}
export const adminServiceHandlers=[
 http.get('/api/v1/admin/inquiries',({request})=>respond(async()=>{admin(request,'SERVICE_OPS');return list(request,cases.filter(c=>c.kind==='inquiries').map(inquiryView))})),
 http.post('/api/v1/admin/inquiries/:id/answer',({request,params})=>respond(async()=>{admin(request,'SERVICE_OPS');const data=await request.json() as {answer:string};const c=cases.find(c=>c.id===params.id);if(!c)fail('NOT_FOUND','문의가 없습니다.',404);if(c!.status==='RESOLVED'&&c!.answer!==data.answer)fail('CONFLICT','처리 완료한 답변은 바꿀 수 없습니다.',409);return inquiryView(answerCase(String(params.id),data.answer)!)})),
 http.get('/api/v1/notices',({request})=>respond(async()=>{guard(request);const role=store.snapshot().session!.role;const rows=notices.filter(n=>n.roles.includes(role)&&Date.parse(n.startsAt)<=Date.now()&&(!n.endsAt||Date.parse(n.endsAt)>Date.now())&&!(n as unknown as AdminNotice).endedAt);return list(request,rows.map(n=>({...n,...noticeView(n)})))})),
 ...(['post','patch'] as const).map(method=>http[method]('/api/v1/admin/notices'+(method==='patch'?'/:id':''),({request,params})=>respond(async()=>{
  admin(request,'SERVICE_OPS');const d=await request.json() as NoticeCommand
  if(!['NOTICE','MAINTENANCE'].includes(d.kind)||!d.title?.trim()||d.title.length>200||!d.body?.trim()||d.body.length>4000||!Array.isArray(d.targetRoles)||!d.targetRoles.length||new Set(d.targetRoles).size!==d.targetRoles.length||d.targetRoles.some(r=>!['PARENT','STUDENT','ADMIN'].includes(r))||!Number.isFinite(Date.parse(d.visibleFrom))||(d.visibleTo&&Date.parse(d.visibleTo)<=Date.parse(d.visibleFrom)))fail('VALIDATION_FAILED','공지 내용·공개 기간을 확인해 주세요.',400)
  let n=notices.find(n=>n.id===params.id);if(method==='patch'&&!n)fail('NOT_FOUND','공지가 없습니다.',404);if(n&&(n as unknown as AdminNotice).endedAt)fail('CONFLICT','종료한 공지는 수정할 수 없습니다.',409)
  if(!n){n={id:crypto.randomUUID(),title:d.title,content:d.body,roles:d.targetRoles,startsAt:d.visibleFrom,endsAt:d.visibleTo};notices.push(n)}
  Object.assign(n,{kind:d.kind,title:d.title,content:d.body,roles:d.targetRoles,startsAt:d.visibleFrom,endsAt:d.visibleTo});return noticeView(n)
 },method==='post'?201:200))),
 http.delete('/api/v1/admin/notices/:id',({request,params})=>respond(async()=>{admin(request,'SERVICE_OPS');const n=notices.find(n=>n.id===params.id);if(!n)fail('NOT_FOUND','공지가 없습니다.',404);Object.assign(n!,{endedAt:(n as unknown as AdminNotice).endedAt??new Date().toISOString()});return noticeView(n!)})),
 http.get('/api/v1/admin/payments',({request})=>respond(async()=>{admin(request,'PAYMENT_VIEW');return list(request,demoPayments)})),
 http.get('/api/v1/admin/refund-requests',({request})=>respond(async()=>{admin(request,'PAYMENT_VIEW');return list(request,demoRefunds)})),
 http.post('/api/v1/admin/refund-requests/:id/approve',({request,params})=>respond(async()=>{
  admin(request,'PAYMENT_REFUND');const key=request.headers.get('Idempotency-Key');if(!key)fail('VALIDATION_FAILED','멱등 키가 필요합니다.',400)
  const previous=receipts.get(key!);if(previous){if(previous.requestId!==params.id)fail('CONFLICT','같은 키로 다른 환불을 처리할 수 없습니다.',409);return structuredClone(previous.data)}
  const r=demoRefunds.find(r=>r.id===params.id);if(!r)fail('NOT_FOUND','환불 요청이 없습니다.',404);if(r!.status==='COMPLETED')return r;if(r!.status==='APPROVED')return r;if(r!.status!=='REQUESTED'||!r!.usageVerifiedAt)fail('REFUND_NOT_READY','승인할 수 없는 상태입니다.',409)
  r!.status='APPROVED';r!.pgStatus='PENDING';receipts.set(key!,{requestId:r!.id,data:structuredClone(r!)});return r
 },202)),
 http.post('/api/v1/admin/refund-requests/:id/reject',({request,params})=>respond(async()=>{admin(request,'PAYMENT_REFUND');const d=await request.json() as {reason:string};if(!d.reason?.trim()||d.reason.length>200)fail('VALIDATION_FAILED','반려 사유는 200자 이내로 입력해 주세요.',400);const r=demoRefunds.find(r=>r.id===params.id);if(!r)fail('NOT_FOUND','환불 요청이 없습니다.',404);if(!['REQUESTED','FAILED'].includes(r!.status))fail('REFUND_STATE_CHANGED','처리할 수 없는 상태입니다.',409);r!.status='REJECTED';r!.rejectReason=d.reason;return r})),
 http.get('/api/v1/admin/payments/reconciliation',({request})=>respond(async()=>{admin(request,'PAYMENT_VIEW');const q=new URL(request.url).searchParams;if(!q.get('from')||!q.get('to')||q.get('from')!>q.get('to')!)fail('INVALID_DATE_RANGE','조회 기간을 확인해 주세요.',409);return list(request,demoPayments.map((p,i)=>({orderId:p.orderId,localStatus:p.status,pgStatus:i?'CANCELED':'DONE',result:'MATCH',entitlementStatus:p.entitlementStatus,source:'LOCAL'})))})),
]
