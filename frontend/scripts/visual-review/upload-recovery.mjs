import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page, state } = review
page.setDefaultTimeout(30000)
let pending = false, ready = false, release, failName = 'failed.txt'
const transfers = [], chats = []
await page.route('**/api/files/upload-policy', route => route.fulfill({ json: { extensions: ['pdf','doc','docx','xls','xlsx','csv','txt','md'], max_size_bytes: 1024 * 1024 } }))
await page.route('**/api/files/upload', async route => {
  const body = route.request().postDataJSON(); transfers.push(body.fileName)
  if (pending) await new Promise(resolve => { release = resolve })
  if (body.fileName === failName) return route.fulfill({ status: 503, json: { detail: 'Transfer temporarily unavailable' } })
  return route.fulfill({ json: { complete: true, uuid: `upload-${body.fileName}`, title: body.fileName } })
})
await page.route('**/api/documents/poll_status?*', route => route.fulfill({ json: ready ? { status: 'SUCCESS', complete: true, raw_text: 'Uploaded policy text', valid: true, processing: false } : { status: 'PROCESSING', complete: false, raw_text: null, valid: false, processing: true } }))
await page.route('**/api/chat', route => {
  chats.push(route.request().postDataJSON())
  return route.fulfill({ contentType: 'application/x-ndjson', body: JSON.stringify({ kind: 'text', content: 'The attached policy is ready for review.' }) + '\n' })
})
async function shot(id, locator) {
  if (locator) await locator.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${id}: overflow`)
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, `${id}.axe.json`), 'utf8')), [], `${id}: accessibility`)
  console.log(`Captured ${id}`)
}
const file = (name, content = 'Test document') => ({ name, mimeType: 'text/plain', buffer: Buffer.from(content) })
try {
  for (const [width, height] of [[320,568],[768,600],[1440,900]]) {
    pending = false; ready = false; failName = 'failed.txt'; state.first = true
    await page.setViewportSize({ width, height })
    await page.goto(review.baseURL + '/?mode=chat')
    const draft = page.getByRole('textbox', { name: 'Message input' })
    await draft.fill('Review the uploaded policy.')
    await page.getByRole('button', { name: 'Add', exact: true }).click()
    await page.getByRole('menu').getByText(/Up to 1 MB per file/).waitFor()
    await shot(`upload-chat-limits-${width}`)
    await page.keyboard.press('Escape')
    const before = transfers.length
    await page.getByLabel('Attach files', { exact: true }).setInputFiles([file('unsupported.png'), file('large.txt', 'x'.repeat(1024 * 1024 + 1)), file('failed.txt'), file('good.txt')])
    await page.getByRole('button', { name: 'Retry upload: failed.txt', exact: true }).waitFor()
    await page.getByRole('button', { name: 'Retry upload: unsupported.png', exact: true }).waitFor()
    await page.getByRole('button', { name: 'Retry upload: large.txt', exact: true }).waitFor()
    assert.deepEqual(transfers.slice(before).sort(), ['failed.txt','good.txt'])
    assert.equal(await draft.inputValue(), 'Review the uploaded policy.')
    await shot(`upload-partial-validation-errors-${width}`, page.getByRole('button', { name: 'Retry upload: large.txt', exact: true }))
    for (const name of ['unsupported.png','large.txt']) await page.getByRole('button', { name: `Dismiss upload: ${name}`, exact: true }).click()
    failName = ''; await page.getByRole('button', { name: 'Retry upload: failed.txt', exact: true }).click()
    await page.getByRole('button', { name: 'Retry upload: failed.txt', exact: true }).waitFor({ state: 'hidden' })
    await page.getByRole('button', { name: 'Deselect failed.txt', exact: true }).waitFor()
    const transferCount = transfers.length
    await page.getByLabel('Attach files', { exact: true }).setInputFiles(file('good.txt'))
    await page.getByText(/good.txt already added/).waitFor()
    assert.equal(transfers.length, transferCount)
    await shot(`upload-retry-and-duplicate-${width}`, draft)
    const chatCount = chats.length
    await draft.press('Enter')
    await page.getByText(/Waiting for good.txt/).waitFor()
    assert.equal(chats.length, chatCount, 'Processing queues the message')
    await shot(`upload-processing-queued-question-${width}`)
    ready = true
    await page.getByText('The attached policy is ready for review.', { exact: true }).waitFor()
    assert.equal(chats.length, chatCount + 1)
    const sent = JSON.stringify(chats.at(-1))
    assert.ok(sent.includes('upload-good.txt') && sent.includes('upload-failed.txt'))
    await shot(`upload-processing-complete-${width}`)
    await draft.fill('Keep this draft during transfer.')
    pending = true
    await page.getByLabel('Attach files', { exact: true }).setInputFiles(file('cancel.txt'))
    await page.getByRole('button', { name: 'Cancel upload: cancel.txt', exact: true }).waitFor()
    await page.waitForFunction(() => document.querySelector('button[aria-label="Send message"]')?.disabled)
    await draft.press('Enter')
    assert.equal(await draft.inputValue(), 'Keep this draft during transfer.')
    await shot(`upload-transfer-blocks-send-${width}`, draft)
    await page.getByRole('button', { name: 'Cancel upload: cancel.txt', exact: true }).click()
    pending = false; release()
    await page.getByText(/Upload canceled. Check Files/).waitFor()
    await page.waitForTimeout(300)
    await draft.press('Enter')
    await page.waitForTimeout(300)
    assert.ok(!JSON.stringify(chats.at(-1)).includes('upload-cancel.txt'), 'A late canceled response cannot attach')
    await shot(`upload-canceled-late-response-${width}`)
    await page.goto(review.baseURL + '/?mode=files')
    await page.getByText(/Up to 1 MB per file/).waitFor()
    await shot(`upload-files-limits-${width}`)
  }
  for (const [width, height] of [[320,568],[1440,900]]) {
  await page.setViewportSize({ width, height })
  await page.goto(review.baseURL + '/?mode=chat')
  ready = false
  const beforeDrop = transfers.length
  const drop = await page.evaluateHandle(() => {
    const data = new DataTransfer()
    data.items.add(new File(['Dropped policy'], 'dropped.txt', { type: 'text/plain' }))
    data.items.add(new File(['Not a supported type'], 'dropped.png', { type: 'image/png' }))
    return data
  })
  await page.getByRole('textbox', { name: 'Message input' }).dispatchEvent('drop', { dataTransfer: drop })
  await page.getByRole('button', { name: 'Deselect dropped.txt', exact: true }).waitFor()
  await page.getByRole('button', { name: 'Retry upload: dropped.png', exact: true }).waitFor()
  assert.deepEqual(transfers.slice(beforeDrop), ['dropped.txt'])
  await shot(`upload-drag-drop-shared-validation-${width}`)
  await page.getByRole('button', { name: 'Deselect dropped.txt', exact: true }).click()
  ready = true
  await page.waitForTimeout(2800)
  assert.equal(await page.getByRole('button', { name: 'Deselect dropped.txt', exact: true }).count(), 0)
  await page.getByRole('textbox', { name: 'Message input' }).fill('Continue without the removed attachment.')
  await page.getByRole('textbox', { name: 'Message input' }).press('Enter')
  await page.getByText('The attached policy is ready for review.', { exact: true }).waitFor()
  assert.ok(!JSON.stringify(chats.at(-1)).includes('upload-dropped.txt'))
  await shot(`upload-removed-during-processing-${width}`)
  }
  review.observations.push('Runtime size/type policy shown in Files and chat. Mixed batch rejects unsupported/oversized files before transfer; valid sibling remains attached; retry transfers only failure; duplicate name is skipped. Processing queues a message until both exact uploaded IDs are ready. Transfer blocks Send/Enter while preserving the draft; cancel ignores late responses. 320/768/1440px synthetic uploads only.')
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('upload-recovery-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
