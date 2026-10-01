import assert from 'node:assert/strict'
import { expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { optimization } from './fixtures.mjs'
const review=await createReview({output:process.env.REVIEW_OUTPUT,baseURL:process.env.REVIEW_BASE_URL})
const {page}=review
page.setDefaultTimeout(30000)
const stamp='2026-09-30T10:00:00Z'
const base={surface:'kb',run_uuid:'opt-review',item_id:'kb-1',item_name:'Research administration policies — proposal deadline and budget conditions',status:'completed',category:'needs_review',started_at:stamp,completed_at:stamp,score:0.8,baseline_score:0.65,trigger:'quality_alert',trigger_detail:{},tied_with_baseline:false,apply_preview:optimization.apply_preview,suggestion_count:0,applied_at:null,reverted_at:null,is_live:false,can_manage:true,dismissed_at:null,error_message:null,error_code:null,error_context:null,stopped_reason:null,phase:null,progress_message:null,judge_model:'Review grader',overfitting_warning:true,link:'/?kb=kb-1'}
const seed=()=>[base,
 {...base,run_uuid:'failed',surface:'workflow',item_name:'Failed workflow tuning',category:'failed',status:'failed',score:null,error_code:'judge_unavailable',error_message:'The grader could not be reached. Open the workflow to review settings and retry.',apply_preview:null},
 {...base,run_uuid:'running',surface:'extraction',item_name:'Budget extraction tuning in progress',category:'in_flight',status:'running',score:null,progress_message:'Comparing candidate settings',apply_preview:null},
 {...base,run_uuid:'live',item_name:'Live policy configuration',category:'applied',is_live:true,applied_at:stamp},
 {...base,run_uuid:'reverted',item_name:'Reverted policy configuration',category:'applied',is_live:false,applied_at:stamp,reverted_at:stamp},
 {...base,run_uuid:'superseded',item_name:'Earlier applied configuration',category:'applied',is_live:false,applied_at:stamp},
 {...base,run_uuid:'no-change',item_name:'No measurable improvement',category:'no_change',score:0.65,tied_with_baseline:true,apply_preview:null},
 {...base,run_uuid:'cancelled',item_name:'Cancelled budget experiment',category:'cancelled',status:'cancelled',score:null,apply_preview:null},
 {...base,run_uuid:'readonly',item_name:'Shared policy collection — view only',can_manage:false},
 {...base,run_uuid:'dismissed',item_name:'Dismissed policy suggestion',category:'dismissed',dismissed_at:stamp},
].map(x=>({...x}))
let rows=seed(),failRead=true,failWrite=true,applyCalls=0
await page.route('**/api/optimizer/inbox*',r=>{
 if(failRead)return r.fulfill({status:503,json:{detail:'Suggestions unavailable'}})
 const show=new URL(r.request().url()).searchParams.get('include_dismissed')==='true';const items=rows.filter(x=>show||x.category!=='dismissed');const count=c=>items.filter(x=>x.category===c).length
 return r.fulfill({json:{items,counts:{total:items.length,needs_review:count('needs_review'),pending_review:count('needs_review'),failed:count('failed'),in_flight:count('in_flight'),applied:count('applied'),no_change:count('no_change'),dismissed:count('dismissed')},lookback_days:30}})
})
await page.route('**/api/optimizer/inbox/kb/*/*',r=>{const p=new URL(r.request().url()).pathname.split('/'),item=rows.find(x=>x.run_uuid===p[5]);if(failWrite)return r.fulfill({status:503,json:{detail:'Suggestion update unavailable'}});item.category=p[6]==='dismiss'?'dismissed':'needs_review';item.dismissed_at=p[6]==='dismiss'?stamp:null;return r.fulfill({json:{ok:true}})})
await page.route('**/api/knowledge/kb-1/optimize/opt-review/apply',r=>{applyCalls++;if(failWrite)return r.fulfill({status:503,json:{detail:'Apply unavailable. Please retry.'}});Object.assign(rows[0],{category:'applied',applied_at:stamp,is_live:true});return r.fulfill({json:{ok:true,applied_config:optimization.best_config,previous_override:null,applied_at:stamp}})})
async function shot(id){await review.capture(id);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),id+': page overflow');assert.deepEqual(JSON.parse(await readFile(resolve(review.out,id+'.axe.json'),'utf8')),[],id+': accessibility');console.log('Captured '+id)}
const row=name=>page.getByRole('article').filter({hasText:name})
try{
 for(const width of [320,1440]){
  rows=seed();failRead=true;failWrite=true;applyCalls=0;await page.setViewportSize({width,height:width===320?740:1000});await page.goto(review.baseURL+'/tuning');await page.getByRole('button',{name:'Retry',exact:true}).waitFor();failRead=false;await page.getByRole('button',{name:'Retry',exact:true}).click()
  await row(base.item_name).waitFor();await shot('tuning-populated-'+width)
  assert.equal(await row('Shared policy collection — view only').getByRole('button').count(),0)
  await expect(row('Live policy configuration')).toContainText('Live on this item');await expect(row('Earlier applied configuration')).toContainText('not the current live configuration');await expect(row('Reverted policy configuration')).toContainText('Reverted')
  await row(base.item_name).getByRole('button',{name:'Review & apply',exact:true}).click();const dialog=page.getByRole('dialog');await dialog.waitFor();await shot('tuning-comparison-'+width)
  const apply=dialog.getByRole('button',{name:'Apply',exact:true});assert.equal(await apply.isDisabled(),true);await dialog.getByRole('checkbox').check();await apply.click();await page.getByText('Apply unavailable. Please retry.',{exact:true}).waitFor();assert.equal(applyCalls,1);await expect(dialog.getByRole('checkbox')).toBeChecked();await shot('tuning-apply-recovery-'+width)
  failWrite=false;await apply.click();await dialog.waitFor({state:'hidden'});await expect(row(base.item_name)).toContainText('Live on this item');assert.equal(applyCalls,2);await shot('tuning-applied-'+width)
  await page.getByRole('checkbox',{name:'Show dismissed',exact:true}).check();const dismissed=row('Dismissed policy suggestion');await dismissed.getByRole('button',{name:'Restore',exact:true}).waitFor();failWrite=true;await dismissed.getByRole('button',{name:'Restore',exact:true}).click();await page.getByText('Suggestion update unavailable',{exact:true}).waitFor();await dismissed.getByRole('button',{name:'Restore',exact:true}).waitFor();failWrite=false;await dismissed.getByRole('button',{name:'Restore',exact:true}).click();await dismissed.getByRole('button',{name:'Dismiss',exact:true}).waitFor();await dismissed.getByRole('button',{name:'Dismiss',exact:true}).click();await dismissed.getByRole('button',{name:'Restore',exact:true}).waitFor();await shot('tuning-dismissed-restored-'+width)
 }
 assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
 review.observations.push('Synthetic lifecycle and UI-state evidence: mixed tuning categories, comparison/regression acknowledgement, failed apply and exact retry count, live/not-live/reverted labels, dismiss/restore recovery, view-only actions hidden. Real configured-item persistence and backend permission enforcement remain separately open.')
}catch(error){await review.capture('tuning-blocked',String(error));throw error}finally{await review.flush();await review.browser.close()}
