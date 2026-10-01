import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { workflow, stamp } from './fixtures.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL}),{page}=review
page.setDefaultTimeout(30000)
const zoom=process.env.REVIEW_BROWSER_ZOOM==='2'
const sample={uuid:'review-1',workflow_id:'workflow-1',workflow_name:'Proposal readiness review',step_name:'Confirm sponsor eligibility and unresolved budget exceptions',status:'pending',assigned_to_user_ids:['reviewer'],assignee_role:'specific_users',requester_user_id:'colleague',team_id:'team-1',created_at:stamp,decision_at:null,step_index:1,review_instructions:'Check the missing budget justification and confirm the sponsor deadline before approving.',artifact_kind:'markdown',data_for_review:{value:'## Review findings\n\nBudget justification is missing.\n\n| Requirement | Finding |\n|---|---|\n| Deadline | Confirm with sponsor notice |\n| Budget exception | Needs PI explanation |'},edited_artifact:null,timeout_action:'none',reviewer_comments:'',source_docs:[{uuid:'doc-0',title:'Proposal narrative.pdf'}]}
const stats={conversations:42,search_runs:28,workflows_started:16,workflows_completed:14,workflows_failed:2,tokens_in:280000,tokens_out:42000,active_users:5,active_teams:1}
const fixed={
 '/api/extractions/test-cases':[],'/api/extractions/search-sets/item-1/quality-history':{runs:[]},'/api/extractions/search-sets/item-1/history':{runs:[]},
 '/api/auth/config':{auth_methods:['password'],oauth_providers:[],trial_system_enabled:false},
 '/api/auth/email-preferences':{onboarding:true,nudges:true,announcements:true},'/api/auth/api-token/status':{has_token:false,created_at:null},'/api/chat/memory':{extractions:[],workflows:[],kbs:[]},
 '/api/teams/team-1/members':[{user_id:'reviewer',name:'Alex Morgan',email:'reviewer@example.test',role:'owner'},{user_id:'colleague',name:'Jordan Research Administration Colleague',email:'jordan@example.test',role:'member'}],'/api/teams/team-1/invites':[],'/api/teams/team-1/join-links':[],
 '/api/credentials':[], '/api/reviews':{reviews:[sample]},'/api/reviews/team':{reviews:[sample]},'/api/reviews/review-1':sample,
 '/api/support/tickets':{tickets:[],total:0,limit:50,offset:0},'/api/support/contacts':{contacts:[]},
 '/api/verification/mine':{requests:[]},
 '/api/admin/usage':stats,'/api/admin/usage/timeseries':{days:[],previous_period:stats},'/api/admin/system/version':{current:'5.0.0',update_available:false},
 '/api/optimizer/inbox':{items:[],counts:{total:0,needs_review:0,failed:0,in_flight:0,applied:0,no_change:0,dismissed:0,pending_review:0},lookback_days:30},
 '/api/workflows/workflow-1':{...workflow,steps:[{id:'review',name:'Review evidence',data:{},is_output:true,tasks:[{id:'prompt',name:'Prompt',data:{prompt:'Summarize proposal requirements and cite the source.'}}]}]},
 '/api/extractions/search-sets/item-1':{id:'item-1',uuid:'item-1',title:'Budget compliance extraction',set_type:'extraction',user_id:'reviewer',extraction_config:{},created_at:stamp,updated_at:stamp},
 '/api/extractions/search-sets/item-1/items':[{id:'field-1',uuid:'field-1',search_set_uuid:'item-1',searchphrase:'Budget',title:'Budget',searchtype:'text',enum_values:[],is_optional:false,description:'The total budget'}],
 '/api/extractions/search-sets/item-1/quality-status':{status:'unvalidated'},'/api/extractions/search-sets/item-1/quality-sparkline':{scores:[]},'/api/extractions/search-sets/item-1/cross-field-rules':{rules:[]},
}
await page.route('**/api/**',r=>{const p=new URL(r.request().url()).pathname.replace(/\/$/,'');return p in fixed?r.fulfill({json:fixed[p]}):r.fallback()})
async function shot(id){
 await review.capture(id);await page.screenshot({path:resolve(review.out,id+'.png'),fullPage:false});const capture=review.captures.at(-1)
 assert.ok(capture.pageWidth<=capture.viewport.width,id+': page overflow')
 if(zoom){assert.equal(capture.browserZoom,2);assert.equal(capture.visualViewportScale,1);assert.equal(capture.viewport.width,Math.round(page.viewportSize().width/2))}
 assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': accessibility')
 // Deliberate data/code scrollers are checked separately from clipped ordinary controls.
 const clipped=await page.locator('main input:not([type=hidden]),main select,main textarea,main button').evaluateAll(elements=>elements.filter(e=>{const r=e.getBoundingClientRect();if(!e.checkVisibility({checkVisibilityCSS:true})||!r.width||r.bottom<0||r.top>innerHeight||e.closest('[inert]'))return false;let p=e.parentElement;while(p&&p!==document.body){const s=getComputedStyle(p);if(['auto','scroll'].includes(s.overflowX)&&p.scrollWidth>p.clientWidth+2&&p.getAttribute('role')==='region'&&p.getAttribute('aria-label'))return false;p=p.parentElement}return r.left < -2 || r.right > innerWidth+2}).map(e=>e.getAttribute('aria-label')||e.textContent.trim().slice(0,80)))
 assert.deepEqual(clipped,[],id+': clipped controls');console.log('Captured '+id)
}
const scenes=[['home','/?mode=chat'],['files','/?mode=files'],['projects','/?mode=projects'],['library','/?tab=library'],['workflow','/?workflow=workflow-1'],['extraction','/?extraction=item-1'],['automation','/?mode=automations&automation=auto-1'],['knowledge','/?mode=knowledge&kb=kb-1'],['reviews','/reviews'],['review-detail','/reviews/review-1'],['account','/account'],['teams','/teams'],['credentials','/credentials'],['support','/support'],['learning','/certification'],['tuning','/tuning'],['sharing','/verification'],['admin','/admin'],['docs','/docs']]
try{
 const widths=process.env.REVIEW_WIDTHS?.split(',').map(Number)||(zoom?[1440,780]:[320,390,768,1024,1440])
 for(const width of widths){
  await page.setViewportSize({width,height:zoom?(width===780?1136:1000):(width<400?568:800)})
  for(const [id,path] of scenes){await page.goto(review.baseURL+path);await page.getByRole('main').first().waitFor();if(zoom)assert.equal(await review.setBrowserZoom(),2);await page.waitForTimeout(450);await shot('layout-'+id+'-'+width)}
  await page.goto(review.baseURL+'/?workflow=workflow-1');if(zoom)await review.setBrowserZoom();await page.getByRole('button',{name:'Open step: Review evidence',exact:true}).click();await shot('layout-step-editor-'+width);const editor=page.getByRole('region',{name:'Edit step: Review evidence',exact:true});await editor.getByRole('tab',{name:'Output',exact:true}).click();await editor.getByRole('checkbox',{name:'Mark step as workflow output'}).scrollIntoViewIfNeeded();await editor.getByRole('tab',{name:'Basic Setup',exact:true}).click();await editor.getByRole('button',{name:'Edit task: Prompt',exact:true}).click();await page.keyboard.press('Escape');await editor.getByRole('button',{name:'DONE',exact:true}).click()
  await page.goto(review.baseURL+'/reviews/review-1');if(zoom)await review.setBrowserZoom();await page.getByRole('button',{name:'Edit before approving',exact:true}).click();await shot('layout-review-edit-'+width)
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[]);review.observations.push(zoom?'Actual chrome.tabs.setZoom(2), confirmed by API value, halved CSS viewport and unchanged visualViewport.scale. Synthetic core/supporting surface and editor checks, reduced motion enabled.':'Five-width ordinary control and page containment, named data scroll regions and axe checks. Synthetic review fixtures; no screen reader or real user observations.')
}catch(error){await review.capture('enlarged-layouts-blocked',String(error));throw error}finally{await review.flush();await review.browser.close()}
