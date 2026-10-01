import assert from 'node:assert/strict'
import { expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { items as fixtures } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
page.setDefaultTimeout(15000)
let personal, team, failClone, shareMode, clones, shares
await page.route('**/api/library?*', r => r.fulfill({ json: [{ id: 'library-1', scope: 'personal', title: 'My library', owner_user_id: 'reviewer' }, { id: 'team-library', scope: 'team', team_id: 'team-1', title: 'Research office' }] }))
await page.route('**/api/library/library-1/items*', r => r.fulfill({ json: personal }))
await page.route('**/api/library/team-library/items*', r => r.fulfill({ json: team }))
await page.route('**/api/library/clone', async r => {
  const data = r.request().postDataJSON(); clones.push(data)
  if (failClone) return r.fulfill({ status: 503, json: { detail: 'Copy unavailable. Try again.' } })
  const original = [...personal, ...team].find(i => i.id === data.item_id)
  const copy = { ...original, id: 'copy-' + clones.length, item_id: 'copy-workflow-' + clones.length, name: original.name + ' (Copy)', verified: false }
  personal.push(copy); return r.fulfill({ json: copy })
})
await page.route('**/api/library/share', async r => {
  const data = r.request().postDataJSON(); shares.push(data)
  await new Promise(resolve => setTimeout(resolve, 300))
  if (shareMode === 'error' || (shareMode === 'force-error' && data.force)) return r.fulfill({ status: 503, json: { detail: 'Sharing unavailable. Your note is retained.' } })
  if (shareMode.startsWith('conflict') || shareMode === 'force-error') {
    if (!data.force) return r.fulfill({ status: 409, json: { detail: 'Already shared' } })
  }
  const copy = { ...personal[0], id: 'shared-' + shares.length, item_id: 'shared-workflow-' + shares.length, name: personal[0].name + ' (Team copy)' }
  team.push(copy); return r.fulfill({ json: copy })
})
async function shot(id) {
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), id + ': overflow')
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [], id + ': accessibility')
  console.log('Captured ' + id)
}
async function menu(name, action) {
  const row = page.locator('.library-item-row').filter({ has: page.getByRole('button', { name: 'Open ' + name, exact: true }) })
  await row.hover(); await row.getByRole('button', { name: 'More actions', exact: true }).click()
  await page.getByRole('group', { name: 'Actions for ' + name, exact: true }).getByRole('button', { name: action, exact: true }).click()
}
try {
  for (const width of [320, 1440]) {
    personal = [{ ...fixtures[0] }]; team = []; failClone = true; shareMode = 'error'; clones = []; shares = []
    await page.setViewportSize({ width, height: width === 320 ? 640 : 1000 }); await page.goto(review.baseURL + '/?mode=chat&tab=library')
    await menu(fixtures[0].name, 'Duplicate')
    await page.getByRole('button', { name: 'Retry item action', exact: true }).waitFor(); await shot('library-copy-error-' + width)
    failClone = false; await page.getByRole('button', { name: 'Retry item action', exact: true }).click()
    await page.getByRole('button', { name: 'Open ' + fixtures[0].name + ' (Copy)', exact: true }).waitFor(); assert.deepEqual(clones, [{ item_id: 'item-0' }, { item_id: 'item-0' }]); await shot('library-independent-personal-copy-' + width)
    await menu(fixtures[0].name, 'Send to team…')
    const dialog = page.getByRole('dialog', { name: 'Share with team', exact: true }), note = dialog.getByRole('textbox', { name: 'Add a note (optional)', exact: true })
    await dialog.getByText(/This creates an independent team copy/).waitFor(); await note.fill('Please check the sponsor deadline against the original.')
    const share = dialog.getByRole('button', { name: 'Share with Research office', exact: true })
    await share.click(); await expect(dialog.getByRole('button', { name: 'Sharing…' })).toBeDisabled(); await page.keyboard.press('Escape'); await expect(dialog).toBeVisible()
    await dialog.getByRole('alert').waitFor(); await expect(dialog.getByRole('alert')).toBeFocused(); assert.equal(shares.length, 1); await shot('library-share-retained-error-' + width)
    shareMode = 'conflict'; await share.click()
    const confirm = page.getByRole('dialog', { name: 'Already shared to team', exact: true }); await confirm.waitFor(); await shot('library-repeat-share-confirmation-' + width)
    await page.keyboard.press('Escape'); await confirm.waitFor({ state: 'hidden' }); await expect(note).toHaveValue('Please check the sponsor deadline against the original.')
    shareMode = 'force-error'; await share.click(); await confirm.getByRole('button', { name: 'Share a copy', exact: true }).click(); await dialog.getByRole('alert').waitFor(); await expect(note).toHaveValue('Please check the sponsor deadline against the original.'); await shot('library-repeat-share-error-' + width)
    shareMode = 'conflict'; await share.click(); await confirm.getByRole('button', { name: 'Share a copy', exact: true }).click(); await dialog.waitFor({ state: 'hidden' })
    assert.equal(shares.length, 6); assert.deepEqual(shares[3], { item_id: 'item-0', team_id: 'team-1', comment: 'Please check the sponsor deadline against the original.', force: true }); assert.deepEqual(shares[5], shares[3])
    await page.getByRole('button', { name: 'Team', exact: true }).click(); await page.getByRole('button', { name: 'Open ' + fixtures[0].name + ' (Team copy)', exact: true }).waitFor(); await shot('library-team-copy-destination-' + width)
    await menu(fixtures[0].name + ' (Team copy)', 'Add to my library')
    await page.getByRole('status').filter({ hasText: 'Copy to My Library' }).waitFor(); await page.getByRole('button', { name: 'Mine', exact: true }).click()
    await page.getByRole('button', { name: 'Open ' + fixtures[0].name + ' (Team copy) (Copy)', exact: true }).waitFor(); assert.equal(clones.at(-1).item_id, 'shared-6'); await shot('library-team-copy-in-mine-' + width)
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push('Personal copy failure/retry, explicit independent team copy guidance, failed share draft retention and pending guard, duplicate-copy confirmation/cancel/failed force/retry, team destination and copy back to Mine at 320/1440. All writes intercepted; no teammate notifications delivered. Source update semantics require separate source/backend evidence.')
} catch (error) { await review.capture('library-reuse-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
