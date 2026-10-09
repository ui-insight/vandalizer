import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const data = new URL('../../../backend/certification-data/', import.meta.url)
const read = async name => JSON.parse(await readFile(new URL(name, data), 'utf8'))
const all = await read('panel-modules.json'), structure = await read('course-structure.json')
const teaching = await read('drafts/v5.0/foundations-teaching.json')
const exercise = await read('drafts/v5.0/foundations-exercise.json')
const prompts = await read('drafts/v5.0/foundations-decisions.json')
const module = { ...all.find(item => item.id === 'foundations'), ...teaching.module_patch,
  lessons: teaching.replacements.map(({ knowledge_check, ...lesson }) => ({ ...lesson, knowledgeCheck: knowledge_check })),
  decisionPrompts: prompts.map(prompt => ({ ...prompt, prompt_sha256: 'a'.repeat(64) })), practicalPreparation: true }
const identity = { enrollment_id: 'qa-foundations-assignment', course_version: 'qa-foundations-draft', manifest_sha256: 'd'.repeat(64), course_title: 'Foundations 5.0 assignment preview', modules_total: 1, module_ids: [module.id], maximum_xp: module.xp }
const course = { ...structure, ...identity, versioned: true, modules: [module], prerequisites: { foundations: [] } }
const progress = { ...identity, id: 'qa-foundations', user_id: 'reviewer', modules: { foundations: { provisioned_docs: ['qa-assigned-source'] } }, total_xp: 0, level: 'novice', certified: false, learning_position: null, position_revision: 0 }
const contracts = JSON.parse(await readFile(new URL('../../src/components/certification/__fixtures__/chat-tool-contract.json', import.meta.url), 'utf8'))
const content = { ...contracts.find(item => item.tool_name === 'get_certification_module' && item.content.module_id === 'foundations').content,
  ...identity, overview: exercise.overview, instructions: exercise.instructions, agent_guidance: exercise.chat_instructions, expected_fields: exercise.expected_fields,
  star_criteria: {}, lesson_titles: module.lessons.map(lesson => lesson.title), assessment_keys: [] }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Actual panel/chat renderers and authored draft Foundations instructions with synthetic transport. Viewing/toggling only; no real preparation, source decision, model, credit or enrollment.' })
const { page, context, state } = review
const reads = []
await context.route('**/api/certification/**', route => {
  const req = route.request(), path = new URL(req.url()).pathname
  assert.equal(req.method(), 'GET', `Unexpected certification write ${path}`); reads.push(path)
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/exercise')) return route.fulfill({ json: exercise })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/practical-runs')) return route.fulfill({ json: { enrollment_id: identity.enrollment_id, module_id: 'foundations', runs: [], older_runs_available: false } })
  return route.fallback()
})
async function capture(id, target) {
  if (target) await target.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
try {
  for (const width of native ? [640, 780, 1440] : [320, 390, 1440]) {
    await page.setViewportSize({ width, height: native ? 1100 : 800 })
    await page.goto(review.baseURL + '/certification')
    if (native) await review.setBrowserZoom(2)
    const panel = page.locator('[data-cert-panel="true"]')
    await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    await panel.getByRole('button', { name: /^1 Foundations/ }).click()
    await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
    const summary = panel.locator('summary').filter({ hasText: /^Your Foundations assignment$/ })
    await summary.waitFor()
    const assignment = summary.locator('..')
    assert.equal(await assignment.getByRole('listitem').count(), exercise.instructions.length)
    for (const instruction of exercise.instructions) await assignment.getByText(instruction, { exact: true }).waitFor()
    assert.equal(await assignment.getByText(/Extract 3\+|Extract 8\+/).count(), 0)
    await capture(`panel-introduction-${width}`, summary)
    await capture(`panel-scope-${width}`, assignment.getByRole('listitem').nth(2))
    await capture(`panel-source-checks-${width}`, assignment.getByRole('listitem').last())
    await summary.focus(); await page.keyboard.press('Space')
    assert.equal(await assignment.getAttribute('open'), null)
    const prepare = panel.getByRole('button', { name: 'Choose my extraction', exact: true })
    await capture(`panel-next-action-${width}`, prepare)
    await panel.getByRole('button', { name: 'Return to workspace', exact: true }).click()
    state.chatChunks = [{ kind: 'tool_call', tool_name: 'get_certification_module', tool_call_id: 'assignment', args: {} },
      { kind: 'tool_result', tool_name: 'get_certification_module', tool_call_id: 'assignment', content }]
    await page.getByRole('textbox', { name: 'Message input', exact: true }).fill('Show my Foundations assignment.')
    await page.getByRole('button', { name: 'Send message', exact: true }).click()
    const card = page.locator('.cert-chat-card').last()
    await card.locator('summary').filter({ hasText: 'Exercise instructions' }).click()
    const steps = card.locator('.cert-procedure > li')
    await steps.last().waitFor()
    assert.equal(await steps.count(), exercise.instructions.length)
    assert.equal(await card.getByText(/Extract 3\+|Extract 8\+/).count(), 0)
    for (let index = 0; index < exercise.instructions.length; index++) {
      assert.equal((await steps.nth(index).innerText()).trim(), exercise.instructions[index])
      assert.equal(await steps.nth(index).evaluate(el => el.scrollWidth <= el.clientWidth), true)
    }
    await capture(`chat-start-${width}`, steps.first())
    await capture(`chat-final-step-${width}`, steps.last())
  }
  assert.equal(progress.total_xp, 0); assert.equal(progress.certified, false)
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ panelInstructionCount: exercise.instructions.length, chatInstructionCount: exercise.chat_instructions.length, certificationRequests: reads, certificationWrites: 0, realCreditAwarded: false, realPreparation: false })
} catch (error) { await review.capture('blocked', String(error)); throw error } finally { await review.flush(); await review.browser.close() }
