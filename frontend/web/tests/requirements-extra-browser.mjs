import {createRequire} from 'node:module'
import assert from 'node:assert/strict'
import {mkdir,writeFile} from 'node:fs/promises'
import path from 'node:path'
const require=createRequire(process.env.PLAYWRIGHT_PACKAGE??import.meta.url)
const {chromium}=require('playwright')
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH})
const base=process.env.DEMO_URL??'http://127.0.0.1:5230',out=process.env.QA_OUTPUT_DIR
if(out)await mkdir(out,{recursive:true})
const context=await browser.newContext({viewport:{width:1440,height:900}})
await context.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//,r=>r.abort())
await context.route('**/login?reauthMock=1',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><p>개발용 재확인 완료</p>'}))
const p=await context.newPage(),errors=[],layouts=[]
p.setDefaultTimeout(15000);p.on('pageerror',e=>errors.push(e.message))
async function go(to){if(new URL(p.url()).pathname===to)return;if(!await p.locator('a[href="'+to+'"]').count()){await p.locator('a[href="/admin/home"]').first().click();await p.waitForURL(u=>u.pathname==='/admin/home')}await p.locator('a[href="'+to+'"]').first().click();await p.waitForURL(u=>u.pathname===to)}
try{
  await p.goto(base+'/login-help');await p.getByRole('heading',{name:'로그인이 어려우신가요?'}).waitFor()
  assert.equal(await p.getByRole('link',{name:'Google 계정 복구'}).getAttribute('href'),'https://accounts.google.com/signin/recovery')
  console.log('PASS Google·학생 기기 로그인 복구 안내')
  await p.goto(base+'/review');await p.getByRole('button',{name:'관리자 시연 시작'}).click()
  await p.getByRole('heading',{name:'모델·프롬프트 버전',exact:true}).waitFor()
  for(const width of [1440,1024,768,390]){
    await p.setViewportSize({width,height:900})
    for(const page of ['models','usage','support']){
      await go('/admin/'+page);await p.waitForTimeout(250)
      const overflow=await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2)
      assert.equal(overflow,false,'관리자 가로 넘침 '+page+' '+width)
      layouts.push({width,page,overflow})
      if(out)await p.screenshot({path:path.join(out,page+'-'+width+'.jpg'),type:'jpeg',fullPage:true})
    }
  }
  console.log('PASS 관리자 3개 화면 × 4개 규격')
  await go('/review');await p.getByRole('button',{name:'학부모 시연 시작'}).click();await go('/parent/account')
  const section=p.locator('section').filter({has:p.getByRole('heading',{name:'회원 탈퇴',exact:true})}).last()
  await section.getByRole('button',{name:'구독·환불 상태 먼저 확인'}).click()
  await section.getByText('진행 중 구독 0건',{exact:false}).waitFor()
  await section.getByRole('button',{name:'Google 본인 확인',exact:true}).click()
  await section.getByRole('button',{name:'완료 확인',exact:true}).click()
  await section.getByText('재확인을 마쳤습니다.',{exact:false}).waitFor()
  await section.getByLabel('계정과 자녀 정보에 미치는 영향을 확인했습니다.').check()
  await section.getByRole('button',{name:'탈퇴 요청 확정'}).click()
  await p.waitForURL('**/withdrawal-status')
  await p.getByRole('heading',{name:'탈퇴 처리 상태',exact:true}).waitFor()
  await p.getByRole('button',{name:'처리 상태 확인'}).click()
  await p.getByText('탈퇴 요청 접수 · 자녀 정보 삭제 처리 중',{exact:true}).waitFor()
  assert.equal(new URL(p.url()).search,'')
  console.log('PASS 탈퇴 사전 확인·Google 재확인·메모리 영수증으로 처리 상태 조회')
  assert.deepEqual(errors,[])
}catch(e){console.error(e);console.error((await p.locator('body').innerText()).slice(-2000));if(out)await p.screenshot({path:path.join(out,'failure.jpg'),type:'jpeg'}).catch(()=>{});throw e}
finally{if(out)await writeFile(path.join(out,'results.json'),JSON.stringify({layouts,pageErrors:errors},null,2));await browser.close()}
