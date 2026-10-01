import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL}),{page}=review
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id+': page overflow');assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': accessibility');console.log('Captured '+id)}
try{
 for(const width of [320,390,768,1024,1440]){
  await page.setViewportSize({width,height:width<400?568:800});await page.goto(review.baseURL+'/docs');await page.getByRole('heading',{name:'Review a proposal with its sources'}).waitFor()
  const menu=page.getByRole('button',{name:'Open documentation navigation'});if(await menu.isVisible()){await menu.focus();await page.keyboard.press('Enter');await page.getByRole('dialog',{name:'Documentation navigation'}).waitFor();await page.keyboard.press('Escape');assert.equal(await menu.evaluate(e=>e===document.activeElement),true)}
  const unresolved=await page.locator('a[href^="#"]').evaluateAll(links=>links.map(a=>a.getAttribute('href').slice(1)).filter(id=>id&&!document.getElementById(id)));assert.deepEqual(unresolved,[])
  await page.locator('#user-guide').scrollIntoViewIfNeeded();await shot('docs-task-guide-'+width)
  const examples=page.getByRole('region',{name:'Scrollable documentation example'});for(const region of await examples.all()){assert.equal(await region.getAttribute('tabindex'),'0')}
  await page.locator('#getting-started').scrollIntoViewIfNeeded();await page.getByRole('link',{name:'Open workspace',exact:true}).click();await page.getByRole('navigation',{name:'Workspace navigation'}).waitFor()
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[]);review.observations.push({evidence:'Five-width Docs anchor, mobile modal focus/Escape, named code/table regions and workspace return. RA steps cross-checked with file-readiness, chat reading/export, Library reuse, extraction export, workflow guidance and review recovery scripts; those prove UI contracts, not answer correctness or backend execution.'})
}catch(error){await review.capture('docs-walkthrough-blocked',String(error));throw error}finally{await review.flush();await review.browser.close()}
