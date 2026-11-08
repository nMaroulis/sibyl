import { expect, test } from '@playwright/test';

test.beforeEach(async ({ request }) => {
  const system = await (await request.get('/api/v1/system')).json();
  test.skip(
    system.mode !== 'demo' || system.allow_live_trading,
    'Requires an isolated Demo-only workspace.',
  );
});
test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'wait' });
});

test('Granger panel runs exact-source lag research and exports actual evidence', async ({
  page,
}) => {
  await page.goto('/markets?tab=correlation');
  const summary = page.getByText('Lag predictability · Granger analysis', { exact: true });
  await summary.click();
  const panel = summary.locator('..');
  await panel.getByRole('combobox', { name: 'Lag order', exact: true }).selectOption('3');
  const response = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === '/api/v1/markets/granger' && r.request().method() === 'POST',
  );
  await panel.getByRole('button', { name: 'Run lag analysis', exact: true }).click();
  const saved = await response;
  expect(saved.ok(), await saved.text()).toBeTruthy();
  const evidence = await saved.json();
  expect(evidence.source).toBe('demo');
  expect(evidence.lags).toBe(3);
  expect(evidence.observations).toBeGreaterThan(100);
  expect(evidence.items).toHaveLength(2 * (evidence.symbols.length - 1));
  await expect(panel.getByRole('columnheader', { name: 'Adjusted p', exact: true })).toBeVisible();
  await panel.getByText('Held-out errors & assumptions', { exact: true }).click();
  await expect(
    panel.getByRole('columnheader', { name: '+ Reference lags MAE', exact: true }),
  ).toBeVisible();
  const download = page.waitForEvent('download');
  await panel.getByRole('button', { name: 'Export lag evidence', exact: true }).click();
  expect((await download).suggestedFilename()).toBe('sibyl-granger-analysis.json');
  await panel.screenshot({ path: '/tmp/sibyl-v230-two/granger-ui.png', animations: 'disabled' });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await panel.evaluate((e) => {
      const bounds = e.getBoundingClientRect();
      const wrappers = [...e.querySelectorAll('.table-wrap')];
      return (
        bounds.right <= innerWidth &&
        e.scrollWidth <= e.clientWidth + 1 &&
        wrappers.every((t) => t.getBoundingClientRect().width <= bounds.width)
      );
    }),
  ).toBeTruthy();
});

test('installed momentum package backtests, replays and exports through real plugin API', async ({
  page,
  request,
}) => {
  const catalog = await (await request.get('/api/v1/strategies/plugins')).json();
  test.skip(
    !catalog.items.some(
      (p: { id: string; status: string }) => p.id === 'local-momentum' && p.status === 'ready',
    ),
    'Requires the reviewed example installed in the disposable environment.',
  );
  await page.goto('/strategies');
  const summary = page.getByText('Custom Python strategies', { exact: true });
  await summary.click();
  const workspace = summary.locator('..');
  await workspace
    .getByRole('combobox', { name: 'Custom algorithm', exact: true })
    .selectOption('local-momentum');
  await workspace.getByRole('spinbutton', { name: 'Momentum lookback', exact: true }).fill('8');
  await workspace.getByRole('spinbutton', { name: 'Return threshold · %', exact: true }).fill('0');
  const response = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === '/api/v1/strategies/plugins/backtests' &&
      r.request().method() === 'POST',
  );
  await workspace.getByRole('button', { name: 'Backtest custom strategy', exact: true }).click();
  const saved = await response;
  expect(saved.status(), await saved.text()).toBe(201);
  const run = await saved.json();
  expect(run.plugin.implementation.distribution).toBe('sibyl-momentum-example');
  expect(run.plugin.implementation.version).toBe('0.1.0');
  expect(run.source).toBe('demo');
  expect(run.fills.length).toBeGreaterThan(1);
  const result = page.getByRole('region', { name: 'Custom backtest results', exact: true });
  await expect(result.getByText('Demo · synthetic input', { exact: true })).toBeVisible();
  await expect(result.locator('.recharts-surface').first()).toBeVisible();
  const replay = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/plugins/backtests/${run.id}/rerun`) && r.request().method() === 'POST',
  );
  await result.getByRole('button', { name: 'Rerun exact custom input', exact: true }).click();
  const repeated = await replay;
  expect(repeated.status(), await repeated.text()).toBe(201);
  const data = await repeated.json();
  expect(data.signal_fingerprint).toBe(run.signal_fingerprint);
  expect(data.fills).toEqual(run.fills);
  const download = page.waitForEvent('download');
  await result.getByRole('button', { name: 'Export custom evidence', exact: true }).click();
  expect((await download).suggestedFilename()).toBe(`sibyl-custom-backtest-${data.id}.json`);
  await result.screenshot({ path: '/tmp/sibyl-v230-two/plugin-ui.png', animations: 'disabled' });
});
