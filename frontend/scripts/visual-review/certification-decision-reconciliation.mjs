import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
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
const runState = 'prepared', empty = false
let loseResponse = true, mode = 'found', locked = false
const receipts = new Map(), submissions = []
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5305', resetStorage: false })
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
    if (mode === 'failed') return route.fulfill({ status: 422, json: { detail: 'Synthetic rejected read, not a rejected submission' } })
    const record = receipts.get(path.split('/').at(-1))
    return route.fulfill({ status: record ? 200 : 404, json: record || { detail: 'Not found' } })
  }
  if (path.includes('/decisions/')) {
    const promptId = path.split('/decisions/')[1].split('/')[0]
    const prompt = prompts.find(item => item.id === promptId)
    if (path.includes('/runs/')) {
      const latest = [...receipts.values()].filter(item => item.prompt_id === promptId).at(-1) || null
      return route.fulfill({ json: { enrollment_id: identity.enrollment_id, module_id: module.id, prompt,
        run_id: runId, run_state: runState, can_submit: !locked && runState === (prompt.phase === 'before_execution' ? 'prepared' : 'completed'),
        read_only_reason: locked ? 'This run has already left preparation.' : null,
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
    if (loseResponse) { loseResponse = false; if (mode === 'missing') receipts.delete(record.uuid); return route.fulfill({ status: 503, json: { detail: 'Synthetic lost response after saving' } }) }
    return route.fulfill({ json: record })
  }
  return route.fallback()
})
async function enter() {
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await page.getByRole('button', { name: /^1 Foundations/ }).click()
  const challenge = page.getByRole('button', { name: 'Challenge', exact: true })
  if (process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2') { await challenge.focus(); await challenge.press('Enter') } else await challenge.click()
  await page.getByRole('heading', { name: 'Review your saved work', exact: true }).waitFor()
}
const panel = page.getByRole('region', { name: 'Practical review', exact: true })
async function capture(name) {
  await review.capture(name, 'Synthetic saved runs and HTTP receipts in the actual local production frontend. No real learner, model, execution or earned credit.')
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${name}.axe.json`, 'utf8')), [])
  console.log(name)
}
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
try {
  await page.goto(review.baseURL + '/certification')
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1700 : 1000 })
    const suffix = native ? 'native' : width
    for (mode of ['found', 'missing', 'failed']) {
      receipts.clear(); loseResponse = true; locked = false
      await page.evaluate(() => sessionStorage.clear())
      await page.goto(review.baseURL + '/certification')
      if (native) await review.setBrowserZoom(2)
      await enter()
      await panel.getByRole('combobox', { name: 'Saved run', exact: true }).selectOption(runId)
      await panel.getByLabel('This saved scope is ready to run', { exact: true }).check()
      await panel.getByRole('textbox', { name: 'Explain your decision', exact: true }).fill('I checked the saved source and fields against the assigned task.')
      await panel.getByRole('button', { name: 'Save my decision', exact: true }).click()
      await panel.getByRole('alert').waitFor()
      const count = submissions.length
      if (process.env.REVIEW_READONLY_RECOVERY === '1') {
        locked = true
        await panel.getByRole('button', { name: 'Reload saved runs', exact: true }).click()
        await panel.getByText('This run has already left preparation.', { exact: true }).waitFor()
        assert.ok(await panel.getByRole('button', { name: 'Check saved decision', exact: true }).isEnabled())
      }
      await panel.getByRole('button', { name: 'Check saved decision', exact: true }).click()
      if (mode === 'found') {
        await panel.getByRole('button', { name: 'Save my decision', exact: true }).waitFor()
        await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Saved practical decision')
        await panel.getByLabel('Saved practical decision', { exact: true }).scrollIntoViewIfNeeded()
      } else {
        await panel.getByRole('button', { name: 'Check saved decision', exact: true }).waitFor()
        await panel.getByRole('alert').scrollIntoViewIfNeeded()
        assert.equal(await panel.getByLabel('This saved scope is ready to run', { exact: true }).isDisabled(), true)
      }
      assert.equal(submissions.length, count, 'A read must never submit again')
      await capture(`${mode}-${suffix}`)
      if (locked) {
        assert.equal(await panel.getByRole('button', { name: 'Retry original decision', exact: true }).count(), 0)
        assert.equal(await panel.getByLabel('This saved scope is ready to run', { exact: true }).isDisabled(), true)
        assert.equal(submissions.length, count)
      } else if (mode === 'missing') {
        await panel.getByRole('button', { name: 'Retry original decision', exact: true }).click()
        await panel.getByRole('button', { name: 'Save my decision', exact: true }).waitFor()
        assert.equal(submissions.length, count + 1)
        assert.deepEqual(submissions.at(-1), submissions.at(-2))
      } else assert.equal(await panel.getByRole('button', { name: 'Retry original decision', exact: true }).count(), 0)
    }
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ states: ['found', 'missing', 'failed'], readOnlyChecks: true, originalBodyRetry: true, creditAwarded: 0 })
} catch (error) { await capture('blocked'); throw error } finally { await review.flush(); await review.browser.close() }
