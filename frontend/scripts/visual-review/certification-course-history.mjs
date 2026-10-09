import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'

const data = new URL('../../../backend/certification-data/', import.meta.url)
const read = async name => JSON.parse(await readFile(new URL(name, data), 'utf8'))
const modules = await read('panel-modules.json')
const structure = await read('course-structure.json')
const prompts = (await read('drafts/v5.0/foundations-decisions.json')).map((prompt, index) => ({ ...prompt, prompt_sha256: String(index + 1).repeat(64) }))
const module = modules.find(item => item.id === 'foundations')
module.decisionPrompts = prompts; module.assessment = null; module.practicalPreparation = true
const identity = { enrollment_id: 'b'.repeat(32), course_version: 'qa-practical-review-draft', manifest_sha256: 'b'.repeat(64), course_title: 'Local practical review fixture', modules_total: modules.length, module_ids: modules.map(item => item.id), maximum_xp: 2675 }
const course = { ...identity, ...structure, versioned: true, prerequisites: Object.fromEntries(modules.map(item => [item.id, []])), modules }
const progress = { ...identity, learning_position: null, position_revision: 0, id: 'qa-progress', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, last_activity_date: null }
const runId = 'a'.repeat(32)
const source = 'Principal Investigator: Sarah Chen\nInstitution: University of Idaho\nTotal Budget: USD 485000\nProject Period: January 2026 through December 2028\nSponsoring Agency: National Science Foundation\n\nThis synthetic source is used only for local interface testing.'
const fields = prompts[1].required_fields
const proposalEnabled = process.env.REVIEW_SCOPE_PROPOSAL === '1'
const proposal = proposalEnabled ? { case: await read('drafts/v5.0/foundations-proposal.json'),
  proposal_sha256: 'e'.repeat(64), original_source_id: 'course_asset:nih-r01-neuroscience.pdf',
  source_options: [{ id: 'course_asset:nih-r01-neuroscience.pdf', title: 'nih-r01-neuroscience.pdf' },
    { id: 'assigned-source', title: 'Assigned NSF proposal — saved source' }] } : null
