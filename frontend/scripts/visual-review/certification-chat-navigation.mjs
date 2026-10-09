import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const data = new URL('../../../backend/certification-data/', import.meta.url)
const all = JSON.parse(await readFile(new URL('panel-modules.json', data), 'utf8'))
const draft = JSON.parse(await readFile(new URL('drafts/v5.0/ai-literacy-teaching.json', data), 'utf8'))
const module = { ...all.find(m => m.id === draft.module_id), lessons: draft.replacements.map(({ knowledge_check, ...lesson }) => ({ ...lesson, knowledgeCheck: knowledge_check })) }
const identity = { enrollment_id: 'qa-chat-navigation', course_version: 'qa-v5-teaching', manifest_sha256: 'e'.repeat(64), course_title: 'Vandalizer 5.0 teaching preview', modules_total: 1, module_ids: [module.id], maximum_xp: module.xp }
const structure = JSON.parse(await readFile(new URL('course-structure.json', data), 'utf8'))
const course = { ...structure, ...identity, versioned: true, modules: [module], prerequisites: { [module.id]: [] } }
const position = lesson => ({ module_id: module.id, lesson_id: lesson.id, revision: lesson.revision, content_sha256: 'f'.repeat(64), saved_at: '2026-10-07T12:00:00Z' })
const progress = { ...identity, id: 'qa-navigation', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, learning_position: null, position_revision: 0 }
const payloads = JSON.parse(await readFile(new URL('../../src/components/certification/__fixtures__/chat-tool-contract.json', import.meta.url), 'utf8'))
const moduleContent = { ...payloads.find(item => item.tool_name === 'get_certification_module' && item.content.module_id === module.id).content, ...identity, lesson_titles: module.lessons.map(item => item.title) }
const first = module.lessons[0]
const content = { ...identity, module_id: module.id, module_title: module.title, lesson_id: first.id, lesson_revision: first.revision, lesson_number: 1, lesson_count: module.lessons.length, is_last: false, title: first.title, content: first.content, objective: first.objective, knowledge_check: first.knowledgeCheck, diagram: first.diagram }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Actual frontend and authored draft lessons; synthetic course/cursor transport. Direct chat navigation, explicit cursor save and failure recovery. No model or credit verification.' })
const { page, context, state } = review
const writes = [], agentRequests = []
let saveFails = false
page.on('request', request => { if (new URL(request.url()).pathname === '/api/chat') agentRequests.push(request.url()) })
await context.route('**/api/certification/**', async route => {
  const req = route.request(), path = new URL(req.url()).pathname
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/position')) {
    assert.equal(req.method(), 'PUT')
    const body = req.postDataJSON(); writes.push(body)
    assert.equal(body.module_id, module.id); assert.equal(body.expected_revision, progress.position_revision)
    const lesson = module.lessons.find(item => item.id === body.lesson_id); assert.ok(lesson)
    if (saveFails) return route.fulfill({ status: 409, json: { detail: 'Synthetic cursor conflict. Refresh before saving.' } })
    progress.position_revision++; progress.learning_position = position(lesson)
    progress.modules[module.id].learning_position = progress.learning_position
    return route.fulfill({ json: { ...identity, saved: true, position_revision: progress.position_revision, learning_position: progress.learning_position } })
  }
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  assert.equal(req.method(), 'GET', `Unexpected write: ${path}`)
  return route.fallback()
})
async function capture(id, target) {
  if (target) await target.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
async function send(payload, tool = 'get_certification_lesson') {
  state.chatChunks = [{ kind: 'tool_call', tool_name: tool, tool_call_id: 'lesson', args: {} }, { kind: 'tool_result', tool_name: tool, tool_call_id: 'lesson', content: payload }, { kind: 'text', content: 'Saved lesson ready.' }]
  await page.getByRole('textbox', { name: 'Message input', exact: true }).fill('Show this saved lesson.')
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
  const card = page.locator('.cert-chat-card').last(); await card.getByText(payload.title, { exact: true }).first().waitFor()
  return card
}
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
try {
  for (const width of native ? [640, 780, 1440] : [320, 390, 768, 1440]) {
    progress.position_revision = 0; progress.learning_position = position(module.lessons[2])
    progress.modules = { [module.id]: { completed: false, stars: 0, attempts: 0, xp_earned: 0, learning_position: progress.learning_position } }
    await page.setViewportSize({ width, height: native ? 1100 : 700 }); await page.goto(review.baseURL)
    if (native) await review.setBrowserZoom(2)
    const card = await send(content), navigation = card.getByRole('navigation', { name: 'Chat lesson navigation' })
    await navigation.waitFor()
    const draftBox = page.getByRole('textbox', { name: 'Message input', exact: true })
    await draftBox.fill('Keep this unsent question while I browse.')
    const callsBefore = agentRequests.length, writesBefore = writes.length
    assert.ok(callsBefore > 0, 'The agent request observer must see the fixture delivery')
    await capture(`first-reading-${width}`, card.getByRole('heading'))
    await capture(`first-navigation-${width}`, navigation)
    await navigation.getByRole('combobox').focus()
    await capture(`lesson-list-${width}`, navigation.getByRole('combobox'))
    const next = card.getByRole('button', { name: 'Next lesson', exact: true })
    await next.focus(); await page.keyboard.press('Space')
    const secondHeading = card.getByRole('heading', { name: module.lessons[1].title, exact: true })
    await secondHeading.waitFor(); assert.equal(await secondHeading.evaluate(el => document.activeElement === el), true)
    await capture(`next-lesson-${width}`, secondHeading)
    await card.getByRole('button', { name: 'Previous lesson', exact: true }).click()
    const correct = card.getByRole('radio').nth(first.knowledgeCheck.options.findIndex(item => item.correct))
    await correct.check(); await card.getByRole('button', { name: 'Check answer', exact: true }).click()
    await card.getByText(/Correct\. /).waitFor()
    await next.click(); await card.getByRole('button', { name: 'Previous lesson', exact: true }).click()
    assert.equal(await card.getByRole('radio', { checked: true }).count(), 0, 'Other lessons must not inherit a practice answer')
    await card.getByRole('button', { name: 'Return to saved lesson', exact: true }).click()
    assert.equal(await navigation.getByRole('combobox').inputValue(), module.lessons[2].id)
    await navigation.getByRole('combobox').selectOption(module.lessons.at(-1).id)
    assert.equal(await next.isDisabled(), true)
    await capture(`last-navigation-${width}`, navigation)
    assert.equal(writes.length, writesBefore); assert.equal(agentRequests.length, callsBefore)
    saveFails = true
    await card.getByRole('button', { name: 'Save my place', exact: true }).click()
    const refresh = card.getByRole('button', { name: 'Refresh progress', exact: true }); await refresh.waitFor()
    await capture(`failed-save-${width}`, refresh)
    await refresh.click(); assert.equal(writes.length, writesBefore + 1)
    await card.getByRole('button', { name: 'Return to saved lesson', exact: true }).click()
    assert.equal(await navigation.getByRole('combobox').inputValue(), module.lessons[2].id)
    saveFails = false
    await next.click(); await card.getByRole('button', { name: 'Save my place', exact: true }).click()
    await card.getByText('Place saved across devices.', { exact: true }).waitFor()
    assert.equal(writes.at(-1).lesson_id, module.lessons[3].id)
    assert.equal(await draftBox.inputValue(), 'Keep this unsent question while I browse.')
    assert.equal(agentRequests.length, callsBefore)
    await capture(`saved-place-${width}`, navigation)
    await card.getByRole('button', { name: 'Open learning panel', exact: true }).click()
    const panel = page.locator('[data-cert-panel="true"]')
    await panel.getByRole('heading', { name: module.lessons[3].title, exact: true }).waitFor()
    await capture(`panel-saved-place-${width}`, panel.getByRole('heading', { name: module.lessons[3].title, exact: true }))
    await panel.getByRole('button', { name: 'Return to workspace', exact: true }).click()
    assert.equal(writes.length, writesBefore + 2)
    const oldCard = await send({ ...content, lesson_revision: 1 })
    assert.equal(await oldCard.getByRole('navigation', { name: 'Chat lesson navigation' }).count(), 0)
    await capture(`historical-revision-${width}`, oldCard.getByText('This saved card is available to read. Open the learning panel for the current course lessons.', { exact: true }))
    await page.reload()
    const moduleCard = await send(moduleContent, 'get_certification_module')
    const moduleCalls = agentRequests.length
    await moduleCard.getByRole('button', { name: `Start the lessons (${module.lessons.length})`, exact: true }).click()
    await moduleCard.getByRole('heading', { name: first.title, exact: true }).waitFor()
    await moduleCard.getByRole('button', { name: 'Return to saved lesson', exact: true }).click()
    const restored = moduleCard.getByRole('heading', { name: module.lessons[3].title, exact: true })
    await restored.waitFor()
    assert.equal(agentRequests.length, moduleCalls)
    assert.equal(writes.length, writesBefore + 2)
    await capture(`module-start-and-restored-${width}`, restored)
    await moduleCard.getByRole('button', { name: 'Close lessons', exact: true }).click()
    assert.equal(await moduleCard.getByRole('navigation', { name: 'Chat lesson navigation' }).count(), 0)

  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ explicitCursorWrites: writes, extraAgentRequestsFromNavigation: 0, failedSaveDoesNotRetry: true, originalSavedPlacePreservedOnFailure: true, chatDraftPreserved: true, panelUsesSavedStableId: true })
} catch (error) { await review.capture('blocked', String(error)); throw error } finally { await review.flush(); await review.browser.close() }
