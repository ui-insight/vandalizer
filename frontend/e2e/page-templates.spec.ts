import { test, expect } from '@playwright/test'

test.use({ channel: process.env.PLAYWRIGHT_CHANNEL || undefined })

for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
test(`review and save a design without approving the Page (${viewport.width}px)`, async ({ page }) => {
  await page.setViewportSize(viewport)
  const writes: unknown[] = []
  await page.route('**/api/page-templates/prepare', route => route.fulfill({ json: {
    draft_id: 'prepared-design', fields: [{ id: 'field_1', label: 'Award title', bar: false }],
    preview_html: '<style>body{font:16px/1.5 system-ui;padding:24px;color:#17364a}.panel{border:1px solid #ccc;padding:20px}</style><h1>Budget dashboard</h1><div class="panel">Not in this file</div>',
  } }))
  await page.route('**/api/page-templates', async route => {
    writes.push(route.request().postDataJSON())
    await route.fulfill({ json: { uuid: 'template', name: 'NIH Budget Dashboard', team_id: null } })
  })
  await page.goto('/e2e/fixtures/page-templates.html')
  await expect(page.getByText('24 values filled from New budget.xlsx · 0 kept from the template.')).toBeVisible()
  await page.getByRole('button', { name: 'Save as template' }).click()
  const dialog = page.getByRole('dialog', { name: 'Save as template' })
  const preview = dialog.frameLocator('iframe')
  await expect(preview.getByRole('heading', { name: 'Budget dashboard' })).toBeVisible()
  await expect(preview.getByText('Not in this file')).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Save template' })).toBeDisabled()
  await dialog.getByLabel('Template name').fill('NIH Budget Dashboard')
  await dialog.getByLabel('Description', { exact: true }).fill('Team budget review')
  await dialog.getByLabel('Reusable guidance').fill('Review source notes before acting.')
  await dialog.getByText('Review field meanings (1)').click()
  await dialog.getByLabel('Field 1', { exact: true }).fill('Award title from the new file')
  const frame = dialog.locator('iframe')
  const frameWidth = await frame.evaluate(element => element.getBoundingClientRect().width)
  const previewWidth = await dialog.locator('.page-preview').evaluate(element => element.getBoundingClientRect().width)
  expect(frameWidth).toBeGreaterThan(previewWidth - 4)
  await expect.poll(() => preview.locator('body').evaluate(() => window.innerWidth)).toBeGreaterThan(frameWidth - 4)
  expect(await dialog.evaluate(element => element.scrollWidth - element.clientWidth)).toBeLessThanOrEqual(1)
  await page.screenshot({ path: `/tmp/page-template-review-${viewport.width}.png`, fullPage: true })
  await dialog.getByRole('button', { name: 'Save template' }).click()
  await expect(dialog.getByText('Template saved privately. It contains the design and empty fields.')).toBeVisible()
  expect(writes).toEqual([{ draft_id: 'prepared-design', name: 'NIH Budget Dashboard', description: 'Team budget review', guidance: 'Review source notes before acting.', field_labels: { field_1: 'Award title from the new file' } }])
  await dialog.getByRole('button', { name: 'Done' }).click()
  await expect(page.getByRole('button', { name: 'Save page', exact: true })).toBeEnabled()
})
}
