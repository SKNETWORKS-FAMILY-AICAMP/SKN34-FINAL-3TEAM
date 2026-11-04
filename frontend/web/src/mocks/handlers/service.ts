import { requireNoPendingTransfer, transferUnavailableChildren, replaceTransferChildren } from '../fixtures/guardianTransfers.ts'
import { http, HttpResponse } from 'msw/http'
import { fixtureStore as store } from '../fixtures/student.ts'
import { mockIdentity } from '../fixtures/accounts.ts'
import { guard, respond } from './student.ts'
import { parentGuard, parentChild, fail, page, consumeActionReauth } from './parent.ts'
import { notificationLabels } from '../../domain/service.ts'
import type { SupportTarget, NotificationItem, NotificationSettings } from '../../domain/service.ts'
import type { DeletionRequest } from '../../domain/service.ts'
import { errorReports,reportedAttemptIds } from '../fixtures/admin/operations.ts'
import { reports,conversations } from '../fixtures/parent.ts'
const deletions = new Map<string, DeletionRequest & { owner: string }>()
const withdrawalReceipts = new Map<string, {withdrawalRequestId:string;status:string}>()
// 시연 저장 모양. 응답은 아래 *View로 core OpenAPI(`SupportReport`·`SupportInquiry`) 모양으로 바꿔 보낸다.
type OwnedCase = { id: string; owner: string; kind: string; key?: string; targetType?: SupportTarget; targetId?: string; category: string; title?: string; comment: string; status: 'RECEIVED' | 'IN_REVIEW' | 'RESOLVED'; answer?: string; createdAt: string }
type MockNotice = { id: string; title: string; content: string; roles: string[]; startsAt: string; endsAt: string | null }
export const cases: OwnedCase[] = []
const inbox = new Map<string, NotificationItem[]>()
const settings = new Map<string, NotificationSettings>()
export const notices: MockNotice[]=[{id:'demo-notice',title:'가상 데이터 시연 안내',content:'현재 개발 시연에서는 직접 만든 예시 학생과 학습 기록을 사용합니다. 실제 개인정보를 입력하지 마세요.',roles:['PARENT','STUDENT','ADMIN'],startsAt:'2026-10-29T00:00:00+09:00',endsAt:null}]
const owner = () => [mockIdentity.email, store.snapshot().session?.role, store.snapshot().session?.child?.id ?? ''].join(':')
function auth(request: Request) { guard(request); return store.snapshot().session! }
function adult(request: Request) { const s = auth(request); if (s.role === 'STUDENT') fail('FORBIDDEN','학생 알림함은 제공하지 않습니다.',403); return s }
function notifications() {
  const key = owner()
  if (!inbox.has(key)) inbox.set(key, [{id:crypto.randomUUID(),childId:null,type:'REPORT_COMPLETED',title:'가상 리포트 알림 예시',link:'/' + store.snapshot().session!.role.toLowerCase() + '/report',readAt:null,createdAt:new Date().toISOString()}])
  return inbox.get(key)!
}
function reportView(c: OwnedCase) {
  const r = errorReports.find(r => r.reportId === c.id)
  return { reportId:c.id,status:r?.status ?? c.status,targetType:c.targetType,targetId:c.targetId,category:c.category,comment:c.comment,reviewReason:r?.reviewReason ?? null,createdAt:c.createdAt }
}
const inquiryView = (c: OwnedCase) => ({ inquiryId:c.id,category:c.category,title:c.title ?? c.comment.slice(0,60),body:c.comment,status:c.status,answer:c.answer ?? null,createdAt:c.createdAt })
const view = (c: OwnedCase) => c.kind === 'error-reports' ? reportView(c) : inquiryView(c)
const preferences = () => settings.get(owner()) ?? { items: Object.keys(notificationLabels).map(type => ({ type: type as keyof typeof notificationLabels, enabled: true })) }
export const serviceHandlers = [
  http.get('/api/v1/help', ({ request }) => respond(async () => {
    const s = auth(request)
    if (new URL(request.url).searchParams.get('role') !== s.role) fail('FORBIDDEN','현재 역할의 안내만 열 수 있습니다.',403)
    return { role: s.role, items: s.role === 'STUDENT' ? [
      { title:'미션은 어떻게 시작하나요?',body:'생각 지도에서 미션을 고르고 질문을 읽어 주세요. 답을 쓰거나 보기에서 고른 뒤 제출할 수 있습니다.' },
      { title:'쓰던 답은 어디에 있나요?',body:'저장 완료 표시를 확인해 주세요. 저장 실패 때는 화면을 닫기 전에 다시 저장해 주세요. 내 공책에서 이어할 수 있습니다.' },
      { title:'정답과 예시 답은 언제 보나요?',body:'생각을 적고 필요한 질문에 답한 뒤 마무리하면 볼 수 있습니다. 마지막에는 내 생각을 돌아봐 주세요.' },
    ] : [
      { title:'자녀와 조회 기간',body:'선택한 자녀와 기간의 기록만 조회합니다. 다른 자녀로 바꾸면 분석 범위를 다시 확인해 주세요.' },
      { title:'숫자와 분석의 한계',body:'활동 건수와 답변 근거를 확인합니다. 기록이 적거나 판정이 보류된 경우 능력 점수로 해석하지 않습니다.' },
      { title:'QR과 PIN으로 자녀 기기 등록',body:'자녀 기기·PIN에서 자녀별 본인 확인 후 PIN을 정하고 등록 코드를 발급합니다. 자녀 기기에서 QR을 열고 등록한 뒤 PIN을 입력해 주세요.' },
    ] }
  })),
  ...(['error-reports','inquiries'] as const).flatMap(kind => [
    http.get('/api/v1/' + kind, ({ request }) => respond(async () => { auth(request); return page(cases.filter(c => c.owner === owner() && c.kind === kind).map(view)) })),
    http.get('/api/v1/' + kind + '/:id', ({ request,params }) => respond(async () => { auth(request); const c = cases.find(c => c.id === params.id && c.owner === owner() && c.kind === kind); if (!c) fail('NOT_FOUND','접수 내역이 없습니다.',404); return view(c!) })),
    http.post('/api/v1/' + kind, ({ request }) => respond(async () => {
      const s = auth(request)
      if (s.role === 'ADMIN') fail('FORBIDDEN','사용자 계정으로 문의해 주세요.',403)
      const data = await request.json() as Partial<OwnedCase> & { body?: string }
      const key = request.headers.get('Idempotency-Key') ?? ''
      if (kind === 'inquiries' && (!['ACCOUNT','USAGE','PAYMENT'].includes(data.category ?? '') || !data.title?.trim() || data.title.length > 200 || !data.body?.trim())) fail('VALIDATION_FAILED','유형·제목·내용을 확인해 주세요.',400)
      if (kind === 'error-reports') {
        if (!key) fail('VALIDATION_FAILED','Idempotency-Key가 필요합니다.',400)
        const previous = cases.find(c => c.kind === kind && c.owner === owner() && c.key === key)
        if (previous) return reportView(previous)
        if (!data.targetId?.trim() || !['FOLLOWUP','JUDGMENT','ANALYSIS','REPORT'].includes(data.targetType ?? '') || !['WRONG_JUDGMENT','ODD_QUESTION','MISMATCH','INAPPROPRIATE','OTHER'].includes(data.category ?? '') || (data.comment?.length ?? 0) > 10000) fail('VALIDATION_FAILED','신고 대상·유형을 확인해 주세요.',400)
      }
      // 시연 범위 밖의 대상 번호를 실제로 확인했다고 표시하지 않는다.
      const c: OwnedCase = { id:crypto.randomUUID(),owner:owner(),kind,...(kind==='error-reports'?{key,targetType:data.targetType,targetId:data.targetId,comment:data.comment??''}:{title:data.title,comment:data.body!}),category:data.category!,status:'RECEIVED',createdAt:new Date().toISOString() }
      if(kind==='error-reports'){
        const owned=(store.snapshot().children??[]).map(c=>c.id)
        const attempts=store.snapshot().attempts.filter(a=>owned.includes(a.studentId)&&(s.role!=='STUDENT'||a.studentId===s.child?.id))
        const linked=attempts.find(a=>a.answers.some(answer=>answer.answerId===data.targetId))
        if(['JUDGMENT','FOLLOWUP'].includes(data.targetType??'')&&!linked)fail('NOT_FOUND','본인의 신고 대상 기록을 확인하지 못했습니다.',404)
        if(data.targetType==='REPORT'&&(s.role!=='PARENT'||!reports.get(data.targetId!)?.some(v=>owned.includes(v.childId))))fail('NOT_FOUND','본인의 리포트를 확인하지 못했습니다.',404)
        if(data.targetType==='ANALYSIS'&&(s.role!=='PARENT'||![...conversations.values()].some(c=>owned.includes(c.childId)&&c.messages.some(m=>m.messageId===data.targetId))))fail('NOT_FOUND','본인의 분석 답변을 확인하지 못했습니다.',404)
        errorReports.unshift({reportId:c.id,status:'RECEIVED',targetType:data.targetType!,targetId:data.targetId!,category:c.category,comment:c.comment,corrections:[]})
        if(linked)reportedAttemptIds.set(c.id,linked.attemptId)
      }
      cases.unshift(c)
      return view(c)
    },201)),
  ]),
  http.get('/api/v1/notifications', ({ request }) => respond(async () => {
    adult(request)
    const q = new URL(request.url).searchParams, current = Number(q.get('page') ?? 0), size = Number(q.get('size') ?? 20)
    if (!Number.isInteger(current) || current < 0 || !Number.isInteger(size) || size < 1 || size > 100) fail('VALIDATION_FAILED','페이지를 확인해 주세요.',400)
    const items = notifications().filter(n => q.get('unreadOnly') !== 'true' || !n.readAt)
    return { items:items.slice(current*size,(current+1)*size),page:current,size,hasNext:(current+1)*size<items.length }
  })),
  // 실제 core처럼 구독 준비(ready)만 먼저 보내고 연결을 유지한다. 학생은 403.
  http.get('/api/v1/notifications/stream', async ({ request }) => {
    try { adult(request) } catch (error) { return respond(async () => { throw error }) }
    const body = new ReadableStream<Uint8Array>({ start(controller) {
      controller.enqueue(new TextEncoder().encode('event: ready\ndata: {"reconcile":"/api/v1/notifications"}\n\n'))
      request.signal.addEventListener('abort', () => { try { controller.close() } catch { /* 이미 닫힘 */ } }, { once: true })
    } })
    return new HttpResponse(body, { headers: { 'Content-Type': 'text/event-stream' } })
  }),
  http.patch('/api/v1/notifications/:id/read', ({ request,params }) => respond(async () => {
    adult(request); const n = notifications().find(n => n.id === params.id)
    if (!n) fail('NOT_FOUND','알림이 없습니다.',404)
    n!.readAt ??= new Date().toISOString()
  },204)),
  http.post('/api/v1/notifications/read-all', ({ request }) => respond(async () => { adult(request); for (const n of notifications()) n.readAt ??= new Date().toISOString() },204)),
  http.get('/api/v1/notification-settings', ({ request }) => respond(async () => { adult(request); return preferences() })),
  http.put('/api/v1/notification-settings', ({ request }) => respond(async () => {
    adult(request); const data = await request.json() as NotificationSettings
    if (!Array.isArray(data.items) || !data.items.length || data.items.length>6 || new Set(data.items.map(s=>s.type)).size!==data.items.length || data.items.some(s => !(s.type in notificationLabels) || typeof s.enabled !== 'boolean')) fail('VALIDATION_FAILED','알림 유형을 확인해 주세요.',422)
    const next = { items:preferences().items.map(s => data.items.find(v => v.type === s.type) ?? s) }
    settings.set(owner(), next); return next
  })),
  // 메모리 시연 상태. 실제 처리 완료·PG 승인·삭제 완료를 자동으로 만들지 않는다.
  http.get('/api/v1/children/:childId/deletion-impact', ({ request,params }) => respond(async () => {
    const c = await parentChild(request,String(params.childId))
    return { childId:c.id,actions:[{ scope:'UNLINK',effect:'보호자 연결과 학생 이용을 중단합니다. 학습 기록 삭제와 다릅니다.' },{ scope:'PROFILE',effect:'프로필과 학습·대화·리포트 삭제를 요청합니다.' },{ scope:'RECORDS',effect:'프로필을 남기고 학습·대화·리포트 삭제를 요청합니다. 자동으로 학습이 재개되지는 않습니다.' }],retainedTransactionsYears:5,deviceCleanupPending:true }
  })),
  http.delete('/api/v1/children/:childId/link', ({request,params})=>respond(async()=>{
    const c=await parentChild(request,String(params.childId));requireNoPendingTransfer(c.id);consumeActionReauth(request,'CHILD_UNLINK',c.id)
    replaceTransferChildren(mockIdentity.email,(await store.children()).filter(v=>v.id!==c.id))
  },204)),
  http.post('/api/v1/children/:childId/deletion-requests',({request,params})=>respond(async()=>{
    const c=await parentChild(request,String(params.childId)),data=await request.json() as {scope:'PROFILE'|'RECORDS'}
    requireNoPendingTransfer(c.id)
    consumeActionReauth(request,'CHILD_DELETE',c.id,data.scope)
    if ([...deletions.values()].some(v=>v.childId===c.id&&v.status==='CONFIRMED')) fail('DELETION_IN_PROGRESS','이미 삭제 처리 중입니다.',409)
    const result={deletionRequestId:crypto.randomUUID(),childId:c.id,scope:data.scope,status:'CONFIRMED',completedServices:[],owner:owner()}
    deletions.set(result.deletionRequestId,result);transferUnavailableChildren.add(c.id);return result
  },202)),
  http.get('/api/v1/children/:childId/deletion-requests/:requestId',({request,params})=>respond(async()=>{
    parentGuard(request);const result=deletions.get(String(params.requestId))
    if (!result||result.owner!==owner()||result.childId!==params.childId) fail('NOT_FOUND','삭제 요청이 없습니다.',404)
    return result
  })),
  http.get('/api/v1/me/withdrawal/precheck', ({ request }) => respond(async () => { parentGuard(request,true); return { canWithdraw:true,activeSubscriptions:0,unresolvedRefunds:0,retainedTransactionsYears:5 } })),
  http.post('/api/v1/me/withdrawal',({request})=>respond(async()=>{
    parentGuard(request,true);requireNoPendingTransfer();consumeActionReauth(request,'WITHDRAWAL')
    const statusToken=crypto.randomUUID(),state={withdrawalRequestId:crypto.randomUUID(),status:'WITHDRAWAL_REQUESTED'}
    withdrawalReceipts.set(statusToken,state);return {...state,statusToken}
  },202)),
  http.get('/api/v1/me/withdrawal',({request})=>respond(async()=>{
    const result=withdrawalReceipts.get(request.headers.get('X-Withdrawal-Status-Token')??'')
    if (!result) fail('FORBIDDEN','조회 영수증이 필요합니다.',403)
    return result
  })),
]

export function answerCase(key:string,answer:string){
    const c=cases.find(c=>c.id===key&&c.kind==='inquiries'),data={answer}
    if(!c)fail('NOT_FOUND','문의가 없습니다.',404)
    if(!data.answer?.trim()||data.answer.length>4000)fail('VALIDATION_FAILED','답변 내용을 확인해 주세요.',422)
    c!.answer=data.answer;c!.status='RESOLVED'
    const targetInbox=inbox.get(c!.owner)??[]
    const enabled=settings.get(c!.owner)?.items.find(s=>s.type==='INQUIRY_ANSWERED')?.enabled??true
    if(enabled&&!targetInbox.some(n=>n.id==='inquiry-'+c!.id))targetInbox.unshift({id:'inquiry-'+c!.id,childId:null,type:'INQUIRY_ANSWERED',title:'문의에 답변이 등록되었습니다.',link:'/parent/support',readAt:null,createdAt:new Date().toISOString()})
    inbox.set(c!.owner,targetInbox);return c
}
