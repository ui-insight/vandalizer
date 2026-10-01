import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { workflow } from './fixtures.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page}=review
page.setDefaultTimeout(30000)
await page.route('**/api/workflows/workflow-1',r=>r.fulfill({json:{...workflow,steps:[{id:'review',name:'Review evidence',data:{},is_output:true,tasks:[{id:'prompt',name:'Prompt',data:{prompt:'Summarize the proposal.'}}]}]}}))
await page.route('**/api/workflows/workflow-1/validation-plan',r=>r.fulfill({json:{checks:[],plan_stale:false}}))
await page.route('**/api/workflows/workflow-1/validation-plan/generate',r=>r.fulfill({json:{checks:[],plan_stale:false}}))
await page.route('**/api/workflows/workflow-1/quality-history*',r=>r.fulfill({json:{history:[]}}))
await page.route('**/api/extractions/search-sets/item-1/quality-status*',r=>r.fulfill({json:{status:'unvalidated'}}))
await page.route('**/api/extractions/search-sets/item-1/quality-history*',r=>r.fulfill({json:{runs:[]}}))
await page.route('**/api/extractions/search-sets/item-1/cross-field-rules',r=>r.fulfill({json:{rules:[]}}))
await page.route('**/api/workflows/workflow-1/validation-inputs',r=>r.fulfill({json:{inputs:[{id:'input-1',type:'text',text:'Budget: 200',label:'Proposal example'}]}}))
await page.route('**/api/workflows/workflow-1/expected-outputs',r=>r.fulfill({json:{expected_outputs:[{id:'expected-1',type:'expected_output',label:'Proposal summary with budget',output_text:'The budget is 200.',source:'manual'}]}}))
await page.route('**/api/extractions/test-cases?*',r=>r.fulfill({json:[{uuid:'test-1',search_set_uuid:'item-1',label:'Proposal example with budget',source_type:'text',source_text:'Budget: 200',expected_values:{Budget:'200'},user_id:'reviewer',created_at:'2026-09-24T00:00:00Z'}]}))
await page.route('**/api/extractions/search-sets/item-1',r=>r.fulfill({json:{id:'item-1',uuid:'item-1',title:'Budget compliance extraction',set_type:'extraction',user_id:'reviewer',extraction_config:{},created_at:'',updated_at:''}}))
await page.route('**/api/extractions/search-sets/item-1/items',r=>r.fulfill({json:[{id:'field-1',uuid:'field-1',search_set_uuid:'item-1',searchphrase:'Budget',title:'Budget',searchtype:'text',enum_values:[],is_optional:false,description:'The total budget'}]}))
await page.route('**/api/extractions/search-sets/item-1/history*',r=>r.fulfill({json:{runs:[]}}))
await page.route('**/api/extractions/search-sets/item-1/quality-sparkline*',r=>r.fulfill({json:{scores:[]}}))
await page.route('**/api/extractions/search-sets/item-1/baseline-probe',r=>r.fulfill({json:{no_settings_score:0.5,num_cases_judged:1,sample_case_ids:['test-1'],tokens_used:200,duration_ms:30}}))
await page.route('**/api/extractions/search-sets/item-1/optimize?*',r=>r.fulfill({json:{items:new URL(r.request().url()).searchParams.get('limit')==='1'?[]:[{uuid:'previous-1',status:'completed',started_at:'2026-09-29T10:00:00Z',num_trials:8,optimized_score:0.84,baseline_default_score:0.52,judge_model:'Review model',options:{}}],count:1,skip:0,limit:20}}))

