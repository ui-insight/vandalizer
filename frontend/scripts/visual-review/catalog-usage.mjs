import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { catalog } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
page.setDefaultTimeout(15000)
const usage = (input, output, output_names = [], notes = []) => ({ input, output, output_names, notes })
const cases = [
  { id: 'files', kind: 'workflow', name: 'Review proposal documents', description: 'Find missing budget explanations.', usage: usage("Select documents or use the active project's files.", "Results from the workflow's output steps.", ['Review findings', 'Source references', 'Final recommendations']) },
  { id: 'text', kind: 'workflow', name: 'Review supplied narrative text', description: 'Turn a draft narrative into a review checklist.', usage: usage('Paste or type the text to process. Selected documents can also be included.', "Results from the workflow's output steps.", ['Checklist'], ['2 fixed documents configured; access is checked at run time.']) },
  { id: 'none', kind: 'workflow', name: 'Generate a review template', description: 'Create a blank proposal-review template.', usage: usage("No manual run input is required by this workflow's configuration.", "Results from the workflow's output steps.", ['Template']) },
  { id: 'extraction', kind: 'search_set', set_type: 'extraction', name: 'Extract funding dates', description: 'Collect the deadlines and award dates described in your documents.', usage: usage('Choose the documents to extract from.', 'Structured values for the configured extraction fields.') },
  { id: 'prompt', kind: 'search_set', set_type: 'prompt', name: 'Rewrite review instructions for an international research collaboration with multiple participating institutions', description: 'Make supplied instructions easier for collaborators to follow.', usage: usage('Review the saved instructions and provide the context they ask for.', 'A generated response from the saved prompt.') },
  { id: 'kb', kind: 'knowledge_base', name: 'Research policy reference', description: 'Answer questions about institutional research policies.', total_sources: 2, total_chunks: 0, kb_status: 'building', usage: usage('Ask a question about the indexed sources.', 'An answer with supporting source references when available.', [], ['No indexed content is available for chat yet.']) },
  { id: 'unknown', kind: 'workflow', name: 'Legacy item without documentation', description: null, usage: undefined },
]
const entries = cases.map(item => ({ ...catalog[0], display_name: item.name, source_uuid: 'fixture-' + item.id, quality_score: null, quality_tier: null, quality_grade: null, ...item }))
await page.route('**/api/verification/verified?*', route => {
  const q = new URL(route.request().url()).searchParams
  const items = entries.filter(e => (!q.get('kind') || e.kind === q.get('kind')) && (!q.get('search') || `${e.name} ${e.description || ''}`.toLowerCase().includes(q.get('search').toLowerCase())))
  return route.fulfill({ json: { items, total: items.length } })
})
async function shot(id) {
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), id + ': overflow')
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [], id + ': accessibility')
  console.log('Captured ' + id)
}
try {
  for (const [width, height] of [[320,568],[768,600],[1440,900]]) {
    await page.setViewportSize({ width, height }); await page.goto(review.baseURL + '/?mode=chat&tab=library')
    await page.getByRole('button', { name: 'Explore', exact: true }).click()
    await page.getByRole('button', { name: cases[0].name, exact: true }).waitFor()
    await shot('catalog-purpose-first-' + width)
    for (const variant of cases) {
      const title = page.getByRole('button', { name: variant.name, exact: true })
      const card = page.getByRole('article').filter({ has: title })
      if (variant.id === 'prompt') await card.getByText('Prompt', { exact: true }).waitFor()
      if (variant.id === 'unknown') await card.getByText('Purpose not described.', { exact: true }).waitFor()
      await title.focus(); await page.keyboard.press('Enter')
      const dialog = page.getByRole('dialog', { name: variant.name, exact: true })
      const summary = dialog.getByRole('region', { name: 'Inputs and output', exact: true })
      await summary.scrollIntoViewIfNeeded()
      if (variant.usage) await summary.getByText(variant.usage.input, { exact: true }).waitFor()
      else await summary.getByText(/Input requirements are not described/).waitFor()
      if (variant.id === 'files') await summary.getByText(/Final recommendations/).waitFor()
      await shot('catalog-usage-' + variant.id + '-' + width)
      const action = dialog.getByRole('button', { name: variant.kind === 'knowledge_base' ? 'Add to My Knowledge Bases' : 'Save to Library', exact: true })
      await action.scrollIntoViewIfNeeded(); assert.equal(await action.isVisible(), true)
      await page.keyboard.press('Escape'); await dialog.waitFor({ state: 'hidden' })
      assert.equal(await title.evaluate(e => e === document.activeElement), true)
    }
    await page.getByRole('button', { name: 'Extractions & prompts', exact: true }).click()
    await page.getByRole('button', { name: cases[4].name, exact: true }).waitFor()
    await page.waitForFunction(() => document.querySelectorAll('article').length === 2)
    assert.equal(await page.getByRole('article').count(), 2)
    await shot('catalog-prompts-filter-' + width)
    await page.goto(review.baseURL + '/?mode=knowledge')
    await page.getByRole('tab', { name: 'Explore', exact: true }).click()
    const kbCard = page.getByRole('article').filter({ has: page.getByRole('button', { name: cases[5].name, exact: true }) })
    await kbCard.getByText('No indexed content is available for chat yet.', { exact: true }).waitFor()
    await kbCard.getByRole('region', { name: 'Inputs and output' }).scrollIntoViewIfNeeded()
    await shot('catalog-knowledge-input-output-' + width)
  }
  review.observations.push('Purpose/type/input/output hierarchy for files/text/no-input workflows, extraction, long prompt, unindexed KB and missing documentation. Complete output labels and fixed-document caveats in details; action reachability and keyboard focus return; honest combined extraction/prompt filter; KB Explore summary. 320/768/1440 synthetic catalog entries; no execution.')
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('catalog-usage-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
