import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import {resolve} from 'node:path'
import {createReview} from './harness.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page}=review
page.setDefaultTimeout(15000)
await page.route('**/api/folders/create',r=>r.fulfill({status:503,json:{detail:'Folder service unavailable'}}))
await page.route('**/api/knowledge/create',r=>r.fulfill({status:503,json:{detail:'Knowledge service unavailable'}}))
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[]);console.log('Captured '+id)}
async function associated(input,part){assert.equal(await input.getAttribute('aria-invalid'),'true');assert.equal(await input.evaluate((e,part)=>(e.getAttribute('aria-describedby')||'').split(' ').map(id=>document.getElementById(id)?.textContent).join(' ').includes(part),part),true);assert.equal(await input.evaluate(e=>e===document.activeElement),true)}
try{
 for(const[width,height]of[[320,568],[768,600],[1440,900]]){
  await page.setViewportSize({width,height});await page.goto(review.baseURL+'/?mode=files')
  await page.getByRole('region',{name:'Workspace source panel',exact:true}).getByRole('button',{name:'Add',exact:true}).click();await page.getByRole('menuitem',{name:'New Folder',exact:true}).click()
  const folder=page.getByRole('dialog',{name:'New Folder',exact:true}),name=folder.getByRole('textbox',{name:'Folder name',exact:true})
  await folder.getByRole('button',{name:'Create',exact:true}).click();await associated(name,'cannot be empty');await shot(`form-folder-required-${width}`)
  await name.fill('Review evidence');await folder.getByRole('button',{name:'Create',exact:true}).click();await folder.getByRole('alert').filter({hasText:'service unavailable'}).waitFor();assert.equal(await name.getAttribute('aria-invalid'),'false');assert.equal(await name.inputValue(),'Review evidence');await shot(`form-folder-save-error-${width}`)
  await page.goto(review.baseURL+'/?mode=knowledge');await page.getByRole('region',{name:'Workspace source panel',exact:true}).getByRole('button',{name:'New',exact:true}).click()
  const kb=page.getByRole('dialog',{name:'Create Knowledge Base',exact:true}),title=kb.getByRole('textbox',{name:'Title',exact:true}),description=kb.getByRole('textbox',{name:'Description',exact:true})
  assert.equal(await title.getAttribute('aria-required'),'true');await shot(`form-knowledge-guidance-${width}`)
  await title.fill('Research administration policies');await kb.getByRole('button',{name:'Create',exact:true}).click();await associated(title,'already exists');await shot(`form-knowledge-duplicate-${width}`)
  await title.fill('New review knowledge');await description.fill('Guidance for internal proposal review.');await kb.getByRole('button',{name:'Create',exact:true}).click();await kb.getByRole('alert').filter({hasText:'service unavailable'}).waitFor();assert.equal(await title.getAttribute('aria-invalid'),'false');assert.equal(await description.inputValue(),'Guidance for internal proposal review.');await shot(`form-knowledge-save-error-${width}`)
  await kb.getByRole('button',{name:'Cancel',exact:true}).click();await page.getByRole('button',{name:'Edit',exact:true}).click();await page.getByRole('button',{name:'Add URLs',exact:true}).click()
  const urls=page.getByRole('dialog',{name:'Add URLs',exact:true}),input=urls.getByRole('textbox',{name:'URLs to add, one per line',exact:true})
  await input.fill('ftp://example.org/policy');await urls.getByRole('button',{name:'Add URLs',exact:true}).click();await associated(input,'Line 1');await shot(`form-url-validation-${width}`)
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push('Required/optional guidance and linked field errors are reviewed at three sizes. Empty folder names, duplicate Knowledge titles and invalid URL schemes focus the correct field. Synthetic save failures preserve valid drafts and do not mark them invalid.')
}finally{await review.flush();await review.browser.close()}
