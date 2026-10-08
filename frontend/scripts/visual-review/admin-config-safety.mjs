import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL}),{page}=review
let failures=new Set(),configWrites=[],providerWrites=0
const model={id:'model-1',name:'Research model',tag:'research-model',external:true,thinking:false,api_protocol:'openai',endpoint:'https://model.institution.example.test/v1',api_key:'***',context_window:128000}
const config={extraction_config:{mode:'one_pass',one_pass:{thinking:true,structured_output:true,model:'Research model'},chunking:{enabled:false,max_keys_per_chunk:10},repetition:{enabled:false},use_images:false},quality_config:{verification_gates:{require_validation:false,min_extraction_accuracy:.7,min_extraction_consistency:.8,min_workflow_grade:'C'},quality_tiers:{excellent:{min_score:90},good:{min_score:70},fair:{min_score:50}}},auth_methods:['password','oauth'],oauth_providers:[{id:'provider-1',provider:'oauth',display_name:'Campus identity',client_id:'institutional-client',redirect_uri:'https://institution.example.test/auth/callback'}],available_models:[model],default_model:model.name,ocr_endpoint:'https://ocr.institution.example.test',outbound_url_allowed_hosts:[],ocr_api_key:'***',web_search_provider:'',web_search_endpoint:'',web_search_api_key:'',ocr_provider:'raw',ocr_options:{},ocr_async:false,ocr_timeout_seconds:120,llm_endpoint:'',highlight_color:'#eab308',ui_radius:'12px',default_team_id:'',compliance_config:{enabled:false,check_on_upload:true,rules:'',chunk_size:8000,chunk_overlap:200},retention_config:{enabled:false,policies:{}},support_contacts:[]}
const fixed={'/api/auth/me':{id:'reviewer',user_id:'reviewer',email:'reviewer@example.test',name:'Alex Morgan',is_admin:true,is_staff:true,current_team:'team-1'},'/api/auth/config':{auth_methods:['password'],oauth_providers:[],trial_system_enabled:false},'/api/admin/system/version':{current:'5.0.0',update_available:false},'/api/admin/catalog/status':{update_available:false},'/api/admin/telemetry/optin':{show_banner:false},'/api/admin/readiness':{ready:true,blockers_remaining:0,items:[]},'/api/admin/readiness/ocr':{item:null,probe:{ok:true}},'/api/admin/config':config}
await page.route('**/api/**',async r=>{const p=new URL(r.request().url()).pathname.replace(/\/$/,''),m=r.request().method();if(failures.has(m+' '+p))return r.fulfill({status:503,json:{detail:'Configuration service unavailable. Retry this request.'}});if(p==='/api/admin/config'&&m==='PUT'){const body=r.request().postDataJSON();configWrites.push(body);if(body.support_contacts)config.support_contacts=body.support_contacts;return r.fulfill({json:{status:'ok'}})};if(p==='/api/admin/config/auth/providers/provider-1'&&m==='PUT'){providerWrites++;config.oauth_providers[0]={...config.oauth_providers[0],...r.request().postDataJSON()};failures.add('GET /api/admin/config');return r.fulfill({json:{status:'ok'}})};if(p==='/api/admin/config/compliance'&&m==='PUT')return r.fulfill({json:r.request().postDataJSON()});if(p==='/api/admin/users')return r.fulfill({json:{items:[],total:0,capped:false}});if(p in fixed)return r.fulfill({json:fixed[p]});return r.fallback()})
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id+': page overflow');assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': accessibility');const overflow=await page.locator('.section-page__content').evaluate(root=>[...root.querySelectorAll('div,p,fieldset')].filter(e=>e.clientWidth>50&&e.clientHeight>0&&e.scrollWidth>e.clientWidth+3&&getComputedStyle(e).overflowX==='visible'&&!e.closest('.admin-table-region')).map(e=>({width:e.clientWidth,content:e.scrollWidth,text:e.textContent?.slice(0,60)})));assert.deepEqual(overflow,[],id+': nested overflow');console.log('Captured '+id)}
try {
 for (const width of [320, 1440]) {
  await page.setViewportSize({width,height:900})
  await page.goto(review.baseURL+'/admin?tab=config')
  await page.getByRole('button',{name:'Save Theme'}).waitFor()
  assert.equal(await page.getByText(/Unsaved changes:/).count(),0)
  await page.getByRole('checkbox',{name:'Activate compliance checks'}).check()
  await page.getByRole('button',{name:'Save Processing Settings'}).first().click()
  await page.getByText('Processing settings saved.',{exact:true}).first().waitFor()
  await page.getByText(/Unsaved changes: Compliance/).waitFor()
  await shot('save-scope-'+width)
  await page.getByRole('button',{name:'Save Compliance Settings'}).click()
  await page.getByText(/Unsaved changes:/).waitFor({state:'hidden'})
  const field=page.getByRole('spinbutton',{name:'Excellent score threshold'})
  await field.fill('150')
  const before=configWrites.length
  await page.getByRole('button',{name:'Save Processing Settings'}).last().click()
  assert.equal(await field.getAttribute('aria-invalid'),'true')
  assert.equal(await field.evaluate(el=>document.activeElement===el),true)
  assert.equal(configWrites.length,before)
  await shot('invalid-threshold-'+width)
  await field.fill('95')
  if(width===320) await page.getByRole('combobox',{name:'Section',exact:true}).selectOption('users'); else await page.getByRole('button',{name:'Users',exact:true}).click()
  await page.getByRole('dialog',{name:'Discard unsaved configuration?'}).waitFor()
  await shot('discard-dialog-'+width)
  await page.getByRole('button',{name:'Keep editing',exact:true}).click()
  assert.equal(await field.inputValue(),'95')
  assert.equal(new URL(page.url()).searchParams.get('tab'),'config')
  if(width===320) await page.getByRole('combobox',{name:'Section',exact:true}).selectOption('users'); else await page.getByRole('button',{name:'Users',exact:true}).click()
  await page.getByRole('button',{name:'Discard and leave',exact:true}).click()
  await page.waitForURL('**/admin?tab=users')
 }
 assert.deepEqual(review.errors,[])
 assert.deepEqual([...review.unmatched],[])
 review.observations.push({evidence:'Processing save scope, separate compliance save, rejected threshold, focus, keep editing and explicit discard verified at 320 and 1440px. Synthetic API fixtures only.'})
 console.log('Configuration fixes passed at both widths')
} catch(error) { await review.capture('config-fix-blocked',String(error)); throw error } finally { await review.flush(); await review.browser.close() }
