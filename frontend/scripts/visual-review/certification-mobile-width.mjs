import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const payloads = JSON.parse(await readFile(new URL('../../src/components/certification/__fixtures__/chat-tool-contract.json', import.meta.url), 'utf8'))
const lesson = payloads.find(row => row.tool_name === 'get_certification_lesson' && row.content.module_id === 'workflow_design')
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Actual frontend with a real exported teaching payload and synthetic transport. Responsive navigation labels, short-screen keyboard reach and retained chat/source state; no actual mobile keyboard.' })
const { page, state } = review
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
async function capture(id) {
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
try {
  for (const width of native ? [640, 780, 1440] : [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: native ? 1000 : 650 })
    await page.goto(review.baseURL)
    if (native) await review.setBrowserZoom(2)
    state.chatChunks = [{ kind: 'tool_call', tool_name: lesson.tool_name, tool_call_id: 'lesson', args: {} }, { kind: 'tool_result', tool_name: lesson.tool_name, tool_call_id: 'lesson', content: lesson.content }, { kind: 'text', content: 'Saved lesson ready.' }]
    const draft = page.getByRole('textbox', { name: 'Message input', exact: true })
    await draft.fill('Show this saved lesson.')
    await page.getByRole('button', { name: 'Send message', exact: true }).click()
    await page.getByText('Saved lesson ready.', { exact: true }).waitFor()
    await draft.fill('Keep this unsent learner question.')
    const nav = page.getByRole('navigation', { name: 'Workspace navigation', exact: true })
    const card = page.locator('.cert-chat-card')
    const original = await card.elementHandle()
    const heading = card.getByRole('heading', { name: lesson.content.title, exact: true })
    await nav.getByRole('button', { name: 'Chat', exact: true }).focus()
    await heading.scrollIntoViewIfNeeded()
    await capture(`reading-${width}`)
    const compact = await page.evaluate(() => innerWidth <= 767)
    assert.equal((await nav.boundingBox()).width, compact ? 56 : 88)
    if (compact) {
      const readingWidth = (await card.boundingBox()).width
      await nav.getByRole('button', { name: 'Show navigation labels', exact: true }).focus(); await page.keyboard.press('Space')
      assert.equal((await nav.boundingBox()).width, 88)
      assert.equal(readingWidth - (await card.boundingBox()).width, 32)
      await capture(`navigation-labels-${width}`)
      await nav.getByRole('button', { name: 'Hide navigation labels', exact: true }).focus(); await page.keyboard.press('Space')
      assert.equal((await nav.boundingBox()).width, 56)
    }
    await card.locator('.chat-markdown p').first().scrollIntoViewIfNeeded()
    await capture(`reading-body-${width}`)
    await nav.getByRole('button', { name: 'Files', exact: true }).click()
    const sourcePanel = page.getByRole('button', { name: 'Files panel', exact: true })
    if (await sourcePanel.isVisible()) await sourcePanel.click()
    const document = page.getByRole('checkbox', { name: 'Select Proposal narrative.pdf', exact: true })
    await document.check()
    await nav.getByRole('button', { name: 'Chat', exact: true }).click()
    assert.equal(await draft.inputValue(), 'Keep this unsent learner question.')
    assert.equal(await original.evaluate(el => el.isConnected), true)
    await heading.scrollIntoViewIfNeeded()
    await capture(`reading-after-source-selection-${width}`)
    await page.setViewportSize({ width, height: native ? 500 : 250 })
    const knowledge = nav.getByRole('button', { name: 'Knowledge', exact: true })
    await nav.getByRole('button', { name: 'Chat', exact: true }).focus()
    await page.keyboard.press('Tab'); await page.keyboard.press('Tab'); await page.keyboard.press('Tab')
    assert.equal(await knowledge.evaluate(el => document.activeElement === el && el.matches(':focus-visible')), true)
    const reachable = await knowledge.evaluate(el => { const r = el.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth })
    assert.equal(reachable, true, 'Short-screen navigation must scroll the focused action into view')
    await capture(`short-navigation-focus-${width}`)
    await nav.getByRole('button', { name: 'Files', exact: true }).click()
    if (await sourcePanel.isVisible()) await sourcePanel.click()
    assert.equal(await document.isChecked(), true)
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ compactNavigationWidth: 56, expandedNavigationWidth: 88, extraReadingWidth: 32, chatDraftPreserved: true, lessonNodePreserved: true, sourceSelectionPreserved: true, actualMobileKeyboard: false })
} catch (error) { await review.capture('blocked', String(error)); throw error } finally { await review.flush(); await review.browser.close() }
