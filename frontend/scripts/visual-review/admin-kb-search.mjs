import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'

const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
const requests = []
let records, failSearch = false, failRename = false
const fixed = {
  '/api/auth/me': { id: 'reviewer', user_id: 'reviewer', name: 'Alex Morgan', email: 'reviewer@example.test', is_admin: true, is_staff: true, current_team: 'team-1' },
  '/api/auth/config': { auth_methods: ['password'], oauth_providers: [], trial_system_enabled: false },
  '/api/admin/system/version': { current: '5.0.0', update_available: false },
  '/api/admin/catalog/status': { update_available: false },
  '/api/admin/telemetry/optin': { show_banner: false },
}
await page.route('**/api/**', async route => {
  const url = new URL(route.request().url()), path = url.pathname.replace(/\/$/, '')
  if (path in fixed) return route.fulfill({ json: fixed[path] })
  if (path === '/api/admin/knowledge-bases') {
    const search = url.searchParams.get('search') || '', status = url.searchParams.get('status') || '', sort = url.searchParams.get('sort') || 'created', offset = Number(url.searchParams.get('offset') || 0), limit = Number(url.searchParams.get('limit') || 1000)
    requests.push({ search, status, sort, offset, limit })
    if (failSearch) { failSearch = false; return route.fulfill({ status: 503, json: { detail: 'Search temporarily unavailable' } }) }
    const matching = records.filter(kb => (!status || kb.status === status) && (!search || [kb.title, kb.owner_email, kb.team_name, ...kb.tags].some(value => value?.toLowerCase().includes(search.toLowerCase()))))
    matching.sort(sort === 'updated' ? (a, b) => b.updated_at.localeCompare(a.updated_at) || a.uuid.localeCompare(b.uuid) : (a, b) => a.title.localeCompare(b.title) || a.uuid.localeCompare(b.uuid))
    return route.fulfill({ json: { total: matching.length, knowledge_bases: matching.slice(offset, offset + limit) } })
  }
  if (path === '/api/knowledge/kb-502/update') {
    if (failRename) { failRename = false; return route.fulfill({ status: 503, json: { detail: 'Rename temporarily unavailable' } }) }
    records[502].title = route.request().postDataJSON().title
    return route.fulfill({ json: records[502] })
  }
  return route.fallback()
})
async function capture(id) {
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, `${id}.axe.json`), 'utf8')), [])
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
}
async function search(value) {
  await page.getByRole('textbox', { name: 'Search knowledge bases', exact: true }).fill(value)
  await page.getByRole('button', { name: 'Search all records', exact: true }).click()
}
try {
  for (const width of [1440, 320]) {
    records = Array.from({ length: 503 }, (_, i) => ({ uuid: `kb-${i}`, title: `Policy ${String(i).padStart(4, '0')}`, status: i === 502 ? 'error' : 'ready', tags: i === 502 ? ['v2026.10'] : [], verified: false, total_sources: 2, total_chunks: 40, owner_id: 'owner', owner_email: i === 502 ? 'late.owner@example.test' : 'owner@example.test', team_id: 'team-1', team_name: i === 502 ? 'Regional research office' : 'Research office', created_at: '2026-10-01T12:00:00Z', updated_at: i === 502 ? '2026-10-08T12:00:00Z' : '2026-10-01T12:00:00Z' }))
    await page.setViewportSize({ width, height: 900 })
    await page.goto(review.baseURL + '/admin?tab=knowledgebases')
    await page.getByText('Policy 0099', { exact: true }).waitFor()
    assert.equal(await page.getByText('Policy 0502', { exact: true }).count(), 0)
    await page.getByRole('button', { name: 'Next page', exact: true }).click()
    await page.getByText('Policy 0100', { exact: true }).waitFor()
    for (const query of ['late.owner', 'regional research', 'v2026.10']) {
      await search(query)
      await page.getByText('Policy 0502', { exact: true }).waitFor()
      assert.ok(requests.some(request => request.search === query && request.offset === 0))
    }
    await page.getByRole('combobox', { name: 'Knowledge base status' }).selectOption('ready')
    await page.getByText('No knowledge bases match these filters.', { exact: true }).waitFor()
    await page.getByRole('combobox', { name: 'Knowledge base status' }).selectOption('error')
    await page.getByText('Policy 0502', { exact: true }).waitFor()
    await page.getByRole('button', { name: 'Updated', exact: true }).click()
    await page.getByText('Policy 0502', { exact: true }).waitFor()
    await capture(`kb-global-match-${width}`)
    await page.getByRole('button', { name: 'Rename Policy 0502', exact: true }).click()
    const title = page.getByRole('textbox', { name: 'Knowledge base title', exact: true })
    await title.fill('Regional policy — revised')
    failRename = true
    await page.getByRole('button', { name: 'Save title for Policy 0502', exact: true }).click()
    await page.getByText('Rename temporarily unavailable', { exact: true }).waitFor()
    assert.equal(await title.inputValue(), 'Regional policy — revised')
    if (width === 320) {
      const region = await page.getByRole('region', { name: 'Knowledge base inventory — scroll for more columns' }).boundingBox()
      for (const control of [title, page.getByText('Rename temporarily unavailable', { exact: true }), page.getByRole('button', { name: 'Save title for Policy 0502', exact: true }), page.getByRole('button', { name: 'Cancel rename', exact: true })]) {
        const bounds = await control.boundingBox()
        assert.ok(bounds.x >= region.x - 1 && bounds.x + bounds.width <= region.x + region.width + 1, `Rename feedback/control clipped: ${JSON.stringify(bounds)}`)
      }
    }
    await capture(`kb-rename-retry-${width}`)
    await page.getByRole('button', { name: 'Save title for Policy 0502', exact: true }).click()
    const renamed = page.getByRole('button', { name: 'Rename Regional policy — revised', exact: true })
    await renamed.waitFor()
    assert.ok(await renamed.evaluate(el => el === document.activeElement))
    failSearch = true
    await search('no-match')
    await page.getByText('Search temporarily unavailable', { exact: true }).waitFor()
    await capture(`kb-search-retry-${width}`)
    await page.getByRole('button', { name: 'Refresh', exact: true }).click()
    await page.getByText('No knowledge bases match these filters.', { exact: true }).waitFor()
    await capture(`kb-global-empty-${width}`)
  }
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  review.observations.push({ requests, evidence: 'Synthetic 503-record inventory. Search beyond initial pages, global status/sort, rename draft/focus recovery, search retry, narrow layout and axe checks.' })
  console.log('Full-inventory KB search, status, sorting and recovery passed at desktop and mobile widths')
} finally {
  await review.flush()
  await review.browser.close()
}
