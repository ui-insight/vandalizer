import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import {createReview} from './harness.mjs'
const lessons=JSON.parse(await readFile(new URL('../../../backend/certification-data/lessons.json',import.meta.url),'utf8'))
const exercises=JSON.parse(await readFile(new URL('../../../backend/certification-data/exercises.json',import.meta.url),'utf8'))
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL||'http://127.0.0.1:5290',resetStorage:false})
const {page,context,state}=review;page.setDefaultTimeout(10000);page.setDefaultNavigationTimeout(30000)
let progress={id:'cert-review',user_id:'reviewer',modules:{},total_xp:0,level:'novice',certified:false,certified_at:null,last_activity_date:null}
let progressReads=0,seq=0,failNextProgress=false
await context.route('**/api/certification/**',async route=>{
 const path=new URL(route.request().url()).pathname
 if(path.endsWith('/progress')){progressReads++;if(failNextProgress){failNextProgress=false;return route.fulfill({status:503,json:{detail:'Review-only unavailable progress'}})}return route.fulfill({json:progress})}
 const mid=path.match(/\/modules\/([^/]+)\/exercise/)?.[1]
 if(mid)return route.fulfill({json:exercises[mid]})
 return route.fallback()
})
function set(name,data){const id='supp-'+ ++seq;state.chatChunks=[{kind:'tool_call',content:'',tool_name:name,tool_call_id:id,args:{}},{kind:'tool_result',tool_name:name,tool_call_id:id,content:data},{kind:'text',content:'State '+seq}];return seq}
async function send(name,data){const n=set(name,data);await page.getByRole('textbox',{name:'Message input'}).fill('Review certification.');await page.getByRole('button',{name:'Send message',exact:true}).click();await page.getByText('State '+n,{exact:true}).waitFor()}
async function go(){await page.goto(review.baseURL);await page.getByRole('textbox',{name:'Message input'}).waitFor()}
async function shot(id,note='Synthetic backend/tool responses; actual frontend interactions.'){await review.capture(id,note);console.log(id)}
function ld(mid,i){return{module_id:mid,module_title:lessons[mid].title,lesson_number:i+1,lesson_count:lessons[mid].lessons.length,...lessons[mid].lessons[i],is_last:i===lessons[mid].lessons.length-1}}
try{
 if(process.env.REVIEW_ONLY!=='completion'){
 if(process.env.REVIEW_ONLY!=='lessons'){
 await page.setViewportSize({width:390,height:844})
 for(const [mid,l] of Object.entries(lessons)){
  await go();const e=exercises[mid]||{}
  await send('get_certification_module',{module_id:mid,title:l.title,xp:100,overview:e.overview,instructions:e.chat_instructions,lesson_titles:l.lessons.map(x=>x.title),expected_fields:e.expected_fields,star_criteria:e.star_criteria,sample_documents:e.documents,assessment_keys:l.assessment?.questions.map(x=>x.key)||[]})
  const action=page.getByRole('button',{name:`Start the lessons (${l.lessons.length})`,exact:true});await action.scrollIntoViewIfNeeded();await shot('module-actions-'+mid+'-390')
  const bounds=await action.boundingBox();review.observations.push({id:'module-action-'+mid,bounds,reachable:bounds.x>=0&&bounds.x+bounds.width<=390&&bounds.y>=0&&bounds.y+bounds.height<=844})
 }
 for(const width of [320,390,768,1440]){
  await page.setViewportSize({width,height:width<=390?844:1000});await go();await send('get_certification_lesson',ld('workflow_design',6));await shot('long-top-'+width)
  await page.getByRole('button',{name:'Continue to lesson 8',exact:true}).scrollIntoViewIfNeeded();await shot('long-bottom-'+width)
 }
 }
 await page.setViewportSize({width:1440,height:1000});await go();await send('get_certification_lesson',ld('ai_literacy',2));await shot('knowledge-check-chat')
 review.observations.push({id:'knowledge-check',payloadHasCheck:!!ld('ai_literacy',2).knowledge_check,rendered:await page.getByText(lessons.ai_literacy.lessons[2].knowledge_check.question,{exact:true}).count()})
 const practice=lessons.ai_literacy.lessons[2].knowledge_check;assert.equal(await page.getByRole('radiogroup',{name:practice.question,exact:true}).count(),1);await page.getByRole('radio',{name:practice.options.find(x=>!x.correct).text,exact:true}).check();await page.getByRole('button',{name:'Check answer',exact:true}).click();await shot('knowledge-check-wrong');await page.getByRole('radio',{name:practice.options.find(x=>x.correct).text,exact:true}).check();await page.getByRole('button',{name:'Check answer',exact:true}).click();await shot('knowledge-check-correct')
 await page.setViewportSize({width:320,height:844});for(const [mid,module] of Object.entries(lessons)){for(const [i,lesson] of module.lessons.entries()){if(!lesson.diagram)continue;await go();await send('get_certification_lesson',ld(mid,i));await page.getByRole('region',{name:'Lesson diagram',exact:true}).scrollIntoViewIfNeeded();await shot('diagram-'+lesson.diagram+'-320')}}
 await page.setViewportSize({width:1440,height:1000})
 await page.goto(review.baseURL+'/certification');await page.getByRole('combobox',{name:'Learning panel position',exact:true}).selectOption('fullscreen');await page.getByRole('button',{name:/^0 AI Literacy/}).click();await shot('chat-to-panel-resume')
 await page.getByRole('button',{name:/^Lesson 3:/}).click();await shot('panel-diagram-and-knowledge-check')
 await page.getByRole('button',{name:'Return to workspace',exact:true}).click();await go()
 await send('provision_certification_lab',{module_id:'foundations',provisioned_docs:['doc-0'],document_names:exercises.foundations.documents,folder:'Certification Lab',message:'1 sample document(s) are in the "Certification Lab" folder (Files tab).'});await shot('lab-provisioned')
 await go();await send('submit_certification_assessment',{module_id:'ai_literacy',stored:true,message:'Answers saved. Run check_certification_module then complete_certification_module to bank the XP.'});await shot('assessment-saved')
 }
 await page.setViewportSize({width:1440,height:1000});await go();await send('check_certification_module',{module_id:'ai_literacy',title:'AI Literacy',passed:true,stars:3,checks:[{name:'Self-assessment completed',passed:true,detail:'Answer all 3 reflection questions'}]});await shot('check-passed')
 progress={...progress,modules:{ai_literacy:{completed:true,stars:3,xp_earned:125}},total_xp:125,level:'apprentice'}
 const before=progressReads,n=set('complete_certification_module',{module_id:'ai_literacy',title:'AI Literacy',stars:3,xp_earned:125,total_xp:125,level:'apprentice',level_up:true,certified:false})
 await page.getByRole('button',{name:'Complete the module',exact:true}).click();await page.getByText('State '+n,{exact:true}).waitFor();await shot('module-complete');assert.ok(progressReads>before,'Live completion must refresh shared progress');review.observations.push({id:'completion-sync',refreshed:progressReads>before,progressReadsBefore:before,progressReadsAfter:progressReads,message:state.lastChat.message})
 await page.getByRole('button',{name:"What's next?",exact:true}).focus();await shot('keyboard-focus')
 failNextProgress=true;await send('submit_certification_assessment',{module_id:'ai_literacy',stored:true});await page.getByText('Your certification action was saved, but the progress display is awaiting refresh. You do not need to submit it again.',{exact:true}).waitFor();await shot('saved-refresh-failed')
 const lastWrite=state.lastChat,readsBeforeRetry=progressReads;await page.getByRole('button',{name:'Refresh certification progress',exact:true}).click();await page.getByRole('button',{name:'Refresh certification progress',exact:true}).waitFor({state:'hidden'});assert.equal(progressReads,readsBeforeRetry+1);assert.equal(state.lastChat,lastWrite);await shot('saved-refresh-recovered');review.observations.push({id:'refresh-retry',reads:progressReads-readsBeforeRetry,repeatedWrite:false})
 progress={...progress,modules:Object.fromEntries(Object.keys(lessons).map(id=>[id,{completed:true,stars:3}])),total_xp:2675,level:'architect',certified:true,certified_at:'2026-10-02T12:00:00Z'}
 await go();await send('get_certification_progress',{...progress,modules_completed:11,modules_total:11,next_module_id:null,modules:Object.entries(lessons).map(([module_id,m])=>({module_id,title:m.title,xp:100,completed:true,stars:3}))});await shot('progress-certified');
 await page.goto(review.baseURL+'/certification');await page.getByRole('combobox',{name:'Learning panel position',exact:true}).selectOption('fullscreen');await page.getByText('Course progress and credential',{exact:true}).click();await shot('panel-certified')
 assert.deepEqual([...review.unmatched],[]);assert.deepEqual(review.errors,[])
}catch(e){await shot('blocked',String(e));throw e}
finally{await review.flush();await review.browser.close()}
