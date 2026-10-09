import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { createReview } from './harness.mjs'

const session = JSON.parse(await readFile('/private/tmp/certification-editor-instruction-session.json', 'utf8'))
const { listing, original, field_id: fieldId } = session
const artifact = original.input_snapshot.artifact
const instruction = 'Extract the full multi-year project budget as a plain USD number; never an annual subtotal.'
const data = new URL('../../../backend/certification-data/', import.meta.url)
const modules = JSON.parse(await readFile(new URL('panel-modules.json', data), 'utf8'))
const structure = JSON.parse(await readFile(new URL('course-structure.json', data), 'utf8'))
Object.assign(modules.find(item => item.id === 'validation_qa'), { validationAssessment: listing.case, assessment: null })
const identity = { enrollment_id: listing.enrollment_id, course_version: listing.course_version, manifest_sha256: listing.manifest_sha256,
  course_title: 'Instruction repair QA', module_ids: modules.map(item => item.id), modules_total: modules.length, maximum_xp: 2675 }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5305', resetStorage: false,
  evidenceMode: 'Frozen frontend connected to real authenticated extraction GET/PATCH and certification capture APIs. Isolated MongoDB 27029; original failed run seeded with synthetic providers. No live models or earned credit.' })
const { page, context } = review
const writes = [], popupCaptures = [], popupErrors = [], recaptures = [], retests = []
let rejectNextSave = false
await context.route('**/api/**', async route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (!['GET', 'HEAD'].includes(request.method())) writes.push({ path, method: request.method(), body: request.postDataJSON() })
  if (path === `/api/extractions/items/${fieldId}` && rejectNextSave) {
    rejectNextSave = false
    return route.fulfill({ status: 503, json: { detail: 'Synthetic temporary save failure' } })
  }
  if (path === `/api/extractions/items/${fieldId}` || path === `/api/extractions/search-sets/${artifact.uuid}/items`
      || path.startsWith('/api/certification/modules/validation_qa/') || path.startsWith('/api/certification/validation-')) {
    const response = await route.fetch({ url: session.api_origin + new URL(request.url()).pathname + new URL(request.url()).search })
    assert.equal(response.status(), 200, await response.text())
    if (path.endsWith('/validation-captures') && request.method() === 'POST') recaptures.push(await response.json())
    if (path.endsWith('/modules/validation_qa/validation-runs') && request.method() === 'POST') retests.push(await response.json())
    return route.fulfill({ response })
  }
  const extraction = { uuid: artifact.uuid, title: artifact.title, set_type: 'extraction', user_id: 'reviewer', item_count: artifact.fields.length }
  if (path === '/api/auth/config') return route.fulfill({ json: { auth_methods: ['password'], oauth_providers: [] } })
  if (path === '/api/extractions/search-sets') return route.fulfill({ json: [extraction] })
  if (path.startsWith(`/api/extractions/search-sets/${artifact.uuid}`)) {
    const suffix = path.slice(`/api/extractions/search-sets/${artifact.uuid}`.length)
    const value = suffix === '' ? { ...extraction, id: artifact.uuid, extraction_config: {}, created_at: '', updated_at: '' }
      : suffix === '/quality-status' ? { status: 'unvalidated' } : suffix === '/quality-sparkline' ? { scores: [] }
      : suffix === '/cross-field-rules' ? { rules: [] } : ['/history', '/quality-history'].includes(suffix) ? { runs: [] } : null
    if (value !== null) return route.fulfill({ json: value })
  }
  if (path === '/api/extractions/test-cases') return route.fulfill({ json: [] })
  if (path.startsWith('/api/certification/')) {
    assert.equal(request.method(), 'GET')
    if (path.endsWith('/progress')) return route.fulfill({ json: { ...identity, id: 'repair-editor', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, learning_position: null } })
    if (path.endsWith('/course')) return route.fulfill({ json: { ...structure, ...identity, versioned: true, prerequisites: Object.fromEntries(modules.map(item => [item.id, []])), modules } })
    if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
    if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
    if (path.endsWith('/practical-runs')) return route.fulfill({ json: { runs: [], older_runs_available: false } })
  }
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
async function capture(id) {
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
async function capturePopup(popup, id) {
  await popup.addScriptTag({ path: createRequire(import.meta.url).resolve('axe-core/axe.min.js') })
  const violations = await popup.evaluate(async () => (await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } })).violations.map(item => ({ id: item.id, nodes: item.nodes.map(node => ({ target: node.target, summary: node.failureSummary })) })))
  await writeFile(`${review.out}/${id}.axe.json`, JSON.stringify(violations, null, 2))
  await popup.screenshot({ path: `${review.out}/${id}.png` })
  await writeFile(`${review.out}/${id}.txt`, await popup.locator('body').ariaSnapshot())
  assert.deepEqual(violations, [])
  const bounds = await popup.evaluate(() => ({ width: innerWidth, pageWidth: document.documentElement.scrollWidth }))
  assert.equal(bounds.width, bounds.pageWidth)
  popupCaptures.push({ id, url: popup.url(), ...bounds })
  console.log(id)
}
try {
  for (const width of native ? [780] : [320, 1440]) {
    assert.equal((await context.request.post(session.api_origin + '/qa/reset-instruction')).status(), 200)
    await page.setViewportSize({ width, height: native ? 1600 : 900 })
    await page.goto(review.baseURL + '/?mode=chat&tab=assistant')
    if (native) await review.setBrowserZoom(2)
    const draft = page.getByRole('textbox', { name: 'Message input', exact: true })
    await draft.fill('Keep my unsent question while I save a field instruction.')
    const originalDraft = await draft.elementHandle()
    const opener = page.getByRole('button', { name: 'Open learning panel', exact: true })
    if (!await opener.isVisible()) await page.getByRole('button', { name: 'Open activity', exact: true }).click()
    await opener.click()
    const panel = page.locator('[data-cert-panel]')
    await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    const module = modules.find(item => item.id === 'validation_qa')
    await panel.getByRole('button', { name: new RegExp(`^${module.number} ${module.title}`) }).click()
    await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
    await panel.getByRole('button', { name: /^Open original run \d+: completed$/ }).click()
    await panel.getByRole('button', { name: 'Use this original failure for repair', exact: true }).click()
    const link = panel.getByRole('link', { name: 'Open selected extraction in a new tab', exact: true })
    const [popup] = await Promise.all([page.waitForEvent('popup'), link.click()])
    popup.on('pageerror', error => popupErrors.push(String(error)))
    await popup.setViewportSize({ width, height: native ? 1600 : 900 })
    await popup.waitForLoadState('domcontentloaded')
    if (native) assert.deepEqual(await popup.evaluate(() => ({ dpr: devicePixelRatio, width: innerWidth })), { dpr: 2, width: width / 2 })
    if (width < 1024) {
      const library = popup.getByRole('button', { name: 'Open Library panel', exact: true })
      if (await library.isVisible()) await library.click()
    }
    await popup.getByRole('button', { name: 'Total Project Budget', exact: true }).click()
    const form = popup.getByRole('form', { name: 'Extraction instructions for Total Project Budget', exact: true })
    const textarea = form.getByRole('textbox', { name: 'Extraction instructions', exact: true })
    assert.equal(await textarea.inputValue(), session.wrong_instruction)
    await textarea.scrollIntoViewIfNeeded()
    await capturePopup(popup, `instruction-original-${width}`)
    await textarea.fill(instruction)
    await textarea.press('Tab')
    const writesBeforeSave = writes.length
    await popup.getByRole('textbox', { name: 'Allowed values', exact: true }).focus()
    await textarea.focus()
    await capturePopup(popup, `instruction-draft-${width}`)
    assert.equal(writes.length, writesBeforeSave)
    rejectNextSave = true
    await form.getByRole('button', { name: 'Save instructions', exact: true }).click()
    await form.getByRole('alert').waitFor({ timeout: 10000 })
    assert.equal(await textarea.inputValue(), instruction)
    await capturePopup(popup, `instruction-retry-${width}`)
    await form.getByRole('button', { name: 'Save instructions', exact: true }).click()
    await form.getByRole('status').waitFor()
    assert.equal(await form.getByRole('button', { name: 'Save instructions', exact: true }).isDisabled(), true)
    await capturePopup(popup, `instruction-saved-${width}`)
    const returnAction = popup.getByRole('button', { name: 'Close editor tab and return to course', exact: true })
    await Promise.all([popup.waitForEvent('close'), returnAction.click()])
    await page.waitForFunction(element => document.activeElement === element, await link.elementHandle(), { timeout: 5000 })
    assert.equal(await originalDraft.evaluate(element => element.isConnected && element.value.startsWith('Keep my unsent')), true)
    assert.equal(await panel.getByRole('combobox', { name: 'Owned extraction', exact: true }).inputValue(), artifact.uuid)
    await panel.getByRole('button', { name: 'Capture extraction and both sources', exact: true }).click()
    const prepare = panel.getByRole('button', { name: 'Prepare complete repaired retest', exact: true })
    await prepare.waitFor(); assert.equal(await prepare.isEnabled(), true)
    await prepare.scrollIntoViewIfNeeded()
    await capture(`repaired-capture-${width}`)
    const repaired = recaptures.at(-1)
    assert.equal(repaired.artifact_id, artifact.uuid)
    assert.notEqual(repaired.input_snapshot_sha256, original.input_snapshot.input_snapshot_sha256)
    assert.notEqual(repaired.artifact_sha256, original.input_snapshot.artifact_sha256)
    assert.deepEqual(repaired.artifact.fields.map(({ id, title, is_optional, enum_values }) => ({ id, title, is_optional, enum_values })), artifact.fields.map(({ id, title, is_optional, enum_values }) => ({ id, title, is_optional, enum_values })))
    assert.equal(repaired.artifact.fields.find(field => field.id === fieldId).searchphrase, instruction)
    await prepare.click()
    const scope = panel.getByRole('form', { name: 'Approve complete validation suite', exact: true })
    await scope.waitFor()
    await scope.getByRole('combobox', { name: 'Scope choice', exact: true }).scrollIntoViewIfNeeded()
    await capture(`linked-retest-${width}`)
    const retest = retests.at(-1)
    assert.equal(retest.phase, 'retest'); assert.equal(retest.state, 'prepared')
    assert.equal(retest.can_execute, false)
    assert.equal(retest.input_snapshot.uuid, repaired.uuid)
    assert.equal(retest.original_run.run_id, original.run_id)
    assert.equal(retest.original_run.run_sha256, original.run_sha256)
    assert.deepEqual(retest.suite, original.suite)
    const state = await (await context.request.get(session.api_origin + '/qa/state')).json()
    assert.equal(state.original_capture_unchanged, true)
    assert.equal(state.total_xp, 0); assert.equal(state.certified, false)
    assert.equal(state.provider_calls, session.initial_provider_calls); assert.equal(state.judge_calls, 0)
    const reread = await (await context.request.get(session.api_origin + `/api/certification/validation-runs/${original.run_id}?enrollment_id=${listing.enrollment_id}`)).json()
    assert.deepEqual(reread, original)
    review.observations.push({ width, repairedCapture: repaired, linkedRetest: retest, state, originalRunUnchanged: true, originalChatNodeRetained: true })
  }
  assert.equal(writes.length, (native ? 1 : 2) * 4)
  for (const write of writes.filter(item => item.method === 'PATCH')) assert.deepEqual(write.body, { searchphrase: instruction })
  assert.deepEqual(popupErrors, []); assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ popupCaptures, writes, expectedSyntheticSaveFailures: native ? 1 : 2 })
} catch (error) {
  review.observations.push({ diagnosticWrites: writes })
  for (const popup of context.pages().filter(item => item !== page && !item.isClosed())) {
    await popup.screenshot({ path: `${review.out}/blocked-editor.png` })
    await writeFile(`${review.out}/blocked-editor.txt`, await popup.locator('body').ariaSnapshot())
    await writeFile(`${review.out}/blocked-editor-inputs.json`, JSON.stringify(await popup.locator('form').evaluateAll(forms => forms.map(form => ({ name: form.getAttribute('aria-label'), html: form.outerHTML }))), null, 2))
  }
  await review.capture('blocked', String(error)); throw error
}
finally { await review.flush(); await review.browser.close() }
