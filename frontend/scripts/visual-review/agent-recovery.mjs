import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page, state } = review
page.setDefaultTimeout(15000)
let failStatus=false, currentStatus='queued', reads=[], writes=[]
const longStep='Compare institutional review requirements with the complete international proposal narrative and supporting budgets'
const runStatus = () => ({status:currentStatus,num_steps_completed:1,num_steps_total:3,current_step_name:longStep,current_step_detail:'Source is no longer accessible.',current_step_preview:null,final_output:{output:{findings:'Complete findings. '+ 'Supporting evidence remains readable. '.repeat(15),review:'Review finished.'}},steps_output:{Extract:'Preserved completed findings'},output_step_names:['Review'],approval_request_id:currentStatus==='paused'?'approval-1':null,error:currentStatus==='failed'?'Source is no longer accessible.':null})
await page.route('**/api/workflows/status?*', route => {
  reads.push(new URL(route.request().url()).searchParams.get('session_id'))
  return failStatus ? route.fulfill({status:503,json:{detail:'Status unavailable'}}) : route.fulfill({json:runStatus()})
})
page.on('request', request=> {if(request.method()!=='GET' && request.url().includes('/api/workflows')) writes.push(request.url())})
const tool=(name,id,args,content)=>[{kind:'tool_call',tool_name:name,tool_call_id:id,args,content:''}, ...(content===undefined?[]:[{kind:'tool_result',tool_name:name,tool_call_id:id,content}])]
async function shot(id,target) {
  if(target) await target.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.ok(review.captures.at(-1).pageWidth<=review.captures.at(-1).viewport.width,id+': overflow')
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': accessibility')
  console.log('Captured '+id)
}
async function send(chunks, message='Review this task') {
  state.chatChunks=chunks
  await page.getByRole('textbox',{name:'Message input'}).fill(message)
  await page.getByRole('button',{name:'Send message',exact:true}).click()
  await page.getByRole('button',{name:'Stop response'}).waitFor({state:'hidden'})
}
async function fresh() { await page.goto(review.baseURL+'/?mode=chat'); await page.getByRole('textbox',{name:'Message input'}).waitFor() }
async function openStream(chunks) {
  await page.evaluate(chunks=>{
    const original=window.fetch.bind(window)
    window.fetch=(input,init)=>{
      if(new URL(typeof input==='string'?input:input.url,location.href).pathname!=='/api/chat')return original(input,init)
      const body=new ReadableStream({start(controller){
        for(const chunk of chunks)controller.enqueue(new TextEncoder().encode(JSON.stringify(chunk)+'\n'))
        init.signal.addEventListener('abort',()=>controller.error(new DOMException('Stopped','AbortError')))
        window.failAgentStream=()=>controller.error(new Error('Connection interrupted'))
      }})
      return Promise.resolve(new Response(body,{headers:{'Content-Type':'application/x-ndjson','X-Conversation-UUID':'agent-conversation','X-Activity-ID':'agent-activity'}}))
    }
  },chunks)
}
try {
 for (const [width,height] of [[320,568],[768,500],[1440,900]]) {
  await page.setViewportSize({width,height}); await fresh()
  const approval=tool('create_workflow','approve',{name:longStep},{needs_confirmation:true,preview:'Create a three-step review workflow. '+ 'Review the proposed inputs and output before continuing. '.repeat(5)})
  await send(approval)
  const card=page.getByRole('region',{name:'Review proposed action'})
  await shot('agent-approval-review-'+width,card.getByRole('button',{name:'Create workflow',exact:true}))
  state.chatChunks=[{kind:'text',content:'Your request is being reviewed; no completion is claimed.'}]
  await card.getByRole('button',{name:'Create workflow',exact:true}).focus();await page.keyboard.press('Enter')
  await page.getByText('Your request is being reviewed; no completion is claimed.',{exact:true}).waitFor()
  assert.equal(state.lastChat.message,'Yes, go ahead')
  await shot('agent-approval-requested-'+width,page.getByRole('region',{name:'Earlier action decision'}))
  await fresh();await send(approval)
  state.chatChunks=[{kind:'text',content:'Your cancellation request was received.'}]
  await card.getByRole('button',{name:'Cancel action'}).focus();await page.keyboard.press('Enter')
  await page.getByText('Your cancellation request was received.',{exact:true}).waitFor()
  assert.equal(state.lastChat.message,'No, cancel that')
  await shot('agent-cancellation-requested-'+width,page.getByRole('region',{name:'Earlier action decision'}))

  await fresh()
  await page.getByRole('button',{name:'Choose a knowledge base',exact:true}).click()
  const picker=page.getByRole('dialog',{name:'Attach knowledge bases'})
  await picker.getByRole('button',{name:'Research administration policies',exact:true}).click();await picker.getByRole('button',{name:'Attach',exact:true}).click()
  await send([...tool('create_workflow','done',{name:'Prepared review'},{workflow_id:'workflow-1',message:'The review workflow is saved.'}),...tool('get_document_text','failed',{document_uuid:'doc-0'},{error:'The selected source cannot be read.',hint:'Choose an accessible source and keep the completed workflow.'})])
  await page.getByRole('button',{name:'Open workflow',exact:true}).waitFor()
  const recovery=page.getByRole('button',{name:'Review recovery options'})
  await shot('agent-failed-step-'+width,recovery)
  state.chatChunks=[{kind:'text',content:'The completed workflow remains saved. Choose another source to continue.'}]
  await recovery.focus();await page.keyboard.press('Enter')
  await page.getByText('The completed workflow remains saved. Choose another source to continue.',{exact:true}).waitFor()
  assert.deepEqual(state.lastChat.knowledge_base_uuids,['kb-1']);assert.ok(state.lastChat.message.includes('Do not repeat completed changes without my approval.'))
  assert.equal(await page.getByRole('button',{name:'Open workflow',exact:true}).count(),1)
  await shot('agent-recovery-keeps-context-'+width)

  await fresh();failStatus=false;currentStatus='queued';reads=[];writes=[]
  await send(tool('run_workflow','run',{workflow_id:'workflow-1'},{session_id:'session-review',status:'running'}))
  const progress=page.getByRole('region',{name:'Workflow run progress'})
  await progress.getByRole('status').filter({hasText:'Workflow queued'}).waitFor()
  await shot('agent-workflow-queued-'+width,progress)
  currentStatus='running';await progress.getByRole('status').filter({hasText:'Workflow running'}).waitFor()
  await shot('agent-workflow-running-'+width,progress)
  failStatus=true;await progress.getByRole('alert').waitFor()
  await shot('agent-workflow-status-error-'+width,progress.getByRole('button',{name:'Check workflow status'}))
  failStatus=false;currentStatus='failed'
  await progress.getByRole('button',{name:'Check workflow status'}).focus();await page.keyboard.press('Enter')
  await progress.getByRole('status').filter({hasText:'Workflow failed'}).waitFor()
  await progress.getByText('Completed step results',{exact:true}).click()
  await shot('agent-workflow-partial-failure-'+width,progress.getByLabel('Completed workflow step results'))
  assert.ok(reads.length>=4 && reads.every(id=>id==='session-review'));assert.deepEqual(writes,[])
  await progress.getByRole('button',{name:'Open this workflow run'}).click()
  await page.waitForURL(url=>url.searchParams.get('workflow')==='workflow-1')
  await page.getByRole('tablist',{name:'Workflow editor sections'}).waitFor()
  assert.deepEqual(writes,[])

  for(const value of ['paused','canceled','completed']) {
    await fresh();currentStatus=value
    await send(tool('run_workflow','run-'+value,{workflow_id:'workflow-1'},{session_id:'session-'+value,status:'running'}))
    await progress.getByRole('status').filter({hasText:value==='paused'?'Awaiting workflow approval':value==='canceled'?'Workflow canceled':'Workflow complete'}).waitFor()
    if(value==='completed') {
      const output=progress.getByLabel('Workflow output',{exact:true});await output.waitFor();assert.ok((await output.textContent()).includes('Review finished.'))
      await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:()=>Promise.reject(new Error('Blocked'))}}))
      await progress.getByRole('button',{name:'Copy workflow output'}).click()
      await progress.getByText('Copy failed. Try again or select the result text.').waitFor()
    }
    await shot('agent-workflow-'+value+'-'+width,progress)
  }

  await fresh()
  await openStream([{kind:'plan_update',content:'',plan_tasks:[{content:'Create workflow',active_form:'Creating workflow',status:'completed'},{content:'Read selected document',active_form:'Reading selected document',status:'in_progress'},{content:'Produce summary',active_form:'Producing summary',status:'pending'}]},...tool('create_workflow','saved',{name:'Preserved'},{workflow_id:'workflow-1',message:'Created and saved.'}),...tool('get_document_text','interrupted',{document_uuid:'doc-0'})])
  await page.getByRole('textbox',{name:'Message input'}).fill('Continue with the saved workflow');await page.getByRole('button',{name:'Send message',exact:true}).click()
  await page.getByRole('list',{name:'Plan steps'}).waitFor()
  await shot('agent-plan-running-'+width,page.getByRole('list',{name:'Plan steps'}))
  await page.getByRole('button',{name:'Stop response'}).click()
  await page.getByText(/Response stopped. Partial output is preserved/).waitFor()
  assert.equal(await page.locator('.animate-spin').count(),0)
  await shot('agent-plan-stopped-'+width,page.getByRole('list',{name:'Plan steps'}))
 }
 review.observations.push('Explicit tool states, long approval previews and keyboard decisions, failed-step recovery with preserved KB context/artifacts, queued/running/paused/canceled/completed workflows, same-session status retry without writes, partial and long final output, clipboard failure, plan progress and Stop. Three widths; synthetic APIs/streams, no live workflow execution or device screen-reader certification.')
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
} catch(error){await review.capture('agent-recovery-blocked',String(error));throw error}
finally{await review.flush();await review.browser.close()}
