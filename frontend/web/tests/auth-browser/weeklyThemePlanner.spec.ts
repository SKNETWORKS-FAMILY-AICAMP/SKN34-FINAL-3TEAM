import { test, expect } from '@playwright/test'
import type { PlanChange } from '../../src/data/admin/themePlannerApi.ts'

test('주차 교환, 게시 전후 미편성 복귀, 잠긴 주 상세와 홈 대기 필터', async ({page,context})=>{
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
    if(p==='/admin/weekly-themes/'+chosen) return json({themeId:chosen,title:'공개할 이야기',status:'PUBLISHED',weekLocked:true,grade:'G4',
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
  await first.getByRole('button',{name:'게시 내용 보기'}).click()
  await expect(page.getByRole('heading',{name:/월요일 · 월요일 단서/})).toBeVisible()
  await expect(page.getByText(/읽기 전용/)).toBeVisible()
  await expect(page.getByRole('button',{name:'테마 저장'})).toHaveCount(0)
  await page.getByRole('button',{name:'편성 보드로'}).click()
  await page.getByRole('button',{name:'게시 검토 대기'}).click()
  await expect(page.getByText('게시 검토를 기다리는 테마가 없습니다.')).toBeVisible()
})
