import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { workflow } from './fixtures.mjs'
const review = await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page,state}=review
state.validationQueries=true
page.setDefaultTimeout(15000)
let fail=true, inputs=[], checks=[], saves=[], evaluations=0, preparations=0
await page.route('**/api/workflows/workflow-1',r=>r.fulfill({json:{...workflow,steps:[{id:'review',name:'Review evidence',data:{},is_output:true,tasks:[{id:'prompt',name:'Prompt',data:{prompt:'Summarize the proposal.'}}]}]}}))
await page.route('**/api/workflows/workflow-1/validation-plan',r=>{
 if(r.request().method()==='PUT'){saves.push(r.request().postDataJSON());if(fail)return r.fulfill({status:503,json:{detail:'Save temporarily unavailable'}});checks=r.request().postDataJSON().checks}
 return r.fulfill({json:{checks,plan_stale:false}})
})
await page.route('**/api/workflows/workflow-1/validation-inputs',r=>{
 if(r.request().method()==='PUT'){saves.push(r.request().postDataJSON());if(fail)return r.fulfill({status:503,json:{detail:'Save temporarily unavailable'}});inputs=r.request().postDataJSON().inputs}
 return r.fulfill({json:{inputs}})
})
await page.route('**/api/workflows/workflow-1/quality-history*',r=>r.fulfill({json:{runs:[]}}))
await page.route('**/api/workflows/workflow-1/expected-outputs',r=>r.fulfill({json:{expected_outputs:[]}}))
await page.route('**/api/workflows/workflow-1/validate',r=>{evaluations++;assert.equal(checks[0].name,'Check the full budget');return r.fulfill({json:{grade:'A',summary:'All example checks passed',checks:[{id:'budget',name:checks[0].name,status:'PASS',reason:'Matches the expected budget',score:1}]}})})
await page.route('**/api/workflows/workflow-1/create-temp-documents',r=>{preparations++;assert.equal(inputs[0].text,'Budget: 250');assert.equal(r.request().postDataJSON().texts[0].text,'Budget: 250');return r.fulfill({status:503,json:{detail:'Synthetic execution boundary: no model run'}})})
let failQuestion=true, questionWrites=[]
await page.route('**/api/knowledge/kb-1/test-queries/*',r=>{questionWrites.push(r.request().postDataJSON());return r.fulfill(failQuestion?{status:503,json:{detail:'Question save unavailable'}}:{json:{uuid:'q1',...r.request().postDataJSON()}})})
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[]);console.log(id)}
async function openWorkflow(){await page.goto(review.baseURL+'/?mode=files&tab=library&workflow=workflow-1');await page.getByRole('tab',{name:'Validate',exact:true}).click();await page.getByRole('button',{name:'Edit check',exact:true}).waitFor()}
try{
 for(const width of [320,1440]){
  await page.setViewportSize({width,height:width===320?740:1000});fail=true;inputs=[];checks=[{id:'budget',name:'Check budget',description:'Budget matches the example',category:'accuracy',source:'manual'}];saves=[];evaluations=0;preparations=0
  await openWorkflow();await page.getByRole('button',{name:'Edit check',exact:true}).click();await page.getByRole('textbox',{name:'Check name',exact:true}).fill('Check the full budget')
  await page.getByRole('button',{name:'Run & results',exact:true}).click();assert.equal(await page.getByRole('textbox',{name:'Check name',exact:true}).inputValue(),'Check the full budget')
  await page.getByRole('button',{name:'Save',exact:true}).click();await page.getByRole('button',{name:'Run & results',exact:true}).click();await page.getByRole('button',{name:'Check latest run',exact:true}).click()
  await page.getByRole('button',{name:'Retry saving validation changes',exact:true}).waitFor();assert.equal(evaluations,0)
  await shot('workflow-save-failed-'+width)
  await page.getByRole('button',{name:'Improve',exact:true}).click();assert.equal(await page.getByRole('button',{name:'Check latest run',exact:true}).isVisible(),true)
  fail=false;await page.getByRole('button',{name:'Retry saving validation changes',exact:true}).click();await page.getByRole('button',{name:'Retry saving validation changes',exact:true}).waitFor({state:'hidden'})
  await page.getByRole('button',{name:'Check latest run',exact:true}).click();await page.getByRole('region',{name:'Workflow validation review summary'}).waitFor();assert.equal(evaluations,1);assert.equal(checks[0].name,'Check the full budget');await shot('workflow-saved-check-'+width)
  inputs=[{id:'input-1',type:'text',text:'Budget: 200',label:'Proposal budget'}];await openWorkflow();await page.getByRole('textbox',{name:'Test content',exact:true}).fill('Budget: 250');await page.getByRole('button',{name:'Run & results',exact:true}).click();await page.getByRole('button',{name:'Run check',exact:true}).click();await page.getByText('Synthetic execution boundary: no model run',{exact:true}).waitFor();assert.equal(preparations,1);assert.equal(inputs[0].text,'Budget: 250')
  await page.goto(review.baseURL+'/?mode=knowledge');await page.getByRole('button',{name:'Edit',exact:true}).click();await page.getByRole('tab',{name:'Validation',exact:true}).click();await page.getByRole('button',{name:'Edit test query',exact:true}).first().click();await page.getByRole('textbox',{name:'Expected answer',exact:true}).fill('October 15, by 5 PM')
  await page.getByRole('button',{name:'Run & results',exact:true}).click();await page.getByText('Save or cancel your question edits before leaving Examples. Your draft is still here.',{exact:true}).waitFor();assert.equal(await page.getByRole('textbox',{name:'Expected answer',exact:true}).inputValue(),'October 15, by 5 PM');await shot('kb-preserved-question-'+width)
  failQuestion=true;await page.getByRole('button',{name:'Save',exact:true}).click();await page.getByText(/Could not save this question:/).waitFor();await page.getByRole('button',{name:'Improve',exact:true}).click();assert.equal(await page.getByRole('textbox',{name:'Expected answer',exact:true}).inputValue(),'October 15, by 5 PM')
  failQuestion=false;await page.getByRole('button',{name:'Save',exact:true}).click();await page.getByRole('textbox',{name:'Expected answer',exact:true}).waitFor({state:'hidden'});assert.equal(questionWrites.at(-1).expected_answer,'October 15, by 5 PM');await page.getByRole('button',{name:'Run & results',exact:true}).click();await page.getByRole('button',{name:'Run 3 questions',exact:true}).waitFor()
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push('Verified workflow draft-save failure blocks both evaluation and tuning; retry retains edits; immediate Run waits for updated text persistence. KB stage changes preserve open edits and failed saves. Synthetic API responses; execution deliberately stops before model calls.')
}catch(error){await review.capture('handoff-blocked',String(error));throw error}finally{await review.flush();await review.browser.close()}
