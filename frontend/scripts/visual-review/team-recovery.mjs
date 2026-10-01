import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page}=review
page.setDefaultTimeout(30000)
let failDetails=true,failInvite=true,failCreate=true,invites=[],writes=[]
const members=[{user_id:'reviewer',name:'Alex Morgan',email:'reviewer@example.test',role:'owner'},{user_id:'colleague',name:'Jordan Lee — Institutional Research Administration',email:'jordan.research.administration@example.test',role:'member'}]
await page.route('**/api/teams/team-1/members',r=>failDetails?r.fulfill({status:503,json:{detail:'Team details unavailable'}}):r.fulfill({json:members}))
await page.route('**/api/teams/team-1/invites',r=>r.fulfill({json:invites}))
await page.route('**/api/teams/team-1/join-links',r=>r.fulfill({json:[]}))
await page.route('**/api/teams/invite',r=>{const data=r.request().postDataJSON();writes.push(data);if(failInvite)return r.fulfill({status:503,json:{detail:'Invitation service unavailable'}});invites=[{...data,token:'synthetic-only',expires_at:'2099-10-01T00:00:00Z'}];return r.fulfill({json:{token:'synthetic-only',email:data.email}})})
await page.route('**/api/teams/create',r=>{writes.push(r.request().postDataJSON());return failCreate?r.fulfill({status:503,json:{detail:'Team creation unavailable'}}):r.fulfill({json:{uuid:'team-new',name:'Draft team'}})})
await page.route('**/api/teams/member/role',r=>{const data=r.request().postDataJSON();writes.push(data);members.find(m=>m.user_id===data.user_id).role=data.role;return r.fulfill({json:{ok:true}})})
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id+': overflow');assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': accessibility');console.log('Captured '+id)}
try {
 for(const width of [320,1440]) {
  failDetails=true;failInvite=true;failCreate=true;invites=[];writes=[];members[1].role='member'
  await page.setViewportSize({width,height:width===320?700:900});await page.goto(review.baseURL+'/teams')
  await page.getByRole('button',{name:'Retry team details',exact:true}).waitFor();failDetails=false;await page.getByRole('button',{name:'Retry team details',exact:true}).click()
  await page.getByText(members[1].name,{exact:true}).waitFor()
  await shot('team-members-'+width)
  const email=page.getByRole('textbox',{name:'Email',exact:true})
  await email.fill('new-colleague@example.test');await page.getByRole('button',{name:'Invite',exact:true}).click()
  await page.getByRole('alert').filter({hasText:'Invitation service unavailable'}).waitFor()
  assert.equal(await email.inputValue(),'new-colleague@example.test')
  failInvite=false;await page.getByRole('button',{name:'Invite',exact:true}).click();await page.getByText('new-colleague@example.test',{exact:true}).waitFor()
  assert.equal(await email.inputValue(),'');assert.deepEqual(writes[0],writes[1])
  const role=page.getByRole('combobox',{name:'Role for '+members[1].name,exact:true});await role.selectOption('admin');await page.waitForFunction(()=>document.querySelector('select[aria-label^="Role for"]')?.value==='admin')
  assert.deepEqual(writes.at(-1),{team_id:'team-1',user_id:'colleague',role:'admin'})
  const name=page.getByRole('textbox',{name:'New team name',exact:true});await name.fill('Draft team')
  await page.getByRole('button',{name:'Create',exact:true}).click();await page.getByRole('alert').filter({hasText:'Team creation unavailable'}).waitFor();assert.equal(await name.inputValue(),'Draft team')
  await name.scrollIntoViewIfNeeded();await shot('team-create-retry-'+width)
  failCreate=false;await page.getByRole('button',{name:'Create',exact:true}).click();await page.waitForFunction(()=>document.querySelector('[aria-label="New team name"]')?.value==='')
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push('Non-delivering synthetic team lifecycle: details retry, long member names, invitation failure/retry with same payload, role change scoped to team-1, failed creation preserves name. No real invitations, membership changes, transfers or deletion.')
}catch(error){await review.capture('team-recovery-blocked',String(error));throw error}
finally{await review.flush();await review.browser.close()}
