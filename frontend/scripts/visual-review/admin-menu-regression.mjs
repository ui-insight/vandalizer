import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
let role = 'admin', many = false
await page.route('**/api/auth/me', r => r.fulfill({ json: { id: 'reviewer', user_id: 'reviewer', name: 'Alex Morgan', email: 'reviewer@example.test', is_admin: role === 'admin', is_staff: role === 'staff', is_examiner: role === 'examiner', is_support_agent: role === 'admin', current_team: 'team-1', current_team_uuid: 'team-1' } }))
await page.route('**/api/teams/', r => r.fulfill({ json: Array.from({ length: many ? 12 : 1 }, (_, i) => ({ id: `team-${i + 1}`, uuid: `team-${i + 1}`, name: many ? `Research administration and sponsored programs — regional team ${i + 1}` : 'Research office', owner_user_id: role === 'owner' ? 'reviewer' : 'someone-else', role: role === 'owner' ? 'owner' : 'member' })) }))
const stats = { conversations: 18, search_runs: 12, workflows_started: 10, workflows_completed: 7, workflows_failed: 2, tokens_in: 14000, tokens_out: 4000, active_users: 3, active_teams: 1 }
const fixed = { '/api/auth/config': { auth_methods: ['password'], oauth_providers: [], trial_system_enabled: true }, '/api/config/features': { telemetry_collector_enabled: true, m365_enabled: false }, '/api/admin/system/version': { current: '5.0.0', update_available: false }, '/api/admin/catalog/status': { update_available: false }, '/api/admin/telemetry/optin': { show_banner: false }, '/api/admin/usage': stats, '/api/admin/usage/timeseries': { days: [], previous_period: stats }, '/api/admin/users': { items: [], total: 0, capped: false }, '/api/admin/teams': { items: [], total: 0, capped: false } }
await page.route('**/api/**', r => { const p = new URL(r.request().url()).pathname.replace(/\/$/, ''); return p in fixed ? r.fulfill({ json: fixed[p] }) : r.fallback() })
async function capture(id) {
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, `${id}.axe.json`), 'utf8')), [])
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
}
try {
  for (const width of [1440, 768, 390, 320]) {
    role = 'admin'; many = true
    await page.setViewportSize({ width, height: 568 })
    await page.goto(review.baseURL + '/admin?tab=usage')
    const trigger = page.getByRole('button', { name: 'Account menu: Research administration and sponsored programs — regional team 1', exact: true })
    await trigger.click()
    const search = page.getByRole('searchbox', { name: 'Find a team' })
    await search.waitFor()
    const bounds = await page.locator('.account-menu-popup').boundingBox()
    assert.ok(bounds.y >= 0 && bounds.y + bounds.height <= 568, JSON.stringify(bounds))
    await capture('menu-many-' + width)
    await search.fill('regional team 12')
    await page.keyboard.press('ArrowDown')
    assert.match(await page.evaluate(() => document.activeElement.textContent), /regional team 12/)
    await page.keyboard.press('Escape')
    assert.equal(await page.getByRole('menu').count(), 0)
    assert.equal(await trigger.evaluate(el => el === document.activeElement), true)
    await trigger.click()
    await page.keyboard.press('Tab')
    assert.equal(await page.getByRole('menu').count(), 0)
    await trigger.click()
    await page.getByRole('menuitem', { name: 'Logout', exact: true }).scrollIntoViewIfNeeded()
    await capture('menu-actions-' + width)
    await page.keyboard.press('Escape')
  }
  for (const [testRole, label] of [['owner', 'Team Admin'], ['staff', 'Admin'], ['examiner', null]]) {
    role = testRole; many = false
    await page.goto(review.baseURL + '/admin?tab=usage')
    await page.getByRole('button', { name: 'Account menu: Research office' }).click()
    if (label) assert.equal(await page.getByRole('menuitem', { name: label, exact: true }).count(), 1)
    else assert.equal(await page.getByRole('menuitem', { name: /Admin|Analytics/ }).count(), 0)
    await capture('menu-role-' + role)
  }
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  console.log('Dropdown permissions, viewport bounds, search, Escape and Tab passed')
} catch (error) { await review.capture('menu-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
