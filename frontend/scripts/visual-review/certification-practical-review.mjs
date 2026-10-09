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
module.decisionPrompts = prompts; module.assessment = null
const identity = { enrollment_id: 'qa-practical-review', course_version: 'qa-practical-review-draft', manifest_sha256: 'b'.repeat(64), course_title: 'Local practical review fixture', modules_total: modules.length, module_ids: modules.map(item => item.id), maximum_xp: 2675 }
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
let runState = 'prepared', empty = false, loseResponse = true
const receipts = new Map(), submissions = []
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5292', resetStorage: false })
const { page, context } = review
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: '#581c87', ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url()), path = url.pathname
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (path.endsWith('/position')) {
    const body = request.postDataJSON()
    progress.position_revision++
    progress.learning_position = { module_id: body.module_id, lesson_id: body.lesson_id, revision: 1, content_sha256: 'c'.repeat(64), saved_at: new Date().toISOString() }
    return route.fulfill({ json: { saved: true, ...identity, position_revision: progress.position_revision, learning_position: progress.learning_position } })
  }
  if (path.endsWith('/practical-runs')) return route.fulfill({ json: { runs: empty ? [] : [{ run_id: runId, state: runState }], older_runs_available: false } })
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
        run_id: runId, run_state: runState, can_submit: runState === (prompt.phase === 'before_execution' ? 'prepared' : 'completed'),
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
async function enter() {
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await page.getByRole('button', { name: /^1 Foundations/ }).click()
  await page.getByRole('button', { name: 'Challenge', exact: true }).click()
  await page.getByRole('heading', { name: 'Review your saved work', exact: true }).waitFor()
}
const panel = page.getByRole('region', { name: 'Practical review', exact: true })
async function capture(name) {
  await review.capture(name, 'Synthetic saved runs and HTTP receipts in the actual local production frontend. No real learner, model, execution or earned credit.')
  console.log(name)
}
try {
  await page.goto(review.baseURL + '/certification'); await enter()
  await capture('initial-run-selection')
  await panel.getByRole('combobox', { name: 'Saved run', exact: true }).selectOption(runId)
  await panel.getByText('Saved source: Assigned NSF proposal — saved source', { exact: true }).click()
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
    await panel.getByText('Reviewed NSF proposal extraction', { exact: true }).scrollIntoViewIfNeeded()
    await capture('scope-evidence-' + width)
  }
  await page.setViewportSize({ width: 390, height: 844 })
  if (proposalEnabled) {
    const selector = panel.getByRole('combobox', { name: 'Source I would authorize', exact: true })
    assert.equal(await selector.inputValue(), '', 'The learner must explicitly choose a source')
    for (const width of [320, 390, 1440]) {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
      await panel.getByLabel('Original scope proposal', { exact: true }).scrollIntoViewIfNeeded()
      await capture('original-proposal-' + width)
    }
    await selector.selectOption('assigned-source')
    for (const width of [320, 390, 1440]) {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
      await selector.scrollIntoViewIfNeeded()
      await capture('explicit-source-correction-' + width)
    }
    await page.setViewportSize({ width: 390, height: 844 })
  }
  await panel.getByLabel('This saved scope is ready to run', { exact: true }).check()
  await panel.getByRole('textbox', { name: 'Explain your decision', exact: true }).fill('I corrected the selected proposal and checked the saved fields against the assigned NSF task.')
  await panel.getByRole('button', { name: 'Save my decision', exact: true }).click()
  await panel.getByRole('alert').waitFor()
  assert.equal(submissions.length, 1)
  if (proposalEnabled) assert.deepEqual(submissions[0].proposal_selection, { proposal_sha256: proposal.proposal_sha256, source_id: 'assigned-source' })
  await capture('scope-unconfirmed-390')
  await page.reload()
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('button', { name: 'Open learning panel', exact: true }).click()
  await enter()
  await page.setViewportSize({ width: 390, height: 844 })
  await panel.getByRole('combobox', { name: 'Saved run', exact: true }).selectOption(runId)
  await panel.getByRole('button', { name: 'Check saved decision', exact: true }).scrollIntoViewIfNeeded()
  await capture('scope-restored-pending-390')
  await panel.getByRole('button', { name: 'Check saved decision', exact: true }).click()
  await panel.getByRole('button', { name: 'Save my decision', exact: true }).waitFor()
  assert.equal(submissions.length, 1, 'A saved receipt must resolve the lost response without another POST')
  if (proposalEnabled) {
    await panel.getByText('Your recorded source: Assigned NSF proposal — saved source', { exact: true }).waitFor()
    await panel.getByLabel('Saved practical decision', { exact: true }).scrollIntoViewIfNeeded()
  }
  await capture('scope-saved-390')
  runState = 'completed'
  await panel.getByRole('button', { name: 'Reload saved runs', exact: true }).click()
  await panel.getByText(/This run has already left preparation/).waitFor()
  await panel.getByText(/This run has already left preparation/).scrollIntoViewIfNeeded()
  await capture('scope-history-readonly-390')
  await panel.getByRole('combobox', { name: 'Review stage', exact: true }).selectOption('value_review')
  await panel.getByText('Saved extraction output', { exact: true }).waitFor()
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
    await panel.getByRole('group', { name: 'PI Name', exact: true }).scrollIntoViewIfNeeded()
    await capture('value-source-check-' + width)
  }
  await page.setViewportSize({ width: 390, height: 844 })
  await panel.getByLabel('I cannot verify all required values yet', { exact: true }).check()
  await panel.getByRole('textbox', { name: 'Explain your decision', exact: true }).fill('The investigator is supported; I still need to verify the remaining four required values.')
  for (const field of fields) {
    const group = panel.getByRole('group', { name: field, exact: true })
    await group.getByRole('textbox', { name: 'What did you establish?', exact: true }).fill('I have not established this value from the saved source yet.')
  }
  const pi = panel.getByRole('group', { name: 'PI Name', exact: true })
  await pi.getByRole('textbox', { name: 'Value you checked', exact: true }).fill('Sarah Chen')
  await pi.getByRole('combobox', { name: 'Source check', exact: true }).selectOption('supported')
  await pi.getByRole('textbox', { name: 'Exact source passage', exact: true }).fill('A quotation that does not occur in this source.')
  await panel.getByRole('button', { name: 'Save my decision', exact: true }).click()
  await panel.getByRole('alert').waitFor()
  await capture('invalid-quote-editable-390')
  assert.equal(await pi.getByRole('textbox', { name: 'Exact source passage', exact: true }).isEnabled(), true)
  await pi.getByRole('textbox', { name: 'Exact source passage', exact: true }).fill('Principal Investigator: Sarah Chen')
  await panel.getByRole('button', { name: 'Save my decision', exact: true }).click()
  await panel.getByRole('heading', { name: 'Decision saved', exact: true }).waitFor()
  await panel.getByText('Saved source checks', { exact: true }).click()
  await panel.getByText('Saved source checks', { exact: true }).scrollIntoViewIfNeeded()
  await capture('unresolved-values-saved-390')
  assert.equal(receipts.size, 2)
  assert.equal(progress.total_xp, 0)
  await review.flush()
  for (const item of review.captures) {
    assert.equal(item.pageWidth <= item.viewport.width, true, item.id + ' horizontal overflow')
    assert.deepEqual(JSON.parse(await readFile(resolve(review.out, item.id + '.axe.json'), 'utf8')), [], item.id + ' accessibility violations')
  }
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
} catch (error) {
  await capture('failure-state')
  throw error
} finally { await review.flush(); await review.browser.close() }
