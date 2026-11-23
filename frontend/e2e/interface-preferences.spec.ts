import { expect, test } from '@playwright/test';

test('appearance and navigation choices apply immediately and survive reload', async ({ page }) => {
  await page.goto('/settings?tab=interface');
  const root = page.locator('html');
  const nav = page.getByRole('navigation', { name: 'Main navigation' });
  await expect(page.getByRole('radio', { name: 'Light' })).toBeChecked();
  await expect(page.getByRole('radio', { name: 'Left' })).toBeChecked();
  await expect(nav).toHaveCSS('flex-direction', 'column');

  await page.getByText('Dark', { exact: true }).click();
  await page.getByText('Bottom', { exact: true }).click();
  await expect(root).toHaveCSS('color-scheme', 'dark');
  await expect(nav).toHaveCSS('flex-direction', 'row');
  await expect(nav).toHaveCSS('position', 'fixed');

  await page.reload();
  await expect(page.getByRole('radio', { name: 'Dark' })).toBeChecked();
  await expect(page.getByRole('radio', { name: 'Bottom' })).toBeChecked();
  await nav.getByRole('link', { name: 'Sibyl', exact: true }).click();
  await expect(page).toHaveURL(/\/sibyl$/);
  await expect(root).toHaveCSS('color-scheme', 'dark');

  await page.goto('/settings?tab=interface');
  await page.getByText('Left', { exact: true }).click();
  await page.getByText('Light', { exact: true }).click();
  await expect(nav).toHaveCSS('flex-direction', 'column');
  await expect(root).toHaveCSS('color-scheme', 'light');
});

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 320, height: 600 },
]) {
  test(`bottom dock clears the end of the page at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.addInitScript(() => {
      localStorage.setItem('sibyl.interface', JSON.stringify({ navigation: 'bottom' }));
    });
    await page.goto('/settings?tab=interface');
    await expect(page.getByRole('radio', { name: 'Bottom' })).toBeChecked();
    const nav = page.getByRole('navigation', { name: 'Main navigation' });
    const dock = (await nav.boundingBox())!;
    expect(dock.x).toBeGreaterThan(0);
    expect(dock.x + dock.width).toBeLessThan(viewport.width);

    const tabs = (await page.getByRole('tablist', { name: 'Settings sections' }).boundingBox())!;
    const tab = (await page.getByRole('tab', { name: 'Interface' }).boundingBox())!;
    expect(tab.x).toBeGreaterThanOrEqual(tabs.x);
    expect(tab.x + tab.width).toBeLessThanOrEqual(tabs.x + tabs.width);

    const footer = page.getByRole('contentinfo');
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await expect
      .poll(async () => {
        const bounds = (await footer.boundingBox())!;
        return bounds.y + bounds.height;
      })
      .toBeLessThan(dock.y);
    expect((await nav.boundingBox())!.y).toBeCloseTo(dock.y);

    const more = nav.getByRole('button', { name: 'More tools' });
    await more.focus();
    await more.press('ArrowUp');
    await expect(more).toHaveAttribute('aria-expanded', 'true');
    const menu = page.getByRole('group', { name: 'More destinations' });
    const panel = (await menu.boundingBox())!;
    expect(panel.y + panel.height).toBeLessThan(dock.y);
    await expect(menu.getByRole('link', { name: 'Agents' })).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(menu).toBeHidden();
    await expect(more).toBeFocused();
  });
}

test('navigation labels can be hidden in either dock and restored after reload', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/settings?tab=interface');
  const showLabels = page.getByRole('switch', { name: 'Show labels' });
  const nav = page.getByRole('navigation', { name: 'Main navigation' });
  const marketLabel = nav.getByRole('link', { name: 'Markets' }).locator('.dock-label');
  await expect(showLabels).toBeChecked();
  await expect(marketLabel).toBeVisible();

  await showLabels.click();
  await expect(showLabels).not.toBeChecked();
  await expect(marketLabel).toBeHidden();
  await expect(nav.getByRole('link', { name: 'Settings' }).locator('.dock-icon')).toHaveCSS(
    '--dock-center-shift',
    '0px',
  );

  await page.getByText('Bottom', { exact: true }).click();
  await expect(nav).toHaveCSS('flex-direction', 'row');
  await expect(marketLabel).toBeHidden();
  await nav.getByRole('button', { name: 'More tools' }).click();
  const agents = nav.getByRole('link', { name: 'Agents' });
  await expect(agents).toBeVisible();
  await expect(agents.locator('.dock-label')).toBeHidden();

  await page.reload();
  await expect(showLabels).not.toBeChecked();
  await expect(marketLabel).toBeHidden();
  await showLabels.focus();
  await showLabels.press('Space');
  await expect(showLabels).toBeChecked();
  await expect(marketLabel).toBeVisible();
});
