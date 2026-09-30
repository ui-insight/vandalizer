import { createReview } from './harness.mjs'
import assert from 'node:assert/strict'
const review=await createReview({output:process.env.REVIEW_OUTPUT||'../artifacts/visual-review',baseURL:process.env.REVIEW_BASE_URL||'http://127.0.0.1:5180'});
const {page,state,capture}=review;
page.setDefaultTimeout(6000);
async function go(path) { const url=new URL(path,review.baseURL);if(!url.searchParams.has('mode'))url.searchParams.set('mode','chat');await page.goto(url.href);await page.getByRole('main').waitFor({state:'attached'});await page.waitForTimeout(500) }
async function shot(id,note='') {console.log(id, (await capture(id,note)).slice(0,14000))}
async function scene(id,fn) {if(process.env.REVIEW_ONLY&&!process.env.REVIEW_ONLY.split(',').includes(id))return;try{await fn()}catch(e){console.log('SCENE FAILED',id,e.message);process.exitCode=1;await shot(id+'-blocked',e.message)}}
try {
 for (const [id,path] of [['chat-home','/'],['files','/?mode=files'],['projects','/?mode=projects'],['automations','/?mode=automations'],['knowledge','/?mode=knowledge'],['library','/?tab=library']].filter(([id])=>!process.env.REVIEW_ONLY||process.env.REVIEW_ONLY.split(',').includes(id))) {
  await page.goto(review.baseURL+path);
  await page.getByRole('main').waitFor({timeout:15000}).catch(async e=>{console.log(await page.locator('body').innerText()); throw e});
  await page.waitForTimeout(700);
  console.log(id, (await capture(id)).slice(0,14000));
 }
 await scene('file-browser',async()=>{
  await go('/?mode=files');await page.getByRole('checkbox',{name:'Select Proposal narrative.pdf',exact:true}).check();await shot('files-selected');
  await page.getByRole('row',{name:'Document: Proposal narrative.pdf',exact:true}).getByRole('button',{name:'More options'}).click();await shot('files-context-menu');
 });
 await scene('project-detail',async()=>{
  await go('/?mode=projects');await page.getByRole('button',{name:/^Community resilience proposal/}).click();await shot('project-detail');
 });
 await scene('automation-detail',async()=>{
  await go('/?mode=automations');await page.getByRole('button',{name:'Open automation: Review incoming proposals',exact:true}).click();await shot('automation-detail');
 });
 await scene('wizard',async()=>{
  await go('/?mode=automations'); await page.getByRole('button',{name:'New',exact:true}).click(); await shot('wizard-1-name');
  await page.getByPlaceholder('e.g. Process grant applications').fill('Review proposal intake');
  await page.getByRole('button',{name:'Next',exact:true}).click();await shot('wizard-2-trigger');
  await page.getByRole('button',{name:'Next',exact:true}).click();await shot('wizard-3-folder');
  await page.locator('#wizard-watch-folder').selectOption('folder-1');
  await page.getByRole('button',{name:'Next',exact:true}).click();await shot('wizard-4-action');
  await page.getByRole('button',{name:'Select Workflow',exact:false}).click(); await shot('wizard-action-picker');
  await page.getByRole('button',{name:'Proposal readiness review',exact:false}).click();
  await page.getByRole('button',{name:'Next',exact:true}).click(); await shot('wizard-5-activation');
 });
 await scene('wizard-keyboard',async()=>{
  await go('/?mode=automations');await page.getByRole('button',{name:'New',exact:true}).click();await page.getByPlaceholder('e.g. Process grant applications').fill('Keyboard review');
  await page.getByPlaceholder('What does this automation do?').fill('First line');await shot('wizard-description-before-enter');await page.getByPlaceholder('What does this automation do?').press('Enter');await shot('wizard-description-enter');
  review.observations.push({id:'wizard-description-enter',expected:'Advance to the next step without dismissing the wizard',actual:await page.getByRole('dialog').count()?await page.getByRole('dialog').innerText():'Dialog dismissed; draft no longer visible'});
  assert.equal(await page.getByRole('dialog').count(),1,'Enter must not dismiss the wizard');
  assert.match(await page.getByRole('dialog').innerText(),/Step 2 of/,'Enter must advance exactly one step');
 });
 await scene('knowledge-detail',async()=>{
  await go('/?mode=knowledge');await page.getByRole('button',{name:'Edit',exact:true}).click();await shot('knowledge-detail');
  await page.getByRole('tab',{name:'Validation',exact:true}).click();await shot('knowledge-validation');
  await page.getByRole('tab',{name:'Test questions',exact:true}).click();await shot('knowledge-queries');
  await page.getByRole('tab',{name:'Check answer quality',exact:true}).click();await shot('knowledge-run');
  await page.getByRole('tab',{name:'History',exact:true}).click();await shot('knowledge-history');
 });
 await scene('validation-wizard',async()=>{
  state.validationQueries=true;await go('/?mode=knowledge');await page.getByRole('button',{name:'Edit',exact:true}).click();
  await page.getByRole('tab',{name:'Validation',exact:true}).click();await page.getByRole('tab',{name:'Improve retrieval',exact:true}).click();await page.getByRole('button',{name:'Validate & improve',exact:true}).click();await shot('validation-wizard-questions');
  for(const id of ['preview','baseline','budget']){await page.getByRole('dialog').getByRole('button',{name:'Next',exact:false}).click();await shot('validation-wizard-'+id)}
  state.validationQueries=false;
 });
 await scene('validation-results',async()=>{
  // Also run in development to guard the StrictMode mounted-ref regression.
  state.validationQueries=true;await go('/?mode=knowledge');await page.getByRole('button',{name:'Edit',exact:true}).click();await page.getByRole('tab',{name:'Validation',exact:true}).click();await page.getByRole('tab',{name:'Check answer quality',exact:true}).click();await page.getByRole('button',{name:'Run 3 questions',exact:true}).click();await page.getByRole('button',{name:'CSV',exact:true}).waitFor({timeout:12000});
  await page.getByText('Average answer accuracy: 90% with this KB, versus 40% without it.',{exact:false}).waitFor();
  assert.equal(await page.getByText('Answer quality not yet measured',{exact:true}).count(),0,'Completed validation must refresh the parent summary');
  await shot('validation-results','Synthetic scored results; summary refreshed from KB detail endpoint, no model grading performed.');
  await page.getByRole('tab',{name:'History',exact:true}).click();await shot('validation-history-populated');state.validationQueries=false;state.validated=false;
 });
 await scene('catalog',async()=>{
  await go('/?tab=library');await page.getByRole('button',{name:'Explore',exact:true}).click();await shot('catalog');
  await page.getByRole('button').filter({hasText:'Proposal readiness review'}).click();await shot('catalog-detail');
 });
 await scene('kb-catalog',async()=>{
  await go('/?mode=knowledge');await page.getByRole('tab',{name:'Explore',exact:true}).click();await shot('knowledge-catalog');
 });
 await scene('chat-upload',async()=>{
  await go('/');await page.getByRole('main').getByRole('button',{name:'Add',exact:true}).click();await shot('chat-add-menu');
  const chooserPromise=page.waitForEvent('filechooser');await page.getByRole('menuitem',{name:/^Add Document(?: |$)/}).click();const chooser=await chooserPromise;
  await chooser.setFiles({name:'Review sample.txt',mimeType:'text/plain',buffer:Buffer.from('Synthetic review fixture. Proposal due October 15. Budget justification required.')});
  await page.getByText('Review sample.txt',{exact:false}).first().waitFor(); await shot('chat-file-attached','Synthetic upload and processing response; no backend ingestion.');
  state.chatChunks=[{kind:'text',content:'Synthetic harness response. Check the recorded request for attachment scope.'}];
  await page.getByRole('textbox',{name:'Message input'}).fill('Summarize the file I just uploaded.');await page.getByRole('button',{name:'Send message'}).click();await page.getByText('Synthetic harness response.',{exact:false}).waitFor();
  review.observations.push({id:'upload-chat-scope',expected:['doc-upload'],actual:state.lastChat?.document_uuids,uploadPresentInFixture:state.uploaded});await shot('chat-file-request','Inspect manifest observation upload-chat-scope for the document UUIDs actually submitted.');
  assert.deepEqual(state.lastChat?.document_uuids,['doc-upload'],'Uploaded file must stay attached to the next chat request');
  state.uploadError=true;await page.getByLabel('Attach files').setInputFiles({name:'Oversized sample.txt',mimeType:'text/plain',buffer:Buffer.from('Synthetic upload error scenario.')});await page.getByRole('button',{name:'Retry upload: Oversized sample.txt'}).waitFor();await shot('chat-upload-error');state.uploadError=false;await page.getByRole('button',{name:'Retry upload: Oversized sample.txt'}).click();await page.getByRole('button',{name:'Dismiss upload: Oversized sample.txt'}).waitFor({state:'hidden'});await shot('chat-upload-retried');
 });
 await scene('chat-kb',async()=>{
  await go('/?mode=knowledge'); await page.getByRole('tabpanel',{name:'Mine'}).getByRole('button',{name:'Chat',exact:true}).click(); await shot('chat-kb-attached');
  state.chatChunks=[{kind:'sources',content:'',sources:[{document_title:'Institutional research policies',kb_title:'Research administration policies',kb_uuid:'kb-1',content_preview:'Proposal due October 15. Budget requires justification.',url:'https://example.org/policies'}]},{kind:'text',content:'The proposal is due **October 15**. Include a budget justification. [1]'}];
  await page.getByRole('textbox',{name:'Message input'}).fill('When is the proposal due, and what must I include?');await page.getByRole('button',{name:'Send message'}).click();await page.getByText('The proposal is due', {exact:false}).waitFor();await shot('chat-kb-answer','Synthetic response and citations; does not evaluate model accuracy.');
 });
 await scene('agent',async()=>{
  await go('/');state.chatChunks=[{kind:'plan_update',content:'',plan_tasks:[{content:'Review proposal requirements',active_form:'Reviewing proposal requirements',status:'completed'},{content:'Create a reusable workflow',active_form:'Creating a reusable workflow',status:'in_progress'}]},{kind:'tool_call',content:'',tool_name:'create_workflow',tool_call_id:'tool-1',args:{name:'Proposal review'}},{kind:'tool_result',tool_name:'create_workflow',tool_call_id:'tool-1',content:{needs_confirmation:true,preview:'Create Proposal review with three steps: extract requirements, review the budget, and summarize gaps.'}},{kind:'text',content:'I can create this reusable workflow. Review the proposed change before confirming.'}];
  await page.getByRole('textbox',{name:'Message input'}).fill('Create a reusable proposal review workflow.');await page.getByRole('button',{name:'Send message'}).click();await page.getByRole('button',{name:'Create workflow',exact:true}).waitFor();await shot('chat-agent-confirmation','Synthetic tool stream; backend execution is not exercised.');
  state.chatChunks=[{kind:'tool_call',content:'',tool_name:'create_workflow',tool_call_id:'tool-2',args:{name:'Proposal review'}},{kind:'tool_result',tool_name:'create_workflow',tool_call_id:'tool-2',content:{workflow_id:'workflow-1',name:'Proposal review',steps_created:3,steps:[{name:'Extract requirements'},{name:'Review budget'},{name:'Summarize gaps'}]}},{kind:'plan_update',content:'',plan_tasks:[{content:'Review proposal requirements',active_form:'Reviewing proposal requirements',status:'completed'},{content:'Create a reusable workflow',active_form:'Creating a reusable workflow',status:'completed'}]},{kind:'text',content:'Created Proposal review. You can open it from the library.'}];
  await page.getByRole('button',{name:'Create workflow',exact:true}).click();await page.getByText('Created Proposal review.',{exact:false}).waitFor();review.observations.push({id:'agent-confirm',actual:state.lastChat.message});await page.getByRole('button',{name:'Open workflow',exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'Create workflow',exact:true}).count(),0,'Approval must not remain actionable after confirmation');await shot('chat-agent-complete');
  state.chatChunks=[{kind:'tool_call',content:'',tool_name:'run_workflow',tool_call_id:'tool-3',args:{workflow_id:'workflow-1'}},{kind:'tool_result',tool_name:'run_workflow',tool_call_id:'tool-3',content:{error:'Select at least one document before running this workflow.'}},{kind:'text',content:'Attach a document, then try the workflow again.'}];
  await page.getByRole('textbox',{name:'Message input'}).fill('Run it now.');await page.getByRole('button',{name:'Send message'}).click();await page.getByText('Attach a document, then try the workflow again.',{exact:false}).waitFor();assert.equal(await page.getByText('All 2 steps completed',{exact:true}).count(),0,'A new failed action must not retain an old completed plan');await shot('chat-agent-error');
 });
 await scene('first-session',async()=>{state.first=true;state.empty=true;await go('/');await shot('chat-onboarding');state.first=false});
 for (const [id,path] of [['files','/?mode=files'],['projects','/?mode=projects'],['automations','/?mode=automations'],['knowledge','/?mode=knowledge'],['library','/?tab=library']]) await scene(id+'-empty',async()=>{await go(path);await shot(id+'-empty')});
 state.empty=false;
 await page.setViewportSize({width:390,height:844});
 await scene('automation-editor-mobile',async()=>{await go('/?mode=automations');await page.getByRole('button',{name:'Open automation: Review incoming proposals',exact:true}).click();await shot('automation-editor-mobile');await page.getByRole('button',{name:'Close automation',exact:true}).click();await page.getByRole('button',{name:'Close automation',exact:true}).waitFor({state:'hidden'});await page.getByRole('button',{name:'Automations panel',exact:true}).click();await page.getByRole('button',{name:'New',exact:true}).waitFor()});
 for (const [id,path] of [['chat','/'],['files','/?mode=files'],['projects','/?mode=projects'],['automations','/?mode=automations'],['knowledge','/?mode=knowledge'],['library','/?tab=library']]) await scene(id+'-mobile',async()=>{await go(path);await shot(id+'-mobile')});
} finally {await review.flush();await review.browser.close();if(review.unmatched.size||review.errors.length)process.exitCode=1;console.log(JSON.stringify({captures:review.captures.length,unmatched:[...review.unmatched],errors:review.errors,observations:review.observations},null,2))}
