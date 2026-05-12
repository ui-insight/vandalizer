import { test, expect } from '@playwright/test'

test.describe('Static smoke', () => {
  // These tests only check static-render paths — they do not require a backend.
  // App-state-dependent tests below need E2E_BACKEND_AVAILABLE.

  test('app shell renders with Vandalizer title @smoke', async ({ page }) => {
    await page.goto('/login')
    await expect(page).toHaveTitle(/vandalizer/i)
  })

  test('main bundle loads without console errors @smoke', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (err) => errors.push(err.message))
    await page.goto('/login')
    // Give the bundle a moment to evaluate
    await page.waitForLoadState('domcontentloaded')
    expect(errors).toEqual([])
  })
})

test.describe('Authentication', () => {
  test.beforeEach(async () => {
    if (!process.env.E2E_BACKEND_AVAILABLE) test.skip()
  })

  test('login page renders email and password fields', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByPlaceholder(/email/i)).toBeVisible()
    await expect(page.getByPlaceholder(/password/i)).toBeVisible()
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible()
  })

  test('shows error on invalid credentials', async ({ page }) => {
    await page.goto('/login')
    await page.getByPlaceholder(/email/i).fill('nonexistent_user@example.com')
    await page.getByPlaceholder(/password/i).fill('wrongpassword')
    await page.getByRole('button', { name: /sign in/i }).click()
    await expect(page.locator('[class*="red"]')).toBeVisible({ timeout: 5000 })
  })

  test('redirects to app after successful login', async ({ page }) => {
    const testUser = process.env.E2E_TEST_USER
    const testPass = process.env.E2E_TEST_PASS
    if (!testUser || !testPass) {
      test.skip()
      return
    }

    await page.goto('/login')
    await page.getByPlaceholder(/email/i).fill(testUser)
    await page.getByPlaceholder(/password/i).fill(testPass)
    await page.getByRole('button', { name: /sign in/i }).click()
    await expect(page).not.toHaveURL(/\/login/, { timeout: 8000 })
  })

  test('registration page has all required fields', async ({ page }) => {
    await page.goto('/register')
    await expect(page.getByPlaceholder(/full name/i)).toBeVisible()
    await expect(page.getByPlaceholder(/email/i)).toBeVisible()
    await expect(page.getByPlaceholder(/password/i)).toBeVisible()
  })
})
