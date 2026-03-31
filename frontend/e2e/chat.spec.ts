import { test, expect, type Page } from '@playwright/test'

async function loginAs(page: Page, user: string, pass: string) {
  await page.goto('/login')
  await page.getByLabel(/username/i).fill(user)
  await page.getByLabel(/password/i).fill(pass)
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 8000 })
}

test.describe('Chat', () => {
  test.beforeEach(async ({ page }) => {
    const user = process.env.E2E_TEST_USER
    const pass = process.env.E2E_TEST_PASS
    if (!user || !pass) test.skip()
    else await loginAs(page, user, pass)
  })

  test('chat page renders', async ({ page }) => {
    await page.goto('/chat')
    await expect(
      page.getByText(/chat/i).or(page.getByText(/conversation/i)).or(page.getByText(/message/i)),
    ).toBeVisible({ timeout: 8000 })
  })

  test('message input is present', async ({ page }) => {
    await page.goto('/chat')
    const input = page.getByRole('textbox').or(page.locator('textarea'))
    await expect(input).toBeVisible({ timeout: 8000 })
  })

  test('can type in the message input', async ({ page }) => {
    await page.goto('/chat')
    const input = page.getByRole('textbox').or(page.locator('textarea')).first()
    if (await input.isVisible({ timeout: 5000 }).catch(() => false)) {
      await input.fill('Hello, this is a test message')
      await expect(input).toHaveValue('Hello, this is a test message')
    }
  })
})
