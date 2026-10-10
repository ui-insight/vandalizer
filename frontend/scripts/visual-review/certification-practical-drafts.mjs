import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const data = new URL('../../../backend/certification-data/', import.meta.url)
const modules = JSON.parse(await readFile(new URL('panel-modules.json', data), 'utf8'))
const structure = JSON.parse(await readFile(new URL('course-structure.json', data), 'utf8'))
const validation = JSON.parse(await readFile(new URL('../../src/components/certification/__fixtures__/validation-repair-http.json', import.meta.url), 'utf8'))
const governance = JSON.parse(await readFile(new URL('../../src/components/certification/__fixtures__/governance-http.json', import.meta.url), 'utf8'))
const handoff = governance.review.handoff, run = handoff.release.memo.run, capture = validation.original.input_snapshot
const scenarios = [
  { name: 'expectations', moduleId: 'validation_qa', property: 'validationAssessment', endpoint: 'validation-suites', listing: validation.listing,
    saved: capture, kind: 'capture', reference: capture.uuid, form: 'Save representative test expectations',
    fields: { 'Expected value': 'Original learner-authored expected value', 'Exact source quote': 'Original source quote entered by the learner', [capture.case.questions[0].prompt]: 'Original learner explanation of representative coverage and limitations.' } },
  { name: 'memo', moduleId: 'governance', property: 'governanceAssessment', endpoint: 'governance-work', listing: governance.listing,
    saved: run, kind: 'run', reference: run.run_id, form: 'Write the accountable capstone memo',
    fields: { 'Intended use': 'Original learner-authored private training use.', 'Known limitations': 'Original learner-authored source and workflow limits.' } },
  { name: 'supervision', moduleId: 'governance', property: 'governanceAssessment', endpoint: 'governance-work', listing: governance.listing,
    saved: handoff, kind: 'handoff', reference: handoff.uuid, form: 'Explain your complete capstone supervision',
    fields: { [handoff.case.questions.find(q => q.id === 'final_supervision').prompt]: 'Original learner-authored explanation of supervision and recovery.' } },
]
if (process.env.REVIEW_SCOPE_DRAFTS === '1') {
  const prepared = { ...validation.original, state: 'prepared', result: null, result_sha256: null, scope_decision: null, scope_decision_id: null, scope_decision_sha256: null, authorization_sha256: null, can_save_scope: true, can_execute: false, can_finalize: false }
  const capstone = governance.prepared_runs[0]
  scenarios.splice(0, scenarios.length,
    { name: 'validation-scope', moduleId: 'validation_qa', property: 'validationAssessment', endpoint: 'validation-suites', listing: validation.listing,
      saved: prepared, kind: 'run', reference: prepared.run_id, form: 'Approve complete validation suite', choice: 'Scope choice', fields: { 'Why this scope is appropriate': 'My original learner-authored scope explanation for both complete cases.' } },
    { name: 'governance-scope', moduleId: 'governance', property: 'governanceAssessment', endpoint: 'governance-work', listing: governance.listing,
      saved: capstone, kind: 'run', reference: capstone.run_id, form: 'Approve or hold the exact capstone extraction', choice: 'Execution choice', fields: { 'Explain your execution scope choice': 'My original learner-authored approval for the exact internal diagnostic extraction only.' } })
}
if (process.env.REVIEW_CAPSTONE_DRAFTS === '1') {
  const original = run.source_finding.run, input = original.input_snapshot, memo = handoff.release.memo
  const shared = { moduleId: 'governance', property: 'governanceAssessment', endpoint: 'governance-work', listing: governance.listing }
  scenarios.splice(0, scenarios.length,
    { ...shared, name: 'correction', saved: input, kind: 'capture', reference: input.uuid, form: 'Correct the proposed capstone scope',
      fields: { [input.case.questions.find(q => q.id === 'scope_correction').prompt]: 'My original learner correction rejecting broad access, external sends and recurring automation.' } },
    { ...shared, name: 'finding', saved: original, kind: 'run', reference: original.run_id, form: 'Record the original source finding',
      fields: { 'Actual unsupported Funds Obligated to Date value': '600000', 'Exact award notice page quote': 'Original award notice quote entered by the learner.', 'Exact issued amendment page quote': 'Original issued amendment quote entered by the learner.', 'Explain the actual mismatch and the instruction change you will test': 'My original explanation of the observed mismatch and planned bounded repair.' } },
    { ...shared, name: 'release', saved: memo, kind: 'memo', reference: memo.uuid, form: 'Inspect and decide capstone memo release', choice: 'Memo release choice', checkbox: true,
      fields: { [memo.case.questions.find(q => q.id === 'release_review').prompt]: 'My original release rationale for this exact memo and learner-only private training destination.' } })
}
if (process.env.REVIEW_CONNECTED_VALIDATION_DRAFTS === '1' || process.env.REVIEW_CONNECTED_COMPARISON_DRAFTS === '1') {
  const raw = await readFile(new URL('drafts/v5.0/multi-step-case.json', data))
  const { createHash } = await import('node:crypto')
  const definition = { ...JSON.parse(raw), case_sha256: createHash('sha256').update(raw).digest('hex') }
  const identity = { enrollment_id: '1'.repeat(32), course_version: 'connected-draft-fixture', manifest_sha256: 'a'.repeat(64), module_id: 'multi_step' }
  const input = { ...identity, uuid: 'b'.repeat(32), case: definition, input_snapshot_sha256: 'c'.repeat(64), artifact_id: 'd'.repeat(24), artifact_sha256: 'e'.repeat(64),
    captured_at: '2026-10-08', execution_authorized: false, credit_awarded: false,
    artifact: { workflow: { id: 'd'.repeat(24), name: 'Synthetic connected draft plan', version: 1, input_config: {}, output_config: {}, resource_config: {}, config_override: null },
      steps: ['Extraction', 'Prompt', 'Formatter'].map((name, i) => ({ step: { id: String(i), name: name + ' stage', is_output: i === 2, data: {} }, tasks: [{ id: String(i), name, data: { input_sources: [i ? 'step_input' : 'workflow_documents'] } }] })), referenced_extraction_sets: {} },
    documents: [{ document_id: 'f'.repeat(32), assigned_filename: definition.source_filename, title: definition.source_filename, source_sha256: definition.source_sha256, text_sha256: '1'.repeat(64), text: 'Synthetic source text for browser draft preservation only.' }] }
  const prepared = { ...identity, run_id: '2'.repeat(32), state: 'prepared', plan_sha256: '3'.repeat(64), case_sha256: definition.case_sha256, input_snapshot_id: input.uuid, input_snapshot: input, model_names: ['Synthetic model'], prepared_at: '2026-10-08',
    stage_plans: ['Extraction', 'Prompt', 'Formatter'].map((name, i) => ({ step_id: String(i), task_id: String(i), step_name: name + ' stage', task_type: name, effective_input_sources: [i ? 'step_input' : 'workflow_documents'], receives_previous_stage: i > 0, model_names: ['Synthetic model'], output_key: name })),
    scope_decision_id: null, scope_decision_sha256: null, scope_decision: null, authorization_sha256: null, result_sha256: null, stage_events_sha256: '4'.repeat(64), stage_events: [], result: null, can_save_scope: true, can_execute: false, can_finalize: false, credit_awarded: false, module_completion_eligible: false }
  const listing = { ...identity, case: definition, can_submit: true, read_only_reason: null, workflows: [], older_workflows_available: false, captures: [], older_captures_available: false,
    runs: [{ run_id: prepared.run_id, state: prepared.state, prepared_at: prepared.prepared_at, input_snapshot_id: input.uuid, workflow_name: input.artifact.workflow.name }], older_runs_available: false, submissions: [], older_submissions_available: false }
  // This synthetic complete retest is used only to render an editable explanation, never to claim success.
  const retest = { ...validation.original, run_id: '5'.repeat(32), phase: 'retest', original_run: validation.original, scope_decision: null }
  scenarios.splice(0, scenarios.length,
    { name: 'connected-scope', moduleId: 'multi_step', property: 'connectedWorkflowAssessment', endpoint: 'connected-workflows', listing, saved: prepared, kind: 'run', reference: prepared.run_id,
      form: 'Approve or hold connected run', choice: 'Scope choice', fields: { 'Explain your scope choice': 'My original connected workflow scope choice for the exact assigned source and saved plan.' } },
    { name: 'validation-interpretation', moduleId: 'validation_qa', property: 'validationAssessment', endpoint: 'validation-suites', listing: validation.listing, saved: retest, kind: 'run', reference: retest.run_id,
      form: 'Save validation repair interpretation', fields: { [retest.input_snapshot.case.questions.find(q => q.id === 'repair_review').prompt]: 'My original learner explanation of the complete retest and remaining limitations.' } })
  if (process.env.REVIEW_CONNECTED_COMPARISON_DRAFTS === '1') {
    const original = { ...prepared, state: 'completed', can_save_scope: false, can_execute: false, result_sha256: '6'.repeat(64),
      result: { status: 'completed', final_output: 'Synthetic original result for draft rendering only.', credit_awarded: false },
      stage_events: prepared.stage_plans.flatMap((stage, index) => ['stage_started', 'stage_completed'].map(kind => ({ receipt_sha256: '7'.repeat(64), receipt: { kind, stage_index: index, output_key: stage.output_key, status: 'completed', result: { output: 'Synthetic saved stage result.' } } }))) }
    const corrected = { ...original, run_id: '8'.repeat(32), result_sha256: '9'.repeat(64), input_snapshot: { ...input, artifact: { ...input.artifact, workflow: { ...input.artifact.workflow, version: 2 } } } }
    listing.runs = [original, corrected].map(value => ({ run_id: value.run_id, state: value.state, prepared_at: value.prepared_at, input_snapshot_id: value.input_snapshot_id, workflow_name: value.input_snapshot.artifact.workflow.name }))
    scenarios.splice(0, scenarios.length, { name: 'connected-comparison', moduleId: 'multi_step', property: 'connectedWorkflowAssessment', endpoint: 'connected-workflows', listing,
      saved: original, kind: 'run', reference: original.run_id, comparisonRuns: [original, corrected], form: 'Compare actual connected runs',
      fields: { [`Compare the connection repair ${definition.questions.find(q => q.id === 'connection_repair').prompt}`]: 'My original explanation of the two exact connected results and the bounded configuration change.',
        [`Check facts and interpretation ${definition.questions.find(q => q.id === 'source_review').prompt}`]: 'My original explanation distinguishing supported source facts from interpretations and unverified conclusions.' } })
  }

  if (process.env.REVIEW_CONNECTED_COMPARISON_DRAFTS === '1') {
    const recovery = JSON.parse(await readFile(new URL('../../src/components/certification/__fixtures__/connected-recovery-http.json', import.meta.url), 'utf8'))
    scenarios.push({ name: 'connected-recovery', moduleId: 'multi_step', property: 'connectedWorkflowAssessment', endpoint: 'connected-workflows', listing: recovery.listing,
      saved: recovery.stopped, kind: 'run', reference: recovery.stopped.run_id, form: 'Inspect your stopped run and choose recovery',
      radios: ['Reasoning', 'Original run, successful output and failed-stage evidence', 'Prepare and separately approve a new internal run'],
      fields: { 'Explain the evidence and recovery limits': 'My original learner explanation of the saved stopped run: preserve the successful prefix and separately approve any new internal execution.' } })
  }

}
if (process.env.REVIEW_BATCH_DRAFTS === '1') {
  const batch = JSON.parse(await readFile('../artifacts/visual-review/certification-batch-review-drafts-2026-10-08/http-fixture.json', 'utf8'))
  scenarios.splice(0, scenarios.length, { name: 'batch-interpretation', moduleId: 'batch_processing', property: 'batchAssessment', endpoint: 'batch-work', listing: batch.listing,
    saved: batch.retry, kind: 'run', reference: batch.retry.run_id, form: 'Save batch recovery interpretation',
    fields: { [batch.listing.case.questions.find(q => q.id === 'batch_review').prompt]: 'My original explanation of the complete batch inventory, preserved successes and selected recovery receipt.' } })
}
if (process.env.REVIEW_BUDGET_DRAFTS === '1') {
  const budget = JSON.parse(await readFile('../artifacts/visual-review/certification-budget-review-drafts-2026-10-08/http-fixture.json', 'utf8'))
  scenarios.splice(0, scenarios.length, { name: 'budget-interpretation', moduleId: 'advanced_nodes', property: 'budgetWorkflowAssessment', endpoint: 'budget-workflows', listing: budget.listing,
    saved: budget.run, kind: 'run', reference: budget.run.run_id, form: 'Review budget results',
    fields: Object.fromEntries(budget.listing.case.questions.filter(q => q.phase === 'after_execution').map(q => [q.prompt, `My original learner explanation for ${q.id} on this exact saved budget run.`])) })
}
if (process.env.REVIEW_BUDGET_CALCULATION_DRAFTS === '1') {
  const budget = JSON.parse(await readFile('../artifacts/visual-review/certification-budget-review-drafts-2026-10-08/http-fixture.json', 'utf8'))
  const calculation = budget.run.input_snapshot.calculation, first = budget.listing.calculation_fields[0].inputs[0]
  const shared = { moduleId: 'advanced_nodes', property: 'budgetWorkflowAssessment', endpoint: 'budget-workflows', listing: budget.listing, saved: calculation, kind: 'calculation', reference: calculation.uuid }
  scenarios.splice(0, scenarios.length,
    { ...shared, name: 'budget-calculation', form: 'Record budget calculations', fields: {
      [`${first.label} amount (USD)`]: '123.', [`Source quotation for ${first.label}`]: 'Original unfinished exact source quotation.',
      [`Explain your check of ${first.label}`]: 'Original unfinished explanation of the source amount.',
      'Explain what these additions establish and what remains unresolved': 'Original learner explanation of what these additions establish and the source limits that remain unresolved.' } },
    { ...shared, name: 'budget-method', form: 'Capture budget workflow', fields: { [budget.listing.case.questions.find(q => q.id === 'method_choice').prompt]: 'My original explanation of the interpretation method and recorded arithmetic for this exact calculation and workflow revision.' } })
}
if (process.env.REVIEW_WORKFLOW_DESIGN_DRAFTS === '1') {
  const workflow = JSON.parse(await readFile('../artifacts/visual-review/certification-workflow-design-drafts-2026-10-08/http-fixture.json', 'utf8'))
  scenarios.splice(0, scenarios.length, { name: 'workflow-design-approval', moduleId: 'workflow_design', property: 'workflowDesignAssessment', endpoint: 'designs', listing: workflow.listing,
    saved: workflow.capture, kind: 'capture', reference: workflow.capture.uuid, form: 'Your workflow design decisions',
    fields: { 'Trace the saved data flow': 'My original trace of the exact captured workflow inputs and outputs.', 'Correction and approval boundary': 'My original boundary: this captured design is internal and requires a separate execution approval.',
      'Evidence and review path': 'My original explanation of supported evidence, unresolved facts and the stop path for this captured revision.' } })
}
if (process.env.REVIEW_PROCESS_DRAFTS === '1') {
  const process = JSON.parse(await readFile('../artifacts/visual-review/certification-early-draft-preservation-2026-10-08/http-fixture.json', 'utf8'))
  scenarios.splice(0, scenarios.length, { name: 'process-design', moduleId: 'process_mapping', property: 'processAssessment', endpoint: 'process-designs', listing: process.listing,
    saved: process.listing, kind: 'assignment', reference: '', form: 'Your process design',
    fields: { 'Working method and rationale': 'My original rationale for this bounded recurring process.', 'Corrected process map': 'My original process map with explicit source checking, a human decision and a stop before release.',
      'Bounded task brief': 'My original brief limiting inputs, audience and outputs, and preserving unresolved work for review.' } })
}
let outputFixture
if (process.env.REVIEW_OUTPUT_DRAFTS === '1') {
  outputFixture = JSON.parse(await readFile('../artifacts/visual-review/certification-output-drafts-2026-10-08/http-fixture.json', 'utf8'))
  const { listing, run, handoff } = outputFixture
  const shared = { moduleId: 'output_delivery', property: 'outputWorkflowAssessment', endpoint: 'output-workflows', listing }
  scenarios.splice(0, scenarios.length,
    { ...shared, name: 'output-inspection', saved: run, kind: 'run', reference: run.run_id, form: 'Inspect files and approve release', choice: 'Release choice', checkboxes: true,
      fields: Object.fromEntries([...run.result.generated_artifacts.files.map(file => [`What you checked in ${file.filename}`, 'My original learner observation of this exact generated file.']), ...listing.case.questions.filter(q => q.phase === 'after_generation_before_release').map(q => [q.prompt, 'My original inspection explanation of the exact files and private learner-only release scope.'])]) },
    { ...shared, name: 'output-interpretation', saved: handoff, kind: 'handoff', reference: handoff.uuid, form: 'Explain delivery outcome',
      fields: { [listing.case.questions.find(q => q.id === 'delivery_review').prompt]: 'My original explanation of the controlled failed handoff: no private copy or external delivery is confirmed.' } })
}
for (const item of scenarios) Object.assign(modules.find(m => m.id === item.moduleId), { [item.property]: item.listing.case, assessment: null })
let active = scenarios[0]
const switching = process.env.REVIEW_COURSE_SWITCH_DRAFTS === '1'
let alternate = false, choiceRevision = 0, switchPreview = null
const identity = (other = alternate) => ({ enrollment_id: other ? 'a1'.repeat(16) : active.listing.enrollment_id,
  course_version: other ? 'alternate-draft-qa' : active.listing.course_version, manifest_sha256: other ? 'b2'.repeat(32) : active.listing.manifest_sha256,
  course_title: other ? 'Alternate saved course QA' : 'Practical draft QA', module_ids: modules.map(m => m.id), modules_total: modules.length, maximum_xp: 2675 })
