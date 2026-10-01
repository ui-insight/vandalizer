import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const run='/private/tmp/vandalizer-ra8-backend'
const {password}=JSON.parse(await readFile(resolve(run,'runtime.json'),'utf8'))
const state=JSON.parse(await readFile(resolve(run,'collaboration-state.json'),'utf8'))
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:'http://127.0.0.1:5181',isolatedBackend:true,resetStorage:false}),{page,context}=review
page.setDefaultTimeout(20000)
async function api(method,path,data){const cookies=await context.cookies(),csrf=cookies.find(c=>c.name==='csrf_token')?.value;const r=await context.request.fetch(review.baseURL+'/api'+path,{method,data,headers:csrf?{'X-CSRF-Token':csrf}:{}});assert.ok(r.ok(),method+' '+path+': '+r.status());return r.json()}
async function login(role){await context.clearCookies();for(let attempt=0;attempt<7;attempt++){const r=await context.request.post(review.baseURL+'/api/auth/login',{data:{user_id:'ra8-'+role+'@example.test',password}});if(r.status()===429){await page.waitForTimeout(10000);continue}assert.ok(r.ok(),'Local fixture sign-in: '+r.status());return}throw new Error('Local login rate limit did not clear')}
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id+': overflow');assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': axe');console.log('Captured '+id)}
async function project(){await page.goto(review.baseURL+'/?mode=chat&project='+state.project.uuid);await page.getByRole('button',{name:'Manage project',exact:true}).click();return page.getByRole('dialog',{name:'Manage project',exact:true})}
try{
 await login('owner')
 for(const width of [390,1440]){
  await page.setViewportSize({width,height:width===390?700:1000})
  await api('POST','/teams/switch/'+state.team.uuid)
  await page.goto(review.baseURL+'/teams');await page.getByRole('heading',{name:state.team.name,exact:true}).waitFor();await page.getByRole('button',{name:'Rename team',exact:true}).waitFor();assert.equal(await page.getByRole('heading',{name:'Transfer Ownership',exact:true}).count(),0);await shot('live-team-admin-after-transfer-'+width)
  const row=page.getByText(state.second_team.name,{exact:true}).locator('..').locator('..');await row.getByRole('button',{name:'Switch',exact:true}).click();await page.getByRole('heading',{name:state.second_team.name,exact:true}).waitFor();await page.getByRole('button',{name:'Delete Team',exact:true}).waitFor();await shot('live-team-switch-owner-'+width)
  let modal=await project();await modal.getByRole('button',{name:'Rename project',exact:true}).waitFor();await shot('live-project-owner-'+width);await modal.getByRole('button',{name:'Close',exact:true}).click()
  await page.getByRole('textbox',{name:'Message input'}).fill('Unsent project evidence question')
  await page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('button',{name:'Projects',exact:true}).click();await page.getByRole('textbox',{name:'New project name'}).fill('Unsubmitted local project draft');await page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('button',{name:'Chat',exact:true}).click();assert.equal(await page.getByRole('textbox',{name:'Message input'}).inputValue(),'');await page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('button',{name:'Projects',exact:true}).click();assert.equal(await page.getByRole('textbox',{name:'New project name'}).inputValue(),'Unsubmitted local project draft');await page.getByRole('button').filter({hasText:state.project.title}).first().click();await page.getByRole('button',{name:'Manage project',exact:true}).waitFor();assert.equal(await page.getByRole('textbox',{name:'Message input'}).inputValue(),'Unsent project evidence question');await shot('live-project-draft-return-'+width)
 }
 await login('member');await api('POST','/teams/switch/'+state.team.uuid);await page.goto(review.baseURL+'/teams');await page.getByRole('heading',{name:'Transfer Ownership',exact:true}).waitFor();await shot('live-team-new-owner')
 let modal=await project();await modal.getByRole('button',{name:'Rename project',exact:true}).waitFor();assert.equal(await modal.getByRole('button',{name:'Delete project',exact:true}).count(),0);await shot('live-project-editor');await modal.getByRole('button',{name:'Close',exact:true}).click()
 // The viewer was removed by the API suite. Reinvite for its UI, then remove again.
 await login('owner');const link=await api('POST','/projects/'+state.project.uuid+'/invite-link',{role:'viewer',max_uses:1})
 await login('viewer');await api('POST','/projects/join/accept/'+link.token);modal=await project();await modal.getByText(/You have read-only access/).waitFor();assert.equal(await modal.getByRole('button',{name:'Rename project',exact:true}).count(),0);await shot('live-project-viewer');await modal.getByRole('button',{name:'Close',exact:true}).click()
 assert.deepEqual(review.errors,[]);review.observations.push('Real local API cookies and controlled account permissions; no intercepted API data, model runs, or production actions. API suite separately checks removal, expired invitations, and denied writes.')
}catch(error){await review.capture('isolated-collaboration-browser-blocked',String(error));throw error}finally{await review.flush();await review.browser.close()}
