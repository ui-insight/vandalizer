import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import {createReview} from './harness.mjs'
const lessons=JSON.parse(await readFile(new URL('../../../backend/certification-data/lessons.json',import.meta.url),'utf8'))
const exercises=JSON.parse(await readFile(new URL('../../../backend/certification-data/exercises.json',import.meta.url),'utf8'))
const xp=[50,100,100,100,150,150,200,200,250,250,300], ids=Object.keys(lessons)
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL||'http://127.0.0.1:5290'})
const {page,state,context}=review
page.setDefaultTimeout(12000)
let progress={id:'cert-review',user_id:'reviewer',modules:{},total_xp:0,level:'novice',certified:false,certified_at:null,last_activity_date:null}
await context.route('**/api/certification/**',async route=>{
 const p=new URL(route.request().url()).pathname
 if(p.endsWith('/progress'))return route.fulfill({json:progress})
 const match=p.match(/\/modules\/([^/]+)\/exercise/)
 if(match)return route.fulfill({json:exercises[match[1]]||{}})
 return route.fallback()
})
let seq=0
function chunks(name,data){const id='cert-'+ ++seq;return [{kind:'tool_call',content:'',tool_name:name,tool_call_id:id,args:{}},{kind:'tool_result',tool_name:name,tool_call_id:id,content:data},{kind:'text',content:'Certification review fixture.'}]}
async function send(name,data,prompt='Review this certification state.'){
 state.chatChunks=chunks(name,data)
 await page.getByRole('textbox',{name:'Message input'}).fill(prompt)
 await page.getByRole('button',{name:'Send message',exact:true}).click()
 await page.getByText('Certification review fixture.',{exact:true}).waitFor()
}
async function go(){await page.goto(review.baseURL);await page.getByRole('textbox',{name:'Message input'}).waitFor()}
async function shot(id,note='Controlled tool result; real React frontend; no model or backend execution.'){
 await review.capture(id,note);console.log(id)
}
function moduleData(mid){const l=lessons[mid],e=exercises[mid]||{};return {module_id:mid,title:l.title,xp:xp[ids.indexOf(mid)],completed:false,stars:0,overview:e.overview||'',instructions:e.chat_instructions||e.instructions||[],lesson_titles:l.lessons.map(x=>x.title),expected_fields:e.expected_fields||[],star_criteria:e.star_criteria||{},sample_documents:e.documents||[],assessment_keys:l.assessment?.questions.map(x=>x.key)||[],assessment_questions:l.assessment?.questions||[]}}
function progressData(count=0){return {total_xp:count?125:0,level:count?'apprentice':'novice',certified:count===11,modules_completed:count,modules_total:11,next_module_id:ids[count]||null,modules:ids.map((id,i)=>({module_id:id,title:lessons[id].title,xp:xp[i],completed:i<count,stars:i<count?3:0}))}}
function lessonData(mid,i){return {module_id:mid,module_title:lessons[mid].title,lesson_number:i+1,lesson_count:lessons[mid].lessons.length,...lessons[mid].lessons[i],is_last:i===lessons[mid].lessons.length-1}}
try{
 await go();await shot('entry-1440')
 state.chatChunks=chunks('get_certification_progress',progressData())
 await page.getByRole('button',{name:'Start the certification course',exact:true}).click()
 await page.getByText('0/11 modules complete',{exact:true}).waitFor()
 review.observations.push({id:'entry-message',message:state.lastChat.message})
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:width===1440?1000:844})
  await go();await send('get_certification_progress',progressData());await shot('progress-'+width)
  for(const mid of ids){await go();await send('get_certification_module',moduleData(mid));await shot('module-'+mid+'-'+width)}
 }
 await page.setViewportSize({width:1440,height:1000})
 for(const mid of ids)for(let i=0;i<lessons[mid].lessons.length;i++){
  await go();await send('get_certification_lesson',lessonData(mid,i));await shot('lesson-'+mid+'-'+(i+1))
 }
 for(const width of [320,390,768,1440]){
  await page.setViewportSize({width,height:width<=390?844:1000})
  await go();await send('get_certification_lesson',lessonData('workflow_design',6));await shot('lesson-long-'+width)
  await go();await send('check_certification_module',{module_id:'extraction_engine',title:'Extraction Engine',passed:true,stars:1,checks:[{name:'15+ extraction fields',passed:true,detail:'You have 15 unique fields across your extraction tasks (need 15+)'},{name:'Missing expected fields',passed:false,detail:'Consider adding: PI Name, Institution, Total Budget, Grant Number, Specific Aims'}]});await shot('check-contradiction-'+width)
  await go();await send('check_certification_module',{module_id:'foundations',title:'Foundations',passed:false,stars:0,checks:[{name:'Extraction template exists',passed:true,detail:'Create an extraction template (from chat or the Library tab)'},{name:'Expected fields configured',passed:false,detail:'Found 0/5 expected fields across your extraction tasks (missing: PI Name, Institution, Total Budget)'},{name:'Extraction executed',passed:false,detail:'Run the extraction at least once (the agent can do this for you)'}]});await shot('check-failed-'+width)
  await go();await send('complete_certification_module',{module_id:'governance',title:'Governance',stars:3,xp_earned:375,total_xp:2675,level:'architect',level_up:false,certified:true});await shot('certified-'+width)
 }
 await page.setViewportSize({width:1440,height:1000})
 await go();await send('get_certification_module',moduleData('foundations'))
 await page.getByRole('button',{name:'Open files beside chat',exact:true}).click();await shot('files-beside-chat')
 await go();await send('get_certification_progress',{error:'Certification progress is unavailable.',hint:'Try again in a moment.'});await shot('progress-error')
 state.chatChunks=chunks('get_certification_progress',progressData())
 await page.getByRole('button',{name:'Review recovery options',exact:true}).click();await page.getByText('0/11 modules complete',{exact:true}).waitFor();await shot('progress-recovery')
 await go();await send('get_certification_lesson',lessonData('ai_literacy',0))
 state.chatChunks=chunks('get_certification_lesson',lessonData('ai_literacy',1))
 await page.getByRole('button',{name:'Continue to lesson 2',exact:true}).click();await page.getByText('Lesson 2/9 · AI Literacy',{exact:true}).waitFor();review.observations.push({id:'lesson-continue',message:state.lastChat.message});await shot('lesson-continued')
 progress={...progress,modules:{ai_literacy:{completed:true,stars:3,xp_earned:125}},total_xp:125,level:'apprentice'}
 await go();await shot('returning-entry');await page.goto(review.baseURL+'/certification');await shot('panel-existing-progress')
 review.observations.push({id:'scope',note:'All authored chat module and lesson cards captured. Progress results are fixtures despite known real progress-tool KeyError. No end-to-end agent pass is claimed.'})
 assert.deepEqual([...review.unmatched],[]);assert.deepEqual(review.errors,[])
}catch(e){await shot('blocked',String(e));throw e}
finally{await review.flush();await review.browser.close()}