const summary = other => ({ ...identity(other), total_xp: 0, completed_modules: 0, credential_id: null, has_saved_place: false, record_counts: {} })

const course = () => ({ ...structure, ...identity(), versioned: true, prerequisites: Object.fromEntries(modules.map(m => [m.id, []])), modules: modules.map(m => m.id === active.moduleId ? { ...m, [active.property]: active.listing.case } : m) })
const progress = () => ({ ...identity(), id: 'draft-qa', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, learning_position: null })
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5305', resetStorage: false,
  evidenceMode: switching ? 'Frozen production frontend; synthetic saved-course selection and owned-history fixtures. Explicit UI switch away/return retains original authored drafts; no assessment submissions, executions or credit. Not durable migration evidence.' : 'Frozen production frontend; synthetic owned-history API fixtures. Tab-local practical drafts across reload/navigation with zero submissions, execution, grading or credit.' })
const { page, context } = review
const writes = []
await context.route('**/api/certification/**', route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (request.method() !== 'GET') writes.push({ method: request.method(), path })
  if (switching && path.endsWith('/saved-course-options')) return route.fulfill({ json: { current_enrollment_id: identity().enrollment_id, read_only: true, next_cursor: null,
    courses: [{ activation_id: 'c3'.repeat(16), action: alternate ? 'return_to_original_course' : 'resume_upgraded_course', ...identity(!alternate), definition_available: true }] } })
  if (switching && path.endsWith('/saved-course-preview')) {
    const action = alternate ? 'return_to_original_course' : 'resume_upgraded_course'
    switchPreview = { request: { request_id: (++choiceRevision).toString(16).padStart(32, '0'), activation_id: 'c3'.repeat(16), action, preview_sha256: 'd4'.repeat(32), consent: 'select_saved_course_preserving_both_histories_and_credit' },
      preview: { schema_version: 1, activation_id: 'c3'.repeat(16), action, read_only: true, can_activate: false, credit_transferred: false, selection_revision: choiceRevision,
        source: summary(alternate), target: summary(!alternate), preservation_policy: 'keep_both_existing_enrollments_and_original_workspace_references', state_sha256: 'e5'.repeat(32), preview_sha256: 'd4'.repeat(32) } }
    return route.fulfill({ json: switchPreview })
  }
  if (switching && request.method() === 'POST' && path.endsWith('/saved-course-selections')) {
    assert.deepEqual(request.postDataJSON(), switchPreview.request)
    const source = identity(), target = identity(!alternate)
    alternate = !alternate
    return route.fulfill({ json: { current_enrollment_id: target.enrollment_id, confirmation_pending: false, receipt: {
      request_id: switchPreview.request.request_id, kind: 'saved_course_selection.1', receipt_sha256: 'f6'.repeat(32), source_enrollment_id: source.enrollment_id,
      target_enrollment_id: target.enrollment_id, target_course_version: target.course_version, target_manifest_sha256: target.manifest_sha256,
      revision: choiceRevision, selected_at: '2026-10-08T23:00:00Z', action: switchPreview.request.action, credit_transferred: false, histories_preserved: true } } })
  }
  assert.equal(request.method(), 'GET')
  if (switching && path.endsWith('/selection-status')) return route.fulfill({ json: { read_only: true, current_enrollment_id: identity().enrollment_id, pending: null } })

  if (path.endsWith('/progress')) return route.fulfill({ json: progress() })
  if (path.endsWith('/course')) return route.fulfill({ json: course() })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (path.endsWith('/practical-runs')) return route.fulfill({ json: { runs: [], older_runs_available: false } })
  if (path.endsWith(`/modules/${active.moduleId}/${active.endpoint}`)) return route.fulfill({ json: active.listing })
  if (active.comparisonRuns) {
    const saved = active.comparisonRuns.find(value => path.endsWith(`/connected-runs/${value.run_id}`))
    if (saved) return route.fulfill({ json: saved })
  }
  if (outputFixture) {
    for (const [suffix, saved] of [['output-runs', outputFixture.run], ['output-file-reviews', outputFixture.inspection], ['output-handoffs', outputFixture.handoff]]) {
      if (path.endsWith(`/${suffix}/${saved.uuid || saved.run_id}`)) return route.fulfill({ json: saved })
    }
  }
  if (path.endsWith(`/workflow-design-captures/${active.reference}`) || path.endsWith(`/budget-calculations/${active.reference}`) || path.endsWith(`/budget-runs/${active.reference}`) || path.endsWith(`/batch-runs/${active.reference}`) || path.endsWith(`/connected-runs/${active.reference}`) || path.endsWith(`/validation-${active.kind === 'capture' ? 'captures' : 'runs'}/${active.reference}`) || path.endsWith(`/governance/${active.kind}/${active.reference}`)) return route.fulfill({ json: active.saved })
  return route.fallback()
})
async function openForm() {
  if (active.moduleId === 'workflow_design') await page.evaluate(({ key, reference }) => sessionStorage.setItem(key, reference), { key: `certification-workflow-capture:${active.listing.enrollment_id}:${active.listing.case.case_sha256}:selected`, reference: active.reference })
  await page.goto(review.baseURL + '/certification', { waitUntil: 'networkidle' })
  const panel = page.locator('[data-cert-panel]')
  await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  const module = modules.find(m => m.id === active.moduleId)
  // A reload can retain the current module; returning to overview is unnecessary.
  if (!await panel.getByRole('button', { name: 'Challenge', exact: true }).count()) await panel.getByRole('button', { name: new RegExp(`^${module.number} ${module.title}`) }).click()
  await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
  if (active.moduleId === 'process_mapping') {
    // This assignment opens its authored form directly.
  } else if (active.moduleId === 'workflow_design') {
    // The original selected capture is reread by the production capture component.
  } else if (active.moduleId === 'output_delivery') {
    await panel.getByRole('combobox', { name: 'Open saved output work', exact: true }).selectOption(`${active.kind}:${active.reference}`)
    await panel.getByRole('button', { name: active.kind === 'run' ? 'Inspect these files and choose release scope' : 'Explain this actual delivery outcome', exact: true }).click()
  } else if (active.moduleId === 'advanced_nodes') {
    await panel.getByRole('combobox', { name: 'Open saved budget work', exact: true }).selectOption(`${active.kind}:${active.reference}`)
    await panel.getByRole('button', { name: active.name === 'budget-calculation' ? 'Revise these calculations' : active.name === 'budget-method' ? 'Use these saved calculations' : 'Review this completed budget run', exact: true }).click()
    if (active.name === 'budget-method') await panel.getByRole('combobox', { name: 'Owned budget workflow', exact: true }).selectOption(active.listing.workflows[0].workflow_id)
  } else if (active.moduleId === 'batch_processing') {
    await panel.getByRole('combobox', { name: 'Saved record type', exact: true }).selectOption('run')
    await panel.getByRole('textbox', { name: 'Saved batch reference', exact: true }).fill(active.reference)
    await panel.getByRole('button', { name: 'Open saved batch reference', exact: true }).click()
    await panel.getByRole('button', { name: 'Reconcile inventory and explain recovery', exact: true }).click()
  } else if (active.moduleId === 'multi_step') {
    if (active.comparisonRuns) {
      for (const [index, saved] of active.comparisonRuns.entries()) {
        await panel.getByRole('combobox', { name: 'Open saved connected work', exact: true }).selectOption(`run:${saved.run_id}`)
        await panel.getByRole('button', { name: index ? 'Use as corrected run' : 'Use as original run', exact: true }).click()
      }
    } else await panel.getByRole('combobox', { name: 'Open saved connected work', exact: true }).selectOption(`run:${active.reference}`)
  } else {
    const validation = active.moduleId === 'validation_qa'
    await panel.getByRole('combobox', { name: validation ? 'Saved record type' : 'Saved capstone record type', exact: true }).selectOption(active.kind)
    await panel.getByRole('textbox', { name: validation ? 'Saved validation reference' : 'Saved capstone reference', exact: true }).fill(active.reference)
    await panel.getByRole('button', { name: validation ? 'Open saved validation reference' : 'Open saved capstone reference', exact: true }).click()
  }
  if (active.name === 'validation-interpretation') await panel.getByRole('button', { name: 'Explain the repair and complete retest', exact: true }).click()
  const form = panel.getByRole('form', { name: active.form, exact: true })
  if (active.name === 'correction') await panel.getByText('Start an original diagnostic exercise from this capture', { exact: true }).click()
  await form.waitFor()
  return form
}
async function switchCourse() {
  const panel = page.locator('[data-cert-panel]')
  const curriculum = panel.getByRole('button', { name: 'Curriculum', exact: true })
  if (await curriculum.count()) await curriculum.click()
  const details = panel.locator('details').filter({ has: page.locator('summary').filter({ hasText: /^Course progress and credential$/ }) }).first()
  if (await details.getAttribute('open') === null) await details.locator('summary').first().click()
  await panel.getByRole('button', { name: 'Choose a saved course', exact: true }).click()
  await panel.getByRole('button', { name: `Review ${identity(!alternate).course_title}`, exact: true }).click()
  const region = panel.getByRole('region', { name: 'Saved course preservation review', exact: true })
  const oldAlternate = alternate
  await region.getByRole('checkbox').check()
  await region.getByRole('button', { name: alternate ? 'Return to original course' : 'Resume upgraded course', exact: true }).click()
  await region.getByRole('button', { name: 'Refresh my course', exact: true }).click()
  assert.equal(alternate, !oldAlternate)
  await page.waitForFunction(title => document.querySelector('[aria-label="Your course"]')?.textContent === title, identity().course_title)
  assert.equal(await panel.getByRole('form', { name: active.form, exact: true }).count(), 0)
}
async function snap(id, form) {
  const status = form.getByRole('status')
  await status.scrollIntoViewIfNeeded()
  const clipped = await form.evaluate(root => [root, ...root.querySelectorAll('button,p,label,legend,textarea,input')].filter(el => el.clientWidth && !['TEXTAREA','INPUT'].includes(el.tagName) && el.scrollWidth > el.clientWidth + 1).map(el => el.tagName))
  assert.deepEqual(clipped, [])
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
const inspectControls = process.env.REVIEW_ASSESSMENT_CONTROLS === '1'
async function inspectFormControls(form) {
  const controls = await form.locator('input,textarea,select').evaluateAll(elements => elements.map(element => ({
    tag: element.tagName, type: element.type, required: element.required, disabled: element.disabled,
    label: [...element.labels || []].map(label => label.textContent.trim()).join(' '),
    describedBy: (element.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean).map(id => document.getElementById(id)?.textContent?.trim() || null),
    group: element.closest('fieldset')?.querySelector('legend')?.textContent?.trim() || null,
  })))
  assert.ok(controls.length, `${active.name}: controls must be present`)
  for (const control of controls) {
    assert.ok(control.label, `${active.name}: each control needs its associated label`)
    assert.ok(control.describedBy.every(Boolean), `${active.name}: instruction references must resolve`)
    if (control.type === 'radio') assert.ok(control.group, `${active.name}: radio choices need a named group`)
  }
  const answer = form.locator('textarea[required]:enabled').first()
  assert.equal(await answer.count(), 1, `${active.name}: required answer exposed`)
  const value = await answer.inputValue()
  await answer.fill('')
  assert.equal(await answer.evaluate(element => element.reportValidity()), false)
  assert.equal(await answer.evaluate(element => element === document.activeElement), true)
  await page.keyboard.insertText(value + ' Keyboard correction retained.')
  assert.equal(await answer.inputValue(), value + ' Keyboard correction retained.')
  await page.keyboard.press('Tab')
  review.observations.push({ form: active.form, controls, nativeRequiredErrorFocused: true, keyboardCorrection: true, submissions: 0 })
}
try {
  for (const width of native ? [780] : inspectControls ? [320] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1800 : 1100 })
    for (const scenario of scenarios) {
      active = scenario
      alternate = false
      await page.goto(review.baseURL, { waitUntil: 'networkidle' })
      await page.evaluate(() => { localStorage.clear(); sessionStorage.clear() })
      let form = await openForm()
      if (native) await review.setBrowserZoom(2)
      if (active.radios) for (const label of active.radios) await form.getByRole('radio', { name: label, exact: true }).check()
      if (active.checkboxes) for (const box of await form.getByRole('checkbox').all()) await box.check()
      if (active.checkbox) await form.getByRole('checkbox').check()
      if (active.choice) await form.getByRole('combobox', { name: active.choice, exact: true }).selectOption('approve')
      for (const [label, value] of Object.entries(active.fields)) await form.getByRole('textbox', { name: label, exact: true }).first().fill(value)
      if (inspectControls) {
        await inspectFormControls(form)
        await snap(`${active.name}-controls-${width}`, form)
        continue
      }
      await snap(`${active.name}-draft-${width}`, form)
      if (switching) {
        const draftsBefore = await page.evaluate(() => Object.fromEntries(Object.entries(sessionStorage).filter(([key]) => (key.startsWith('cert-course-draft:') || key.startsWith('certification-process-draft:')))))
        await switchCourse()
        assert.deepEqual(await page.evaluate(() => Object.fromEntries(Object.entries(sessionStorage).filter(([key]) => (key.startsWith('cert-course-draft:') || key.startsWith('certification-process-draft:'))))), draftsBefore)
        await switchCourse()
      }
      form = await openForm()
      for (const [label, value] of Object.entries(active.fields)) assert.equal(await form.getByRole('textbox', { name: label, exact: true }).first().inputValue(), value)
      if (active.choice) {
        assert.equal(await form.getByRole('combobox', { name: active.choice, exact: true }).inputValue(), 'approve')
        if (!active.checkboxes) assert.equal(await form.getByRole('button').count(), 1)
        if (active.radios) for (const label of active.radios) await form.getByRole('radio', { name: label, exact: true }).check()
      if (active.checkboxes) for (const box of await form.getByRole('checkbox').all()) assert.equal(await box.isChecked(), true)
        if ('can_execute' in active.saved) assert.equal(active.saved.can_execute, false)
        if (active.checkbox) assert.equal(await form.getByRole('checkbox').isChecked(), true)
      }
      if (active.radios) for (const label of active.radios) assert.equal(await form.getByRole('radio', { name: label, exact: true }).isChecked(), true)
      assert.match(await form.getByRole('status').innerText(), /Draft kept in this browser tab/)
      await snap(`${active.name}-restored-${width}`, form)
      await page.evaluate(() => {
        window.originalDraftStorage = Storage.prototype.setItem
        Storage.prototype.setItem = function(key, value) { if ((key.startsWith('cert-course-draft:') || key.startsWith('certification-process-draft:'))) throw new Error('Synthetic draft storage failure'); return window.originalDraftStorage.call(this, key, value) }
      })
      const [label, original] = Object.entries(active.fields)[0]
      await form.getByRole('textbox', { name: label, exact: true }).first().fill(original + ' Current edit retained.')
      assert.match(await form.getByRole('status').innerText(), /Keep this form open/)
      await snap(`${active.name}-storage-unavailable-${width}`, form)
      await page.evaluate(() => { Storage.prototype.setItem = window.originalDraftStorage; delete window.originalDraftStorage })
    }
  }
  if (switching) {
    assert.equal(writes.length, scenarios.length * (native ? 1 : 2) * 2)
    assert.ok(writes.every(item => item.method === 'POST' && item.path.endsWith('/saved-course-selections')))
  } else assert.deepEqual(writes, [])
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  review.observations.push(inspectControls
    ? { inspectedForms: scenarios.map(s => s.name), noAutomaticSubmissions: true, modelRequests: 0, credit: 0, actualAssistiveTechnology: false }
    : { restoredDrafts: scenarios.map(s => s.name), noAutomaticSubmissions: true, storageFailureExplained: true, modelRequests: 0, credit: 0, optionalCourseSwitches: switching ? writes.length : 0, selectionFixtureOnly: switching })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
