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
    const tab = (await page.getByRole('tab', { name: 'UI/UX' }).boundingBox())!;
    expect(tab.x).toBeGreaterThanOrEqual(tabs.x);
    expect(tab.x + tab.width).toBeLessThanOrEqual(tabs.x + tabs.width);

    const surface = page.locator('.workspace-surface');
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await expect
      .poll(async () => {
        const bounds = (await surface.boundingBox())!;
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

test('page transitions follow the dock, persist, and respect reduced motion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.addInitScript(() => {
    const animate = Element.prototype.animate;
    Element.prototype.animate = function (keyframes, options) {
      if (
        Array.isArray(keyframes) &&
        this.matches('.page-view, .interface-motion-sample .interface-preview-content')
      ) {
        this.setAttribute('data-test-motion', JSON.stringify(keyframes[0]));
      }
      return animate.call(this, keyframes, options);
    };
  });

  await page.goto('/settings?tab=interface');
  const nav = page.getByRole('navigation', { name: 'Main navigation' });
  const view = page.locator('.page-view');
  const preview = page.locator('.interface-motion-sample .interface-preview-content');
  await expect(page.getByRole('tab', { name: 'UI/UX' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('radio', { name: /^Dock reveal/ })).toBeChecked();
  await expect(view).toHaveAttribute('data-test-motion', /"clipPath".*translateX/);
  await page.getByText('Bottom', { exact: true }).click();
  await page.getByRole('button', { name: 'Preview', exact: true }).click();
  await expect(preview).toHaveAttribute('data-test-motion', /"clipPath".*translateY/);
  await nav.getByRole('link', { name: 'Strategies', exact: true }).click();
  await expect(page).toHaveURL(/\/strategies$/);
  await expect(view).toHaveAttribute('data-test-motion', /"clipPath".*translateY/);

  for (const [label, firstFrame] of [
    ['Slide', /"transform":"translateY\(24px\)"/],
    ['Soft zoom', /"transform":"scale\(.96\)"/],
    ['Fade', /^\{"opacity":0\.25\}$/],
  ] as const) {
    await page.goto('/settings?tab=interface');
    await page.getByText(label, { exact: true }).click();
    await expect(preview).toHaveAttribute('data-test-motion', firstFrame);
    await nav.getByRole('link', { name: 'Strategies', exact: true }).click();
    await expect(view).toHaveAttribute('data-test-motion', firstFrame);
  }

  await page.goto('/settings?tab=interface');
  await page.reload();
  await expect(page.getByRole('radio', { name: /^Fade/ })).toBeChecked();

  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.reload();
  await expect(page.getByText('Your device has reduced motion enabled.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Preview', exact: true })).toBeHidden();
  await nav.getByRole('link', { name: 'Strategies', exact: true }).click();
  await expect(page).toHaveURL(/\/strategies$/);
  await expect(view).not.toHaveAttribute('data-test-motion', /.+/);
});
