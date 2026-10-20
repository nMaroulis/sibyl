import { expect, test } from '@playwright/test';

test.beforeEach(async ({ request }) => {
  const response = await request.get('/api/v1/system');
  expect(
    response.ok(),
    'Start the local API and dashboard before running browser tests.',
  ).toBeTruthy();
  const system = await response.json();
  test.skip(
    system.mode !== 'demo' || system.allow_live_trading,
    'Browser tests require a demo-only workspace.',
  );
});

test('portfolio is home and shows a sourced portfolio and working date ranges', async ({
  page,
}) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/portfolio$/);
  await expect(page.getByRole('heading', { name: 'Portfolio', exact: true })).toBeVisible();
  const navigation = page.getByRole('navigation', { name: 'Main navigation' });
  await expect(navigation.getByRole('link', { name: 'Overview', exact: true })).toHaveCount(0);
  await expect(navigation.getByRole('link', { name: 'Connections', exact: true })).toHaveCount(0);
  await expect(navigation.getByRole('link', { name: 'Settings', exact: true })).toHaveCount(1);
  await expect(
    page.locator('.summary-label').getByText('Portfolio value', { exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: '1W', exact: true }).click();
  await expect(page.getByRole('button', { name: '1W', exact: true })).toHaveClass(/selected/);
  await page.getByRole('button', { name: 'Hide balances', exact: true }).click();
  await expect(page.locator('.app')).toHaveClass(/private-mode/);
});

test('paper order review and fill update the virtual ledger', async ({ page }) => {
  await page.goto('/trade');
  await page.getByLabel('Quantity · BTC').fill('0.001');
  await page.getByRole('button', { name: 'Review paper order' }).click();
  await expect(page.getByText('Estimated debit', { exact: true })).toBeVisible();
  const fill = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/orders') && response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Confirm paper buy' }).click();
  expect((await fill).status()).toBe(201);
  await expect(
    page.getByText('Paper order filled. Your virtual balances have been updated.'),
  ).toBeVisible();
});

