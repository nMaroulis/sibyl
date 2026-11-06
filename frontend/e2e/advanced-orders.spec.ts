import { expect, test, type Page } from '@playwright/test';

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'wait' });
});

/** Browser-only native-order fixtures: every exchange write is intercepted, never sent to a server. */
async function tradeFixture(page: Page, original = false) {
  const connection = {
    id: 'browser-testnet',
    exchange: 'binance-testnet',
    label: 'Browser Testnet',
    sandbox: true,
    active: true,
  };
  const order = {
    id: 'original',
    account: connection.label,
    exchange: connection.exchange,
    environment: 'test',
    sandbox: true,
    status: 'open',
    origin: 'sibyl',
    filled: 0,
    remaining: 0.001,
    price: 48000,
    notional: 48,
    tracking: true,
    exchange_order_id: 'native-original',
    client_order_id: 'original-client',
    confirmation: 'BUY BTC',
    expires_at: new Date(Date.now() + 60000).toISOString(),
    request: {
      connection_id: connection.id,
      symbol: 'BTC/USDT',
      side: 'buy',
      quantity: 0.001,
      order_type: 'limit',
      limit_price: 48000,
    },
  };
  const system = await (await page.request.get('/api/v1/system')).json();
  const writes: { path: string; body: Record<string, unknown> }[] = [];
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request(),
      url = new URL(request.url()),
      path = url.pathname.replace('/api/v1', '');
    if (request.method() === 'POST' && path.startsWith('/exchange-')) {
      const body = request.postDataJSON();
      writes.push({ path, body });
      let result: unknown;
      if (path === '/exchange-order-lists/preview')
        result = {
          id: 'group',
          status: 'preview',
          account: connection.label,
          environment: 'test',
          confirmation: 'OCO BTC/USDT',
          expires_at: order.expires_at,
          orders: [],
        };
      else if (path.endsWith('/replace/preview'))
        result = {
          ...order,
          id: 'replacement',
          status: 'preview',
          confirmation: 'REPLACE BTC/USDT',
          replacement_of: 'original',
        };
      else if (path === '/exchange-orders/preview')
        result = {
          ...order,
          id: 'conditional',
          status: 'preview',
          confirmation: 'BUY BTC',
          request: body,
        };
      else
        result = {
          ...order,
          status: 'submitted',
          message: 'Native test fixture submitted',
          orders: [],
          account: connection.label,
          environment: 'test',
        };
      return route.fulfill({ json: result });
    }
    if (request.method() !== 'GET')
      return route.fulfill({
        status: 403,
        json: { detail: 'Unmocked writes are forbidden in browser acceptance.' },
      });
    if (path === '/accounts')
      return route.fulfill({
        json: {
          mode: 'test',
          active_ids: [connection.id],
          accounts: [connection],
          signature: 'browser-testnet',
        },
      });
    if (path === '/connections') return route.fulfill({ json: [connection] });
    if (path === '/system') {
      return route.fulfill({ json: { ...system, allow_live_trading: true } });
    }
    if (path === '/exchange-orders/monitor')
      return route.fulfill({
        json: {
          items: original ? [order] : [],
          accounts: [connection],
          total: original ? 1 : 0,
          has_more: false,
        },
      });
    return route.continue();
  });
  return writes;
}

test('conditional entry keeps trigger and limit separate until explicit confirmation', async ({
  page,
}) => {
  const writes = await tradeFixture(page);
  await page.goto('/trade');
  await page
    .locator('.exchange-execution-grid')
    .getByRole('combobox', { name: 'Account', exact: true })
    .selectOption('browser-testnet');
  await page
    .getByRole('combobox', { name: 'Order type', exact: true })
    .selectOption('stop_loss_limit');
  await page.getByLabel(/Limit price · USDT/).fill('52000');
  await page.getByLabel(/Trigger price · USDT/).fill('51000');
  await page.getByRole('button', { name: 'Review exchange order', exact: true }).click();
  await expect(page.getByLabel('Type BUY BTC to confirm')).toBeVisible();
  expect(writes).toHaveLength(1);
  expect(writes[0].body).toMatchObject({
    order_type: 'stop_loss_limit',
    trigger_price: 51000,
    limit_price: 52000,
  });
  await expect(
    page.getByRole('button', { name: 'Confirm exchange stop loss limit order' }),
  ).toBeDisabled();
  await page.getByLabel('Type BUY BTC to confirm').fill('BUY BTC');
  await page.getByRole('button', { name: 'Confirm exchange stop loss limit order' }).click();
  await expect(page.getByText('Native test fixture submitted').first()).toBeVisible();
  expect(writes).toHaveLength(2);
});

test('OCO is progressive and changing the shared quantity invalidates its visible review', async ({
  page,
}) => {
  const writes = await tradeFixture(page);
  await page.goto('/trade');
  await page
    .locator('.exchange-execution-grid')
    .getByRole('combobox', { name: 'Account', exact: true })
    .selectOption('browser-testnet');
  const linked = page.locator('.advanced-order-disclosure');
  await expect(linked).not.toHaveAttribute('open');
  await linked.locator('summary').click();
  await linked.getByLabel(/Take-profit trigger \/ limit/).fill('45000');
  await linked.getByLabel(/Stop trigger/).fill('51000');
  await linked.getByLabel(/Stop limit/).fill('52000');
  await linked.getByRole('button', { name: 'Review linked orders' }).click();
  await expect(linked.getByLabel('Type OCO BTC/USDT')).toBeVisible();
  expect(writes).toHaveLength(1);
  await page.screenshot({ path: test.info().outputPath('oco-review.png'), fullPage: true });
  await page.getByLabel('Base asset quantity', { exact: true }).fill('0.002');
  await expect(linked.getByLabel('Type OCO BTC/USDT')).toHaveCount(0);
  expect(writes).toHaveLength(1);
});

test('replacement shows both non-atomic outcomes and requires a new typed review', async ({
  page,
}) => {
  const writes = await tradeFixture(page, true);
  await page.goto('/trade');
  await page.getByRole('button', { name: 'Replace…', exact: true }).click();
  const modal = page.getByRole('dialog', { name: 'Replace an unfilled limit' });
  await expect(modal).toContainText('Cancellation may succeed while the new order fails');
  await modal.getByLabel('New total base quantity').fill('0.002');
  await modal.getByRole('button', { name: 'Review replacement' }).click();
  await expect(modal.getByRole('button', { name: 'Confirm cancel / replace' })).toBeDisabled();
  expect(writes[0].body.quantity).toBe(0.002);
  await modal.getByLabel('Type REPLACE BTC/USDT').fill('REPLACE BTC/USDT');
  await modal.getByRole('button', { name: 'Confirm cancel / replace' }).click();
  await expect(modal).not.toBeVisible();
  expect(writes).toHaveLength(2);
});
