import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import {resolve} from 'node:path'
import {createReview} from './harness.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page}=review
page.setDefaultTimeout(15000)
let release, creates=0
await page.route('**/api/folders/create',async route=>{
 if(route.request().method()!=='POST')return route.fallback()
 creates++;await new Promise(resolve=>{release=resolve});await route.fulfill({json:{uuid:'new-review-folder',name:'Review evidence',parent_uuid:null}})
})
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[]);assert.deepEqual(review.captures.at(-1).smallControls,[],id+': control targets');console.log('Captured '+id)}
async function focusVisible(control){await control.focus();await page.keyboard.press('Tab');await page.keyboard.press('Shift+Tab');assert.equal(await control.evaluate(e=>e===document.activeElement&&getComputedStyle(e).outlineStyle!=='none'&&parseFloat(getComputedStyle(e).outlineWidth)>=2),true)}
try{
 for(const[width,height]of[[320,568],[768,600],[1440,900]]){
  await page.setViewportSize({width,height});await page.goto(review.baseURL+'/?mode=files')
  const selected=page.getByRole('checkbox',{name:'Select Proposal narrative.pdf',exact:true});await focusVisible(selected);await page.keyboard.press('Space');assert.equal(await selected.isChecked(),true);await shot(`actions-file-selection-focus-${width}`);await page.keyboard.press('Space')
  await page.getByRole('region',{name:'Workspace source panel',exact:true}).getByRole('button',{name:'Add',exact:true}).click();await page.getByRole('menuitem',{name:'New Folder',exact:true}).click()
  const dialog=page.getByRole('dialog',{name:'New Folder',exact:true});await dialog.waitFor()
  const create=dialog.getByRole('button',{name:'Create',exact:true});await focusVisible(create);await shot(`actions-primary-keyboard-${width}`)
  const normal=await create.evaluate(e=>getComputedStyle(e).backgroundColor);await create.hover();assert.notEqual(await create.evaluate(e=>getComputedStyle(e).backgroundColor),normal);await shot(`actions-primary-hover-${width}`)
  await dialog.getByRole('textbox',{name:'Folder name',exact:true}).fill('Review evidence');await create.click();const pending=dialog.getByRole('button',{name:'Creating…',exact:true});await pending.waitFor();assert.equal(await pending.isDisabled(),true);assert.equal(await pending.getAttribute('aria-busy'),'true');await shot(`actions-folder-saving-${width}`);release();await dialog.waitFor({state:'hidden'})
  await page.goto(review.baseURL+'/?mode=automations');await page.getByRole('button',{name:'New',exact:true}).click();const wizard=page.getByRole('dialog',{name:'New Automation',exact:true});await shot(`actions-wizard-disabled-${width}`)
  await wizard.getByPlaceholder('e.g. Process grant applications').fill('Keyboard review');await wizard.getByRole('button',{name:'Next',exact:true}).click();await page.keyboard.press('Escape')
  const discard=page.getByRole('dialog',{name:'Discard this automation draft?',exact:true});await discard.waitFor();await focusVisible(discard.getByRole('button',{name:'Keep editing',exact:true}));await shot(`actions-destructive-review-${width}`);await page.keyboard.press('Enter');await discard.waitFor({state:'hidden'});assert.equal(await wizard.isVisible(),true)
 }
 assert.equal(creates,3);assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push('Keyboard file selection, primary hover/focus, pending and disabled actions, and destructive draft review are exercised at three sizes. All visible enabled controls in these states meet the 24px minimum; action buttons use 36px. Folder writes are synthetic and pending responses are explicitly released.')
}finally{release?.();await review.flush();await review.browser.close()}
