import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { createReview } from './harness.mjs'

const data = new URL('../../../backend/certification-data/', import.meta.url)
const modules = JSON.parse(await readFile(new URL('panel-modules.json', data), 'utf8'))
const structure = JSON.parse(await readFile(new URL('course-structure.json', data), 'utf8'))
const validation = JSON.parse(await readFile(new URL('../../src/components/certification/__fixtures__/validation-repair-http.json', import.meta.url), 'utf8'))
const governance = JSON.parse(await readFile(new URL('../../src/components/certification/__fixtures__/governance-http.json', import.meta.url), 'utf8'))
const finding = governance.review.handoff.release.memo.run.source_finding
const scenarios = [
  { moduleId: 'validation_qa', property: 'validationAssessment', endpoint: 'validation-suites', listing: validation.listing, saved: validation.original,
    artifact: validation.original.input_snapshot.artifact, reference: validation.original.run_id },
  { moduleId: 'governance', property: 'governanceAssessment', endpoint: 'governance-work', listing: governance.listing, saved: finding,
    artifact: finding.run.input_snapshot.artifact, reference: finding.uuid },
]
for (const scenario of scenarios) Object.assign(modules.find(item => item.id === scenario.moduleId), { [scenario.property]: scenario.listing.case, assessment: null })
let active = scenarios[0]
const identity = () => ({ enrollment_id: active.listing.enrollment_id, course_version: active.listing.course_version, manifest_sha256: active.listing.manifest_sha256,
  course_title: 'Repair editor QA', module_ids: modules.map(item => item.id), modules_total: modules.length, maximum_xp: 2675 })
const course = () => ({ ...structure, ...identity(), versioned: true, prerequisites: Object.fromEntries(modules.map(item => [item.id, []])), modules })
const progress = () => ({ ...identity(), id: 'repair-editor', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, learning_position: null })
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5305', resetStorage: false,
  evidenceMode: 'Frozen frontend; saved validation and governance responses from disposable real HTTP with synthetic providers. Read-only repair editor handoff, preserved failed evidence and chat. No live models, learner writes or earned credit.' })
