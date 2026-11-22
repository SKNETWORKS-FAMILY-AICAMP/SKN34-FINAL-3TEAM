import { test, expect } from '@playwright/test'
import type { PlanChange } from '../../src/data/admin/themePlannerApi.ts'

test('주차 교환, 게시 전후 미편성 복귀, 게시된 주의 테마 관리와 홈 대기 필터', async ({page,context})=>{
  const a='11111111-1111-4111-8111-111111111111', b='22222222-2222-4222-8222-222222222222', chosen='33333333-3333-4333-8333-333333333333'
  const base=new Date();base.setUTCDate(base.getUTCDate()+((8-base.getUTCDay())%7||7))
  const weeks=Array.from({length:4},(_,i)=>new Date(base.getTime()+7*i*86400000).toISOString().slice(0,10))
  const candidates=[{draftId:a,title:'숲의 단서',generationWeek:weeks[0],plannedWeek:weeks[0] as string|null},
    {draftId:b,title:'호숫가 지도',generationWeek:weeks[0],plannedWeek:weeks[1] as string|null}]
  let published=false
  const changes:PlanChange[]=[]
  const publications:unknown[]=[]
  await context.route('**/api/v1/**',async route=>{
    const req=route.request(),url=new URL(req.url()),p=url.pathname.replace('/api/v1','')
    const json=(obj:unknown,status=200)=>route.fulfill({status,json:obj})
    if(p==='/auth/refresh') return json({role:'ADMIN',accessToken:'synthetic',expiresIn:900,nextAction:'READY',startPath:'/admin/home'})
    if(p==='/me') return json({role:'ADMIN',name:'테스트 관리자',permissions:['CONTENT'],userId:'synthetic',nextAction:'READY',startPath:'/admin/home'})
    if(p==='/notifications/stream') return route.abort()
    if(p==='/admin/weekly-themes/planner' && req.method()==='GET') return json({grade:'G4',weekStart:weeks[0],candidates,
      weeks:weeks.map((weekStart,i)=>({weekStart,locked:i===0&&published,planned:candidates.find(c=>c.plannedWeek===weekStart)??null,
        themes:i===0?[{themeId:chosen,title:'공개할 이야기',version:3,status:published?'PUBLISHED':'REVIEW_REQUIRED'}]:[]}))})
    if(p==='/admin/weekly-themes/planner' && req.method()==='PUT') {
      const plan=req.postDataJSON() as PlanChange; changes.push(plan)
      candidates[0].plannedWeek=plan.targetWeek;candidates[1].plannedWeek=plan.expectedWeek
      return json({draftId:a,plannedWeek:plan.targetWeek,grade:'G4',displacedDraftId:b})
    }
    if(p==='/admin/weekly-themes/'+chosen+'/publish') {
      publications.push(req.postDataJSON());published=true;candidates[1].plannedWeek=null
      return json({themeId:chosen,status:'PUBLISHED'})
    }
    if(p==='/admin/weekly-themes/'+chosen) return json({themeId:chosen,title:'공개할 이야기',status:'PUBLISHED',weekLocked:true,grade:'G4',version:3,publishedVersion:3,reviewRequested:false,
      weekStart:weeks[0],intro:'시작 이야기 본문',outro:'종료 이야기 본문',days:[{day:'MON',missionId:'m',title:'월요일 단서'}]})
    if(p==='/admin/weekly-themes' && url.searchParams.get('status')==='REVIEW_REQUIRED') return json({items:published?[]:[{themeId:chosen,title:'공개할 이야기',grade:'G4',weekStart:weeks[0]}],totalElements:published?0:1,page:0,size:20})
    return json({items:[],totalElements:0,page:0,size:20})
  })
  await page.goto('/admin/themes?status=REVIEW_REQUIRED')
  await expect(page.getByRole('heading',{name:'게시 검토 대기'})).toBeVisible()
  await page.getByRole('button',{name:'해당 주차에서 게시 검토'}).click()
  const first=page.getByRole('region',{name:weeks[0]+' 주차'})
  const second=page.getByRole('region',{name:weeks[1]+' 주차'})
  await expect(first.getByText('숲의 단서')).toBeVisible()
  await first.getByRole('button',{name:'주차 변경·맞바꾸기'}).click()
  await page.getByRole('button',{name:'변경 내용 확인'}).click()
  await expect(page.getByRole('dialog')).toContainText('호숫가 지도')
  await page.getByRole('dialog').getByRole('button',{name:'편성 확정'}).click()
  await expect(first.getByText('호숫가 지도')).toBeVisible();await expect(second.getByText('숲의 단서')).toBeVisible()
  expect(changes).toEqual([{grade:'G4',draftId:a,expectedWeek:weeks[0],targetWeek:weeks[1],expectedTargetDraftId:b}])
  await page.reload();await expect(second.getByText('숲의 단서')).toBeVisible()
  await first.getByRole('button',{name:'최종 게시'}).click()
  await expect(page.getByRole('dialog')).toContainText('호숫가 지도')
  await page.getByRole('dialog').getByRole('button',{name:'취소'}).click()
  expect(publications).toHaveLength(0)
  await first.getByRole('button',{name:'최종 게시'}).click()
  await page.getByRole('dialog').getByRole('button',{name:'최종 게시 확정'}).click()
  await expect(first.getByRole('button',{name:'최종 게시'})).toHaveCount(0)
  expect(publications).toEqual([{expectedVersion:3,expectedPlannedDraftId:b}])
  await second.getByRole('button',{name:'주차 변경·맞바꾸기'}).click()
  await page.getByLabel('편성 주차 (월요일)').fill(weeks[0])
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText('이미 게시된 주차')
  await expect(page.getByRole('button',{name:'변경 내용 확인'})).toBeDisabled()
  await page.getByRole('dialog').getByRole('button',{name:'취소'}).click()
  expect(changes).toHaveLength(1)
  await first.getByRole('button',{name:'게시 테마 관리'}).click()
  await page.getByText('작업본의 요일별 장면').click()
  await expect(page.getByRole('heading',{name:/월요일 · 월요일 단서/})).toBeVisible()
  await expect(page.getByRole('textbox',{name:'테마 제목'})).toBeEditable()
  await expect(page.getByLabel('주 시작일')).toHaveCount(0)
  await expect(page.getByRole('button',{name:'제공 중단',exact:true})).toBeVisible()
  await page.getByRole('button',{name:'편성 보드로'}).click()
  await page.getByRole('button',{name:'게시 검토 대기'}).click()
  await expect(page.getByText('게시 검토를 기다리는 테마가 없습니다.')).toBeVisible()
})

