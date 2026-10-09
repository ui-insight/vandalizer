import assert from 'node:assert/strict'
import { expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
const from='2026-10-01T00:00:00Z',until='2026-10-08T00:00:00Z'
const stats={period_start:from,period_end:until,conversations:10,search_runs:5,workflows_started:53,workflows_completed:0,workflows_failed:53,tokens_in:300,tokens_out:200,active_users:2,active_teams:1}
const events=Array.from({length:53},(_,i)=>({id:`event-${i}`,title:`Failed research workflow ${String(i).padStart(3,'0')}`,status:'failed',user_id:'reviewer',user_name:'Research administrator',user_email:'reviewer@example.test',team_id:null,team_name:null,started_at:'2026-10-02T10:00:00Z',finished_at:'2026-10-02T10:01:00Z',duration_ms:60000,tokens_in:200,tokens_out:100,steps_completed:1,steps_total:3,error:'Provider connection failed. Retry after checking the saved endpoint.'}))
const requests=[]
let failExport=false
await page.route('**/api/**',async r=>{
 const url=new URL(r.request().url()),p=url.pathname.replace(/\/$/,'')
 if(p==='/api/auth/me')return r.fulfill({json:{id:'reviewer',user_id:'reviewer',name:'Alex Morgan',email:'reviewer@example.test',is_admin:true,is_staff:true,current_team:'team-1'}})
 if(p==='/api/auth/config')return r.fulfill({json:{auth_methods:['password'],oauth_providers:[],trial_system_enabled:false}})
 if(p==='/api/admin/system/version')return r.fulfill({json:{current:'5.0.0',update_available:false}})
 if(p==='/api/admin/catalog/status')return r.fulfill({json:{update_available:false}})
 if(p==='/api/admin/telemetry/optin')return r.fulfill({json:{show_banner:false}})
 if(p==='/api/admin/usage')return r.fulfill({json:stats})
 if(p==='/api/admin/usage/timeseries')return r.fulfill({json:{days:[],previous_period:stats}})
 if(p==='/api/admin/workflows'){
  const n=Number(url.searchParams.get('page')||1);requests.push(Object.fromEntries(url.searchParams))
  if(failExport&&n===2)return r.fulfill({status:503,json:{detail:'Export service unavailable'}})
  return r.fulfill({json:{items:events.slice((n-1)*50,n*50),total:53,page:n,pages:2,summary:{total:53,completed:0,failed:53,running:0,success_rate:0,avg_duration_ms:60000,total_tokens:15900}}})
 }
 return r.fallback()
})
async function shot(id){await review.capture(id);assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id)}
async function section(tab){if(page.viewportSize().width<900)await page.getByRole('combobox',{name:'Section',exact:true}).selectOption(tab);else await page.getByRole('button',{name:tab==='usage'?'Usage':'Workflows',exact:true}).click()}
try{
 for(const width of [1440,320]){
  await page.setViewportSize({width,height:900})
  await page.goto(review.baseURL+'/admin?tab=usage')
  const link=page.getByRole('link',{name:'Inspect 53 failed workflows in this window'})
  await link.waitFor();await link.click()
  await page.getByText(events[0].title,{exact:true}).waitFor()
  assert.equal(new URL(page.url()).searchParams.get('from'),from)
  assert.equal(requests.at(-1).started_before,until)
  assert.equal(requests.at(-1).status,'failed')
  if(width===320){
   const region=page.locator('.admin-table-region');assert.ok(await region.evaluate(e=>e.scrollWidth<=e.clientWidth+1))
   await page.locator('tbody tr').first().scrollIntoViewIfNeeded()
   await shot('workflow-mobile-summary')
   await page.getByRole('button',{name:'Table view',exact:true}).click()
   assert.ok(await region.evaluate(e=>e.scrollWidth>e.clientWidth))
   await page.locator('tbody tr').first().scrollIntoViewIfNeeded()
   await shot('workflow-mobile-table')
   await page.getByRole('button',{name:'Summary view',exact:true}).click()
  }
  await section('usage')
  await link.waitFor()
  await section('workflows')
  await page.getByText(events[0].title,{exact:true}).waitFor()
  const scroll=page.locator('#main-content').locator('..')
  await scroll.evaluate(e=>e.scrollTop=650)
  await expect.poll(()=>scroll.evaluate(e=>e.scrollTop)).toBe(650)
  // Browser Back/Forward changes sections without moving to the header first.
  await page.goBack()
  await link.waitFor()
  await page.goForward()
  await page.getByText(events[0].title,{exact:true}).waitFor()
  await expect.poll(()=>scroll.evaluate(e=>e.scrollTop)).toBe(650)
  assert.equal(requests.at(-1).started_after,from)
  const downloaded=page.waitForEvent('download')
  await page.getByRole('button',{name:'Export all matching records'}).click()
  const file=await downloaded;const csv=await readFile(await file.path(),'utf8')
  assert.ok(csv.includes(events[52].title));assert.ok(csv.includes('End exclusive (UTC)'));assert.ok(csv.includes(until))
  assert.equal(csv.trim().split('\n').length,54)
  failExport=true
  let unexpected=false;const onDownload=()=>{unexpected=true};page.on('download',onDownload)
  await page.getByRole('button',{name:'Export all matching records'}).click()
  await page.getByRole('alert').filter({hasText:'Export service unavailable'}).waitFor()
  assert.equal(unexpected,false);page.off('download',onDownload);failExport=false
  await shot('complete-export-recovery-'+width)
  await page.getByRole('button',{name:'Clear date range'}).click()
  await expect.poll(()=>requests.at(-1).started_after).toBe(undefined)
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push({requests,evidence:'Exact Usage failure links; date retention and scroll restoration; 53-row complete CSV with UTC filters; failed second page produces no partial download; mobile summaries and table toggle.'})
} catch(error){await review.capture('remaining-blocked',String(error));throw error} finally {await review.flush();await review.browser.close()}
