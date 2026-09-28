// Synthetic local data only. No requests are allowed to reach a backend.
export const stamp = '2026-09-24T16:00:00Z'
export const docs = ['Proposal narrative.pdf', 'Budget justification.docx', 'Award terms – draft.pdf'].map((title, i) => ({ id: `doc-${i}`, uuid: `doc-${i}`, title, extension: i === 1 ? 'docx' : 'pdf', processing: false, valid: true, task_status: 'complete', folder: null, created_at: stamp, updated_at: stamp, token_count: 3400 + i * 1200, num_pages: 8 + i, chromadb_ready: true, chunk_count: 24 }))
export const folders = [{id:'folder-1',uuid:'folder-1',title:'FY2027 proposals',path:'FY2027 proposals',parent_id:'',is_shared_team_root:false}]
export const kb = {uuid:'kb-1', title:'Research administration policies',description:'Institutional guidance for proposal review and award management.',status:'ready',shared_with_team:false,team_owned:false,verified:false,organization_ids:[],tags:['Research','Policies'],team_id:null,total_sources:3,sources_ready:2,sources_failed:1,total_chunks:84,created_at:stamp,updated_at:stamp,user_id:'reviewer',scope:'mine',can_manage:true,last_validation_score:null,last_validated_at:null,sources:[{uuid:'source-1',source_type:'document',document_uuid:'doc-0',document_title:docs[0].title,status:'ready',chunk_count:42,created_at:stamp},{uuid:'source-2',source_type:'url',url:'https://example.org/policies',url_title:'Institutional research policies',status:'ready',chunk_count:42,created_at:stamp},{uuid:'source-3',source_type:'url',url:'https://example.org/archived',status:'error',error_message:'The source could not be retrieved. HTTP 404.',chunk_count:0,created_at:stamp}]}
export const project = {uuid:'project-1',title:'Community resilience proposal',description:'Prepare the proposal, review requirements, and track supporting documents.',owner_user_id:'reviewer',team_id:null,state:'active',root_folder_uuid:'folder-1',kb_uuid:'kb-1',created_at:stamp,updated_at:stamp,role:'owner',capabilities:{files:{count:3,folders:1},knowledge:{ready:true,documents:3},workflows:{count:1},extractions:{count:1},automations:{count:1},external_kbs:{count:0},members:{count:2}}}
export const workflow = {id:'workflow-1',uuid:'workflow-1',name:'Proposal readiness review',description:'Review requirements and identify missing information.',steps:[],verified:false,user_id:'reviewer',created_at:stamp,updated_at:stamp}
export const automation = {last_event_status:'completed',last_event_at:stamp,id:'auto-1',name:'Review incoming proposals',description:'Review new files in the proposal folder.',enabled:true,trigger_type:'folder_watch',trigger_config:{folder_id:'folder-1',file_types:['pdf','docx']},action_type:'workflow',action_id:'workflow-1',action_name:workflow.name,user_id:'reviewer',team_id:null,shared_with_team:false,output_config:{},created_at:stamp,updated_at:stamp,can_manage:true}
export const items = ['Proposal readiness review','Budget compliance extraction','Summarize award conditions'].map((name,i)=>({id:`item-${i}`,item_id:i===0?'workflow-1':`extraction-${i}`,item_uuid:`item-${i}`,kind:i===0?'workflow':'search_set',name,description:'Identify requirements, supporting evidence, and next steps.',set_type:i===1?'extraction':i===2?'prompt':null,tags:['Research'],note:null,folder:null,pinned:i===0,favorited:i===1,verified:false,added_by_user_id:'reviewer',created_at:stamp,last_used_at:stamp,quality_score:i===0?86:null,quality_tier:i===0?'good':null}))
export const catalog = items.map((item,i)=>({...item,source_uuid:item.item_id,verified:true,display_name:item.name,markdown:'A reusable starting point for research administration. Review results before use.',organization_ids:[],quality_grade:i===0?'B':null,last_validated_at:i===0?stamp:null,validation_run_count:i===0?4:0,test_case_count:i===0?12:0,adoption_count:16-i*5}))
export const queries = ['When is the proposal due?','What must the budget justification include?','Who approves the final submission?'].map((query,i)=>({uuid:`query-${i}`,query,expected_source_labels:['Proposal narrative.pdf'],expected_answer_contains:null,expected_answer:['October 15','An explanation of requested costs','The research office'][i],category:'factual',notes:null,external_id:null,auto_generated:false,source_chunk_ids:[],last_judged_score:null,last_judged_at:null,created_at:stamp,updated_at:stamp}))
export const validationResult={kb_uuid:'kb-1',kb_title:kb.title,raw_score:82,score:66,quality_tier:'fair',num_test_queries:3,num_sources:3,mode:'judge+baseline',judge_model:'Review model',answer_model:'Review model',source_health:{total:3,healthy:2,unhealthy:1,ratio:2/3,details:[]},chunk_coverage:{total:3,with_chunks:2,without_chunks:1,ratio:2/3,total_chunks:84},retrieval_precision:{total_queries:3,avg_precision:0.85,avg_judge_score:0.9,avg_baseline_score:0.4,avg_lift:0.5,num_queries_judged:3,num_queries_baselined:3,details:queries.map(q=>({query_uuid:q.uuid,query:q.query,category:q.category,precision:0.85,retrieved_sources:['Proposal narrative.pdf'],expected_sources:['Proposal narrative.pdf'],expected_answer:q.expected_answer,actual_answer:q.expected_answer,baseline_answer:'This information is not available.',judge:{score:0.9,verdict:'PASS',confidence:0.9,reasoning:'Matches the expected answer in the review fixture.',evidence:q.expected_answer,missing_facts:[],hallucinated_facts:[]},lift:0.5}))},score_breakdown:{raw_score:82,final_score:66,sample_size_factor:0.8,sample_size_penalty:16,num_test_cases:3,num_runs:1,test_cases_needed:7,runs_needed:2}};

