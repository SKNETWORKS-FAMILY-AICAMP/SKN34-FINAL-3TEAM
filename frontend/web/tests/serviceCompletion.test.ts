import test from 'node:test'
import assert from 'node:assert/strict'
import { notificationPath } from '../src/domain/service.ts'
Object.defineProperty(globalThis,'location',{value:new URL('http://localhost/'),configurable:true})
const {setupServer}=await import('msw/node')
const {serviceHandlers}=await import('../src/mocks/handlers/service.ts')
const {studentHandlers,startDeviceStudentSession}=await import('../src/mocks/handlers/student.ts')
const {retentionHandlers}=await import('../src/mocks/handlers/retention.ts')
const {retentionState}=await import('../src/mocks/fixtures/retention.ts')
const {fixtureStore}=await import('../src/mocks/fixtures/student.ts')
const {parentHandlers}=await import('../src/mocks/handlers/parent.ts')
const {studentDeviceHandlers}=await import('../src/mocks/handlers/studentDevice.ts')
const {adminHandlers}=await import('../src/mocks/handlers/admin.ts')
const {adminServiceHandlers}=await import('../src/mocks/handlers/adminService.ts')
const server=setupServer(...retentionHandlers,...serviceHandlers,...studentDeviceHandlers,...parentHandlers,...adminHandlers,...adminServiceHandlers,...studentHandlers)
server.listen({onUnhandledFrame:'error'});test.after(()=>server.close())
let token=''
async function call(path:string,method='GET',data?:unknown,headers:Record<string,string>={}) {
  const r=await fetch('http://localhost/api/v1'+path,{method,headers:{...(token?{Authorization:'Bearer '+token}:{}),'Content-Type':'application/json',...headers},...(data===undefined?{}:{body:JSON.stringify(data)})})
  const text=await r.text();return {status:r.status,data:text?JSON.parse(text):null}
}
async function login(email='parent@example.test') { const r=await call('/auth/login','POST',{email,password:'demo-only'});assert.equal(r.status,200);token=r.data.accessToken }
test('알림 링크는 동일 출처·현재 역할만 허용',()=>{
  assert.equal(notificationPath('/parent/report?childId=x','PARENT','https://example.test'),'/parent/report?childId=x')
  for(const link of ['javascript:alert(1)','https://evil.test/parent/report','//evil.test/parent/report','/admin/home'])assert.equal(notificationPath(link,'PARENT','https://example.test'),null)
})
test('본인 문의·운영 답변·처리 상태와 알림의 연결, 타 계정 격리',async()=>{
  await login()
  assert.equal((await call('/inquiries','POST',{category:'OTHER',title:'문의',body:'옛 유형'})).status,400)
  const created=await call('/inquiries','POST',{category:'USAGE',title:'기록 확인',body:'시연 문의 내용'})
  assert.equal(created.status,201);assert.equal(created.data.title,'기록 확인');assert.equal(created.data.body,'시연 문의 내용')
  const report={targetType:'JUDGMENT',targetId:'foreign-answer',category:'OTHER',comment:'타인 기록 요청'}
  assert.equal((await call('/error-reports','POST',report)).status,400)
  assert.equal((await call('/error-reports','POST',report,{'Idempotency-Key':crypto.randomUUID()})).status,404)
  await login('admin@example.test')
  assert.equal((await call('/admin/inquiries')).data.items.some((c:{inquiryId:string})=>c.inquiryId===created.data.inquiryId),true)
  assert.equal((await call('/admin/inquiries/'+created.data.inquiryId+'/answer','POST',{answer:'기록은 내 공책에서 확인해 주세요.'})).status,200)
  await login()
  const own=(await call('/inquiries')).data.items.find((c:{inquiryId:string})=>c.inquiryId===created.data.inquiryId)
  assert.deepEqual((await call('/inquiries/'+created.data.inquiryId)).data,own)
  assert.equal(own.status,'RESOLVED');assert.ok(own.answer.includes('내 공책'))
  const notifications=await call('/notifications?unreadOnly=true&page=0&size=20')
  const n=notifications.data.items.find((n:{type:string})=>n.type==='INQUIRY_ANSWERED')
  assert.ok(n);assert.equal((await call('/notifications/'+n.id+'/read','PATCH',{})).status,204)
  assert.equal((await call('/notifications/'+n.id+'/read','PATCH',{})).status,204)
  await login('content@example.test')
  assert.equal((await call('/inquiries')).data.items.length,0)
  assert.equal((await call('/admin/inquiries')).status,403)
})
test('알림 설정 유형 검증·부분 변경 유지',async()=>{
  await login()
  assert.equal((await call('/notification-settings','PUT',{items:[{type:'WRONG',enabled:true}]})).status,422)
  const result=await call('/notification-settings','PUT',{items:[{type:'REPORT_FAILED',enabled:false}]})
  assert.equal(result.data.items.find((s:{type:string})=>s.type==='REPORT_FAILED').enabled,false)
  assert.equal(result.data.items.length,9) // 일일 리포트 2종(P24), 학년 진급(#432) 추가
})
test('삭제 재확인 scope·자녀 결합 및 단회 사용, 미완료 상태 보존',async()=>{
  await login()
  const start=await call('/me/reauth','POST',{purpose:'CHILD_DELETE',childId:'demo-seoyun',scope:'RECORDS'})
  const proof=(await call('/me/reauth','POST',{challengeId:start.data.challengeId})).data.reauthToken
  assert.equal((await call('/children/demo-seoyun/deletion-requests','POST',{scope:'PROFILE'},{'X-Reauth-Token':proof})).status,403)
  const result=await call('/children/demo-seoyun/deletion-requests','POST',{scope:'RECORDS'},{'X-Reauth-Token':proof})
  assert.equal(result.status,202);assert.equal(result.data.status,'CONFIRMED');assert.deepEqual(result.data.completedServices,[])
  assert.equal((await call('/children/demo-seoyun/deletion-requests','POST',{scope:'RECORDS'},{'X-Reauth-Token':proof})).status,403)
  assert.equal((await call('/children/demo-seoyun/deletion-requests/'+result.data.deletionRequestId)).data.status,'CONFIRMED')
})
test('모델 평가 객체·평가 밖 범위 거부·인증 계정 승인과 버전 복귀',async()=>{
  await login('admin@example.test')
  const me=await call('/me');assert.equal(me.status,200);assert.equal(me.data.role,'ADMIN')
  const evaluation={datasetId:'demo-eval',datasetVersion:'v1',baselineVersion:'base',comparisonReport:'demo report',trainingEvaluationSeparation:'demo split',quoteAccuracy:'demo quotes',calculationAccuracy:'demo counts',humanReview:'demo review',evaluatedScopes:['judgment/grade-3/narrative']}
  const make=async(version:string)=>call('/admin/model-versions','POST',{kind:'PROMPT',name:'service-test',version,evaluation})
  const a=await make('v1');assert.equal(a.status,201);assert.equal(a.data.evalResult.approval,null)
  // 오류 코드는 core ModelVersionService와 같음: 규칙 위반 422 MODEL_APPROVAL_REJECTED, 상태·중복 409 MODEL_VERSION_CONFLICT
  const outOfScope=await call('/admin/model-versions/'+a.data.id+'/activate','POST',{approved:true,scopes:['other'],reason:'범위 오류',reanalysisPlanned:false})
  assert.deepEqual([outOfScope.status,outOfScope.data.code],[422,'MODEL_APPROVAL_REJECTED'])
  const notApproved=await call('/admin/model-versions/'+a.data.id+'/activate','POST',{scopes:evaluation.evaluatedScopes,reason:'승인 누락',reanalysisPlanned:false})
  assert.deepEqual([notApproved.status,notApproved.data.code],[422,'MODEL_APPROVAL_REJECTED'])
  const change=(id:string,action:string)=>call('/admin/model-versions/'+id+'/'+action,'POST',{...(action==='activate'?{approved:true}:{}),scopes:evaluation.evaluatedScopes,reason:'가상 검토 기록',reanalysisPlanned:false})
  const activated=(await change(a.data.id,'activate')).data
  assert.equal(activated.evalResult.approval.approvedBy,'mock-service-ops')
  assert.equal(activated.approvedBy,activated.evalResult.approval.approvedBy) // core는 둘이 다르면 활성 버전을 거부
  const again=await change(a.data.id,'activate');assert.deepEqual([again.status,again.data.code],[409,'MODEL_VERSION_CONFLICT'])
  const b=await make('v2');await change(b.data.id,'activate')
  const back=await change(a.data.id,'rollback');assert.equal(back.status,200);assert.equal(back.data.evalResult.revision,3)
  const dup=await make('v1');assert.deepEqual([dup.status,dup.data.code],[409,'MODEL_VERSION_CONFLICT'])
  const rubric=await call('/admin/model-versions','POST',{kind:'RUBRIC',name:'service-test',version:'r1',evaluation})
  assert.deepEqual([rubric.status,rubric.data.code],[422,'MODEL_APPROVAL_REJECTED']) // RUBRIC은 refId 필수
})

