import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const read = async path => JSON.parse(await readFile(new URL(path, import.meta.url), 'utf8'))
const modules = await read('../../../backend/certification-data/panel-modules.json')
const structure = await read('../../../backend/certification-data/course-structure.json')
const processFixture = await read('../../../artifacts/visual-review/certification-early-draft-preservation-2026-10-08/http-fixture.json')
const workflowFixture = await read('../../../artifacts/visual-review/certification-workflow-design-drafts-2026-10-08/http-fixture.json')
const scenarios = [
  { module: 'process_mapping', property: 'processAssessment', listing: processFixture.listing,
    fields: ['Working method and rationale', 'Corrected process map', 'Bounded task brief'] },
  { module: 'workflow_design', property: 'workflowDesignAssessment', listing: workflowFixture.listing,
    fields: ['Trace the saved data flow', 'Correction and approval boundary', 'Evidence and review path'] },
]
let active = scenarios[0], captureReceipt = null, saved = null
const writes = []
const identity = () => ({ enrollment_id: active.listing.enrollment_id, course_version: active.listing.course_version, manifest_sha256: active.listing.manifest_sha256,
  course_title: 'Local design status QA', module_ids: modules.map(m => m.id), modules_total: modules.length, maximum_xp: 2675 })
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5307', resetStorage: false,
  evidenceMode: 'Frozen production frontend, synthetic held design writes and reads. No real learner, workflow execution, model, grade or credit.' })
