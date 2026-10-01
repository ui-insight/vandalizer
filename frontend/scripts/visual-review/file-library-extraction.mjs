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

let failRun=false,runs=[]
await page.route('**/api/library/items/*/touch',route=>route.fulfill({json:{ok:true}}))
await page.route('**/api/files/download?*',route=>route.fulfill({contentType:'text/plain',body:'Proposal budget: 250.50'}))
await page.route('**/api/extractions/run-sync',route=>{runs.push(route.request().postDataJSON());return failRun?route.fulfill({status:503,json:{detail:'Extraction worker unavailable'}}):route.fulfill({json:{results:[{Budget:'250.50'}],sources:[{}]}})})
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id+': overflow');assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': accessibility');console.log('Captured '+id)}
try{
 for(const [width,height]of[[1440,900],[1024,768],[768,700],[390,844],[320,700]]){
  await page.setViewportSize({width,height})
  for(const selected of [false,true]){
   runs=[];failRun=false
   await page.goto(review.baseURL+'/?mode=files')
   const file=page.getByRole('row',{name:'Document: Proposal narrative.pdf',exact:true})
   if(selected)await file.getByRole('checkbox').check();else {await file.click();await page.getByText('Synthetic review document.',{exact:false}).waitFor()}
   await page.getByRole('button',{name:/^(?:Open )?Library(?: panel)?$/}).click()
   await page.getByRole('button',{name:'Open Budget compliance extraction',exact:true}).click()
   const run=page.getByRole('button',{name:'RUN',exact:true});await run.waitFor();assert.equal(await run.isEnabled(),true)
   const prefix=`extraction-file-${selected?'selected':'opened'}-${width}`
   failRun=true;await run.click();await page.getByRole('alert').filter({hasText:'Extraction worker unavailable'}).waitFor()
   assert.deepEqual(runs[0].document_uuids,['doc-0']);await shot(prefix+'-failed')
   failRun=false;await run.click();await page.getByText('250.50',{exact:true}).first().waitFor()
   assert.deepEqual(runs.map(r=>r.document_uuids),[['doc-0'],['doc-0']])
   await page.getByText('250.50',{exact:true}).first().scrollIntoViewIfNeeded();await shot(prefix+'-result')
   await page.getByRole('button',{name:'Close extraction',exact:true}).click()
   await page.getByRole('button',{name:'Open Budget compliance extraction',exact:true}).waitFor()
   if(width<768)await page.getByRole('button',{name:'Files panel',exact:true}).click()
   if(selected)assert.equal(await file.getByRole('checkbox').isChecked(),true);else await page.getByText('Synthetic review document.',{exact:false}).waitFor()
   await shot(prefix+'-return')
  }
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push('Opened and checkbox-selected document → Library → extraction → failed run → retry → displayed value → return at five widths. Outgoing document IDs verified. Synthetic values; no real extraction accuracy claim.')
}catch(error){await review.capture('extraction-file-blocked',String(error));throw error}
finally{await review.flush();await review.browser.close()}
