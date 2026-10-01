import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page}=review
page.setDefaultTimeout(30000)
let ticket={uuid:'support-1',ticket_number:1024,subject:'Unable to inspect the budget justification after returning to a shared project',status:'open',priority:'high',classification:'bug',user_id:'reviewer',user_name:'Jordan Lee',user_email:'author@example.test',team_id:'team-1',assigned_to:'reviewer',category:null,tags:['documents'],watchers:[],watcher_ids:[],read_by:[],message_count:1,last_message_preview:'The document is still processing.',last_message_at:'2026-09-30T10:00:00Z',last_message_user_id:'reviewer',last_message_is_support_reply:false,created_at:'2026-09-30T10:00:00Z',updated_at:'2026-09-30T10:00:00Z',closed_at:null,messages:[{uuid:'message-1',user_id:'reviewer',user_name:'Jordan Lee',content:'I can open the project, but the budget document says it is processing. Please help me recover the source.',is_support_reply:false,is_internal_note:false,created_at:'2026-09-30T10:00:00Z',edited_at:null}],attachments:[]}
let failList=true,failTicket=true,failSend=true,failUpload=true,sends=[],uploads=[]
await page.route('**/api/support/tickets?*',r=>failList?r.fulfill({status:503,json:{detail:'List unavailable'}}):r.fulfill({json:{tickets:[ticket],total:1,limit:50,offset:0}}))
await page.route('**/api/support/tickets/support-1',r=>failTicket?r.fulfill({status:503,json:{detail:'Ticket unavailable'}}):r.fulfill({json:ticket}))
await page.route('**/api/support/tickets/support-1/read',r=>r.fulfill({json:{ok:true}}))
await page.route('**/api/notifications/read-item/support_ticket/support-1',r=>r.fulfill({json:{ok:true,marked_count:0}}))
await page.route('**/api/support/contacts',r=>r.fulfill({json:{contacts:[]}}))
await page.route('**/api/support/tickets/support-1/messages',r=>{const data=r.request().postDataJSON();sends.push(data);if(failSend)return r.fulfill({status:503,json:{detail:'Message unavailable'}});ticket={...ticket,messages:[...ticket.messages,{uuid:'reply-new',user_id:'reviewer',user_name:'Alex Morgan',content:data.content,is_support_reply:false,is_internal_note:false,created_at:new Date().toISOString(),edited_at:null}]};return r.fulfill({json:ticket})})
await page.route('**/api/support/tickets/support-1/attachments',r=>{uploads.push(r.request().postData());if(failUpload)return r.fulfill({status:503,json:{detail:'Attachment unavailable'}});ticket={...ticket,attachments:[{uuid:'attachment-1',filename:'source-note.txt',file_type:'text/plain',uploaded_by:'reviewer',message_uuid:null,created_at:new Date().toISOString()}]};return r.fulfill({json:ticket})})
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id+': overflow');assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': accessibility');console.log('Captured '+id)}
try {
 await page.setViewportSize({width:390,height:844});await page.goto(review.baseURL+'/')
 await page.getByRole('button',{name:'Support',exact:true}).click()
 const panel=page.getByRole('region',{name:'Support',exact:true})
 await panel.getByRole('button',{name:'Retry tickets',exact:true}).waitFor();failList=false;await panel.getByRole('button',{name:'Retry tickets',exact:true}).click()
 await panel.getByRole('button',{name:new RegExp(ticket.subject)}).click()
 await panel.getByRole('button',{name:'Retry ticket',exact:true}).waitFor();failTicket=false;await panel.getByRole('button',{name:'Retry ticket',exact:true}).click()
 const message=panel.getByRole('textbox',{name:'Message',exact:true});await message.fill('The same budget source still fails to open.')
 await panel.getByRole('button',{name:'Send message',exact:true}).click();await page.getByText('Failed to send message',{exact:true}).waitFor()
 await panel.getByLabel('Upload files',{exact:true}).setInputFiles({name:'source-note.txt',mimeType:'text/plain',buffer:Buffer.from('Synthetic file evidence')})
 await panel.getByRole('button',{name:'Retry attachments',exact:true}).waitFor()
 await panel.getByRole('button',{name:'Close support',exact:true}).click();await page.getByRole('button',{name:'Support',exact:true}).click()
 assert.equal(await message.inputValue(),'The same budget source still fails to open.')
 await panel.getByRole('button',{name:'Retry attachments',exact:true}).waitFor()
 await panel.getByRole('button',{name:'Back',exact:true}).click();await panel.getByRole('button',{name:new RegExp(ticket.subject)}).click()
 assert.equal(await message.inputValue(),'The same budget source still fails to open.')
 await shot('support-reply-and-file-retained')
 failSend=false;await panel.getByRole('button',{name:'Send message',exact:true}).click();await page.waitForFunction(()=>document.querySelector('textarea[aria-label="Message"]')?.value==='')
 assert.deepEqual(sends,[{content:'The same budget source still fails to open.',is_internal_note:false},{content:'The same budget source still fails to open.',is_internal_note:false}])
 failUpload=false;await panel.getByRole('button',{name:'Retry attachments',exact:true}).click();await panel.getByRole('button',{name:'Retry attachments',exact:true}).waitFor({state:'hidden'})
 await panel.getByRole('link',{name:'source-note.txt',exact:true}).waitFor();assert.equal(uploads.length,2);for(const body of uploads)assert.ok(body.includes('Synthetic file evidence'))
 await shot('support-reply-and-file-sent')
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push('Synthetic non-delivering Support list/detail failure recovery; reply text and failed attachment survive panel closure and list return; retries preserve exact text/file content, and successful sends clear only submitted drafts.')
}catch(error){await review.capture('support-reply-blocked',String(error));throw error}
finally{await review.flush();await review.browser.close()}
