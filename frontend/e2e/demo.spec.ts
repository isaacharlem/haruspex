// One spec against the full compose demo (make demo running):
// fleet fills -> a divergent run reaches AT_RISK/DOOMED -> a policy toast
// fires -> the run detail renders the prognosis fan -> the Analyst opens
// (setup card without a key, chat box with one).

import { expect, test } from '@playwright/test'

const API_KEY = process.env.E2E_API_KEY ?? ''

test.beforeEach(async ({ page }) => {
  expect(API_KEY, 'E2E_API_KEY must carry a dashboard key (make e2e extracts it)').toBeTruthy()
  await page.addInitScript((key) => {
    window.localStorage.setItem(
      'haruspex-dashboard-key',
      JSON.stringify({ state: { key }, version: 0 }),
    )
  }, API_KEY)
})

test('the demo comes alive end to end', async ({ page }) => {
  await page.goto('/')

  await test.step('fleet shows at least 8 live runs', async () => {
    await expect
      .poll(async () => page.getByTestId('run-card').filter({ hasText: '/hr' }).count(), {
        timeout: 120_000,
        message: 'live run cards (showing a $/hr burn rate) should reach 8',
      })
      .toBeGreaterThanOrEqual(8)
  })

  await test.step('a divergent run reaches AT_RISK or DOOMED', async () => {
    await expect(
      page
        .getByTestId('run-card')
        .filter({ hasText: /DOOMED|AT RISK/ })
        .first(),
    ).toBeVisible({ timeout: 180_000 })
  })

  await test.step('the prognosis fan renders on a live run', async () => {
    await page
      .getByTestId('run-card')
      .filter({ hasText: '/hr' })
      .filter({ hasText: /P\((hit target|diverge)\) \d/ })
      .first()
      .click()
    await expect(page.locator('path[data-fan="q50"]').first()).toBeVisible({
      timeout: 60_000,
    })
    await page.goBack()
  })

  await test.step('a policy-fired toast appears', async () => {
    await expect(
      page.getByTestId('toast').filter({ hasText: /Kill directed|stopped|warning/ }).first(),
    ).toBeVisible({ timeout: 240_000 })
  })

  await test.step('the killed run shows its sigil on the fleet', async () => {
    await expect(
      page.getByTestId('run-card').filter({ hasText: 'KILLED' }).first(),
    ).toBeVisible({ timeout: 120_000 })
  })

  await test.step('the Analyst opens: setup card without a key, chat box with one', async () => {
    await page.getByTestId('open-copilot').click()
    await expect(page.getByTestId('copilot-panel')).toBeVisible()
    const setupCard = page.getByTestId('copilot-setup-card')
    const chatInput = page.getByTestId('copilot-input')
    await expect(setupCard.or(chatInput).first()).toBeVisible({ timeout: 15_000 })
    if (await setupCard.isVisible()) {
      await expect(setupCard).toContainText('ANTHROPIC_API_KEY')
    } else {
      await expect(chatInput).toBeEnabled()
    }
  })
})
