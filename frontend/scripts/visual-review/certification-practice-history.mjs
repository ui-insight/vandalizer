import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const root = new URL('../../../backend/certification-data/', import.meta.url)
const modules = JSON.parse(await readFile(new URL('panel-modules.json', root), 'utf8'))
const draft = JSON.parse(await readFile(new URL('drafts/v5.0/ai-literacy-teaching.json', root), 'utf8'))
const module = { ...modules.find(item => item.id === draft.module_id), lessons: draft.replacements.map(({ knowledge_check, ...lesson }) => ({ ...lesson, knowledgeCheck: knowledge_check })) }
const first = module.lessons[0]
const identity = { enrollment_id: 'practice-course', course_version: 'qa-v5-teaching', manifest_sha256: 'e'.repeat(64), course_title: 'Vandalizer 5.0 teaching preview', modules_total: 1, module_ids: [module.id], maximum_xp: module.xp }
const course = { ...JSON.parse(await readFile(new URL('course-structure.json', root), 'utf8')), ...identity, versioned: true, modules: [module], prerequisites: { [module.id]: [] } }
const position = { module_id: module.id, lesson_id: first.id, revision: first.revision, content_sha256: 'f'.repeat(64), saved_at: '2026-10-08T12:00:00Z' }
const progress = { ...identity, id: 'qa-practice', user_id: 'reviewer', modules: { [module.id]: { completed: false, stars: 0, attempts: 0, xp_earned: 0, learning_position: position } }, total_xp: 0, level: 'novice', certified: false, certified_at: null, learning_position: position, position_revision: 1 }
const content = { ...identity, module_id: module.id, module_title: module.title, lesson_id: first.id, lesson_revision: first.revision, lesson_number: 1, lesson_count: module.lessons.length, is_last: false, title: first.title, content: first.content, objective: first.objective, knowledge_check: first.knowledgeCheck, diagram: first.diagram }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5303', resetStorage: false,
  evidenceMode: 'Actual authored draft question and frozen frontend; synthetic course transport. Browser-local practice persistence, chat/panel reuse and storage failure. No certification writes or model grading.' })
const { page, context, state } = review
const courseRequests = []
await context.route('**/api/auth/config', route => route.fulfill({ json: { auth_methods: ['password'], oauth_providers: [] } }))
await context.route('**/api/certification/**', route => {
  const request = route.request(), path = new URL(request.url()).pathname
  assert.equal(request.method(), 'GET', `Practice must not write a course: ${path}`); courseRequests.push(path)
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  return route.fallback()
})
async function send() {
  state.chatChunks = [{ kind: 'tool_call', tool_name: 'get_certification_lesson', tool_call_id: 'practice', args: {} }, { kind: 'tool_result', tool_name: 'get_certification_lesson', tool_call_id: 'practice', content }]
  await page.getByRole('textbox', { name: 'Message input', exact: true }).fill('Show this saved lesson.')
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
  const card = page.locator('.cert-chat-card').last()
  await card.getByRole('navigation', { name: 'Chat lesson navigation' }).waitFor()
  return card
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
    const suffix = native ? 'native' : width
    await page.setViewportSize({ width, height: native ? 1700 : 1000 })
    await page.goto(review.baseURL)
    await page.evaluate(() => { localStorage.clear(); sessionStorage.clear() })
    await page.reload()
    if (native) await review.setBrowserZoom(2)
    let card = await send()
    const practice = card.getByRole('group', { name: 'Knowledge check · practice' })
    await practice.getByRole('radio').nth(first.knowledgeCheck.options.findIndex(item => !item.correct)).check()
    await practice.getByRole('button', { name: 'Check answer', exact: true }).click()
    await practice.getByRole('radio').nth(first.knowledgeCheck.options.findIndex(item => item.correct)).check()
    await practice.getByRole('button', { name: 'Check answer', exact: true }).click()
    await practice.getByText('Recent practice attempts', { exact: true }).focus(); await page.keyboard.press('Enter')
    await capture(`chat-practice-history-${suffix}`, practice.getByText('Recent practice attempts', { exact: true }))
    const saved = await page.evaluate(() => Object.fromEntries(Object.entries(localStorage).filter(([key]) => key.startsWith('cert-practice:'))))
    assert.equal(Object.keys(saved).length, 1)
    assert.equal(JSON.parse(Object.values(saved)[0]).attempts.length, 2)
    await page.reload(); card = await send()
    await card.getByText(/2 recent practice attempts saved on this browser/).waitFor()
    assert.equal(await card.getByRole('radio', { checked: true }).count(), 0)
    await card.getByRole('button', { name: 'Open learning panel', exact: true }).click()
    const panel = page.locator('[data-cert-panel="true"]')
    await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    const panelPractice = panel.getByRole('group', { name: 'Knowledge check · practice' })
    await panelPractice.getByText(/2 recent practice attempts saved on this browser/).waitFor()
    await panelPractice.getByText('Recent practice attempts', { exact: true }).click()
    await capture(`panel-restored-practice-${suffix}`, panelPractice.getByText('Recent practice attempts', { exact: true }))
    await panelPractice.getByRole('button', { name: 'Clear saved practice', exact: true }).click()
    assert.equal(await panelPractice.getByRole('radio').first().evaluate(node => document.activeElement === node), true)
    assert.equal(await page.evaluate(() => Object.keys(localStorage).filter(key => key.startsWith('cert-practice:')).length), 0)
    await page.evaluate(() => {
      window.practiceOriginalSetItem = Storage.prototype.setItem
      Storage.prototype.setItem = function(key, value) { if (key.startsWith('cert-practice:')) throw new Error('Synthetic storage failure'); return window.practiceOriginalSetItem.call(this, key, value) }
    })
    await panelPractice.getByRole('radio').first().check()
    await panelPractice.getByRole('button', { name: 'Check answer', exact: true }).click()
    await panelPractice.getByRole('alert').waitFor()
    await capture(`practice-storage-unavailable-${suffix}`, panelPractice.getByRole('alert'))
    await page.evaluate(() => { Storage.prototype.setItem = window.practiceOriginalSetItem; delete window.practiceOriginalSetItem })
    assert.equal(progress.total_xp, 0); assert.equal(progress.position_revision, 1)
  }
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  review.observations.push({ persistedBrowserAttempts: true, scope: 'learner/enrollment/lesson/revision/question', chatPanelHistoryMatches: true, restoredAnswersDoNotSubmit: true, noCourseWrites: true, readingPositionUnchanged: true, courseRequests })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
