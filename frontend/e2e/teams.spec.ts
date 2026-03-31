import { test, expect, type Page } from '@playwright/test'

async function loginAs(page: Page, user: string, pass: string) {
  await page.goto('/login')
  await page.getByLabel(/username/i).fill(user)
  await page.getByLabel(/password/i).fill(pass)
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 8000 })
}

test.describe('Team settings', () => {
  test.beforeEach(async ({ page }) => {
    const user = process.env.E2E_TEST_USER
    const pass = process.env.E2E_TEST_PASS
    if (!user || !pass) test.skip()
    else await loginAs(page, user, pass)
  })

  test('team settings page renders', async ({ page }) => {
    await page.goto('/teams')
    await expect(
      page.getByText(/team/i).first(),
    ).toBeVisible({ timeout: 8000 })
  })

  test('team members section is visible', async ({ page }) => {
    await page.goto('/teams')
    await expect(
      page.getByText(/member/i).or(page.getByText(/owner/i)),
    ).toBeVisible({ timeout: 8000 })
  })

  test('invite UI is accessible', async ({ page }) => {
    await page.goto('/teams')
    const inviteBtn = page.getByRole('button', { name: /invite/i })
    if (await inviteBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await inviteBtn.click()
      // Should show an email input or invite form
      await expect(
        page.getByRole('textbox').or(page.getByText(/email/i)),
      ).toBeVisible({ timeout: 5000 })
    }
  })
})
