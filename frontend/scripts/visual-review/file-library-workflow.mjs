import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { workflow } from './fixtures.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page}=review
page.setDefaultTimeout(15000)
const runnable={...workflow,input_config:{trigger_type:'document'},steps:[{id:'step-review',name:'Review evidence',data:{},is_output:true,tasks:[{id:'task-review',name:'Prompt',data:{prompt:'Summarize this document.'}}]}]}
let runs=[],failRun=false
const status={status:'completed',num_steps_completed:1,num_steps_total:1,current_step_name:null,current_step_detail:null,current_step_preview:null,final_output:'Review complete for the selected document.',steps_output:{'Review evidence':'Review complete for the selected document.'},output_step_names:['Review evidence'],approval_request_id:null}
await page.route('**/api/files/download?*',route=>route.fulfill({contentType:'text/plain',body:'Proposal due October 15. Budget requires justification.'}))
await page.route('**/api/workflows/workflow-1',route=>route.fulfill({json:runnable}))
await page.route('**/api/library/items/*/touch',route=>route.fulfill({json:{ok:true}}))
await page.route('**/api/workflows/workflow-1/run',route=>{runs.push(route.request().postDataJSON());return failRun?route.fulfill({status:503,json:{detail:'Workflow queue unavailable'}}):route.fulfill({json:{session_id:'navigation-review-run'}})})
await page.route('**/api/workflows/status?*',route=>route.fulfill({json:status}))
await page.route('**/api/workflows/status/stream?*',route=>route.fulfill({contentType:'text/event-stream',body:`data: ${JSON.stringify(status)}\n\n`}))
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${id}: overflow`);assert.deepEqual(JSON.parse(await readFile(resolve(review.out,`${id}.axe.json`),'utf8')),[],`${id}: accessibility`);console.log(`Captured ${id}`)}
try{
 for(const [width,height]of[[1440,900],[1024,768],[768,700],[390,844],[320,568]]){
  runs=[];failRun=false;await page.setViewportSize({width,height});await page.goto(review.baseURL+'/?mode=files')
  const file=page.getByRole('row',{name:'Document: Proposal narrative.pdf',exact:true});await file.click()
  await page.getByText('Synthetic review document.',{exact:false}).waitFor();await shot(`file-library-open-file-${width}`)
  if(width<768)await page.getByRole('button',{name:'Open Library panel',exact:true}).click()
  else{assert.equal(await page.getByRole('button',{name:/^(?:Open )?Library(?: panel)?$/}).isVisible(),true);await page.getByRole('button',{name:/^(?:Open )?Library(?: panel)?$/}).click()}
  const item=page.getByRole('button',{name:'Open Proposal readiness review',exact:true});await item.waitFor()
  if(width>=768)assert.equal(await page.getByRole('button',{name:'Close document',exact:true}).isVisible(),true)
  await shot(`file-library-browse-${width}`);await item.click()
  const run=page.getByRole('button',{name:'RUN',exact:true});await run.waitFor();assert.equal(await run.isEnabled(),true)
  if(width>=768)assert.equal(await page.getByRole('button',{name:'Close document',exact:true}).isVisible(),true)
  else{
   await page.getByRole('button',{name:'Files panel',exact:true}).click();await page.getByText('Synthetic review document.',{exact:false}).waitFor()
   await page.getByRole('button',{name:'Open tool panel',exact:true}).click();assert.equal(await run.isEnabled(),true)
  }
  await shot(`file-library-tool-${width}`)
  failRun=true;await run.click();await page.getByText('Workflow queue unavailable',{exact:true}).waitFor();assert.deepEqual(runs[0].document_uuids,['doc-0']);await shot(`file-library-run-error-${width}`)
  await page.getByRole('button',{name:'Dismiss error',exact:true}).click();failRun=false;await run.click();await page.getByText('Review complete for the selected document.',{exact:false}).first().waitFor();assert.deepEqual(runs.map(r=>r.document_uuids),[['doc-0'],['doc-0']]);await page.getByText('Review complete for the selected document.',{exact:false}).first().scrollIntoViewIfNeeded();await shot(`file-library-run-complete-${width}`)
  await page.getByRole('button',{name:'Close workflow',exact:true}).click();await page.getByRole('button',{name:'Open Proposal readiness review',exact:true}).waitFor()
  if(width<768)await page.getByRole('button',{name:'Files panel',exact:true}).click()
  await page.getByText('Synthetic review document.',{exact:false}).waitFor();await shot(`file-library-return-${width}`)
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
}catch(error){await review.capture('file-library-blocked',String(error));throw error}
finally{await review.flush();await review.browser.close()}
