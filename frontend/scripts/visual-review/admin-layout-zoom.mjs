import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
const stamp='2026-09-30T10:00:00Z'
const stats={conversations:18,search_runs:12,workflows_started:10,workflows_completed:7,workflows_failed:2,tokens_in:14000,tokens_out:4000,active_users:3,active_teams:1}
const users=Array.from({length:12},(_,i)=>({user_id:`user-${i}`,name:i===0?'Alexandra Montgomery — Research Development and Sponsored Programs':`Research colleague ${i}`,email:`research.administrator.${i}@institution.example.test`,is_admin:false,is_staff:false,is_examiner:i===1,tokens_total:18000-i*100,workflows_run:10,conversations:18,last_active:stamp}))
const events=['failed','completed','running','queued','canceled'].map((status,i)=>({id:`event-${i}`,status,title:`Review proposal requirements, cost sharing and budget justification for the coastal resilience renewal ${i}`,user_id:'user-0',user_name:users[0].name,user_email:users[0].email,team_id:'team-1',team_name:'Research administration — cross-institution award review',started_at:stamp,finished_at:status==='running'?null:stamp,duration_ms:43000,tokens_in:1400,tokens_out:400,steps_completed:status==='completed'?3:1,steps_total:3,error:status==='failed'?'The budget source could not be read. Open the source and retry the run after processing finishes.':null}))
let failUsers=false,failDetail=false,failHistory=false,failEvents=false,empty=false,denied=false
await page.route('**/api/auth/config',r=>r.fulfill({json:{auth_methods:['password'],oauth_providers:[],trial_system_enabled:false}}))
await page.route('**/api/admin/system/version',r=>r.fulfill({json:{current:'5.0.0',update_available:false}}))
await page.route('**/api/admin/usage?*',r=>r.fulfill({json:stats}))
await page.route('**/api/admin/usage/timeseries?*',r=>r.fulfill({json:{days:[{date:'2026-09-30',...stats}],previous_period:stats}}))
await page.route('**/api/admin/users?*',r=>failUsers?r.fulfill({status:503,json:{detail:'User records unavailable'}}):r.fulfill({json:{items:empty?[]:users,total:12,capped:false}}))
await page.route('**/api/admin/users/user-0/detail?*',r=>failDetail?r.fulfill({status:503,json:{detail:'User details unavailable'}}):r.fulfill({json:{...users[0],...stats,document_count:12,timeseries:[{date:'2026-09-30',...stats}],previous_period:stats,recent_workflows:events}}))
await page.route('**/api/admin/users/user-0/history?*',r=>failHistory?r.fulfill({status:503,json:{detail:'History unavailable'}}):r.fulfill({json:{items:[{timestamp:stamp,source:'activity',action:'workflow.failed',title:events[0].title,resource_type:'workflow',resource_id:'workflow-1',status:'failed',ip_address:null,detail:{}}],total:1,capped:false}}))
await page.route('**/api/admin/workflows?*',r=>{if(failEvents)return r.fulfill({status:denied?403:503,json:{detail:denied?'Access to these records was denied.':'Workflow records unavailable'}});const url=new URL(r.request().url()),status=url.searchParams.get('status'),q=url.searchParams.get('search');const items=empty?[]:events.filter(e=>(!status||e.status===status)&&(!q||e.title.includes(q)));return r.fulfill({json:{items,total:items.length,page:1,pages:1,summary:empty?null:{total:5,completed:1,failed:1,running:1,success_rate:20,avg_duration_ms:43000,total_tokens:9000}}})})

try {
  await page.setViewportSize({ width: 1280, height: 1000 })
  for (const tab of ['users', 'workflows', 'usage']) {
    await page.goto(review.baseURL + '/admin?tab=' + tab)
    await review.setBrowserZoom(2)
    await page.locator('.admin-section-intro').waitFor()
    if (tab === 'users') await page.getByRole('button',{name:/^View Alexandra/}).waitFor()
    if (tab === 'workflows') await page.getByRole('button',{name:/Details for.*failed$/}).waitFor()
    const region = page.getByRole('region').filter({has: page.locator('table')}).first()
    if (await region.count()) await region.scrollIntoViewIfNeeded()
    await review.capture('zoom-' + tab)
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), tab)
    assert.deepEqual(JSON.parse(await readFile(resolve(review.out, 'zoom-' + tab + '.axe.json'), 'utf8')), [])
  }
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
} finally { await review.flush(); await review.browser.close() }
