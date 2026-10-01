import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page}=review
page.setDefaultTimeout(30000)
const stamp='2026-09-30T10:00:00Z',name='Sponsor eligibility and budget review — institutional research administration'
let failures=new Set(),acknowledged=false,starts=0
const writes=[]
const summary={avg_score:81,total_runs:24,items_validated:6,total_verified:8,items_below_threshold:2}
const qualityItem={item_kind:'workflow',item_id:'wf-1',display_name:name,quality_score:72,quality_tier:'good',last_validated_at:stamp,validation_run_count:6,trend:'down',stale:true}
const alert={uuid:'alert-1',alert_type:'regression',item_kind:'workflow',item_id:'wf-1',item_name:name,severity:'warning',message:'The latest validation score fell after a model change. Inspect the failed cases.',previous_score:91,current_score:72,acknowledged:false,created_at:stamp}
const suite={run_uuid:'suite-1',status:'completed',model:'research-model',total_items:2,completed_items:2,succeeded:1,failed:1,mean_score:72,error:null,started_at:stamp,finished_at:stamp,results:[{item_id:'wf-1',kind:'workflow',name,score:72,grade:'B',prev_score:91,delta:-19,status:'ok'},{item_id:'ext-1',kind:'extraction',name:'Award dates and reporting obligations',score:null,grade:null,prev_score:85,delta:null,status:'failed'}]}
const level={name:'restricted',label:'Restricted institutional data',color:'#facc15',severity:3}
const config={enabled:true,auto_classify_on_upload:true,default_classification:'restricted',levels:[level]}
const optimizerRun={surface:'workflow',run_uuid:'opt-1',item_id:'wf-1',item_name:name,item_deleted:false,user_id:'user-1',user_email:'alexandra.montgomery@institution.example.test',status:'failed',trigger:'baseline_drift',started_at:stamp,completed_at:stamp,baseline_score:.81,optimized_score:null,tied_with_baseline:false,error_code:'model_unavailable',error_message:'Configured research model is unavailable. Ask the platform administrator to check the provider.',is_live:false,dismissed_at:null}
const fixed={
 '/api/auth/me':{id:'reviewer',user_id:'reviewer',email:'reviewer@example.test',name:'Alex Morgan',is_admin:true,is_staff:true,is_examiner:false,is_support_agent:false,is_demo_user:false,current_team:'team-1',current_team_uuid:'team-1',sso_provider:null},
 '/api/auth/config':{auth_methods:['password'],oauth_providers:[],trial_system_enabled:false},'/api/admin/system/version':{current:'5.0.0',update_available:false},'/api/admin/catalog/status':{update_available:false},'/api/admin/telemetry/optin':{show_banner:false},
 '/api/admin/quality/summary':summary,
 '/api/admin/quality/timeline':{timeline:[{date:'2026-09-29',avg_score:91,run_count:4,items_validated:2},{date:'2026-09-30',avg_score:72,run_count:2,items_validated:1}]},
 '/api/admin/quality/items':{items:[qualityItem]},
 '/api/admin/quality/items/workflow/wf-1':{item_kind:'workflow',item_id:'wf-1',history:[{uuid:'v1',score:72,accuracy:70,consistency:74,grade:'B',model:'research-model',created_at:stamp}],model_comparison:[{model:'research-model',avg_score:72,run_count:6}]},
 '/api/admin/quality/by-model':{models:[{model:'research-model',run_count:6,items_validated:2,avg_score:72,kinds:{workflow:{run_count:6,avg_score:72}},last_run_at:stamp}]},
 '/api/admin/quality/judge-calibration':{surfaces:[{surface:'workflow',published_floor:.8,min_accuracy:.85,fixture_path:null,models:[{judge_model:'research-model',calibrated:false,kappa:null,accuracy:null,measured_at:null,n_runs:0,drift_detectable:false}],measured_models:[],ledger_entries:0,drift_detectable:false}],available_models:['research-model']},
 '/api/admin/quality/regression-suite/runs':{runs:[suite,{...suite,run_uuid:'suite-2',model:'earlier-model',mean_score:91}]},
 '/api/admin/quality/regression-suite/runs/suite-1':suite,
 '/api/admin/quality/regression-suite/runs/suite-2':{...suite,run_uuid:'suite-2',model:'earlier-model',mean_score:91,results:suite.results.map(r=>({...r,score:91}))},
 '/api/admin/quality/regression-suite/runs/accepted-run':{...suite,run_uuid:'accepted-run'},
 '/api/admin/classification/dashboard':{config,counts:{restricted:16,unclassified:2},recent_classifications:[{uuid:'doc-1',title:'Sponsored research agreement — multi-institution coastal resilience study',classification:'restricted',confidence:.82,classified_at:stamp,classified_by:'research-model'}]},
 '/api/admin/retention/dashboard':{classification_config:config,retention_config:{enabled:false,policies:{restricted:{retention_days:2555,soft_delete_grace_days:30}},activity_retention_days:365,chat_retention_days:180,workflow_result_retention_days:730,activity_stale_threshold_minutes:60},document_counts:{restricted:16,unclassified:2},pending_deletions:2,soft_deleted:1,retention_holds:3},
}
await page.route('**/api/**',async r=>{
 const url=new URL(r.request().url()),p=url.pathname.replace(/\/$/,'')
 if(failures.has(p))return r.fulfill({status:503,json:{detail:'Records temporarily unavailable. Retry this request.'}})
 if(p==='/api/admin/quality/alerts')return r.fulfill({json:{alerts:acknowledged?[]:[alert]}})
 if(p==='/api/admin/quality/alerts/alert-1/acknowledge'){writes.push(p);acknowledged=true;return r.fulfill({json:{ok:true}})}
 if(p==='/api/admin/quality/regression-suite'){writes.push(p);starts++;return r.fulfill({json:{run_uuid:'accepted-run',status:'running'}})}
 if(p==='/api/admin/optimizer/activity'){const runs=url.searchParams.get('status')==='completed'?[]:[optimizerRun];return r.fulfill({json:{runs,summary:{window_days:14,total:runs.length,by_status:{failed:1},by_surface:{workflow:1},auto_triggered:1,user_launched:0,failed:runs.length,applied:0,dismissed:0,pending_review:0,tokens_used:1200,failure_reasons:runs.length?[{reason:optimizerRun.error_message,count:1}]:[],truncated:false}}})}
 if(p==='/api/audit')return r.fulfill({json:{entries:[{uuid:'event-1',timestamp:stamp,actor_user_id:'alexandra.montgomery@institution.example.test',actor_type:'user',action:'workflow.run',resource_type:'workflow',resource_id:'wf-1',resource_name:name,team_id:'team-1',organization_id:null,detail:{document:'award-agreement-2027.pdf',status:'failed',reason:'The provider could not complete validation. Existing saved results remain available.',complete_detail_marker:'This final field must be visible after expanding the complete event.'},ip_address:null}],total:1,skip:0,limit:25}})
 if(p in fixed)return r.fulfill({json:fixed[p]})
 return r.fallback()
})
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id+': page overflow');const nested=await page.locator('.section-page__content').evaluate(root=>[...root.querySelectorAll('div,p,fieldset')].filter(e=>e.clientWidth>50&&e.clientHeight>0&&e.scrollWidth>e.clientWidth+3&&getComputedStyle(e).overflowX==='visible'&&!e.closest('.admin-table-region')).map(e=>({class:e.className,width:e.clientWidth,content:e.scrollWidth,text:e.textContent?.slice(0,60)})));assert.deepEqual(nested,[],id+': nested overflow');assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': accessibility');console.log('Captured '+id)}
async function go(tab){await page.goto(review.baseURL+'/admin?tab='+tab)}
try{
 for(const width of [320,1440]){
  await page.setViewportSize({width,height:width===320?740:1000});acknowledged=false
  failures=new Set(['/api/admin/quality/summary']);await go('quality');await page.getByRole('button',{name:'Retry quality data'}).waitFor();failures.clear();await page.getByRole('button',{name:'Retry quality data'}).click();await page.getByRole('button',{name:'View quality for '+name}).waitFor();await shot('admin-quality-'+width)
  failures.add('/api/admin/quality/items/workflow/wf-1');const open=page.getByRole('button',{name:'View quality for '+name});await open.focus();await page.keyboard.press('Enter');await page.getByRole('button',{name:'Retry item quality'}).waitFor();failures.clear();await page.getByRole('button',{name:'Retry item quality'}).click();await page.getByText('Score Timeline',{exact:true}).waitFor();await shot('admin-quality-item-'+width)
  await page.getByRole('button',{name:/research-model 72%/}).click();await page.getByLabel('Compare with').selectOption('suite-2');await page.getByText(/^Mean: research-model/).waitFor();await shot('admin-quality-comparison-'+width)
  failures.add('/api/admin/quality/alerts/alert-1/acknowledge');await page.getByRole('button',{name:'Acknowledge alert for '+name}).click();await page.getByText(/Failed to acknowledge alert:/).waitFor();assert.equal(acknowledged,false);failures.clear();await page.getByRole('button',{name:'Acknowledge alert for '+name}).click();await page.getByRole('button',{name:'Acknowledge alert for '+name}).waitFor({state:'hidden'})
  failures.add('/api/admin/quality/regression-suite/runs/accepted-run');const before=starts;await page.getByRole('button',{name:'Run Regression Suite',exact:true}).click();await page.getByRole('button',{name:'Retry run status'}).waitFor();await shot('admin-quality-status-retry-'+width);failures.clear();await page.getByRole('button',{name:'Retry run status'}).click();await page.getByText('Catalog mean:',{exact:false}).waitFor();assert.equal(starts,before+1)
  failures.add('/api/admin/optimizer/activity');await go('optimizer');await page.getByRole('button',{name:'Retry optimizer activity'}).waitFor();failures.clear();await page.getByRole('button',{name:'Retry optimizer activity'}).click();await page.getByText(name,{exact:false}).waitFor();await shot('admin-optimizer-'+width);await page.getByRole('combobox',{name:'Status',exact:true}).selectOption('completed');await page.getByText('No optimizer runs in this window.').waitFor();await shot('admin-optimizer-filtered-'+width)
  failures.add('/api/admin/classification/dashboard');await go('compliance');await page.getByRole('button',{name:'Retry compliance records'}).waitFor();failures.clear();await page.getByRole('button',{name:'Retry compliance records'}).click();await page.getByText('Recent classifications',{exact:true}).waitFor();await shot('admin-compliance-'+width)
  failures.add('/api/audit');await go('audit');await page.getByRole('button',{name:'Retry audit log'}).waitFor();failures.clear();await page.getByRole('button',{name:'Retry audit log'}).click();await page.getByText(name,{exact:false}).waitFor();await page.getByRole('textbox',{name:'Filter audit actions'}).fill('workflow.run');await page.getByRole('combobox',{name:'Filter audit resources'}).selectOption('workflow');await page.waitForTimeout(500);await page.getByText('View event details',{exact:true}).click();await page.getByText(/This final field must be visible/).waitFor();assert.ok((await page.getByRole('link',{name:'Export CSV'}).getAttribute('href')).includes('action=workflow.run&resource_type=workflow'));await shot('admin-audit-detail-'+width)
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push({evidence:'Local synthetic Admin quality/governance reads, failed-read recovery, keyboard item detail, comparison, failed acknowledgement, accepted regression status retry, optimizer filters, retention policy and full audit event. No backend/model execution or production changes.',writes})
}catch(error){await review.capture('admin-governance-blocked',String(error));throw error}finally{await review.flush();await review.browser.close()}
