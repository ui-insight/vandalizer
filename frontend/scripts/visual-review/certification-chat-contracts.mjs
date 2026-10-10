import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const real = JSON.parse(await readFile(new URL('../../src/components/certification/__fixtures__/chat-tool-contract.json', import.meta.url), 'utf8'))
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Actual production frontend with exported real teaching payloads and synthetic malformed tool responses. No model, grading, persisted course write or external message.' })
const { page, context, state } = review
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
const apiCalls = []
await context.route('**/api/certification/**', async route => { apiCalls.push({ method: route.request().method(), path: new URL(route.request().url()).pathname }); return route.fallback() })
const bad = [
  ['get_certification_progress', { modules: { wrong: 'shape' } }],
  ['get_certification_module', { module_id: 'foundations', title: 'Incomplete module' }],
  ['get_certification_lesson', { module_id: 'foundations', content: 'Incomplete lesson' }],
  ['check_certification_module', { module_id: 'foundations', passed: 'false', checks: {} }],
  ['complete_certification_module', { module_id: 'foundations', total_xp: 125, certified: 'false' }],
  ['provision_certification_lab', { module_id: 'foundations', provisioned_docs: 'wrong-shape' }],
  ['submit_certification_assessment', { module_id: 'foundations', stored: false }],
  ['complete_certification_module', { error: 'The certification response could not be confirmed.', code: 'certification_response_invalid', hint: 'Inspect saved state without repeating the write.' }],
]
const valid = [
  ...['get_certification_progress', 'get_certification_module', 'get_certification_lesson'].map(name => { const r = real.find(r => r.tool_name === name); return [name, r.content] }),
  ['check_certification_module', { module_id: 'foundations', title: 'Foundations', passed: true, stars: 1, checks: [{ name: 'Required run', passed: true, detail: 'Output saved' }, { name: 'Optional enrichment', passed: false, detail: 'Review the extra source context' }] }],
  ['complete_certification_module', { module_id: 'foundations', title: 'Foundations', stars: 1, xp_earned: 125, total_xp: 125, level: 'apprentice', level_up: true, certified: false }],
]
const structureOnly = process.env.REVIEW_CARD_STRUCTURE === '1'
let sequence = 0
async function send(tool, payload) {
  await page.goto(review.baseURL, { waitUntil: 'domcontentloaded' })
  const id = `contract-${++sequence}`
  state.chatChunks = [{ kind: 'tool_call', tool_name: tool, tool_call_id: id, args: {} }, { kind: 'tool_result', tool_name: tool, tool_call_id: id, content: payload }, { kind: 'text', content: id }]
  await page.getByRole('textbox', { name: 'Message input', exact: true }).fill('Show the saved certification response.')
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
  await page.getByText(id, { exact: true }).waitFor()
  return page.locator('.agent-tool-result').last()
}
async function capture(id, target) {
  await target.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
try {
  for (const width of native ? [780] : structureOnly ? [320, 1440] : [320, 390, 1440]) {
    await page.setViewportSize({ width, height: native ? 1000 : width < 500 ? 844 : 1000 })
    for (const [index, [tool, payload]] of (structureOnly ? [] : bad).entries()) {
      const result = await send(tool, payload)
      if (native) await review.setBrowserZoom(2)
      assert.ok((await result.getByRole('status').innerText()).endsWith('Result needs review'))
      assert.equal(await result.locator('.cert-chat-card').count(), 0)
      assert.equal(await result.getByRole('button', { name: 'Review recovery options', exact: true }).count(), 0)
      const refresh = result.getByRole('button', { name: 'Check saved course progress', exact: true })
      const before = apiCalls.length
      await refresh.click()
      await result.getByText('Current progress loaded. Open the learning panel to inspect your saved work.', { exact: true }).waitFor()
      assert.ok(apiCalls.length > before)
      assert.ok(apiCalls.slice(before).every(c => c.method === 'GET'))
      await capture(`malformed-${index}-${native ? 'native200' : 'normal'}-${width}`, refresh)
    }
    for (const [index, [tool, payload]] of valid.entries()) {
      const result = await send(tool, payload)
      if (native) await review.setBrowserZoom(2)
      assert.equal(await result.locator('.cert-chat-card').count(), 1)
      assert.equal(await result.getByRole('alert').count(), 0)
      if (structureOnly) {
        const card = result.locator('.cert-chat-card')
        assert.ok(await card.getByRole('heading', { level: 3 }).count())
        if (tool === 'get_certification_progress') {
          assert.equal(await card.getByRole('progressbar', { name: 'Course modules completed' }).count(), 1)
          assert.equal(await card.getByRole('listitem').count(), payload.modules.length)
        }
        if (tool === 'check_certification_module') {
          assert.equal(await card.getByRole('listitem').count(), payload.checks.length)
          assert.match(await card.getByRole('listitem').nth(0).innerText(), /— Met/)
          assert.match(await card.getByRole('listitem').nth(1).innerText(), /— Not met/)
        }
        review.observations.push({ tool, width, accessibleStructure: await card.ariaSnapshot() })
      }
      if (tool === 'check_certification_module') {
        assert.equal(await result.getByText('"Foundations" — module requirements met; review check details', { exact: true }).count(), 1)
        assert.equal(await result.getByText(/all checks passed/i).count(), 0)
      }
      await capture(`valid-${index}-${native ? 'native200' : 'normal'}-${width}`, result.locator('.cert-chat-card'))
    }
  }
  assert.ok(apiCalls.every(c => c.method === 'GET'))
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push(structureOnly
    ? { semanticCardCases: valid.length, headings: true, namedProgress: true, moduleAndCheckLists: true, originalRolelessVerdicts: true, actualCertificationWrites: 0, actualModelCalls: 0 }
    : { malformedCases: bad.length, validCases: valid.length, savedStateRecovery: 'GET-only', actualCertificationWrites: 0, actualModelCalls: 0 })
} catch (error) { await review.capture('blocked', String(error)); throw error } finally { await review.flush(); await review.browser.close() }
