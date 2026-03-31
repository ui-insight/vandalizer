import { test, expect, type Page } from '@playwright/test'

async function loginAs(page: Page, user: string, pass: string) {
  await page.goto('/login')
  await page.getByLabel(/username/i).fill(user)
  await page.getByLabel(/password/i).fill(pass)
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 8000 })
}

test.describe('Workflows', () => {
  test.beforeEach(async ({ page }) => {
    const user = process.env.E2E_TEST_USER
    const pass = process.env.E2E_TEST_PASS
    if (!user || !pass) test.skip()
    else await loginAs(page, user, pass)
  })

  test('workflows page renders', async ({ page }) => {
    await page.goto('/workflows')
    await expect(
      page.getByRole('heading', { name: /workflow/i }).or(page.getByText(/workflow/i).first()),
    ).toBeVisible({ timeout: 8000 })
  })

  test('new workflow button is visible', async ({ page }) => {
    await page.goto('/workflows')
    const createBtn = page.getByRole('button', { name: /new|create/i })
    await expect(createBtn).toBeVisible({ timeout: 8000 })
  })

  test('can open workflow creation', async ({ page }) => {
    await page.goto('/workflows')
    const createBtn = page.getByRole('button', { name: /new|create/i })
    if (await createBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await createBtn.click()
      // Should see a name input or workflow editor
      await expect(
        page.getByRole('textbox').or(page.getByText(/name/i)),
      ).toBeVisible({ timeout: 5000 })
    }
  })
})
