import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
let failMore = true
const requests = []
const teams = Array.from({length: 503}, (_, i) => ({team_id: `team-${i}`, uuid: `team-${i}`, name: `Research team ${String(i).padStart(4, '0')}`, owner_user_id: 'reviewer', member_count: 1, is_default: false}))
const certs = Array.from({length: 503}, (_, i) => ({user_id: `learner-${i}`, progress_id: `p-${i}`, name: `Learner ${String(i).padStart(4, '0')}`, email: `learner-${i}@example.test`, level: 'novice', total_xp: 0, modules_completed: 0, modules_total: 10, certified: false, unlocked: false, can_unlock: false, course_title: 'Preserved course', course_version: 'legacy', is_active: false}))
const fixed = {'/api/auth/me': {id:'reviewer', user_id:'reviewer', email:'reviewer@example.test', name:'Alex Morgan', is_admin:true, is_staff:true, current_team:'team-1'}, '/api/auth/config': {auth_methods:['password'],oauth_providers:[],trial_system_enabled:false}, '/api/admin/system/version':{current:'5.0.0',update_available:false}, '/api/admin/catalog/status':{update_available:false}, '/api/admin/telemetry/optin':{show_banner:false}, '/api/admin/users/isolated':{items:[],total:0,capped:false}}
await page.route('**/api/**', async route => {
 const url = new URL(route.request().url()), path = url.pathname.replace(/\/$/,'')
 if(path in fixed) return route.fulfill({json:fixed[path]})
 if(path === '/api/admin/teams/all' || path === '/api/admin/certifications') {
   const offset=Number(url.searchParams.get('offset')||0), limit=Number(url.searchParams.get('limit')||500), q=(url.searchParams.get('q')||'').toLowerCase()
   requests.push({path,offset,q})
   if(path.endsWith('/teams/all') && offset && failMore) { failMore=false; return route.fulfill({status:503,json:{detail:'Temporary inventory failure'}}) }
   const items=(path.endsWith('/teams/all') ? teams : certs).filter(row=>!q || row.name.toLowerCase().includes(q))
   return route.fulfill({json:{items:items.slice(offset,offset+limit),total:items.length,capped:offset+limit<items.length}})
 }
 return route.fallback()
})
async function shot(id) { await review.capture(id); assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[]); assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)) }
try {
 await page.setViewportSize({width:390,height:844})
 await page.goto(review.baseURL+'/admin?tab=teams')
 await page.getByRole('button',{name:'Research team 0499',exact:true}).waitFor()
 await page.getByRole('button',{name:'Load more teams',exact:true}).click()
 await page.getByRole('alert').filter({hasText:'Temporary inventory failure'}).waitFor()
 assert.equal(await page.getByRole('button',{name:'Research team 0499',exact:true}).count(),1)
 await page.getByRole('button',{name:'Load more teams',exact:true}).click()
 await page.getByRole('button',{name:'Research team 0502',exact:true}).scrollIntoViewIfNeeded()
 await shot('teams-beyond-cap-390')
 await page.goto(review.baseURL+'/admin?tab=certifications')
 await page.getByText('Learner 0000',{exact:true}).waitFor()
 await page.getByRole('button',{name:'Next page',exact:true}).click()
 await page.getByText('Learner 0100',{exact:true}).waitFor()
 await page.getByPlaceholder(/Search users/).fill('0502')
 await page.getByRole('button',{name:'Search all records',exact:true}).click()
 await page.getByText('Learner 0502',{exact:true}).waitFor()
 assert.ok(requests.some(r=>r.path.endsWith('/certifications')&&r.offset===0&&r.q==='0502'))
 await shot('certification-global-search-390')
 assert.deepEqual(review.errors,[]); assert.deepEqual([...review.unmatched],[])
 review.observations.push({requests,evidence:'503 synthetic teams/certification records; late team reached after retry; enrollment search reaches outside the initial page.'})
 console.log('Large inventory paging, retry, and global certification search passed')
} catch(error) { await review.capture('inventory-blocked',String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
