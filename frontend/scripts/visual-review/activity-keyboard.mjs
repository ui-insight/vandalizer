import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page}=review
page.setDefaultTimeout(30000)
const timestamp=new Date().toISOString()
const base={type:'workflow_run',status:'failed',title:'Review proposal exceptions',conversation_id:null,search_set_uuid:null,workflow_id:'workflow-1',workflow_session_id:'activity-session',started_at:timestamp,finished_at:timestamp,last_updated_at:timestamp,error:'The worker could not finish this review.',tokens_input:0,tokens_output:0,message_count:0,result_snapshot:{},meta_summary:{description_generated:true}}
let failLoad=true, failDelete=false, deleted=[], executions=0
const events=[{...base,id:'conversation',type:'conversation',status:'completed',title:'Discuss sponsor conditions',conversation_id:'saved-chat',workflow_id:null}, { ...base,id:'extraction',type:'search_set_run',status:'completed',title:'Extract budget evidence',workflow_id:null,search_set_uuid:'activity-extraction',result_snapshot:{normalized:{Budget:'$125,000'},document_warnings:[{document_uuid:'doc-0',title:'Proposal narrative.pdf',codes:['partial_ocr'],text:'Only the first 30 pages could be read.'}],cross_field:{results:[{rule_id:'budget',status:'fail',passed:false,message:'Budget exceeds the approved cap.'}],summary:{pass:0,fail:1,unparseable:0,total:1,pass_rate:0,violation_rate:1}}}},{...base,id:'failed'}, {...base,id:'cancelled',status:'canceled',title:'Cancelled budget check',meta_summary:{pending_review_uuid:'old-review'}},{...base,id:'approval',status:'running',title:'Review waiting for a person',meta_summary:{pending_review_uuid:'review-1'}},{...base,id:'stale',status:'running',title:'Unresponsive worker',last_updated_at:'2026-01-01T00:00:00Z'},...Array.from({length:36},(_,i)=>({...base,id:'history-'+i,status:'completed',title:'Institutional research proposal supporting document review '+(i+1)}))]
await page.route('**/api/activity/streams/**',route=>failLoad?route.fulfill({status:503,json:{detail:'Activity unavailable'}}):route.fulfill({json:{events:events.filter(e=>!deleted.includes(e.id)),stale_threshold_minutes:30}}))
await page.route('**/api/activity/failed',route=>{assert.equal(route.request().method(),'DELETE');if(failDelete)return route.fulfill({status:503,json:{detail:'Activity deletion temporarily unavailable'}});deleted.push('failed');return route.fulfill({json:{status:'ok',message:'Deleted'}})})
const status={status:'failed',error:'The worker could not finish this review.',num_steps_completed:0,num_steps_total:1,final_output:null,steps_output:{},output_step_names:[],approval_request_id:null}
await page.route('**/api/workflows/status?*',route=>route.fulfill({json:status}))
await page.route('**/api/workflows/status/stream?*',route=>route.fulfill({contentType:'text/event-stream',body:`data: ${JSON.stringify(status)}\n\n`}))
await page.route('**/api/workflows/*/run',route=>{executions++;return route.fulfill({status:503,json:{detail:'Should not execute when opening activity'}})})
await page.route('**/api/chat/history/saved-chat',r=>r.fulfill({json:{activity_id:'conversation',messages:[{role:'user',content:'Which sponsor conditions need review?'},{role:'assistant',content:'Confirm the budget cap against the award letter.'}],url_attachments:[],file_attachments:[]}}))
await page.route('**/api/extractions/search-sets/activity-extraction',r=>r.fulfill({json:{id:'activity-extraction',uuid:'activity-extraction',title:'Budget compliance extraction',set_type:'extraction',user_id:'reviewer',extraction_config:{},created_at:'',updated_at:''}}))
await page.route('**/api/extractions/search-sets/activity-extraction/items',r=>r.fulfill({json:[{id:'field-1',uuid:'field-1',search_set_uuid:'activity-extraction',searchphrase:'Budget',title:'Budget',searchtype:'text',enum_values:[],is_optional:false}]}))
await page.route('**/api/extractions/search-sets/activity-extraction/quality-status*',r=>r.fulfill({json:{status:'unvalidated'}}))
await page.route('**/api/extractions/search-sets/activity-extraction/history*',r=>r.fulfill({json:{runs:[]}}))
await page.route('**/api/extractions/search-sets/activity-extraction/quality-sparkline*',r=>r.fulfill({json:{scores:[]}}))
await page.route('**/api/extractions/run-sync',r=>{executions++;return r.fulfill({status:503,json:{detail:'Opening a saved extraction must not run it'}})})
await page.route('**/api/reviews/review-1',r=>r.fulfill({json:{uuid:'review-1',workflow_id:'workflow-1',workflow_name:'Proposal readiness review',step_name:'Approve readiness handoff',status:'pending',assigned_to_user_ids:['reviewer'],assignee_role:'specific_users',requester_user_id:'reviewer',team_id:'team-1',expires_at:null,created_at:timestamp,decision_at:null,escalated_at:null,step_index:1,review_instructions:'Confirm the deadline against the original before approving.',artifact_kind:'markdown',data_for_review:{value:'Sponsor deadline: October 15. Budget justification needs PI review.'},edited_artifact:null,timeout_action:'none',escalation_user_ids:[],reviewer_user_id:null,reviewer_comments:'',expired_at:null,source_docs:[],requester:null}}))
await page.route('**/api/extractions/search-sets/activity-extraction/cross-field-rules',r=>r.fulfill({json:{rules:[]}}))
await page.route('**/api/extractions/search-sets/activity-extraction/quality-history*',r=>r.fulfill({json:{runs:[]}}))
await page.route('**/api/extractions/test-cases?*',r=>r.fulfill({json:[]}))
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id+': overflow');assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': accessibility');console.log('Captured '+id)}
try {
 for(const width of [320,1440]) {
  deleted=[];failLoad=true
  await page.setViewportSize({width,height:width===320?700:900});await page.goto(review.baseURL+'/?mode=files')
  const expand=page.getByRole('button',{name:width===320?'Open activity':'Expand activity',exact:true})
  await expand.click()
  const rail=page.getByRole('complementary',{name:'Activity',exact:true})
  await rail.getByRole('button',{name:'Retry activity',exact:true}).waitFor()
  failLoad=false;await rail.getByRole('button',{name:'Retry activity',exact:true}).click()
  const failed=rail.getByRole('button',{name:'Open Review proposal exceptions: Failed',exact:true})
  await failed.waitFor()
  assert.equal(await rail.getByRole('button',{name:'Open Cancelled budget check: Cancelled',exact:true}).count(),1)
  assert.equal(await rail.getByRole('button',{name:'Open Review waiting for a person: Awaiting approval',exact:true}).count(),1)
  assert.equal(await rail.getByRole('button',{name:'Open Unresponsive worker: Timed out',exact:true}).count(),1)
  await shot('activity-dense-'+width)
  await rail.getByRole('button',{name:'Open Discuss sponsor conditions: Completed',exact:true}).click();await page.getByText('Confirm the budget cap against the award letter.',{exact:true}).waitFor();const draft=page.getByRole('textbox',{name:'Message input',exact:true});await draft.fill('Keep this follow-up while I inspect a run.');await shot('activity-conversation-'+width);if(width===320)await expand.click()
  await rail.getByRole('button',{name:'Open Extract budget evidence: Completed',exact:true}).click();await page.getByText('$125,000',{exact:true}).waitFor();await page.getByText('Budget exceeds the approved cap.',{exact:false}).waitFor();await page.getByText('Only the first 30 pages could be read.',{exact:false}).waitFor();await shot('activity-extraction-restored-'+width);await page.getByRole('button',{name:'Close extraction',exact:true}).click();if(width===320)await expand.click()
  await failed.focus();await page.keyboard.press('Enter')
  const close=page.getByRole('button',{name:'Close workflow',exact:true});await close.waitFor();await close.click()
  if(width===320)await expand.click()
  await failed.waitFor()
  await page.waitForFunction(()=>document.activeElement?.getAttribute('aria-label')==='Open Review proposal exceptions: Failed')
  await failed.focus();await page.keyboard.press('Space');await close.waitFor();await close.click();if(width===320)await expand.click()
  const remove=rail.getByRole('button',{name:'Delete activity: Review proposal exceptions',exact:true})
  await remove.focus();await page.keyboard.press('Enter')
  const confirm=page.getByRole('dialog',{name:'Delete from activity?',exact:true});await confirm.getByRole('button',{name:'Cancel',exact:true}).click()
  assert.equal(deleted.length,0)
  failDelete=true;await remove.click();await confirm.getByRole('button',{name:'Delete',exact:true}).click();await page.getByText('Activity deletion temporarily unavailable',{exact:true}).waitFor();await failed.waitFor();assert.equal(deleted.length,0);await shot('activity-delete-error-'+width);await page.getByRole('button',{name:'Dismiss error',exact:true}).click();failDelete=false;await remove.click();await confirm.getByRole('button',{name:'Delete',exact:true}).click();await failed.waitFor({state:'hidden'})
  assert.equal(executions,0)
  await shot('activity-after-delete-'+width)
  if(width===320)await page.getByRole('dialog',{name:'Activity',exact:true}).getByRole('button',{name:'Close activity',exact:true}).click();await page.getByRole('button',{name:/^(?:Open )?Assistant(?: panel)?$/}).click();assert.equal(await draft.inputValue(),'Keep this follow-up while I inspect a run.');await page.getByText('Confirm the budget cap against the award letter.',{exact:true}).waitFor();if(width===320)await expand.click();await rail.getByRole('button',{name:'Open Review waiting for a person: Awaiting approval',exact:true}).click();await page.waitForURL('**/reviews/review-1');await page.getByRole('button',{name:'Approve',exact:true}).waitFor();await shot('activity-pending-review-'+width);assert.equal(executions,0)
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push('Forty-two mixed conversation, extraction and workflow records: load failure/retry, failure/cancellation/pending/stale labels, Enter/Space opening without rerun, separate cancel/confirm deletion, drawer focus return at 320px. Synthetic API; no live task execution.')
} catch(error){await review.capture('activity-keyboard-blocked',String(error));throw error}
finally {await review.flush();await review.browser.close()}
