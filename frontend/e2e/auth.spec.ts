import { test, expect } from '@playwright/test'

test.describe('Authentication', () => {
  test('login page renders username and password fields', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByLabel(/username/i)).toBeVisible()
    await expect(page.getByLabel(/password/i)).toBeVisible()
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible()
  })

  test('shows error on invalid credentials', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel(/username/i).fill('nonexistent_user')
    await page.getByLabel(/password/i).fill('wrongpassword')
    await page.getByRole('button', { name: /sign in/i }).click()
    // Expect some error message to appear
    await expect(page.locator('[class*="red"]')).toBeVisible({ timeout: 5000 })
  })

  test('redirects to app after successful login', async ({ page }) => {
    // Skip if no test credentials are configured
    const testUser = process.env.E2E_TEST_USER
    const testPass = process.env.E2E_TEST_PASS
    if (!testUser || !testPass) {
      test.skip()
      return
    }

    await page.goto('/login')
    await page.getByLabel(/username/i).fill(testUser)
    await page.getByLabel(/password/i).fill(testPass)
    await page.getByRole('button', { name: /sign in/i }).click()
    // After login, should not be on /login anymore
    await expect(page).not.toHaveURL(/\/login/, { timeout: 8000 })
  })

  test('registration page has all required fields', async ({ page }) => {
    await page.goto('/register')
    await expect(page.getByLabel(/username/i)).toBeVisible()
    await expect(page.getByLabel(/email/i)).toBeVisible()
    await expect(page.getByLabel(/password/i).first()).toBeVisible()
  })
})
