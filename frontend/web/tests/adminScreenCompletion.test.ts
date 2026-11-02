import test from 'node:test'
import assert from 'node:assert/strict'
import { adminServiceApi as api } from '../src/data/admin/serviceApi.ts'
import { setAccessToken } from '../src/data/apiClient.ts'
import { noticeStatus, noticeStatusLabel } from '../src/domain/admin/service.ts'
Object.defineProperty(globalThis,'location',{value:new URL('http://localhost/'),configurable:true})
const {setupServer}=await import('msw/node')
const {adminServiceHandlers,demoRefunds}=await import('../src/mocks/handlers/adminService.ts')
const {serviceHandlers}=await import('../src/mocks/handlers/service.ts')
const {studentHandlers}=await import('../src/mocks/handlers/student.ts')
const {parentHandlers}=await import('../src/mocks/handlers/parent.ts')
const server=setupServer(...adminServiceHandlers,...serviceHandlers,...parentHandlers,...studentHandlers)
server.listen({onUnhandledFrame:'error'});test.after(()=>server.close())
let token=''
async function call(path:string,method='GET',data?:unknown,extra:Record<string,string>={}){const r=await fetch('http://localhost/api/v1'+path,{method,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json',...extra},...(data===undefined?{}:{body:JSON.stringify(data)})});return {status:r.status,data:r.status===204?null:await r.json()}}
async function login(email:string){const r=await call('/auth/login','POST',{email,password:'demo-only'});assert.equal(r.status,200);token=r.data.accessToken}
test('관리 API의 실제 요청 모양: 승인 body 없음·멱등 키, 반려 reason만, 공지 canonical DTO',async(t)=>{
 const requests:{url:string;init:RequestInit}[]=[];setAccessToken('contract-admin','ADMIN')
 t.mock.method(globalThis,'fetch',async(url:string,init:RequestInit)=>{requests.push({url:String(url),init});return Response.json({id:'r'})})
 await api.approve('r/id','key-1');await api.reject('r/id','검토 사유');await api.answer('i/id','답변')
 await api.saveNotice({kind:'NOTICE',title:'제목',body:'내용',targetRoles:['PARENT'],visibleFrom:'2026-10-29T00:00:00+09:00',visibleTo:null})
 assert.ok(requests[0].url.endsWith('/admin/refund-requests/r%2Fid/approve'));assert.equal(requests[0].init.body,undefined);assert.equal(new Headers(requests[0].init.headers).get('Idempotency-Key'),'key-1')
 assert.deepEqual(JSON.parse(String(requests[1].init.body)),{reason:'검토 사유'});assert.equal(new Headers(requests[1].init.headers).get('Idempotency-Key'),null)
 assert.ok(requests[2].url.endsWith('/admin/inquiries/i%2Fid/answer'));assert.equal(JSON.parse(String(requests[3].init.body)).visibleTo,null)
 setAccessToken(null)
})
test('환불 조회·승인 권한 분리, 승인 202는 PG 대기이며 중복 키 재현',async()=>{
 await login('payment@example.test');assert.equal((await call('/admin/refund-requests')).status,200)
 assert.equal((await call('/admin/refund-requests/demo-refund-1/approve','POST',undefined,{'Idempotency-Key':'a'})).status,403)
 await login('ops@example.test');assert.equal((await call('/admin/payments')).status,403)
 await login('parent@example.test');assert.equal((await call('/admin/refund-requests')).status,403)
 await login('admin@example.test');const first=await call('/admin/refund-requests/demo-refund-1/approve','POST',undefined,{'Idempotency-Key':'same-key'})
 assert.equal(first.status,202);assert.equal(first.data.status,'APPROVED');assert.equal(first.data.pgStatus,'PENDING')
 assert.deepEqual((await call('/admin/refund-requests/demo-refund-1/approve','POST',undefined,{'Idempotency-Key':'same-key'})).data,first.data)
 assert.equal((await call('/admin/refund-requests/demo-refund-2/approve','POST',undefined,{'Idempotency-Key':'same-key'})).status,409)
 demoRefunds[0].status='REQUESTED';demoRefunds[0].pgStatus=null
})
test('공지 생성·수정·종료: 범위·기간 검증, 종료 공지 비노출, 문의 명시적 답변',async()=>{
 await login('admin@example.test');const inquiry=(await call('/admin/inquiries')).data.items.find((v:{inquiryId:string})=>v.inquiryId==='demo-admin-inquiry');assert.ok(inquiry)
 const answered=await call('/admin/inquiries/'+inquiry.inquiryId+'/answer','POST',{answer:'내 공책에서 확인해 주세요.'});assert.equal(answered.data.status,'RESOLVED')
 const data={kind:'NOTICE',title:'관리 공지',body:'가상 공지 내용',targetRoles:['ADMIN'],visibleFrom:'2026-01-01T00:00:00+09:00',visibleTo:null}
 const n=await call('/admin/notices','POST',data);assert.equal(n.status,201);assert.ok(n.data.noticeId);assert.equal(n.data.body,data.body)
 assert.equal((await call('/admin/notices','POST',{...data,targetRoles:['WRONG']})).status,400)
 assert.equal((await call('/admin/notices/'+n.data.noticeId,'PATCH',{...data,title:'수정 공지'})).data.title,'수정 공지')
 assert.ok((await call('/notices')).data.items.some((v:{noticeId:string})=>v.noticeId===n.data.noticeId))
 assert.ok((await call('/admin/notices/'+n.data.noticeId,'DELETE')).data.endedAt)
 assert.equal((await call('/notices')).data.items.some((v:{noticeId:string})=>v.noticeId===n.data.noticeId),false)
 assert.equal((await call('/admin/notices/'+n.data.noticeId,'PATCH',data)).status,409)
 await login('payment@example.test');assert.equal((await call('/admin/inquiries')).status,403)
})
test('공지 상태는 공개 기간·endedAt으로 계산: 예약·공개 중·종료',()=>{
 const now=Date.parse('2026-11-02T12:00:00+09:00')
 assert.equal(noticeStatus({visibleFrom:'2026-11-03T00:00:00+09:00',visibleTo:null,endedAt:null},now),'SCHEDULED')
 assert.equal(noticeStatus({visibleFrom:'2026-11-01T00:00:00+09:00',visibleTo:null,endedAt:null},now),'ACTIVE')
 assert.equal(noticeStatus({visibleFrom:'2026-11-02T12:00:00+09:00',visibleTo:'2026-11-02T12:00:01+09:00',endedAt:null},now),'ACTIVE')
 assert.equal(noticeStatus({visibleFrom:'2026-11-01T00:00:00+09:00',visibleTo:'2026-11-02T12:00:00+09:00',endedAt:null},now),'ENDED')
 assert.equal(noticeStatus({visibleFrom:'2026-11-03T00:00:00+09:00',visibleTo:null,endedAt:'2026-11-02T01:00:00Z'},now),'ENDED')
 assert.deepEqual(noticeStatusLabel,{SCHEDULED:'예약',ACTIVE:'공개 중',ENDED:'종료'})
})
test('관리자 공지 목록 어댑터는 GET /admin/notices에 상태·대상·페이지만 보낸다',async(t)=>{
 const urls:URL[]=[];setAccessToken('contract-admin','ADMIN')
 t.mock.method(globalThis,'fetch',async(url:string)=>{urls.push(new URL(String(url),'http://localhost/'));return Response.json({items:[],page:0,size:20,totalElements:0})})
 await api.notices();await api.notices({status:'SCHEDULED',role:'PARENT'},2)
 assert.equal(urls[0].pathname,'/api/v1/admin/notices');assert.deepEqual([...urls[0].searchParams],[['page','0'],['size','20']])
 assert.deepEqual(Object.fromEntries(urls[1].searchParams),{status:'SCHEDULED',role:'PARENT',page:'2',size:'20'})
 setAccessToken(null)
})
test('관리자 공지 전체 목록: 예약·종료 공지도 새로 조회되고 SERVICE_OPS만 허용',async()=>{
 await login('admin@example.test');const base={kind:'NOTICE',body:'목록 공지',targetRoles:['PARENT']}
 const day=86400000,iso=(ms:number)=>new Date(ms).toISOString()
 const scheduled=(await call('/admin/notices','POST',{...base,title:'예약 공지',visibleFrom:iso(Date.now()+day),visibleTo:null})).data.noticeId
 const ended=(await call('/admin/notices','POST',{...base,title:'종료 공지',visibleFrom:iso(Date.now()-day),visibleTo:null})).data.noticeId
 await call('/admin/notices/'+ended,'DELETE')
 const ids=async(q:string)=>{const r=await call('/admin/notices'+q);assert.equal(r.status,200);for(const k of ['items','page','size','totalElements'])assert.ok(k in r.data,k);return r.data.items.map((v:{noticeId:string})=>v.noticeId) as string[]}
 assert.ok((await ids('?status=SCHEDULED')).includes(scheduled));assert.equal((await ids('?status=ACTIVE')).includes(scheduled),false)
 assert.ok((await ids('?status=ENDED')).includes(ended));assert.equal((await ids('?status=ACTIVE')).includes(ended),false)
 assert.equal((await ids('?role=STUDENT')).includes(scheduled),false);assert.ok((await ids('?role=PARENT&size=100')).includes(scheduled))
 assert.equal((await call('/admin/notices?status=PUBLISHED')).status,400);assert.equal((await call('/admin/notices?size=101')).status,400)
 for(const email of ['payment@example.test','parent@example.test']){await login(email);assert.equal((await call('/admin/notices')).status,403)}
 assert.equal((await call('/notices')).data.items.some((v:{noticeId:string})=>v.noticeId===scheduled||v.noticeId===ended),false)
})
