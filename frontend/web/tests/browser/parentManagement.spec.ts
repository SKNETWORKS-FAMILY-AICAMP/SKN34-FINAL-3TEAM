import {test,expect} from '@playwright/test'
test('parent seven pages readable layout @responsive',async({page},info)=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message))
 await page.goto('/login');await page.getByRole('button',{name:'시연 계정으로 로그인',exact:true}).click();await expect(page).toHaveURL(/parent\/journal/)
 for(const [route,title] of [['report','리포트·AI 챗봇'],['settings','계정·자녀 설정'],['devices','기기·PIN'],['billing','이용권·결제'],['help','이용 도움말'],['support','문의·오류 신고'],['notices','공지·점검 안내']]){
  await page.goto(`/parent/${route}?childId=demo-seoyun`);await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();await page.waitForTimeout(350)
  await expect(page.locator('#parent-main .parent-child-picker')).toHaveCount(0);await expect(page.locator('.ws-header').getByRole('combobox',{name:'현재 자녀 선택'})).toBeVisible();if(route==='report'){await expect(page.locator('.report-overview')).toHaveCount(0);await expect(page.getByRole('button',{name:'리포트 자세히 보기',exact:false})).toBeVisible()}
  if(route==='settings'){await expect(page.getByRole('heading',{name:'서윤의 프로필'})).toBeVisible();await page.getByRole('tab',{name:'공개·동의',exact:true}).click();await expect(page.getByRole('heading',{name:'동의 이력·철회'})).toBeVisible();await page.screenshot({path:info.outputPath('consents.png'),fullPage:true});const trigger=page.getByRole('button',{name:'동의 문서·이력 보기'}).first();await trigger.click();const reader=page.getByRole('dialog');await expect(reader.locator('.consent-document-text')).toBeVisible();expect(await reader.locator('.consent-document-text').evaluate(el=>getComputedStyle(el).overflowY)).toBe('visible');await page.screenshot({path:info.outputPath('consent-document.png'),fullPage:true});await page.keyboard.press('Escape');await expect(reader).toHaveCount(0);await expect(trigger).toBeFocused();await page.getByRole('tab',{name:'프로필',exact:true}).click()}
  if(route==='devices'){await expect(page.locator('.device-setup-steps li')).toHaveCount(3)}
  if(route==='billing'){await expect(page.locator('#current-subscriptions')).toHaveCount(1);const current=await page.locator('#current-subscriptions').boundingBox(),free=await page.locator('.parent-free-plan').first().boundingBox();if(current&&free)expect(current.y).toBeLessThan(free.y)}
  if(route==='help'){await page.locator('.service-reading-list summary').first().click();await expect(page.locator('.service-reading-body').first()).toBeVisible()}
  if(route==='support'){await page.getByRole('button',{name:'학습 결과가 이상해요',exact:true}).click();await expect(page.getByRole('button',{name:'접수하기',exact:true})).toBeDisabled()}
  if(route==='notices'){await page.getByRole('textbox',{name:'공지 제목 검색'}).fill('없는공지-visual-check');await expect(page.locator('.service-empty')).toBeVisible();await page.getByRole('textbox',{name:'공지 제목 검색'}).fill('')}
  await page.screenshot({path:info.outputPath(`${route}.png`),fullPage:true})
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true)
 }
 expect(errors).toEqual([])
})


test('header child selection persists across parent categories @responsive',async({page},info)=>{
 await page.goto('/login');await page.getByRole('button',{name:'시연 계정으로 로그인',exact:true}).click();await expect(page).toHaveURL(/parent\/journal/)
 const picker=page.locator('.ws-header').getByRole('combobox',{name:'현재 자녀 선택'})
 await expect(picker).toBeVisible();await picker.selectOption('demo-doyun')
 await expect(page).toHaveURL(/childId=demo-doyun/)
 const notification=page.getByRole('button',{name:'알림 열기'})
 await expect(notification).toBeVisible()
 await expect.poll(async()=>{
  const selected=await picker.boundingBox(),bell=await notification.boundingBox()
  // 넓은 화면에서는 알림 왼쪽, 좁은 화면에서는 다음 줄에 표시하며 서로 겹치지 않는다.
  return !!selected && !!bell && (selected.x+selected.width<=bell.x+1 || selected.y>=bell.y+bell.height-1)
 }).toBe(true)
 await page.goto('/parent/settings');await expect(picker).toHaveValue('demo-doyun');await expect(page.getByRole('heading',{name:'도윤의 프로필'})).toBeVisible()
 await page.goto('/parent/notices');await expect(picker).toHaveValue('demo-doyun')
 await page.screenshot({path:info.outputPath('header-child-picker.png')})
 if(info.project.name==='compact'){await page.getByRole('button',{name:'학부모 메뉴 열기'}).click();await expect(page.getByRole('dialog').getByRole('button',{name:'로그아웃'})).toBeVisible()}
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true)
})
