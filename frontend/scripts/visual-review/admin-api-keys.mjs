import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page}=review
let failures=new Set(), created=false, revoked=false, creates=0
const stamp='2026-09-30T10:00:00Z',name='Research administration reporting service'
const key={id:'key-1',name,prefix:'synthetic_test',scopes:['metrics:read','documents:read'],description:'Synthetic test fixture',created_by:'reviewer',created_at:stamp,expires_at:null,revoked_at:null,last_used_at:stamp,last_used_ip:'192.0.2.1'}
const fixed={'/api/auth/me':{id:'reviewer',user_id:'reviewer',email:'reviewer@example.test',name:'Alex Morgan',is_admin:true,is_staff:true,current_team:'team-1'},'/api/auth/config':{auth_methods:['password'],oauth_providers:[],trial_system_enabled:false},'/api/admin/system/version':{current:'5.0.0',update_available:false},'/api/admin/catalog/status':{update_available:false},'/api/admin/telemetry/optin':{show_banner:false}}
await page.route('**/api/**',async r=>{
 const p=new URL(r.request().url()).pathname.replace(/\/$/,''),method=r.request().method()
 if(p==='/api/admin/api-keys'&&method==='POST')creates++
 if(failures.has(method+' '+p))return r.fulfill({status:503,json:{detail:'Service temporarily unavailable. Retry this request.'}})
 if(p==='/api/admin/api-keys'&&method==='POST'){created=true;return r.fulfill({json:{...key,token:'synthetic-token-not-a-real-secret'}})}
 if(p==='/api/admin/api-keys/key-1'&&method==='DELETE'){revoked=true;return r.fulfill({json:{ok:true}})}
 if(p==='/api/admin/api-keys')return r.fulfill({json:created&&!revoked?[key]:[]})
 if(p==='/api/admin/api-keys/docs')return r.fulfill({json:{markdown:'# Management API\n\nRead selected research records using scoped credentials.\n\n```sh\ncurl --header "X-API-Key: YOUR_TOKEN" https://institution.example.test/api/mgmt/v1/metrics\n```'}})
 if(p in fixed)return r.fulfill({json:fixed[p]})
 return r.fallback()
})
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id+': page overflow');assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': accessibility');console.log('Captured '+id)}
try{
 for(const width of [320,1440]){
  await page.setViewportSize({width,height:width===320?740:1000});created=false;revoked=false
  failures=new Set(['GET /api/admin/api-keys']);await page.goto(review.baseURL+'/admin?tab=apikeys');await page.getByRole('button',{name:'Retry API keys'}).waitFor();await shot('keys-read-error-'+width);failures.clear();await page.getByRole('button',{name:'Retry API keys'}).click();await page.getByText(/No API keys yet/).waitFor()
  const open=page.getByRole('button',{name:'New key',exact:true});await open.focus();await page.keyboard.press('Enter');await page.getByLabel('Name',{exact:true}).fill(name);await page.getByLabel('Description (optional)').fill('Budget reporting only');await page.getByLabel('documents:read',{exact:true}).check()
  failures.add('POST /api/admin/api-keys');const before=creates;await page.getByRole('button',{name:'Create key',exact:true}).click();await page.getByRole('alert').waitFor();assert.equal(await page.getByLabel('Name',{exact:true}).inputValue(),name);await shot('keys-create-retained-'+width);failures.clear();await page.getByRole('button',{name:'Create key',exact:true}).click();await page.getByRole('dialog',{name:'Copy your token now'}).waitFor();assert.equal(creates,before+2)
  await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw new Error('Clipboard unavailable')}}}));await page.getByRole('button',{name:'Copy token',exact:true}).click();await page.getByText(/Could not copy. Select the token/).waitFor();await shot('keys-token-copy-error-'+width);await page.keyboard.press('Escape');await page.getByRole('dialog').waitFor({state:'hidden'});await page.getByRole('region',{name:'Management API keys'}).waitFor();await shot('keys-populated-'+width)
  failures.add('DELETE /api/admin/api-keys/key-1');await page.getByRole('button',{name:'Revoke API key '+name}).click();await page.getByRole('button',{name:'Confirm',exact:true}).click();await page.getByRole('button',{name:'Dismiss error'}).waitFor();assert.equal(revoked,false);await page.getByRole('button',{name:'Dismiss error'}).click();failures.clear();await page.getByRole('button',{name:'Revoke API key '+name}).click();await page.getByRole('button',{name:'Confirm',exact:true}).click();await page.getByText(/No API keys yet/).waitFor();assert.equal(revoked,true)
  failures.add('GET /api/admin/api-keys/docs');const docs=page.getByRole('button',{name:'View documentation',exact:true});await docs.click();await page.getByRole('button',{name:'Retry documentation'}).waitFor();failures.clear();await page.getByRole('button',{name:'Retry documentation'}).click();await page.getByRole('heading',{name:'Management API',exact:true}).waitFor();await shot('keys-documentation-'+width);await page.keyboard.press('Escape');assert.equal(await docs.evaluate(el=>el===document.activeElement),true)
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push({evidence:'Synthetic API key read/create/revoke and docs recovery; retained draft, clipboard failure and keyboard modal return. No real credentials created or revoked.'})
}catch(error){await review.capture('keys-blocked',String(error));throw error}finally{await review.flush();await review.browser.close()}
