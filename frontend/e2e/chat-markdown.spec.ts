import { expect, test, type Locator } from '@playwright/test';
const answer =
  '## Forecast overview\n\nA **clear signal** with *uncertainty*.\n\n1. Read the model.\n2. Compare the benchmark.\n\n| Metric | Value |\n| --- | --- |\n| MAE | 2.4 |\n\n```python\nprint("forecast")\n```\n\n[Documentation](https://example.com/docs)\n\n[Unsafe](javascript:alert(1))\n\n![External image](https://markdown-image.invalid/tracker.png)\n\n<script>alert("unsafe")</script>';
const turn = {
  id: 'markdown-fixture',
  session_id: 'markdown-chat',
  module: 'chronos',
  question: 'Explain this forecast',
  answer,
  mode: 'llm',
  provider: 'mock',
  model: 'fixture',
  created_at: '2026-11-07T12:00:00Z',
  observations: [],
  delegations: [],
};
test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'wait' });
});
async function verify(prose: Locator) {
  await expect(
    prose.getByRole('heading', { name: 'Forecast overview', exact: true }),
  ).toBeVisible();
  await expect(prose.locator('strong')).toHaveText('clear signal');
  await expect(prose.locator('ol > li')).toHaveCount(2);
  await expect(prose.getByRole('cell', { name: '2.4', exact: true })).toBeVisible();
  await expect(prose.locator('pre code')).toHaveText('print("forecast")\n');
  await expect(prose.getByRole('link', { name: 'Documentation', exact: true })).toHaveAttribute(
    'rel',
    'noopener noreferrer',
  );
  await expect(prose.getByRole('link', { name: 'Unsafe', exact: true })).toHaveCount(0);
  await expect(prose.locator('script,img')).toHaveCount(0);
}
test('Chronos renders Markdown in its page dialog without executing HTML or loading remote images', async ({
  page,
}) => {
  let images = 0;
  page.on('request', (r) => {
    if (r.url().includes('markdown-image.invalid')) images++;
  });
  await page.route('**/api/v1/agents/ask/stream', (r) =>
    r.fulfill({
      contentType: 'application/x-ndjson',
      body: JSON.stringify({ type: 'reply', reply: turn }) + '\n',
    }),
  );
  await page.goto('/forecast');
  await page.getByRole('button', { name: 'Ask Chronos', exact: true }).click();
  const input = page.getByRole('textbox', { name: 'Message Chronos', exact: true });
  await input.fill('Explain this forecast');
  await input.press('Enter');
  await verify(page.locator('.agent-answer .chat-markdown'));
  expect(images).toBe(0);
  await page
    .locator('.agent-answer')
    .screenshot({ path: '/tmp/sibyl-chat-markdown/chronos.png', animations: 'disabled' });
});
test('saved Sibyl replies and specialist consultations share the Markdown renderer', async ({
  page,
}) => {
  await page.route('**/api/v1/sibyl/conversations/markdown-chat', (r) =>
    r.fulfill({
      json: {
        id: 'markdown-chat',
        title: 'Markdown test',
        turns: [
          {
            ...turn,
            delegations: [
              {
                agent_id: 'chronos',
                name: 'Chronos',
                status: 'completed',
                mode: 'inference',
                provider: 'mock',
                question: 'Explain this forecast',
                answer,
              },
            ],
          },
        ],
      },
    }),
  );
  await page.goto('/sibyl?chat=markdown-chat');
  await verify(page.locator('.sibyl-answer > .chat-markdown'));
  await page.locator('.sibyl-consultations > summary').click();
  await verify(page.locator('.sibyl-consultations .chat-markdown'));
});
