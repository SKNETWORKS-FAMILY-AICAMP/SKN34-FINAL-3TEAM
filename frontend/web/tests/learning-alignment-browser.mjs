import {createRequire} from 'node:module'
import {createServer} from 'node:http'
import {readFile,mkdir,writeFile} from 'node:fs/promises'
import {resolve,extname,sep} from 'node:path'
import assert from 'node:assert/strict'
const require=createRequire(process.env.PLAYWRIGHT_PACKAGE??import.meta.url),{chromium}=require('playwright'),root=resolve('dist'),out=process.env.QA_OUTPUT_DIR
if(out)await mkdir(out,{recursive:true})
const server=createServer(async(req,res)=>{const path=resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));if(path!==root&&!path.startsWith(root+sep))return res.writeHead(403).end();try{let data,ext;try{data=await readFile(path);ext=extname(path)}catch{data=await readFile(resolve(root,'index.html'));ext='.html'}res.setHeader('Content-Type',{'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml'}[ext]??'application/octet-stream');res.end(data)}catch{res.writeHead(500).end()}})
await new Promise(done=>server.listen(0,'127.0.0.1',done));const origin='http://127.0.0.1:'+server.address().port
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH}),errors=[],layouts=[],checks=[]
async function fresh(){const c=await browser.newContext({viewport:{width:1440,height:1080}});await c.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//,r=>r.abort());const p=await c.newPage();p.setDefaultTimeout(12000);p.on('pageerror',e=>errors.push(e.message));return p}
async function capture(p,name){for(const width of [1440,1024,768]){await p.setViewportSize({width,height:1080});await p.waitForTimeout(150);const overflow=await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);layouts.push({name,width,overflow});assert.equal(overflow,false,name+width);if(out)await p.screenshot({path:`${out}/${name}-${width}.jpg`,type:'jpeg',fullPage:true})}}
try{
for(const finished of [false,true]){
 const p=await fresh(),c=p.context(),child={id:'student-contract',nickname:'시연 학생',grade:3,birthYear:2017}
 const mission={id:'contract-math',title:'직사각형의 넓이',subject:'수학',grade:3,gradeMax:4,thinkingType:'SOLVE',inputType:'SOLUTION_STEPS',question:'가로 6m, 세로 5m인 직사각형의 넓이를 구하세요.',hint:'넓이를 구하는 식을 생각해 보세요.',sceneUri:'',staticSceneUri:'',choices:[],categories:[],answerUnit:'m²',inputTemplate:['구하는 값','계산 과정']}
 const attempt={attemptId:'attempt-contract',studentId:child.id,mission,status:'IN_PROGRESS',helped:false,answers:finished?[{answerId:'answer-contract',version:1,submittedAt:new Date().toISOString(),inputType:'SOLUTION_STEPS',text:'6 × 5 = 30',feedback:{status:'DONE',judgment:{result:'CORRECT',trial:false},nextActions:['FINISH']}}]:[],...(finished?{finishedAt:new Date().toISOString(),revealKind:'ANSWER',reveal:'6 × 5 = 30m²',checklist:[{elementId:'steps',label:'계산 과정',satisfied:true,quote:'6 × 5',sourceType:'AI_OBSERVATION'},{elementId:'final',label:'최종 답',satisfied:true,quote:'30',sourceType:'ANSWER_KEY'}]}:{})}
 let role='PARENT',reflectionBody,assessmentBody
 await c.route('**/api/v1/**',async r=>{const path=new URL(r.request().url()).pathname,reply=(body,status=200)=>r.fulfill({status,contentType:'application/json',body:JSON.stringify(body)})
 if(path.endsWith('/auth/refresh'))return reply({accessToken:'fixture-parent',role})
 if(path.endsWith('/me'))return reply({role,child:role==='STUDENT'?child:undefined,nextAction:'READY',startPath:role==='PARENT'?'/parent/journal':'/student/home'})
 if(path.endsWith('/children'))return reply({items:[child]})
 if(path.endsWith('/auth/student-sessions')){role='STUDENT';return reply({role,accessToken:'fixture-student',child})}
 if(path.endsWith('/students/me/home'))return reply({student:child,state:'OK',missions:[mission],resume:attempt,period:{from:'2026-10-26',to:'2026-11-01'}})
 if(path.endsWith('/students/me/look'))return reply({theme:'lake',companion:'mungchi',updatedAt:null})
 if(path.endsWith('/self-assessment')){assessmentBody=r.request().postDataJSON();return reply(attempt.checklist.map(e=>({elementId:e.elementId,label:e.label,selfChecked:assessmentBody.checks.find(v=>v.elementId===e.elementId)?.checked??null,aiChecked:e.satisfied,quote:e.quote})))}
 if(path.endsWith('/reflection')){reflectionBody=r.request().postDataJSON();assert.equal(reflectionBody.difficulty,'NORMAL');attempt.status='COMPLETED';attempt.reflection=reflectionBody;return reply({attemptId:attempt.attemptId,status:'COMPLETED',reflection:reflectionBody})}
 if(path.endsWith('/attempts/attempt-contract'))return reply(attempt)
 if(path.endsWith('/missions'))return reply({items:[mission]})
 if(path.endsWith('/attempts')){const q=new URL(r.request().url()).searchParams;return reply({items:[],page:Number(q.get('page')??0),size:100,totalElements:0,studentId:child.id,childId:child.id,state:'NO_RECORD',period:{from:q.get('from'),to:q.get('to')}})}
 return reply({items:[],page:0,size:20,totalElements:0})})
 await p.goto(origin+'/oauth/complete');await p.getByRole('button',{name:'이 자녀로 학습 시작'}).click();await p.getByRole('button',{name:'이어서 작성하기'}).click()
 if(!finished){await p.getByLabel('최종 답',{exact:true}).fill('30');assert.equal(await p.getByLabel('답 단위',{exact:true}).innerText(),'m²');await p.getByLabel('구하는 값',{exact:true}).fill('직사각형의 넓이');await p.getByLabel('계산 과정',{exact:true}).fill('6 × 5 = 30');assert.equal(await p.getByRole('checkbox',{name:'최종 답',exact:true}).count(),0);checks.push('운영 빌드: 답 단위·수 입력·서버 입력 틀·마무리 전 자기 평가 숨김')}
 else{await p.getByRole('checkbox',{name:'최종 답',exact:true}).check();await p.getByRole('button',{name:'내 확인 저장',exact:true}).click();await p.getByRole('region',{name:'내 확인과 선생님 확인 비교'}).waitFor();assert.deepEqual(assessmentBody,{checks:[{elementId:'final',checked:true}]});await p.getByText('선택하지 않았어요',{exact:false}).waitFor();checks.push('운영 빌드: 최종 답 자기 평가 부분 저장·서버 비교 응답')}
 await capture(p,finished?'self-assessment':'answer-unit')
 if(finished){await p.getByRole('button',{name:'돌아보기 남기기'}).click();await p.getByRole('button',{name:'보통이에요',exact:true}).click();await p.getByRole('button',{name:'돌아보기 저장하고 완료'}).click();await p.getByRole('heading',{name:'나의 공책',exact:true}).waitFor();assert.equal(reflectionBody.difficulty,'NORMAL');checks.push('운영 빌드: NORMAL 전송 → 완료 → 내 공책')}
 await c.close()
}
const p=await fresh(),base=process.env.DEMO_URL??'http://127.0.0.1:5242'
await p.goto(base+'/admin/login');await p.getByLabel('이메일',{exact:true}).fill('admin@example.test');await p.getByRole('button',{name:'시연 계정으로 로그인'}).click();await p.waitForURL('**/admin/home');await p.getByRole('link',{name:'미션 관리',exact:true}).click();await p.getByRole('button',{name:'새 미션 작성',exact:true}).click()
await p.getByLabel('미션 제목',{exact:true}).fill('브라우저 검증: 직사각형의 넓이');await p.getByLabel('교과',{exact:true}).fill('수학');await p.getByLabel('미션 입력 방식',{exact:true}).selectOption('SOLUTION_STEPS');await p.getByLabel('미션 질문',{exact:true}).fill('가로 6m, 세로 5m인 직사각형의 넓이는 얼마인가요?');await p.getByLabel('답 단위',{exact:true}).fill('m²');await p.getByLabel('입력 틀',{exact:true}).fill('구하는 값\n계산 과정');await p.getByLabel('성취기준',{exact:true}).fill('직사각형의 넓이 구하기');await p.getByRole('button',{name:'미션 초안 저장',exact:true}).click();await p.getByRole('button',{name:'편집 닫기',exact:true}).waitFor()
for(let n=1;n<=2;n++){await p.getByRole('button',{name:'기준표 요소 추가',exact:true}).click();await p.getByLabel(`요소 ${n} 코드`,{exact:true}).fill(n===1?'FINAL_ANSWER':'STEPS');await p.getByLabel(`요소 ${n} 이름`,{exact:true}).fill(n===1?'최종 답':'넓이를 구하는 과정')}
await p.getByLabel('정답 수',{exact:true}).fill('30');await p.getByRole('button',{name:'새 기준표 버전 저장',exact:true}).click();await p.getByText('새 기준표 버전을 저장했습니다.',{exact:true}).waitFor();await p.getByRole('button',{name:'검토 요청',exact:true}).click();await p.getByRole('button',{name:'현재 버전 검토 승인',exact:true}).click();await p.getByText('서버 응답 · 검토 필요',{exact:true}).waitFor();await p.getByRole('button',{name:'게시',exact:true}).click();await p.getByText('서버 응답 · 공개',{exact:true}).waitFor();await p.getByLabel('미션 제목',{exact:true}).fill('브라우저 검증: 넓이 편집본 v2');await p.getByRole('button',{name:'새 미션 버전 저장',exact:true}).click();await p.getByText('편집본 v2',{exact:false}).first().waitFor();await p.getByText('학생 공개본 v1',{exact:false}).waitFor();await capture(p,'admin-mission');checks.push('DEV 화면: 미션 생성·기준표·정답 객체·검토·게시·편집본 v2/공개본 v1 유지')
assert.deepEqual(errors,[]);console.log(JSON.stringify({checks,layouts,errors},null,2))
}catch(e){if(out)for(const[i,c]of browser.contexts().entries())for(const p of c.pages()){console.error((await p.locator('body').innerText()).slice(-3500));await p.screenshot({path:`${out}/failure-${i}.jpg`,fullPage:true})}throw e}
finally{if(out)await writeFile(`${out}/results.json`,JSON.stringify({checks,layouts,errors},null,2));await browser.close();await new Promise(done=>server.close(done))}
