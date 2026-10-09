import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const rows = JSON.parse(await readFile(new URL('../../src/components/certification/__fixtures__/chat-tool-contract.json', import.meta.url), 'utf8'))
const lesson = rows.find(row => row.tool_name === 'get_certification_lesson')
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Actual course reader with synthetic transport; a full notification polling interval and reload. Diagnostic follow-up to a WebKit background error; no model, credit or notification delivery.' })
try {
  await review.page.goto(review.baseURL)
  review.state.chatChunks = [{ kind: 'tool_call', tool_name: lesson.tool_name, tool_call_id: 'polling', args: {} }, { kind: 'tool_result', tool_name: lesson.tool_name, tool_call_id: 'polling', content: lesson.content }]
  const polled = review.page.waitForResponse(response => new URL(response.url()).pathname === '/api/notifications/count', { timeout: 45000 })
  await review.page.getByRole('textbox', { name: 'Message input', exact: true }).fill('Open the lesson.')
  await review.page.getByRole('button', { name: 'Send message', exact: true }).click()
  const heading = review.page.getByRole('heading', { name: lesson.content.title, exact: true })
  await heading.waitFor(); await heading.scrollIntoViewIfNeeded()
  const response = await polled
  assert.equal(response.status(), 200)
  assert.deepEqual(await response.json(), { unread_count: 0 })
  await review.capture('lesson-after-background-poll')
  assert.deepEqual(review.errors, [])
  await review.page.reload()
  await review.page.getByRole('textbox', { name: 'Message input', exact: true }).waitFor()
  await review.capture('reload-after-completed-poll')
  for (const id of ['lesson-after-background-poll', 'reload-after-completed-poll']) assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ notificationPollCompleted: true, notificationResponseMatchesContract: true, pageReloaded: true, earlierParallelErrorReproduced: false })
} catch (error) { await review.capture('blocked', String(error)); throw error } finally { await review.flush(); await review.browser.close() }
