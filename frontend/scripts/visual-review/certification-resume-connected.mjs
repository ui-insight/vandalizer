import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const session = JSON.parse(await readFile('/private/tmp/certification-lesson-resume-session.json', 'utf8'))
assert.equal(session.api_origin, 'http://127.0.0.1:5293')
assert.ok(session.database.startsWith('certification_qa_'))
const origin = session.api_origin, output = process.env.REVIEW_OUTPUT
const before = await fetch(origin + '/qa/state').then(response => response.json())
assert.equal(before.position_revision, 0)
const course = await fetch(origin + '/api/certification/course?enrollment_id=' + session.enrollment_id).then(response => response.json())
const lessons = course.modules.find(item => item.id === 'ai_literacy').lessons
const clients = [], writes = []
async function create(name, width) {
  const review = await createReview({ output: `${output}/${name}`, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Actual certification HTTP routes and disposable MongoDB persistence. Separate browser processes/profiles, synthetic authenticated test identity and chat transport. No model call or real learner.' })
  clients.push(review)
  await review.context.route('**/api/certification/**', async route => {
    const req = route.request(), url = new URL(req.url()), method = req.method()
    assert.ok(method === 'GET' || (method === 'PUT' && url.pathname.endsWith('/position')), 'Only reads and explicit reading cursors are allowed')
    const response = await fetch(origin + url.pathname + url.search, { method, headers: { 'Content-Type': 'application/json' }, ...(method === 'GET' ? {} : { body: req.postData() }) })
    const body = await response.text()
    if (method === 'PUT') writes.push({ browser: name, request: req.postDataJSON(), status: response.status, response: JSON.parse(body) })
    await route.fulfill({ status: response.status, contentType: 'application/json', body })
  })
  await review.page.setViewportSize({ width, height: 900 })
  await review.page.goto(review.baseURL)
  return review
}
async function send(review, module = false) {
  const tool = module ? 'get_certification_module' : 'get_certification_lesson', payload = module ? session.module : session.lesson
  review.state.chatChunks = [{ kind: 'tool_call', tool_name: tool, tool_call_id: 'resume', args: {} }, { kind: 'tool_result', tool_name: tool, tool_call_id: 'resume', content: payload }, { kind: 'text', content: 'Original course teaching loaded.' }]
  await review.page.getByRole('textbox', { name: 'Message input', exact: true }).fill('Open my course teaching.')
  await review.page.getByRole('button', { name: 'Send message', exact: true }).click()
  const card = review.page.locator('.cert-chat-card').last()
  if (module) await card.getByRole('button', { name: `Start the lessons (${lessons.length})`, exact: true }).click()
  await card.getByRole('navigation', { name: 'Chat lesson navigation' }).waitFor()
  return card
}
async function show(card, index) { await card.getByRole('combobox').selectOption(lessons[index].id) }
async function save(card) {
  await card.getByRole('button', { name: 'Save my place', exact: true }).click()
  await card.getByText('Place saved across devices.', { exact: true }).waitFor()
}
async function capture(review, name, target) {
  await target.scrollIntoViewIfNeeded(); await review.capture(name)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${name}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(name)
}
try {
  const a = await create('browser-a', 1440), b = await create('browser-b', 390)
  let cardA = await send(a), cardB = await send(b)
  await a.page.evaluate(() => localStorage.setItem('qa-browser-isolation', 'a'))
  assert.equal(await b.page.evaluate(() => localStorage.getItem('qa-browser-isolation')), null)
  await cardA.getByRole('button', { name: 'Open learning panel', exact: true }).click()
  const previousPanel = a.page.locator('[data-cert-panel="true"]')
  await previousPanel.getByRole('button', { name: /Foundations/ }).click()
  await previousPanel.getByRole('heading', { name: 'Module 1: Foundations', exact: true }).waitFor()
  await previousPanel.getByRole('button', { name: 'Return to workspace', exact: true }).click()
  await show(cardA, 2); await save(cardA)
  await cardA.getByRole('button', { name: 'Open learning panel', exact: true }).click()
  await previousPanel.getByRole('heading', { name: lessons[2].title, exact: true }).waitFor()
  await capture(a, 'reopened-panel-follows-new-chat-module', previousPanel.getByRole('heading', { name: lessons[2].title, exact: true }))
  await previousPanel.getByRole('button', { name: 'Return to workspace', exact: true }).click()
  await capture(a, 'first-device-saved', cardA.getByText('Place saved across devices.', { exact: true }))
  await show(cardB, 3)
  await cardB.getByRole('button', { name: 'Save my place', exact: true }).click()
  const refresh = cardB.getByRole('button', { name: 'Refresh progress', exact: true }); await refresh.waitFor()
  assert.equal(writes.at(-1).status, 409)
  let saved = await fetch(origin + '/qa/state').then(response => response.json())
  assert.equal(saved.learning_position.lesson_id, lessons[2].id); assert.equal(saved.position_revision, 1)
  await capture(b, 'stale-device-conflict', refresh)
  const count = writes.length
  await refresh.click(); await cardB.getByRole('button', { name: 'Return to saved lesson', exact: true }).click()
  assert.equal(await cardB.getByRole('combobox').inputValue(), lessons[2].id)
  assert.equal(writes.length, count)
  await capture(b, 'refreshed-original-place', cardB.getByRole('heading', { name: lessons[2].title, exact: true }))
  await show(cardB, 4); await save(cardB)
  await a.page.reload(); cardA = await send(a)
  await cardA.getByRole('button', { name: 'Return to saved lesson', exact: true }).click()
  assert.equal(await cardA.getByRole('combobox').inputValue(), lessons[4].id)
  await capture(a, 'reload-after-second-device-save', cardA.getByRole('heading', { name: lessons[4].title, exact: true }))
  await cardA.getByRole('button', { name: 'Open learning panel', exact: true }).click()
  let panel = a.page.locator('[data-cert-panel="true"]')
  await panel.getByRole('heading', { name: lessons[4].title, exact: true }).waitFor()
  await capture(a, 'panel-same-persisted-lesson', panel.getByRole('heading', { name: lessons[4].title, exact: true }))
  await panel.getByRole('button', { name: 'Next', exact: true }).click()
  await panel.getByText('Place saved across devices.', { exact: true }).waitFor()
  assert.equal(writes.at(-1).request.lesson_id, lessons[5].id)
  await panel.getByRole('button', { name: 'Return to workspace', exact: true }).click()
  await b.page.reload(); cardB = await send(b, true)
  await cardB.getByRole('button', { name: 'Return to saved lesson', exact: true }).click()
  assert.equal(await cardB.getByRole('combobox').inputValue(), lessons[5].id)
  await capture(b, 'module-reader-resumes-panel-save', cardB.getByRole('heading', { name: lessons[5].title, exact: true }))
  await show(cardB, 0); await save(cardB)
  await capture(b, 'explicit-restart-saved', cardB.getByText('Place saved across devices.', { exact: true }))
  await a.page.reload(); cardA = await send(a)
  await cardA.getByRole('button', { name: 'Open learning panel', exact: true }).click()
  panel = a.page.locator('[data-cert-panel="true"]')
  await panel.getByRole('heading', { name: lessons[0].title, exact: true }).waitFor()
  await capture(a, 'panel-restarted-without-credit-reset', panel.getByRole('heading', { name: lessons[0].title, exact: true }))
  const after = await fetch(origin + '/qa/state').then(response => response.json())
  assert.equal(after.position_revision, 4); assert.equal(after.learning_position.lesson_id, lessons[0].id)
  for (const key of ['total_xp', 'certified', 'credentials', 'attempts', 'active_enrollment_id']) assert.deepEqual(after[key], before[key])
  assert.deepEqual(after.modules.foundations, before.modules.foundations)
  assert.deepEqual(after.modules.ai_literacy.self_assessment, before.modules.ai_literacy.self_assessment)
  assert.deepEqual(after.modules.ai_literacy.provisioned_docs, before.modules.ai_literacy.provisioned_docs)
  assert.equal(after.in_flight_writes, 0)
  assert.deepEqual(writes.map(item => item.status), [200, 409, 200, 200, 200])
  assert.deepEqual(writes.map(item => item.request.expected_revision), [0, 0, 1, 2, 3])
  for (const client of clients) { assert.deepEqual(client.errors, []); assert.deepEqual([...client.unmatched], []) }
  await writeFile(`${output}/persistence.json`, JSON.stringify({ before, after, writes, browserStorageIsolated: true, liveModelCalls: 0 }, null, 2))
} catch (error) { for (const client of clients) await client.capture('blocked', String(error)); throw error }
finally { for (const client of clients) { await client.flush(); await client.browser.close() } }
