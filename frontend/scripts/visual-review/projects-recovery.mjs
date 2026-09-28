import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { project, kb } from './fixtures.mjs'
const review = await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page,state}=review
page.setDefaultTimeout(12000)
let fail='', projects=[], writes=[]
const longTitle='Community resilience proposal — long-term monitoring, regional partnerships and supporting evidence'
const emptyProject={...project,uuid:'project-empty',title:'New research project',capabilities:{files:{count:0,folders:0},knowledge:{ready:false,documents:0},workflows:{count:0},extractions:{count:0},automations:{count:0},external_kbs:{count:0},members:{count:1}}}
const viewer={...project,uuid:'project-viewer',title:'Shared read-only review',owner_user_id:'another-owner',role:'viewer',can_leave:true}
await page.route('**/api/projects',async route=>{
 if(route.request().method()==='POST'){
  const body=route.request().postDataJSON();writes.push(body)
  if(fail==='create')return route.fulfill({status:503,json:{detail:'Project creation unavailable'}})
  const created={...emptyProject,title:body.title};projects.push(created);return route.fulfill({json:created})
 }
 if(fail==='list')return route.fulfill({status:503,json:{detail:'Projects unavailable'}})
 return route.fulfill({json:projects})
})
await page.route('**/api/projects/*',route=>{
 const id=new URL(route.request().url()).pathname.split('/').at(-1)
 if(id==='forbidden')return route.fulfill({status:403,json:{detail:'Project access unavailable'}})
 const item=projects.find(p=>p.uuid===id)
 assert.ok(item,`Unexpected project: ${id}`)
 if(route.request().method()==='PATCH'){
  const body=route.request().postDataJSON();writes.push({id,...body})
  if(fail==='save')return route.fulfill({status:503,json:{detail:'Project changes unavailable'}})
  Object.assign(item,body)
 }
 if(fail==='detail')return route.fulfill({status:503,json:{detail:'Project details unavailable'}})
 return route.fulfill({json:item})
})
await page.route('**/api/projects/*/members',route=>fail==='members'?route.fulfill({status:503,json:{detail:'Members unavailable'}}):route.fulfill({json:[{user_id:'reviewer',role:'owner',name:'Review owner',email:'review@example.com'}]}))
await page.route('**/api/projects/*/pins',route=>route.fulfill({json:[]}))
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${id}: overflow`);assert.deepEqual(JSON.parse(await readFile(resolve(review.out,`${id}.axe.json`),'utf8')),[],`${id}: accessibility`);console.log(`Captured ${id}`)}
const nav=name=>page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('button',{name,exact:true})
async function send(text){state.chatChunks=[{kind:'text',content:`Response to ${text}`}];await page.getByRole('textbox',{name:'Message input'}).fill(text);await page.getByRole('button',{name:'Send message'}).click();await page.getByText(`Response to ${text}`,{exact:true}).waitFor()}
try{
 for(const [width,height]of[[320,568],[768,600],[1440,900]]){
  projects=[{...structuredClone(project),title:longTitle},structuredClone(viewer),{...project,uuid:'forbidden',title:'Access revoked project'},...Array.from({length:58},(_,i)=>({...project,uuid:`extra-${i}`,title:`Research project ${String(i).padStart(2,'0')}`}))];fail='list';writes=[]
  await page.setViewportSize({width,height});await page.goto(review.baseURL+'/?mode=projects')
  await page.getByRole('button',{name:'Retry projects',exact:true}).waitFor();await shot(`projects-load-error-${width}`)
  fail='';await page.getByRole('button',{name:'Retry projects',exact:true}).click();await page.getByRole('button',{name:/Show more projects/}).waitFor();await shot(`projects-many-${width}`)
  await page.getByRole('button',{name:/Show more projects/}).click();await page.getByText('Research project 57',{exact:true}).waitFor()
  await page.getByRole('searchbox',{name:'Search projects'}).fill('not-present');await page.getByRole('button',{name:'Clear search',exact:true}).waitFor();await shot(`projects-no-results-${width}`)
  await page.getByRole('button',{name:'Clear search',exact:true}).click()
  await page.getByRole('textbox',{name:'New project name'}).fill('New research project');fail='create';await page.getByRole('button',{name:'Create project',exact:true}).click();await page.getByRole('alert').filter({hasText:'Your name is preserved'}).waitFor();await shot(`projects-create-error-${width}`)
  fail='';await page.getByRole('button',{name:'Create project',exact:true}).click();await page.getByRole('button',{name:'Manage project',exact:true}).waitFor();assert.deepEqual(writes[0],writes[1])
  await page.getByRole('button',{name:'Manage project',exact:true}).click();let detail=page.getByRole('dialog',{name:'Manage project',exact:true});await detail.getByRole('button',{name:'Add project files',exact:true}).waitFor();await shot(`projects-empty-detail-${width}`)
  await detail.getByRole('button',{name:'Close',exact:true}).click();await nav('Projects').click()
  await page.getByRole('button').filter({hasText:longTitle}).first().click();await page.getByRole('button',{name:'Manage project',exact:true}).waitFor()
  fail='members';await page.getByRole('button',{name:'Manage project',exact:true}).click();detail=page.getByRole('dialog',{name:'Manage project',exact:true});await detail.getByRole('button',{name:'Retry members',exact:true}).waitFor();await shot(`projects-members-error-${width}`)
  fail='';await detail.getByRole('button',{name:'Retry members',exact:true}).click();await detail.getByText('Review owner',{exact:true}).waitFor()
  await detail.getByRole('button',{name:'Rename project',exact:true}).click();await detail.getByRole('textbox',{name:'Project title'}).fill('Renamed community review');fail='save';await detail.getByRole('button',{name:'Save title',exact:true}).click();await detail.getByRole('alert').waitFor();await shot(`projects-title-error-${width}`)
  fail='';await detail.getByRole('button',{name:'Save title',exact:true}).click();await detail.getByRole('heading',{name:'Renamed community review',exact:true}).waitFor()
  await detail.getByRole('button',{name:'Edit description',exact:true}).click();await detail.getByRole('textbox',{name:'Project description'}).fill('A retained description covering the source documents and review plan.');fail='save';await detail.getByRole('button',{name:'Save description',exact:true}).click();await detail.getByRole('alert').waitFor();await shot(`projects-description-error-${width}`)
  fail='';await detail.getByRole('button',{name:'Save description',exact:true}).click();await detail.getByRole('textbox',{name:'Project description'}).waitFor({state:'hidden'})
  fail='save';await detail.getByRole('combobox',{name:'Project status'}).selectOption('submitted');await detail.getByRole('button',{name:'Retry status',exact:true}).waitFor();await shot(`projects-status-error-${width}`)
  fail='';await detail.getByRole('button',{name:'Retry status',exact:true}).click();await detail.getByRole('button',{name:'Retry status',exact:true}).waitFor({state:'hidden'})
  await detail.getByRole('button',{name:'Open project files',exact:true}).click();await page.getByRole('checkbox',{name:'Select Proposal narrative.pdf',exact:true}).check();await nav('Chat').click()
  await page.getByRole('button',{name:'Add',exact:true}).click();await page.getByRole('menuitem',{name:'Add Knowledge Base',exact:true}).click();const picker=page.getByRole('dialog',{name:'Attach knowledge bases',exact:true});await picker.getByRole('button',{name:kb.title,exact:true}).click();await picker.getByRole('button',{name:'Attach',exact:true}).click()
  await send('Within the project');assert.equal(state.lastChat.project_uuid,'project-1');assert.deepEqual(state.lastChat.document_uuids,['doc-0']);assert.deepEqual(state.lastChat.knowledge_base_uuids,['kb-1']);await shot(`projects-scoped-chat-${width}`)
  await page.getByRole('button',{name:'Exit',exact:true}).click();await send('Outside the project');assert.equal(state.lastChat.project_uuid??null,null);assert.deepEqual(state.lastChat.document_uuids,[]);assert.deepEqual(state.lastChat.knowledge_base_uuids,[]);assert.equal(await page.getByText('Response to Within the project',{exact:true}).count(),0);await shot(`projects-exited-chat-${width}`)
  await nav('Projects').click();await page.getByRole('button').filter({hasText:'Shared read-only review'}).first().click();await page.getByRole('button',{name:'Manage project',exact:true}).click();detail=page.getByRole('dialog',{name:'Manage project',exact:true});await detail.getByText(/You have read-only access/).waitFor();assert.equal(await detail.getByRole('button',{name:'Rename project',exact:true}).count(),0);await shot(`projects-viewer-detail-${width}`)
  await detail.getByRole('button',{name:'Close',exact:true}).click();await page.getByRole('button',{name:'Exit',exact:true}).click();await nav('Projects').click();await page.getByRole('button').filter({hasText:'Access revoked project'}).first().click();await page.getByText(/Could not open this project/).waitFor();assert.equal(await page.getByRole('button',{name:'Manage project',exact:true}).count(),0);await shot(`projects-access-error-${width}`)
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
}catch(error){await review.capture('projects-recovery-blocked',String(error));throw error}
finally{await review.flush();await review.browser.close()}