let runState = 'completed', empty = false, loseResponse = true
let reason = 'This is saved history from a different course. It remains available for reading; new work belongs to your selected course.'
const receipts = new Map(), submissions = []
let mode = 'ready'
const historyReads = []
const oldCourse = { ...identity, enrollment_state: 'transferred', read_only: true, modules: [{ module_id: module.id, title: module.title, decision_prompts: prompts }] }
const historyList = { read_only: true, older_courses_available: true, courses: [{ ...identity, enrollment_state: 'transferred', created_at: '2026-10-01T12:00:00Z', definition_available: true }] }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5292', resetStorage: false })
const { page, context } = review
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: '#581c87', ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url()), path = url.pathname
  if (path.includes('/practical-history')) {
    assert.equal(request.method(), 'GET'); historyReads.push(path)
    if (path.endsWith('/practical-history')) return route.fulfill({ status: mode === 'list_error' ? 503 : 200, json: mode === 'list_error' ? { detail: 'Synthetic outage' } : mode === 'empty' ? { ...historyList, courses: [] } : historyList })
    return route.fulfill({ status: mode === 'course_error' ? 503 : 200, json: mode === 'course_error' ? { detail: 'Original definition unavailable' } : mode === 'mismatch' ? { ...oldCourse, enrollment_id: 'foreign-course' } : mode === 'legacy' ? { ...oldCourse, modules: [], provenance: 'legacy_version_unknown' } : oldCourse })
  }
  if (path.endsWith('/automatic-reviews')) return route.fulfill({ json: { enrollment_id: identity.enrollment_id, module_id: module.id, attempts: [], older_attempts_available: false } })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/progress') && mode === 'progress_error') return route.fulfill({ status: 503, json: { detail: 'Synthetic current-course outage' } })
  if (path.endsWith('/progress')) return route.fulfill({ json: { ...progress, enrollment_id: 'c'.repeat(32) } })
  if (path.endsWith('/course')) return route.fulfill({ json: { ...course, enrollment_id: 'c'.repeat(32) } })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (path.endsWith('/position')) {
    const body = request.postDataJSON()
    progress.position_revision++
    progress.learning_position = { module_id: body.module_id, lesson_id: body.lesson_id, revision: 1, content_sha256: 'c'.repeat(64), saved_at: new Date().toISOString() }
    return route.fulfill({ json: { saved: true, ...identity, position_revision: progress.position_revision, learning_position: progress.learning_position } })
  }
  if (path.endsWith('/practical-runs')) return route.fulfill({ json: { enrollment_id: identity.enrollment_id, module_id: module.id, read_only_reason: reason, runs: empty ? [] : [{ run_id: runId, state: runState }], older_runs_available: false } })
  if (path.includes('/learner-decisions/')) {
    const record = receipts.get(path.split('/').at(-1))
    return route.fulfill({ status: record ? 200 : 404, json: record || { detail: 'Not found' } })
  }
  if (path.includes('/decisions/')) {
    const promptId = path.split('/decisions/')[1].split('/')[0]
    const prompt = prompts.find(item => item.id === promptId)
    if (path.includes('/runs/')) {
      const latest = [...receipts.values()].filter(item => item.prompt_id === promptId).at(-1) || null
      return route.fulfill({ json: { enrollment_id: identity.enrollment_id, module_id: module.id, prompt,
        run_id: runId, run_state: runState, can_submit: false, read_only_reason: reason,
        lab_folder_id: 'Certification training lab', artifact: { title: 'Reviewed NSF proposal extraction', fields: fields.map(searchphrase => ({ searchphrase, is_optional: false })) },
        documents: [{ document_id: 'assigned-source', title: 'Assigned NSF proposal — saved source', text: source }],
        scope_proposal: proposal,
        result: runState === 'completed' ? { entities: [{ 'PI Name': 'Sarah Chen', Institution: 'University of Idaho', 'Total Budget': 'USD 485000', 'Project Period': '2026–2028', 'Sponsoring Agency': 'National Science Foundation' }] } : null,
        latest_decision: latest } })
    }
    assert.equal(request.method(), 'POST')
    assert.equal(url.searchParams.get('enrollment_id'), identity.enrollment_id)
    const body = request.postDataJSON(); submissions.push(body)
    if (body.value_checks.some(check => check.source_quote && !source.includes(check.source_quote))) return route.fulfill({ status: 422, json: { detail: 'Each source check must cite the saved assigned document' } })
    const record = { uuid: body.request_id, enrollment_id: identity.enrollment_id, module_id: module.id, run_id: runId,
      prompt_id: promptId, prompt_sha256: prompt.prompt_sha256, submitted_at: new Date().toISOString(), submission: body, credit_awarded: false }
    receipts.set(record.uuid, record)
    if (loseResponse) { loseResponse = false; return route.fulfill({ status: 503, json: { detail: 'Synthetic lost response after saving' } }) }
    return route.fulfill({ json: record })
  }
  return route.fallback()
})
const history = page.getByRole('region', { name: 'Saved course work', exact: true })
const panel = page.getByRole('region', { name: 'Practical review', exact: true })
async function enter() {
  await page.goto(review.baseURL + '/certification', { waitUntil: 'domcontentloaded' })
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  if (mode !== 'progress_error') await page.getByText('Course progress and credential', { exact: true }).click()
  await history.getByRole('button', { name: 'Browse saved course work', exact: true }).click()
}
async function selectCourse() {
  await history.getByRole('combobox', { name: 'Saved course', exact: true }).selectOption(identity.enrollment_id)
  await history.getByRole('region', { name: 'Original course history', exact: true }).waitFor()
  await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Original course history')
}
async function capture(id) {
  await review.capture(id, 'Synthetic owned course history in the production frontend. Opening history does not change selection, submit work or call a model.')
  if (process.env.REVIEW_TEXT_SCALE === '2') {
    const overflow = await history.evaluate(root => [root, ...root.querySelectorAll('button,p,h3,h4,h5,h6,summary')].filter(el => el.clientWidth && el.scrollWidth > el.clientWidth + 1).map(el => el.textContent.slice(0,80)))
    assert.deepEqual(overflow, [], 'History content clips at enlarged text')
  }
  console.log(id)
}
try {
  for (const width of (process.env.REVIEW_WIDTHS || '320,390,1440').split(',').map(Number)) {
    mode = 'ready'; await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 }); await enter()
    await history.getByRole('combobox', { name: 'Saved course', exact: true }).scrollIntoViewIfNeeded(); await capture('course-list-' + width)
    await selectCourse(); await capture('original-course-' + width)
    await history.getByRole('combobox', { name: 'Saved module', exact: true }).selectOption('foundations')
    await panel.getByRole('combobox', { name: 'Saved run', exact: true }).selectOption(runId)
    await panel.getByText('Saved source: Assigned NSF proposal — saved source', { exact: true }).click()
    await panel.getByRole('region', { name: 'Saved source text: Assigned NSF proposal — saved source', exact: true }).focus(); await capture('historical-source-' + width)
    await panel.getByRole('combobox', { name: 'Review stage', exact: true }).selectOption('value_review')
    await panel.getByRole('region', { name: 'Saved extraction values', exact: true }).focus(); await capture('historical-values-' + width)
    assert.equal(await panel.getByRole('button', { name: 'Save my decision', exact: true }).isEnabled(), false)
    for (const name of ['Prepare a practical run', 'Execute saved practical run', 'Request automatic assessment']) assert.equal(await panel.getByRole('region', { name, exact: true }).count(), 0)
    await panel.getByRole('button', { name: 'View saved assessments', exact: true }).click()
    await panel.getByText('No saved assessments are available for this module yet.', { exact: true }).waitFor()
    await panel.getByRole('region', { name: 'Saved automatic assessments', exact: true }).scrollIntoViewIfNeeded(); await capture('historical-feedback-' + width)
    await history.getByRole('button', { name: 'Close saved course work', exact: true }).click()
    assert.equal(await history.getByRole('button', { name: 'Browse saved course work', exact: true }).evaluate(el => el === document.activeElement), true)
  }
  await page.setViewportSize({ width: 390, height: 844 })
  for (const current of ['empty', 'list_error', 'course_error', 'mismatch', 'legacy', 'progress_error']) {
    mode = current; await enter()
    if (['course_error', 'mismatch'].includes(current)) { await history.getByRole('combobox', { name: 'Saved course', exact: true }).selectOption(identity.enrollment_id); await history.getByRole('alert').waitFor() }
    else if (current === 'legacy' || current === 'progress_error') await selectCourse()
    else if (current === 'list_error') await history.getByRole('alert').waitFor()
    else await history.getByText('No saved course enrollments are available yet.', { exact: true }).waitFor()
    await history.scrollIntoViewIfNeeded(); await capture('history-' + current + '-390')
  }
  mode = 'ready'; await history.getByText('Open a course by reference', { exact: true }).click()
  await history.getByRole('textbox', { name: 'Full enrollment reference', exact: true }).fill(identity.enrollment_id)
  await history.getByRole('button', { name: 'Open original course', exact: true }).click()
  await history.getByRole('region', { name: 'Original course history', exact: true }).waitFor(); await capture('history-reference-390')
  assert.equal(submissions.length, 0); assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  for (const item of review.captures) {
    assert.equal(item.pageWidth, item.viewport.width, item.id + ' horizontal overflow')
    assert.deepEqual(JSON.parse(await readFile(resolve(review.out, item.id + '.axe.json'), 'utf8')), [], item.id + ' accessibility')
  }
  review.observations.push({ synthetic: true, historyReads: historyReads.length, submissionWrites: 0, selectionWrites: 0, liveModelCalls: 0 })
} catch (error) {
  console.error('Course history check failed:', error); review.observations.push({ failed: true, message: String(error) }); throw error
} finally { await review.flush(); await review.browser.close() }
