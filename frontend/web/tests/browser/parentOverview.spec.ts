import { test, expect } from '@playwright/test'
test('기록 팝업 필터·원문 복귀·반응형 @responsive', async ({page}, info) => {
 const errors:string[]=[]; page.on('pageerror',e=>errors.push(e.message))
 await page.goto('/login'); await page.getByRole('button',{name:'시연 계정으로 로그인',exact:true}).click()
 await expect(page).toHaveURL(/parent\/journal/)
 await page.evaluate(async()=>{const path='/src/mocks/fixtures/sharing.ts';const {saveSharing}=await import(path);saveSharing('demo-seoyun',true)})
 await page.goto('/parent/journal?childId=demo-seoyun&from=2026-10-01&to=2026-10-31')
 await expect(page.getByRole('heading',{name:'서윤의 학습 현황'})).toBeVisible()
 await expect(page.locator('.pd-focus-value>strong')).toHaveText('3')
 await page.evaluate(()=>document.fonts.ready)
 await page.screenshot({path:info.outputPath('overview.png'),fullPage:true})
 await page.getByRole('button',{name:'생각 활동 전체 보기',exact:true}).click()
 const dialog=page.getByRole('dialog')
 await dialog.getByRole('button',{name:'날짜 필터'}).click()
 const picker=page.getByRole('group',{name:'날짜 선택',exact:true})
 await expect(picker).toBeVisible()
 const b=(await picker.boundingBox())!, v=page.viewportSize()!
 expect(b.x).toBeGreaterThanOrEqual(0);expect(b.x+b.width).toBeLessThanOrEqual(v.width);expect(b.y+b.height).toBeLessThanOrEqual(v.height)
 await page.screenshot({path:info.outputPath('date-filter.png')})
 await page.keyboard.press('Escape');await expect(picker).toHaveCount(0);await expect(dialog).toBeVisible()
 await expect(dialog.getByRole('button',{name:'날짜 필터'})).toBeFocused()
 await dialog.getByRole('button',{name:'유형 필터'}).click()
 await page.getByRole('group',{name:'유형 선택'}).getByRole('button',{name:'전체',exact:true}).click()
 await dialog.getByRole('textbox',{name:'활동 검색'}).fill('없는활동98765')
 await expect(dialog.getByText('조건에 맞는 활동이 없습니다.')).toBeVisible()
 await dialog.getByRole('button',{name:'검색·유형 초기화'}).click()
 await dialog.getByRole('button',{name:'원문 보기 ↗'}).first().click()
 await expect(dialog.locator('.pd-original-heading')).toBeVisible();await expect(dialog.locator('.pd-original-answer').first()).toBeVisible()
 await page.screenshot({path:info.outputPath('original.png')})
 await dialog.getByRole('button',{name:'← 목록으로'}).click();await expect(dialog.getByRole('textbox',{name:'활동 검색'})).toHaveValue('')
 await dialog.getByRole('button',{name:'참여 기록',exact:true}).click()
 await expect(dialog.getByRole('button',{name:'나눈 생각',exact:true})).toBeVisible()
 await dialog.getByRole('button',{name:'포인트 내역',exact:true}).click()
 await page.screenshot({path:info.outputPath('participation.png')})
 expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);expect(errors).toEqual([])
})

