import { expect, test } from '@playwright/test';

test('module chat reads NDJSON and opens safe run details without invoking a provider', async ({
  page,
}) => {
  await page.route('**/api/v1/agents/ask/stream', async (route) => {
    const body = route.request().postDataJSON();
    const activity = {
      type: 'activity',
      id: 'tool-fixture',
      run_id: 'fixture-run',
      task_id: 'task-fixture',
      agent: 'sibyl-reporter',
      kind: 'tool',
      label: 'news_briefing',
    };
    const reply = {
      id: 'fixture-reply',
      run_id: 'fixture-run',
      module: 'reporter',
      session_id: 'fixture-session',
      question: body.message,
      answer: 'A source-attributed fixture answer.',
      engine: 'ProtoLink',
      mode: 'llm',
      provider: 'mock',
      tool: 'news_briefing',
      evidence: { mode: 'demo' },
      observations: [],
      created_at: new Date().toISOString(),
    };
    await route.fulfill({
      contentType: 'application/x-ndjson',
      body:
        [
          { type: 'status', status: 'queued' },
          { ...activity, status: 'running' },
          { ...activity, status: 'completed' },
          { type: 'reply', reply },
        ]
          .map((frame) => JSON.stringify(frame))
          .join('\n') + '\n',
    });
  });
  await page.route('**/api/v1/agents/runs/fixture-run/summary', (route) =>
    route.fulfill({
      json: {
        tokens: { total: 123, estimated: true, known_calls: 1, calls: 1 },
        tools: [
          {
            id: 'tool-fixture',
            agent: 'sibyl-reporter',
            tool: 'news_briefing',
            outcome: 'completed',
            duration_seconds: 0.25,
          },
        ],
        calls: [
          {
            agent: 'sibyl-reporter',
            provider: 'mock',
            model: 'fixture-model',
            latency_ms: 250,
            input_tokens: 100,
            output_tokens: 23,
            total_tokens: 123,
            estimated: true,
            source: 'estimate',
            cost: null,
          },
        ],
      },
    }),
  );
  await page.goto('/news');
  await page.getByRole('button', { name: 'Ask Reporter', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Ask Reporter' });
  await dialog.getByRole('textbox', { name: 'Message Reporter' }).fill('Explain the news');
  await dialog.getByRole('button', { name: 'Send message' }).click();
  await expect(dialog.getByText('A source-attributed fixture answer.')).toBeVisible();
  await dialog.getByText('Run details', { exact: true }).click();
  await expect(dialog.getByText(/123 estimated tokens/)).toBeVisible();
  await expect(dialog.getByText('Cost unavailable')).toBeVisible();
  await expect(dialog.getByText(/completed · 0.25s/)).toBeVisible();
});

test('an interrupted stream does not invent an answer or automatically retry', async ({ page }) => {
  let attempts = 0;
  await page.route('**/api/v1/agents/ask/stream', (route) => {
    attempts++;
    return route.fulfill({
      contentType: 'application/x-ndjson',
      body: JSON.stringify({ type: 'status', status: 'queued' }) + '\n',
    });
  });
  await page.goto('/news');
  await page.getByRole('button', { name: 'Ask Reporter', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Ask Reporter' });
  await dialog.getByRole('textbox', { name: 'Message Reporter' }).fill('Explain this');
  await dialog.getByRole('button', { name: 'Send message' }).click();
  await expect(dialog.getByRole('alert')).toContainText('Connection ended before a final reply');
  expect(attempts).toBe(1);
  await expect(dialog.getByRole('textbox', { name: 'Message Reporter' })).toHaveValue(
    'Explain this',
  );
});