export const optimization = {uuid:'opt-review',kb_uuid:'kb-1',status:'completed',phase:'completed',progress_message:'Synthetic comparison complete',current_trial_index:1,total_trials_planned:1,best_score_so_far:0.8,best_config_so_far:null,token_budget:500000,tokens_used:4200,estimated_cost_usd:null,actual_cost_usd:null,baseline_no_kb_score:0.4,baseline_default_score:0.65,optimized_score:0.8,judge_variance:0.01,judge_model:'Review model',default_config:{k:4,model:'review-model',prompt_variant:'strict',query_rewriting:false,source_label_visibility:true},best_config:{k:8,model:'review-model',prompt_variant:'strict',query_rewriting:false,source_label_visibility:true},trials:[],data_source_suggestions:[],options:{apply_on_finish:false},error_message:null,started_at:stamp,completed_at:stamp,cancel_requested:false,applied_at:null,reverted_at:null,apply_preview:{total:2,will_change:2,improvements:1,regressions:1,significant_regressions:1,net_delta:0.15,noise_sigma:0.01,items:[{item_id:'query-1',label:'When is the proposal due?',baseline:0.9,winner:0.7,delta:-0.2,within_noise:false,is_regression:true,significant:true},{item_id:'query-2',label:'What does the budget need?',baseline:0.4,winner:0.9,delta:0.5,within_noise:false,is_regression:false,significant:true}]}};

