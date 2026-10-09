import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { createHash } from 'node:crypto'
import { createReview } from './harness.mjs'
import { workflow } from './fixtures.mjs'

const data = new URL('../../../backend/certification-data/', import.meta.url)
const read = async name => JSON.parse(await readFile(new URL(name, data), 'utf8'))
const modules = await read('panel-modules.json'), structure = await read('course-structure.json')
const prompts = (await read('drafts/v5.0/foundations-decisions.json')).map((prompt, i) => ({ ...prompt, prompt_sha256: String(i + 1).repeat(64) }))
Object.assign(modules.find(item => item.id === 'foundations'), { decisionPrompts: prompts, practicalPreparation: true, assessment: null })
const rawCase = await readFile(new URL('drafts/v5.0/workflow-design-case.json', data))
const definition = { ...JSON.parse(rawCase), case_sha256: createHash('sha256').update(rawCase).digest('hex') }
Object.assign(modules.find(item => item.id === 'workflow_design'), { workflowDesignAssessment: definition, assessment: null })
const extraCases = [
  ['multi_step', 'multi-step', 'connectedWorkflowAssessment', 'connected-workflows', 'workflow', 'Saved workflow'],
  ['advanced_nodes', 'advanced-nodes', 'budgetWorkflowAssessment', 'budget-workflows', 'workflow', 'Owned budget workflow'],
  ['output_delivery', 'output-delivery', 'outputWorkflowAssessment', 'output-workflows', 'workflow', 'Owned output workflow'],
  ['validation_qa', 'validation-qa', 'validationAssessment', 'validation-suites', 'extraction', 'Owned extraction'],
  ['batch_processing', 'batch-processing', 'batchAssessment', 'batch-work', 'extraction', 'Owned extraction'],
  ['governance', 'governance-capstone', 'governanceAssessment', 'governance-work', 'extraction', 'Owned capstone extraction'],
]
for (const entry of extraCases) {
  const raw = await readFile(new URL(`drafts/v5.0/${entry[1]}-case.json`, data))
  entry.push({ ...JSON.parse(raw), case_sha256: createHash('sha256').update(raw).digest('hex') })
  Object.assign(modules.find(item => item.id === entry[0]), { [entry[2]]: entry[6], assessment: null })
}
const scenarios = process.env.REVIEW_REMAINING_EDITORS === '1' ? extraCases.map(([moduleId, , , , kind, label]) => ({ moduleId, kind, label }))
  : [{ moduleId: 'foundations', kind: 'extraction', label: 'My extraction' }, { moduleId: 'workflow_design', kind: 'workflow', label: 'Saved workflow' }]
const identity = { enrollment_id: 'editor-link-course', course_version: 'editor-link-fixture', manifest_sha256: 'a'.repeat(64), course_title: 'Editor link QA', module_ids: modules.map(item => item.id), modules_total: modules.length, maximum_xp: 2675 }
const course = { ...structure, ...identity, versioned: true, prerequisites: Object.fromEntries(modules.map(item => [item.id, []])), modules }
const progress = { ...identity, id: 'editor-links', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, learning_position: null }
const extraction = { uuid: 'e'.repeat(32), title: 'My exact proposal fields', set_type: 'extraction', user_id: 'reviewer', item_count: 1 }
const workflowId = 'c'.repeat(24)
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5305', resetStorage: false,
  evidenceMode: 'Frozen frontend and authored draft cases. Synthetic owned artifact choices and editor reads. Exact new-tab destinations, original course/chat preservation; no capture, grading, model execution or live learner change.' })
