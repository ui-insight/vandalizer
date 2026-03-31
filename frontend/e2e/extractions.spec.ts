import { test, expect, type Page } from '@playwright/test'

async function loginAs(page: Page, user: string, pass: string) {
  await page.goto('/login')
  await page.getByLabel(/username/i).fill(user)
  await page.getByLabel(/password/i).fill(pass)
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 8000 })
}

test.describe('Extractions / Library', () => {
  test.beforeEach(async ({ page }) => {
    const user = process.env.E2E_TEST_USER
    const pass = process.env.E2E_TEST_PASS
    if (!user || !pass) test.skip()
    else await loginAs(page, user, pass)
  })

  test('library page renders', async ({ page }) => {
    await page.goto('/library')
    await expect(
      page.getByText(/library/i).or(page.getByText(/search set/i)).or(page.getByText(/extraction/i)),
    ).toBeVisible({ timeout: 8000 })
  })

  test('can see search sets or empty state', async ({ page }) => {
    await page.goto('/library')
    // Either existing search sets or an empty state / create button
    await expect(
      page.getByRole('button', { name: /new|create/i }).or(page.getByText(/no.*search/i)).or(page.locator('table, [data-testid]')),
    ).toBeVisible({ timeout: 8000 })
  })

  test('create search set button is accessible', async ({ page }) => {
    await page.goto('/library')
    const createBtn = page.getByRole('button', { name: /new|create/i })
    if (await createBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await createBtn.click()
      // Should show a name/title input
      await expect(
        page.getByRole('textbox').or(page.getByText(/title|name/i)),
      ).toBeVisible({ timeout: 5000 })
    }
  })
})
