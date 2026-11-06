import { expect, test } from '@playwright/test';

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'wait' });
});

test.beforeEach(async ({ request }) => {
  const system = await (await request.get('/api/v1/system')).json();
  test.skip(
    system.mode !== 'demo' || system.allow_live_trading,
    'Requires an isolated Demo-only workspace.',
  );
});

test('continuous replay preserves an actual API plan and renders carried balances', async ({
  page,
}) => {
  await page.goto('/strategies');
  const backtest = page.waitForResponse(
    (r) => r.url().includes('/strategies/backtest') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Run backtest', exact: true }).click();
  expect((await backtest).ok()).toBeTruthy();
  await page.getByText('Validate on unseen data', { exact: true }).click();
  await page
    .getByRole('combobox', { name: 'Parameter selection', exact: true })
    .selectOption('fixed');
  await page.getByText('Selection rules & limits', { exact: true }).click();
  await page
    .getByRole('checkbox', { name: 'Also replay continuous deployment', exact: true })
    .check();
  const saved = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === '/api/v1/strategies/validations' &&
      r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Run walk-forward test', exact: true }).click();
  const response = await saved;
  expect(response.ok(), await response.text()).toBeTruthy();
  const study = await response.json();
  expect(study.deployment.adaptive.transitions).toHaveLength(study.folds.length);
  const replay = page.locator('.continuous-replay');
  await expect(replay.getByText('Continuous walk-forward replay', { exact: true })).toBeVisible();
  await replay.getByText('Balances entering each parameter window', { exact: true }).click();
  await expect(
    replay.getByRole('columnheader', { name: 'Units carried', exact: true }),
  ).toBeVisible();
});

test('historical basket study uses current Demo holdings, saves real metrics and exports input evidence', async ({
  page,
}) => {
  await page.goto('/account');
  await page.getByText('Historical basket risk', { exact: true }).click();
  const saved = page.waitForResponse(
    (r) => new URL(r.url()).pathname === '/api/v1/account/risk' && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Calculate & save risk study', exact: true }).click();
  const response = await saved;
  expect(response.status(), await response.text()).toBe(201);
  const study = await response.json();
  expect(study.observations).toBeGreaterThanOrEqual(30);
  expect(study.source.source).toBe('demo');
  const results = page.getByRole('region', { name: 'Basket risk results', exact: true });
  await expect(results.getByText('Demo reference history', { exact: true })).toBeVisible();
  await results
    .getByText('Weights, correlations & variance contributions', { exact: true })
    .click();
  await expect(
    results.getByRole('columnheader', { name: 'Share of variance', exact: true }),
  ).toBeVisible();
  await results.locator('summary').filter({ hasText: 'Hypothetical basket path' }).click();
  await expect(results.locator('.recharts-surface').first()).toBeVisible();
  const download = page.waitForEvent('download');
  await results.getByRole('button', { name: 'Export full study', exact: true }).click();
  expect((await download).suggestedFilename()).toBe(`sibyl-basket-risk-${study.id}.json`);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBeTruthy();
});

test('conversation reply review keeps the original unconfirmed outcome', async ({
  page,
  request,
}) => {
  const history = await (
    await request.get('/api/v1/settings/messaging/telegram/deliveries?kind=reply')
  ).json();
  const fixture = history.items.find((r: { preview: string }) =>
    r.preview.startsWith('Demo conversation reply'),
  );
  test.skip(!fixture, 'Requires an explicitly seeded unsent conversation receipt fixture.');
  await page.goto('/settings?tab=messaging');
  await page.getByText('Review Telegram deliveries', { exact: true }).click();
  await page.getByRole('combobox', { name: 'Delivery type', exact: true }).selectOption('reply');
  await page.getByRole('button', { name: /Demo conversation reply/ }).click();
  const dialog = page.getByRole('dialog', { name: 'Review Telegram delivery', exact: true });
  await expect(
    dialog.getByText('Demo conversation reply — retained test text only.', { exact: true }),
  ).toBeVisible();
  await expect(dialog.getByText(/grouped across all message parts/)).toBeVisible();
  await dialog.getByRole('button', { name: 'I received it in Telegram', exact: true }).click();
  await expect(dialog.getByText('User reports received', { exact: true }).last()).toBeVisible();
  const detail = await (
    await request.get(`/api/v1/settings/messaging/telegram/deliveries/${fixture.id}`)
  ).json();
  expect(detail.status).toBe('uncertain');
  expect(detail.sent_parts).toBe(0);
  expect(detail.reviews.at(-1).native_confirmation).toBe(false);
});

test('Coinbase UI subscribes with the exact selected interval while REST fixtures remain offline', async ({
  page,
  request,
}) => {
  // This is a browser protocol fixture. No Coinbase REST or socket traffic leaves the test.
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get('source') !== 'coinbase') {
      await route.continue();
      return;
    }
    if (url.pathname === '/api/v1/markets/live') {
      await route.fulfill({
        contentType: 'application/x-ndjson',
        body:
          JSON.stringify({
            type: 'ticker',
            source: 'coinbase',
            price: 123.45,
            time_basis: 'provider_envelope',
            observed_at: new Date().toISOString(),
          }) + '\n',
      });
      return;
    }
    url.searchParams.set('source', 'demo');
    const response = await request.get(url.toString());
    await route.fulfill({ response });
  });
  const subscribe = page.waitForRequest(
    (r) => new URL(r.url()).pathname === '/api/v1/markets/live',
  );
  await page.goto('/markets?source=coinbase&symbol=BTC%2FUSDT&timeframe=5m');
  const first = new URL((await subscribe).url());
  expect(first.searchParams.get('source')).toBe('coinbase');
  expect(first.searchParams.get('timeframe')).toBe('5m');
  await expect(page.locator('.market-live-state')).not.toHaveText('REST snapshots');
  const next = page.waitForRequest(
    (r) =>
      new URL(r.url()).pathname === '/api/v1/markets/live' &&
      new URL(r.url()).searchParams.get('timeframe') === '1h',
  );
  await page.goto('/markets?source=coinbase&symbol=BTC%2FUSDT&timeframe=1h');
  expect(new URL((await next).url()).searchParams.get('source')).toBe('coinbase');
});
