import { test, expect } from '@playwright/test'

test.use({ channel: process.env.PLAYWRIGHT_CHANNEL || undefined })

test('jump links work in the actual chat review card and expanded preview', async ({ page }) => {
  const url = '/e2e/fixtures/page-preview.html?mode=chat#message'
  // The app cannot be embedded. A #link accidentally resolved against its
  // URL therefore blanks the preview instead of scrolling within the report.
  await page.route('**/e2e/fixtures/page-preview.html*', async route => {
    const response = await route.fetch()
    await route.fulfill({ response, headers: { ...response.headers(), 'X-Frame-Options': 'DENY', 'Content-Security-Policy': "frame-ancestors 'none'" } })
  })
  await page.goto(url)
  await expect(page.getByText('Ready for your review')).toBeVisible()
  const outerUrl = page.url()
  const compact = page.frameLocator('iframe[title="Page preview"]')
  await compact.getByRole('link', { name: 'Full budget table', exact: true }).click()
  await expect(compact.locator('#budget-table')).toBeInViewport()
  await expect(compact.getByRole('heading', { name: 'Budget dashboard' })).toBeAttached()

  await page.getByRole('button', { name: 'Expand preview' }).click()
  const dialog = page.getByRole('dialog', { name: 'Budget dashboard' })
  const expanded = dialog.frameLocator('iframe')
  await expanded.getByRole('link', { name: 'Personnel', exact: true }).click()
  await expect(expanded.locator('#personnel')).toBeInViewport()
  await expanded.locator('#personnel').getByRole('link', { name: 'Back to top' }).click()
  // Keyboard activation must remain same-document navigation too.
  await expanded.getByRole('link', { name: 'Full budget table', exact: true }).focus()
  await expanded.getByRole('link', { name: 'Full budget table', exact: true }).press('Enter')
  await expect(expanded.locator('#budget-table')).toBeInViewport()
  await expanded.locator('#budget-table').getByRole('link', { name: 'Back to top' }).click()
  await expanded.getByRole('link', { name: 'Source notes', exact: true }).click()
  await expanded.locator('summary').filter({ hasText: 'Source notes' }).click()
  await expect(expanded.getByText('Figures are in USD.')).toBeVisible()
  await expanded.locator('summary').filter({ hasText: 'Calculated summary' }).press('Enter')
  await expect(expanded.getByText('Total: $100,000.')).toBeVisible()
  expect(page.url()).toBe(outerUrl)
  for (const frame of page.frames().filter(frame => frame.parentFrame())) {
    expect(await frame.evaluate('window.untrustedPreviewScriptRan')).toBeUndefined()
  }
  await expect(dialog.locator('iframe')).toHaveAttribute('sandbox', 'allow-popups allow-popups-to-escape-sandbox')
  await page.getByRole('button', { name: 'Close Budget dashboard' }).click()
  await expect(compact.getByRole('heading', { name: 'Budget dashboard' })).toBeAttached()
  await expect(page.getByRole('button', { name: 'Save new version' })).toBeEnabled()
})
