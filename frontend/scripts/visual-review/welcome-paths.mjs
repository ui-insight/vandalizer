import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const review = await createReview({ output: '../artifacts/visual-review/welcome-paths', baseURL: 'http://127.0.0.1:5189' })
const { page, state, capture } = review
state.first = true
try {
  for (const width of [1440, 768, 320]) {
    await page.setViewportSize({ width, height: 1000 })
    await page.goto(review.baseURL + '/?mode=chat')
    await page.getByRole('heading', { name: 'What would you like to get done?' }).waitFor()
    await capture(`welcome-${width}`)
    assert.deepEqual(JSON.parse(await readFile(`${review.out}/welcome-${width}.axe.json`, 'utf8')), [])
    assert.ok(review.captures.at(-1).pageWidth <= width)
    await page.getByRole('button', { name: 'Start a conversation', exact: true }).click()
    assert.equal(await page.getByRole('textbox', { name: 'Message input' }).evaluate(el => el === document.activeElement), true)
    await page.getByRole('button', { name: 'Choose a knowledge base', exact: true }).click()
    const picker = page.getByRole('dialog', { name: 'Attach knowledge bases' })
    await picker.getByRole('button', { name: 'Research administration policies', exact: true }).click()
    await picker.getByRole('button', { name: 'Attach', exact: true }).click()
    assert.equal(await page.getByRole('heading', { name: 'What would you like to get done?' }).count(), 0)
    assert.equal(await page.getByText('Getting started', { exact: true }).count(), 0)
    await capture(`welcome-knowledge-${width}`)
    await page.getByRole('textbox', { name: 'Message input' }).fill('What are the review requirements?')
    await Promise.all([page.waitForResponse(response => response.url().endsWith('/api/chat')), page.getByRole('button', { name: 'Send message', exact: true }).click()])
    assert.deepEqual(state.lastChat.knowledge_base_uuids, ['kb-1'])
    assert.ok(!state.lastChat.is_first_session && !state.lastChat.run_demo)
    await page.goto(review.baseURL + '/?mode=chat')
    await Promise.all([page.waitForResponse(response => response.url().endsWith('/api/chat')), page.getByRole('button', { name: 'Build a workflow', exact: true }).click()])
    assert.equal(state.lastChat.message, 'Help me turn a recurring task into a workflow.')
    assert.ok(!state.lastChat.run_demo && !state.lastChat.include_onboarding_context)
    assert.equal(await page.getByText('Your document is attached.', { exact: false }).count(), 0)
  }
  assert.deepEqual(review.errors, [])
  console.log('Welcome paths verified at 1440, 768, and 320px.')
} finally { await review.flush(); await review.browser.close() }
