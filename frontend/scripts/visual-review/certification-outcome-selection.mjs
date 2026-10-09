import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'

const root = resolve(process.env.REVIEW_PACKAGE || '../artifacts/visual-review/certification-full-course-preview-2026-10-07/package-complete')
const report = JSON.parse(await readFile(`${root}/preview-report.json`, 'utf8'))
assert.equal(report.preview_only, true); assert.equal(report.enrollment_available, false)
const course = { ...JSON.parse(await readFile(`${root}/public-course.json`, 'utf8')), enrollment_id: 'qa-full-course-preview' }
const exercises = JSON.parse(await readFile(`${root}/${report.release_id}/exercises.json`, 'utf8'))
const budget = JSON.parse(await readFile(`${root}/${report.release_id}/advanced-cases/advanced_nodes.json`, 'utf8'))
// Match the real delivery's public field descriptors, excluding answers/anchors.
const calculationFields = budget.calculations.map(check => ({ id: check.id, unit: check.unit, operation: check.operation,
  inputs: check.inputs.map(id => { const amount = budget.amounts.find(item => item.id === id); return { id, label: amount.label, source_page: amount.anchor.page } }) }))
const progress = { ...course, id: 'qa-preview', user_id: 'reviewer', modules: Object.fromEntries(course.modules.map(module => [module.id, { provisioned_docs: [] }])), total_xp: 0, level: 'novice', certified: false, learning_position: null, position_revision: 0 }
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
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Actual combined-outcome UI and complete assembled public-course payload with synthetic saved assessment lists/results. Exact explicit selection, mixed requirements, stale/invalid response rejection and recovery. All requests are GET-only. No actual grading or credit verification.' })
const { page, context } = review
const reads = []
const contract = JSON.parse(await readFile(`${root}/${report.release_id}/outcomes.json`, 'utf8'))
let malformed = false, listFails = false
const ids = { review: '1'.repeat(32), scenario: '2'.repeat(32), failed: '3'.repeat(32), pending: '4'.repeat(32), unavailable: '5'.repeat(32) }

