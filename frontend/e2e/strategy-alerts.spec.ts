import { expect, test } from '@playwright/test';

/** Examples use local GETs only; this test never starts a run or saves a real rule. */
test('strategy alert preview and mixed inbox remain explicitly illustrative', async ({ page }) => {
  await page.goto('/alerts?tab=strategies');
  await page.getByRole('button', { name: 'View example', exact: true }).click();
  await expect(page.getByText('Illustrative example', { exact: true })).toBeVisible();
  const rule = page.locator('.strategy-alert-card');
  await expect(rule).toContainText('My trend strategy');
  await expect(rule).toContainText('Paper execution');
  await expect(rule).toContainText('Demo');
  await expect(
    page.getByRole('button', { name: 'New strategy alert', exact: true }),
  ).toBeDisabled();
  await expect(rule.getByRole('button', { name: 'Pause alert', exact: true })).toBeDisabled();
  await expect(rule.getByRole('link', { name: 'Open monitor', exact: true })).toHaveAttribute(
    'aria-disabled',
    'true',
  );
  await expect(page.locator('.strategy-alert-example')).toContainText('Run paused');
  await page.getByRole('tab', { name: 'Inbox', exact: true }).click();
  await expect(page.locator('.alert-inbox-item')).toHaveCount(4);
  await expect(page.locator('.alert-inbox-list')).toContainText('Bitcoin milestone');
  await expect(page.locator('.alert-inbox-list')).toContainText('My trend strategy');
  await expect(page.getByRole('button', { name: 'Mark all read', exact: true })).toBeDisabled();
  await expect(page.getByRole('link', { name: 'Open strategy monitor', exact: true })).toHaveCount(
    0,
  );
  await page.getByRole('button', { name: 'Return to my alerts', exact: true }).click();
  await expect(page.getByText('Illustrative example', { exact: true })).toHaveCount(0);
});
