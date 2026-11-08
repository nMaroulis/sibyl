import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('health report is explicit, downloadable and preserves the exact observation', async ({
  page,
  request,
}) => {
  const system = await (await request.get('/api/v1/system')).json();
  test.skip(
    system.mode !== 'demo' || system.allow_live_trading,
    'Requires isolated Demo workspace.',
  );
  await page.goto('/settings?tab=workspace');
  const panel = page
    .locator('.workspace-health')
    .filter({ has: page.getByRole('heading', { name: 'Workspace health report', exact: true }) });
  await expect(
    panel.getByRole('button', { name: 'Download health report', exact: true }),
  ).toBeDisabled();
  const response = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === '/api/v1/workspace/diagnostics' &&
      r.request().method() === 'POST',
  );
  await panel.getByRole('button', { name: 'Run health check', exact: true }).click();
  const checked = await response;
  expect(checked.ok(), await checked.text()).toBeTruthy();
  const report = await checked.json();
  expect(report.database.status).toBe('passed');
  await expect(panel.getByText(report.database.note, { exact: true })).toBeVisible();
  const download = page.waitForEvent('download');
  await panel.getByRole('button', { name: 'Download health report', exact: true }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe('sibyl-health-report.json');
  expect(JSON.parse(await readFile((await file.path())!, 'utf8'))).toEqual(report);
  await page.screenshot({
    path: '/tmp/sibyl-release-health/ui.png',
    animations: 'disabled',
    fullPage: true,
  });
});
