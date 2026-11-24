import { expect, test } from '@playwright/test';

test('appearance and navigation choices apply immediately and survive reload', async ({ page }) => {
  await page.goto('/settings?tab=interface');
  const root = page.locator('html');
  const nav = page.getByRole('navigation', { name: 'Main navigation' });
  await expect(page.getByRole('radio', { name: 'Light' })).toBeChecked();
  await expect(root).toHaveCSS('color-scheme', 'light');
  await expect(page.getByRole('radio', { name: 'Bottom' })).toBeChecked();
  await expect(page.getByRole('switch', { name: 'Show labels' })).toBeChecked();
  await expect(nav.getByRole('link', { name: 'Markets' }).locator('.dock-label')).toBeVisible();
  await expect(page.getByRole('radio', { name: /^Soft zoom/ })).toBeChecked();
  await expect(nav).toHaveCSS('flex-direction', 'row');
  await expect(nav).toHaveCSS('position', 'fixed');

  await page.getByText('Dark', { exact: true }).click();
  await page.getByText('Left', { exact: true }).click();
  await expect(root).toHaveCSS('color-scheme', 'dark');
  await expect(nav).toHaveCSS('flex-direction', 'column');

  await page.reload();
  await expect(page.getByRole('radio', { name: 'Dark' })).toBeChecked();
  await expect(page.getByRole('radio', { name: 'Left' })).toBeChecked();
  await expect(nav).toHaveCSS('flex-direction', 'column');
  await nav.getByRole('link', { name: 'Sibyl', exact: true }).click();
  await expect(page).toHaveURL(/\/sibyl$/);
  await expect(root).toHaveCSS('color-scheme', 'dark');

  await page.goto('/settings?tab=interface');
  await page.getByText('Bottom', { exact: true }).click();
  await page.getByText('Light', { exact: true }).click();
  await expect(nav).toHaveCSS('flex-direction', 'row');
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
  await page.getByText('Left', { exact: true }).click();
  await expect(nav).toHaveCSS('flex-direction', 'column');
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
  await expect(page.getByRole('radio', { name: /^Soft zoom/ })).toBeChecked();
  await expect(view).toHaveAttribute(
    'data-test-motion',
    /"opacity":0\.45,"transform":"scale\(.96\)"/,
  );

  await page.getByText('Dock reveal', { exact: true }).click();
  const bottomCircle = /^\{"clipPath":"circle\(0px at [1-9][\d.]*px [1-9][\d.]*px\)"\}$/;
  await expect(preview).toHaveAttribute('data-test-motion', bottomCircle);
  await nav.getByRole('link', { name: 'Strategies', exact: true }).click();
  await expect(page).toHaveURL(/\/strategies$/);
  await expect(view).toHaveAttribute('data-test-motion', bottomCircle);

  await page.goto('/settings?tab=interface');
  await page.getByText('Left', { exact: true }).click();
  await page.getByRole('button', { name: 'Preview', exact: true }).click();
  const leftCircle = /^\{"clipPath":"circle\(0px at 0px [\d.]+px\)"\}$/;
  await expect(preview).toHaveAttribute('data-test-motion', leftCircle);
  await nav.getByRole('link', { name: 'Strategies', exact: true }).click();
  await expect(view).toHaveAttribute('data-test-motion', leftCircle);

  await page.goto('/settings?tab=interface');
  await page.getByText('Bottom', { exact: true }).click();
  for (const [label, firstFrame] of [
    ['Slide', /^\{"transform":"translateY\([1-9]\d*px\)"\}$/],
    ['Soft zoom', /"opacity":0\.45,"transform":"scale\(.96\)"/],
    ['Fade', /^\{"opacity":0\}$/],
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

test('dock finishes apply in both positions and survive reload', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/settings?tab=interface');
  const styles = page.getByRole('group', { name: 'Dock style' });
  const nav = page.getByRole('navigation', { name: 'Main navigation' });
  await expect(styles.getByRole('radio', { name: 'Glass', exact: true })).toBeChecked();

  const finishes = new Set<string>();
  for (const label of ['Glass', 'Porcelain', 'Graphite', 'Aurora']) {
    await styles.getByText(label, { exact: true }).click();
    await expect(nav).toHaveAttribute('data-dock-style', label.toLowerCase());
    await expect
      .poll(() => nav.evaluate((element) => getComputedStyle(element, '::before').backdropFilter))
      .toMatch(label === 'Glass' ? /^blur\(/ : /^none$/);
    finishes.add(
      await nav.evaluate((element) => {
        const style = getComputedStyle(element, '::before');
        return style.backgroundColor + style.backgroundImage;
      }),
    );
  }
  expect(finishes.size).toBe(4);

  await page.getByText('Left', { exact: true }).click();
  await page.getByText('Dark', { exact: true }).click();
  await page.reload();
  await expect(nav).toHaveCSS('flex-direction', 'column');
  await expect(nav).toHaveAttribute('data-dock-style', 'aurora');
  await expect(styles.getByRole('radio', { name: 'Aurora', exact: true })).toBeChecked();
});

test('unpinned pages move to More and Account stays pinned', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/settings?tab=interface');
  const shortcuts = page.getByRole('group', { name: 'Dock shortcuts' });
  const nav = page.getByRole('navigation', { name: 'Main navigation' });
  const account = shortcuts.getByRole('checkbox', { name: 'Account', exact: true });
  await expect(account).toBeChecked();
  await expect(account).toBeDisabled();
  await shortcuts.getByText('Trade', { exact: true }).click();
  await shortcuts.getByText('Research', { exact: true }).click();
  await expect(nav.getByRole('link', { name: 'Research', exact: true })).toBeVisible();
  await expect(nav.getByRole('link', { name: 'Trade', exact: true })).toHaveCount(0);

  await page.reload();
  await expect(shortcuts.getByRole('checkbox', { name: 'Trade', exact: true })).not.toBeChecked();
  await expect(shortcuts.getByRole('checkbox', { name: 'Research', exact: true })).toBeChecked();
  await nav.getByRole('button', { name: 'More tools' }).click();
  const more = nav.getByRole('group', { name: 'More destinations' });
  await expect(more.getByRole('link', { name: 'Research', exact: true })).toHaveCount(0);
  await more.getByRole('link', { name: 'Trade', exact: true }).click();
  await expect(page).toHaveURL(/\/trade$/);
  await expect(nav.getByRole('button', { name: 'More tools' })).toHaveAttribute(
    'data-current',
    'true',
  );
});

test('the dock fits narrow screens with only Account or every shortcut pinned', async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 600 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.addInitScript(() => {
    localStorage.setItem('sibyl.interface', JSON.stringify({ pinnedPaths: ['/unknown'] }));
  });
  await page.goto('/settings?tab=interface');
  const nav = page.getByRole('navigation', { name: 'Main navigation' });
  await expect(nav.getByRole('link', { name: 'Account', exact: true })).toBeVisible();
  await nav.getByRole('button', { name: 'More tools' }).click();
  const more = nav.getByRole('group', { name: 'More destinations' });
  await expect(more.getByRole('link')).toHaveCount(11);
  const bounds = (await more.boundingBox())!;
  expect(bounds.x).toBeGreaterThanOrEqual(0);
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(320);
  await page.setViewportSize({ width: 320, height: 280 });
  const lastLink = more.getByRole('link', { name: 'Coming soon' });
  await more.getByRole('link', { name: 'Sibyl', exact: true }).focus();
  await page.keyboard.press('End');
  await expect(lastLink).toBeFocused();
  await expect(lastLink).toBeInViewport({ ratio: 0.9 });
  expect(await more.evaluate((panel) => panel.scrollTop)).toBeGreaterThan(0);
  await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 320, height: 600 });

  const shortcuts = page.getByRole('group', { name: 'Dock shortcuts' });
  for (const checkbox of await shortcuts.getByRole('checkbox').all()) {
    if (await checkbox.isEnabled()) await checkbox.locator('..').click();
  }
  await expect(nav.getByRole('button', { name: 'More tools' })).toHaveCount(0);
  await expect(nav.getByRole('link')).toHaveCount(12);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(320);
});
