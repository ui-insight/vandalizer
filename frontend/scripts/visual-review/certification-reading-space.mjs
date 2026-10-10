import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const fixtures = JSON.parse(await readFile(new URL('../../src/components/certification/__fixtures__/chat-tool-contract.json', import.meta.url), 'utf8'))
const lesson = fixtures.find(item => item.tool_name === 'get_certification_lesson').content
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL,
  evidenceMode: 'Certification reading space, composer targets and preserved unsent draft. Synthetic chat response; no actual message, model, course or grade write. Text enlargement is not an OS keyboard.' })
const { page, context, state } = review
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
const writes = []
await context.route('**/api/certification/**', async route => {
  if (route.request().method() !== 'GET') writes.push(route.request().url())
  return route.fallback()
})
async function capture(id) {
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
try {
  await page.setViewportSize({ width: native ? 780 : 320, height: native ? 1000 : 844 })
  await page.goto(review.baseURL)
  if (native) await review.setBrowserZoom(2)
  state.chatChunks = [{ kind: 'tool_call', tool_name: 'get_certification_lesson', tool_call_id: 'reading-space', args: {} },
    { kind: 'tool_result', tool_name: 'get_certification_lesson', tool_call_id: 'reading-space', content: lesson },
    { kind: 'text', content: 'reading-space-delivered' }]
  const draft = page.getByRole('textbox', { name: 'Message input', exact: true })
  await draft.fill('Show the lesson.')
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
  await page.getByText('reading-space-delivered', { exact: true }).waitFor()
  await draft.fill('Keep my question.')
  const reading = page.getByRole('region', { name: 'Conversation', exact: true })
  const metrics = await page.evaluate(() => {
    const reading = document.querySelector('[aria-label="Conversation"]'), composer = document.querySelector('.chat-composer')
    return { rootFontSize: getComputedStyle(document.documentElement).fontSize,
      readingHeight: reading.getBoundingClientRect().height, composerHeight: composer.getBoundingClientRect().height,
      textSize: getComputedStyle(composer.querySelector('textarea')).fontSize,
      controls: [...composer.querySelectorAll('button')].filter(el => el.getClientRects().length).map(el => {
        const r = el.getBoundingClientRect()
        return { name: el.getAttribute('aria-label') || el.textContent.trim(), width: r.width, height: r.height }
      }) }
  })
  review.observations.push(metrics)
  if (process.env.REVIEW_MIN_READING_HEIGHT) {
    assert.ok(metrics.readingHeight >= Number(process.env.REVIEW_MIN_READING_HEIGHT), JSON.stringify(metrics))
    assert.ok(metrics.controls.every(control => control.width >= 44 && control.height >= 44), JSON.stringify(metrics.controls))
  }
  await reading.locator('.cert-chat-card').scrollIntoViewIfNeeded()
  await capture('course-and-unsent-question')
  const add = page.getByRole('button', { name: 'Add', exact: true })
  await add.click()
  const menu = page.getByRole('menu')
  await menu.waitFor()
  assert.equal(await menu.evaluate(el => { const r = el.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth }), true, 'Attachment menu remains visible')
  await capture('attachment-menu')
  const lastAttachment = menu.getByRole('menuitem').last()
  await lastAttachment.focus()
  assert.equal(await lastAttachment.evaluate(el => {
    const r = el.getBoundingClientRect(), hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
    return el === document.activeElement && !!hit && el.contains(hit)
  }), true, 'The final attachment action is focusable and unobscured')
  await add.click()
  await page.getByRole('button', { name: /^Choose chat model:/ }).click()
  const model = page.getByRole('dialog', { name: 'Choose chat model', exact: true })
  await model.waitFor()
  await capture('model-picker')
  await model.getByRole('button', { name: 'Close model picker', exact: true }).click()
  assert.equal(await draft.inputValue(), 'Keep my question.')
  assert.deepEqual(writes, [])
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ unsentDraftPreserved: true, attachmentAndModelControlsReachable: true, actualMobileKeyboard: false })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
