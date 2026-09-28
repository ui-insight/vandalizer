import assert from 'node:assert/strict'
import { createReview } from './harness.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT || '../artifacts/visual-review/journeys', baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5182' })
const { page, state } = review
page.setDefaultTimeout(8000)
async function go(path) { await page.goto(review.baseURL + path); await page.getByRole('main').waitFor(); await page.waitForTimeout(400) }
async function capture(id) {
  await review.capture(id)
  const width = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }))
  assert.ok(width.document <= width.viewport, `${id}: horizontal overflow`)
}
async function send(message) { await page.getByRole('textbox', { name: 'Message input' }).fill(message); await page.getByRole('button', { name: 'Send message' }).click() }
try {
  await go('/?mode=automations')
  await page.getByRole('button', { name: 'Open automation: Review incoming proposals', exact: true }).click()
  state.failAutomationSave = true
  state.automationSaveDelay = 800
  await page.getByRole('textbox', { name: 'Automation description' }).fill('Keep this edited description')
  await page.getByRole('textbox', { name: 'Automation description' }).press('Tab')
  await capture('automation-saving')
  await page.getByRole('button', { name: 'Retry save', exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Run now', exact: true }).isDisabled(), true)
  await capture('automation-save-failed')
  state.failAutomationSave = false
  state.automationSaveDelay = 0
  await page.getByRole('button', { name: 'Retry save', exact: true }).click()
  await page.getByText('All changes saved automatically', { exact: true }).waitFor()
  assert.equal(state.savedAutomation.description, 'Keep this edited description')
  await capture('automation-save-retried')
  await page.getByRole('button', { name: 'Close automation', exact: true }).click()
  await page.getByRole('button', { name: 'Open automation: Review incoming proposals', exact: true }).click()
  assert.equal(await page.getByRole('textbox', { name: 'Automation description' }).inputValue(), 'Keep this edited description')
  state.savedAutomation = undefined

  await go('/?mode=files')
  await page.getByRole('checkbox', { name: 'Select Proposal narrative.pdf', exact: true }).check()
  await page.getByRole('checkbox', { name: 'Select Budget justification.docx', exact: true }).check()
  state.failDelete = 'doc-1'
  await page.getByRole('button', { name: 'Delete', exact: true }).click()
  await capture('files-delete-confirmation')
  await page.getByRole('dialog').getByRole('button', { name: 'Delete', exact: true }).click()
  await page.getByText(/Failed items remain selected for retry/).waitFor()
  assert.equal(await page.getByRole('checkbox', { name: 'Select Budget justification.docx', exact: true }).isChecked(), true)
  await page.getByRole('checkbox', { name: 'Select Proposal narrative.pdf', exact: true }).waitFor({ state: 'hidden' })
  await capture('files-delete-partial-failure')
  state.failDelete = null
  await page.getByRole('button', { name: 'Delete', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Delete', exact: true }).click()
  await page.getByRole('checkbox', { name: 'Select Budget justification.docx', exact: true }).waitFor({ state: 'hidden' })
  assert.deepEqual(state.deleteRequests, ['doc-0', 'doc-1', 'doc-1'])
  await capture('files-delete-retried')
  state.deletedDocs = []

  state.validationQueries = true
  await go('/?mode=knowledge')
  await page.getByRole('button', { name: 'Edit', exact: true }).click()
  await page.getByRole('tab', { name: 'Validation', exact: true }).click()
  await page.getByRole('button', { name: 'Run 3 questions', exact: true }).click()
  await page.getByRole('tab', { name: 'Sources (3)', exact: true }).click()
  await capture('validation-running-sources')
  await page.getByRole('tab', { name: 'Validation', exact: true }).click()
  await page.getByRole('button', { name: 'CSV', exact: true }).waitFor({ timeout: 12000 })
  await page.getByRole('button', { name: /When is the proposal due/ }).click()
  await page.getByText('Expected answer', { exact: true }).waitFor()
  await capture('validation-question-detail')
  await page.setViewportSize({ width: 390, height: 700 })
  await page.getByText('Expected answer', { exact: true }).scrollIntoViewIfNeeded()
  await capture('validation-question-detail-mobile')
  state.validationQueries = false
  state.validated = false

  await go('/?mode=chat&tab=library')
  await page.getByLabel('Filter library by type').selectOption('prompt')
  assert.equal(await page.getByRole('button', { name: 'Open Proposal readiness review', exact: true }).count(), 0)
  await page.getByRole('button', { name: 'Open Summarize award conditions', exact: true }).waitFor()
  await capture('library-type-filter-mobile')
  await page.getByLabel('Filter library by type').selectOption('all')
  await page.getByRole('button', { name: 'View: All items · Change', exact: true }).click()
  await page.getByText('How organization works', { exact: true }).click()
  await capture('library-views-mobile')
  await page.getByRole('button', { name: /^Favorites/ }).focus()
  await page.keyboard.press('Enter')
  await page.getByRole('button', { name: 'View: Favorites · Change', exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Open Proposal readiness review', exact: true }).count(), 0)
  await capture('library-favorites-mobile')

  await go('/?mode=knowledge')
  await page.getByRole('tabpanel', { name: 'My KBs' }).getByRole('button', { name: 'Chat', exact: true }).click()
  const preview = 'Proposal due October 15. Include a budget justification.'
  state.chatChunks = [{ kind: 'sources', content: '', sources: [{ document_title: 'Proposal narrative.pdf', document_uuid: 'doc-0', chunk_id: 'chunk-1', page: 2, kb_uuid: 'kb-1', kb_title: 'Research administration policies', content_preview: preview }] }, { kind: 'text', content: 'The proposal is due October 15. Include a budget justification.' }]
  await send('When is the proposal due?')
  const citation = page.getByRole('button', { name: /Proposal narrative.pdf · p. 2 · Research/ })
  await citation.click()
  await capture('chat-citation-menu-mobile')
  await page.getByRole('menuitem', { name: 'Preview', exact: true }).click()
  await page.getByText(preview, { exact: false }).waitFor()
  await capture('chat-citation-preview-mobile')
  assert.deepEqual(state.lastChat.knowledge_base_uuids, ['kb-1'])

  await go('/?mode=files')
  await page.getByRole('checkbox', { name: 'Select Proposal narrative.pdf', exact: true }).check()
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 700 })
    await capture(`files-bulk-actions-${width}`)
    const folderName = await page.getByRole('row', { name: 'Folder: FY2027 proposals', exact: true }).locator('.file-name').boundingBox()
    assert.ok(folderName && folderName.width >= 100 && folderName.height < 60, 'Folder badges must not squeeze the name into a few characters')
    for (const label of ['Download', 'Move', 'Delete', 'Clear selection']) {
      const box = await page.getByRole('group', { name: 'Selected files and bulk actions' }).getByRole('button', { name: label, exact: true }).boundingBox()
      assert.ok(box && box.x >= 0 && box.x + box.width <= width, `${label} must fit on ${width}px`)
    }
  }
  await page.getByRole('button', { name: 'Clear selection', exact: true }).click()
  assert.equal(await page.getByRole('checkbox', { name: 'Select Proposal narrative.pdf', exact: true }).isChecked(), false)

  state.first = true
  await go('/?mode=chat')
  await page.getByLabel('Attach files').setInputFiles({ name: 'Review sample.txt', mimeType: 'text/plain', buffer: Buffer.from('Proposal due October 15.') })
  await page.getByText('2. Ask a question', { exact: true }).waitFor()
  await capture('onboarding-document-attached-mobile')
  state.chatChunks = [{ kind: 'sources', content: '', sources: [{ document_title: 'Review sample.txt', document_uuid: 'doc-upload', chunk_id: 'first-task-chunk', content_preview: 'Proposal due October 15.' }] }, { kind: 'text', content: 'The deadline in your document is October 15.' }]
  await send('What are the key deadlines?')
  await page.getByText('3. Check the evidence', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Review sample.txt', exact: true }).click()
  await page.getByRole('menuitem', { name: 'Preview', exact: true }).click()
  await page.getByText('Proposal due October 15.', { exact: false }).waitFor()
  assert.deepEqual(state.lastChat.document_uuids, ['doc-upload'])
  await capture('onboarding-evidence-checked-mobile')
  state.first = false

  await go('/?mode=chat')
  state.chatChunks = [{ kind: 'tool_call', content: '', tool_name: 'create_workflow', tool_call_id: 'cancel-tool', args: { name: 'Cancel review' } }, { kind: 'tool_result', tool_name: 'create_workflow', tool_call_id: 'cancel-tool', content: { needs_confirmation: true, preview: 'Create Cancel review with one review step.' } }, { kind: 'text', content: 'Review the proposed workflow before creating it.' }]
  await send('Prepare a workflow.')
  await page.getByRole('button', { name: 'Cancel action', exact: true }).waitFor()
  await capture('agent-approval-mobile')
  state.chatChunks = [{ kind: 'text', content: 'Canceled. No workflow was created.' }]
  await page.getByRole('button', { name: 'Cancel action', exact: true }).click()
  await page.getByText('Canceled. No workflow was created.', { exact: true }).waitFor()
  assert.equal(state.lastChat.message, 'No, cancel that')
  assert.equal(await page.getByRole('button', { name: 'Create workflow', exact: true }).count(), 0)
  assert.equal(await page.getByRole('button', { name: 'Cancel action', exact: true }).count(), 0)
  await capture('agent-canceled-mobile')
} catch (error) {
  review.errors.push(String(error))
  await review.capture('journeys-blocked', String(error))
  process.exitCode = 1
} finally {
  await review.flush()
  await review.browser.close()
  if (review.unmatched.size || review.errors.length) process.exitCode = 1
  console.log(JSON.stringify({ captures: review.captures.length, errors: review.errors, unmatched: [...review.unmatched] }, null, 2))
}
