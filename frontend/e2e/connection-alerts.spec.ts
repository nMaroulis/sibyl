import { expect, test } from '@playwright/test';

/** This preview only reads examples; it never saves a rule or probes an exchange. */
test('connection alert preview explains read evidence and joins the mixed inbox', async ({
  page,
}) => {
  await page.goto('/alerts?tab=connections');
  await page.getByRole('button', { name: 'View example', exact: true }).click();
  await expect(page.getByText('Illustrative example', { exact: true })).toBeVisible();
  const card = page.locator('.strategy-alert-card');
  await expect(card).toContainText('My price feed');
  await expect(card).toContainText('3 consecutive failed reads');
  await expect(card).toContainText('Awaiting successful reads');
  await expect(
    page.getByRole('button', { name: 'New connection alert', exact: true }),
  ).toBeDisabled();
  await expect(card.getByRole('button', { name: 'Pause alert', exact: true })).toBeDisabled();
  await expect(page.locator('.strategy-alert-example')).toContainText('Read failures observed');
  await page.getByRole('tab', { name: 'Inbox', exact: true }).click();
  await expect(page.locator('.alert-inbox-item')).toHaveCount(4);
  await expect(page.locator('.alert-inbox-list')).toContainText('My price feed');
  await expect(page.locator('.alert-inbox-list')).toContainText('Transport read 3');
  await expect(page.getByRole('button', { name: 'Mark all read', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Return to my alerts', exact: true }).click();
  await expect(page.getByText('Illustrative example', { exact: true })).toHaveCount(0);
});
