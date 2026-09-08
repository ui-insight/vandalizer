import { test, expect, type Page } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { randomBytes } from 'node:crypto'

/**
 * Every unit test for the token-estimate self-check patches the database, so
 * none of them prove an admin can SEE a token-undercount alert or clear it.
 * Two bugs in this effort passed their unit tests while the behaviour was
 * broken, which is exactly the gap end-to-end coverage closes.
 *
 * Runs without a GPU. The alert is seeded straight into MongoDB rather than
 * provoked from a live model, because nothing in the product creates a
 * `QualityAlert` over HTTP — there is no such endpoint — and because a
 * GPU-bound chat turn would make this test too slow and too flaky to keep.
 * The seeded document is the exact shape `record_shortfall`
 * (`backend/app/services/token_estimate_check.py`) writes; if that shape
 * drifts, the assertions below stop describing the real feature, so keep the
 * two in step.
 *
 * The row is seeded under a uuid this file owns and is deleted in `afterAll`
 * whether the test passed or failed, and `beforeAll` sweeps the same uuid
 * prefix first so a run that was killed outright still cannot leave a row
 * behind. It never touches any other row: the deployment's `quality_alerts`
 * collection is shared, production-shaped data.
 */

// Directory holding the compose project that serves the deployment under test.
// Seeding shells out to docker against that project's mongo, so this must be
// the compose project's directory, not the frontend's.
//
// Deliberately has no default. A default would be one machine's layout, and
// the failure mode of guessing wrong here is seeding rows into whatever mongo
// the guess happens to reach. Unset means the suite skips.
const COMPOSE_DIR = process.env.E2E_COMPOSE_DIR || ''

// Owned by this spec: a uuid we can find and delete exactly, and a model name
// no real deployment would configure, so a stray row is obviously test debris.
const ALERT_UUID = `e2e-token-undercount-${randomBytes(8).toString('hex')}`
const MODEL = `e2e-undercount-model-${randomBytes(4).toString('hex')}`

// Mirrors the wording built in `record_shortfall`, including the thousands
// separators, so the seeded row is a realistic one rather than a placeholder.
// It does NOT guard that wording: this constant is seeded by this file, so
// rewording `record_shortfall` leaves the assertion green. What the assertion
// guards is that whatever message the API returns reaches the screen verbatim
// — no truncation, no summarising, no dropped digits — which is worth having,
// and which is why the constant is a full sentence with separators in it.
const ESTIMATED = 91_000
const CHARGED = 104_500
const BUDGET = 120_000
const MESSAGE =
  `Token estimate read low for ${MODEL}: estimated ${ESTIMATED.toLocaleString('en-US')} ` +
  `but the model charged ${CHARGED.toLocaleString('en-US')}, read low by ` +
  `${(CHARGED - ESTIMATED).toLocaleString('en-US')} tokens. It still fit the input budget ` +
  `of ${BUDGET.toLocaleString('en-US')}, but budgets for this model are optimistic and ` +
  `will fail nearer the context limit. Raise token_safety_margin on this model's config, ` +
  `or check that its name matches its published identifier.`

const DB = process.env.E2E_MONGO_DB || 'vandalizer'

let mongoContainer: string | null = null

/**
 * Resolve the mongo container once, via compose, then talk to it with plain
 * `docker exec`.
 *
 * `docker compose exec` would be the obvious call, and it is what this does on
 * a developer's host. It is split in two because this spec is normally run
 * inside the Playwright image, where compose cannot fully resolve the project:
 * the deployment's overlay pulls in an `env_file` that lives outside the repo
 * and so outside the container's mounts. `compose ps` needs no such
 * resolution, and `docker exec` needs no compose at all.
 */
function mongosh(js: string): string {
  if (mongoContainer === null) {
    mongoContainer = execFileSync('docker', ['compose', 'ps', '-q', 'mongo'], {
      cwd: COMPOSE_DIR,
      encoding: 'utf8',
      timeout: 60_000,
    }).trim()
    expect(mongoContainer, `no mongo container in the compose project at ${COMPOSE_DIR}`)
      .not.toBe('')
  }
  return execFileSync(
    'docker',
    ['exec', '-i', mongoContainer, 'mongosh', DB, '--quiet', '--eval', js],
    { encoding: 'utf8', timeout: 60_000 },
  ).trim()
}

/** The document `record_shortfall` inserts, minus the fields Mongo/Beanie fill. */
const SEED_DOC = {
  uuid: ALERT_UUID,
  alert_type: 'token_undercount',
  item_kind: 'model',
  item_id: MODEL,
  item_name: MODEL,
  severity: 'warning',
  message: MESSAGE,
  previous_score: null,
  current_score: null,
  previous_tier: null,
  current_tier: null,
  acknowledged: false,
  acknowledged_by: null,
  acknowledged_at: null,
}

