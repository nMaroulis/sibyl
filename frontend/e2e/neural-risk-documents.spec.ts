import { expect, test } from '@playwright/test';

test.beforeEach(async ({ request }) => {
  const system = await (await request.get('/api/v1/system')).json();
  test.skip(
    system.mode !== 'demo' || system.allow_live_trading,
    'Requires isolated Demo-only workspace.',
  );
});
test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'wait' });
});

test('small neural model fits real Demo input and exposes training and independent evidence', async ({
  page,
  request,
}) => {
  const existing = await (await request.get('/api/v1/forecast-models')).json();
  await page.goto('/forecast?tab=models');
  if (existing.items.length)
    await expect(
      page.getByRole('combobox', { name: 'Saved model version', exact: true }),
    ).toBeVisible();
  else await expect(page.getByText('No models in this view', { exact: true })).toBeVisible();
  const train = page.getByRole('button', { name: 'Train model', exact: true });
  if (existing.items.length) await train.click();
  await page.getByText('Model settings & assumptions', { exact: true }).click();
  await page.getByRole('combobox', { name: 'Numerical model', exact: true }).selectOption('mlp');
  const horizon = page.getByRole('combobox', { name: 'Maximum forecast horizon', exact: true });
  await expect(horizon.locator('option')).toHaveCount(2);
  await horizon.selectOption('7');
  const response = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === '/api/v1/forecast-models' && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Try with Demo prices', exact: true }).click();
  const saved = await response;
  expect(saved.ok(), await saved.text()).toBeTruthy();
  const model = await saved.json();
  expect(model.model.parameters.family).toBe('mlp');
  expect(model.training).toHaveLength(7);
  await page.getByText('Neural training evidence', { exact: true }).click();
  await expect(page.getByRole('columnheader', { name: 'Final loss', exact: true })).toBeVisible();
  await expect(page.getByText('Trained neural model', { exact: true })).toBeVisible();
  await page.screenshot({
    path: '/tmp/sibyl-v230-next3/neural-ui.png',
    fullPage: true,
    animations: 'disabled',
  });
});

test('historical watch builder saves explicit assets and renders dated Demo basket evidence', async ({
  page,
  request,
}) => {
  await page.goto('/alerts?tab=risk');
  await page.getByRole('button', { name: 'New risk alert', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'New account risk alert', exact: true });
  await dialog.getByRole('combobox', { name: 'Watch for', exact: true }).selectOption('volatility');
  await dialog.getByRole('textbox', { name: /Basket assets/ }).fill('BTC, ETH');
  await dialog.getByRole('combobox', { name: 'Daily history', exact: true }).selectOption('60');
  await dialog
    .getByRole('spinbutton', { name: 'Annualized volatility limit · %', exact: true })
    .fill('10');
  const response = page.waitForResponse(
    (r) => new URL(r.url()).pathname === '/api/v1/risk-alerts' && r.request().method() === 'POST',
  );
  await dialog.getByRole('button', { name: 'Start watching', exact: true }).click();
  const saved = await response;
  expect(saved.ok(), await saved.text()).toBeTruthy();
  const rule = await saved.json();
  expect(rule.basket_assets).toEqual(['BTC', 'ETH']);
  const check = await request.post(`/api/v1/risk-alerts/${rule.id}/check`, { data: {} });
  expect(check.ok(), await check.text()).toBeTruthy();
  await page.goto(`/alerts?tab=risk&rule_id=${rule.id}`);
  const evidence = page.getByRole('dialog', { name: 'Valuation evidence', exact: true });
  await expect(evidence.getByText('Historical basket · BTC + ETH', { exact: true })).toBeVisible();
  await expect(evidence.getByText(/hypothetical daily-rebalanced historical basket/)).toBeVisible();
  await page.screenshot({
    path: '/tmp/sibyl-v230-next3/risk-ui.png',
    fullPage: true,
    animations: 'disabled',
  });
});

test('messaging exposes opt-in documents and original attachment receipts without sending', async ({
  page,
  request,
}) => {
  await page.goto('/settings?tab=messaging');
  const setting = page.getByRole('checkbox', {
    name: 'Send long replies as a text document',
    exact: true,
  });
  await expect(setting).toBeVisible();
  await setting.check();
  await page.getByText('Review Telegram deliveries', { exact: true }).click();
  await page.getByRole('combobox', { name: 'Delivery type', exact: true }).selectOption('reply');
  const rows = await (
    await request.get('/api/v1/settings/messaging/telegram/deliveries?kind=reply')
  ).json();
  const fixture = rows.items.find((r: { preview: string }) =>
    r.preview.startsWith('Demo document reply'),
  );
  test.skip(!fixture, 'Requires explicit unsent fixture.');
  await page.getByRole('button', { name: /Demo document reply/ }).click();
  const dialog = page.getByRole('dialog', { name: 'Review Telegram delivery', exact: true });
  await expect(
    dialog.getByText('Text document · sibyl-reply-43.txt', { exact: true }),
  ).toBeVisible();
  await expect(dialog.getByText('0/1 parts confirmed', { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBeTruthy();
  await page.screenshot({
    path: '/tmp/sibyl-v230-next3/document-ui.png',
    fullPage: true,
    animations: 'disabled',
  });
});
