import { expect, test } from '@playwright/test';

test.beforeEach(async ({ request }) => {
  const system = await (await request.get('/api/v1/system')).json();
  test.skip(
    system.mode !== 'demo' || system.allow_live_trading,
    'Requires an isolated Demo-only workspace.',
  );
});

test('backtest reference table and selectable equity overlay use actual API results', async ({
  page,
}) => {
  await page.goto('/strategies');
  const response = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname.startsWith('/api/v1/strategies/backtest') &&
      r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Run backtest', exact: true }).click();
  const result = await (await response).json();
  expect(Object.keys(result.benchmarks)).toHaveLength(4);
  await expect(page.getByText('Reference portfolios · same input & costs')).toBeVisible();
  await page.getByRole('button', { name: 'Equity & benchmark', exact: true }).click();
  await page.getByLabel('Reference portfolio', { exact: true }).selectOption('installments');
  await expect(page.locator('.backtest-chart-toolbar')).toContainText(
    'dashed Scheduled installments',
  );
  await expect(page.locator('.benchmark-comparison')).toContainText('Every 20 candles');
});

test('portable model import refits and archive/restore retains the selected research', async ({
  page,
  request,
}) => {
  const trained = await request.post('/api/v1/forecast-models', {
    data: { input_kind: 'demo', candles: 360, max_horizon: 7, label: 'Browser portable research' },
  });
  expect(trained.ok()).toBeTruthy();
  const original = (await trained.json()).model;
  const bundle = await (await request.get(`/api/v1/forecast-models/${original.id}/bundle`)).text();
  await page.goto(`/forecast?tab=models&model=${original.id}`);
  await page.getByText('Import a model from another workspace', { exact: true }).click();
  await page.getByLabel('Forecast bundle', { exact: true }).setInputFiles({
    name: 'model.json',
    mimeType: 'application/json',
    buffer: Buffer.from(bundle),
  });
  await page.getByRole('button', { name: 'Import & verify', exact: true }).click();
  await expect(page.getByText('Imported · unverified source', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Use latest matching feed', exact: true }),
  ).toBeDisabled();
  await page.getByRole('button', { name: 'Archive model', exact: true }).click();
  await expect(page.getByText('Archived model', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Show archived versions', { exact: true })).toBeChecked();
  await expect(
    page.getByRole('button', { name: 'Forecast saved input', exact: true }),
  ).toBeDisabled();
  await page.getByRole('button', { name: 'Restore model', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Forecast saved input', exact: true }),
  ).toBeEnabled();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export portable bundle', exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(/chronos-bundle-.*\.json/);
});

test('inbox export and opt-in retention controls are usable on narrow screens', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/alerts?tab=inbox');
  await page.getByText('History export & retention', { exact: true }).click();
  const controls = page.locator('.notification-history-controls');
  await expect(
    controls.getByText('Automatically clear old read notices', { exact: true }),
  ).toBeVisible();
  await expect(controls.getByLabel('Automatically clear old read notices')).not.toBeChecked();
  await controls.getByLabel('Notification kind').selectOption('order');
  const download = page.waitForEvent('download');
  await controls.getByRole('button', { name: 'Export CSV', exact: true }).click();
  expect((await download).suggestedFilename()).toBe('sibyl-notifications.csv');
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBeTruthy();
});

test('workspace displays actual scoped process resources', async ({ page }) => {
  await page.goto('/settings?tab=workspace');
  const metrics = page.getByRole('region', { name: 'Python process resources' });
  await expect(metrics).toContainText('Resident memory');
  await expect(metrics).toContainText('Database + WAL');
  await expect(metrics).toContainText('Current Python API process');
  await expect(metrics).not.toContainText('undefined');
});