type AlertRow = {
  uuid: string
  alert_type: string
  item_kind: string
  item_id: string
  item_name: string
  severity: string
  message: string
  acknowledged: boolean
}

async function loginAs(page: Page, user: string, pass: string) {
  await page.goto('/login')
  await page.getByPlaceholder(/email/i).fill(user)
  await page.getByPlaceholder(/password/i).fill(pass)
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 30_000 })
}

/** Alerts the admin API returns, filtered to the one this spec owns. */
async function ourAlert(page: Page, acknowledged: boolean): Promise<AlertRow | undefined> {
  const res = await page.request.get(
    `/api/admin/quality/alerts?limit=200&acknowledged=${acknowledged}`,
  )
  expect(res.ok(), `GET /api/admin/quality/alerts?acknowledged=${acknowledged}`).toBeTruthy()
  const body = await res.json()
  return (body.alerts as AlertRow[]).find((a) => a.uuid === ALERT_UUID)
}

test.describe('Token-undercount alerts reach an admin', () => {
  test.skip(
    !COMPOSE_DIR || !process.env.E2E_TEST_USER || !process.env.E2E_TEST_PASS,
    'needs E2E_COMPOSE_DIR and E2E_TEST_USER / E2E_TEST_PASS',
  )

  test.beforeAll(() => {
    // Sweep debris from an earlier run that never reached `afterAll` — a
    // timeout kill, a stopped container, a Ctrl-C. Without this, a SIGKILLed
    // worker leaves a token-undercount alert permanently visible in a real
    // admin UI, which is exactly what this file's header promises it will not
    // do. Scoped to this spec's own uuid prefix, which no real alert can
    // carry; anything broader could reach a genuine alert.
    mongosh(
      `print(db.quality_alerts.deleteMany({ uuid: /^e2e-token-undercount-/ }).deletedCount)`,
    )

    const out = mongosh(
      `print(db.quality_alerts.insertOne(Object.assign(${JSON.stringify(SEED_DOC)}, ` +
        `{ created_at: new Date() })).acknowledged)`,
    )
    expect(out, 'seeding the alert into MongoDB').toContain('true')
  })

  test.afterAll(() => {
    // Runs whether the test passed or failed. Deletes this spec's row only.
    mongosh(`print(db.quality_alerts.deleteOne({ uuid: ${JSON.stringify(ALERT_UUID)} }).deletedCount)`)
  })

  test('an admin sees a seeded token-undercount alert and can acknowledge it', async ({ page }) => {
    await loginAs(page, process.env.E2E_TEST_USER!, process.env.E2E_TEST_PASS!)

    // 1. The API hands the alert to an admin, with the fields the UI reads.
    const seeded = await ourAlert(page, false)
    expect(seeded, `alert ${ALERT_UUID} missing from the unacknowledged list`).toBeDefined()
    expect(seeded!.alert_type).toBe('token_undercount')
    expect(seeded!.item_kind).toBe('model')
    expect(seeded!.item_name).toBe(MODEL)
    expect(seeded!.message).toContain(MODEL)
    expect(seeded!.message).toMatch(/estimated/i)
    expect(['warning', 'critical']).toContain(seeded!.severity)
    expect(seeded!.acknowledged).toBe(false)

    // 2. It reaches the screen. `QualityAlert.item_kind` is documented as
    //    "search_set" | "workflow" and this feature writes "model", so an
    //    admin UI that switched on the kind would drop the alert silently
    //    while every API assertion above still passed. This is the assertion
    //    that would catch that.
    await page.goto('/admin?tab=quality')
    const row = page
      .locator('div')
      .filter({ hasText: MODEL })
      .filter({ has: page.getByRole('button', { name: /acknowledge/i }) })
      .last()
    await expect(row, 'the alert is rendered in the admin Quality tab').toBeVisible({
      timeout: 30_000,
    })
    await expect(row).toContainText(MESSAGE)
    await expect(row).toContainText(/warning/i)

    // 3. An admin can clear it from the UI. Going through the button rather
    //    than a raw POST is deliberate: the acknowledge endpoint is CSRF
    //    protected, so only the app's own client exercises the real path.
    await row.getByRole('button', { name: /acknowledge/i }).click()
    await expect(row).toBeHidden({ timeout: 15_000 })

    // 4. It left the unacknowledged list...
    expect(
      await ourAlert(page, false),
      'acknowledged alert still returned as unacknowledged',
    ).toBeUndefined()

    // ...and, crucially, it turned up in the acknowledged one. Asserting only
    // the absence above would be vacuous: this endpoint defaults to
    // `acknowledged=false`, so an alert that had been deleted, or never
    // existed, would satisfy it just as well. This half proves it *moved*.
    const cleared = await ourAlert(page, true)
    expect(cleared, `alert ${ALERT_UUID} missing from the acknowledged list`).toBeDefined()
    expect(cleared!.acknowledged).toBe(true)
    expect(cleared!.alert_type).toBe('token_undercount')
  })
})
