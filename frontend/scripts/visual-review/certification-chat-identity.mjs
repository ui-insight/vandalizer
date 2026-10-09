import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const root = new URL('../../../backend/certification-data/courses/legacy-2026-10-02.1/', import.meta.url)
const modules = JSON.parse(await readFile(new URL('panel-modules.json', root), 'utf8'))
const structure = JSON.parse(await readFile(new URL('course-structure.json', root), 'utf8'))
const identity = { enrollment_id: 'qa-selected', course_title: 'Synthetic continuation course', course_version: 'qa-original', manifest_sha256: 'a'.repeat(64) }
const course = { ...identity, ...structure, versioned: true, modules, prerequisites: Object.fromEntries(modules.map(module => [module.id, []])), selected_outcome_completion: false }
const progress = { ...identity, user_id: 'reviewer', total_xp: 0, level: 'novice', certified: false, modules: {}, module_ids: modules.map(module => module.id), modules_total: modules.length, modules_completed: 0 }
const checked = { ...identity, module_id: 'foundations', title: 'Foundations', passed: true, stars: 2, maximum_stars: 3, credit_basis: 'legacy_rubric', checks: [{ name: 'Original required check', passed: true, detail: 'Synthetic saved result for action-binding inspection.' }] }
const listed = { ...identity, total_xp: 0, level: 'novice', certified: false, modules_completed: 0, modules_total: 1, next_module_id: 'foundations', modules: [{ module_id: 'foundations', title: 'Foundations', completed: false, stars: 0, xp: 100 }] }
const cases = []
for (const [name, changed] of Object.entries({ current: {}, 'wrong-version': { course_version: 'earlier' }, 'wrong-manifest': { manifest_sha256: 'b'.repeat(64) }, 'wrong-enrollment': { enrollment_id: 'previous' } })) {
  cases.push({ name: `${name}-check`, tool: 'check_certification_module', content: { ...checked, ...changed }, action: 'Complete the module', enabled: name === 'current' })
  cases.push({ name: `${name}-progress`, tool: 'get_certification_progress', content: { ...listed, ...changed }, action: 'Start with Foundations', enabled: name === 'current' })
}
cases.push({ name: 'removed-module', tool: 'check_certification_module', content: { ...checked, module_id: 'removed' }, action: 'Complete the module', enabled: false })
cases.push({ name: 'original-completion', tool: 'complete_certification_module', content: { ...identity, enrollment_id: 'previous', module_id: 'foundations', title: 'Foundations', stars: 2, xp_earned: 100, total_xp: 100, level: 'apprentice', level_up: false, certified: false }, completion: true })

const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Actual production frontend with frozen original course content and synthetic enrollment/receipts. Tests exact card-to-selection binding only. No actual course choice, assessment, model call or earned credit.' })
const { page, context, state } = review
let requests = 0
await context.route('**/api/certification/**', route => {
  assert.equal(route.request().method(), 'GET'); requests++
  const path = new URL(route.request().url()).pathname
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
let sequence = 0
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1200 : 900 })
    for (const item of cases) {
      await page.goto(review.baseURL, { waitUntil: 'domcontentloaded' })
      if (native) await review.setBrowserZoom(2)
      const id = `identity-${++sequence}`
      state.chatChunks = [{ kind: 'tool_call', tool_name: item.tool, tool_call_id: id, args: {} }, { kind: 'tool_result', tool_name: item.tool, tool_call_id: id, content: item.content }, { kind: 'text', content: id }]
      await page.getByRole('textbox', { name: 'Message input', exact: true }).fill('Show this recorded course result.')
      await page.getByRole('button', { name: 'Send message', exact: true }).click()
      await page.getByText(id, { exact: true }).waitFor()
      const result = page.locator('.agent-tool-result').last()
      assert.equal(await result.locator('.cert-chat-card').count(), 1)
      if (item.completion) {
        await result.getByText('Course version: qa-original', { exact: true }).waitFor()
        assert.equal(await result.getByRole('button', { name: "What's next?", exact: true }).count(), 0)
        assert.ok(await result.getByRole('button', { name: 'Open current course', exact: true }).isEnabled())
      } else {
        // Waiting for selected metadata avoids treating initial loading as a match.
        const action = result.getByRole('button', { name: item.action, exact: true })
        if (item.enabled) await action.waitFor({ state: 'visible' })
        assert.equal(await action.isEnabled(), item.enabled)
        if (!item.enabled) assert.equal(await result.getByRole('button', { name: 'Refresh progress', exact: true }).count(), 1)
      }
      await result.scrollIntoViewIfNeeded()
      const capture = `${item.name}-${width}`
      await review.capture(capture)
      assert.deepEqual(JSON.parse(await readFile(`${review.out}/${capture}.axe.json`, 'utf8')), [])
      assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
      console.log(capture)
    }
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ identityCases: cases.length, certificationReads: requests, certificationWrites: 0, actualModelCalls: 0, originalContentPreserved: true })
} catch (error) { await review.capture('blocked', String(error)); throw error } finally { await review.flush(); await review.browser.close() }
