import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { workflow, kb, validationResult } from './fixtures.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page}=review
page.setDefaultTimeout(30000)
await page.route('**/api/workflows/workflow-1',r=>r.fulfill({json:{...workflow,steps:[{id:'review',name:'Review evidence',data:{},is_output:true,tasks:[{id:'prompt',name:'Prompt',data:{prompt:'Summarize the proposal.'}}]}]}}))
await page.route('**/api/workflows/workflow-1/validation-plan',r=>r.fulfill({json:{checks:[],plan_stale:false}}))
await page.route('**/api/workflows/workflow-1/validation-plan/generate',r=>r.fulfill({json:{checks:[],plan_stale:false}}))
await page.route('**/api/workflows/workflow-1/quality-history*',r=>r.fulfill({json:{runs:[]}}))
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

const result={search_set_uuid:'item-1',num_runs:3,num_sources:1,aggregate_accuracy:1,aggregate_consistency:1,score:80,quality_tier:'good',executive_summary:{mean_accuracy:1,mean_consistency:1,perfect_fields_count:1,total_fields_count:1,run_to_run_std_dev:0,best_run:{source_index:0,run_index:0,correct:1},worst_run:{source_index:0,run_index:0,correct:1},per_run_reproducibility:[]},sources:[{source_label:'Proposal budget',source_type:'text',fields:[{field_name:'Budget',expected:'250',extracted_values:['250','250','250'],most_common_value:'250',distinct_value_count:1,consistency:1,accuracy:1,accuracy_method:'exact',enum_compliance:null,error_types:{}}],overall_accuracy:1,overall_consistency:1,per_run_correct:[1,1,1]}],challenging_fields:[],error_type_summary:{}}

result.aggregate_accuracy=0;result.executive_summary.mean_accuracy=0;result.executive_summary.perfect_fields_count=0;result.sources[0].fields[0].extracted_values=['200','200','200'];result.sources[0].fields[0].most_common_value='200';result.sources[0].fields[0].accuracy=0;result.sources[0].fields[0].error_types={wrong_value:3};result.challenging_fields=[{field_name:'Budget',source_label:'Proposal budget',accuracy:0,consistency:1,most_common_error:'wrong_value'}]
await page.route('**/api/extractions/validate-v2',r=>r.fulfill({json:result}))
await page.route('**/api/workflows/workflow-1/validation-inputs',r=>r.fulfill({json:{inputs:[]}}))
await page.route('**/api/workflows/workflow-1/validation-plan',r=>r.fulfill({json:{checks:[{check_id:'deadline',name:'Deadline matches the source',description:'Compare the saved sponsor deadline.',check_type:'semantic',step_index:0}],plan_stale:false}}))
await page.route('**/api/workflows/workflow-1/validate',r=>r.fulfill({json:{checks:[{check_id:'deadline',name:'Deadline matches the source',status:'FAIL',detail:'The result says October 30; the sponsor notice says October 15.'},{check_id:'budget',name:'Budget is supported',status:'SKIP',detail:'No expected budget was recorded.'}],grade:'D',summary:'The recorded deadline conflicts with the expected answer.',quality_score:40,step_breakdown:[],static_diagnostics:[]}}))
await page.route('**/api/workflows/workflow-1/improvement-suggestions',r=>r.fulfill({json:{suggestions:''}}))
const kbResult=structuredClone(validationResult);kbResult.retrieval_precision.details[0].judge.verdict='FAIL';kbResult.retrieval_precision.details[0].judge.score=0;kbResult.retrieval_precision.details[0].actual_answer='October 30';kbResult.retrieval_precision.details[0].judge.reasoning='The saved sponsor notice requires October 15.';kbResult.retrieval_precision.details[1].judge=null;kbResult.retrieval_precision.details[1].expected_answer=null
review.state.validationQueries=true
await page.route('**/api/knowledge/kb-1/validation-tasks/*',r=>r.fulfill({json:r.request().url().endsWith('/active')?{task:null}:{task_id:review.state.validationTaskId,status:'completed',run_uuid:'validation-1',result:kbResult}}))
async function shot(id,locator){if(locator)await locator.scrollIntoViewIfNeeded();await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id+': overflow');assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': accessibility');console.log('Captured '+id)}
try{
 for(const width of [320,1440]){
  await page.setViewportSize({width,height:width===320?740:1000});review.state.validated=false
  await page.goto(review.baseURL+'/?mode=knowledge');await page.getByRole('button',{name:kb.title,exact:true}).click();await page.getByRole('tab',{name:'Validation',exact:true}).click();await page.getByRole('tab',{name:'Check answer quality',exact:true}).click();await page.getByRole('button',{name:'Run 3 questions',exact:true}).click();const kbSummary=page.getByRole('region',{name:'Validation review summary'});await kbSummary.waitFor();assert.match(await kbSummary.innerText(),/1 failed, 0 need review, 1 ungraded/);await shot('validation-kb-summary-'+width,kbSummary);await page.getByRole('button',{name:/When is the proposal due/}).last().click();await page.getByText('October 30',{exact:true}).waitFor();await shot('validation-kb-failed-evidence-'+width,page.getByText('October 30',{exact:true}))
  await page.goto(review.baseURL+'/?mode=library&workflow=workflow-1&tab=validate');await page.getByRole('tab',{name:'Validate',exact:true}).click();await page.getByRole('button',{name:'Run Validation',exact:true}).click();const workflowSummary=page.getByRole('region',{name:'Workflow validation review summary'});await workflowSummary.waitFor();assert.match(await workflowSummary.innerText(),/1 failed, 0 need review, 1 skipped/);await shot('validation-workflow-summary-'+width,workflowSummary)
  await page.goto(review.baseURL+'/?mode=library&extraction=item-1&tab=validate');await page.getByRole('tab',{name:'Validate',exact:true}).click();await page.getByRole('button',{name:'Run detailed validation',exact:true}).click();const extractionSummary=page.getByRole('region',{name:'Extraction validation review summary'});await extractionSummary.waitFor();assert.match(await extractionSummary.innerText(),/1 test sources, 3 runs per source; 1 field\/source pairs/);await shot('validation-extraction-summary-'+width,extractionSummary)
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[]);review.observations.push('Synthetic result presentation for all three domains: failed/ungrounded KB answers, failed/skipped workflow checks, consistently wrong extraction. Recorded expected answers and next actions are visible; fixture scores are not accuracy evidence.')
}catch(error){await review.capture('validation-results-blocked',String(error));throw error}finally{await review.flush();await review.browser.close()}
