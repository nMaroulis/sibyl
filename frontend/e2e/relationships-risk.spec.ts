import { readFile } from 'node:fs/promises';
import { expect, test } from '@playwright/test';

test.beforeEach(async ({ request }) => {
  const system = await (await request.get('/api/v1/system')).json();
  test.skip(
    system.mode !== 'demo' || system.allow_live_trading,
    'Requires an isolated Demo-only workspace.',
  );
});

test('distance matrix and return regression use the real comparison API and export evidence', async ({
  page,
}) => {
  await page.goto('/markets?source=demo');
  await page.getByRole('tab', { name: 'Correlations', exact: true }).click();
  const response = page.waitForResponse(
    (r) =>
      r.url().includes('/markets/correlation?') &&
      new URL(r.url()).searchParams.get('method') === 'distance',
  );
  await page.getByRole('combobox', { name: 'Method', exact: true }).selectOption('distance');
  const evidence = await (await response).json();
  expect(evidence.regression.observations).toBeGreaterThan(30);
  await expect(page.locator('.correlation-table')).toBeVisible();
  await page
    .getByText(`Return regression · reference ${evidence.regression.reference}`, { exact: true })
    .click();
  const analysis = page.locator('.return-relationships');
  await expect(analysis).toContainText('This intercept is not CAPM alpha.');
  await analysis
    .getByLabel('Inspect return pair')
    .selectOption(evidence.regression.items[1].target);
  await expect(analysis.getByRole('img', { name: /log returns with fitted line/ })).toHaveAttribute(
    'aria-label',
    new RegExp(evidence.regression.items[1].target),
  );
  const download = page.waitForEvent('download');
  await analysis.getByRole('button', { name: 'Export regression evidence', exact: true }).click();
  const downloaded = await download;
  expect(downloaded.suggestedFilename()).toBe('sibyl-return-regression.json');
  const exported = JSON.parse(await readFile((await downloaded.path())!, 'utf8'));
  expect(exported.source).toBe('demo');
  expect(exported.timeframe).toBe('1d');
  expect(exported.reference).toBe(evidence.regression.reference);
  await page.getByRole('button', { name: 'Ask Analyst', exact: true }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Ask Analyst', exact: true });
  await dialog.getByLabel('Message Analyst').fill('Explain the selected comparison.');
  const request = page.waitForRequest(
    (r) => r.url().includes('/api/v1/agents/ask') && r.method() === 'POST',
  );
  await dialog.getByRole('button', { name: 'Send message', exact: true }).click();
  const payload = (await request).postDataJSON();
  expect(payload.context.correlation_method).toBe('distance');
  expect(payload.context.comparison_symbols).toEqual(evidence.symbols);
});

test('account diversification stays compact and discloses its limits on mobile', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/account');
  const details = page.locator('.portfolio-diversification');
  await expect(details.locator('summary')).toContainText('effective assets');
  await details.locator('summary').click();
  await expect(details).toContainText('HHI · 0–100');
  await expect(details).toContainText('not measure correlations');
  await expect(details.locator('.diversification-grid > div')).toHaveCount(3);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBeTruthy();
});

test('HHI risk setup saves a real passive Demo rule with correct units', async ({
  page,
  request,
}) => {
  await page.goto('/alerts?tab=risk');
  await page.getByRole('button', { name: 'New risk alert', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('combobox', { name: 'Watch for', exact: true }).selectOption('hhi');
  await dialog.getByLabel('HHI limit · 0–100', { exact: true }).fill('90');
  await dialog
    .getByPlaceholder('Asset concentration HHI', { exact: true })
    .fill(`Browser HHI ${Date.now()}`);
  const saved = page.waitForResponse(
    (r) => r.url().endsWith('/api/v1/risk-alerts') && r.request().method() === 'POST',
  );
  await dialog.getByRole('button', { name: 'Start watching', exact: true }).click();
  const response = await saved;
  expect(response.status()).toBe(201);
  const rule = await response.json();
  expect(rule.metric).toBe('hhi');
  const card = page.locator('.risk-rule-card').filter({ hasText: rule.label });
  await expect(card).toContainText('90 / 100');
  await expect(card).toContainText('Demo');
  const archived = await request.post(`/api/v1/risk-alerts/${rule.id}/action`, {
    data: { action: 'archive', revision: rule.revision },
  });
  expect(archived.ok()).toBeTruthy();
});

test('exchange support exposes new fill and Kraken stream capabilities without claiming recovery', async ({
  page,
}) => {
  await page.goto('/settings?tab=exchanges');
  for (const exchange of ['Bitstamp', 'Gemini']) {
    await page.getByRole('button', { name: `View ${exchange} support`, exact: true }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByRole('tab', { name: 'History & synchronization', exact: true }).click();
    const history = dialog
      .locator('.exchange-feature')
      .filter({ hasText: 'Resumable trade imports' });
    await expect(history).toContainText('Supported');
    await expect(dialog).toContainText('Match native fills and fees');
    await expect(dialog).toContainText('Automatic client-ID recovery is pending');
    await dialog.getByRole('button', { name: 'Close dialog', exact: true }).click();
  }
  await page.getByRole('button', { name: 'View Kraken support', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('tab', { name: 'Market data', exact: true }).click();
  await expect(dialog).toContainText(
    'Kraken supports native intervals and labels local receipt timing',
  );
});