test('긴 활동 제목과 유형별 10건을 표시하고 목록으로 이동 @responsive',async({page},info)=>{
 await page.goto('/login');await page.getByRole('button',{name:'시연 계정으로 로그인',exact:true}).click();await expect(page).toHaveURL(/parent\/journal/)
 // This isolated browser's synthetic fixture only; never writes to the service DB.
 await page.evaluate(async()=>{
  const studentPath='/src/mocks/fixtures/student.ts',sharingPath='/src/mocks/fixtures/sharing.ts'
  const {fixtureStore,persistFixtureState}=await import(studentPath)
  const {saveSharing}=await import(sharingPath)
  const snapshot=fixtureStore.snapshot(),seed=snapshot.attempts.find((a:{studentId:string})=>a.studentId==='demo-seoyun')
  const topics=['도서관','새로운 운동장','우리 동네 버스','바다를 지키는 방법','친구와 함께 정한 약속']
  const types=['ANALYZE','EVALUATE','CREATE','SOLVE','REFLECT']
  const attempts=types.flatMap((type,t)=>Array.from({length:10},(_,i)=>{
   const a=structuredClone(seed);a.attemptId=`overview-${type}-${i}`
   a.mission={...a.mission,thinkingType:type,title:i%2===0?`${topics[t]}: 서로 다른 의견을 듣고 모두가 함께 지킬 수 있는 방법을 제안해 보세요 (${i+1})`:`${topics[t]} ${i+1}`}
   a.answers=a.answers.map((answer:{answerId:string},j:number)=>({...answer,answerId:`${a.attemptId}-${j}`}))
   return a
  }))
  fixtureStore.restoreSnapshot({...snapshot,attempts});persistFixtureState();saveSharing('demo-seoyun',true)
 })
 await page.goto('/parent/journal?childId=demo-seoyun&from=2026-10-01&to=2026-10-31')
 await expect(page.locator('.pd-focus-value>strong')).toHaveText('50')
 await expect(page.getByText('10개 미션에서 관찰',{exact:true})).toHaveCount(5)
 // Match the service's three process metrics in this browser-only visual fixture.
 await page.evaluate(async()=>{
  const path='/src/data/queryClient.ts', {queryClient}=await import(path)
  const key=['parent','summary',{childId:'demo-seoyun',from:'2026-10-01',to:'2026-10-31'}]
  const summary=queryClient.getQueryData(key),base=summary.metrics[0]
  const metrics=[
   {label:'완료한 활동',numerator:50,formula:'완료한 활동 / 전체 활동'},
   {label:'도움 없이 시작한 활동',numerator:46,formula:'도움 없이 시작한 활동 / 전체 활동'},
   {label:'되묻기 후 생각을 더한 활동',numerator:3,formula:'되묻기 후 보완 답변이 있는 활동 / 전체 활동'},
  ].map(m=>({...base,...m,count:m.numerator,denominator:50,value:m.numerator/50,state:'OK'}))
  queryClient.setQueryData(key,{...summary,metrics:[base,...metrics]})
 })
 await expect(page.locator('.pd-kpi')).toHaveCount(3)
 const rows=page.locator('.pd-types li')
 for(let i=0;i<5;i++){
  await expect(rows.nth(i).locator('.pd-recent-missions>button:not(.pd-more-dots)')).toHaveCount(5)
  expect(await rows.nth(i).evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true)
 }
 await page.locator('.pd-metric-definition summary').first().click()
 await expect(page.locator('.pd-metric-definition[open] p')).toBeVisible()
 await page.locator('.pd-metric-definition summary').first().click()
 await page.evaluate(()=>document.fonts.ready)
 await page.screenshot({path:info.outputPath('overview-dense.png'),fullPage:true})
 expect(await page.locator('.pd-overview').evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true)
 await page.getByRole('button',{name:'분석하기 자세히 보기',exact:true}).click()
 await expect(page.getByRole('dialog').getByText('10개 활동',{exact:true})).toBeVisible()
})
test('비공개 원문 요청 없음 @responsive',async({page})=>{
 const requests:string[]=[];page.on('request',r=>{if(/\/children\/[^/]+\/(?:attempts|records)(?:\/|$)/.test(new URL(r.url()).pathname))requests.push(r.url())})
 await page.goto('/login');await page.getByRole('button',{name:'시연 계정으로 로그인',exact:true}).click();await expect(page).toHaveURL(/parent\/journal/)
 await page.getByRole('button',{name:'생각 활동 전체 보기',exact:true}).click()
 await expect(page.getByText('원문 비공개 상태에서는 날짜와 답변을 표시하지 않습니다.')).toBeVisible()
 await expect(page.getByRole('button',{name:'원문 보기 ↗'})).toHaveCount(0);expect(requests).toEqual([])
})
