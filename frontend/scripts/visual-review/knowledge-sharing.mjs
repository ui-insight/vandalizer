import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { kb, stamp } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page, state } = review
page.setDefaultTimeout(15000)
let rows, current, failList, failShare, shareWrites, detailReads, listReads
const variants = [
  { uuid: 'empty', title: 'Empty knowledge base', status: 'empty', total_sources: 0, sources_ready: 0, sources_failed: 0, total_chunks: 0, sources: [] },
  { uuid: 'building', title: 'Building knowledge base', status: 'building', sources_failed: 0, sources_ready: 0, total_chunks: 0, sources: kb.sources.map(s => ({ ...s, status: 'processing', chunk_count: 0, error_message: null })) },
  { uuid: 'partial', title: 'Partially ready knowledge base' },
  { uuid: 'failed', title: 'All sources failed', status: 'error', sources_ready: 0, sources_failed: 3, total_chunks: 0, sources: kb.sources.map(s => ({ ...s, status: 'error', chunk_count: 0, error_message: 'Source unavailable. Please retry.' })) },
  { uuid: 'validated', title: 'Validated knowledge base', sources_ready: 3, sources_failed: 0, last_validation_score: .9, last_validation_baseline_score: .4, last_validation_lift: .5, last_validated_at: stamp, sources: kb.sources.map(s => ({ ...s, status: 'ready', error_message: null })) },
]
await page.route('**/api/knowledge/list/v2*', route => {
  const q = new URL(route.request().url()).searchParams; listReads.push(Object.fromEntries(q))
  if (failList) return route.fulfill({ status: 503, json: { detail: 'Knowledge list temporarily unavailable.' } })
  const filtered = rows.filter(k => !q.get('search') || k.title.toLowerCase().includes(q.get('search').toLowerCase()))
  const skip = Number(q.get('skip') || 0), limit = Number(q.get('limit') || 50)
  return route.fulfill({ json: { items: filtered.slice(skip, skip + limit), total: filtered.length } })
})
await page.route('**/api/knowledge/*', route => {
  const id = new URL(route.request().url()).pathname.split('/').pop()
  if (id === 'list') return route.fulfill({ json: rows })
  const found = rows.find(k => k.uuid === id) || (id === 'canonical' ? current : null)
  if (!found) return route.fallback()
  detailReads.push(id)
  return route.fulfill({ json: found })
})
await page.route('**/api/knowledge/canonical/share', route => {
  const body = route.request().postDataJSON(); shareWrites.push(body)
  // Apply before dropping the acknowledgement: retry must send true again.
  current.shared_with_team = body.shared_with_team
  return failShare ? route.fulfill({ status: 503, json: { detail: 'The sharing response was lost. Retry to confirm.' } }) : route.fulfill({ json: { ok: true, shared_with_team: current.shared_with_team } })
})
async function shot(id, locator) {
  if (locator) await locator.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), id + ': overflow')
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [], id + ': accessibility')
  console.log('Captured ' + id)
}
async function open() { await page.goto(review.baseURL + '/?mode=knowledge'); await page.getByRole('tab', { name: 'My KBs', exact: true }).waitFor() }
const back = () => page.getByRole('button', { name: 'Back to knowledge bases', exact: true }).click()
try {
  for (const [width, height] of [[320,568],[768,700],[1440,900]]) {
    await page.setViewportSize({ width, height })
    failList = true; failShare = true; shareWrites = []; detailReads = []; listReads = []
    rows = variants.map(v => ({ ...structuredClone(kb), ...v }))
    await open(); await page.getByRole('button', { name: 'Retry loading knowledge bases' }).waitFor()
    await shot('knowledge-list-error-' + width)
    failList = false; await page.getByRole('button', { name: 'Retry loading knowledge bases' }).click()
    await page.getByRole('button', { name: variants[0].title, exact: true }).waitFor()
    await shot('knowledge-availability-list-' + width)
    for (const variant of variants) {
      const card = page.getByRole('article').filter({ has: page.getByRole('button', { name: variant.title, exact: true }) })
      if (['empty', 'building', 'failed'].includes(variant.uuid)) assert.equal(await card.getByRole('button', { name: 'Chat', exact: true }).count(), 0)
      await card.getByRole('button', { name: variant.title, exact: true }).click()
      await page.getByRole('tab', { name: /^Sources \(/ }).waitFor()
      await shot('knowledge-' + variant.uuid + '-' + width, page.locator('.kb-health-summary'))
      await back()
    }
    current = { ...structuredClone(kb), uuid: 'canonical', title: 'Shared research policies', team_id: 'team-1' }
    rows = [current]; await open()
    await page.getByRole('button', { name: current.title, exact: true }).click()
    await page.getByText('Manage knowledge base', { exact: true }).click()
    await page.getByRole('switch', { name: 'Share with Team', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: 'Share with team', exact: true })
    await dialog.getByLabel('Add a note (optional)').fill('Please review these sources before running the proposal checks.')
    await dialog.getByRole('button', { name: 'Share with Research office', exact: true }).click()
    await dialog.getByRole('alert').waitFor(); await shot('knowledge-share-response-lost-' + width)
    assert.equal(await dialog.getByLabel('Add a note (optional)').inputValue(), 'Please review these sources before running the proposal checks.')
    assert.equal(shareWrites.length, 1); assert.equal(shareWrites[0].shared_with_team, true)
    failShare = false; await dialog.getByRole('button', { name: 'Share with Research office', exact: true }).click()
    await dialog.waitFor({ state: 'hidden' }); await page.getByRole('switch', { name: 'Shared with Team', exact: true }).waitFor()
    assert.deepEqual(shareWrites[1], shareWrites[0]); await shot('knowledge-shared-' + width, page.getByRole('switch', { name: 'Shared with Team', exact: true }))
    await page.getByRole('switch', { name: 'Shared with Team', exact: true }).click()
    await page.getByRole('switch', { name: 'Share with Team', exact: true }).waitFor()
    assert.equal(shareWrites[2].shared_with_team, false)
    current.team_owned = true; current.shared_with_team = true; await open()
    await page.getByRole('button', { name: current.title, exact: true }).click()
    await page.getByText('Manage knowledge base', { exact: true }).click()
    assert.equal(await page.getByRole('switch', { name: 'Team owned', exact: true }).isDisabled(), true)
    await shot('knowledge-team-owned-' + width, page.getByRole('switch', { name: 'Team owned', exact: true }))
    current.can_manage = false
    rows = [{ ...current, uuid: 'bookmark-view', is_reference: true, reference_uuid: 'bookmark-1', source_kb_uuid: 'canonical' }]
    await open(); await page.getByRole('button', { name: current.title, exact: true }).waitFor()
    assert.equal(await page.getByRole('button', { name: 'Edit', exact: true }).count(), 0)
    await shot('knowledge-readonly-bookmark-' + width)
    await page.getByRole('button', { name: current.title, exact: true }).click()
    await page.getByRole('tab', { name: /^Sources \(/ }).waitFor()
    assert.equal(detailReads.at(-1), 'canonical')
    assert.equal(await page.getByRole('button', { name: 'Edit title', exact: true }).count(), 0)
    await shot('knowledge-readonly-detail-' + width, page.locator('.kb-health-summary'))
    await back(); await page.getByRole('tabpanel', { name: 'My KBs' }).getByRole('button', { name: 'Chat', exact: true }).click()
    await page.getByRole('textbox', { name: 'Message input' }).fill('Use this knowledge base')
    await page.getByRole('button', { name: 'Send message', exact: true }).click()
    await page.getByRole('button', { name: 'Copy message', exact: true }).first().waitFor()
    assert.deepEqual(state.lastChat.knowledge_base_uuids, ['canonical'])
    await shot('knowledge-bookmark-chat-' + width)
  }
  // Exercise more than one server page: the last KB remains searchable and sortable.
  rows = Array.from({ length: 205 }, (_, i) => ({ ...structuredClone(kb), uuid: 'many-' + i, title: i === 204 ? 'A later-page knowledge base' : 'Research ' + String(i).padStart(3, '0') }))
  listReads = []; await open()
  await page.getByRole('button', { name: 'A later-page knowledge base', exact: true }).waitFor()
  assert.ok(listReads.some(q => q.skip === '200'))
  await page.getByRole('combobox', { name: 'Sort knowledge bases' }).selectOption('name')
  assert.equal(await page.getByRole('article').first().getByRole('button', { name: 'A later-page knowledge base', exact: true }).count(), 1)
  await shot('knowledge-later-page-sort-1440')
  review.observations.push('List retry, five availability states, explicit share/unshare and lost-acknowledgement retry with preserved note, team ownership guard, read-only canonical bookmark detail/chat, 205-row pagination and sort. Synthetic APIs; no live team notification, ingestion, or model execution.')
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('knowledge-sharing-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
