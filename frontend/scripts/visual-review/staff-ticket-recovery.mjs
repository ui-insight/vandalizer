import assert from 'node:assert/strict'
import { expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page}=review
page.setDefaultTimeout(30000)
const stamp='2026-09-30T10:00:00Z',subject='Unable to inspect a budget justification after returning to the shared research project'
const message={uuid:'message-1',user_id:'author',user_name:'Jordan Lee',content:'Please inspect the budget processing state. The source document and its table need to remain available during review.',is_support_reply:false,is_internal_note:false,created_at:stamp,edited_at:null}
const base={uuid:'staff-1',ticket_number:1024,subject,status:'open',priority:'high',classification:'bug',user_id:'author',user_name:'Jordan Lee — Research Administration and Sponsored Programs',user_email:'jordan.lee@institution.example.test',team_id:'team-1',assigned_to:null,category:null,tags:['documents'],watchers:[],watcher_ids:[],read_by:[],message_count:40,last_message_preview:message.content,last_message_at:stamp,last_message_user_id:'author',last_message_is_support_reply:false,created_at:stamp,updated_at:stamp,closed_at:null,messages:Array.from({length:40},(_,i)=>({...message,uuid:'message-'+i,content:`Message ${i+1}: ${message.content} `+ 'The failed source remains attached to the project. '.repeat(i===39?15:1)})),attachments:[{uuid:'image-1',filename:'budget-evidence.png',file_type:'image/png',uploaded_by:'author',message_uuid:null,created_at:stamp}]}
let ticket=structuredClone(base),failures=new Set(),sent=[],uploads=[],patches=[]
await page.route('**/api/**',async r=>{
 const p=new URL(r.request().url()).pathname.replace(/\/$/,''),method=r.request().method()
 const key=method+' '+p
 if(p==='/api/support/tickets/staff-1/messages')sent.push(r.request().postDataJSON())
 if(p==='/api/support/tickets/staff-1/attachments'&&method==='POST')uploads.push(r.request().postDataBuffer().toString())
 if(p==='/api/support/tickets/staff-1'&&method==='PATCH')patches.push(r.request().postDataJSON())
 if(failures.has(key))return r.fulfill({status:503,json:{detail:'Temporary service failure. Retry your retained work.'}})
 if(p==='/api/auth/me')return r.fulfill({json:{id:'reviewer',user_id:'reviewer',email:'reviewer@example.test',name:'Alex Morgan',is_admin:false,is_staff:false,is_examiner:false,is_support_agent:true,is_demo_user:false,current_team:'team-1',current_team_uuid:'team-1'}})
 if(p==='/api/support/stats')return r.fulfill({json:{total:50,open:35,in_progress:10,closed:5}})
 if(p==='/api/support/tags')return r.fulfill({json:{tags:['documents','processing']}})
 if(p==='/api/support/contacts')return r.fulfill({json:{contacts:[{user_id:'reviewer',name:'Alex Morgan',email:'reviewer@example.test'}]}})
 if(p==='/api/support/tickets')return r.fulfill({json:{tickets:[ticket,...Array.from({length:49},(_,i)=>({...base,uuid:'other-'+i,ticket_number:1025+i,subject:'Research source review '+i}))],total:50,limit:200,offset:0}})
 if(p==='/api/support/tickets/staff-1'){
  if(method==='PATCH')Object.assign(ticket,r.request().postDataJSON())
  return r.fulfill({json:ticket})
 }
 if(p==='/api/support/tickets/staff-1/read')return r.fulfill({json:{ok:true}})
 if(p==='/api/support/tickets/staff-1/messages'){
  const body=r.request().postDataJSON();ticket.messages.push({...message,uuid:'reply-'+sent.length,user_id:'reviewer',user_name:'Alex Morgan',is_support_reply:true,...body});return r.fulfill({json:ticket})
 }
 if(p==='/api/support/tickets/staff-1/attachments'&&method==='POST'){
  ticket.attachments.push({uuid:'file-1',filename:'support-evidence.txt',file_type:'text/plain',uploaded_by:'reviewer',message_uuid:null,created_at:stamp});return r.fulfill({json:ticket})
 }
 if(p==='/api/support/tickets/staff-1/attachments/image-1')return r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="220" height="120"><rect width="220" height="120" fill="#dbeafe"/><text x="16" y="60" fill="#1e3a8a">Synthetic budget evidence</text></svg>'})
 if(p==='/api/support/tickets/staff-1/watchers'){
  ticket.watchers=[{user_id:'watcher-1',name:'Casey Research — Sponsored Programs',email:r.request().postDataJSON().email}];return r.fulfill({json:ticket})
 }
 if(p==='/api/support/tickets/staff-1/watchers/watcher-1'){ticket.watchers=[];return r.fulfill({json:ticket})}
 if(p==='/api/feedback/admin/stats')return r.fulfill({json:{by_source:{chat:15,extraction:10,product:8},thumbs_up_rate:.84,positive_last_7_days:12}})
 if(p==='/api/feedback/admin/positive')return r.fulfill({json:{items:[{source:'product',sentiment:'positive',message:'The document stays open beside the review workflow, so I can check requirements against the source before handing off the result.',feature:'workspace',user_id:'author',created_at:stamp}],count:1}})
 return r.fallback()
})
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id+': page overflow');assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': accessibility');console.log('Captured '+id)}
async function backToQueue(){while(await page.getByRole('button',{name:'Dismiss error',exact:true}).count())await page.getByRole('button',{name:'Dismiss error',exact:true}).first().click();await page.getByRole('button',{name:'Back to tickets',exact:true}).click()}
const open=()=>page.getByRole('button',{name:'Open ticket 1024: '+subject,exact:true})
try{
 for(const width of [320,1440]){
  ticket=structuredClone(base);failures=new Set(['GET /api/support/tickets/staff-1']);sent=[];uploads=[];patches=[]
  await page.setViewportSize({width,height:width===320?640:1000});await page.goto(review.baseURL+'/support?q=budget&priority=high');await open().waitFor();await shot('staff-dense-queue-'+width)
  await open().press('Enter');await page.getByRole('button',{name:'Retry ticket',exact:true}).waitFor();await shot('staff-detail-error-'+width);failures.clear();await page.getByRole('button',{name:'Retry ticket',exact:true}).click();await page.getByRole('textbox',{name:'Reply',exact:true}).waitFor()
  failures.add('PATCH /api/support/tickets/staff-1');await page.getByRole('button',{name:'Assign to me',exact:true}).click();await page.getByText('Could not assign ticket',{exact:true}).waitFor();assert.equal(ticket.assigned_to,null);failures.clear();await page.getByRole('button',{name:'Assign to me',exact:true}).click();await page.getByText('Assigned to you',{exact:true}).waitFor();await page.getByRole('button',{name:'Release assignment',exact:true}).click();await page.getByText('Unassigned',{exact:true}).waitFor()
  await page.getByRole('combobox',{name:'Change ticket status'}).selectOption('in_progress');await expect(page.getByRole('combobox',{name:'Change ticket status'})).toHaveValue('in_progress')
  const reply=page.getByRole('textbox',{name:'Reply',exact:true});await reply.fill('I will check the source processing status.');await page.getByRole('button',{name:'Internal note',exact:true}).click();const note=page.getByRole('textbox',{name:'Internal note',exact:true});await note.fill('Internal: investigate the worker before sending a requester-visible reply.')
  failures.add('POST /api/support/tickets/staff-1/messages');await page.getByRole('button',{name:'Add Note',exact:true}).click();await page.getByText('Failed to send message',{exact:true}).waitFor();assert.deepEqual(sent,[{content:'Internal: investigate the worker before sending a requester-visible reply.',is_internal_note:true}]);assert.ok((await note.boundingBox()).width >= 180, 'Reply text must have usable line length');await shot('staff-internal-note-recovery-'+width)
  failures.add('POST /api/support/tickets/staff-1/attachments');await page.locator('input[type=file]').setInputFiles({name:'support-evidence.txt',mimeType:'text/plain',buffer:Buffer.from('Synthetic support evidence for recovery checks.')});await page.getByRole('button',{name:'Retry attachments',exact:true}).waitFor();await expect(page.getByRole('button',{name:'Retry attachments',exact:true})).toBeEnabled()
  while(await page.getByRole('button',{name:'Dismiss error',exact:true}).count())await page.getByRole('button',{name:'Dismiss error',exact:true}).first().click();await backToQueue();await open().click();await note.waitFor();assert.equal(await note.inputValue(),sent[0].content);await page.getByRole('button',{name:'Retry attachments',exact:true}).waitFor();assert.ok(page.url().includes('q=budget'));await shot('staff-retained-file-draft-'+width)
  failures.clear();await page.getByRole('button',{name:'Retry attachments',exact:true}).click();await page.getByRole('link',{name:'support-evidence.txt',exact:true}).waitFor();assert.equal(uploads.length,2);assert.ok(uploads.every(body=>body.includes('Synthetic support evidence for recovery checks.')))
  await page.getByRole('button',{name:'Add Note',exact:true}).click();await page.getByRole('textbox',{name:'Reply',exact:true}).waitFor();assert.deepEqual(sent[1],sent[0]);assert.equal(await reply.inputValue(),'')
  await reply.fill('The source is available for inspection.');await page.getByRole('button',{name:'Reply',exact:true}).click();await expect(reply).toHaveValue('');assert.equal(sent.at(-1).is_internal_note,false)
  await page.getByRole('button',{name:'Tag user',exact:true}).click();await page.getByRole('textbox',{name:'Watcher email'}).fill('casey@example.test');failures.add('POST /api/support/tickets/staff-1/watchers');await page.getByRole('button',{name:'Add watcher',exact:true}).click();await page.getByText('Temporary service failure. Retry your retained work.',{exact:true}).last().waitFor();assert.equal(await page.getByRole('textbox',{name:'Watcher email'}).inputValue(),'casey@example.test');failures.clear();await page.getByRole('button',{name:'Add watcher',exact:true}).click();await page.getByRole('button',{name:'Remove watcher Casey Research — Sponsored Programs'}).waitFor();await shot('staff-watcher-'+width);await page.getByRole('button',{name:'Remove watcher Casey Research — Sponsored Programs'}).click();await page.getByRole('button',{name:'Remove watcher Casey Research — Sponsored Programs'}).waitFor({state:'hidden'})
  const preview=page.getByRole('button',{name:'budget-evidence.png',exact:true});await preview.click();const dialog=page.getByRole('dialog',{name:'Attachment: budget-evidence.png'});await dialog.waitFor();await shot('staff-attachment-preview-'+width);await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});await expect(preview).toBeFocused()
  await backToQueue();failures.add('GET /api/feedback/admin/positive');await page.getByRole('button',{name:/What.s Working/}).click();await page.getByRole('button',{name:'Retry feedback',exact:true}).waitFor();failures.clear();await page.getByRole('button',{name:'Retry feedback',exact:true}).click();await page.getByText('Positive · last 7 days',{exact:true}).waitFor();await shot('staff-positive-feedback-'+width);await backToQueue();await open().waitFor()
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push('Synthetic non-delivering staff UI: 50-ticket queue, 40-message conversation, failed detail retry, assignment/release, status, failed internal note and attachment retained through queue return, exact payload retries, requester reply, watcher recovery, attachment modal/focus, failed feedback read/retry and return to triage. No real users contacted or backend lifecycle claimed.')
}catch(error){await review.capture('staff-recovery-blocked',String(error));throw error}finally{await review.flush();await review.browser.close()}
