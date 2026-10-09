import assert from 'node:assert/strict'
import { expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL}),{page}=review
const stats={conversations:0,search_runs:0,workflows_started:0,workflows_completed:0,workflows_failed:0,tokens_in:0,tokens_out:0,active_users:0,active_teams:0}
const records=Array.from({length:503},(_,i)=>({user_id:`person-${i}`,team_id:`group-${i}`,name:`Research ${String(i).padStart(4,'0')}`,email:`qa-${i}@example.test`,tokens_total:503-i,workflows_run:0,workflows_completed:0,conversations:0,active_users:0,member_count:1,avg_latency_ms:null,last_active:null,level:'novice',total_xp:0,modules_completed:0,modules_total:10,certified:false,certified_at:null,last_activity_date:null,unlocked:false}))
const fixed={'/api/auth/me':{id:'reviewer',user_id:'reviewer',name:'Alex Morgan',email:'reviewer@example.test',is_admin:true,is_staff:true,current_team:'team-1'},'/api/auth/config':{auth_methods:['password'],oauth_providers:[],trial_system_enabled:false},'/api/admin/system/version':{current:'5.0.0',update_available:false},'/api/admin/catalog/status':{update_available:false},'/api/admin/telemetry/optin':{show_banner:false},'/api/admin/teams/all':{items:[],total:0,capped:false},'/api/admin/users/isolated':{items:[],total:0,capped:false}}
await page.route('**/api/**',async r=>{
 const url=new URL(r.request().url()),p=url.pathname.replace(/\/$/,'')
 if(p in fixed)return r.fulfill({json:fixed[p]})
 if(['/api/admin/users','/api/admin/teams','/api/admin/certifications'].includes(p)){
  const offset=Number(url.searchParams.get('offset')||0),limit=Number(url.searchParams.get('limit')||500),q=url.searchParams.get('q')||''
  const items=records.filter(row=>!q||row.name.includes(q));return r.fulfill({json:{items:items.slice(offset,offset+limit),total:items.length,capped:offset+limit<items.length}})
 }
 if(p.match(/^\/api\/admin\/users\/person-\d+\/history$/))return r.fulfill({json:{items:[],total:0,capped:false}})
 if(p.match(/^\/api\/admin\/(users\/person-|teams\/group-)\d+\/detail$/))return r.fulfill({json:{...records[6],...stats,timeseries:[],previous_period:null,document_count:0,recent_workflows:[],recent_conversations:[],members:[]}})
 return r.fallback()
})
async function shot(id){await review.capture(id);assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id)}
try{
 for(const tab of ['users','teams','certifications']){
  await page.setViewportSize({width:1440,height:900});await page.goto(review.baseURL+'/admin?tab='+tab)
  if(tab==='teams')await page.getByRole('tab',{name:'Usage Stats',exact:true}).click()
  await page.getByText('Research 0000',{exact:true}).waitFor()
  const downloaded=page.waitForEvent('download');await page.getByRole('button',{name:'Export all matching records'}).click()
  const csv=await readFile(await (await downloaded).path(),'utf8');assert.equal(csv.trim().split('\n').length,504);assert.ok(csv.includes('Research 0502'));assert.ok(csv.includes('Timezone'))
  await shot(tab+'-complete-export')
  if(tab!=='certifications'){
   const scroll=page.locator('#main-content').locator('..')
   const open=page.getByRole('button',{name:tab==='users'?'View Research 0006':'View team usage: Research 0006',exact:true})
   await open.scrollIntoViewIfNeeded();const top=await scroll.evaluate(e=>e.scrollTop);assert.ok(top>0)
   await open.click();await page.getByRole('button',{name:tab==='users'?'Back to Users':'Back to Teams',exact:true}).waitFor()
   await expect.poll(()=>scroll.evaluate(e=>e.scrollTop)).toBe(0)
   await page.getByRole('button',{name:tab==='users'?'Back to Users':'Back to Teams',exact:true}).click()
   await page.getByText('Research 0000',{exact:true}).waitFor();await expect.poll(()=>scroll.evaluate(e=>e.scrollTop)).toBe(top)
   await shot(tab+'-restored-detail')
  }
  await page.setViewportSize({width:320,height:900})
  await page.locator('.admin-table-region').scrollIntoViewIfNeeded();assert.ok(await page.locator('.admin-table-region').evaluate(e=>e.scrollWidth<=e.clientWidth+1))
  await shot(tab+'-mobile-summary')
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push({evidence:'All 503 users, teams and certification records exported with metadata. User/team detail return restores the originating list position. Mobile summaries preserve records and controls.'})
} catch(error){await review.capture('inventory-export-blocked',String(error));throw error}finally{await review.flush();await review.browser.close()}