export async function installFixtures(context, state = {empty:false, first:false}, unmatched = new Set()) {
 await context.route('**/api/**', async route => {
  const req=route.request(), url=new URL(req.url()), p=url.pathname.replace(/\/$/,'');
  if(!p.startsWith('/api/')) return route.continue();
  let data;
  const list = value => state.empty ? [] : value;
  if(p==='/api/auth/me') data={id:'reviewer',user_id:'reviewer',email:'reviewer@example.test',name:'Alex Morgan',is_admin:false,is_staff:false,is_examiner:false,is_support_agent:false,is_demo_user:false,current_team:'team-1',current_team_uuid:'team-1',sso_provider:null};
  else if(p==='/api/teams') data=[{id:'team-1',uuid:'team-1',name:'Research office',owner_user_id:'reviewer',role:'owner'}];
  else if(p==='/api/config/theme') data={highlight_color:'#eab308',ui_radius:'4px',org_name:'Vandalizer',app_name:'Vandalizer',logo_data_url:'',icon_data_url:''};
  else if(p==='/api/config/version') data={version:'5.0.0',environment:'development',deployment_label:'Visual review'};
  else if(p==='/api/config/features') data={m365_enabled:false};
  else if(p==='/api/reviews/count') data={count:0};
  else if(p==='/api/certification/progress') data={id:'cert-review',user_id:'reviewer',modules:{},total_xp:0,level:'novice',certified:false,certified_at:null,last_activity_date:null};
  else if(p==='/api/extractions/search-sets') data=[];
  else if(p==='/api/config/models') data=[{name:'Review model',tag:'review-model',context_window:128000,provider:'local'}];
  else if(p==='/api/config/user') data={model:'review-model',temperature:0.2,top_p:1,available_models:[{name:'Review model',tag:'review-model',context_window:128000}]};
  else if(p==='/api/config/onboarding-status') data={has_documents:!state.first,has_workflows:!state.first,has_extraction_sets:!state.first,has_knowledge_base:!state.first,has_conversations:!state.first,first_session_completed:!state.first,has_ready_knowledge_base:!state.first,suggestion_pills:['Summarize my documents','Review proposal requirements','Ask a knowledge base','Build a reusable workflow'],recent_activity:[],active_alerts:[],maturity_stage:state.first?'newcomer':'practitioner',unprocessed_doc_count:0};
  else if(p==='/api/documents/list') data={folders:list(folders),documents:list((state.uploaded?[...docs,{...docs[0],uuid:'doc-upload',id:'doc-upload',title:'Review sample.txt',extension:'txt'}]:docs).filter(d=>!state.deletedDocs?.includes(d.uuid)))};
  else if(p==='/api/documents/search') data={items:list(docs),total:state.empty?0:docs.length};
  else if(p==='/api/documents/titles') data={documents:docs,folders};
  else if(p==='/api/documents/poll_status') data={status:'SUCCESS',status_messages:[],complete:true,raw_text:'Synthetic review document. Proposal due October 15. Budget requires justification.',valid:true,processing:false,title:'Review sample.txt'};
  else if(/^\/api\/files\/doc-\d+\/usage$/.test(p)) {const doc=docs.find(d=>d.uuid===p.split('/')[3]);data={document:{uuid:doc.uuid,title:doc.title},folder:{path:[],team_id:null},knowledge_bases:[],extractions:[],workflows:[],total:0};}
  else if(/^\/api\/files\/doc-\d+$/.test(p)&&req.method()==='DELETE') {const id=p.split('/')[3];(state.deleteRequests??=[]).push(id);if(state.failDelete===id)return route.fulfill({status:503,json:{detail:'Deletion temporarily unavailable.'}});(state.deletedDocs??=[]).push(id);data={ok:true};}
  else if(p==='/api/files/upload') {if(state.uploadError)return route.fulfill({status:413,json:{detail:'This file exceeds the upload limit.'}});state.uploaded=true;data={complete:true,uuid:'doc-upload',title:'Review sample.txt',status:'success'}}
  else if(p==='/api/files/upload-policy') data={extensions:['pdf','doc','docx','xls','xlsx','csv','txt','md'],max_size_bytes:500*1024*1024};
  else if(p==='/api/folders/all') data=folders;
  else if(p.startsWith('/api/folders/breadcrumbs/')) data=[];
  else if(p==='/api/projects') data=list([project,{...project,uuid:'project-2',title:'Watershed monitoring renewal',state:'draft'}]);
  else if(p.endsWith('/pins')) data=[];
  else if(p==='/api/projects/project-1') data=project;
  else if(p==='/api/projects/project-1/documents') data={document_uuids:docs.map(d=>d.uuid)};
  else if(p==='/api/knowledge/list') data=list([kb]);
  else if(p==='/api/knowledge/list/v2') data={items:list([kb]),total:state.empty?0:1};
  else if(p==='/api/knowledge/kb-1') { state.kbDetailReads=(state.kbDetailReads||0)+1;data={...kb,...(state.optimization?{last_validation_score:0.8,last_validation_metric:'composite_quality',last_validation_config_state:state.optimizationReverted?'reverted':state.optimizationApplied?'applied':'proposed',last_validated_at:stamp}:state.validated?{last_validation_score:0.9,last_validation_baseline_score:0.4,last_validation_lift:0.5,last_validated_at:stamp}:{})}; }
  else if(p.endsWith('/source-health')) data={total:3,healthy:2,unhealthy:1,ratio:2/3,details:kb.sources.map(s=>({...s,name:s.document_title||s.url,error:s.error_message}))};
  else if(p.endsWith('/validation-grader')) data={model:'Review model',configured:true,fallback:null};
  else if(p.endsWith('/test-queries')) data={test_queries:state.validationQueries?queries:[]};
  else if(p.endsWith('/baseline-probe')) data={no_kb_score:0.4,num_queries_judged:3,sample_query_ids:queries.map(q=>q.uuid),tokens_used:1800,duration_ms:900};
  else if(p.endsWith('/validate')) {state.validated=true;state.validationTaskId=route.request().postDataJSON()?.request_id || 'review-validation';data={task_id:state.validationTaskId,status:'queued'}}
  else if(p.endsWith('/validation-tasks/active')) data={task:null};
  else if(p.includes('/validation-tasks/')) data={task_id:state.validationTaskId,status:'completed',run_uuid:'validation-1',result:validationResult};
  else if(p.endsWith('/quality')) data={history:state.validated?[{uuid:'validation-1',score:66,quality_tier:'fair',raw_score:82,judge_model:'Review model',num_queries_judged:3,num_test_queries:3,mode:'judge+baseline',created_at:stamp,source:'manual',result_snapshot:validationResult}]:[],contract:{}};
  else if(p.endsWith('/optimize/active')) data={run:state.optimization?{...optimization,applied_at:state.optimizationApplied?stamp:null,reverted_at:state.optimizationReverted?stamp:null}:null};
  else if(p.endsWith('/optimize/opt-review/apply')) {state.applyCalls=(state.applyCalls||0)+1;if(state.failApply)return route.fulfill({status:503,json:{detail:'Could not apply settings. Please retry.'}});state.optimizationApplied=true;state.optimizationReverted=false;data={ok:true,applied_config:optimization.best_config,previous_override:null,applied_at:stamp};}
  else if(p.endsWith('/optimize/opt-review/revert')) {state.revertCalls=(state.revertCalls||0)+1;state.optimizationReverted=true;data={ok:true,restored_config:null,reverted_at:stamp};}
  else if(p.endsWith('/optimize/opt-review')) data={...optimization,applied_at:state.optimizationApplied?stamp:null,reverted_at:state.optimizationReverted?stamp:null};
  else if(p.endsWith('/optimize')) data={items:[],skip:0,limit:20,count:0};
  else if(p.endsWith('/optimize/history')) data={runs:[],total:0};
  else if(p.endsWith('/feedback-impact')) data={applied_at:null,thumbs_up_rate_before:null,thumbs_up_rate_after:null};
  else if(p==='/api/automations') data=list([automation,{...automation,id:'auto-2',last_event_status:null,last_event_at:null,name:'Weekly award digest',enabled:false,trigger_type:'schedule',trigger_config:{frequency:'weekly',time:'09:00',weekday:0,timezone:'America/Los_Angeles'}}]);
  else if(p==='/api/automations/active') data={active_automation_ids:[],recently_completed:[]};
  else if(p==='/api/automations/auto-1') {
   if(req.method()==='PATCH') { (state.automationWrites??=[]).push(req.postDataJSON()); if(state.automationSaveDelay)await new Promise(resolve=>setTimeout(resolve,state.automationSaveDelay));if(state.failAutomationSave)return route.fulfill({status:503,json:{detail:'Save temporarily unavailable.'}});state.savedAutomation={...(state.savedAutomation||automation),...req.postDataJSON()}; }
   data=state.savedAutomation||automation;
  }
  else if(p==='/api/library') data=[{id:'library-1',scope:'personal',title:'My library',owner_user_id:'reviewer',team_id:null,item_count:state.empty?0:3}];
  else if(p==='/api/library/library-1/items') {
   if(req.method()==='POST'){state.catalogSaveCalls=(state.catalogSaveCalls||0)+1;if(state.failCatalogSave)return route.fulfill({status:503,json:{detail:'Library temporarily unavailable.'}});state.catalogSaved=true;data=items[0];}
   else data=state.catalogScenario?(state.catalogSaved?[items[0]]:[]):list(items);
  }
  else if(p==='/api/knowledge/kb-1/adopt') {state.adoptCalls=(state.adoptCalls||0)+1;if(state.failAdopt)return route.fulfill({status:503,json:{detail:'Knowledge library temporarily unavailable.'}});data={uuid:'ref-1',kb_uuid:'kb-1'};}
  else if(p==='/api/workflows/workflow-1') data=workflow;
  else if(p==='/api/workflows/workflow-1/history') data={runs:[]};
  else if(p==='/api/workflows/workflow-1/quality-sparkline') data={scores:[]};
  else if(p==='/api/workflows/workflow-1/quality-status') data={};
  else if(p==='/api/library/folders') data=[];
  else if(p==='/api/verification/verified') {
   const pool=[...catalog,{...catalog[0],id:'catalog-kb',item_id:'kb-1',source_uuid:'kb-1',kind:'knowledge_base',name:kb.title,display_name:kb.title,total_sources:3,total_chunks:84,sources_ready:2,kb_status:'ready'}];
   const displayPool=state.catalogLong?pool.map(item=>({...item,description:'A research-administration review covering eligibility, sponsor conditions, evidence gaps, approvals, and the final submission package. '.repeat(5),markdown:'## Review instructions\n\n'+('Read the source documents, compare the requirements, and check each finding before using it.\n\n'.repeat(14))})):pool;
   const filtered=list(displayPool.filter(i=>!url.searchParams.get('kind')||i.kind===url.searchParams.get('kind'))); data={items:filtered,total:filtered.length};
  }
  else if(p.includes('/verification/collections')) data={collections:[]};
  else if(p==='/api/activity/streams') data={events:[],stale_threshold_minutes:30};
  else if(p==='/api/workflows') data=list([workflow]);
  else if(p==='/api/chat/conversations') data=[];
  else if(p==='/api/chat/memory') data={memories:[]};
  else if(p==='/api/chat') {
    state.lastChat=req.postDataJSON();
    const chunks=state.chatChunks || [{kind:'text',content:'The proposal is due **October 15**. Include a budget justification and review the award conditions before submission.'}];
    return route.fulfill({status:200,contentType:'application/x-ndjson',headers:{'X-Conversation-UUID':'review-conversation','X-Activity-ID':'review-activity'},body:chunks.map(x=>JSON.stringify(x)).join('\n')+'\n'});
  }
  else if(p.includes('/organizations') || p.includes('/notifications') || p.includes('/search_sets') || p.includes('/searchsets')) data=[];
  else { unmatched.add(`${req.method()} ${p}`); return route.fulfill({status:501,json:{detail:`Unconfigured review fixture: ${p}`}}); }
  return route.fulfill({status:200,json:data});
 });
}