const { page, context } = review
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: '#581c87', ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
await context.route('**/api/certification/**', route => {
  const request = route.request(), path = new URL(request.url()).pathname, post = request.method() === 'POST'
  if (post) writes.push({ path, body: request.postDataJSON() })
  if (path.endsWith('/course')) return route.fulfill({ json: { ...structure, ...identity(), versioned: true,
    prerequisites: Object.fromEntries(modules.map(m => [m.id, []])), modules: modules.map(m => m.id === active.module ? { ...m, [active.property]: active.listing.case, assessment: null } : m) } })
  if (path.endsWith('/progress')) return route.fulfill({ json: { ...identity(), user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, learning_position: null } })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (path.endsWith('/practical-runs')) return route.fulfill({ json: { runs: [], older_runs_available: false } })
  if (post && path.endsWith('/design-captures')) {
    const body = request.postDataJSON()
    captureReceipt = { ...workflowFixture.capture, uuid: body.request_id, request: body }
    return route.fulfill({ status: 503, json: { detail: 'Synthetic lost capture response' } })
  }
  if (post && (path.endsWith('/process-designs') || path.endsWith('/designs'))) {
    const body = request.postDataJSON()
    saved = { ...identity(), uuid: body.request_id, module_id: active.module, submission: body, submitted_at: '2026-10-09T16:00:00Z', credit_awarded: false, module_completion_eligible: false,
      ...(active.module === 'process_mapping' ? { case: active.listing.case, submission_channel: 'authenticated_learner_process_request' }
        : { input_snapshot: captureReceipt, execution_authorized: false, submission_channel: 'authenticated_learner_workflow_design_request' }) }
    return route.fulfill({ status: 503, json: { detail: 'Synthetic lost save response' } })
  }
  if (captureReceipt && path.endsWith('/workflow-design-captures/' + captureReceipt.uuid)) return route.fulfill({ json: captureReceipt })
  if (saved && (path.endsWith('/process-designs/' + saved.uuid) || path.endsWith('/workflow-designs/' + saved.uuid))) return route.fulfill({ json: saved })
  if (path.endsWith(`/modules/${active.module}/${active.module === 'process_mapping' ? 'process-designs' : 'designs'}`)) return route.fulfill({ json: active.listing })
  if (path.endsWith('/automatic-reviews')) return route.fulfill({ json: { ...identity(), module_id: active.module, attempts: [], older_attempts_available: false } })
  return route.fallback()
})
let unblock = null, handler = null
async function hold(fragment, method) {
  handler = async route => {
    if (route.request().method() === method && new URL(route.request().url()).pathname.endsWith(fragment)) await new Promise(resolve => { unblock = resolve })
    return route.fallback()
  }
  await context.route('**/api/**', handler)
}
async function release() { await context.unroute('**/api/**', handler); unblock?.(); unblock = null }
const panel = page.locator('[data-cert-panel]')
async function captureStatus(text, id) {
  const status = panel.getByRole('status').filter({ hasText: text })
  await status.waitFor(); await status.scrollIntoViewIfNeeded()
  await review.capture(id, 'Held synthetic request; closing is not cancellation; checking causes no second write.')
}
async function pendingCycle({ suffix, send, sending, check, readSuffix, done, id }) {
  await hold(suffix, 'POST')
  const button = panel.getByRole('button', { name: send, exact: true })
  await button.focus(); await button.press('Enter')
  await captureStatus(sending, id + '-sending')
  assert.equal(await panel.getByText(/Closing this panel does not confirm/).count(), 1)
  await release()
  const checkButton = panel.getByRole('button', { name: check, exact: true })
  await checkButton.waitFor(); await panel.getByRole('alert').filter({ hasText: /could not confirm/ }).waitFor()
  const count = writes.length
  await hold(readSuffix(), 'GET'); await checkButton.click()
  await captureStatus('Checking the saved state', id + '-checking')
  assert.equal(writes.length, count)
  assert.equal(await panel.getByText('This check does not start, repeat or grade work.').count(), 1)
  await release(); await panel.getByRole('region', { name: done, exact: true }).waitFor()
  assert.equal(writes.length, count)
}
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
try {
  for (const width of native ? [780] : [320, 1440]) for (active of scenarios) {
    await page.setViewportSize({ width, height: native ? 1688 : 1000 })
    if (page.url().startsWith(review.baseURL)) await page.evaluate(() => sessionStorage.clear())
    captureReceipt = null; saved = null; writes.length = 0
    await page.goto(review.baseURL + '/certification', { waitUntil: 'networkidle' })
    await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    const module = modules.find(m => m.id === active.module)
    await panel.getByRole('button', { name: new RegExp(`^${module.number} ${module.title}`) }).click()
    await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
    if (active.module === 'workflow_design') {
      await panel.getByRole('combobox', { name: 'Saved workflow', exact: true }).selectOption(active.listing.workflows[0].workflow_id)
      await panel.getByRole('combobox', { name: 'Starting process map', exact: true }).selectOption(workflowFixture.capture.request.process_submission_id)
      await pendingCycle({ suffix: '/design-captures', send: 'Capture selected revision', sending: 'Sending the input capture', check: 'Check saved capture',
        readSuffix: () => '/workflow-design-captures/' + captureReceipt.uuid, done: 'Captured workflow configuration', id: 'capture-' + width })
    }
    for (const label of active.fields) await panel.getByRole('textbox', { name: label, exact: true }).fill('My bounded internal design preserves evidence and requires explicit human review before any release.')
    const process = active.module === 'process_mapping'
    await pendingCycle({ suffix: process ? '/process-designs' : '/designs', send: process ? 'Save my reviewed design' : 'Approve this saved revision',
      sending: process ? 'Sending the process design' : 'Sending the workflow approval', check: process ? 'Check saved design' : 'Check saved approval',
      readSuffix: () => (process ? '/process-designs/' : '/workflow-designs/') + saved.uuid, done: process ? 'Saved process design' : 'Saved workflow approval', id: active.module + '-' + width })
    assert.equal(writes.length, process ? 1 : 2)
  }
  for (const item of review.captures) {
    assert.equal(item.pageWidth, item.viewport.width, item.id + ' page overflow')
    assert.deepEqual(JSON.parse(await readFile(`${review.out}/${item.id}.axe.json`, 'utf8')), [])
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ delayedSyntheticRequests: true, repeatedWritesDuringChecks: 0, liveModels: 0, actualLearners: 0 })
} catch (error) { review.observations.push({ failed: true, message: String(error) }); throw error }
finally { unblock?.(); await review.flush(); await review.browser.close() }