const { page, context } = review
const writes = [], popupCaptures = [], popupErrors = []
await context.route('**/api/**', async route => {
  const request = route.request(), url = new URL(request.url()), path = url.pathname
  if (request.method() !== 'GET' && request.method() !== 'HEAD') writes.push({ path, method: request.method() })
  if (path === '/api/auth/config') return route.fulfill({ json: { auth_methods: ['password'], oauth_providers: [] } })
  if (path === '/api/extractions/search-sets') return route.fulfill({ json: [extraction] })
  if (path.startsWith(`/api/extractions/search-sets/${extraction.uuid}`)) {
    const suffix = path.slice(`/api/extractions/search-sets/${extraction.uuid}`.length)
    const value = suffix === '' ? { ...extraction, id: extraction.uuid, extraction_config: {}, created_at: '', updated_at: '' }
      : suffix === '/items' ? [{ id: 'field-1', uuid: 'field-1', search_set_uuid: extraction.uuid, searchphrase: 'PI name', title: 'PI name', searchtype: 'text', enum_values: [], is_optional: false }]
        : suffix === '/quality-status' ? { status: 'unvalidated' } : suffix === '/quality-sparkline' ? { scores: [] }
          : suffix === '/cross-field-rules' ? { rules: [] } : ['/history', '/quality-history'].includes(suffix) ? { runs: [] } : null
    if (value !== null) return route.fulfill({ json: value })
  }
  if (path === '/api/extractions/test-cases') return route.fulfill({ json: [] })
  if (path === `/api/workflows/${workflowId}`) return route.fulfill({ json: { ...workflow, id: workflowId, uuid: workflowId, name: 'My exact report design', input_config: { trigger_type: 'text_input' } } })
  if (path === `/api/workflows/${workflowId}/quality-status`) return route.fulfill({ json: {} })
  if (path === `/api/workflows/${workflowId}/history`) return route.fulfill({ json: { runs: [] } })
  if (path === `/api/workflows/${workflowId}/quality-sparkline`) return route.fulfill({ json: { scores: [] } })
  if (path.startsWith('/api/certification/')) {
    assert.equal(request.method(), 'GET')
    if (path.endsWith('/progress')) return route.fulfill({ json: progress })
    if (path.endsWith('/course')) return route.fulfill({ json: course })
    if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
    if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
    if (path.endsWith('/practical-runs')) return route.fulfill({ json: { runs: [], older_runs_available: false } })
    const entry = extraCases.find(([moduleId, , , endpoint]) => path.endsWith(`/modules/${moduleId}/${endpoint}`))
    if (entry) {
      const caseDefinition = entry[6]
      return route.fulfill({ json: {
        ...identity, module_id: entry[0], case: caseDefinition, can_submit: true, read_only_reason: null,
        workflows: [{ workflow_id: workflowId, name: 'My exact report design', version: 1 }], older_workflows_available: false,
        extractions: [{ artifact_id: extraction.uuid, title: extraction.title }], older_extractions_available: false,
        assigned_sources: [], captures: [], older_captures_available: false, runs: [], older_runs_available: false,
        submissions: [], older_submissions_available: false, suites: [], older_suites_available: false,
        inspections: [], older_inspections_available: false, handoffs: [], older_handoffs_available: false,
        calculations: [], older_calculations_available: false,
        calculation_fields: (caseDefinition.calculations || []).map(check => ({ id: check.id, unit: check.unit, operation: check.operation,
          inputs: check.inputs.map(id => { const amount = caseDefinition.amounts.find(item => item.id === id); return { id, label: amount.label, source_page: amount.anchor.page } }) })),
        records: Object.fromEntries(['capture', 'run', 'correction', 'scope', 'finding', 'memo', 'release', 'handoff', 'review'].map(kind => [kind, { items: [], older_available: false }])),
      } })
    }
    if (path.endsWith('/workflow_design/designs')) return route.fulfill({ json: {
      ...identity, module_id: 'workflow_design', case: definition, can_submit: true, read_only_reason: null,
      submissions: [], older_submissions_available: false, workflows: [{ workflow_id: workflowId, name: 'My exact report design', version: 1 }],
      older_workflows_available: false, process_choices: [], older_process_choices_available: false,
    } })
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
    for (const { moduleId, kind, label } of scenarios) {
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
      if (moduleId === 'foundations') await panel.getByRole('button', { name: 'Choose my extraction', exact: true }).click()
      const selection = panel.getByRole('combobox', { name: label, exact: true })
      const artifactId = kind === 'extraction' ? extraction.uuid : workflowId
      assert.equal(await panel.getByRole('link', { name: `Open selected ${kind} in a new tab`, exact: true }).count(), 0)
      await selection.selectOption(artifactId)
      const link = panel.getByRole('link', { name: `Open selected ${kind} in a new tab`, exact: true })
      await link.scrollIntoViewIfNeeded(); await link.focus()
      if (process.env.REVIEW_FOCUS_TRACE === '1') {
        console.log('before-popup-focus', await link.evaluate(element => ({ target: document.activeElement === element, tag: document.activeElement?.tagName, text: document.activeElement?.textContent?.slice(0, 80) })))
        await page.evaluate(() => {
          window.editorFocusTrace = []
          for (const kind of ['focus', 'blur', 'focusin', 'focusout']) window.addEventListener(kind, event => window.editorFocusTrace.push({ kind, target: event.target?.tagName, active: document.activeElement?.tagName }), true)
        })
      }
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
      if (process.env.REVIEW_FOCUS_TRACE === '1') console.log('after-popup-focus', await link.evaluate(element => ({ target: document.activeElement === element, tag: document.activeElement?.tagName, text: document.activeElement?.textContent?.slice(0, 80), trace: window.editorFocusTrace })))
      await page.waitForFunction(element => document.activeElement === element, await link.elementHandle(), { timeout: 5000 })
      assert.equal(await originalDraft.evaluate(element => element.isConnected && element.value.startsWith('Keep my unsent')), true)
      assert.equal(await selection.inputValue(), artifactId)
      await capture(`${moduleId}-course-retained-${width}`)
    }
  }
  assert.deepEqual(writes, [])
  assert.deepEqual(popupErrors, [])
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  review.observations.push({ popupCaptures, closedEditorTabViaCourseAction: true, originalCourseAndChatRetained: true, artifactIdsVerified: true, courseWrites: 0, editorWrites: 0, modelRequests: 0 })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
