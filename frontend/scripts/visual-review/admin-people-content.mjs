import assert from 'node:assert/strict'
import { expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page}=review
page.setDefaultTimeout(30000);page.setDefaultNavigationTimeout(30000)
const stamp='2026-09-30T10:00:00Z'
let isAdmin=true,failRead=true,failWrite=true,empty=false,writes=[]
const person={user_id:'user-1',name:'Alexandra Montgomery — Sponsored Programs and Research Development',email:'alexandra.montgomery@institution.example.test'}
const team={team_id:'team-1',uuid:'team-1',name:'Research administration — cross-institution award review',owner_user_id:'reviewer',member_count:2,is_default:true}
const stats={conversations:18,search_runs:12,workflows_started:10,workflows_completed:7,workflows_failed:2,tokens_in:14000,tokens_out:4000,active_users:3,active_teams:1}
const progress={...person,level:'apprentice',total_xp:1200,modules_completed:4,modules_total:10,certified:false,certified_at:null,last_activity_date:'2026-09-30',unlocked:false,updated_at:stamp}
const kb={uuid:'kb-admin',title:'Sponsor policies and institutional budget justification requirements — 2027 edition',status:'ready',verified:true,tags:['Policy','Research'],total_sources:14,total_chunks:234,owner_id:'user-1',owner_email:person.email,team_id:'team-1',team_name:team.name,created_at:stamp,updated_at:stamp}
const org={uuid:'org-1',name:'University Research Administration and Sponsored Programs',org_type:'university',parent_id:null,metadata:{},created_at:stamp,updated_at:stamp,user_count:1,team_count:1,children:[{uuid:'org-2',name:'College of Environmental Science and Coastal Resilience',org_type:'college',parent_id:'org-1',metadata:{},created_at:stamp,updated_at:stamp,user_count:0,team_count:0,children:[]}]}
const movingChild=org.children[0]
const otherOrg={...org,uuid:'org-3',name:'Partner Research University',user_count:0,team_count:0,children:[]}
await page.route('**/api/auth/me',r=>r.fulfill({json:{id:'reviewer',user_id:'reviewer',email:'reviewer@example.test',name:'Alex Morgan',is_admin:isAdmin,is_staff:!isAdmin,is_examiner:false,is_support_agent:false,is_demo_user:false,current_team:'team-1',current_team_uuid:'team-1',sso_provider:null}}))
const fixed={
 '/api/auth/config':{auth_methods:['password'],oauth_providers:[],trial_system_enabled:false},
 '/api/admin/system/version':{current:'5.0.0',update_available:false},
 '/api/admin/catalog/status':{update_available:false},'/api/admin/telemetry/optin':{show_banner:false},
 '/api/admin/usage':stats,'/api/admin/usage/timeseries':{days:[],previous_period:stats},
 '/api/admin/teams/all':{items:[team],total:1,capped:false},'/api/admin/users/isolated':{items:[person],total:1,capped:false},
 '/api/admin/teams':{items:[{...team,tokens_total:18000,workflows_completed:7,active_users:2,avg_latency_ms:43000}],total:1,capped:false},
 '/api/admin/teams/team-1/detail':{...team,...stats,document_count:14,timeseries:[{date:'2026-09-30',...stats}],previous_period:stats,members:[{...person,role:'member',tokens_total:18000,workflows_run:10,conversations:18,last_active:stamp}],recent_workflows:[]},
 '/api/verification/examiners/search':{users:[person]},
}
await page.route('**/api/**',async r=>{
 const p=new URL(r.request().url()).pathname.replace(/\/$/,'');const method=r.request().method()
 if(method!=='GET'&&(p.startsWith('/api/admin/')||p.startsWith('/api/organizations/')||p==='/api/knowledge/kb-admin/update')){
  writes.push({path:p,data:r.request().postDataJSON()});if(failWrite)return r.fulfill({status:503,json:{detail:'Change unavailable. Please retry.'}})
  if(p==='/api/knowledge/kb-admin/update')kb.title=r.request().postDataJSON().title
  if(p==='/api/admin/certifications/user-1/unlock'){progress.unlocked=r.request().postDataJSON().unlocked;return r.fulfill({json:{user_id:'user-1',unlocked:progress.unlocked}})}
  if(p==='/api/organizations/org-1')org.name=r.request().postDataJSON().name
  if(p==='/api/organizations/org-2/move'){org.children=[];movingChild.parent_id='org-3';otherOrg.children=[movingChild]}
  return r.fulfill({json:{ok:true,...(p==='/api/knowledge/kb-admin/update'?kb:{})}})
 }
 if(['/api/admin/knowledge-bases','/api/admin/certifications','/api/teams/team-1/members','/api/organizations/tree','/api/organizations/org-1/members'].includes(p)){
  if(failRead)return r.fulfill({status:503,json:{detail:'Records temporarily unavailable'}})
  const payload=p==='/api/admin/knowledge-bases'?{knowledge_bases:empty?[]:[kb],total:empty?0:1}:p==='/api/admin/certifications'?{items:empty||new URL(r.request().url()).searchParams.get('q')==='missing-person'?[]:[progress],total:empty||new URL(r.request().url()).searchParams.get('q')==='missing-person'?0:1,capped:false}:p==='/api/teams/team-1/members'?[{...person,role:'member'}]:p==='/api/organizations/tree'?{tree:empty?[]:[org,otherOrg]}:{users:[person],teams:[team]}
  return r.fulfill({json:payload})
 }
 if(p in fixed)return r.fulfill({json:fixed[p]})
 return r.fallback()
})
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id+': page overflow');const nested=await page.locator('.section-page__content').evaluate(root=>[...root.querySelectorAll('div,p,fieldset')].filter(e=>e.clientWidth>50&&e.clientHeight>0&&e.scrollWidth>e.clientWidth+3&&getComputedStyle(e).overflowX==='visible'&&!e.closest('.admin-table-region')).map(e=>({tag:e.tagName,class:e.className,width:e.clientWidth,content:e.scrollWidth,text:e.textContent?.slice(0,80)})));assert.deepEqual(nested,[],id+': uncontained nested overflow');assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': accessibility');console.log('Captured '+id)}
async function go(tab){await page.goto(review.baseURL+'/admin?tab='+tab)}
try{
 for(const width of [320,1440]){
  await page.setViewportSize({width,height:width===320?740:1000});isAdmin=true;empty=false;failRead=true;failWrite=true;org.children=[movingChild];movingChild.parent_id='org-1';otherOrg.children=[]
  await go('knowledgebases');await page.getByRole('alert').filter({hasText:'Records'}).waitFor();failRead=false;await page.getByRole('button',{name:'Refresh',exact:true}).click()
  await page.getByRole('button',{name:/^Rename Sponsor/}).waitFor();await shot('admin-kb-inventory-'+width)
  const title=kb.title;await page.getByRole('button',{name:`Rename ${title}`,exact:true}).click();await page.getByRole('textbox',{name:'Knowledge base title',exact:true}).fill(title+' revised')
  await page.getByRole('button',{name:`Save title for ${title}`,exact:true}).click();await page.getByRole('alert').filter({hasText:'Change unavailable'}).waitFor();assert.equal(await page.getByRole('textbox',{name:'Knowledge base title'}).inputValue(),title+' revised');await shot('admin-kb-rename-recovery-'+width)
  failWrite=false;await page.getByRole('button',{name:`Save title for ${title}`,exact:true}).click();await page.getByRole('button',{name:`Rename ${title} revised`,exact:true}).waitFor();await expect(page.getByRole('button',{name:`Rename ${title} revised`,exact:true})).toBeFocused()
  failRead=true;await go('certifications');await page.getByRole('alert').filter({hasText:'Records'}).waitFor();failRead=false;await page.getByRole('button',{name:'Refresh',exact:true}).click();await page.getByText('4/10',{exact:true}).waitFor();await shot('admin-certifications-'+width)
  progress.unlocked=false;failWrite=true
  await page.getByRole('button',{name:`Unlock prerequisites for ${person.name}`,exact:true}).click()
  await page.getByRole('textbox',{name:'Reason for access change'}).fill('Synthetic administrator recovery')
  await page.getByRole('button',{name:'Save access change',exact:true}).click()
  await page.getByRole('alert').filter({hasText:'Change unavailable'}).waitFor()
  failWrite=false;await page.getByRole('button',{name:'Retry same access change',exact:true}).click()
  await page.getByRole('button',{name:`Re-lock prerequisites for ${person.name}`,exact:true}).click()
  await page.getByRole('textbox',{name:'Reason for access change'}).fill('Restore prerequisite checks after review')
  await page.getByRole('button',{name:'Save access change',exact:true}).click()
  await page.getByRole('button',{name:`Unlock prerequisites for ${person.name}`,exact:true}).waitFor()
  await page.getByRole('textbox',{name:'Search users or courses...',exact:true}).fill('missing-person')
  await page.getByRole('button',{name:'Search all records',exact:true}).click()
  await page.getByText('No records match this search.',{exact:true}).waitFor()
  failRead=true;await go('teams');await page.getByRole('button',{name:team.name,exact:true}).click();await page.getByRole('button',{name:'Retry members',exact:true}).waitFor();failRead=false;await page.getByRole('button',{name:'Retry members',exact:true}).click();await page.getByRole('button',{name:`Remove ${person.name} from ${team.name}`,exact:true}).waitFor();await shot('admin-team-members-'+width)
  failWrite=true;await page.getByRole('textbox',{name:`Add user to ${team.name}`,exact:true}).fill('new.researcher@example.test');await page.getByRole('button',{name:'Add',exact:true}).click();await page.getByText('Change unavailable. Please retry.',{exact:true}).waitFor();assert.equal(await page.getByRole('textbox',{name:`Add user to ${team.name}`,exact:true}).inputValue(),'new.researcher@example.test')
  await page.getByRole('tab',{name:'Usage Stats',exact:true}).click();await page.getByRole('button',{name:`View team usage: ${team.name}`,exact:true}).click();await page.getByText('Members (1)',{exact:true}).waitFor();await shot('admin-team-usage-'+width)
  await page.getByRole('button',{name:'Back to Teams',exact:true}).click();await page.getByRole('tab',{name:/Isolated Users/}).click();await page.getByRole('combobox',{name:`Team for ${person.name}`,exact:true}).selectOption('team-1');await shot('admin-isolated-users-'+width)
  failRead=true;await go('organizations');await page.getByRole('button',{name:'Retry organizations',exact:true}).waitFor();failRead=false;await page.getByRole('button',{name:'Retry organizations',exact:true}).click();await page.getByRole('button',{name:`Manage ${org.name}`,exact:true}).waitFor();await shot('admin-organizations-'+width)
  failRead=true;await page.getByRole('button',{name:`Manage ${org.name}`,exact:true}).click();await page.getByRole('button',{name:'Retry members',exact:true}).waitFor();failRead=false;await page.getByRole('button',{name:'Retry members',exact:true}).click();await page.getByRole('button',{name:`Remove ${person.name} from ${org.name}`,exact:true}).waitFor();await shot('admin-org-members-'+width)
  const orgName=org.name;await page.getByRole('button',{name:`Rename ${orgName}`,exact:true}).click();await page.getByRole('textbox',{name:'Organization name',exact:true}).fill(orgName+' revised');failWrite=true;await page.getByRole('button',{name:'Save',exact:true}).click();await page.getByText('Change unavailable. Please retry.',{exact:true}).waitFor();assert.equal(await page.getByRole('textbox',{name:'Organization name',exact:true}).inputValue(),orgName+' revised');failWrite=false;await page.getByRole('button',{name:'Save',exact:true}).click();await page.getByRole('button',{name:`Manage ${orgName} revised`,exact:true}).waitFor()
  await page.getByRole('button',{name:`Move ${movingChild.name}`,exact:true}).focus();await page.keyboard.press('Enter');const parentSelect=page.getByRole('combobox',{name:'New parent',exact:true});assert.equal(await parentSelect.locator('option[value="org-2"]').count(),0);await parentSelect.selectOption('org-3');failWrite=true;await page.getByRole('button',{name:'Move organization',exact:true}).click();await page.getByText('Change unavailable. Please retry.',{exact:true}).waitFor();assert.equal(await parentSelect.inputValue(),'org-3');await shot('admin-org-keyboard-move-'+width);failWrite=false;await page.getByRole('button',{name:'Move organization',exact:true}).click();await page.getByRole('button',{name:'Move organization',exact:true}).waitFor({state:'hidden'});assert.equal(movingChild.parent_id,'org-3')
  await page.getByRole('button',{name:'Import CSV',exact:true}).click();const dialog=page.getByRole('dialog',{name:'Import Organization Structure',exact:true});await dialog.waitFor();await dialog.locator('input[type=file]').setInputFiles({name:'organizations.csv',mimeType:'text/csv',buffer:Buffer.from('name,parent\nSynthetic University,\nSynthetic College,Synthetic University')});await dialog.getByRole('textbox',{name:'Organization name in row 1',exact:true}).waitFor();await shot('admin-org-import-'+width)
  failWrite=true;await dialog.getByRole('button',{name:'Import 2 Organizations',exact:true}).click();await dialog.getByText('Change unavailable. Please retry.',{exact:true}).waitFor();assert.equal(await dialog.getByRole('textbox',{name:'Organization name in row 1',exact:true}).inputValue(),'Synthetic University');await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});await expect(page.getByRole('button',{name:'Import CSV',exact:true})).toBeFocused()
 }
 isAdmin=false;failRead=false;await go('knowledgebases');await page.getByText('Read-only (renaming requires full admin).',{exact:false}).waitFor();assert.equal(await page.getByRole('button',{name:/^Rename /}).count(),0)
 await go('teams');await page.getByRole('button',{name:team.name,exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:/^Set default team:|^Remove default team:/}).count(),0);await shot('admin-staff-team-permissions')
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push({evidence:'Synthetic local-only people/content Admin checks. Failed reads/writes, long records, rename, certification unlock/re-lock, member drilldowns, CSV import draft/focus, and staff affordances. No real memberships, messages or configuration changed.',writes})
}catch(error){await review.capture('admin-people-blocked',String(error));throw error}finally{await review.flush();await review.browser.close()}
