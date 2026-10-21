import assert from 'node:assert/strict'
import { createReview } from './harness.mjs'

const review = await createReview({ baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5198', output: process.env.REVIEW_OUTPUT || '/private/tmp/vandalizer-home-cleanup' })
const { page, context, state, capture } = review
let first = false
let busy = false
let certificationError = false
const recent = ['Review proposal requirements', 'Summarize an award notice', 'Check the project budget', 'Prepare a compliance review'].map((title, i) => ({ id: `chat-${i}`, type: 'conversation', title, status: 'completed', relative_time: 'Yesterday' }))
await context.route('**/api/config/onboarding-status', route => route.fulfill({ json: {
  has_documents: !first, has_workflows: !first, has_extraction_sets: !first,
  has_conversations: !first, first_session_completed: !first, has_ready_knowledge_base: !first,
  suggestion_pills: [], recent_documents: first ? [] : [{uuid: 'doc-1', title: 'Proposal narrative.pdf'}],
  recent_activity: first ? [] : [...(busy ? [{id: 'run-1', type: 'workflow_run', title: 'Proposal review', status: 'failed', relative_time: 'Just now'}] : []), ...recent], active_alerts: [],
} }))
await context.route('**/api/certification/progress', route => certificationError ? route.fulfill({ status: 503, json: { detail: 'Synthetic unavailable progress' } }) : route.fallback())
await context.route('**/api/reviews?**', route => busy ? route.fulfill({ json: {reviews:[{uuid:'review-1', workflow_name:'Award review', step_name:'Approve report'}]} }) : route.fallback())
async function go() {
  await page.goto(review.baseURL + '/?mode=chat')
  await page.getByRole('heading', {name:'What would you like to get done?'}).waitFor()
}
async function shot(id) {
  await capture(id, 'Synthetic frontend fixtures; no live backend or model execution.')
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'No horizontal page overflow')
}
try {
  await page.setViewportSize({width: 1440, height: 900})
  await go()
  const input = page.getByRole('textbox', {name:'Message input'})
  await input.fill('Keep this draft while I choose a source.')
  const composerNode = await input.elementHandle()
  await shot('home-desktop')
  assert.equal(await page.getByRole('button', {name:'Continue chat:', exact:false}).count(), 3)
  await page.getByText('More recent work (1)', {exact:true}).click()
  assert.equal(await page.getByRole('button', {name:'Continue chat:', exact:false}).count(), 4)
  await page.getByText('More recent work (1)', {exact:true}).click()
  await page.getByRole('button', {name:'Add a source to this conversation: a document, a website or a knowledge base', exact:true}).click()
  const menu = await page.getByRole('menu').boundingBox()
  const inputBox = await input.boundingBox()
  assert(menu.y > inputBox.y, 'Home attachment menu opens below the composer')
  await shot('home-add-menu')
  await page.getByRole('button', {name:'Add a source to this conversation: a document, a website or a knowledge base', exact:true}).click()
  await page.getByText('Choose from your sources', {exact:true}).click()
  await page.getByRole('button', {name:'Select document: Proposal narrative.pdf', exact:true}).click()
  await page.getByText('Documents ready for analysis', {exact:true}).waitFor()
  assert.equal(await composerNode.evaluate(node => node.isConnected), true, 'The composer stays mounted when a source is selected')
  assert.equal(await input.inputValue(), 'Keep this draft while I choose a source.')
  await shot('source-selected-draft-kept')
  state.chatChunks = [{kind:'text',content:'Synthetic answer for the layout regression check.'}]
  await page.getByRole('button', {name:'Send message',exact:true}).click()
  await page.getByText('Synthetic answer for the layout regression check.',{exact:true}).waitFor()
  assert.equal(await input.inputValue(), '')
  assert.deepEqual(state.lastChat.document_uuids, ['doc-1'])
  await shot('conversation-composer')
  await go()
  await page.getByRole('button', {name:'Check a budget',exact:true}).click()
  await page.getByLabel('Recent readable documents').selectOption('doc-1')
  await page.getByRole('button', {name:'Prepare request',exact:true}).click()
  assert.match(await input.inputValue(), /Review the selected budget/)
  assert.equal((await input.inputValue()).match(/Review the selected budget/g).length, 1)
  await shot('task-prepared')
  busy = true; certificationError = true
  await go()
  await page.getByText('Certification progress could not be loaded. Retry to see your saved work.',{exact:true}).waitFor()
  await shot('home-attention-and-certification-error')
  assert.equal(await page.locator('.chat-composer-slot').getByText('Refresh certification progress',{exact:true}).count(),0)
  assert.equal(await page.locator('.home-learning-area').getByRole('button',{name:'Refresh certification progress',exact:true}).count(),1)
  await page.locator('.home-learning-area').scrollIntoViewIfNeeded()
  await shot('home-certification-retry')
  busy = false; certificationError = false
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({width, height:800})
    await go()
    await shot(`home-${width}`)
    assert((await input.boundingBox()).y < 400, 'Composer appears in the first screen')
  }
  first = true
  await page.setViewportSize({width:1440,height:900})
  await go(); await shot('home-first-session')
  await page.setViewportSize({width:390,height:844})
  await go(); await shot('home-first-session-mobile')
  assert.deepEqual([...review.unmatched],[])
  assert.deepEqual(review.errors,[])
  console.log('Home layout, draft/source preservation, sending, task preparation and responsive checks passed.')
} finally {
  await review.flush()
  await review.browser.close()
}
