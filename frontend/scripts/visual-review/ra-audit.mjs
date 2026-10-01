// Supplemental fresh RA audit; all API data is synthetic. Never reaches a live backend.
import { createReview } from './harness.mjs'
import { workflow, kb } from './fixtures.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page}=review
page.setDefaultTimeout(8000)
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

const sampleReview={uuid:'ra-review-1',workflow_id:'workflow-1',workflow_name:'Proposal readiness review',step_name:'Approve submission readiness',status:'pending',assigned_to_user_ids:['reviewer'],assignee_role:'specific_users',requester_user_id:'colleague',team_id:'team-1',expires_at:'2026-10-02T17:00:00Z',created_at:'2026-09-30T10:00:00Z',decision_at:null,escalated_at:null,step_index:1,review_instructions:'Check the missing budget justification and confirm the sponsor deadline before approving.',artifact_kind:'markdown',data_for_review:{value:'## Proposal readiness\n\n**Needs attention:** Budget justification is missing.\n\n- Sponsor deadline: October 15\n- Responsible reviewer: Research office\n- Next action: Request the justification from the PI.'},edited_artifact:null,timeout_action:'none',escalation_user_ids:[],reviewer_user_id:null,reviewer_comments:'',expired_at:null,source_docs:[{uuid:'doc-0',title:'Proposal narrative.pdf'}],requester:{user_id:'colleague',name:'Jordan Lee',email:'jordan@example.test'}}
const stats={conversations:42,search_runs:28,workflows_started:16,workflows_completed:14,workflows_failed:2,tokens_in:280000,tokens_out:42000,active_users:5,active_teams:1}
const extra={
 '/api/certification/modules/ai_literacy/exercise':{documents:[],instructions:[],expected_fields:[],expected_values:{},star_criteria:{}},
 '/api/verification/queue':{requests:[]},'/api/verification/mine':{requests:[]},
 '/api/projects/project-1/members':[{user_id:'reviewer',role:'owner',name:'Alex Morgan',email:'reviewer@example.test'},{user_id:'colleague',role:'editor',name:'Jordan Lee',email:'jordan@example.test'}],
 '/api/admin/system/version':{current:'5.0.0',latest:'5.0.0',update_available:false},
 '/api/extractions/run-sync':{results:[{Budget:'200'}],sources:[{Budget:{quote:'The budget is 200.',page:1,document_uuid:'doc-0',document_title:'Proposal narrative.pdf',verified:true,value_supported:true,support:'supported'}}]},
 '/api/library/items/item-1/touch':{ok:true},
 '/api/chat/memory':{extractions:[],workflows:[],kbs:[]},
 '/api/auth/config':{auth_methods:['password'],oauth_providers:[],demo_login_enabled:false,trial_system_enabled:false},
 '/api/auth/email-preferences':{onboarding:true,nudges:true,announcements:true},
 '/api/auth/api-token/status':{has_token:false,created_at:null},
 '/api/teams/team-1/members':[{user_id:'reviewer',name:'Alex Morgan',email:'reviewer@example.test',role:'owner'},{user_id:'colleague',name:'Jordan Lee',email:'jordan@example.test',role:'member'}],
 '/api/teams/team-1/invites':[], '/api/teams/team-1/join-links':[],
 '/api/credentials':[],
 '/api/reviews':{reviews:[sampleReview]},'/api/reviews/team':{reviews:[sampleReview]},'/api/reviews/ra-review-1':sampleReview,
 '/api/support/tickets':{tickets:[],total:0,limit:50,offset:0},'/api/support/stats':{total:0,open:0,in_progress:0,closed:0},'/api/support/tags':{tags:[]},'/api/support/contacts':{contacts:[]},
 '/api/optimizer/inbox':{items:[],counts:{total:0,needs_review:0,failed:0,in_flight:0,applied:0,no_change:0,dismissed:0,pending_review:0},lookback_days:30},
 '/api/admin/usage':stats,'/api/admin/usage/timeseries':{days:[],previous_period:stats},
 '/api/files/download':null,
}
await page.route('**/api/**',async route=>{
 const p=new URL(route.request().url()).pathname.replace(/\/$/,'')
 if(p==='/api/files/download')return route.fulfill({contentType:'text/plain',body:'Synthetic proposal text: budget justification missing; due October 15.'})
 if(Object.hasOwn(extra,p))return route.fulfill({json:extra[p]})
 return route.fallback()
})
async function shot(id){await review.capture(id,'Fresh RA audit; synthetic data.');console.log('Captured '+id)}
async function scene(id,fn){if(process.env.REVIEW_ONLY&&!process.env.REVIEW_ONLY.split(',').includes(id))return;try{await fn()}catch(e){review.observations.push({id,error:e.message});console.log('SCENE FAILED '+id+': '+e.message);await shot(id+'-blocked')}}
async function go(path){await page.goto(review.baseURL+path);await page.getByRole('main').first().waitFor();await page.waitForTimeout(600)}
try{
 for(const [id,path] of [['account','/account'],['teams','/teams'],['credentials','/credentials'],['reviews','/reviews'],['review-detail','/reviews/ra-review-1'],['support','/support'],['docs','/docs'],['certification','/certification'],['tuning','/tuning'],['team-admin','/admin']])await scene(id,async()=>{await go(path);await shot(id)})
 await scene('credentials-form',async()=>{await go('/credentials');await page.getByRole('button',{name:/New credential/i}).click();await shot('credentials-form')})
 await scene('support-form',async()=>{await go('/');await page.getByRole('button',{name:'Support',exact:true}).click();await shot('support-widget');await page.getByRole('button',{name:'Create your first ticket',exact:true}).click();await shot('support-form')})
 for(const domain of ['workflow','extraction'])await scene(domain,async()=>{
  await go('/?mode=files&tab=library&'+domain+'='+(domain==='workflow'?'workflow-1':'item-1'))
  await shot(domain+'-design')
  const tabs=domain==='workflow'?['Input','Validate','History']:['Results','Validate','History']
  for(const name of tabs){const tab=page.getByRole('tab',{name,exact:true});if(await tab.count()){await tab.click();await shot(domain+'-'+name.toLowerCase())}}
 })
 await scene('workspace-chrome',async()=>{await go('/');await page.getByRole('button',{name:'Expand activity',exact:true}).click();await shot('activity');await page.getByRole('button',{name:/Account menu/i}).click();await shot('account-menu')})

 await scene('extraction-result',async()=>{await go('/?mode=files&tab=library&extraction=item-1');await page.getByRole('checkbox',{name:'Select Proposal narrative.pdf',exact:true}).check();await review.context.grantPermissions(['clipboard-read','clipboard-write']);await page.route('**/api/documents/poll_status*',r=>r.fulfill({json:{status:'SUCCESS',status_messages:[],complete:true,raw_text:'Synthetic review document. The budget is 200. Proposal due October 15. Budget requires justification.',valid:true,processing:false,title:'Proposal narrative.pdf'}}));await page.getByRole('button',{name:'RUN',exact:true}).click();await page.getByText('200',{exact:false}).first().waitFor();await shot('extraction-result');await page.getByText('p. 1',{exact:true}).click();await shot('extraction-source');})
 await scene('workflow-step',async()=>{await go('/?mode=files&tab=library&workflow=workflow-1');review.observations.push({id:'workflow-step-keyboard',elements:await page.getByText('Review evidence',{exact:false}).evaluateAll(es=>es.map(e=>({text:e.textContent,tag:e.tagName,role:e.getAttribute('role'),tabIndex:e.tabIndex,parentRole:e.parentElement?.parentElement?.getAttribute('role'),parentTabIndex:e.parentElement?.parentElement?.tabIndex})))});await page.getByText('Review evidence',{exact:false}).click();await shot('workflow-step');})
 await scene('project-manage',async()=>{await go('/?mode=projects');await page.getByRole('button',{name:/^Community resilience proposal/}).click();await page.getByRole('button',{name:'Manage project',exact:true}).click();await shot('project-manage');})
 await scene('review-edit',async()=>{await go('/reviews/ra-review-1');await page.getByRole('button',{name:'Edit before approving',exact:true}).click();await shot('review-edit')})
 await scene('docs-top',async()=>{await go('/docs');await shot('docs-top');await page.screenshot({path:review.out+'/docs-top.png',fullPage:false});await page.setViewportSize({width:390,height:844});await shot('docs-top-mobile');await page.screenshot({path:review.out+'/docs-top-mobile.png',fullPage:false});await page.setViewportSize({width:1440,height:1000})})


 await scene('automation-history',async()=>{const run={trigger_event_id:'000000000000000000000100',status:'completed',action_type:'workflow',created_at:'2026-09-30T10:00:00Z',started_at:'2026-09-30T10:00:00Z',completed_at:'2026-09-30T10:01:00Z',error:null,output:'Budget justification is missing. Request it from the PI before submission.'};await page.route('**/api/automations/auto-1/runs?*',r=>r.fulfill({json:{items:[run],next_cursor:null}}));await page.route('**/api/automations/auto-1/runs/*',r=>r.fulfill({json:run}));await go('/?mode=automations&automation=auto-1');await page.getByRole('button',{name:'Run history Recorded status and results',exact:true}).click();await shot('automation-history');await page.getByRole('button',{name:'Open run '+run.trigger_event_id,exact:true}).click();await shot('automation-output')})
 await scene('certification-lesson',async()=>{await go('/certification');await page.getByRole('button',{name:/^0 AI Literacy/}).click();await shot('certification-lesson')})
 await scene('activity-populated',async()=>{await page.route('**/api/activity/streams/**',r=>r.fulfill({json:{events:[{id:'activity-1',type:'workflow_run',status:'failed',title:'Proposal readiness review',conversation_id:null,search_set_uuid:null,workflow_id:'workflow-1',workflow_session_id:'session-1',started_at:new Date().toISOString(),finished_at:new Date().toISOString(),last_updated_at:new Date().toISOString(),error:'Workflow queue unavailable',tokens_input:0,tokens_output:0,message_count:0,result_snapshot:{}}],stale_threshold_minutes:30}}));await go('/');await page.getByRole('button',{name:'Expand activity',exact:true}).click();await shot('activity-populated')})

 await scene('team-admin-geometry',async()=>{await page.setViewportSize({width:390,height:844});await go('/admin');review.observations.push({id:'team-admin-overflow',containers:await page.evaluate(()=>[...document.querySelectorAll('*')].filter(e=>e.clientWidth>0&&e.scrollWidth>e.clientWidth+10&&['auto','scroll'].includes(getComputedStyle(e).overflowX)).map(e=>({tag:e.tagName,class:e.className,width:e.clientWidth,contentWidth:e.scrollWidth})))});await shot('team-admin-mobile');await page.setViewportSize({width:1440,height:1000})})
 for(const [id,path] of [['teams','/teams'],['review-detail','/reviews/ra-review-1'],['support','/support'],['docs','/docs'],['certification','/certification'],['team-admin','/admin']])await scene(id+'-mobile',async()=>{await page.setViewportSize({width:390,height:844});await go(path);await shot(id+'-mobile')})

 await scene('role-surfaces',async()=>{await page.route('**/api/auth/me',r=>r.fulfill({json:{id:'reviewer',user_id:'reviewer',email:'reviewer@example.test',name:'Alex Morgan',is_admin:false,is_staff:false,is_examiner:true,is_support_agent:true,is_demo_user:false,current_team:'team-1',current_team_uuid:'team-1',sso_provider:null}}));await go('/verification');await shot('examiner-queue');await go('/support');await shot('support-staff');await page.setViewportSize({width:390,height:844});await go('/verification');await shot('examiner-mobile');await page.setViewportSize({width:1440,height:1000})})
 await scene('ra8-keyboard',async()=>{
  await page.setViewportSize({width:1440,height:1000})
  await go('/?mode=files&tab=library&workflow=workflow-1')
  const openStep=page.getByRole('button',{name:'Open step: Review evidence',exact:true})
  await openStep.focus();await page.keyboard.press('Enter')
  const step=page.getByRole('region',{name:'Edit step: Review evidence',exact:true})
  await step.waitFor()
  if(!await step.evaluate(e=>e===document.activeElement))throw Error('Step did not receive focus')
  if(!await openStep.evaluate(e=>!!e.closest('[inert]')))throw Error('Covered step action remains keyboard reachable')
  const openTask=page.getByRole('button',{name:'Edit task: Prompt',exact:true})
  await openTask.focus();await page.keyboard.press('Space')
  await page.getByRole('region',{name:'Edit task: Prompt',exact:true}).waitFor()
  await page.keyboard.press('Escape')
  await page.waitForTimeout(80)
  if(!await openTask.evaluate(e=>e===document.activeElement))throw Error('Task did not return focus')
  await page.keyboard.press('Escape');await page.waitForTimeout(80)
  if(!await openStep.evaluate(e=>e===document.activeElement))throw Error('Step did not return focus')
  await openStep.press('Enter')
  await page.getByRole('button',{name:'ADD A TASK',exact:true}).press('Enter')
  await page.getByRole('region',{name:'Add a task',exact:true}).waitFor()
  await page.keyboard.press('Escape')
  await step.waitFor()
  await shot('workflow-keyboard-step')
  await page.keyboard.press('Escape')
  for(const name of ['Design','Input','Validate','Advanced','History']){
   const tab=page.getByRole('tab',{name,exact:true})
   if(!await tab.getByText(name,{exact:true}).isVisible())throw Error(name+' label hidden')
  }
  await shot('workflow-readable-tabs')
  await go('/docs');await page.setViewportSize({width:320,height:568})
  await page.getByRole('button',{name:'Open documentation navigation',exact:true}).press('Enter')
  await page.getByRole('dialog',{name:'Documentation navigation'}).waitFor()
  await page.keyboard.press('Escape');await page.waitForTimeout(80)
  if(!await page.getByRole('button',{name:'Open documentation navigation',exact:true}).evaluate(e=>e===document.activeElement))throw Error('Docs menu did not return focus')
  await shot('docs-320')
  await go('/');await page.getByRole('button',{name:'Support',exact:true}).click()
  await page.getByRole('button',{name:'Close support',exact:true}).waitFor()
  await shot('support-320')
  for(const width of [320,390,768,1024,1440]){
   await page.setViewportSize({width,height:width===320?568:900});await go('/admin')
   const overflow=await page.locator('.section-page').evaluate(root=>[root,...root.querySelectorAll('*')].filter(e=>e.clientWidth>0&&e.scrollWidth>e.clientWidth+2&&getComputedStyle(e).overflowX!=='visible').map(e=>({tag:e.tagName,width:e.clientWidth,scroll:e.scrollWidth})))
   if(overflow.length)throw Error('Admin nested overflow '+width+': '+JSON.stringify(overflow))
   await shot('admin-'+width)
  }
  await page.route('**/api/auth/me',r=>r.fulfill({json:{id:'reviewer',user_id:'reviewer',email:'reviewer@example.test',name:'Alex Morgan',is_admin:false,is_staff:false,is_examiner:true,is_support_agent:true,is_demo_user:false,current_team:'team-1',current_team_uuid:'team-1',sso_provider:null}}))
  for(const width of [320,390]){await page.setViewportSize({width,height:568});await go('/verification');await shot('examiner-'+width)}
  review.observations.push({id:'ra8-keyboard',passed:true,checks:['Enter/Space step and task opening','nested Escape and focus return','picker Escape retains step','visible workflow labels','Docs Escape and return','Admin nested widths','named Support close']})
 })

 await scene('ra8-recovery',async()=>{
  await page.route('**/api/auth/me',r=>r.fulfill({json:{id:'reviewer',user_id:'reviewer',email:'reviewer@example.test',name:'Alex Morgan',is_admin:false,is_staff:false,is_examiner:false,is_support_agent:false,is_demo_user:false,current_team:'team-1',current_team_uuid:'team-1',sso_provider:null}}))
  await page.setViewportSize({width:390,height:844});await go('/')
  await page.getByRole('button',{name:'Support',exact:true}).click()
  await page.getByRole('button',{name:'Create your first ticket',exact:true}).click()
  await page.getByLabel('Subject',{exact:true}).fill('Source page missing')
  await page.getByLabel('Description',{exact:true}).fill('The budget source does not open. I expected page 2.')
  await page.getByRole('region',{name:'Support',exact:true}).getByLabel('Upload files',{exact:true}).setInputFiles({name:'source-note.txt',mimeType:'text/plain',buffer:Buffer.from('Synthetic evidence')})
  let sends=0
  await page.route('**/api/support/tickets',async r=>{
   if(r.request().method()!=='POST')return r.fallback()
   sends++;await new Promise(resolve=>setTimeout(resolve,300));return r.fulfill({status:503,json:{detail:'Support unavailable. Please retry.'}})
  })
  await page.getByRole('button',{name:'Submit Ticket',exact:true}).click()
  await page.getByText('Support unavailable. Please retry.',{exact:true}).waitFor()
  await page.getByRole('button',{name:'Close support',exact:true}).click()
  await page.getByRole('button',{name:'Support',exact:true}).click()
  if(await page.getByLabel('Subject',{exact:true}).inputValue()!=='Source page missing')throw Error('Support subject lost')
  if(await page.getByLabel('Description',{exact:true}).inputValue()!=='The budget source does not open. I expected page 2.')throw Error('Support description lost')
  await page.getByText('source-note.txt',{exact:true}).waitFor()
  if(sends!==1)throw Error('Unexpected ticket submission count')
  await shot('support-recovered-draft')
  await page.getByRole('button',{name:'Submit Ticket',exact:true}).click()
  await page.waitForTimeout(500);if(sends!==2)throw Error('Ticket retry missing')
  await page.getByRole('button',{name:'Close support',exact:true}).click()
  await page.setViewportSize({width:1440,height:900})
  await go('/?mode=files&tab=library&extraction=item-1')
  await page.getByRole('checkbox',{name:'Select Proposal narrative.pdf',exact:true}).check()
  await review.context.grantPermissions(['clipboard-read','clipboard-write'])
  await page.evaluate(()=>navigator.clipboard.writeText('Keep my clipboard'))
  await page.route('**/api/documents/poll_status*',r=>r.fulfill({json:{status:'SUCCESS',status_messages:[],complete:true,raw_text:'Synthetic review document. The budget is 200.',valid:true,processing:false,title:'Proposal narrative.pdf'}}))
  await page.getByRole('button',{name:'RUN',exact:true}).click()
  const inspect=page.getByRole('button',{name:'Inspect source for Budget',exact:true})
  await inspect.waitFor();await inspect.focus();await page.keyboard.press('Enter')
  await page.getByText('Synthetic review document.',{exact:false}).waitFor()
  if(await page.evaluate(()=>navigator.clipboard.readText())!=='Keep my clipboard')throw Error('Inspection changed clipboard')
  await page.getByRole('button',{name:'Copy value for Budget',exact:true}).press('Enter')
  await page.waitForTimeout(100)
  if(await page.evaluate(()=>navigator.clipboard.readText())!=='200')throw Error('Copy did not copy exact value')
  await shot('extraction-separate-actions')
  for(const width of [1440,1024,390,320]){
   await page.setViewportSize({width,height:844});await go('/?mode=automations&automation=auto-1')
   await shot('automation-title-'+width)
  }
  review.observations.push({id:'ra8-recovery',passed:true,checks:['Failed Support send retains text and attachment after panel close/reopen','explicit retry sends once','source inspection leaves clipboard intact','copy writes exact value','automation titles at four widths']})
 })

 await scene('ra8-project',async()=>{
  await page.setViewportSize({width:1440,height:1000})
  await page.route('**/api/projects/project-1/pins',r=>r.fulfill({json:[{pin_type:'workflow',target_id:'workflow-1',name:'Proposal readiness review'}]}))
  let runs=0;await page.route('**/api/workflows/workflow-1/run',r=>{runs++;return r.fulfill({status:500,json:{detail:'This scene must not run the workflow'}})})
  await go('/?mode=files&project=project-1')
  const project=page.getByRole('region',{name:'Active project'})
  await project.getByRole('button',{name:'Open files',exact:true}).click()
  await page.getByRole('row',{name:'Document: Proposal narrative.pdf',exact:true}).click()
  await page.getByText('Synthetic review document.',{exact:false}).waitFor()
  await project.getByRole('button',{name:'Pinned tools (1)',exact:true}).click()
  await project.getByRole('button',{name:'Proposal readiness review · workflow',exact:true}).click()
  await page.getByRole('button',{name:'RUN',exact:true}).waitFor()
  if(!await project.getByText('Community resilience proposal',{exact:true}).isVisible())throw Error('Project scope lost')
  await page.getByRole('button',{name:'Close document',exact:true}).waitFor()
  if(runs)throw Error('Opening a pin executed it')
  await shot('project-work-overview')
  await project.getByRole('button',{name:'Pinned tools (1)',exact:true}).click()
  await page.setViewportSize({width:390,height:844});await shot('project-work-mobile')
  await project.getByRole('button',{name:'Ask about project',exact:true}).click()
  if(!await project.getByText('Community resilience proposal',{exact:true}).isVisible())throw Error('Project chat lost scope')
  review.observations.push({id:'ra8-project',passed:true,checks:['overview and pins outside Manage','opening pin retains document and project','opening pin does not run it','project chat retains scope']})
 })
 await scene('ra8-knowledge-learning',async()=>{
  await page.setViewportSize({width:1440,height:1000})
  const sources=[...kb.sources,
   {...kb.sources[0],uuid:'partial-source',document_title:'Incomplete budget guidance',ingestion_warning_text:'only part of the document could be converted'},
   {...kb.sources[1],uuid:'pending-source',url_title:'New sponsor notice',status:'processing',chunk_count:0},
   {...kb.sources[0],uuid:'deleted-source',document_title:'Removed original',document_exists:false}]
  await page.route('**/api/knowledge/kb-1',r=>r.fulfill({json:{...kb,total_sources:6,sources_ready:4,sources}}))
  await go('/?mode=knowledge');await page.getByRole('button',{name:'Edit',exact:true}).click()
  await page.getByRole('combobox',{name:/^Source status/}).selectOption('attention')
  if(await page.getByRole('button',{name:'Inspect source: Proposal narrative.pdf',exact:true}).count())throw Error('Healthy source remained in attention filter')
  for(const name of ['Incomplete budget guidance','New sponsor notice','Removed original'])await page.getByRole('button',{name:'Inspect source: '+name,exact:true}).waitFor()
  await page.getByLabel('Find a source',{exact:true}).fill('Incomplete')
  await page.getByText('Showing 1 of 6',{exact:true}).waitFor();await shot('knowledge-filtered-attention')
  await page.getByLabel('Find a source',{exact:true}).fill('no-match')
  await page.getByRole('button',{name:'Clear source filters',exact:true}).click()
  await page.getByText('Showing 6 of 6',{exact:true}).waitFor()
  await page.getByRole('tab',{name:'Validation',exact:true}).click()
  if(await page.getByRole('tab',{name:'Test questions',exact:true}).getAttribute('aria-selected')!=='true')throw Error('Validation does not start with questions')
  await shot('knowledge-validation-questions')
  await page.getByRole('tab',{name:'Check answer quality',exact:true}).click();await shot('knowledge-validation-check')
  await page.setViewportSize({width:320,height:640});await page.getByRole('tab',{name:'Check answer quality',exact:true}).scrollIntoViewIfNeeded();await shot('knowledge-validation-mobile')
  await go('/certification')
  await page.getByRole('heading',{name:'Check a proposal requirement',exact:true}).waitFor()
  const position=page.getByRole('combobox',{name:'Learning panel position',exact:true})
  for(const mode of ['floating','docked-left','docked-right','docked-bottom','fullscreen']){
   await position.selectOption(mode)
   const bounds=await page.locator('[data-cert-panel]').boundingBox()
   if(!bounds||bounds.x < -1||bounds.x+bounds.width>321)throw Error('Learning panel outside viewport in '+mode)
  }
  const closeBounds=await page.getByRole('button',{name:'Return to workspace',exact:true}).boundingBox();if(!closeBounds||closeBounds.x+closeBounds.width>320)throw Error('Learning close action clipped');await shot('learning-mobile')
  await page.keyboard.press('Tab')
  if(!await page.getByRole('dialog',{name:'Learning and certification'}).evaluate(e=>e.contains(document.activeElement)))throw Error('Learning fullscreen focus escaped')
  await page.keyboard.press('Escape');await page.locator('[data-cert-panel]').waitFor({state:'hidden'})
  review.observations.push({id:'ra8-knowledge-learning',passed:true,checks:['attention includes partial/processing/deleted sources','source search and clear','questions-first validation','five learning positions fit 320px','fullscreen keyboard containment and Escape']})
 })
 await scene('ra8-review',async()=>{
  await page.setViewportSize({width:1440,height:1000});await go('/reviews');await shot('review-queue')
  await go('/reviews/ra-review-1')
  await page.getByLabel('Comments (optional)',{exact:true}).fill('Verify the justification before submission.')
  await page.getByRole('button',{name:'Edit before approving',exact:true}).click()
  await page.getByRole('textbox',{name:'Edit review output',exact:true}).fill('Budget justification checked against the source.')
  await page.getByRole('button',{name:'Inspect Proposal narrative.pdf',exact:true}).click()
  await page.getByRole('region',{name:'Source document: Proposal narrative.pdf',exact:true}).waitFor()
  await shot('review-evidence')
  await page.getByRole('button',{name:'Close source',exact:true}).click()
  if(await page.getByLabel('Comments (optional)',{exact:true}).inputValue()!=='Verify the justification before submission.')throw Error('Source inspection lost comments')
  if(await page.getByRole('textbox',{name:'Edit review output',exact:true}).inputValue()!=='Budget justification checked against the source.')throw Error('Source inspection lost edits')
  await page.getByText('Compare with original output',{exact:true}).click();await shot('review-original-comparison')
  await page.setViewportSize({width:320,height:640});await shot('review-edited-mobile')
  for(const [kind,value] of [['text','A long readiness summary. '.repeat(60)],['json',{deadline:'October 15',budget:'200',note:'Confirm the exact sponsor terms.'}],['extraction_table',[{document:'Proposal narrative.pdf',budget:'200',evidence:'The budget is 200.'},{document:'Budget justification.docx',budget:'150',evidence:'Requested direct costs are 150.'}]]]){
   await page.route('**/api/reviews/ra-review-1',r=>r.fulfill({json:{...sampleReview,artifact_kind:kind,data_for_review:{value}}}))
   await go('/reviews/ra-review-1');await shot('review-'+kind+'-mobile')
  }
  review.observations.push({id:'ra8-review',passed:true,checks:['source inspection keeps comments and edits','original comparison','text/markdown/JSON/table mobile captures']})
 })
 await scene('ra8-guidance',async()=>{
  await page.setViewportSize({width:1440,height:1000});await go('/?tab=library')
  await page.getByText('Find a tool for an RA task',{exact:true}).click()
  for(const task of ['Review requirements','Extract budget details','Summarize award conditions']){
   await page.getByRole('button',{name:task,exact:true}).click();await page.waitForTimeout(350)
   await shot('library-task-'+task.split(' ')[0].toLowerCase())
  }
  await go('/?mode=files&tab=library&workflow=workflow-1');await shot('workflow-run-guidance')
  await page.getByRole('tab',{name:'Validate',exact:true}).click()
  const help=page.getByRole('link',{name:/validation/i}).first()
  if(await help.count()===0)throw Error('Workflow validation help missing')
  for(const id of ['getting-started','project-scope','library-tools','validation','human-review','source-recovery']){
   await go('/docs#'+id)
   const target=page.locator('[id="'+id+'"]')
   if(await target.count()!==1)throw Error('Missing or ambiguous help anchor '+id)
  }
  await shot('docs-task-help')
  review.observations.push({id:'ra8-guidance',passed:true,checks:['three task discovery actions','workflow run overview','validation help link','all task help anchors resolve']})
 })
 await scene('ra8-examiner',async()=>{
  await page.route('**/api/auth/me',r=>r.fulfill({json:{id:'reviewer',user_id:'reviewer',email:'reviewer@example.test',name:'Alex Morgan',is_admin:false,is_staff:false,is_examiner:true,is_support_agent:false,is_demo_user:false,current_team:'team-1',current_team_uuid:'team-1'}}))
  const request={id:'submission-1',uuid:'submission-1',item_kind:'workflow',item_id:'workflow-1',item_name:'Review proposal requirements and budget exceptions across a multi-institution research award',status:'submitted',submitter_user_id:'author',submitter_name:'Jordan Lee',submitter:null,summary:'Proposal review',description:'Compare proposal requirements with source evidence and identify missing budget justifications.',run_instructions:'Supply one proposal PDF. Inspect every cited passage before accepting the summary.',example_inputs:['A sample proposal with a budget justification.'],expected_outputs:['A list of missing items and supporting source passages.'],known_limitations:'Unusual sponsor terms need a human check.',validation_origin:'pending_admin_validation',validation_score:null,reviewer_user_id:null,reviewer_notes:null,submitted_at:'2026-09-30T10:00:00Z',reviewed_at:null}
  let failLoad=true, decisions=0
  await page.route('**/api/verification/queue?*',r=>failLoad?r.fulfill({status:503,json:{detail:'Queue unavailable'}}):r.fulfill({json:{requests:[request]}}))
  await page.route('**/api/verification/submission-1/status',r=>{decisions++;return r.fulfill({status:503,json:{detail:'Review service unavailable'}})})
  await page.setViewportSize({width:390,height:844});await go('/verification')
  await page.getByRole('button',{name:'Retry submissions',exact:true}).waitFor();failLoad=false
  await page.getByRole('button',{name:'Retry submissions',exact:true}).click()
  await page.getByRole('button',{name:'Expand details',exact:true}).click()
  await page.getByRole('button',{name:'Review',exact:true}).click()
  const notes=page.getByRole('textbox',{name:/Review notes for/})
  await notes.fill('Add a concrete example output and cite the expected budget passage.')
  await page.getByRole('button',{name:'Send back',exact:true}).click()
  await page.getByRole('alert').filter({hasText:'Review service unavailable'}).waitFor()
  if(await notes.inputValue()!=='Add a concrete example output and cite the expected budget passage.'||decisions!==1)throw Error('Examiner failed decision lost notes or submitted twice')
  for(const width of [390,320]){
   await page.setViewportSize({width,height:844});await notes.scrollIntoViewIfNeeded();await shot('examiner-decision-'+width)
   const bounds=await notes.boundingBox();if(!bounds||bounds.x<0||bounds.x+bounds.width>width)throw Error('Examiner notes overflow')
  }
  review.observations.push({id:'ra8-examiner',passed:true,checks:['failed load is distinct from empty','retry restores submission','failed decision preserves notes','decision controls fit 320/390']})
 })
 await scene('ra8-credentials',async()=>{
  await page.setViewportSize({width:320,height:640});await go('/credentials')
  await page.getByRole('button',{name:'New credential',exact:true}).click()
  await page.getByLabel('Name',{exact:true}).fill('Institutional records test connection')
  await page.getByLabel('Header name',{exact:true}).fill('X-Api-Key')
  await page.getByLabel('Header value',{exact:true}).fill('synthetic-test-value')
  let successful=false
  await page.route('**/api/credentials/test',r=>r.fulfill({json:{ok:successful,status_code:successful?200:401,elapsed_ms:20,steps:[{step:'Test request',ok:successful,detail:successful?'Synthetic test endpoint accepted the request.':'Synthetic test endpoint rejected access. Check service permissions.'}]}}))
  await page.getByRole('button',{name:'Test',exact:true}).click()
  await page.getByRole('status').filter({hasText:'Test request failed.'}).waitFor();await shot('credential-test-failed')
  successful=true;await page.getByRole('button',{name:'Test',exact:true}).click()
  await page.getByRole('status').filter({hasText:'Connection works'}).waitFor();await shot('credential-test-success')
  await page.getByLabel('Header name',{exact:true}).fill('Authorization')
  if(await page.getByText('Connection works',{exact:false}).count())throw Error('Changed credential retained old success')
  await page.getByLabel('Type',{exact:true}).selectOption('oauth_client_credentials')
  await page.getByLabel('Private key (PEM)',{exact:true}).scrollIntoViewIfNeeded();await shot('credential-oauth-mobile')
  review.observations.push({id:'ra8-credentials',passed:true,checks:['non-delivering failed/successful test','changed configuration clears success','OAuth setup mobile']})
 })
 await scene('ra8-staff',async()=>{
  await page.route('**/api/auth/me',r=>r.fulfill({json:{id:'reviewer',user_id:'reviewer',email:'reviewer@example.test',name:'Alex Morgan',is_admin:false,is_staff:false,is_examiner:false,is_support_agent:true,is_demo_user:false,current_team:'team-1',current_team_uuid:'team-1'}}))
  const ticket={uuid:'support-1',ticket_number:1024,subject:'Unable to inspect the budget justification after returning to a shared project',status:'open',priority:'high',classification:'bug',user_id:'author',user_name:'Jordan Lee',user_email:'author@example.test',team_id:'team-1',assigned_to:'reviewer',category:null,tags:['documents'],watchers:[],watcher_ids:[],read_by:[],message_count:1,last_message_preview:'The document is still processing.',last_message_at:'2026-09-30T10:00:00Z',last_message_user_id:'author',last_message_is_support_reply:false,created_at:'2026-09-30T10:00:00Z',updated_at:'2026-09-30T10:00:00Z',closed_at:null,messages:[{uuid:'message-1',user_id:'author',user_name:'Jordan Lee',content:'I can open the project, but the budget document says it is processing. Please help me recover the source.',is_support_reply:false,is_internal_note:false,created_at:'2026-09-30T10:00:00Z',edited_at:null}],attachments:[]}
  let failLoad=true, sent=[]
  await page.route('**/api/support/tickets?*',r=>failLoad?r.fulfill({status:503,json:{detail:'Triage temporarily unavailable'}}):r.fulfill({json:{tickets:[ticket],total:1,limit:50,offset:0}}))
  await page.route('**/api/support/tickets/support-1',r=>r.fulfill({json:ticket}))
  await page.route('**/api/support/tickets/support-1/read',r=>r.fulfill({json:{ok:true}}))
  await page.route('**/api/support/tickets/support-1/messages',r=>{sent.push(r.request().postDataJSON());return r.fulfill({status:503,json:{detail:'Message service unavailable'}})})
  await page.setViewportSize({width:390,height:844});await go('/support?q=budget&priority=high')
  await page.getByRole('button',{name:'Retry tickets',exact:true}).waitFor();failLoad=false;await page.getByRole('button',{name:'Retry tickets',exact:true}).click()
  const open=page.getByRole('button',{name:'Open ticket 1024: '+ticket.subject,exact:true});await open.waitFor();await shot('staff-queue-mobile')
  await open.press('Enter');const reply=page.getByRole('textbox',{name:'Reply',exact:true});await reply.fill('I am checking the source processing status.')
  await page.getByRole('button',{name:'Back to tickets',exact:true}).click();await open.click()
  if(await reply.inputValue()!=='I am checking the source processing status.')throw Error('Staff queue return lost reply draft')
  if(!page.url().includes('q=budget')||!page.url().includes('priority=high'))throw Error('Staff ticket entry lost filters')
  await page.getByRole('button',{name:'Internal note',exact:true}).click()
  const note=page.getByRole('textbox',{name:'Internal note',exact:true});await note.fill('Internal: check the processing job before replying.')
  await page.getByRole('button',{name:'Add Note',exact:true}).click();await page.getByText('Failed to send message',{exact:true}).waitFor()
  if(sent.length!==1||sent[0].is_internal_note!==true||await note.inputValue()!=='Internal: check the processing job before replying.')throw Error('Failed internal note lost its audience or text')
  await page.getByRole('button',{name:'Back to tickets',exact:true}).click();await open.click()
  if(await note.inputValue()!=='Internal: check the processing job before replying.')throw Error('Internal draft did not survive queue return')
  await page.setViewportSize({width:320,height:640});await note.scrollIntoViewIfNeeded();await shot('staff-internal-draft-mobile')
  review.observations.push({id:'ra8-staff',passed:true,checks:['failed queue load retry','filters retained in ticket','reply and internal-note drafts survive queue return','failed send preserves audience and text']})
 })
 await scene('ra8-entry',async()=>{
  await page.route('**/api/auth/me',r=>r.fulfill({status:401,json:{detail:'Not signed in'}}))
  await page.setViewportSize({width:390,height:844});await go('/landing?register=1')
  await page.getByRole('textbox',{name:'Email address',exact:true}).waitFor()
  await shot('entry-register-deep-link')
  await page.keyboard.press('Escape');await page.getByRole('dialog').waitFor({state:'hidden'})
  const signIn=page.getByRole('button',{name:'Sign in',exact:true})
  await signIn.press('Enter');await page.getByRole('dialog').waitFor()
  await page.keyboard.press('Tab')
  if(!await page.getByRole('dialog').evaluate(e=>e.contains(document.activeElement)))throw Error('Sign-in focus escaped')
  await page.keyboard.press('Escape');await page.waitForTimeout(100)
  if(!await signIn.evaluate(e=>e===document.activeElement))throw Error('Sign-in did not return focus')
  await go('/landing');await shot('entry-mobile');await page.screenshot({path:review.out+'/entry-mobile.png',fullPage:false})
  for(const width of [320,390]) {
   await page.setViewportSize({width,height:844})
   const logo=await page.locator('header img').boundingBox(), login=await signIn.boundingBox()
   if(!logo||!login||logo.x+logo.width>login.x)throw Error(`Landing logo overlaps sign-in at ${width}`)
   await shot(`entry-mobile-${width}`)
   await page.screenshot({path:review.out+`/entry-mobile-${width}.png`,fullPage:false})
  }
  review.observations.push({id:'ra8-entry',passed:true,checks:['registration deep link opens form','mobile sign-in visible','dialog focus containment','Escape and focus return']})
 })

 await scene('public-entry',async()=>{await page.route('**/api/auth/me',r=>r.fulfill({status:401,json:{detail:'Not signed in'}}));await go('/login');await shot('sign-in');await go('/landing');await shot('landing');await page.screenshot({path:review.out+'/landing.png',fullPage:false})})
}finally{await review.flush();await review.browser.close();console.log(JSON.stringify({captures:review.captures.length,unmatched:[...review.unmatched],errors:review.errors,observations:review.observations},null,2))}
