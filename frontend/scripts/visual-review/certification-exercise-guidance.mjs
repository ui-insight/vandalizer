import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const fixture = JSON.parse(await readFile(process.env.REVIEW_FIXTURE, 'utf8'))
const moduleIds = (process.env.REVIEW_MODULES || fixture.course.modules.map(module => module.id).join(',')).split(',')
const identity = { enrollment_id: 'a'.repeat(32), course_version: 'qa-current-exercise-guidance', course_title: fixture.course.course_title, manifest_sha256: 'd'.repeat(64) }
const progress = { ...identity, id: 'qa-exercise-guidance', user_id: 'reviewer', modules: {}, learning_position: null, position_revision: 0, total_xp: 0, level: 'novice', certified: false, certified_at: null }
const course = { ...fixture.course, ...identity, versioned: true, progress, prerequisites: Object.fromEntries(fixture.course.modules.map(module => [module.id, []])) }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL, evidenceMode: 'Actual current exercise and tutor projection via synthetic transport. Active identity is synthetic; lab document list omitted only for challenge access. Original criteria retained. No learner or grading writes.' })
const { page, context, state } = review
const writes = []
await context.route('**/api/certification/**', async route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (path.endsWith('/journey-events')) return route.fallback()
  if (request.method() !== 'GET') writes.push(path)
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/selection-status')) return route.fulfill({ json: { read_only: true, current_enrollment_id: identity.enrollment_id, pending: null } })
  if (path.endsWith('/exercise')) {
    const moduleId = path.split('/').at(-2)
    assert.ok(fixture.exercises[moduleId])
    return route.fulfill({ json: { ...fixture.exercises[moduleId], documents: [] } })
  }
  return route.fallback()
})
const plain = value => value.replaceAll('**', '').replaceAll('`', '').replace(/\s+/g, ' ').trim()
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
async function capture(id, target) {
  await target.scrollIntoViewIfNeeded(); await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1600 : 1000 })
    for (const moduleId of moduleIds) {
      const module = course.modules.find(item => item.id === moduleId), exercise = fixture.exercises[moduleId]
      assert.ok(module && exercise)
      await page.goto(review.baseURL + '/certification')
      if (native) await review.setBrowserZoom(2)
      const panel = page.locator('[data-cert-panel]')
      await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
      await panel.getByRole('button', { name: new RegExp(`^${module.number} ${module.title}`) }).click()
      await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
      const steps = panel.getByRole('heading', { name: 'Exercise Steps', exact: true }).locator('..').locator('ol > li')
      await steps.last().waitFor()
      assert.equal(await steps.count(), exercise.instructions.length)
      for (let i = 0; i < exercise.instructions.length; i++) assert.equal(plain(await steps.nth(i).locator('.cert-lesson-markdown').innerText()), plain(exercise.instructions[i]))
      for (const criteria of Object.values(exercise.star_criteria)) assert.equal(await panel.getByText(criteria, { exact: true }).count(), 1)
      await capture(`${moduleId}-panel-${width}`, steps.last())
      await panel.getByRole('button', { name: 'Return to workspace', exact: true }).click()
      const cardData = { ...fixture.tools[moduleId], ...identity }
      state.chatChunks = [{ kind: 'tool_call', tool_name: 'get_certification_module', tool_call_id: moduleId, args: {} },
        { kind: 'tool_result', tool_name: 'get_certification_module', tool_call_id: moduleId, content: cardData }]
      await page.getByRole('textbox', { name: 'Message input', exact: true }).fill('Show the original module directions.')
      await page.getByRole('button', { name: 'Send message', exact: true }).click()
      const card = page.locator('.cert-chat-card').last()
      const summary = card.locator('summary').filter({ hasText: 'Exercise instructions' })
      await summary.focus(); await page.keyboard.press('Enter')
      const chatSteps = card.locator('.cert-procedure > li')
      await chatSteps.last().waitFor()
      assert.equal(await chatSteps.count(), cardData.instructions.length)
      for (let i = 0; i < cardData.instructions.length; i++) assert.equal(plain(await chatSteps.nth(i).innerText()), plain(cardData.instructions[i]))
      await capture(`${moduleId}-chat-${width}`, chatSteps.last())
    }
  }
  assert.deepEqual(writes, []); assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ moduleIds, exactPanelAndChatInstructions: true, originalCriteriaPreserved: true, keyboardDisclosure: true, courseWrites: writes, modelCalls: 0, credit: 0 })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