const { page, context } = review
const writes = [], popupCaptures = [], popupErrors = []
await context.route('**/api/**', async route => {
  const request = route.request(), url = new URL(request.url()), path = url.pathname
  if (request.method() !== 'GET' && request.method() !== 'HEAD') writes.push({ path, method: request.method() })
  const extraction = { uuid: active.artifact.uuid, title: active.artifact.title, set_type: 'extraction', user_id: 'reviewer', item_count: active.artifact.fields.length }
  if (path === '/api/auth/config') return route.fulfill({ json: { auth_methods: ['password'], oauth_providers: [] } })
  if (path === '/api/extractions/search-sets') return route.fulfill({ json: [extraction] })
  if (path.startsWith(`/api/extractions/search-sets/${extraction.uuid}`)) {
    const suffix = path.slice(`/api/extractions/search-sets/${extraction.uuid}`.length)
    const value = suffix === '' ? { ...extraction, id: extraction.uuid, extraction_config: {}, created_at: '', updated_at: '' }
      : suffix === '/items' ? active.artifact.fields.map(field => ({ ...field, uuid: field.id, search_set_uuid: extraction.uuid, searchtype: 'text' }))
        : suffix === '/quality-status' ? { status: 'unvalidated' } : suffix === '/quality-sparkline' ? { scores: [] }
          : suffix === '/cross-field-rules' ? { rules: [] } : ['/history', '/quality-history'].includes(suffix) ? { runs: [] } : null
    if (value !== null) return route.fulfill({ json: value })
  }
  if (path === '/api/extractions/test-cases') return route.fulfill({ json: [] })
  if (path.startsWith('/api/certification/')) {
    assert.equal(request.method(), 'GET')
    if (path.endsWith('/progress')) return route.fulfill({ json: progress() })
    if (path.endsWith('/course')) return route.fulfill({ json: course() })
    if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
    if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
    if (path.endsWith('/practical-runs')) return route.fulfill({ json: { runs: [], older_runs_available: false } })
    if (path.endsWith(`/modules/${active.moduleId}/${active.endpoint}`)) return route.fulfill({ json: active.listing })
    if (path.endsWith(`/validation-runs/${active.reference}`) || path.endsWith(`/governance/finding/${active.reference}`)) return route.fulfill({ json: active.saved })
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
  const violations = await popup.evaluate(async () => (await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } })).violations.map(item => ({ id: item.id, nodes: item.nodes.map(node => node.target) })))
  await writeFile(`${review.out}/${id}.axe.json`, JSON.stringify(violations, null, 2))
  assert.deepEqual(violations, [])
  await popup.screenshot({ path: `${review.out}/${id}.png` })
  await writeFile(`${review.out}/${id}.txt`, await popup.locator('body').ariaSnapshot())
  const bounds = await popup.evaluate(() => ({ width: innerWidth, pageWidth: document.documentElement.scrollWidth }))
  assert.equal(bounds.width, bounds.pageWidth)
  popupCaptures.push({ id, url: popup.url(), ...bounds })
  console.log(id)
}
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1800 : 1100 })
    for (const scenario of scenarios) {
      active = scenario
      const { moduleId } = scenario, kind = 'extraction'
      const savedEvidence = JSON.stringify(active.saved)
      await page.goto(review.baseURL + '/?mode=chat&tab=assistant')
      if (native) await review.setBrowserZoom(2)
      const draft = page.getByRole('textbox', { name: 'Message input', exact: true })
      await draft.fill('Keep my unsent course question while I inspect the selected editor.')
      const originalDraft = await draft.elementHandle()
      await page.evaluate(() => { window.courseEditorSentinel = 'original-course-tab' })
      const opener = page.getByRole('button', { name: 'Open learning panel', exact: true })
      if (!await opener.isVisible()) await page.getByRole('button', { name: 'Open activity', exact: true }).click()
      await opener.click()
      const panel = page.locator('[data-cert-panel]')
      await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
      const module = modules.find(item => item.id === moduleId)
      await panel.getByRole('button', { name: new RegExp(`^${module.number} ${module.title}`) }).click()
      await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
      const artifactId = active.artifact.uuid
      if (moduleId === 'validation_qa') {
        await panel.getByRole('button', { name: 'Open original run 1: completed', exact: true }).click()
        await panel.getByRole('button', { name: 'Use this original failure for repair', exact: true }).click()
        assert.equal(await panel.getByRole('combobox', { name: 'Owned extraction', exact: true }).isDisabled(), true)
      } else {
        await panel.getByRole('combobox', { name: 'Saved capstone record type', exact: true }).selectOption('finding')
        await panel.getByRole('textbox', { name: 'Saved capstone reference', exact: true }).fill(active.reference)
        await panel.getByRole('button', { name: 'Open saved capstone reference', exact: true }).click()
        await panel.getByRole('heading', { name: 'Repair the same extraction, then capture it', exact: true }).waitFor()
      }
      const selection = moduleId === 'validation_qa' ? panel.getByRole('combobox', { name: 'Owned extraction', exact: true })
        : panel.getByRole('textbox', { name: 'Saved capstone reference', exact: true })
      const expectedSelection = moduleId === 'validation_qa' ? artifactId : active.reference
      const link = panel.getByRole('link', { name: `Open selected ${kind} in a new tab`, exact: true })
      await link.scrollIntoViewIfNeeded(); await link.focus()
      await capture(`${moduleId}-editor-link-${width}`)
      const [popup] = await Promise.all([page.waitForEvent('popup'), link.click()])
      popup.on('pageerror', error => popupErrors.push(String(error)))
      await popup.setViewportSize({ width, height: native ? 1800 : 1100 })
      await popup.waitForLoadState('domcontentloaded')
      if (native) assert.deepEqual(await popup.evaluate(() => ({ dpr: devicePixelRatio, width: innerWidth })), { dpr: 2, width: width / 2 })
      assert.equal(new URL(popup.url()).searchParams.get(kind), artifactId)
      assert.equal(await popup.evaluate(() => window.opener), null)
      const input = popup.getByRole('textbox', { name: kind === 'extraction' ? 'Add term to extract' : 'Text to process', exact: true })
      if (width < 1024) {
        const library = popup.getByRole('button', { name: 'Open Library panel', exact: true })
        if (await library.isVisible()) await library.click()
      }
      await input.fill('Unsent editor note; do not run or save automatically.')
      await input.scrollIntoViewIfNeeded()
      await capturePopup(popup, `${moduleId}-exact-editor-${width}`)
      // The local QA input is deliberately unsent; clear it before choosing the explicit close action.
      await input.fill('')
      const returnAction = popup.getByRole('button', { name: 'Close editor tab and return to course', exact: true })
      await returnAction.scrollIntoViewIfNeeded(); await returnAction.focus()
      await capturePopup(popup, `${moduleId}-return-action-${width}`)
      await Promise.all([popup.waitForEvent('close'), returnAction.click()])
      assert.equal(await page.evaluate(() => window.courseEditorSentinel), 'original-course-tab')
      assert.equal(await page.evaluate(() => document.hasFocus()), true)
      await page.waitForFunction(element => document.activeElement === element, await link.elementHandle(), { timeout: 5000 })
      assert.equal(await originalDraft.evaluate(element => element.isConnected && element.value.startsWith('Keep my unsent')), true)
      assert.equal(await selection.inputValue(), expectedSelection)
      assert.equal(JSON.stringify(active.saved), savedEvidence)
      await capture(`${moduleId}-course-retained-${width}`)
    }
  }
  assert.deepEqual(writes, [])
  assert.deepEqual(popupErrors, [])
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  review.observations.push({ popupCaptures, closedEditorTabViaCourseAction: true, originalCourseAndChatRetained: true, artifactIdsVerified: true, originalFailedEvidenceRetained: true, courseWrites: 0, editorWrites: 0, modelRequests: 0 })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