await context.route('**/api/certification/**', route => {
  const req = route.request(), path = new URL(req.url()).pathname
  assert.equal(req.method(), 'GET', `Preview must not write: ${path}`); reads.push(path)
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/readiness')) {
    const moduleId = path.split('/')[4], query = new URL(req.url()).searchParams
    const selected = { review: query.get('review_attempt_id'), scenario: query.get('scenario_attempt_id') }
    const outcomes = contract.modules.find(module => module.module_id === moduleId).outcomes.map(item => {
      const attempt = item.method === 'scenario_choice' ? selected.scenario : selected.review
      return { outcome_id: item.id, statement: item.statement, method: item.method, attempt_id: attempt,
        state: !attempt ? 'selection_required' : attempt === ids.failed ? 'revision_required' : attempt === ids.pending ? 'assessment_pending' : attempt === ids.unavailable ? 'grading_unavailable' : 'supported' }
    })
    const status = ['revision_required', 'grading_unavailable', 'assessment_pending', 'selection_required'].find(state => outcomes.some(item => item.state === state)) || 'requirements_supported'
    const payload = { ...course, module_id: moduleId, contract_sha256: 'b'.repeat(64), rubric_id: contract.rubric_id, assessment_kind: 'module_readiness_draft',
      status, all_required_outcomes_supported: status === 'requirements_supported', outcomes,
      selected_receipts: Object.entries(selected).filter(([, value]) => value).map(([kind, attempt_id]) => ({ kind: kind === 'review' ? 'automatic_review' : 'scenario_recognition', attempt_id, record_sha256: 'c'.repeat(64), result_sha256: attempt_id === ids.pending ? null : 'd'.repeat(64) })),
      read_only: true, credit_awarded: false, module_completion_eligible: false, staff_review_required: false }
    if (malformed) payload.outcomes.pop()
    return route.fulfill({ json: payload })
  }
  if (path.endsWith('/automatic-reviews')) {
    if (listFails) return route.fulfill({ status: 503, json: { detail: 'Synthetic discovery unavailable' } })
    return route.fulfill({ json: { enrollment_id: course.enrollment_id, module_id: path.split('/')[4], older_attempts_available: true,
      attempts: ['review', 'pending', 'unavailable'].map((kind, index) => ({ attempt_id: ids[kind], prepared_at: `2026-10-0${7-index}T12:00:00Z`, status: { review: 'requirements_supported', pending: 'evaluating', unavailable: 'grading_unavailable' }[kind] })) } })
  }
  if (path.endsWith('/scenarios')) return route.fulfill({ json: { enrollment_id: course.enrollment_id, module_id: path.split('/')[6], bank_sha256: 'e'.repeat(64), read_only: true, older_attempts_available: true,
    attempts: [{ attempt_id: ids.scenario, submitted_at: '2026-10-07T12:00:00Z', passed: true }, { attempt_id: ids.failed, submitted_at: '2026-10-06T12:00:00Z', passed: false }] } })
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
    for (const moduleId of ['ai_literacy', 'foundations', 'governance']) {
      await page.goto(review.baseURL + '/certification')
      if (native) await review.setBrowserZoom(2)
      const panel = page.locator('[data-cert-panel="true"]')
      await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
      const module = course.modules.find(item => item.id === moduleId)
      await panel.getByRole('button', { name: new RegExp(`^${module.number} ${module.title}`) }).click()
      await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
      const section = panel.getByRole('region', { name: 'Combined module outcomes', exact: true })
      await section.getByRole('button', { name: 'Choose saved assessments', exact: true }).click()
      const check = section.getByRole('button', { name: 'Check selected assessments', exact: true })
      await check.waitFor(); await page.waitForFunction(() => [...document.querySelectorAll('button')].some(button => button.textContent === 'Check selected assessments' && !button.disabled))
      const recognition = section.getByRole('combobox', { name: 'Scenario assessment', exact: true })
      const practical = section.getByRole('combobox', { name: 'Automatic assessment', exact: true })
      for (const control of await section.getByRole('combobox').all()) assert.equal(await control.inputValue(), '')
      await capture(`${moduleId}-no-implicit-choice-${width}`, section.getByRole('heading', { name: 'Evidence required for this module', exact: true }))
      if (await practical.count()) await practical.selectOption(ids.review)
      if (await recognition.count()) await recognition.selectOption(moduleId === 'governance' ? ids.failed : ids.scenario)
      if (process.env.REVIEW_SELECTION_LABELS_ONLY === '1') {
        const label = section.getByText(await practical.count() ? /^Selected automatic assessment:/ : /^Selected scenario assessment:/)
        await capture(`${moduleId}-readable-selection-${width}`, label)
        assert.equal(await label.evaluate(element => element.scrollWidth <= element.clientWidth + 1), true)
        continue
      }
      await check.click()
      await section.getByRole('heading', { name: moduleId === 'governance' ? 'Revision needed' : 'All draft outcomes supported', exact: true }).waitFor()
      const result = section.getByRole('region', { name: 'Module outcome result', exact: true })
      assert.equal(await result.evaluate(element => element === document.activeElement), true)
      await capture(`${moduleId}-selected-result-${width}`, result)
      if (moduleId === 'governance') {
        await recognition.selectOption('')
        assert.equal(await section.getByRole('heading', { name: 'Revision needed', exact: true }).count(), 0)
        await check.click(); await section.getByRole('heading', { name: 'Select saved evidence', exact: true }).waitFor()
        await capture(`mixed-missing-recognition-${width}`, result)
        await recognition.selectOption(ids.scenario)
        for (const [kind, label] of [['pending', 'Assessment pending'], ['unavailable', 'Assessment unavailable'], ['review', 'All draft outcomes supported']]) {
          await practical.selectOption(ids[kind]); await check.click()
          await section.getByRole('heading', { name: label, exact: true }).waitFor()
          await capture(`mixed-${kind}-${width}`, result)
        }
        malformed = true
        await check.click(); await section.getByRole('alert').waitFor()
        assert.equal(await section.getByRole('heading', { name: 'All draft outcomes supported', exact: true }).count(), 0)
        await capture(`incomplete-response-rejected-${width}`, section.getByRole('alert'))
        malformed = false; listFails = true
        await section.getByRole('button', { name: 'Refresh saved choices', exact: true }).click()
        await section.getByText('Some saved choices could not be loaded. Refresh the choices, or use a full reference from your saved feedback.', { exact: true }).waitFor()
        await section.getByText('Use an older automatic assessment reference', { exact: true }).click()
        await section.getByRole('textbox', { name: 'Automatic assessment reference', exact: true }).fill(ids.review)
        await check.click(); await section.getByRole('heading', { name: 'All draft outcomes supported', exact: true }).waitFor()
        await capture(`older-reference-recovery-${width}`, result)
        listFails = false
      }
      await section.getByRole('button', { name: 'Close outcome preview', exact: true }).click()
      const opener = section.getByRole('button', { name: 'Choose saved assessments', exact: true })
      await page.waitForFunction(() => document.activeElement?.textContent === 'Choose saved assessments')
      assert.equal(await opener.isEnabled(), true)
    }
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ certificationRequests: reads, certificationWrites: 0, providerCalls: 0, creditAwarded: false, selectedFailurePreserved: true,
    missingMixedRequirementVisible: true, pendingAndUnavailableExplicit: true, originalReceiptSelection: 'Synthetic exact references', realGradingVerified: false })
} catch (error) { await review.capture('blocked', String(error)); throw error } finally { await review.flush(); await review.browser.close() }
