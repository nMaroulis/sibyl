import { expect, test, type Page } from '@playwright/test';

const answer =
  '## Live forecast\n\nA **clear signal** 🌍 with uncertainty.\n\n| Metric | Value |\n| --- | --- |\n| MAE | 2.4 |\n\n```python\nprint("forecast")\n```\n\n[Documentation](https://example.com/docs)\n\n![External image](https://stream-image.invalid/tracker.png)';
async function start(page: Page, sibyl = false) {
  await page.addInitScript(
    ({ answer, sibyl }) => {
      const original = window.fetch.bind(window);
      window.fetch = (input, init) => {
        const url = new URL(input instanceof Request ? input.url : String(input), location.origin);
        if (url.pathname !== `/api/v1/${sibyl ? 'sibyl' : 'agents'}/ask/stream`)
          return original(input, init);
        const encoder = new TextEncoder();
        let closed = false;
        const body = new ReadableStream({
          start(controller) {
            const send = (value: unknown) => {
              const bytes = encoder.encode(JSON.stringify(value) + '\n');
              // Deliberately split NDJSON and UTF-8, independently of Markdown tokens.
              for (let i = 0; i < bytes.length; i += 3) controller.enqueue(bytes.slice(i, i + 3));
            };
            send({ type: 'status', status: 'queued' });
            send({ type: 'answer', operation: 'append', text: '## Live forecast\n\nA **clear' });
            window.addEventListener(
              'stream-more',
              () => {
                if (!closed)
                  send({
                    type: 'answer',
                    operation: 'append',
                    text: answer.slice('## Live forecast\n\nA **clear'.length),
                  });
              },
              { once: true },
            );
            window.addEventListener(
              'stream-reset',
              () => {
                if (!closed)
                  send({
                    type: 'answer',
                    operation: 'replace',
                    text: '## Corrected draft\n\n**Still working**',
                  });
              },
              { once: true },
            );
            window.addEventListener(
              'stream-finish',
              () => {
                if (closed) return;
                closed = true;
                send({
                  type: 'reply',
                  reply: {
                    id: 'stream-reply',
                    module: 'chronos',
                    session_id: 'stream-chat',
                    question: 'Explain',
                    answer,
                    mode: 'llm',
                    provider: 'mock',
                    model: 'fixture',
                    observations: [],
                    delegations: [],
                    context: {},
                    created_at: '2026-11-07T12:00:00Z',
                  },
                });
                controller.close();
              },
              { once: true },
            );
            init?.signal?.addEventListener(
              'abort',
              () => {
                if (closed) return;
                closed = true;
                controller.error(new DOMException('Aborted', 'AbortError'));
              },
              { once: true },
            );
          },
        });
        return Promise.resolve(
          new Response(body, { headers: { 'content-type': 'application/x-ndjson' } }),
        );
      };
    },
    { answer, sibyl },
  );
  if (sibyl) {
    await page.route('**/api/v1/sibyl', (route) =>
      route.fulfill({
        json: {
          ready: true,
          network_ready: true,
          provider: 'mock',
          model: 'fixture',
          specialists: 10,
        },
      }),
    );
    await page.route('**/api/v1/sibyl/conversations/stream-chat', (route) =>
      route.fulfill({ json: { id: 'stream-chat', title: 'Streaming test', turns: [] } }),
    );
    await page.route('**/api/v1/sibyl/conversations/stream-chat/activity', (route) =>
      route.fulfill({ json: null }),
    );
    await page.goto('/sibyl?chat=stream-chat');
    await page.locator('.sibyl-composer textarea').fill('Explain');
    await page.locator('.sibyl-composer textarea').press('Enter');
  } else {
    await page.goto('/forecast');
    await page.getByRole('button', { name: 'Ask Chronos', exact: true }).click();
    const input = page.getByRole('textbox', { name: 'Message Chronos', exact: true });
    await input.fill('Explain');
    await input.press('Enter');
  }
}

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'wait' });
});
for (const sibyl of [false, true])
  test(`${sibyl ? 'Sibyl' : 'Chronos'} streams Markdown before the final reply and replaces provisional text`, async ({
    page,
  }) => {
    let images = 0;
    page.on('request', (request) => {
      if (request.url().includes('stream-image.invalid')) images++;
    });
    await start(page, sibyl);
    const preview = page.getByLabel('Reply in progress', { exact: true });
    await expect(
      preview.getByRole('heading', { name: 'Live forecast', exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText(`${sibyl ? 'Sibyl' : 'Chronos'} is replying`, { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'Stop', exact: true })).toBeEnabled();
    await page.evaluate(() => window.dispatchEvent(new Event('stream-more')));
    await expect(preview.locator('strong')).toHaveText('clear signal');
    await expect(preview.getByRole('cell', { name: '2.4', exact: true })).toBeVisible();
    await expect(preview.locator('pre code')).toHaveText('print("forecast")\n');
    await expect(preview).toContainText('🌍');
    expect(images).toBe(0);
    await page.evaluate(() => window.dispatchEvent(new Event('stream-reset')));
    await expect(
      preview.getByRole('heading', { name: 'Corrected draft', exact: true }),
    ).toBeVisible();
    await expect(preview.getByRole('heading', { name: 'Live forecast', exact: true })).toHaveCount(
      0,
    );
    await page.evaluate(() => window.dispatchEvent(new Event('stream-finish')));
    await expect(preview).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Live forecast', exact: true })).toHaveCount(1);
    await expect(page.getByRole('button', { name: 'Stop', exact: true })).toHaveCount(0);
    await expect(
      page
        .locator(sibyl ? '.sibyl-answer > .chat-markdown' : '.agent-answer .chat-markdown')
        .locator('pre code'),
    ).toHaveText('print("forecast")\n');
    expect(images).toBe(0);
  });

test('Stop discards provisional Markdown and ignores late answer frames', async ({ page }) => {
  await start(page);
  await expect(page.getByLabel('Reply in progress', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Stopped waiting');
  await page.evaluate(() => {
    window.dispatchEvent(new Event('stream-more'));
    window.dispatchEvent(new Event('stream-finish'));
  });
  await expect(page.getByLabel('Reply in progress', { exact: true })).toHaveCount(0);
  await expect(page.locator('.agent-answer')).toHaveCount(0);
});
