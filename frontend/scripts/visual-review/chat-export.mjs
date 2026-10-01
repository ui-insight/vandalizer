import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { docs } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page, state } = review
page.setDefaultTimeout(15000)
const answer = '# Proposal review\n\nThe sponsor deadline is October 15. [1]\n\n' + Array.from({ length: 8 }, (_, i) => `## Finding ${i + 1}\n\nCheck eligibility, the deadline and the budget justification against the original source before handoff.\n`).join('\n') + '\n| Requirement | Value | Evidence |\n|---|---|---|\n| Deadline | October 15 | Sponsor notice [1] |\n| Budget | $125,000.50 | Check the original |\n\nFinal handoff marker.'
const citation = { document_title: docs[0].title, document_uuid: 'doc-0', kb_title: 'Sponsor policies', kb_uuid: 'kb-1', page: 2, page_end: 3, page_approximate: true, content_preview: 'Applications must arrive by October 15.', url: 'https://example.org/sponsor-notice', source_reference: 'Section 4: Submission', chunk_id: 'reference-1' }
async function send(text) { await page.getByRole('textbox', { name: 'Message input', exact: true }).fill(text); await page.getByRole('button', { name: 'Send message', exact: true }).click(); await page.getByRole('button', { name: 'Stop response', exact: true }).waitFor({ state: 'hidden' }) }
async function exportFile(format) { await page.getByRole('button', { name: 'Export conversation', exact: true }).click(); const promise = page.waitForEvent('download'); await page.getByRole('menuitem', { name: format, exact: true }).click(); return readFile(await (await promise).path(), 'utf8') }
async function shot(id) { await review.capture(id); assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), id + ': overflow'); assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [], id + ': accessibility'); console.log('Captured ' + id) }
try {
  for (const width of [320, 1440]) {
    await page.setViewportSize({ width, height: width === 320 ? 700 : 1000 }); await page.goto(review.baseURL + '/?mode=files')
    for (const name of [docs[0].title, docs[1].title]) await page.getByRole('checkbox', { name: 'Select ' + name, exact: true }).check()
    await page.getByRole('navigation', { name: 'Workspace navigation' }).getByRole('button', { name: 'Chat', exact: true }).click()
    state.chatChunks = [{ kind: 'sources', sources: [citation], content: '' }, { kind: 'text', content: answer }, { kind: 'grounding_warning', unsupported_figures: ['$125,000.50'], content: '' }]
    await send('Review these two documents.'); await page.getByText('Final handoff marker.', { exact: true }).waitFor()
    await page.getByRole('button', { name: 'Deselect ' + docs[0].title, exact: true }).click()
    state.chatChunks = [{ kind: 'text', content: 'Second response with no recorded citations.' }]
    await send('Use only the remaining document.'); await page.getByText('Second response with no recorded citations.', { exact: true }).waitFor(); assert.deepEqual(state.lastChat.document_uuids, ['doc-1'])
    await shot('chat-export-after-scope-change-' + width)
    const text = await exportFile('Text'), csv = await exportFile('CSV')
    for (const output of [text, csv]) {
      for (const expected of ['Document IDs: doc-0, doc-1', 'Document IDs: doc-1', 'Source references', 'p. ~2–3', 'Sponsor policies', citation.url, citation.content_preview, citation.source_reference, 'Unconfirmed figures: $125,000.50', 'No source references were recorded for this answer.', 'Final handoff marker.']) assert.ok(output.includes(expected), expected + ' missing from export')
      assert.equal((output.match(/Source references \(inspect/g) || []).length, 1)
    }
    await page.getByRole('button', { name: 'Export conversation', exact: true }).click()
    const opened = review.context.waitForEvent('page'); await page.getByRole('menuitem', { name: 'PDF', exact: true }).click(); const print = await opened; await print.waitForLoadState()
    assert.equal(await print.getByRole('table').count(), 1); const printed = await print.locator('body').innerText()
    for (const expected of [citation.url, citation.content_preview, 'p. ~2–3', 'Document IDs: doc-0, doc-1', 'Final handoff marker.']) assert.ok(printed.includes(expected), expected + ' missing from print')
    await print.close(); await shot('chat-export-print-return-' + width)
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push('Long cited answer and uncited follow-up after scope change; Text/CSV and print HTML preserve recorded per-turn scope, approximate page range, source title/KB/URL/reference/passage, unconfirmed figures and missing evidence; print renders a real table. Browser print dialog/PDF file generation is not certified by this HTML check.')
} catch (error) { await review.capture('chat-export-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