let failLoad = true, failSave = true, failRun = true, saves = [], runs = []
const testcase = {uuid:'test-1', search_set_uuid:'item-1', label:'Proposal budget', source_type:'text', source_text:'Budget: 200', expected_values:{Budget:'200'}}
await page.route('**/api/extractions/test-cases?*', route => failLoad ? route.fulfill({status:503,json:{detail:'Test cases temporarily unavailable'}}) : route.fulfill({json:[testcase]}))
await page.route('**/api/extractions/test-cases/test-1', route => {
 if(route.request().method()==='DELETE') return route.fulfill({status:503,json:{detail:'Cannot remove this case right now'}})
 const data=route.request().postDataJSON();saves.push(data)
 return failSave ? route.fulfill({status:503,json:{detail:'Save temporarily unavailable'}}) : route.fulfill({json:{...testcase,...data}})
})
const result={search_set_uuid:'item-1',num_runs:3,num_sources:1,aggregate_accuracy:1,aggregate_consistency:1,score:80,quality_tier:'good',executive_summary:{mean_accuracy:1,mean_consistency:1,perfect_fields_count:1,total_fields_count:1,run_to_run_std_dev:0,best_run:{source_index:0,run_index:0,correct:1},worst_run:{source_index:0,run_index:0,correct:1},per_run_reproducibility:[]},sources:[{source_label:'Proposal budget',source_type:'text',fields:[{field_name:'Budget',expected:'250',extracted_values:['250','250','250'],most_common_value:'250',distinct_value_count:1,consistency:1,accuracy:1,accuracy_method:'exact',enum_compliance:null,error_types:{}}],overall_accuracy:1,overall_consistency:1,per_run_correct:[1,1,1]}],challenging_fields:[],error_type_summary:{}}
await page.route('**/api/extractions/validate-v2', route => {runs.push(route.request().postDataJSON()); return failRun ? route.fulfill({status:503,json:{detail:'Validation service unavailable'}}) : route.fulfill({json:result})})
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id+': overflow');assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': accessibility');console.log('Captured '+id)}
try {
 for(const width of [320,1440]) {
  failLoad=true;failSave=true;failRun=true;saves=[];runs=[]
  await page.setViewportSize({width,height:width===320?700:900})
  await page.goto(review.baseURL+'/?mode=files&tab=library&extraction=item-1')
  await page.getByRole('tab',{name:'Validate',exact:true}).click()
  await page.getByRole('button',{name:'Retry loading test cases'}).waitFor()
  assert.equal(await page.getByRole('button',{name:'Run detailed validation'}).isDisabled(),true)
  failLoad=false;await page.getByRole('button',{name:'Retry loading test cases'}).click()
  await page.getByRole('button',{name:'Expected values for Proposal budget'}).click()
  const expected=page.getByRole('textbox',{name:'Expected value for Budget',exact:true})
  await expected.fill('250')
  await page.getByRole('button',{name:'Retry saving test cases'}).waitFor()
  assert.equal(await expected.inputValue(),'250')
  await expected.scrollIntoViewIfNeeded();await shot('extraction-unsaved-'+width)
  failSave=false;await page.getByRole('button',{name:'Retry saving test cases'}).click()
  await page.getByRole('button',{name:'Retry saving test cases'}).waitFor({state:'hidden'})
  assert.deepEqual(saves.at(-1),{expected_values:{Budget:'250'}})
  await page.getByRole('button',{name:'Run detailed validation'}).click()
  await page.getByRole('button',{name:'Retry validation'}).waitFor()
  assert.equal(await expected.inputValue(),'250')
  failRun=false;await page.getByRole('button',{name:'Retry validation'}).click()
  await page.getByRole('button',{name:'Retry validation'}).waitFor({state:'hidden'})
  assert.equal(runs.length,2);assert.equal(runs[1].sources[0].expected_values.Budget,'250')
  await page.getByText('Detailed breakdown',{exact:true}).scrollIntoViewIfNeeded();await shot('extraction-check-results-'+width)
  await page.getByRole('button',{name:'Remove Proposal budget'}).click()
  await page.getByText('Cannot remove this case right now',{exact:true}).waitFor()
  assert.equal(await expected.inputValue(),'250')
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push('Synthetic extraction test-case load/save/run/delete failure recovery; expected values survive retries and the outgoing validation request contains the edited value. Fixture scores are not execution or correctness evidence.')
} catch(error) {await review.capture('extraction-recovery-blocked',String(error));throw error}
finally {await review.flush();await review.browser.close()}
