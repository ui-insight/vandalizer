import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { optimization, queries } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page, state } = review
page.setDefaultTimeout(20000)
state.validationQueries = true
state.optimization = true
let failComparison = false
const generation = []
const trial = { trial_id:'review-trial', config:optimization.best_config, score:0.8, judge_score:0.85, lift_vs_default:0.15, num_queries_judged:3, tokens_used:4200, status:'completed', duration_seconds:34, per_query_results:queries.map(q=>({ query_uuid:q.uuid, query:q.query+' Include the required documents, source references and submission requirements.', score:0.8, judge_score:0.8 })) }
const current = { ...optimization, trials:[trial], judge_model:'Evaluation model with a deliberately long descriptive name for reproducible comparisons', judge_prompt_version:'kb-judge-reviewed-questions-and-expected-source-references-v1', test_query_snapshot:{ query_uuids:queries.map(q=>q.uuid), total:3, expected_answer_hashes:{} } }
const previous = { ...current, uuid:'opt-earlier', optimized_score:0.6, trials:[{...trial,score:0.6,per_query_results:trial.per_query_results.map(q=>({...q,score:0.6}))}] }
const run = () => ({...current,applied_at:state.optimizationApplied?'2026-09-29T12:00:00Z':null,reverted_at:state.optimizationReverted?'2026-09-29T12:01:00Z':null})
await page.route('**/api/knowledge/kb-1/optimize/active', r=>r.fulfill({json:{run:run()}}))
await page.route('**/api/knowledge/kb-1/optimize?*', r=>r.fulfill({json:{items:[{...previous,num_trials:1,eval_set_size:3}],count:1,skip:0,limit:20}}))
await page.route('**/api/knowledge/kb-1/optimize/opt-review', r=>r.fulfill({json:run()}))
await page.route('**/api/knowledge/kb-1/optimize/opt-earlier', r=>failComparison?r.fulfill({status:503,json:{detail:'Earlier run temporarily unavailable'}}):r.fulfill({json:previous}))
await page.route('**/api/knowledge/kb-1/test-queries/generate',r=>{generation.push(r.request().postDataJSON());return r.fulfill({json:{created:3,test_queries:queries}})})
async function visibleControl(locator) {
  const box=await locator.boundingBox(), viewport=page.viewportSize()
  assert.ok(box && box.width>=24 && box.height>=24 && box.x>=0 && box.y>=0 && box.x+box.width<=viewport.width && box.y+box.height<=viewport.height, 'Dialog action must fit without scrolling the page')
}
async function shot(id) {
  await review.capture(id)
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${id}: overflow`)
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out,`${id}.axe.json`),'utf8')),[],`${id}: accessibility`)
  console.log(`Captured ${id}`)
}
async function closeWithKeyboard(dialog, trigger) {
  await page.keyboard.press('Escape')
  await dialog.waitFor({state:'hidden'})
  assert.equal(await trigger.evaluate(e=>e===document.activeElement),true,'Closing must restore trigger focus')
}
try {
  for(const [width,height] of [[320,480],[768,500],[1440,600]]) {
    state.optimizationApplied=false;state.optimizationReverted=false;state.failApply=false
    await page.setViewportSize({width,height})
    await page.goto(review.baseURL+'/?mode=knowledge')
    await page.getByRole('button',{name:'Edit',exact:true}).click()
    await page.getByRole('tab',{name:'Validation',exact:true}).click()
    await page.getByRole('tab',{name:'Test questions',exact:true}).click()
    const generate=page.getByRole('button',{name:'Auto-generate (LLM)',exact:true})
    await generate.click()
    const generationDialog=page.getByRole('dialog',{name:'Auto-generate test queries'})
    await visibleControl(generationDialog.getByRole('button',{name:'Generate',exact:true}))
    assert.equal(await generationDialog.getByRole('radio',{name:/Standard/}).isChecked(),true)
    await shot(`validation-generation-dialog-${width}-short`)
    await generationDialog.getByRole('radio',{name:/Exhaustive/}).check()
    await generationDialog.getByText('How question IDs work',{exact:true}).click()
    await visibleControl(generationDialog.getByRole('button',{name:'Generate',exact:true}))
    await shot(`validation-generation-details-${width}-short`)
    await closeWithKeyboard(generationDialog,generate)
    await generate.click()
    await generationDialog.getByRole('radio',{name:/Quick/}).check()
    await generationDialog.getByRole('button',{name:'Generate',exact:true}).click()
    await generationDialog.waitFor({state:'hidden'})
    assert.deepEqual(generation.at(-1),{coverage:'quick',async:true})
    await page.getByRole('tab',{name:'Improve retrieval',exact:true}).click()
    const trialTrigger=page.locator('[role=button][title="View what this trial tried and why it matters"]')
    await trialTrigger.focus();await page.keyboard.press('Enter')
    const detail=page.getByRole('dialog',{name:'Trial details'})
    await detail.waitFor()
    await visibleControl(detail.getByRole('button',{name:'Close',exact:true}))
    await shot(`validation-trial-details-${width}-short`)
    await detail.getByText(/The overall quality score blends/).scrollIntoViewIfNeeded()
    await shot(`validation-trial-details-end-${width}-short`)
    await closeWithKeyboard(detail,trialTrigger)
    await page.getByRole('button',{name:'Previous runs'}).click()
    const compare=page.getByRole('button',{name:'Compare',exact:true})
    await compare.scrollIntoViewIfNeeded()
    await shot(`validation-optimization-history-${width}-short`)
    failComparison=true;await compare.click()
    const comparison=page.getByRole('dialog',{name:'Compare optimization runs'})
    await comparison.getByRole('button',{name:'Retry comparison'}).waitFor()
    await shot(`validation-comparison-error-${width}-short`)
    failComparison=false;await comparison.getByRole('button',{name:'Retry comparison'}).click()
    await comparison.getByText('Winning config diff',{exact:true}).waitFor()
    await visibleControl(comparison.getByRole('button',{name:'Close',exact:true}))
    await shot(`validation-comparison-recovered-${width}-short`)
    await comparison.getByText('Biggest gains',{exact:true}).scrollIntoViewIfNeeded()
    await shot(`validation-comparison-deltas-${width}-short`)
    await closeWithKeyboard(comparison,compare)
    await page.getByRole('button',{name:'Apply optimized settings',exact:true}).click()
    const apply=page.getByRole('dialog')
    await visibleControl(apply.getByRole('button',{name:'Apply',exact:true}))
    await shot(`validation-apply-dialog-${width}-short`)
    await apply.getByRole('checkbox').check();state.failApply=true
    await apply.getByRole('button',{name:'Apply',exact:true}).click()
    await apply.getByRole('alert').waitFor()
    await visibleControl(apply.getByRole('button',{name:'Apply',exact:true}))
    await shot(`validation-apply-retry-${width}-short`)
    state.failApply=false;await apply.getByRole('button',{name:'Apply',exact:true}).click()
    await apply.waitFor({state:'hidden'})
    await page.getByRole('button',{name:'Revert',exact:true}).click()
    await page.getByRole('button',{name:'Apply optimized settings',exact:true}).waitFor()
  }
  assert.equal(generation.length,3)
  assert.equal(state.applyCalls,6);assert.equal(state.revertCalls,3)
  assert.deepEqual(review.errors,[]);assert.deepEqual([...review.unmatched],[])
  review.observations.push('320×480, 768×500 and 1440×600: generation choices and payload, trial details, full comparison values/deltas with retry, apply acknowledgement/failure/retry and revert. Dialog actions fit; Escape restores generation/trial/comparison focus. Synthetic responses; no backend/model execution.')
} catch(error) { await page.screenshot({path:resolve(review.out,'validation-dialogs-blocked.png')});throw error }
finally {await review.flush();await review.browser.close()}
