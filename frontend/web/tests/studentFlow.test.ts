import test from 'node:test'
import assert from 'node:assert/strict'
import { createDemoGateway, demoMissions } from '../src/data/classroom/demoGateway.ts'
import { createApiGateway } from '../src/data/classroom/apiGateway.ts'
import { blankAnswer, validateAnswer, isVerifiedElement } from '../src/domain/classroom.ts'
import type { AnswerContent, InputType } from '../src/domain/classroom.ts'
import { pollFeedback } from '../src/data/classroom/feedbackPolling.ts'
import { normalizeAnswer, wireAttempt } from '../src/mocks/fixtures/student.ts'
import { roleStart } from '../src/domain/navigation.ts'

async function setup(grade5=false) { const api=createDemoGateway();await api.login('parent@example.test','demo');const c=(await api.children())[grade5?1:0];await api.enterStudent(c);return {api,c} }
for(const type of ['NARRATIVE','SOLUTION_STEPS','ESSAY','CHOICE','ORDERING','CLASSIFICATION'] as InputType[]) {
  test(`${type} 입력 검증·서버 제출·메모 제외 직렬화`,async t=>{
    const {api,c}=await setup(type==='ESSAY');api.setScenario('input-fixtures')
    const missions=await api.missions(c)
    const mission=missions.find(m=>m.inputType===type)!
    assert.ok(mission)
    const answer:AnswerContent={...blankAnswer(type),dictatedByGuardian:true}
    assert.notEqual(validateAnswer(answer,mission),null)
    if(type==='NARRATIVE')answer.text='내 경험을 떠올려 생각을 적었어요.'
    if(type==='SOLUTION_STEPS'){answer.finalAnswer='6';answer.steps=['3+3으로 구했어요.']}
    if(type==='ESSAY')answer.essay={claim:'주장',reasons:['첫 까닭','두 번째 까닭'],rebuttal:'반대 의견에 답'}
    if(type==='CHOICE')answer.choiceIds=['leaf']
    if(type==='ORDERING')answer.choiceIds=['seed','sprout','leaf']
    if(type==='CLASSIFICATION')answer.assignments=[{choiceId:'nail',categoryId:'magnetic'},{choiceId:'paper',categoryId:'other'},{choiceId:'clip',categoryId:'magnetic'}]
    assert.equal(validateAnswer(answer,mission),null)
    let a=await api.start(mission,c);a=await api.submit(a.attemptId,answer,'stable-key')
    assert.equal(a.answers[0].content?.dictatedByGuardian,true)
    const bodies:Record<string,unknown>[]=[]
    t.mock.method(globalThis,'fetch',async(_path:string,init:RequestInit)=>{if(init.body)bodies.push(JSON.parse(String(init.body)));return new Response(JSON.stringify(wireAttempt(a)),{headers:{'Content-Type':'application/json'}})})
    await createApiGateway().submit(a.attemptId,answer,'wire-key')
    assert.equal(bodies[0].inputType,type);assert.equal(bodies[0].dictatedByGuardian,true);assert.equal('memo' in bodies[0],false)
    assert.equal('memo' in normalizeAnswer({...bodies[0],memo:'절대 공유하지 않음'},mission),false)
  })
}
test('순서·분류 중복/누락·미정 그룹과 논술 까닭 1개 거부',async()=>{
  const {api,c}=await setup();api.setScenario('input-fixtures');const list=await api.missions(c)
  assert.ok(validateAnswer({...blankAnswer('ORDERING'),choiceIds:['seed','seed','leaf']},list.find(m=>m.inputType==='ORDERING')!))
  assert.ok(validateAnswer({...blankAnswer('CLASSIFICATION'),assignments:[{choiceId:'nail',categoryId:'wrong'}]},list.find(m=>m.inputType==='CLASSIFICATION')!))
  assert.ok(validateAnswer({...blankAnswer('ESSAY'),essay:{claim:'주장',reasons:['하나'] as never,rebuttal:'반대'}},demoMissions(5)[2]))
})
for(const scenario of ['correct','partial','rethink','held'] as const) {
  test(`${scenario} 판정 상태와 원문 근거, 마무리 전 비공개`,async()=>{
    const {api,c}=await setup();api.setScenario(scenario);let a=await api.start(demoMissions(c.grade)[2],c)
    a=await api.submit(a.attemptId,{...blankAnswer('NARRATIVE'),text:'실제 원문에 들어 있는 내 생각이에요.'},'key')
    const f=await api.feedback(a.attemptId,a.answers[0].answerId,()=>{})
    assert.equal(f.judgment?.result,scenario.toUpperCase())
    a=await api.attempt(a.attemptId)
    const wire=wireAttempt(a);assert.equal('reveal' in wire,false);assert.equal('checklist' in wire,false)
    a=await api.finish(a.attemptId);assert.ok(a.reveal);assert.ok(a.checklist?.every(e=>!e.satisfied||isVerifiedElement(e,a.answers.map(a=>a.text))))
  })
}
test('고르기 활동(고르기·순서·분류) 정답은 되묻기 없이 마무리만, 서술 정답은 되묻기 (#82)',async()=>{
  const {api,c}=await setup();api.setScenario('input-fixtures');const list=await api.missions(c)
  const answers:Record<string,AnswerContent>={
    CHOICE:{...blankAnswer('CHOICE'),choiceIds:['leaf']},
    ORDERING:{...blankAnswer('ORDERING'),choiceIds:['seed','sprout','leaf']},
    CLASSIFICATION:{...blankAnswer('CLASSIFICATION'),assignments:[{choiceId:'nail',categoryId:'magnetic'},{choiceId:'paper',categoryId:'other'},{choiceId:'clip',categoryId:'magnetic'}]},
    NARRATIVE:{...blankAnswer('NARRATIVE'),text:'내 생각과 까닭을 적었어요.'},
  }
  for(const [type,answer] of Object.entries(answers)){
    api.setScenario('input-fixtures');const mission=list.find(m=>m.inputType===type)!
    let a=await api.start(mission,c);a=await api.submit(a.attemptId,answer,'key-'+type)
    api.setScenario('correct');const f=await api.feedback(a.attemptId,a.answers[0].answerId,()=>{})
    assert.equal(f.judgment?.result,'CORRECT',type)
    assert.ok(f.judgment?.judgmentId,type)
    assert.deepEqual(f.nextActions,type==='NARRATIVE'?['ANSWER_FOLLOWUP','FINISH']:['FINISH'],type)
    assert.equal(f.followup==null,type!=='NARRATIVE',type)
  }
})
test('RUNNING-only 후 같은 answerId 재조회·취소·답변 중복 없음',async()=>{
  const {api,c}=await setup();api.setScenario('running');let a=await api.start(demoMissions(3)[2],c)
  a=await api.submit(a.attemptId,{...blankAnswer('NARRATIVE'),text:'저장된 답'},'key')
  let requests=0;const orig=api.feedback;api.feedback=(...args)=>{requests++;return orig(...args)}
  const result=await pollFeedback(api,a.attemptId,a.answers[0].answerId,()=>{},new AbortController().signal,1)
  assert.equal(result.status,'DONE');assert.equal(requests,2);assert.equal((await api.attempt(a.attemptId)).answers.length,1)
  const controller=new AbortController();controller.abort();await assert.rejects(pollFeedback(api,a.attemptId,a.answers[0].answerId,()=>{},controller.signal,1))
})
test('학생 홈에 미제출 초안 이어하기, 새 인스턴스에서 snapshot 복원',async()=>{
  const {api,c}=await setup();let a=await api.start(demoMissions(3)[2],c)
  await api.saveDraft(a.attemptId,{answer:{...blankAnswer('NARRATIVE'),text:'복원할 입력'},memo:'학생 전용 메모',version:'0'})
  const home=await api.home(c);assert.equal(home.resume?.attemptId,a.attemptId);assert.equal(home.resume?.answers.length,0)
  const snapshot=api.snapshot();assert.equal('accessToken' in snapshot,false);assert.equal('password' in snapshot,false)
  const restored=createDemoGateway();restored.restoreSnapshot(snapshot);assert.equal((await restored.restore()).role,'STUDENT')
  a=await restored.attempt(a.attemptId);assert.equal(a.draft?.answer.text,'복원할 입력');assert.equal(a.draft?.memo,'학생 전용 메모')
})
test('finish 409는 정답·체크리스트를 상태에 만들지 않음',async()=>{
  const {api,c}=await setup();let a=await api.start(demoMissions(3)[2],c);await assert.rejects(api.finish(a.attemptId))
  a=await api.submit(a.attemptId,{...blankAnswer('NARRATIVE'),text:'보존할 답'},'key');await api.feedback(a.attemptId,a.answers[0].answerId,()=>{})
  api.setScenario('finish-unmet');await assert.rejects(api.finish(a.attemptId));a=await api.attempt(a.attemptId)
  assert.equal(a.reveal,undefined);assert.equal(a.checklist,undefined);assert.equal(a.answers.length,1)
})
test('원문에 없는 인용은 satisfied=true여도 확인된 체크로 표시 금지',()=>{
  assert.equal(isVerifiedElement({elementId:'x',label:'근거',satisfied:true,quote:'조작된 문장',sourceType:'AI_OBSERVATION'},['실제 원문']),false)
  assert.equal(roleStart('STUDENT'),'/student/home');assert.equal(roleStart('PARENT'),'/parent/journal');assert.equal(roleStart('ADMIN'),'/admin/home')
})
