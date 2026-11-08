import { expect, test } from '@playwright/test';

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'wait' });
});
async function startWaiting(page: import('@playwright/test').Page) {
  await page.addInitScript(() => {
    const original = window.fetch.bind(window);
    window.fetch = (input, init) => {
      const url = new URL(input instanceof Request ? input.url : String(input), location.origin);
      if (url.pathname !== '/api/v1/agents/ask/stream') return original(input, init);
      const encoder = new TextEncoder();
      let closed = false;
      const body = new ReadableStream({
        start(controller) {
          const send = (value: unknown) =>
            controller.enqueue(encoder.encode(JSON.stringify(value) + '\n'));
          const activity = (status: 'started' | 'completed') =>
            send({
              type: 'activity',
              update: {
                type: 'tool',
                status,
                activity_id: 'forecast-step',
                event_id: status,
                run_id: 'fixture',
                task_id: 'fixture-task',
                agent_name: 'sibyl-chronos',
                name: 'price_forecast',
                sequence: status === 'started' ? 1 : 2,
                summary: `Tool ${status}`,
                timestamp: new Date().toISOString(),
              },
            });
          activity('started');
          activity('completed');
          window.addEventListener(
            'release-agent-reply',
            () => {
              if (closed) return;
              closed = true;
              send({
                type: 'reply',
                reply: {
                  id: 'progress-fixture',
                  module: 'chronos',
                  session_id: 'fixture',
                  question: 'Explain the forecast',
                  answer: '## Forecast ready\n\nA completed answer.',
                  provider: 'mock',
                  mode: 'llm',
                  observations: [],
                  context: {},
                  created_at: new Date().toISOString(),
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
  });
  await page.goto('/forecast');
  await page.getByRole('button', { name: 'Ask Chronos', exact: true }).click();
  const input = page.getByRole('textbox', { name: 'Message Chronos', exact: true });
  await input.fill('Explain the forecast');
  await input.press('Enter');
}

test('a completed tool keeps a visible working phase and clock until the final reply', async ({
  page,
}) => {
  await startWaiting(page);
  await expect(page.getByText('Chronos is preparing your answer', { exact: true })).toBeVisible();
  await expect(page.locator('.agent-run-activity [data-status="completed"]')).toContainText(
    'price forecast',
  );
  await expect(page.locator('.agent-working time')).not.toHaveText('0s');
  await expect(page.getByRole('button', { name: 'Stop', exact: true })).toBeEnabled();
  await page
    .locator('.agent-thinking')
    .screenshot({ path: '/tmp/sibyl-chat-progress/waiting.png', animations: 'disabled' });
  await page.evaluate(() => window.dispatchEvent(new Event('release-agent-reply')));
  await expect(page.getByRole('heading', { name: 'Forecast ready', exact: true })).toBeVisible();
  await expect(page.locator('.agent-working')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Stop', exact: true })).toHaveCount(0);
});
test('stopping after a tool completes clears the working indicator and ignores late replies', async ({
  page,
}) => {
  await startWaiting(page);
  await expect(page.getByText('Chronos is preparing your answer', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Stopped waiting');
  await expect(page.locator('.agent-working')).toHaveCount(0);
  await page.evaluate(() => window.dispatchEvent(new Event('release-agent-reply')));
  await expect(page.getByRole('heading', { name: 'Forecast ready', exact: true })).toHaveCount(0);
});
