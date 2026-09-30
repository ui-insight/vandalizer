import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import {resolve} from 'node:path'
import {createReview} from './harness.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page}=review
page.setDefaultTimeout(15000)
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id+': overflow');assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': accessibility');console.log('Captured '+id)}
async function contained(dialog){for(let i=0;i<12;i++){await page.keyboard.press('Tab');assert.equal(await dialog.evaluate(e=>e.contains(document.activeElement)),true)}for(let i=0;i<12;i++){await page.keyboard.press('Shift+Tab');assert.equal(await dialog.evaluate(e=>e.contains(document.activeElement)),true)}}
async function reachable(control){await control.focus();assert.equal(await control.evaluate(e=>{const r=e.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight&&r.left>=0&&r.right<=innerWidth&&e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))}),true)}
try{
 for(const[width,height]of[[320,480],[640,450],[1440,900]]){
  await page.setViewportSize({width,height});await page.goto(review.baseURL+'/?mode=knowledge')
  const source=page.getByRole('region',{name:'Workspace source panel',exact:true}),trigger=source.getByRole('button',{name:'New',exact:true})
  await trigger.focus();await page.keyboard.press('Enter');const dialog=page.getByRole('dialog',{name:'Create Knowledge Base',exact:true});await dialog.waitFor()
  await page.waitForTimeout(50);assert.equal(await dialog.getByRole('textbox',{name:'Title',exact:true}).evaluate(e=>e===document.activeElement),true)
  await dialog.getByRole('textbox',{name:'Title',exact:true}).fill('LongKnowledgeBaseNameWithoutSpaces'.repeat(3));await dialog.getByRole('textbox',{name:'Description',exact:true}).fill('A long description with translated labels: Forschungsförderung, gestion des subventions, 研究資料. '.repeat(8))
  await contained(dialog);await reachable(dialog.getByRole('button',{name:'Create',exact:true}));await shot(`access-dialog-long-form-${width}`)
  await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});await page.waitForTimeout(50);assert.equal(await trigger.evaluate(e=>e===document.activeElement),true)
  const about=source.getByRole('button',{name:'What are knowledge bases?',exact:true});await about.click()
  const help=page.getByRole('dialog',{name:'About knowledge bases',exact:true});await help.waitFor();await contained(help);await shot(`access-knowledge-help-${width}`)
  await page.keyboard.press('Escape');await help.waitFor({state:'hidden'});await page.waitForTimeout(50);assert.equal(await about.evaluate(e=>e===document.activeElement),true)
  // Tabs use one tab stop and support arrow keys; selection follows keyboard focus.
  const mine=page.getByRole('tab',{name:'Mine',exact:true});await mine.focus();await page.keyboard.press('ArrowRight');assert.equal(await page.getByRole('tab',{name:'Team',exact:true}).getAttribute('aria-selected'),'true');await shot(`access-scope-keyboard-${width}`)
  await page.goto(review.baseURL+'/?mode=files');const checkbox=page.getByRole('checkbox',{name:'Select Proposal narrative.pdf',exact:true});await checkbox.focus();await page.keyboard.press('Space');assert.equal(await checkbox.isChecked(),true)
  for(let i=0;i<12;i++){await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>!document.activeElement.closest('[inert]')),true)}
  await shot(`access-file-keyboard-${width}`)
  await page.goto(review.baseURL+'/?mode=chat');await page.getByRole('textbox',{name:'Message input'}).fill('Summarize the source');await page.getByRole('button',{name:'Send message'}).click();await page.getByText('The proposal is due October 15',{exact:false}).first().waitFor();await shot(`access-chat-reduced-motion-${width}`)
  assert.equal(await page.evaluate(()=>matchMedia('(prefers-reduced-motion: reduce)').matches),true)
  assert.deepEqual(await page.evaluate(()=>[...document.querySelectorAll('.animate-spin')].filter(e=>e.checkVisibility()).map(e=>getComputedStyle(e).animationDuration).filter(s=>parseFloat(s)>0.001)),[])
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push('Tab/Shift+Tab containment, initial focus, Escape restoration, source selection and scope arrow navigation pass at 320×480, 640×450 and desktop. Long unbroken names and multilingual descriptions are fixture text. Reduced motion is emulated; this checks DOM/live-region behavior, not speech output from a screen reader.')
}finally{await review.flush();await review.browser.close()}