test('strategy studio runs a real API backtest', async ({ page }) => {
  await page.goto('/strategies');
  const result = page.waitForResponse(
    (response) =>
      response.url().endsWith('/strategies/backtest') && response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Run backtest', exact: true }).click();
  expect((await result).status()).toBe(200);
  await expect(page.getByText('Total return', { exact: true })).toBeVisible();
  await expect(page.getByText('Max drawdown', { exact: true })).toBeVisible();
});

test('module Ask opens in place, uses page context, and retains its conversation', async ({
  page,
}) => {
  await page.goto('/markets?asset=ETH');
  await page.getByRole('button', { name: 'Ask Analyst', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Ask Analyst' });
  await expect(dialog).toBeVisible();
  await expect(page).toHaveURL(/markets\?asset=ETH$/);
  await dialog.getByLabel('Message Analyst').fill('Explain the selected indicators.');
  await dialog.getByRole('button', { name: 'Send message' }).click();
  await expect(dialog.getByText('Tool snapshot', { exact: true })).toBeVisible();
  await dialog.getByText('Inspect market_analysis evidence', { exact: true }).click();
  await expect(dialog.locator('.evidence-details pre')).toContainText('ETH/USDT');
  await dialog.getByLabel('Message Analyst').fill('A draft to keep');
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
  await page.getByRole('button', { name: 'Ask Analyst', exact: true }).click();
  await expect(dialog.getByLabel('Message Analyst')).toHaveValue('A draft to keep');
  await expect(dialog.getByText('Tool snapshot', { exact: true })).toBeVisible();
});

test('Broker overlay reads the selected form without clearing or executing it', async ({
  page,
}) => {
  await page.goto('/strategies');
  await page.getByRole('button', { name: /RSI Reversion/ }).click();
  await page.getByLabel('Virtual capital · USDT').fill('2500');
  await page.getByRole('button', { name: 'Ask Broker', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Ask Broker' });
  await dialog.getByLabel('Message Broker').fill('Explain these simulation settings.');
  await dialog.getByRole('button', { name: 'Send message' }).click();
  await dialog.getByText('Inspect strategy_context evidence', { exact: true }).click();
  await expect(dialog.locator('.evidence-details pre')).toContainText('2500');
  await expect(dialog.locator('.evidence-details pre')).toContainText('"strategy": "rsi"');
  await dialog.getByRole('button', { name: 'Close dialog' }).click();
  await expect(page).toHaveURL(/strategies$/);
  await expect(page.getByLabel('Virtual capital · USDT')).toHaveValue('2500');
});

test('knowledge search and exchange setup are accessible', async ({ page }) => {
  await page.goto('/research');
  await page.getByLabel('Search knowledge').fill('diversification');
  await expect(page.getByRole('heading', { name: 'Diversification', exact: true })).toBeVisible();
  await page.goto('/settings?tab=exchanges');
  await page.getByRole('button', { name: 'Connect Binance', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByLabel('API key', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Close dialog' }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
});

test('navigation works on a narrow app viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.getByRole('button', { name: 'More tools' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const more = page.getByRole('group', { name: 'More destinations' });
  await expect(more.getByRole('link')).toHaveCount(3);
  await more.getByRole('link', { name: 'Research', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Research', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'More tools' })).toHaveAttribute(
    'aria-expanded',
    'false',
  );
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBeTruthy();
});

test('market controls change interval, chart type, and correlation method', async ({ page }) => {
  await page.goto('/markets');
  await page.getByLabel('Timeframe', { exact: true }).selectOption('4h');
  await expect(page.getByRole('img', { name: /OHLC candlestick chart/ })).toBeVisible();
  await page.getByRole('button', { name: 'Line', exact: true }).click();
  await expect(page.locator('.indicator-chart')).toBeVisible();
  await page.getByRole('tab', { name: 'Correlations', exact: true }).click();
  await page.getByLabel('Method', { exact: true }).selectOption('spearman');
  await expect(page.locator('.correlation-table')).toBeVisible();
  await expect(page.getByText('179 aligned observations · 4h', { exact: true })).toBeVisible();
});

test('account balances and future features have explicit boundaries', async ({ page }) => {
  await page.goto('/portfolio');
  await expect(page.getByRole('heading', { name: 'Account balances', exact: true })).toBeVisible();
  await page.getByLabel('Value in', { exact: true }).selectOption('BTC');
  await expect(page.getByRole('columnheader', { name: 'Value · BTC', exact: true })).toBeVisible();
  await page.goto('/roadmap');
  await expect(
    page.getByRole('heading', { name: 'Advanced exchange orders', exact: true }),
  ).toBeVisible();
  await expect(page.getByText('Coming soon', { exact: true })).toHaveCount(10);
});

test('news summaries and trading reports expose real data scope', async ({ page }) => {
  await page.goto('/news');
  await page.getByLabel('Summary', { exact: true }).selectOption('extractive');
  await expect(
    page.getByRole('heading', { name: 'The tone of this selection', exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/VADER scores headline and publisher-excerpt wording/)).toBeVisible();
  await page.goto('/reports');
  await expect(page).toHaveURL(/\/trade\?tab=executions$/);
  await expect(page.getByRole('heading', { name: 'Trade', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Matched paper P&L', exact: true })).toBeVisible();
});

test('Trade consolidates order entry and both histories without discarding drafts', async ({
  page,
}) => {
  await page.goto('/trade?asset=ETH');
  const tabs = page.getByRole('tablist', { name: 'Trade sections' });
  await expect(tabs.getByRole('tab')).toHaveCount(3);
  await page.getByLabel('Quantity · ETH', { exact: true }).fill('0.123');
  await page.getByRole('button', { name: 'Review paper order', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Confirm paper buy', exact: true })).toBeVisible();
  await tabs.getByRole('tab', { name: 'Executions', exact: true }).click();
  await page.getByLabel('Search', { exact: true }).fill('ETH');
  await tabs.getByRole('tab', { name: 'Account history', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Account fill ledger', exact: true }),
  ).toBeVisible();
  await tabs.getByRole('tab', { name: 'Executions', exact: true }).click();
  await expect(page.getByLabel('Search', { exact: true })).toHaveValue('ETH');
  await tabs.getByRole('tab', { name: 'Trade', exact: true }).click();
  await expect(page.getByLabel('Quantity · ETH', { exact: true })).toHaveValue('0.123');
  await expect(page.getByRole('button', { name: 'Confirm paper buy', exact: true })).toBeVisible();
});

test('previous account-history links retain filters and select the Trade dock item', async ({
  page,
}) => {
  await page.goto('/reports?tab=history&account=demo&side=sell&environment=demo');
  await expect(page).toHaveURL('/trade?tab=history&account=demo&side=sell&environment=demo');
  await expect(page.getByRole('tab', { name: 'Account history', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(page.getByRole('link', { name: 'Trade', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  );
  await expect(page.getByLabel('Account', { exact: true })).toHaveValue('demo');
  await expect(page.getByLabel('Side', { exact: true })).toHaveValue('sell');
  await expect(page.getByLabel('Environment', { exact: true })).toHaveValue('demo');
});

test('a strategy opens in its monitor with controls, journal, and fixed parameters', async ({
  page,
  request,
}) => {
  const started = await request.post('/api/v1/strategies/jobs', {
    data: { strategy: 'rsi', symbol: 'ETH/USDT', capital: 2500, timeframe: '1m' },
  });
  expect(started.status()).toBe(201);
  const job = await started.json();
  try {
    await page.goto(`/strategies?view=monitor&job=${job.id}`);
    await expect(
      page.getByRole('heading', { name: 'Strategy monitor', exact: true }),
    ).toBeVisible();
    await page.getByRole('tab', { name: 'Run parameters', exact: true }).click();
    await expect(
      page.getByRole('heading', { name: 'Parameters at launch', exact: true }),
    ).toBeVisible();
    await page.getByRole('tab', { name: /Decision journal/ }).click();
    await expect(page.getByRole('cell', { name: 'START', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Pause', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Resume', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Resume', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Pause', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Stop', exact: true }).click();
    await page
      .getByRole('dialog')
      .getByRole('button', { name: 'Stop paper strategy', exact: true })
      .click();
    await expect(page.getByText(/This run is stopped/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Resume', exact: true })).toHaveCount(0);
  } finally {
    await request.post(`/api/v1/strategies/jobs/${job.id}/stop`);
  }
});

test('switching to Monitor preserves the builder draft', async ({ page }) => {
  await page.goto('/strategies');
  await page.getByLabel('Virtual capital · USDT').fill('3210');
  await page.getByRole('tab', { name: /^Monitor/ }).click();
  await expect(
    page.getByRole('heading', { name: 'Your strategy runs', exact: true }),
  ).toBeVisible();
  await page.getByRole('tab', { name: 'Build & backtest', exact: true }).click();
  await expect(page.getByLabel('Virtual capital · USDT')).toHaveValue('3210');
});

test('Settings groups connections and configuration with persistent drafts and keyboard tabs', async ({
  page,
}) => {
  await page.goto('/settings');
  const tabs = page.getByRole('tablist', { name: 'Settings sections' });
  await expect(tabs.getByRole('tab', { name: 'Exchanges', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(page.getByRole('button', { name: 'Connect Binance', exact: true })).toBeVisible();
  await tabs.getByRole('tab', { name: 'AI models', exact: true }).click();
  await expect(page).toHaveURL(/settings\?tab=models$/);
  await page.getByRole('button', { name: 'Local', exact: true }).click();
  await page.getByRole('button', { name: /^Ollama/ }).click();
  await page.getByLabel('Model', { exact: true }).selectOption('__custom__');
  await page.getByLabel('Custom model ID', { exact: true }).fill('draft-model');
  await tabs.getByRole('tab', { name: 'Market data', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Prices & market history', exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel('Custom model ID', { exact: true })).not.toBeVisible();
  await page.goBack();
  await expect(page.getByLabel('Custom model ID', { exact: true })).toHaveValue('draft-model');
  await tabs.getByRole('tab', { name: 'AI models', exact: true }).focus();
  await page.keyboard.press('End');
  await expect(tabs.getByRole('tab', { name: 'Workspace', exact: true })).toBeFocused();
  await expect(page.getByLabel('Workspace API token', { exact: true })).toBeVisible();
  await page.keyboard.press('Home');
  await expect(tabs.getByRole('tab', { name: 'Exchanges', exact: true })).toBeFocused();
  await expect(page.getByRole('button', { name: 'Connect Binance', exact: true })).toBeVisible();
});

test('crypto profiles uses the backend catalog and keeps asset selection in the URL', async ({
  page,
}) => {
  await page.goto('/research?tab=crypto&asset=btc-bitcoin');
  await expect(page.getByRole('tab', { name: 'Crypto profiles', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(
    page.getByRole('group', { name: 'Cryptocurrency profiles' }).getByRole('button'),
  ).toHaveCount(20);
  await page.getByLabel('Search cryptocurrencies', { exact: true }).fill('Ethereum');
  await page.getByRole('button', { name: 'Read about Ethereum', exact: true }).click();
  await expect(page).toHaveURL(/asset=eth-ethereum/);
  await expect(
    page.locator('.crypto-name-row').getByRole('heading', { name: 'Ethereum', exact: true }),
  ).toBeVisible();
  await page.goBack();
  await expect(
    page.locator('.crypto-name-row').getByRole('heading', { name: 'Bitcoin', exact: true }),
  ).toBeVisible();
});
