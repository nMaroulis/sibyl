import { expect, test } from '@playwright/test';

/** Read-only Demo feed; never changes workspace defaults or account permissions. */
test('region zoom and pan preserve full-sample market evidence', async ({ page }) => {
  await page.goto('/markets?source=demo');
  const chart = page.getByRole('img', { name: /OHLC candlestick chart/ });
  await expect(chart).toHaveAttribute('aria-label', /180 of 180/);
  await expect(page.getByRole('heading', { name: 'Market statistics', exact: true })).toBeVisible();
  const statistics = page.locator('#market-statistics');
  await expect(statistics).toContainText('180 consecutive candles');
  const sampleText = await statistics.innerText();
  // Keep the SVG fully in view before deriving the drag coordinates.
  await chart.scrollIntoViewIfNeeded();
  const box = await chart.boundingBox();
  expect(box).not.toBeNull();
  if (!box) throw new Error('Chart bounds unavailable');
  const drag = async (from: number, to: number) => {
    await page.mouse.move(box.x + box.width * from, box.y + box.height * 0.3);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * to, box.y + box.height * 0.7, { steps: 12 });
    await page.mouse.up();
  };
  await drag(0.25, 0.65);
  await expect(chart).not.toHaveAttribute('aria-label', /180 of 180/);
  const zoomed = await chart.getAttribute('aria-label');
  expect(await statistics.innerText()).toBe(sampleText);
  await page.getByRole('button', { name: 'Drag to pan chart', exact: true }).click();
  const position = page.getByRole('slider', { name: 'Chart window position', exact: true });
  const previous = await position.inputValue();
  await drag(0.35, 0.55);
  await expect(chart).toHaveAttribute('aria-label', zoomed!);
  await expect(position).not.toHaveValue(previous);
  await page.getByRole('button', { name: 'Reset chart view', exact: true }).click();
  await expect(chart).toHaveAttribute('aria-label', /180 of 180/);
  await page.getByRole('button', { name: 'Drag to select zoom region', exact: true }).click();
  await drag(0.65, 0.25);
  await expect(chart).toHaveAttribute('aria-label', zoomed!);
  await chart.dblclick();
  await expect(chart).toHaveAttribute('aria-label', /180 of 180/);
  await chart.focus();
  await page.keyboard.press('+');
  await expect(chart).not.toHaveAttribute('aria-label', /180 of 180/);
});

test('market readings disclose score weights, units, definitions and export provenance', async ({
  page,
}) => {
  await page.goto('/markets?source=demo&symbol=ETH%2FBTC');
  const statistics = page.locator('#market-statistics');
  await expect(statistics).toContainText('ETH/BTC');
  await expect(statistics).toContainText('chart zoom is visual only');
  await page.getByText('What makes this score?', { exact: true }).click();
  await expect(page.locator('.market-score-breakdown')).toContainText('25% weight');
  await expect(page.locator('.market-score-breakdown')).toContainText('not independent evidence');
  const risk = statistics
    .locator('.market-statistic-card')
    .filter({ has: page.getByRole('heading', { name: 'Historical risk', exact: true }) });
  await risk.locator('summary').click();
  await expect(risk).toContainText('Expected shortfall');
  await expect(risk).toContainText('One-candle horizon');
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export statistics', exact: true }).click();
  expect((await download).suggestedFilename()).toBe('sibyl-market-statistics.csv');
  await page.getByLabel('Observations', { exact: true }).selectOption('365');
  await expect(statistics).toContainText('365 consecutive candles');
  const sma = statistics
    .locator('dl > div')
    .filter({ has: page.getByText('SMA · 200', { exact: true }) });
  await expect(sma).not.toContainText('—');
});