test('같은 테마의 수정본 검토와 재게시, 제공 중단과 제공 재개', async ({page,context}) => {
  const id = '33333333-3333-4333-8333-333333333333'
  const base = '/admin/weekly-themes'
  const detailPath = base + '/' + id
  const week = '2030-01-07'
  const days = ['MON','TUE','WED','THU','FRI'].map((day,i) => ({day, missionId:'m'+i}))
  const theme = {themeId:id, grade:'G4', weekStart:week, status:'PUBLISHED', version:3, publishedVersion:3,
    reviewRequested:false, title:'처음 게시한 테마', intro:'도입 이야기', days, generationWeek:'2029-12-31'}
  let publicTitle = theme.title
  const mutations: {path:string; body:unknown}[] = []
  await context.route('**/api/v1/**', async route => {
    const request = route.request(), p = new URL(request.url()).pathname.replace('/api/v1','')
    const json = (obj:unknown) => route.fulfill({json:obj})
    if (p === '/auth/refresh') return json({role:'ADMIN',accessToken:'synthetic',expiresIn:900,nextAction:'READY',startPath:'/admin/home'})
    if (p === '/me') return json({role:'ADMIN',name:'테스트 관리자',permissions:['CONTENT'],userId:'synthetic',nextAction:'READY',startPath:'/admin/home'})
    if (p === '/notifications/stream') return route.abort()
    const active = theme.status === 'PUBLISHED'
    if (p === base+'/planner') return json({grade:theme.grade,weekStart:week,candidates:[],weeks:[{weekStart:week,locked:active,planned:null,
      themes:[{themeId:id,status:theme.status,title:active?publicTitle:theme.title,version:active?theme.publishedVersion:theme.version}]}]})
    if (p === detailPath && request.method() === 'GET') return json({...theme,weekLocked:active})
    if (p.startsWith(detailPath) && request.method() !== 'GET') {
      const body = request.postDataJSON()
      mutations.push({path:p,body})
      if (p === detailPath && request.method()==='PUT') {
        theme.version++
        theme.title = body.title
        theme.reviewRequested = false
      } else if (p === detailPath+'/review-request') {
        theme.reviewRequested = true
        if (!active) theme.status = 'REVIEW_REQUIRED'
      } else if (p === detailPath+'/publish') {
        publicTitle = theme.title
        theme.publishedVersion = theme.version
        theme.status = 'PUBLISHED'
      } else if (p === detailPath+'/unpublish') {
        theme.status = 'UNPUBLISHED'
        theme.reviewRequested = false
      }
      return json({...theme,weekLocked:theme.status==='PUBLISHED'})
    }
    return json({items:[],totalElements:0,page:0,size:20})
  })
  await page.goto('/admin/themes?grade=G4&weekStart='+week)
  await page.getByRole('button',{name:'게시 테마 관리'}).click()
  await expect(page.getByText('학생 게시본 v3')).toBeVisible()
  await expect(page.getByRole('button',{name:'수정본 검토 요청'})).toHaveCount(0)
  await page.getByLabel('테마 제목').fill('재검토할 테마')
  await page.getByRole('button',{name:'테마 저장'}).click()
  await expect(page.getByText(/작업본 v4/)).toBeVisible()
  expect(mutations[0]).toMatchObject({path:detailPath,body:{expectedVersion:3,title:'재검토할 테마',grade:'G4',weekStart:week}})
  await page.getByRole('button',{name:'편성 보드로'}).click()
  await expect(page.getByRole('region',{name:week+' 주차'})).toContainText('처음 게시한 테마')
  await page.getByRole('button',{name:'게시 테마 관리'}).click()
  await expect(page.getByLabel('테마 제목')).toHaveValue('재검토할 테마')
  await page.getByRole('button',{name:'수정본 검토 요청'}).click()
  await page.getByRole('button',{name:'수정본 재게시'}).click()
  await expect(page.getByRole('dialog')).toContainText('v4')
  await page.getByRole('button',{name:'재게시 확정'}).click()
  await expect(page.getByText('학생 게시본 v4')).toBeVisible()
  expect(mutations.slice(1)).toEqual([
    {path:detailPath+'/review-request',body:{expectedVersion:4}},
    {path:detailPath+'/publish',body:{expectedVersion:4,expectedPlannedDraftId:null}},
  ])
  await page.getByRole('button',{name:'제공 중단',exact:true}).click()
  await page.getByRole('dialog').getByRole('button',{name:'취소'}).click()
  expect(mutations).toHaveLength(3)
  await page.getByRole('button',{name:'제공 중단',exact:true}).click()
  await page.getByRole('button',{name:'제공 중단 확정'}).click()
  await expect(page.getByText('테마 제공을 중단했습니다.')).toBeVisible()
  expect(mutations[3]).toEqual({path:detailPath+'/unpublish',body:{expectedPublishedVersion:4}})
  await page.getByLabel('테마 제목').fill('아직 저장하지 않은 제목')
  await expect(page.getByRole('button',{name:'검토 요청',exact:true})).toBeDisabled()
  await page.getByLabel('테마 제목').fill('재검토할 테마')
  await page.getByRole('button',{name:'검토 요청',exact:true}).click()
  await page.getByRole('button',{name:'최종 게시',exact:true}).click()
  await page.getByRole('button',{name:'최종 게시 확정'}).click()
  await expect(page.getByRole('button',{name:'게시 테마 관리'})).toBeVisible()
  expect(mutations.slice(4)).toEqual([
    {path:detailPath+'/review-request',body:{expectedVersion:4}},
    {path:detailPath+'/publish',body:{expectedVersion:4,expectedPlannedDraftId:null}},
  ])
})
