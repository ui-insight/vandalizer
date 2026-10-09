import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const root = new URL('../../../backend/certification-data/courses/legacy-2026-10-02.1/', import.meta.url)
const [manifest, modules, structure, exercises] = await Promise.all(['manifest.json', 'panel-modules.json', 'course-structure.json', 'exercises.json'].map(async file => JSON.parse(await readFile(new URL(file, root), 'utf8'))))
const module = modules.find(module => module.id === 'extraction_engine')
const identity = { versioned: true, enrollment_id: 'qa-check-roles', course_version: manifest.release_id, course_title: manifest.title, manifest_sha256: 'a'.repeat(64), maximum_stars: 3, credit_basis: 'legacy_rubric', modules_total: 1, module_ids: [module.id], maximum_xp: 225 }
const course = { ...structure, ...identity, modules: [module], prerequisites: { [module.id]: [] }, tiers: structure.tiers.map(tier => ({ ...tier, moduleIds: tier.moduleIds.filter(id => id === module.id) })).filter(tier => tier.moduleIds.length) }
const progress = { ...identity, id: 'qa-progress', user_id: 'reviewer', modules: { extraction_engine: { completed: false, stars: 0, attempts: 0, provisioned_docs: ['qa-original-document'] } }, total_xp: 0, level: 'novice', certified: false, certified_at: null, learning_position: null, position_revision: 0, unlocked: false }
const cases = [
  { id: 'passed-advice', passed: true, advisory: true },
  { id: 'failed-required', passed: false, advisory: true },
  { id: 'all-passed', passed: true, advisory: false },
]
let current = cases[0]
function result() {
  return { ...identity, module_id: module.id, title: module.title, passed: current.passed, stars: current.passed ? 1 : 0, checks: [
    { name: '15+ extraction fields', role: 'required', passed: current.passed, detail: `You have ${current.passed ? 15 : 14} unique fields across your extraction tasks (need 15+)` },
    ...(current.advisory ? [{ name: 'Missing expected fields', role: 'advisory', passed: false, detail: 'Consider adding: PI Name, Institution, Total Budget, Grant Number, Specific Aims' }] : []),
  ] }
}
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Synthetic required/advisory API responses exercise production chat and panel rendering. Validation is intercepted; no grading, completion or provider call occurs.' })
const { page, context, state } = review
page.setDefaultTimeout(30000)
const requests = []
await context.route('**/api/certification/**', route => {
  const request = route.request(), path = new URL(request.url()).pathname
  requests.push({ method: request.method(), path })
  if (path.endsWith('/validate')) { assert.equal(request.method(), 'POST'); return route.fulfill({ json: result() }) }
  assert.equal(request.method(), 'GET')
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { ...exercises[module.id], ...identity } })
  if (path.endsWith('/selection-status')) return route.fulfill({ json: { read_only: true, current_enrollment_id: identity.enrollment_id, pending: null } })
  return route.fallback()
})
async function check(target, panel) {
  const text = await target.innerText()
  assert.ok(text.includes(current.passed ? current.advisory ? 'Module requirements met' : 'All checks passed' : panel ? 'Some objectives remaining' : 'Not there yet'))
  assert.ok(text.includes(current.passed ? 'Required: Met' : 'Required: Not met'))
  if (current.advisory) { assert.ok(text.includes('Advisory: Suggestion')); assert.ok(!text.includes('All checks passed')) }
  if (current.passed && current.advisory) assert.ok(text.includes('Advisory suggestions do not block completion.'))
}
async function capture(id, target) {
  await target.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1700 : 1000 })
    for (current of cases) {
      await page.goto(review.baseURL)
      if (native) await review.setBrowserZoom(2)
      const id = `roles-${current.id}-${width}`
      state.chatChunks = [{ kind: 'tool_call', tool_name: 'check_certification_module', tool_call_id: id, args: {} }, { kind: 'tool_result', tool_name: 'check_certification_module', tool_call_id: id, content: result() }, { kind: 'text', content: id }]
      await page.getByRole('textbox', { name: 'Message input', exact: true }).fill('Show my saved certification checks.')
      await page.getByRole('button', { name: 'Send message', exact: true }).click()
      await page.getByText(id, { exact: true }).waitFor()
      const card = page.locator('.agent-tool-result').last().locator('.cert-chat-card')
      await check(card, false)
      assert.equal(await card.getByRole('button', { name: 'Complete the module', exact: true }).count(), current.passed ? 1 : 0)
      await capture(`${current.id}-chat-${native ? 'native' : width}`, card)
      await page.goto(review.baseURL + '/certification')
      const panel = page.locator('[data-cert-panel="true"]')
      await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
      await panel.getByRole('button', { name: /^4 Extraction Engine/ }).click()
      await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
      await panel.getByRole('button', { name: 'Check Progress', exact: true }).click()
      const validation = panel.locator('section').filter({ has: page.getByRole('button', { name: 'Dismiss results', exact: true }) })
      await validation.waitFor()
      await check(validation, true)
      await validation.getByRole('button', { name: 'Dismiss results', exact: true }).click({ trial: true })
      const dismissBounds = await validation.getByRole('button', { name: 'Dismiss results', exact: true }).boundingBox()
      if (dismissBounds.width < 44 || dismissBounds.height < 44) console.log(await validation.getByRole('button', { name: 'Dismiss results', exact: true }).evaluate(el => ({ classes: el.className, minHeight: getComputedStyle(el).minHeight, minWidth: getComputedStyle(el).minWidth, spacing: getComputedStyle(el).getPropertyValue('--spacing') })))
      assert.ok(dismissBounds.width >= 44 && dismissBounds.height >= 44, JSON.stringify(dismissBounds))
      await capture(`${current.id}-panel-${native ? 'native' : width}`, validation)
      await validation.getByRole('button', { name: 'Dismiss results', exact: true }).click()
      assert.equal(await validation.count(), 0)
    }
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ cases, requests, allValidationIntercepted: true, completionCalls: 0 })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
