import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'

const root = resolve(process.env.REVIEW_PACKAGE || '../artifacts/visual-review/certification-full-course-preview-2026-10-07/package-complete')
const report = JSON.parse(await readFile(`${root}/preview-report.json`, 'utf8'))
assert.equal(report.preview_only, true); assert.equal(report.enrollment_available, false)
let course = { ...JSON.parse(await readFile(`${root}/public-course.json`, 'utf8')), enrollment_id: 'qa-full-course-preview' }
const baseline = JSON.parse(await readFile(new URL('../../../backend/certification-data/panel-modules.json', import.meta.url), 'utf8'))
const originalCourse = course
const selectedIds = process.env.REVIEW_MODULE_IDS?.split(',')
const inspectedModules = selectedIds ? course.modules.filter(module => selectedIds.includes(module.id)) : course.modules
assert.ok(inspectedModules.length > 0)
if (selectedIds) assert.equal(inspectedModules.length, new Set(selectedIds).size)
const exercises = JSON.parse(await readFile(`${root}/${report.release_id}/exercises.json`, 'utf8'))
const budget = JSON.parse(await readFile(`${root}/${report.release_id}/advanced-cases/advanced_nodes.json`, 'utf8'))
// Match the real delivery's public field descriptors, excluding answers/anchors.
const calculationFields = budget.calculations.map(check => ({ id: check.id, unit: check.unit, operation: check.operation,
  inputs: check.inputs.map(id => { const amount = budget.amounts.find(item => item.id === id); return { id, label: amount.label, source_page: amount.anchor.page } }) }))
