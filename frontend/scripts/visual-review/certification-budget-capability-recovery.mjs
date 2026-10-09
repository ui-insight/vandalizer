import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'

const fixtures = resolve(process.env.REVIEW_FIXTURES || '../artifacts/visual-review/certification-budget-capability-recovery-2026-10-09/fixtures')
const read = async path => JSON.parse(await readFile(path, 'utf8'))
const modules = await read('../backend/certification-data/panel-modules.json')
const structure = await read('../backend/certification-data/course-structure.json')
const old = await read('../artifacts/visual-review/certification-budget-review-drafts-2026-10-08/http-fixture.json')
const cases = await Promise.all(['exception', 'empty', 'checkpoint_limit', 'saved_results'].map(async name => ({ name, run: await read(`${fixtures}/${name}.json`) })))
let active = cases[0]
const identity = () => ({ enrollment_id: active.run.enrollment_id, course_version: active.run.course_version, manifest_sha256: active.run.manifest_sha256,
  course_title: 'Budget recovery QA', module_ids: modules.map(m => m.id), modules_total: modules.length, maximum_xp: 2675 })
const course = () => ({ ...structure, ...identity(), versioned: true, prerequisites: Object.fromEntries(modules.map(m => [m.id, []])),
  modules: modules.map(m => m.id === 'advanced_nodes' ? { ...m, budgetWorkflowAssessment: active.run.input_snapshot.case, assessment: null } : m) })
const progress = () => ({ ...identity(), id: 'budget-recovery-qa', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, learning_position: null })
const listing = () => ({ ...old.listing, ...identity(), case: active.run.input_snapshot.case, workflows: [], assigned_sources: [], calculations: [], captures: [], submissions: [],
  runs: [{ run_id: active.run.run_id, state: active.run.state, prepared_at: active.run.prepared_at, input_snapshot_id: active.run.input_snapshot_id, workflow_name: active.run.input_snapshot.artifact.workflow.name }] })
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5307',
  evidenceMode: 'Production UI with actual disposable-engine/MongoDB run-view fixtures and synthetic read-only delivery. Synthetic provider failures; no live model, course write or credit.' })
const { page, context } = review
const reads = []
await context.route('**/api/certification/**', route => {
  const request = route.request(), path = new URL(request.url()).pathname
  assert.equal(request.method(), 'GET'); reads.push(path)
  if (path.endsWith('/progress')) return route.fulfill({ json: progress() })
  if (path.endsWith('/course')) return route.fulfill({ json: course() })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (path.endsWith('/budget-workflows')) return route.fulfill({ json: listing() })
  if (path.endsWith(`/budget-runs/${active.run.run_id}`)) return route.fulfill({ json: active.run })
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
async function capture(id, target) {
  await target.scrollIntoViewIfNeeded(); await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1688 : 1000 })
    for (active of cases) {
      await page.goto(review.baseURL + '/certification')
      if (native) await review.setBrowserZoom(2)
      const panel = page.locator('[data-cert-panel]')
      await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
      await panel.getByRole('button', { name: /^6 Advanced Nodes/ }).click()
      await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
      await panel.getByRole('combobox', { name: 'Open saved budget work', exact: true }).selectOption(`run:${active.run.run_id}`)
      const evidence = panel.getByRole('region', { name: 'Opened budget evidence', exact: true })
      const guidance = evidence.getByText(active.name === 'saved_results' ? /Open this saved run again/ : /To revise this work/)
      await guidance.waitFor()
      assert.equal(await evidence.getByRole('button', { name: 'Run this approved budget workflow', exact: true }).count(), 0)
      assert.equal(await evidence.getByRole('button', { name: 'Review this completed budget run', exact: true }).count(), 0)
      assert.equal(await evidence.getByRole('button', { name: 'Finalize saved budget results without rerunning', exact: true }).count(), active.name === 'saved_results' ? 1 : 0)
      if (active.name === 'exception') await capture(`unavailable-task-${width}`, evidence.getByText(/This model operation was unavailable/))
      if (active.name === 'empty') await capture(`missing-output-${width}`, evidence.getByText(/This task did not return a usable result/))
      await capture(`${active.name}-recovery-${width}`, guidance)
      assert.ok(!(await evidence.innerText()).includes('PRIVATE PROVIDER SECRET'))
    }
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ cases: cases.map(item => item.name), reads: reads.length, writes: 0, completedReviewOffered: false, finalizedOrRerun: false })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
