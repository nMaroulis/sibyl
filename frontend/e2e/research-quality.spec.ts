import { expect, test } from '@playwright/test';

test.beforeEach(async ({ request }) => {
  const system = await (await request.get('/api/v1/system')).json();
  test.skip(
    system.mode !== 'demo' || system.allow_live_trading,
    'Requires an isolated Demo-only workspace.',
  );
});

test('nested strategy selection uses the actual immutable backtest input and exposes inner evidence', async ({
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
    .getByRole('combobox', { name: 'Score candidates on', exact: true })
    .selectOption('nested');
  const saved = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === '/api/v1/strategies/validations' &&
      r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Run walk-forward test', exact: true }).click();
  const response = await saved;
  expect(response.ok(), await response.text()).toBeTruthy();
  const result = await response.json();
  expect(result.method).toBe('nested-next-open-v1');
  expect(result.folds[0].training_ranking[0].inner_results).toHaveLength(2);
  await expect(page.getByText('Demo · Nested walk-forward', { exact: true })).toBeVisible();
  await page.getByText('Selection ranking for window 1', { exact: true }).click();
  await page.getByText('Inner-window scores', { exact: true }).click();
  await expect(page.getByText('Mean inner return', { exact: true })).toBeVisible();
});

test('richer forecast features train and predict through the normal backend', async ({ page }) => {
  await page.goto('/forecast?tab=models');
  if (
    !(await page.getByRole('button', { name: 'Try with Demo prices', exact: true }).isVisible())
  ) {
    await page.getByRole('button', { name: 'Train model', exact: true }).click();
  }
  await page.getByText('Model settings & assumptions', { exact: true }).click();
  await page
    .getByRole('combobox', { name: 'Price features', exact: true })
    .selectOption('returns_context');
  await page
    .getByRole('combobox', { name: 'Maximum forecast horizon', exact: true })
    .selectOption('7');
  const trained = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === '/api/v1/forecast-models' && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Try with Demo prices', exact: true }).click();
  const response = await trained;
  expect(response.ok(), await response.text()).toBeTruthy();
  expect((await response.json()).model.parameters.feature_set).toBe('returns_context');
  await expect(page.getByText(/Returns \+ 6 context features/)).toBeVisible();
  await page.getByRole('button', { name: 'Forecast saved input', exact: true }).click();
  await expect(page.locator('.form-error')).toHaveCount(0);
});

test('retrieval quality lab saves real passage judgments, scores keyword search and exports evidence', async ({
  page,
  request,
}) => {
  const imported = await request.post('/api/v1/library/documents', {
    data: {
      filename: 'browser-quality.txt',
      data_base64: Buffer.from('A liquid reserve supports redemption obligations.').toString(
        'base64',
      ),
      title: 'Browser quality source',
    },
  });
  expect(imported.ok()).toBeTruthy();
  const source = await imported.json();
  await page.goto('/research?tab=library');
  await page.getByText('Retrieval quality lab', { exact: true }).click();
  await page
    .getByRole('textbox', { name: 'Suite title', exact: true })
    .fill(`Browser relevance ${Date.now()}`);
  await page
    .getByRole('textbox', { name: 'Question 1', exact: true })
    .fill('liquid reserve redemption');
  await page
    .getByRole('textbox', { name: 'Relevant passage IDs 1', exact: true })
    .fill(source.passages[0].id);
  const saved = page.waitForResponse(
    (r) => r.url().endsWith('/evaluations/suites') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Save judgments', exact: true }).click();
  const suite = await (await saved).json();
  await page.getByRole('button', { name: 'Run comparison', exact: true }).click();
  const report = page.getByRole('region', { name: 'Retrieval evaluation results' });
  await expect(report.getByText('completed', { exact: true })).toBeVisible({ timeout: 15000 });
  await expect(report.getByRole('cell', { name: 'keyword', exact: true })).toBeVisible();
  await page.getByText('Inspect query rankings and citations', { exact: true }).click();
  await expect(
    report.getByRole('link', { name: 'Browser quality source', exact: true }),
  ).toBeVisible();
  const downloaded = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export evidence', exact: true }).click();
  expect((await downloaded).suggestedFilename()).toMatch(/^sibyl-retrieval-.*\.json$/);
  await request.delete(`/api/v1/library/evaluations/suites/${suite.id}`);
});

test('Telegram review records user acknowledgment while preserving an uncertain native outcome', async ({
  page,
  request,
}) => {
  const history = await (
    await request.get('/api/v1/settings/messaging/telegram/deliveries')
  ).json();
  const fixture = history.items.find((item: { preview: string }) =>
    item.preview.startsWith('Demo review fixture'),
  );
  test.skip(!fixture, 'Requires an explicitly seeded unsent Demo receipt fixture.');
  await page.goto('/settings?tab=messaging');
  await page.getByText('Review Telegram deliveries', { exact: true }).click();
  await page.getByRole('button', { name: /Demo review fixture/ }).click();
  const dialog = page.getByRole('dialog', { name: 'Review Telegram delivery', exact: true });
  await expect(
    dialog.getByText('Demo review fixture — retained test message only.', { exact: true }),
  ).toBeVisible();
  await dialog.getByRole('button', { name: 'I received it in Telegram', exact: true }).click();
  await expect(dialog.getByText('User reports received', { exact: true }).last()).toBeVisible();
  const detail = await (
    await request.get(`/api/v1/settings/messaging/telegram/deliveries/${fixture.id}`)
  ).json();
  expect(detail.status).toBe('uncertain');
  expect(detail.sent_parts).toBe(0);
  expect(detail.reviews.at(-1).native_confirmation).toBe(false);
});
