import { expect, test } from '@playwright/test';

/** Read-only examples never activate an account or create a risk rule. */
test('risk preview preserves limits, saved evidence and mixed inbox attribution', async ({
  page,
}) => {
  await page.goto('/alerts?tab=risk');
  await page.getByRole('button', { name: 'View example', exact: true }).click();
  await expect(page.getByText('Illustrative example', { exact: true })).toBeVisible();
  const rule = page.locator('.risk-rule-card');
  await expect(rule).toContainText('Bitcoin allocation');
  await expect(rule).toContainText('64%');
  await expect(rule).toContainText('60%');
  await expect(rule).toContainText('Demo balances & prices');
  await expect(page.getByRole('button', { name: 'New risk alert', exact: true })).toBeDisabled();
  await expect(rule.getByRole('button', { name: 'Pause alert', exact: true })).toBeDisabled();
  await rule.getByRole('button', { name: 'View evidence', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Valuation evidence', exact: true });
  await expect(dialog).toContainText('Saved evidence · revision 1');
  await expect(dialog).toContainText('BTC → USDT');
  await expect(dialog).toContainText('60%');
  await dialog.getByRole('button', { name: 'Close dialog', exact: true }).click();
  await page.getByRole('tab', { name: 'Inbox', exact: true }).click();
  await expect(page.locator('.alert-inbox-item')).toHaveCount(4);
  await expect(page.locator('.alert-inbox-list')).toContainText('Risk limit reached');
  await expect(page.getByRole('button', { name: 'Mark all read', exact: true })).toBeDisabled();
});
