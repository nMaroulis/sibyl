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

test('Account is home and shows a sourced portfolio and working date ranges', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByRole('heading', { name: 'Account', exact: true })).toBeVisible();
  const navigation = page.getByRole('navigation', { name: 'Main navigation' });
  await expect(navigation.getByRole('link', { name: 'Overview', exact: true })).toHaveCount(0);
  await expect(navigation.getByRole('link', { name: 'Connections', exact: true })).toHaveCount(0);
  await expect(navigation.getByRole('link', { name: 'Settings', exact: true })).toHaveCount(1);
  await expect(
    page.locator('.account-overview-label').getByText('Portfolio value', { exact: true }),
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

test('strategy studio runs a configured demo backtest through the API', async ({ page }) => {
  await page.goto('/strategies');
  const modes = page.getByRole('group', { name: 'Run mode' });
  await expect(modes.getByRole('radio')).toHaveCount(3);
  await expect(modes.getByRole('radio', { name: 'Backtest', exact: true })).toBeChecked();
  await expect(page.getByRole('radio', { name: /Deploy strategy/ })).not.toBeChecked();
  await expect(page.getByText('Account required', { exact: true })).toBeVisible();
  const help = page.getByRole('button', { name: 'Help for Amount' });
  const amountCaption = page.getByText(/Starting virtual capital for a backtest or paper run/);
  await expect(amountCaption).toBeHidden();
  await help.click();
  await expect(amountCaption).toBeVisible();
  await expect(page.getByText(/Caps the gross value of each order/)).toBeHidden();
  await help.click();
  await expect(amountCaption).toBeHidden();

  await page.getByRole('button', { name: /^Timeframe / }).click();
  const intervals = page.getByRole('dialog', { name: 'Timeframe options' });
  await intervals.getByRole('combobox', { name: 'Search timeframe' }).fill('4h');
  await intervals.getByRole('option', { name: /4 hours/ }).click();

  const market = page.locator('section.panel').filter({
    has: page.getByRole('heading', { name: '3. Set market and amount', exact: true }),
  });
  const pair = market.getByRole('button', { name: /^Spot pair / });
  const pairUse = pair.locator('.asset-pair-icon use');
  await expect(pairUse).toHaveCount(2);
  await expect(pairUse.nth(0)).toHaveAttribute('href', /#asset-btc$/);
  await expect(pairUse.nth(1)).toHaveAttribute('href', /#asset-usdt$/);
  await market.getByRole('button', { name: /^Indicator lookback / }).click();
  await page
    .getByRole('dialog', { name: 'Indicator lookback options' })
    .getByRole('option', { name: /365 candles/ })
    .click();
  const amount = market.getByRole('spinbutton', { name: 'Amount · USDT', exact: true });
  await amount.fill('2400');
  await page.getByText('Paper strategy', { exact: true }).click();
  await expect(modes.getByRole('radio', { name: 'Paper strategy', exact: true })).toBeChecked();
  await expect(modes.locator('input:checked')).toHaveCount(1);
  await expect(amount).toHaveValue('2400');
  await page.getByText('Backtest', { exact: true }).click();
  await expect(amount).toHaveValue('2400');
  const riskPanel = market.getByRole('group', { name: 'Risk & order limits' });
  const risk = riskPanel.getByRole('switch', { name: 'Custom exits' });
  const stopLoss = page.getByRole('spinbutton', { name: 'Stop loss · %' });
  const takeProfit = page.getByRole('spinbutton', { name: 'Take profit · %' });
  const exitLimit = page.getByRole('spinbutton', { name: 'Completed exit limit' });
  const backtest = page.getByRole('button', { name: 'Run backtest', exact: true });
  const orderCap = riskPanel.getByRole('spinbutton', { name: /^Maximum order value · USDT/ });
  const lossPause = riskPanel.getByRole('spinbutton', { name: /^Pause at allocated loss · %/ });
  await orderCap.fill('2500');
  await expect(backtest).toBeDisabled();
  await orderCap.fill('400');
  await lossPause.fill('12');
  await expect(page.getByRole('spinbutton', { name: 'Fee · basis points' })).toBeVisible();
  await expect(page.getByRole('combobox', { name: /Historical input|Backtest data/ })).toHaveCount(
    0,
  );
  await expect(risk).not.toBeChecked();
  await expect(stopLoss).toHaveCount(0);
  await risk.check();
  await expect(takeProfit).toBeVisible();
  await expect(exitLimit).toBeVisible();
  await expect(backtest).toBeEnabled();
  await stopLoss.fill('91');
  await expect(backtest).toBeDisabled();
  await risk.uncheck();
  await expect(stopLoss).toHaveCount(0);
  await expect(backtest).toBeEnabled();
  await risk.check();
  await expect(stopLoss).toHaveValue('91');
  await expect(backtest).toBeDisabled();
  await stopLoss.fill('5');
  const result = page.waitForResponse(
    (response) =>
      response.url().endsWith('/strategies/backtest/demo') &&
      response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Run backtest', exact: true }).click();
  const response = await result;
  expect(response.status()).toBe(200);
  expect(response.request().postDataJSON()).toMatchObject({
    timeframe: '4h',
    candles: 365,
    capital: 2400,
    stop_loss_pct: 5,
    backtest_limits: { max_order_quote: 400, max_loss_pct: 12 },
  });
  const saved = await response.json();
  expect(saved).toMatchObject({
    parameters: { stop_loss_pct: 5, take_profit_pct: null, max_trades: null },
  });
  await expect(page).toHaveURL(/\/strategies$/);
  const report = page.getByRole('region', { name: 'Backtest results' });
  await expect(report).toBeVisible();
  await expect(report.getByLabel('Saved backtest ID')).toHaveText(saved.id);
  await expect(report.getByText('Starting capital', { exact: true })).toBeVisible();
  await expect(report.getByText('2,400 USDT', { exact: true })).toBeVisible();
  await expect(report.getByText('Ending equity', { exact: true })).toBeVisible();
  await expect(report.getByText('Net P&L', { exact: true })).toBeVisible();
  const starting = report.locator('.backtest-balance-flow > div').filter({
    has: page.getByText('Starting capital', { exact: true }),
  });
  await expect(starting.getByText('Total return', { exact: true })).toBeVisible();
  await expect(report.getByText('Total return', { exact: true })).toHaveCount(1);
  await expect(report.getByText('Max drawdown', { exact: true })).toBeVisible();
  await report.getByText('More performance metrics', { exact: true }).click();
  await expect(report.getByText('Sortino ratio', { exact: true })).toBeVisible();
  await expect(report.getByRole('heading', { name: 'Simulated order limits' })).toBeVisible();
  await report.getByRole('button', { name: 'Ask Broker about this run' }).click();
  const broker = page.getByRole('dialog', { name: 'Ask Broker' });
  await broker.getByLabel('Message Broker').fill('What was the result of this backtest?');
  const question = page.waitForRequest((req) => req.url().endsWith('/agents/ask/stream'));
  await broker.getByRole('button', { name: 'Send message' }).click();
  expect((await question).postDataJSON()).toMatchObject({
    module: 'broker',
    context: { backtest_id: saved.id },
  });
  await broker.getByText('Inspect backtest_report evidence', { exact: true }).click();
  const evidence = broker.locator('.evidence-details pre');
  await expect(evidence).toContainText('"initial_capital": 2400');
  await expect(evidence).toContainText(saved.id);
  await expect(evidence).not.toContainText('drawdown_curve');
  await page.getByRole('button', { name: 'Close dialog' }).click();
  await report.getByRole('link', { name: 'View in Experiments' }).click();
  await expect(page).toHaveURL(new RegExp('view=experiments&backtest=' + saved.id));
  await page.reload();
  await expect(page.getByRole('combobox', { name: 'Open saved experiment' })).toHaveValue(saved.id);
  await expect(page.getByText('Starting capital', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Load settings' }).click();
  await expect(risk).toBeChecked();
  await expect(stopLoss).toHaveValue('5');
  await expect(amount).toHaveValue('2400');
  await expect(page.getByText('From saved dataset', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Use latest candles' }).click();
  await expect(page.getByRole('button', { name: /^Indicator lookback / })).toBeVisible();
  await expect(page.getByText('From saved dataset', { exact: true })).toHaveCount(0);
});

test('strategy picker keeps keyboard selection, guides and settings in sync', async ({ page }) => {
  await page.goto('/strategies');
  const picker = page.getByRole('group', { name: 'Strategy algorithm' });
  const first = picker.getByRole('radio', { name: 'EMA Crossover' });
  const rsi = picker.getByRole('radio', { name: 'RSI Reversion' });
  const preview = picker.locator('.strategy-picker-preview');
  const indicator = picker.locator('.strategy-picker-selection');

  await expect(first).toBeChecked();
  const startingPosition = await indicator.evaluate((element) => element.style.transform);
  await first.focus();
  await first.press('ArrowRight');
  await expect(rsi).toBeFocused();
  await expect(rsi).toBeChecked();
  await expect(preview.getByRole('heading', { name: 'RSI Reversion' })).toBeVisible();
  await expect(preview.getByText(/Wilder-smoothed RSI/)).toBeVisible();
  await expect
    .poll(() => indicator.evaluate((element) => element.style.transform))
    .not.toBe(startingPosition);

  const comparison = picker.locator('.strategy-picker-comparison');
  await expect(comparison).toHaveAttribute('inert', '');
  await picker.getByRole('button', { name: 'Compare algorithms' }).click();
  await expect(comparison.getByRole('heading')).toHaveCount(
    await picker.getByRole('radio').count(),
  );
  await expect(comparison.getByText(/Enter when RSI closes below the buy threshold/)).toBeVisible();
  await expect(rsi).toBeChecked();
  await picker.getByRole('button', { name: 'Hide comparison' }).click();
  await expect(comparison).toHaveAttribute('inert', '');

  await page.getByText('Advanced algorithm settings', { exact: true }).click();
  await expect(page.getByRole('spinbutton', { name: 'RSI period', exact: true })).toBeVisible();
  await expect(page.getByRole('spinbutton', { name: 'Fast EMA', exact: true })).toHaveCount(0);
});

test('strategy sizing uses the free quote balance of the selected account', async ({ page }) => {
  const accounts = ['A', 'B'].map((name) => ({
    id: 'sizing-' + name.toLowerCase(),
    exchange: 'binance-testnet',
    label: 'Wallet ' + name,
    provider_name: 'Binance Testnet',
    sandbox: true,
    active: true,
    supported: true,
  }));
  await page.route('**/api/v1/accounts', (route) =>
    route.fulfill({
      json: {
        mode: 'test',
        accounts,
        active_ids: accounts.map((account) => account.id),
        signature: 'sizing-test',
      },
    }),
  );
  await page.route('**/api/v1/strategies/exchange/options', (route) =>
    route.fulfill({
      json: {
        accounts,
        enabled: true,
        server_enabled: true,
        controls: { halted: false },
        handoff_sources: [],
      },
    }),
  );
  await page.route('**/api/v1/markets/symbols?source=*', (route) =>
    route.fulfill({
      json: {
        source: new URL(route.request().url()).searchParams.get('source'),
        timeframes: ['1d'],
        items: [
          { symbol: 'BTC/USDT', base: 'BTC', quote: 'USDT', name: 'Bitcoin' },
          { symbol: 'ETH/USDC', base: 'ETH', quote: 'USDC', name: 'Ethereum' },
        ],
      },
    }),
  );
  await page.route('**/api/v1/connections/sizing-*/balances', (route) => {
    const first = route.request().url().endsWith('sizing-a/balances');
    return route.fulfill({
      json: {
        items: [
          { asset: 'USDT', total: 5000, free: first ? 650 : 1800 },
          ...(!first ? [{ asset: 'USDC', total: 2400, free: null }] : []),
        ],
      },
    });
  });
  await page.goto('/strategies');
  const chooseAccount = async (name: string) => {
    await page.getByRole('button', { name: /Account or feed/ }).click();
    await page.getByRole('option', { name: new RegExp(name) }).click();
  };
  await chooseAccount('Wallet A');
  const balance = page.locator('#strategy-amount-balance');
  const amount = page.getByRole('spinbutton', { name: 'Amount · USDT', exact: true });
  await expect(balance).toContainText('650 USDT');
  const warning = page.locator('#strategy-amount-warning');
  const entry = page.locator('.strategy-amount-entry');
  await expect(warning).toHaveText(
    'Amount exceeds available USDT balance. This amount can only be used for a backtest or paper strategy.',
  );
  await expect(entry).toHaveAttribute('data-over-balance', 'true');
  await expect(amount).toHaveAttribute('aria-invalid', 'false');
  await expect(page.getByRole('button', { name: 'Run backtest', exact: true })).toBeEnabled();

  await page.getByText('Paper strategy', { exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Start paper strategy', exact: true }),
  ).toBeEnabled();
  await page.getByText('Deploy strategy', { exact: true }).click();
  const review = page.getByRole('button', { name: 'Review deployment', exact: true });
  await expect(amount).toHaveAttribute('aria-invalid', 'true');
  await expect(warning).toBeVisible();
  await expect(review).toBeDisabled();
  await amount.fill('650');
  await expect(warning).toHaveCount(0);
  await expect(entry).not.toHaveAttribute('data-over-balance', 'true');
  await expect(review).toBeEnabled();

  const choosePair = async (pair: string) => {
    await page.getByRole('button', { name: /^Spot pair / }).click();
    await page.getByRole('option', { name: new RegExp(pair) }).click();
  };
  await choosePair('ETH/USDC');
  await expect(balance).toContainText('0 USDC');
  await expect(review).toBeDisabled();

  await chooseAccount('Wallet B');
  await expect(balance).toHaveText('Free balance unavailable');
  await choosePair('BTC/USDT');
  await expect(balance).toContainText('1,800 USDT');
  await amount.fill('1500');
  await expect(review).toBeEnabled();
});

test('backtest custom dates use completed UTC candles and save the exact window', async ({
  page,
}) => {
  await page.goto('/strategies');
  const picker = page.getByRole('button', { name: /^Indicator lookback / });
  const submit = page.getByRole('button', { name: 'Run backtest', exact: true });
  await expect(page.getByRole('group', { name: 'Backtest dates · UTC' })).toHaveCount(0);
  await picker.click();
  await page.getByRole('option', { name: 'Custom dates', exact: true }).click();
  const dates = page.getByRole('group', { name: 'Backtest dates · UTC' });
  const end = new Date();
  end.setUTCHours(0, 0, 0, 0);
  end.setUTCDate(end.getUTCDate() - 5);
  const start = new Date(end.getTime());
  start.setUTCDate(start.getUTCDate() - 70);
  const input = (date: Date) => date.toISOString().slice(0, 16);
  await dates.getByLabel('From', { exact: true }).fill(input(start));
  await dates.getByLabel('Until', { exact: true }).fill(input(start));
  await expect(submit).toBeDisabled();
  await dates.getByLabel('Until', { exact: true }).fill(input(end));
  await expect(dates.getByRole('status')).toContainText('70 whole candles');
  const result = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith('/strategies/backtest/range'),
  );
  await submit.click();
  const response = await result;
  expect(response.status(), await response.text()).toBe(200);
  expect(await response.json()).toMatchObject({
    dataset: {
      source: 'demo',
      count: 70,
      start: input(start) + ':00+00:00',
      end: input(end) + ':00+00:00',
    },
  });
  await expect(page.getByRole('region', { name: 'Backtest results' })).toBeVisible();
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
  await page.getByRole('spinbutton', { name: /^Amount · USDT/ }).fill('2500');
  await page.getByRole('button', { name: 'Ask Broker', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Ask Broker' });
  await dialog.getByLabel('Message Broker').fill('Explain these simulation settings.');
  await dialog.getByRole('button', { name: 'Send message' }).click();
  await dialog.getByText('Inspect strategy_context evidence', { exact: true }).click();
  await expect(dialog.locator('.evidence-details pre')).toContainText('2500');
  await expect(dialog.locator('.evidence-details pre')).toContainText('"strategy": "rsi"');
  await dialog.getByRole('button', { name: 'Close dialog' }).click();
  await expect(page).toHaveURL(/strategies$/);
  await expect(page.getByRole('spinbutton', { name: /^Amount · USDT/ })).toHaveValue('2500');
});

test('knowledge search and exchange setup are accessible', async ({ page }) => {
  await page.goto('/research');
  await page.getByLabel('Search knowledge').fill('diversification');
  await expect(page.getByRole('heading', { name: 'Diversification', exact: true })).toBeVisible();
  await page.goto('/settings?tab=exchanges');
  await page.getByRole('button', { name: 'View Binance support', exact: true }).click();
  const exchange = page.getByRole('dialog');
  await expect(exchange).toBeVisible();
  await exchange.getByRole('tab', { name: 'Spot trading', exact: true }).click();
  await expect(exchange.getByText('Market buy & sell', { exact: true })).toBeVisible();
  await expect(
    exchange.getByText('Conditional limits / OCO / cancel-replace', { exact: true }),
  ).toBeVisible();
  await expect(exchange.getByText(/Native stop-loss\/take-profit GTC limits/)).toBeVisible();
  await exchange.getByRole('button', { name: 'Connect Binance', exact: true }).click();
  await expect(page.getByLabel('API key', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Close dialog' }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
});

test('navigation works on a narrow app viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByRole('heading', { name: 'Account', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'More tools' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const more = page.getByRole('group', { name: 'More destinations' });
  await expect(more.getByRole('link')).toHaveCount(4);
  await expect(more.getByRole('link', { name: 'Alerts', exact: true })).toBeVisible();
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
  await page.goto('/account');
  await expect(page.getByRole('heading', { name: 'Account balances', exact: true })).toBeVisible();
  await page.getByRole('combobox', { name: 'Value in', exact: true }).selectOption('BTC');
  await expect(page.getByRole('columnheader', { name: 'Value · BTC', exact: true })).toBeVisible();
  await page.goto('/roadmap?tab=future');
  const advancedOrders = page.getByRole('article').filter({
    has: page.getByRole('heading', { name: 'Advanced exchange orders', exact: true }),
  });
  await expect(advancedOrders.getByText('Coming soon', { exact: true })).toBeVisible();
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

test('Paper starts with the shared risk limits', async ({ page, request }) => {
  await page.goto('/strategies');
  await page.getByText('Paper strategy', { exact: true }).click();
  const risk = page.getByRole('group', { name: 'Risk & order limits' });
  await risk.getByRole('spinbutton', { name: /^Maximum order value/ }).fill('375');
  await risk.getByRole('spinbutton', { name: /^Pause at allocated loss/ }).fill('8');
  const started = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname.endsWith('/strategies/jobs/demo') &&
      response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Start paper strategy', exact: true }).click();
  const response = await started;
  expect(response.status(), await response.text()).toBe(201);
  const job = await response.json();
  try {
    expect(job.parameters.order_limits).toEqual({ max_order_quote: 375, max_loss_pct: 8 });
    await expect(
      page.getByRole('heading', { name: 'Strategy monitor', exact: true }),
    ).toBeVisible();
    await page.getByRole('tab', { name: 'Run parameters', exact: true }).click();
    const parameters = page.locator('.monitor-parameters');
    await expect(parameters.getByText('max order quote')).toBeVisible();
    await expect(parameters.getByText('375', { exact: true })).toBeVisible();
  } finally {
    await request.post(`/api/v1/strategies/jobs/${job.id}/stop`);
  }
});

test('switching to Monitor preserves the builder draft', async ({ page }) => {
  await page.goto('/strategies');
  await page.getByRole('spinbutton', { name: /^Amount · USDT/ }).fill('3210');
  await page.getByRole('tab', { name: /^Monitor/ }).click();
  await expect(
    page.getByRole('heading', { name: 'Your strategy runs', exact: true }),
  ).toBeVisible();
  await page.getByRole('tab', { name: 'Build strategy', exact: true }).click();
  await expect(page.getByRole('spinbutton', { name: /^Amount · USDT/ })).toHaveValue('3210');
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
  await expect(
    page.getByRole('button', { name: 'View Binance support', exact: true }),
  ).toBeVisible();
  await tabs.getByRole('tab', { name: 'AI models', exact: true }).click();
  await expect(page).toHaveURL(/settings\?tab=models$/);
  await page.getByRole('button', { name: 'Local', exact: true }).click();
  await page.getByRole('button', { name: /^Ollama/ }).click();
  await page
    .getByRole('combobox', { name: 'Model · optional', exact: true })
    .selectOption('__custom__');
  await page.getByLabel('Custom model ID', { exact: true }).fill('draft-model');
  await tabs.getByRole('tab', { name: 'Market data', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Market & research data', exact: true }),
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
  await expect(
    page.getByRole('button', { name: 'View Binance support', exact: true }),
  ).toBeVisible();
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

test('exchange category icons open exact implementation details', async ({ page }) => {
  await page.goto('/settings?tab=exchanges');
  const binance = page.getByRole('group', { name: 'Binance feature categories', exact: true });
  await expect(binance.getByRole('button')).toHaveCount(5);
  const account = binance.getByRole('button', {
    name: /^Account overview: All listed features implemented/,
  });
  await expect(account).toHaveClass(/coverage-supported/);
  await account.focus();
  await expect(account.getByRole('tooltip')).toBeVisible();
  await account.press('Escape');
  await expect(account.getByRole('tooltip')).not.toBeVisible();
  await account.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('tab', { name: 'Account overview', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await dialog.getByRole('button', { name: 'Close dialog' }).click();
  const gate = page.getByRole('group', { name: 'Gate feature categories', exact: true });
  const trading = gate.getByRole('button', {
    name: /^Spot trading: No listed features implemented/,
  });
  await expect(trading).toHaveClass(/coverage-unsupported/);
  await trading.click();
  await expect(dialog.getByRole('tab', { name: 'Spot trading', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(
    dialog.getByText('Trading is not implemented for this exchange', { exact: true }),
  ).toBeVisible();
});

test('old portfolio bookmarks retain account scopes', async ({ page }) => {
  await page.goto('/portfolio?scope=account%3Ademo#holdings');
  await expect(page).toHaveURL(/\/account\?scope=account%3Ademo#holdings$/);
  await expect(
    page
      .getByRole('navigation', { name: 'Main navigation' })
      .getByRole('link', { name: 'Account', exact: true }),
  ).toHaveAttribute('aria-current', 'page');
});
