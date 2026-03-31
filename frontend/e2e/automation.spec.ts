import { test, expect, type Page } from '@playwright/test'

async function loginAs(page: Page, user: string, pass: string) {
  await page.goto('/login')
  await page.getByLabel(/username/i).fill(user)
  await page.getByLabel(/password/i).fill(pass)
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 8000 })
}

test.describe('Automation', () => {
  test.beforeEach(async ({ page }) => {
    const user = process.env.E2E_TEST_USER
    const pass = process.env.E2E_TEST_PASS
    if (!user || !pass) test.skip()
    else await loginAs(page, user, pass)
  })

  test('automation page renders', async ({ page }) => {
    await page.goto('/automation')
    await expect(
      page.getByText(/automation/i).first(),
    ).toBeVisible({ timeout: 8000 })
  })

  test('shows automation list or empty state', async ({ page }) => {
    await page.goto('/automation')
    await expect(
      page.getByRole('button', { name: /new|create/i }).or(page.getByText(/no automation/i)).or(page.getByText(/trigger/i)),
    ).toBeVisible({ timeout: 8000 })
  })
})
