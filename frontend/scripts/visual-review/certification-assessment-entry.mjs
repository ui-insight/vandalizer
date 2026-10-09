import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'

const root = resolve(process.env.REVIEW_PACKAGE || '../artifacts/visual-review/certification-full-course-preview-2026-10-07/package-complete')
const report = JSON.parse(await readFile(`${root}/preview-report.json`, 'utf8'))
assert.equal(report.preview_only, true); assert.equal(report.enrollment_available, false)
const course = { ...JSON.parse(await readFile(`${root}/public-course.json`, 'utf8')), enrollment_id: 'qa-full-course-preview' }
const exercises = JSON.parse(await readFile(`${root}/${report.release_id}/exercises.json`, 'utf8'))
const outcomes = JSON.parse(await readFile(`${root}/${report.release_id}/outcomes.json`, 'utf8'))
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
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Actual UI and complete assembled public-course payload. Synthetic enrollment, no provisioned documents and empty owned-history responses test direct chat assessment entry. No real enrollment, lab, decision, assessment, credit or release verification.' })
const { page, context, state } = review
const agentRequests = []
page.on('request', request => { if (new URL(request.url()).pathname === '/api/chat') agentRequests.push(request.url()) })
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
async function send(module, identity = course) {
  const exercise = exercises[module.id]
  const content = { ...identity, module_id: module.id, title: module.title, xp: module.xp, completed: false, stars: 0,
    overview: exercise.overview, instructions: exercise.instructions, agent_guidance: exercise.chat_instructions || [],
    expected_fields: exercise.expected_fields, star_criteria: exercise.star_criteria, sample_documents: exercise.documents,
    provisioned_docs: [], assessment_keys: [], assessment_questions: [], assessment_mode: 'selected_saved_outcomes',
    required_outcomes: outcomes.modules.find(item => item.module_id === module.id).outcomes.map(outcome => ({
      outcome_id: outcome.id, statement: outcome.statement, method: outcome.method,
    })), selected_outcome_completion: false, lesson_titles: module.lessons.map(lesson => lesson.title) }
  state.chatChunks = [{ kind: 'tool_call', tool_name: 'get_certification_module', tool_call_id: 'entry', args: {} },
    { kind: 'tool_result', tool_name: 'get_certification_module', tool_call_id: 'entry', content }]
  await page.getByRole('textbox', { name: 'Message input', exact: true }).fill('Show my assigned module.')
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
  const card = page.locator('.cert-chat-card').last()
  await card.getByText(module.title, { exact: true }).waitFor()
  return card
}
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1200 : 900 })
    for (const module of course.modules) {
      const other = course.modules.find(item => item.id !== module.id)
      progress.learning_position = { module_id: other.id, lesson_id: other.lessons[0].id, revision: other.lessons[0].revision, content_sha256: 'f'.repeat(64), saved_at: '2026-10-07T12:00:00Z' }
      await page.goto(review.baseURL)
      if (native) await review.setBrowserZoom(2)
      const card = await send(module)
      const entry = card.getByRole('button', { name: 'Open module assessment', exact: true })
      await entry.waitFor()
      assert.equal(await card.getByRole('button', { name: 'Check my progress', exact: true }).count(), 0)
      await capture(`${module.id}-chat-entry-${width}`, entry)
      const instructions = card.locator('summary').filter({ hasText: 'Exercise instructions' })
      const disclosure = instructions.locator('..')
      assert.equal(await disclosure.getAttribute('open'), null)
      await card.getByRole('heading', { name: 'Required outcomes', exact: true }).waitFor()
      await instructions.focus(); await page.keyboard.press('Enter')
      assert.notEqual(await disclosure.getAttribute('open'), null)
      const steps = disclosure.locator('.cert-procedure > li')
      assert.equal(await steps.count(), exercises[module.id].instructions.length)
      for (const [index, step] of (await steps.all()).entries()) {
        assert.equal((await step.innerText()).trim(), exercises[module.id].instructions[index])
        assert.ok(await step.evaluate(node => node.scrollWidth <= node.clientWidth))
      }
      for (const guidance of exercises[module.id].chat_instructions || []) {
        if (!exercises[module.id].instructions.includes(guidance)) assert.equal(await card.getByText(guidance, { exact: true }).count(), 0)
      }
      await capture(`${module.id}-instructions-${width}`, steps.first())
      await instructions.focus(); await page.keyboard.press('Enter')
      assert.equal(await disclosure.getAttribute('open'), null)
      const draft = page.getByRole('textbox', { name: 'Message input', exact: true })
      await draft.fill('Keep my unsent question while I inspect the assessment.')
      const callsBefore = agentRequests.length, savedPosition = JSON.stringify(progress.learning_position)
      await entry.focus(); await page.keyboard.press('Enter')
      const panel = page.locator('[data-cert-panel="true"]')
      const challenge = panel.getByRole('button', { name: 'Challenge', exact: true })
      const heading = panel.getByRole('heading', { name: cases[module.id]?.[2] || (module.id === 'ai_literacy' ? 'Practice your judgment' : 'Review your saved work'), exact: true })
      await heading.waitFor()
      await page.waitForFunction(() => document.activeElement?.textContent?.trim() === 'Challenge')
      assert.equal(await challenge.isEnabled(), true)
      await capture(`${module.id}-assessment-${width}`, heading)
      assert.equal(await panel.getByRole('button', { name: 'Complete Module', exact: true }).count(), 0)
      assert.equal(await panel.getByRole('alert').count(), 0)
      await panel.getByRole('button', { name: 'Return to workspace', exact: true }).click()
      assert.equal(await draft.inputValue(), 'Keep my unsent question while I inspect the assessment.')
      assert.equal(agentRequests.length, callsBefore)
      assert.equal(JSON.stringify(progress.learning_position), savedPosition)
    }
    await page.goto(review.baseURL)
    if (native) await review.setBrowserZoom(2)
    const old = await send(course.modules[1], { ...course, enrollment_id: 'previous-course' })
    assert.equal(await old.getByRole('button', { name: /Open module assessment|Check my progress|Set up lab/ }).count(), 0)
    await capture(`historical-card-${width}`, old.getByRole('button', { name: 'Open current course', exact: true }))
    const callsBefore = agentRequests.length
    await old.getByRole('button', { name: 'Open current course', exact: true }).click()
    await page.locator('[data-cert-panel="true"]').waitFor()
    assert.equal(agentRequests.length, callsBefore)
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ packageManifest: report.manifest_sha256, inspectedModules: course.modules.map(module => module.id), certificationRequests: reads,
    certificationWrites: 0, agentCallsFromAssessmentEntry: 0, unsentDraftPreserved: true, savedPositionPreserved: true, noLabPrepared: true, gradingVerified: false })
} catch (error) { await review.capture('blocked', String(error)); throw error } finally { await review.flush(); await review.browser.close() }
