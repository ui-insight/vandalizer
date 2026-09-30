import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page, state } = review
page.setDefaultTimeout(10000)
let sourceStatus = 404, extractionFailed = false, retryFails = false, retriedDocuments = []
await page.route('**/api/files/download?*', route => route.fulfill({ status: sourceStatus, contentType: 'text/plain', body: sourceStatus === 200 ? 'Source recovered' : '' }))
await page.route('**/api/documents/poll_status?*', route => route.fulfill({ json: extractionFailed ? { complete: true, status: 'error', error_message: 'Text extraction failed. Try processing this source again.', raw_text: '' } : { complete: true, status: 'SUCCESS', raw_text: 'Synthetic review document. Proposal due October 15. Budget requires justification.', valid: true, processing: false } }))
await page.route('**/api/documents/doc-0/retry-extraction', route => { retriedDocuments.push('doc-0'); if (retryFails) return route.fulfill({status:503,json:{detail:'Extraction queue unavailable'}}); extractionFailed=false; return route.fulfill({json:{ok:true}}) })
await review.context.route('https://example.org/published-policy', route => route.fulfill({contentType:'text/plain',body:'Synthetic published policy'}))
const preview = 'Proposal due October 15. Include a budget justification.'
async function shot(id, target) {
  if (target) await target.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${id}: overflow`)
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, `${id}.axe.json`), 'utf8')), [], `${id}: accessibility`)
  console.log(`Captured ${id}`)
}
async function send(text) { await page.getByRole('textbox', { name: 'Message input' }).fill(text); await page.getByRole('button', { name: 'Send message' }).click() }
try {
  for (const [width,height] of [[320,568],[768,600],[1440,900]]) {
    await page.setViewportSize({width,height})
    sourceStatus = 404; extractionFailed = false; retryFails = false; retriedDocuments = []
    await page.goto(review.baseURL + '/?mode=knowledge')
    await page.getByRole('tabpanel', { name: 'Mine' }).getByRole('button', { name: 'Chat', exact: true }).click()
    state.chatChunks = [{ kind: 'sources', content: '', sources: [{ document_title: 'Proposal narrative.pdf', document_uuid: 'doc-0', chunk_id: 'chunk-1', page: 2, page_approximate: true, kb_uuid: 'kb-1', kb_title: 'Research administration policies', content_preview: preview }, { document_title: 'Archived guidance', chunk_id: 'chunk-missing' }, { document_title: 'Published policy', chunk_id: 'chunk-url', url: 'https://example.org/published-policy' }] }, { kind: 'text', content: 'The proposal is due October 15. Include a budget justification.' }]
    await send('When is the proposal due?')
    const citation = page.getByRole('button', { name: /Proposal narrative.pdf · p. ~2 · Research/ })
    await citation.waitFor()
    const draft = page.getByRole('textbox', { name: 'Message input' })
    await draft.fill('Keep this follow-up draft')
    await page.getByRole('button', { name: 'Library', exact: true }).click()
    await page.getByRole('button', { name: 'Assistant', exact: true }).click()
    assert.equal(await draft.inputValue(), 'Keep this follow-up draft')
    await citation.focus(); await page.keyboard.press('Enter')
    assert.equal(await page.getByRole('menuitem', { name: 'Preview', exact: true }).evaluate(e => e === document.activeElement), true)
    await page.keyboard.press('Enter')
    await page.getByText(preview, {exact:false}).waitFor()
    await shot(`chat-source-preview-${width}`, citation)
    await citation.click(); await page.keyboard.press('ArrowDown')
    assert.equal(await page.getByRole('menuitem', { name: 'Open at p. ~2', exact: true }).evaluate(e => e === document.activeElement), true)
    const beforeDocument = await page.getByRole('region',{name:'Conversation',exact:true}).evaluate(e=>e.scrollTop)
    await page.keyboard.press('Enter')
    await page.getByText('Source unavailable', {exact:true}).waitFor()
    await shot(`chat-source-missing-${width}`, page.getByRole('button', { name: 'Retry source', exact: true }))
    sourceStatus = 403; await page.getByRole('button', { name: 'Retry source', exact: true }).click()
    await page.getByText(/not accessible with your current account/).waitFor()
    await shot(`chat-source-inaccessible-${width}`, page.getByRole('button', { name: 'Retry source', exact: true }))
    sourceStatus = 200; extractionFailed = true; await page.getByRole('button', { name: 'Retry source', exact: true }).click()
    await page.getByRole('button', { name: 'Retry extraction', exact: true }).waitFor()
    await shot(`chat-source-extraction-failed-${width}`, page.getByRole('button', { name: 'Retry extraction', exact: true }))
    retryFails=true; await page.getByRole('button', { name: 'Retry extraction', exact: true }).click()
    await page.getByText('Extraction queue unavailable', {exact:true}).waitFor()
    await shot(`chat-source-extraction-retry-error-${width}`,page.getByRole('button', { name: 'Retry extraction', exact: true }))
    retryFails=false; await page.getByRole('button', { name: 'Retry extraction', exact: true }).click()
    await page.getByText('Synthetic review document.', {exact:false}).waitFor()
    assert.deepEqual(retriedDocuments,['doc-0','doc-0'])
    await shot(`chat-source-recovered-${width}`, page.getByText('Synthetic review document.', {exact:false}))
    await page.getByRole('navigation', { name: 'Workspace navigation' }).getByRole('button', { name: 'Chat', exact: true }).click()
    assert.equal(await draft.inputValue(), 'Keep this follow-up draft')
    // Closing the citation menu can remove a few pixels from the scroll extent.
    // Allow less than half a text line, while rejecting a jump to another passage.
    const restoredPosition=await page.getByRole('region',{name:'Conversation',exact:true}).evaluate(e=>e.scrollTop)
    assert.ok(Math.abs(restoredPosition-beforeDocument)<=8, `Source return position changed: ${beforeDocument} to ${restoredPosition}`)
    const link=page.getByRole('link',{name:'Published policy',exact:true})
    assert.equal(await link.getAttribute('href'),'https://example.org/published-policy')
    const [external]=await Promise.all([review.context.waitForEvent('page'),link.click()])
    await external.waitForLoadState(); assert.equal(external.url(),'https://example.org/published-policy'); await external.close()
    await page.getByRole('button', { name: 'Archived guidance', exact: true }).click()
    await page.getByText('No preview was saved for this source.', {exact:false}).waitFor()
    await shot(`chat-source-unlinked-${width}`, page.getByText('No preview was saved for this source.', {exact:false}))
    await send('Continue with the same knowledge-base scope')
    await page.getByRole('button',{name:'Copy message',exact:true}).nth(1).waitFor()
    assert.deepEqual(state.lastChat.knowledge_base_uuids, ['kb-1'])
    assert.deepEqual(state.lastChat.document_uuids, [])

    await page.goto(review.baseURL + '/?mode=chat')
    const markdown = '# Review findings\n\n' + Array.from({length:12}, (_,i) => `## Finding ${i+1}\n\nA detailed explanation with **emphasis**, a [source link](https://example.org/reference), and supporting context.\n\n- Check the due date\n- Confirm the requirements\n`).join('\n') + '\n| Requirement | Responsible office | Supporting document | Due date | Status |\n|---|---|---|---|---|\n| Eligibility | Research administration | Sponsor requirements | October 15 | Needs review |\n\n```json\n' + JSON.stringify({ reference: 'long_identifier_'.repeat(16), ready: true }, null, 2) + '\n```\n\nFinal review marker.'
    await page.evaluate(markdown => {
      const original = window.fetch.bind(window)
      window.fetch = (input, init) => {
        if (new URL(typeof input === 'string' ? input : input.url, location.href).pathname !== '/api/chat') return original(input, init)
        const body = new ReadableStream({ start(controller) {
          const emit = text => controller.enqueue(new TextEncoder().encode(JSON.stringify({kind:'text',content:text})+'\n'))
          emit(markdown); window.appendReviewText = emit; window.finishReviewText = () => controller.close()
          init.signal.addEventListener('abort', () => controller.error(new DOMException('Stopped','AbortError')))
        } })
        return Promise.resolve(new Response(body, {headers:{'Content-Type':'application/x-ndjson','X-Conversation-UUID':'reading-review'}}))
      }
    }, markdown)
    await send('Show a detailed review')
    await page.getByText('Final review marker.', {exact:true}).waitFor()
    const conversation = page.getByRole('region', {name:'Conversation',exact:true})
    await conversation.evaluate(e => { e.scrollTop = 100 })
    const position = await conversation.evaluate(e => e.scrollTop)
    await page.evaluate(() => window.appendReviewText('\n\nNew review information arrived.'))
    await page.getByText('New review information arrived.', {exact:true}).waitFor()
    assert.equal(await conversation.evaluate(e => e.scrollTop), position)
    await shot(`chat-reading-position-${width}`)
    await page.getByRole('button', {name:'Scroll to bottom',exact:true}).click()
    await page.waitForTimeout(700)
    console.log('Bottom metrics', await conversation.evaluate(e => ({ height:e.scrollHeight, top:e.scrollTop, client:e.clientHeight, width:e.scrollWidth, left:e.scrollLeft, clientWidth:e.clientWidth })))
    assert.ok(await conversation.evaluate(e => e.scrollHeight-e.scrollTop-e.clientHeight < 5))
    await page.evaluate(() => window.finishReviewText())
    const table = page.getByRole('region', {name:'Response table',exact:true})
    await table.focus(); await page.keyboard.press('ArrowRight')
    await shot(`chat-long-table-${width}`,table)
    const code = page.getByLabel('Code block',{exact:true}); await code.focus(); await page.keyboard.press('ArrowRight')
    await shot(`chat-long-code-${width}`,code)
    await page.evaluate(() => { Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:()=>Promise.reject(new Error('Denied'))}}) })
    await page.getByRole('button', {name:'Copy message',exact:true}).click()
    await page.getByText(/Could not copy the response/).waitFor()
    await shot(`chat-copy-error-${width}`)
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch(error) { console.log('Overflow', await page.evaluate(() => [...document.querySelectorAll('*')].filter(e=>e.clientWidth>0 && e.scrollWidth>e.clientWidth+1).map(e=>({tag:e.tagName,cls:e.className,width:e.clientWidth,scroll:e.scrollWidth,left:e.scrollLeft})).slice(0,25))); await review.capture('chat-reading-blocked',String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
