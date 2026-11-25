import { expect, test } from '@playwright/test';
import type { MessagingSettingsData } from '../src/components/messaging-settings';

test('enabled messaging cards lead the page and their monitors update without a reload', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  const initial = await request.get('/api/v1/settings/messaging');
  expect(initial.ok()).toBeTruthy();
  const settings: MessagingSettingsData = await initial.json();
  const telegram = settings.channels.find(({ id }) => id === 'telegram')!;
  const discord = settings.channels.find(({ id }) => id === 'discord')!;
  const at = Date.now() / 1000;
  Object.assign(telegram, {
    enabled: true,
    has_token: true,
    has_started: true,
    connected: true,
    last_poll_at: at,
  });
  Object.assign(discord, { enabled: true, configured: true, connected: true });
  settings.telegram!.activity = [
    {
      id: 'message-17',
      kind: 'message',
      state: 'pending',
      at,
      total_parts: 2,
      accepted_parts: 1,
    },
    { id: 'alert', kind: 'alert', state: 'uncertain', at: at - 20 },
    { id: 'message-38', kind: 'message', state: 'failed', at: at - 40 },
    { id: 'briefing', kind: 'briefing', state: 'skipped', at: at - 2 * 86400 },
  ];
  settings.telegram!.summary = { messages_received: 13, replies_delivered: 8, replies_waiting: 1 };
  settings.telegram!.updates = { failed: 5 };
  await page.route('**/api/v1/settings/messaging/channels/telegram/activity/17', (route) =>
    route.fulfill({
      json: {
        state: 'completed',
        received_at: at,
        parts: [{ part: 0, state: 'sent', attempts: 1, next_attempt: 0 }],
      },
    }),
  );
  const revision = 'a'.repeat(32);
  settings.telegram!.logs = { entries: 2, bytes: 1200, revision };
  await page.route('**/api/v1/settings/messaging/channels/telegram/activity/38', (route) =>
    route.fulfill({
      json: {
        state: 'failed',
        received_at: at - 40,
        parts: [],
        failure: {
          code: 'context_limit',
          provider: 'ollama',
          estimated_tokens: 4000,
          prompt_tokens: 1000,
        },
      },
    }),
  );
  await page.route('**/api/v1/settings/messaging/channels/telegram/logs?**', async (route) => {
    if (route.request().method() === 'DELETE') {
      settings.telegram!.logs = { entries: 0, bytes: 0, revision };
      settings.telegram!.activity = settings.telegram!.activity!.filter(
        (event) => event.kind !== 'message',
      );
      await route.fulfill({ json: { ...settings.telegram!.logs, cleared: 2 } });
      return;
    }
    await route.fulfill({
      json: {
        ...settings.telegram!.logs,
        items: settings.telegram!.activity!.filter((event) => event.kind === 'message'),
      },
    });
  });
  await page.route('**/api/v1/settings/messaging/telegram/check', (route) =>
    route.fulfill({ json: settings }),
  );
  await page.route('**/api/v1/settings/messaging/telegram/stop', async (route) => {
    telegram.enabled = false;
    telegram.stopped = true;
    await route.fulfill({ json: settings });
  });
  await page.route('**/api/v1/settings/messaging/telegram/enable', async (route) => {
    telegram.enabled = true;
    telegram.stopped = false;
    await route.fulfill({ json: settings });
  });
  await page.route('**/api/v1/settings/messaging/channels/*/timeline?**', (route) => {
    const url = new URL(route.request().url());
    const window = url.searchParams.get('window')!;
    const duration: Record<string, number> = {
      '1h': 3600,
      '1d': 86400,
      '1w': 604800,
      '30d': 2592000,
    };
    const events = url.pathname.endsWith('/telegram/timeline')
      ? settings.telegram!.activity!.filter(
          (event) => window === 'all' || event.at >= at - duration[window],
        )
      : [];
    return route.fulfill({
      json: {
        window,
        start:
          window === 'all'
            ? Math.min(at - 60, ...events.map((event) => event.at))
            : at - duration[window],
        end: at + 1,
        events,
        bins: [
          { count: events.length, attention: false },
          ...Array.from({ length: 35 }, () => ({ count: 0, attention: false })),
        ],
      },
    });
  });
  await page.route('**/api/v1/settings/messaging', (route) => route.fulfill({ json: settings }));
  await page.route('**/api/v1/settings/messaging/telegram/pause', async (route) => {
    telegram.enabled = false;
    await route.fulfill({ json: settings });
  });

  await page.goto('/settings?tab=messaging');
  const cards = page.locator('.messaging-grid h3');
  await expect(cards.nth(0)).toHaveText('Telegram');
  await expect(cards.nth(1)).toHaveText('Discord');
  const monitor = page.getByRole('region', { name: 'Telegram activity monitor' });
  await expect(monitor.getByText('Live', { exact: true })).toBeVisible();
  await expect(monitor.getByText('Delivery queued', { exact: true })).toBeVisible();
  await expect(monitor.getByText('1 of 2 reply parts accepted')).toBeVisible();
  await expect(monitor.getByText('Unconfirmed', { exact: true })).toBeVisible();
  await expect(monitor.getByRole('heading', { name: 'Live activity' })).toBeVisible();
  await expect(monitor.getByLabel('Telegram counts')).toContainText('13');
  await expect(page.getByText(/requests could not be answered/)).toHaveCount(0);
  await expect(page.getByText('Bot checked', { exact: true })).toHaveCount(0);
  await expect(monitor.getByRole('button', { name: 'Check Telegram status' })).toHaveAttribute(
    'aria-description',
    'Connection verified.',
  );
  await monitor
    .getByRole('button', { name: /View message log from/ })
    .first()
    .click();
  const log = page.getByRole('dialog', { name: 'Message log' });
  await expect(log.getByText('Processing completed')).toBeVisible();
  await expect(log.getByText('Accepted by provider')).toBeVisible();
  await expect(log.getByText('1 attempt')).toBeVisible();
  await log.getByRole('button', { name: 'Close dialog' }).click();
  const check = page.waitForResponse('**/api/v1/settings/messaging/telegram/check');
  await monitor.getByRole('button', { name: 'Check Telegram status' }).click();
  await check;
  await expect(monitor.getByText('Live', { exact: true })).toBeVisible();

  await expect(monitor.getByRole('listitem')).toHaveCount(3);
  const earlier = monitor.getByRole('button', { name: 'Show 1 earlier event' });
  await earlier.click();
  await expect(monitor.getByText('Briefing delivery')).toBeVisible();
  await monitor.getByRole('button', { name: 'Show fewer events' }).click();
  await expect(monitor.getByRole('listitem')).toHaveCount(3);

  const trace = monitor.locator('.channel-activity-trace-track');
  const ranges = monitor.getByRole('group', { name: 'Timeline range' });
  await expect(ranges.getByRole('button', { name: 'All time' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(monitor.getByText('4 events', { exact: true })).toBeVisible();
  await ranges.getByRole('button', { name: '1h', exact: true }).click();
  await expect(monitor.getByText('3 events', { exact: true })).toBeVisible();
  await expect(monitor.getByText('Briefing delivery')).toHaveCount(0);
  await ranges.getByRole('button', { name: '1w', exact: true }).click();
  await expect(monitor.getByText('4 events', { exact: true })).toBeVisible();
  await ranges.getByRole('button', { name: 'All time' }).click();
  await expect(trace.locator('[data-recorded="true"]')).toHaveCount(1);
  const sweep = () =>
    trace.evaluate((element) => getComputedStyle(element, '::before').animationName);
  expect(await sweep()).toBe('channel-trace-sweep');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  expect(await sweep()).toBe('none');
  await expect(page.getByRole('region', { name: 'Discord activity monitor' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'WhatsApp activity monitor' })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);

  Object.assign(settings.telegram!.activity[0], { state: 'sent', accepted_parts: 2 });
  await expect(monitor.getByText('Provider accepted', { exact: true })).toBeVisible({
    timeout: 8000,
  });
  await expect(monitor.getByText('2 of 2 reply parts accepted')).toBeVisible();

  await page.getByRole('button', { name: 'Pause Telegram' }).click();
  await expect(cards.nth(0)).toHaveText('Discord');
  await expect(monitor.getByText('Paused', { exact: true })).toBeVisible();
  await expect(
    monitor.getByRole('button', { name: /View message log from/ }).first(),
  ).toBeVisible();
  await monitor.getByRole('button', { name: 'Resume Telegram' }).click();
  await expect(cards.nth(0)).toHaveText('Telegram');
  await monitor.getByRole('button', { name: 'Stop Telegram' }).click();
  const confirm = page.getByRole('dialog', { name: 'Stop Telegram?' });
  await expect(confirm.getByText(/clears queued messages/)).toBeVisible();
  await confirm.getByRole('button', { name: 'Stop listener' }).click();
  await expect(monitor.getByText('Stopped', { exact: true })).toBeVisible();
  await expect(monitor.getByRole('button', { name: 'Start Telegram' })).toBeVisible();
  await expect(monitor.getByText('2 entries · 1.2 KiB in DB')).toBeVisible();
  await monitor.getByRole('button', { name: 'Message logs' }).click();
  await page
    .getByRole('dialog', { name: 'Telegram message logs' })
    .getByRole('button', { name: /failed/i })
    .click();
  await expect(log.getByText('The request exceeded Sibyl’s context allowance')).toBeVisible();
  await expect(
    log.getByText('Prompt estimate 4,000 tokens · allowance 1,000 tokens.'),
  ).toBeVisible();
  await log.getByRole('button', { name: 'Close dialog' }).click();
  await page
    .getByRole('dialog', { name: 'Telegram message logs' })
    .getByRole('button', { name: 'Close dialog' })
    .click();
  await monitor.getByRole('button', { name: 'Clear logs' }).click();
  const clear = page.getByRole('dialog', { name: 'Clear Telegram message logs?' });
  await clear.getByRole('button', { name: 'Cancel' }).click();
  await expect(monitor.getByText('2 entries · 1.2 KiB in DB')).toBeVisible();
  await monitor.getByRole('button', { name: 'Clear logs' }).click();
  await clear.getByRole('button', { name: 'Clear logs' }).click();
  await expect(monitor.getByText('0 entries · 0 B in DB')).toBeVisible();
  await expect(monitor.getByRole('button', { name: 'Clear logs' })).toBeDisabled();
  await expect(monitor.getByLabel('Telegram counts')).toContainText('13');
});
