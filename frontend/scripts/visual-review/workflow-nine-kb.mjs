import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL});const {page,state}=review;page.setDefaultTimeout(30000);state.validationQueries=true
await page.route('**/api/knowledge/kb-1/optimize/models',r=>r.fulfill({json:{judge_model:'Review model',judge_source:'validation_grader',judge_model_fallback:null,validation_grader:'Review model',current_model:'Review model',challenger_models:['Alternative model'],current_shares_judge_family:true,models:[{name:'Review model',family:'review',is_current:true,eligible:false,ineligible_reason:'Same family as the judge'},{name:'Alternative model',family:'alternative',is_current:false,eligible:true,ineligible_reason:null}]}}))
async function shot(id){await review.capture(id);assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[]);console.log(id)}
try{
 for(const width of [390,1440]){
  await page.setViewportSize({width,height:width===390?844:1000});await page.goto(review.baseURL+'/?mode=knowledge');await page.getByRole('button',{name:'Edit',exact:true}).click();await page.getByRole('tab',{name:'Validation',exact:true}).click();await shot('kb-examples-'+width)
  await page.getByRole('button',{name:'Run & results',exact:true}).click();await shot('kb-run-'+width)
  await page.getByRole('button',{name:'Improve',exact:true}).click();await shot('kb-improve-'+width)
  await page.getByRole('button',{name:'Validate & improve',exact:true}).click();const dialog=page.getByRole('dialog');await shot('kb-wizard-questions-'+width)
  for(const id of ['preview','baseline','budget']){await dialog.getByRole('button',{name:'Next',exact:false}).click();await shot('kb-wizard-'+id+'-'+width)}
  await dialog.getByRole('button',{name:/Advanced: choose the judge and challengers/}).click();await shot('kb-wizard-model-options-'+width)
  await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'})
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[]);review.observations.push('Knowledge-base examples, run setup, optional tuning wizard, budget and advanced judge/challenger selection at desktop and mobile widths. No optimization launched.')
}finally{await review.flush();await review.browser.close()}
