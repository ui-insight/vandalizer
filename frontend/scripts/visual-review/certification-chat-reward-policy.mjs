import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const real = JSON.parse(await readFile(new URL('../../src/components/certification/__fixtures__/chat-tool-contract.json', import.meta.url), 'utf8'))
const module = real.find(item => item.tool_name === 'get_certification_module').content
const identity = { enrollment_id: 'synthetic-outcomes', course_title: 'Synthetic outcome course', course_version: 'qa-outcomes', manifest_sha256: 'a'.repeat(64), maximum_stars: 1, credit_basis: 'required_outcomes' }
const completion = { module_id: 'foundations', title: 'Foundations', stars: 1, xp_earned: 100, total_xp: 100, level: 'apprentice', level_up: false, certified: false }
const cases = [
  { id: 'outcome-progress', tool: 'get_certification_progress', content: { ...identity, total_xp: 100, level: 'apprentice', certified: false, modules_completed: 1, modules_total: 2, next_module_id: 'process_mapping', modules: [
    { module_id: 'foundations', title: 'Foundations', xp: 100, completed: true, stars: 1 },
    { module_id: 'process_mapping', title: 'Thinking in Workflows', xp: 100, completed: false, stars: 0 },
  ] } },
  { id: 'outcome-module', tool: 'get_certification_module', content: { ...module, ...identity, completed: true, stars: 1, star_criteria: { 1: 'All required saved outcomes must pass.' }, assessment_keys: [], assessment_questions: [], assessment_mode: 'selected_saved_outcomes', required_outcomes: [{ outcome_id: `${module.module_id}.review`, statement: 'Review saved evidence', method: 'structured_review' }], selected_outcome_completion: true } },
  { id: 'outcome-check', tool: 'check_certification_module', content: { ...identity, module_id: 'foundations', title: 'Foundations', passed: false, stars: 0, checks: [{ name: 'Selected saved evidence', passed: false, detail: 'Open the module assessment to select your saved work.' }] } },
  { id: 'outcome-completion', tool: 'complete_certification_module', content: { ...completion, ...identity } },
  { id: 'legacy-recorded-scale', tool: 'complete_certification_module', stars: '2 of 3 stars', content: { ...completion, ...identity, course_title: 'Synthetic original course', maximum_stars: 3, credit_basis: 'legacy_rubric', stars: 2 } },
  { id: 'historical-unspecified-scale', tool: 'complete_certification_module', stars: '2 stars recorded', content: { ...completion, enrollment_id: identity.enrollment_id, course_title: 'Synthetic historical course', course_version: 'qa-old', manifest_sha256: identity.manifest_sha256, stars: 2 } },
  { id: 'contradictory-outcome-scale', tool: 'complete_certification_module', invalid: true, content: { ...completion, ...identity, maximum_stars: 3 } },
  { id: 'excess-recorded-stars', tool: 'complete_certification_module', invalid: true, content: { ...completion, ...identity, stars: 3 } },
]
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Actual production chat cards with synthetic pinned reward-policy payloads. Synthetic completion cards inspect display only, not an available agent completion path. No model, persisted assessment, XP or certificate issuance.' })
const { page, context, state } = review
const reads = []
await context.route('**/api/certification/**', route => {
  assert.equal(route.request().method(), 'GET')
  reads.push(new URL(route.request().url()).pathname)
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
      const id = `reward-policy-${++sequence}`
      state.chatChunks = [{ kind: 'tool_call', tool_name: item.tool, tool_call_id: id, args: {} }, { kind: 'tool_result', tool_name: item.tool, tool_call_id: id, content: item.content }, { kind: 'text', content: id }]
      await page.getByRole('textbox', { name: 'Message input', exact: true }).fill('Show this saved certification result.')
      await page.getByRole('button', { name: 'Send message', exact: true }).click()
      await page.getByText(id, { exact: true }).waitFor()
      const result = page.locator('.agent-tool-result').last()
      if (item.invalid) {
        assert.equal(await result.locator('.cert-chat-card').count(), 0)
        assert.ok((await result.getByRole('status').innerText()).endsWith('Result needs review'))
      } else {
        assert.equal(await result.locator('.cert-chat-card').count(), 1)
        if (item.stars) assert.equal(await result.getByRole('img', { name: item.stars, exact: true }).count(), 1)
        else assert.equal(await result.getByRole('img', { name: /stars/ }).count(), 0)
      }
      await result.scrollIntoViewIfNeeded()
      const capture = `${item.id}-${width}`
      await review.capture(capture)
      assert.deepEqual(JSON.parse(await readFile(`${review.out}/${capture}.axe.json`, 'utf8')), [])
      assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
      console.log(capture)
    }
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ cases: cases.length, certificationReads: reads.length, certificationWrites: 0, actualModelCalls: 0, gradingVerified: false })
} catch (error) { await review.capture('blocked', String(error)); throw error } finally { await review.flush(); await review.browser.close() }