const progress = { ...course, id: 'qa-preview', user_id: 'reviewer', modules: Object.fromEntries(course.modules.map(module => [module.id, { provisioned_docs: ['synthetic-preview-marker'] }])), total_xp: 0, level: 'novice', certified: false, learning_position: null, position_revision: 0 }
const cases = {
  process_mapping: ['process-designs', 'processAssessment', 'Design a bounded process'],
  workflow_design: ['designs', 'workflowDesignAssessment', 'Inspect and approve your workflow design'],
  multi_step: ['connected-workflows', 'connectedWorkflowAssessment', 'Run, inspect and repair a connected workflow'],
  advanced_nodes: ['budget-workflows', 'budgetWorkflowAssessment', 'Choose methods, check arithmetic and inspect dependencies'],
  output_delivery: ['output-workflows', 'outputWorkflowAssessment', 'Generate, inspect and hand off exact files'],
  validation_qa: ['validation-suites', 'validationAssessment', 'Representative tests and repair'],
  batch_processing: ['batch-work', 'batchAssessment', 'Checked pilot, complete inventory and targeted recovery'],
  governance: ['governance-work', 'governanceAssessment', 'Supervise the capstone and own its handoff'],
}
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Actual UI and complete assembled public-course payload plus a synthetic legacy completion. Required-outcome labels replace inapplicable draft stars; original legacy stars remain visible. Synthetic enrollment, provisioned marker and empty owned-history responses permit entry inspection only. No real enrollment, lab, decision, assessment, credit or release verification.' })
const { page, context } = review
const reads = []
await context.route('**/api/certification/**', route => {
  const req = route.request(), path = new URL(req.url()).pathname
  assert.equal(req.method(), 'GET', `Preview must not write: ${path}`); reads.push(path)
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  const id = path.match(/\/modules\/([^/]+)\//)?.[1]
  if (id && path.endsWith('/exercise')) return route.fulfill({ json: exercises[id] })
  if (id && path.endsWith('/practical-runs')) return route.fulfill({ json: { enrollment_id: course.enrollment_id, module_id: id, runs: [], older_runs_available: false } })
  if (id && cases[id] && path.endsWith('/' + cases[id][0])) {
    const definition = course.modules.find(module => module.id === id)[cases[id][1]]
    const listing = { enrollment_id: course.enrollment_id, module_id: id, course_version: course.course_version,
      manifest_sha256: course.manifest_sha256, case: definition, can_submit: true, read_only_reason: null,
      records: Object.fromEntries(['capture', 'run', 'correction', 'scope', 'finding', 'memo', 'release', 'handoff', 'review'].map(kind => [kind, { items: [], older_available: false }])) }
    for (const key of ['submissions', 'workflows', 'process_choices', 'captures', 'runs', 'assigned_sources', 'calculations', 'extractions', 'suites', 'inspections', 'handoffs', 'recovery_submissions', 'calculation_fields']) {
      listing[key] = []; listing[`older_${key}_available`] = false
    }
    if (id === 'advanced_nodes') listing.calculation_fields = calculationFields
    return route.fulfill({ json: listing })
  }
  return route.fallback()
})
async function capture(id, target) {
  if (target) await target.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1200 : 900 })
    await page.goto(review.baseURL + '/certification')
    if (native) await review.setBrowserZoom(2)
    const panel = page.locator('[data-cert-panel="true"]')
    await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    assert.equal(await panel.getByRole('img', { name: /stars/ }).count(), 0)
    assert.equal(await panel.getByText('Required outcomes', { exact: true }).count(), 11)
    await capture(`course-introduction-${width}`, panel.getByText('Optional walkthrough · work at your own pace', { exact: true }))
    await capture(`course-entry-${width}`, panel.getByRole('button', { name: /^0 AI Literacy/ }))
    await capture(`final-outcome-card-${width}`, panel.getByRole('button', { name: /^10 Collaboration/ }))
    for (const module of inspectedModules) {
      const title = module.title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      await panel.getByRole('button', { name: new RegExp(`^${module.number} ${title}`) }).click()
      const lesson = panel.getByRole('heading', { name: module.lessons[0].title, exact: true })
      await lesson.waitFor()
      await panel.getByText('Module: Not complete', { exact: true }).waitFor()
      assert.equal(await panel.getByRole('img', { name: /stars/ }).count(), 0)
      assert.equal(await panel.getByText('Challenge: Not started', { exact: true }).count(), 0)
      await capture(`${module.id}-status-${width}`, panel.getByText('Module: Not complete', { exact: true }))
      if (module.id === 'foundations') {
        const labButton = panel.getByRole('button', { name: 'Ready', exact: true })
        assert.ok((await labButton.boundingBox()).height >= 44)
        await capture(`ready-lab-entry-${width}`, labButton)
      }
      await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
      const heading = panel.getByRole('heading', { name: cases[module.id]?.[2] || (module.id === 'ai_literacy' ? 'Practice your judgment' : 'Review your saved work'), exact: true })
      await heading.waitFor()
      if (module.id === 'foundations') await panel.getByText('Your Foundations assignment', { exact: true }).waitFor()
      assert.equal(await panel.getByRole('button', { name: 'Complete Module', exact: true }).count(), 0)
      assert.equal(await panel.getByRole('button', { name: 'Submit Self-Assessment', exact: true }).count(), 0)
      assert.equal(await panel.getByRole('alert').count(), 0)
      await capture(`${module.id}-assessment-${width}`, heading)
      await panel.getByRole('button', { name: 'Curriculum', exact: true }).click()
    }
  }
    course = { ...originalCourse, modules: baseline, credential_scope: null, progression_policy: null,
      enrollment_id: 'qa-preserved-legacy', course_version: 'legacy-preview', manifest_sha256: 'f'.repeat(64) }
    Object.assign(progress, { enrollment_id: course.enrollment_id, course_version: course.course_version, manifest_sha256: course.manifest_sha256,
      modules: { foundations: { completed: true, stars: 2, attempts: 1, xp_earned: 125, provisioned_docs: [] } } })
    for (const width of native ? [780] : [320, 1440]) {
      await page.setViewportSize({ width, height: native ? 1200 : 900 }); await page.goto(review.baseURL + '/certification')
      if (native) await review.setBrowserZoom(2)
      const panel = page.locator('[data-cert-panel="true"]')
      await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
      const card = panel.getByRole('button', { name: /Foundations/ })
      assert.equal(await card.getByRole('img', { name: '2 of 3 stars', exact: true }).count(), 1)
      await capture(`legacy-earned-stars-${width}`, card)
      await card.click()
      assert.equal(await panel.getByRole('img', { name: '2 of 3 stars', exact: true }).count(), 2)
      await panel.getByText('Challenge: Complete', { exact: true }).waitFor()
      await capture(`legacy-completed-detail-${width}`, panel.getByRole('heading', { name: 'Module 1: Foundations', exact: true }))
      const labButton = panel.getByRole('button', { name: 'Set Up Lab', exact: true })
      assert.ok((await labButton.boundingBox()).height >= 44)
      await capture(`legacy-lab-entry-${width}`, labButton)
    }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ packageManifest: report.manifest_sha256, inspectedModules: inspectedModules.map(module => module.id), certificationRequests: reads, certificationWrites: 0, realLearnerChanges: false, gradingVerified: false })
} catch (error) { await review.capture('blocked', String(error)); throw error } finally { await review.flush(); await review.browser.close() }