test('공유물 신고 목업은 원문과 처리 결과를 연결하고 완료 상태에서 같은 요청만 받는다', async () => {
  await login()
  const children = fixtureStore.snapshot().children
  assert.ok(children)
  const student = children.find((child) => child.id === 'demo-seoyun')!
  const studentLogin = () => { token = startDeviceStudentSession(student, children) }
  studentLogin()
  const home = await fixtureStore.home(student)
  const mission = home.missions.find((item) => item.status === 'COMPLETED')!
  assert.ok(mission, '커뮤니티 목록을 열 수 있는 완료 미션 필요')
  const list = async () => {
    const result = await call('/missions/' + mission.id + '/community-posts')
    assert.equal(result.status, 200)
    return result.data.items as { postId: string; answer: string }[]
  }
  const submit = async (postId: string) => {
    const result = await call('/error-reports', 'POST',
      { targetType: 'COMMUNITY_POST', targetId: postId, category: 'INAPPROPRIATE', comment: '공유물 확인 요청' },
      { 'Idempotency-Key': crypto.randomUUID() })
    assert.equal(result.status, 201)
    assert.equal('linkedPost' in result.data, false)
    return '/admin/error-reports/' + result.data.reportId
  }

  const [publish, keep, destroyed] = await list()
  const publishPath = await submit(publish.postId)
  const keepPath = await submit(keep.postId)
  const destroyedPath = await submit(destroyed.postId)
  assert.equal((await list()).some(({ postId }) => postId === publish.postId), false)
  assert.equal((await call(publishPath)).status, 403)

  await login('admin@example.test')
  const before = await call(publishPath)
  assert.equal(before.status, 200)
  assert.equal(before.data.linkedPost.available, true)
  assert.equal(before.data.linkedPost.status, 'HIDDEN_REPORT')
  assert.equal(before.data.linkedPost.answer.text, publish.answer)
  const summaries = await call('/admin/error-reports')
  assert.ok(summaries.data.items.some(({ reportId }: { reportId: string }) => reportId === before.data.reportId))
  assert.equal(summaries.data.items.some((row: object) => 'linkedPost' in row), false)

  const resolve = { status: 'RESOLVED', reviewReason: '공유 가능한 내용입니다.', reviewResult: 'VISIBLE' }
  assert.equal((await call(publishPath, 'PATCH', resolve)).status, 409)
  for (const path of [publishPath, keepPath]) {
    assert.equal((await call(path, 'PATCH', { status: 'IN_REVIEW', reviewReason: '원문을 확인합니다.' })).status, 200)
  }
  const resolved = await call(publishPath, 'PATCH', resolve)
  assert.equal(resolved.status, 200)
  assert.equal(resolved.data.reviewResult, 'VISIBLE')
  assert.equal('linkedPost' in resolved.data, false)
  assert.deepEqual(await call(publishPath, 'PATCH', resolve), resolved)
  for (const changed of [{ reviewResult: 'REMOVED' }, { reviewReason: '다른 사유' }, { status: 'IN_REVIEW' }]) {
    assert.equal((await call(publishPath, 'PATCH', { ...resolve, ...changed })).status, 409)
  }
  const removed = await call(keepPath, 'PATCH', { status: 'RESOLVED', reviewReason: '계속 숨깁니다.' })
  assert.equal(removed.status, 200)
  assert.equal(removed.data.reviewResult, 'REMOVED')

  retentionState.posts.splice(retentionState.posts.findIndex((post) => post.postId === destroyed.postId), 1)
  assert.deepEqual((await call(destroyedPath)).data.linkedPost, { postId: destroyed.postId, available: false })

  studentLogin()
  const visible = await list()
  assert.equal(visible.some(({ postId }) => postId === publish.postId), true)
  assert.equal(visible.some(({ postId }) => postId === keep.postId), false)
})
