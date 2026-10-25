import assert from 'node:assert/strict'
import { createReview } from './harness.mjs'
import { workflow } from './fixtures.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page}=review;page.setDefaultTimeout(30000)
let failSave=true
const writes=[],tests=[]
const design={...workflow,steps:[{id:'step-1',name:'Review proposal',data:{},is_output:true,tasks:[{id:'document-task',name:'AddDocument',data:{}},{id:'sibling-task',name:'Prompt',data:{prompt:'Summarize the step input'}}]}]}
await page.route('**/api/documents/poll_status?*',r=>r.fulfill({json:{status:'SUCCESS',complete:true,valid:true,processing:false,title:'Proposal narrative.pdf'}}))
await page.route('**/api/workflows/workflow-1',r=>r.fulfill({json:design}))
await page.route('**/api/workflows/tasks/document-task',r=>{const data=r.request().postDataJSON();writes.push(data);if(failSave)return r.fulfill({status:503,json:{detail:'Task save unavailable'}});design.steps[0].tasks[0].data=data.data;return r.fulfill({json:design.steps[0].tasks[0]})})
await page.route('**/api/workflows/steps/test',r=>{tests.push(r.request().postDataJSON());return r.fulfill({json:{task_id:'pinned-test'}})})
await page.route('**/api/workflows/steps/test/pinned-test',r=>r.fulfill({json:{status:'completed',result:'The pinned document was read.'}}))
try{
 await page.goto(review.baseURL+'/?mode=library&workflow=workflow-1');await page.getByRole('button',{name:'Open step: Review proposal'}).click()
 const step=page.getByRole('region',{name:'Edit step: Review proposal',exact:true})
 await step.getByRole('button',{name:'Edit task: Add document',exact:true}).click()
 const task=page.getByRole('region',{name:'Edit task: Add document',exact:true})
 await task.getByRole('button',{name:'Choose document',exact:true}).click()
 const dialog=page.getByRole('dialog',{name:'Choose a document'});await dialog.getByRole('radio').first().check();await dialog.getByRole('button',{name:'Use document'}).click()
 await review.capture('task-document-selected');await task.getByRole('button',{name:'Save task'}).click();await page.getByText('Task save unavailable',{exact:true}).waitFor()
 assert.equal(await task.isVisible(),true);assert.match(await task.innerText(),/Pinned document: Proposal narrative.pdf/)
 await review.capture('pinned-document-save-error')
 failSave=false;await task.getByRole('button',{name:'Save task'}).click();await task.waitFor({state:'hidden'})
 assert.equal(writes.at(-1).data.override_step_input,true);assert.deepEqual(writes.at(-1).data.input_sources,['select_document']);assert.equal(writes.at(-1).data.selected_document_uuid,'doc-0')
 await step.getByRole('button',{name:'Edit task: Prompt',exact:true}).click();assert.match(await page.locator('.workflow-source-preview').innerText(),/Input\s+Step Input/);await page.keyboard.press('Escape')
 await step.getByRole('button',{name:'Edit task: Add document',exact:true}).click();await task.getByRole('button',{name:'Test Step',exact:true}).click();await page.getByText('The pinned document was read.',{exact:true}).waitFor()
 assert.equal(tests[0].task_data.selected_document_uuid,'doc-0');assert.deepEqual(tests[0].document_uuids,['doc-0']);await review.capture('pinned-document-test')
 await task.getByRole('button',{name:'Use step input',exact:true}).click();await task.getByRole('button',{name:'Save task'}).click();await task.waitFor({state:'hidden'})
 assert.equal(writes.at(-1).data.override_step_input,undefined);assert.deepEqual(writes.at(-1).data.input_sources,['step_input']);assert.equal(writes.at(-1).data.selected_document_uuid,'')
 await step.getByRole('button',{name:'Edit task: Add document',exact:true}).click();assert.match(await task.innerText(),/Using the step’s input: Step Input/);await review.capture('pinned-document-reset')
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push('Pinned document save failure retains selection; retry persists only this task. Sibling input stays unchanged. Test uses pinned document without global selection. Use step input clears the pin and survives reopen. Synthetic API responses; no document execution.')
}finally{await review.flush();await review.browser.close()}
