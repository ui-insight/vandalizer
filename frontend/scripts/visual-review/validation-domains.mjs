import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { workflow } from './fixtures.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page}=review
page.setDefaultTimeout(15000)
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
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id+': overflow');assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': accessibility');console.log('Captured '+id)}
try{
 for(const [width,height]of[[320,568],[768,600],[1440,900]]){
  await page.setViewportSize({width,height})
  for(const domain of ['workflow','extraction']){
   await page.goto(review.baseURL+`/?mode=files&tab=library&${domain}=${domain==='workflow'?'workflow-1':'item-1'}`)
   await page.getByRole('tab',{name:'Validate',exact:true}).click()
   const trigger=page.getByRole('button',{name:'Validate & improve',exact:true})
   await trigger.waitFor();await shot(`theme-${domain}-validation-${width}`);
   if(domain==='extraction'){await page.getByRole('button',{name:'Previous runs',exact:true}).click();await page.getByText('judge: Review model',{exact:true}).waitFor();await shot(`theme-extraction-history-${width}`)}
   await trigger.click()
   const dialog=page.getByRole('dialog',{name:domain==='workflow'?'Validate & improve this workflow':'Tune this extraction',exact:true})
   await dialog.waitFor()
   assert.equal(await dialog.evaluate(e=>{const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width*0.72,r.y+r.height/2))}),true,'Dialog must cover the workspace divider')
   const steps=domain==='workflow'?['concept','test-cases','budget','advanced']:['concept','test-cases','baseline','budget','advanced']
   for(let i=0;i<steps.length;i++){
    if(i>0)await dialog.getByRole('button',{name:'Next',exact:true}).click()
    if(steps[i]==='baseline')await dialog.getByRole('button',{name:'Next',exact:true}).waitFor({state:'visible'})
    await shot(`theme-${domain}-${steps[i]}-${width}`)
    if(domain==='extraction'&&steps[i]==='test-cases'){
     const generate=dialog.getByRole('button',{name:'+ Generate more from documents',exact:true});await generate.click()
     const nested=page.getByRole('dialog',{name:'Generate test cases',exact:true});await nested.waitFor()
     await shot(`theme-extraction-generation-${width}`)
     await page.keyboard.press('Escape');await nested.waitFor({state:'hidden'});assert.equal(await dialog.isVisible(),true)
     assert.equal(await generate.evaluate(e=>e===document.activeElement),true)
    }
   }
   await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'})
  }
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push('Workflow and extraction validation setup and every wizard step use synthetic test data and baseline scores. No optimization start or execution is performed.')
}catch(error){await page.screenshot({path:resolve(review.out,'validation-domains-blocked.png')});throw error}
finally{await review.flush();await review.browser.close()}
