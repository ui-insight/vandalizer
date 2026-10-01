import assert from 'node:assert/strict'
import { expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
page.setDefaultTimeout(15000)
let user, prefs, memory, failReads, failProfile, failPrefs, failClear, failGenerate, failRevoke, profileWrites, prefWrites, tokenWrites, clearWrites
const initialUser = { id: 'reviewer', user_id: 'reviewer', email: 'reviewer@example.test', name: 'Alex Morgan', is_admin: false, is_staff: false, current_team: 'team-1', current_team_uuid: 'team-1', sso_provider: null }
await page.route('**/api/auth/me', r => r.fulfill({ json: user }))
await page.route('**/api/auth/profile', async r => { const body = r.request().postDataJSON(); profileWrites.push(body); await new Promise(resolve => setTimeout(resolve, 200)); if (failProfile) return r.fulfill({ status: 503, json: { detail: 'Profile save unavailable. Try again.' } }); user = { ...user, name: body.name, email: body.email || user.email }; return r.fulfill({ json: user }) })
await page.route('**/api/auth/email-preferences', async r => {
  if (r.request().method() === 'GET') return failReads ? r.fulfill({ status: 503, json: { detail: 'Preferences unavailable.' } }) : r.fulfill({ json: prefs })
  const body = r.request().postDataJSON(); prefWrites.push(body); await new Promise(resolve => setTimeout(resolve, 300)); if (failPrefs) return r.fulfill({ status: 503, json: { detail: 'Preference save unavailable.' } }); prefs = { ...prefs, ...body }; return r.fulfill({ json: prefs })
})
await page.route('**/api/chat/memory', r => {
  if (r.request().method() === 'DELETE') { clearWrites++; if (failClear) return r.fulfill({ status: 503, json: { detail: 'Memory clear unavailable.' } }); memory = { extractions: [], workflows: [], kbs: [] }; return r.fulfill({ json: { success: true, removed: true } }) }
  return failReads ? r.fulfill({ status: 503, json: { detail: 'Memory unavailable.' } }) : r.fulfill({ json: memory })
})
await page.route('**/api/auth/api-token/status', r => failReads ? r.fulfill({ status: 503, json: { detail: 'Token status unavailable.' } }) : r.fulfill({ json: { has_token: false, created_at: null } }))
await page.route('**/api/auth/api-token/generate', r => { tokenWrites.push('generate'); return failGenerate ? r.fulfill({ status: 503, json: { detail: 'Token generation unavailable.' } }) : r.fulfill({ json: { api_token: 'SYNTHETIC-NONFUNCTIONAL-QA-TOKEN', created_at: '2026-09-30T10:00:00Z' } }) })
await page.route('**/api/auth/api-token/revoke', r => { tokenWrites.push('revoke'); return failRevoke ? r.fulfill({ status: 503, json: { detail: 'Token revocation unavailable.' } }) : r.fulfill({ json: { ok: true } }) })
async function shot(id, target) { if (target) await target.scrollIntoViewIfNeeded(); await review.capture(id); assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), id + ': overflow'); assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [], id + ': accessibility'); console.log('Captured ' + id) }
try {
  for (const width of [320, 1440]) {
    user = { ...initialUser }; prefs = { onboarding: true, nudges: false, announcements: true }; memory = { extractions: [], workflows: [{ title: 'Review a multi-institution sponsor proposal and supporting budget justification', count: 12, last_used: '2026-09-30' }], kbs: [] }
    failReads = failProfile = failPrefs = failClear = failGenerate = failRevoke = true; profileWrites = []; prefWrites = []; tokenWrites = []; clearWrites = 0
    await page.setViewportSize({ width, height: width === 320 ? 700 : 1000 }); await page.goto(review.baseURL + '/account')
    await page.getByRole('button', { name: 'Retry email preferences' }).waitFor(); assert.equal(await page.getByRole('checkbox').count(), 0); assert.equal(await page.getByRole('button', { name: 'Generate API Token', exact: true }).count(), 0)
    await shot('account-failed-reads-' + width, page.getByRole('button', { name: 'Retry email preferences' }))
    failReads = false
    for (const name of ['Retry assistant memory', 'Retry email preferences', 'Retry token status']) await page.getByRole('button', { name, exact: true }).click()
    const onboarding = page.getByRole('checkbox', { name: /Onboarding & tutorials/ }), nudges = page.getByRole('checkbox', { name: /Activity nudges/ })
    await onboarding.click(); await expect(nudges).toBeDisabled(); await page.getByRole('alert').filter({ hasText: 'last saved preferences have been restored' }).waitFor(); await expect(onboarding).toBeChecked(); await expect(nudges).not.toBeChecked(); assert.equal(prefWrites.length, 1)
    await shot('account-preference-save-error-' + width, onboarding); failPrefs = false; await onboarding.click(); await expect(onboarding).toBeEnabled(); await expect(onboarding).not.toBeChecked(); assert.deepEqual(prefWrites, [{ onboarding: false }, { onboarding: false }])
    await page.getByRole('textbox', { name: 'Display Name', exact: true }).fill('Alex Research Administrator'); await page.getByRole('textbox', { name: 'Email', exact: true }).fill('updated@example.test'); await page.getByRole('button', { name: 'Save Profile', exact: true }).click(); await page.getByRole('alert').filter({ hasText: 'Enter your current password' }).waitFor(); assert.equal(profileWrites.length, 0)
    await page.getByLabel('Current Password', { exact: true }).fill('synthetic-password'); await page.getByRole('button', { name: 'Save Profile', exact: true }).click(); await page.getByRole('alert').filter({ hasText: 'Profile save unavailable' }).waitFor(); await expect(page.getByRole('textbox', { name: 'Email', exact: true })).toHaveValue('updated@example.test'); await shot('account-profile-draft-error-' + width, page.getByRole('button', { name: 'Save Profile', exact: true }))
    failProfile = false; await page.getByRole('button', { name: 'Save Profile', exact: true }).click(); await page.getByRole('status').filter({ hasText: 'Profile saved' }).waitFor(); assert.deepEqual(profileWrites[1], profileWrites[0])
    await page.getByRole('button', { name: 'Clear and start fresh', exact: true }).click(); await page.getByRole('dialog', { name: 'Clear assistant memory', exact: true }).getByRole('button', { name: 'Clear memory', exact: true }).click(); await page.getByRole('alert').filter({ hasText: 'Memory clear unavailable.' }).waitFor(); await page.getByText(memory.workflows[0].title, { exact: false }).waitFor(); await shot('account-memory-clear-error-' + width, page.getByRole('button', { name: 'Clear and start fresh', exact: true }))
    failClear = false; await page.getByRole('button', { name: 'Clear and start fresh', exact: true }).click(); await page.getByRole('dialog', { name: 'Clear assistant memory', exact: true }).getByRole('button', { name: 'Clear memory', exact: true }).click(); await page.getByText(/Nothing yet/).waitFor(); assert.equal(clearWrites, 2)
    await page.getByRole('button', { name: 'Generate API Token', exact: true }).click(); await page.getByRole('alert').filter({ hasText: 'Token generation unavailable.' }).waitFor(); failGenerate = false; await page.getByRole('button', { name: 'Generate API Token', exact: true }).click(); await page.getByRole('textbox', { name: 'API token', exact: true }).waitFor()
    await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: () => Promise.reject(new Error('Clipboard unavailable')) } })); await page.getByRole('button', { name: 'Copy token', exact: true }).click(); await page.getByRole('alert').filter({ hasText: 'Could not copy the token' }).waitFor(); assert.equal(await page.getByRole('button', { name: 'Token copied', exact: true }).count(), 0); await shot('account-token-copy-error-' + width, page.getByRole('textbox', { name: 'API token', exact: true }))
    await page.getByRole('button', { name: 'Regenerate', exact: true }).click(); await page.getByRole('dialog', { name: 'Replace existing token?', exact: true }).getByRole('button', { name: 'Cancel', exact: true }).click(); assert.deepEqual(tokenWrites, ['generate', 'generate'])
    await page.getByRole('button', { name: 'Revoke Token', exact: true }).click(); await page.getByRole('dialog', { name: 'Revoke API token?', exact: true }).getByRole('button', { name: 'Revoke', exact: true }).click(); await page.getByRole('alert').filter({ hasText: 'Token revocation unavailable.' }).waitFor(); await page.getByText('Active', { exact: true }).waitFor(); await shot('account-token-revoke-error-' + width, page.getByRole('button', { name: 'Revoke Token', exact: true }))
    failRevoke = false; await page.getByRole('button', { name: 'Revoke Token', exact: true }).click(); await page.getByRole('dialog', { name: 'Revoke API token?', exact: true }).getByRole('button', { name: 'Revoke', exact: true }).click(); await page.getByRole('button', { name: 'Generate API Token', exact: true }).waitFor(); assert.deepEqual(tokenWrites, ['generate', 'generate', 'revoke', 'revoke'])
    user = { ...user, sso_provider: 'saml' }; await page.goto(review.baseURL + '/account'); await expect(page.getByRole('textbox', { name: 'Email', exact: true })).toBeDisabled(); await page.getByRole('textbox', { name: 'Display Name', exact: true }).fill('SSO display name'); await page.getByRole('button', { name: 'Save Profile', exact: true }).click(); await page.getByRole('status').filter({ hasText: 'Profile saved' }).waitFor(); assert.deepEqual(profileWrites.at(-1), { name: 'SSO display name' }); await shot('account-sso-managed-email-' + width)
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push('Profile/email/password failure and identical retry, SSO email lock, failed read recovery, serialized preference writes and rollback, memory confirmation/failure/clear, synthetic token status/generation/copy/replace cancel/revoke failure/retry at 320/1440. No real email, token, preference or memory changed.')
} catch (error) { await review.capture('account-recovery-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
