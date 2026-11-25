import { expect, test } from '@playwright/test';

test('a provider can have separate named deployments with independent routing', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 390, height: 900 });
  const ollama = await request.post('/api/v1/settings/llm', {
    data: { provider: 'ollama', model: 'local-alias' },
  });
  expect(ollama.ok()).toBeTruthy();
  let reachable = true;
  await page.route('**/api/v1/settings/llm/deployments/ollama/runtime', (route) =>
    route.fulfill({
      json: reachable
        ? {
            status: 'running',
            models: [{ name: 'local-alias:latest' }, { name: 'local-import:7b' }],
            loaded_models: ['local-alias:latest'],
            loaded_models_checked: true,
          }
        : { status: 'unreachable', models: [] },
    }),
  );
  await page.route('**/api/v1/settings/llm/deployments/*/check', (route) =>
    route.fulfill({ json: { status: 'ready', detail: 'The model answered a test request.' } }),
  );

  await page.goto('/settings?tab=models');
  await expect(page.getByRole('heading', { name: 'Added models' })).toBeVisible();
  const monitor = page.getByRole('region', { name: 'Ollama model server status' });
  await expect(monitor.getByText('Loaded · local-alias:latest')).toBeVisible();
  const localCard = page.getByRole('article', { name: 'Ollama model', exact: true });
  const changeModel = localCard.getByRole('button', { name: 'Change model', exact: true });
  await changeModel.click();
  const localModels = localCard.getByRole('combobox', { name: 'Model', exact: true });
  await expect(localModels.locator('option')).toHaveText([
    'Choose a model',
    'local-alias:latest',
    'local-import:7b',
    'Custom model…',
  ]);
  await expect(localModels).toHaveValue('local-alias:latest');
  await localModels.selectOption('local-import:7b');
  await localCard.getByRole('button', { name: 'Save model', exact: true }).click();
  await expect(localCard.getByText('local-import:7b', { exact: true }).first()).toBeVisible();

  reachable = false;
  await monitor.getByRole('button', { name: 'Check status', exact: true }).click();
  await expect(monitor.getByText('Unreachable', { exact: true })).toBeVisible();
  await changeModel.click();
  await expect(localModels.locator('option')).toHaveText(['Choose a model', 'Custom model…']);
  await expect(localCard.getByLabel('Custom model ID')).toHaveValue('local-import:7b');
  await changeModel.click();
  await page.getByRole('button', { name: 'API', exact: true }).click();

  const picker = page.getByRole('group', { name: 'API model providers' });
  await picker.getByRole('button', { name: 'OpenAI', exact: true }).click();
  await expect(page.getByLabel('Deployment name')).toHaveValue('OpenAI API model');
  await expect(page.getByRole('combobox', { name: 'Model · optional' })).toHaveValue('');
  await page.getByLabel('API key', { exact: true }).fill('sk-first-browser-key-1234');
  await page.getByRole('button', { name: 'Add deployment', exact: true }).click();

  const first = page.getByRole('article', { name: 'OpenAI API model', exact: true });
  const firstHeader = first.locator('header');
  await expect(firstHeader.getByText('Inactive', { exact: true })).toBeVisible();
  const activate = firstHeader.getByRole('button', { name: 'Activate model', exact: true });
  await expect(activate).toBeDisabled();
  await expect(first.getByText('No model selected', { exact: true })).toBeVisible();
  await expect(first.getByText('sk-••••••1234')).toBeVisible();
  await first.getByRole('button', { name: 'Choose model', exact: true }).click();
  await first.getByRole('combobox', { name: 'Model', exact: true }).selectOption('__custom__');
  await first.getByLabel('Custom model ID').fill('chosen-after-add');
  await first.getByRole('button', { name: 'Save model' }).click();
  await expect(first.getByText('chosen-after-add', { exact: true })).toBeVisible();
  await first.getByRole('button', { name: 'Check status' }).click();
  await expect(first.getByRole('status')).toHaveText('The model answered a test request.');
  await activate.click();
  await expect(firstHeader.getByText('Active in workspace', { exact: true })).toBeVisible();
  await first.getByText('Request activity', { exact: true }).click();
  await expect(
    first.getByText('No recent requests are attributed to this deployment yet.'),
  ).toBeVisible();
  await first.getByText('Request activity', { exact: true }).click();
  await expect(activate).toHaveCount(0);
  await expect(localCard.locator('header').getByText('Inactive', { exact: true })).toBeVisible();

  await picker.getByRole('button', { name: 'OpenAI 1 added' }).click();
  await expect(page.getByLabel('Deployment name')).toHaveValue('OpenAI API model (1)');
  const apiKey = page.getByLabel('API key', { exact: true });
  await expect(apiKey).toBeVisible();
  await expect(apiKey).toHaveValue('');
  await apiKey.fill('sk-second-browser-key-5678');
  await page.getByRole('combobox', { name: 'Model · optional' }).selectOption('gpt-4.1-mini');
  await page.getByRole('button', { name: 'Add deployment', exact: true }).click();

  const second = page.getByRole('article', { name: 'OpenAI API model (1)', exact: true });
  await expect(second.getByText('Inactive', { exact: true })).toBeVisible();
  await expect(second.getByText('sk-••••••5678')).toBeVisible();
  await expect(firstHeader.getByText('Active in workspace', { exact: true })).toBeVisible();

  await second.getByRole('button', { name: 'Edit OpenAI API model (1)' }).click();
  const edit = page.getByRole('dialog', { name: 'Edit OpenAI API model (1)', exact: true });
  await expect(edit.getByLabel('API key', { exact: true })).toHaveValue('');
  await edit.getByLabel('Deployment name').fill('Research key');
  await edit.getByText('Advanced', { exact: true }).click();
  await expect(edit.getByLabel('Context window · tokens')).toHaveValue('');
  await expect(edit.getByText('Auto · 1,047,576 tokens', { exact: true })).toBeVisible();
  await edit.getByLabel('Context window · tokens').fill('64000');
  await edit.getByLabel('Max output tokens').fill('2560');
  await edit.getByRole('button', { name: 'Save connection' }).click();

  await page.getByRole('button', { name: 'Customize agents' }).click();
  await page.getByRole('button', { name: 'Configure Reporter model' }).click();
  const assign = page.getByRole('dialog', { name: 'Reporter model' });
  await assign
    .getByRole('combobox', { name: 'Deployment' })
    .selectOption({ label: 'Research key · gpt-4.1-mini' });
  await assign.getByRole('button', { name: 'Save agent model' }).click();
  const research = page.getByRole('article', { name: 'Research key', exact: true });
  await research.getByText('Request activity', { exact: true }).click();
  await expect(research.getByText('Custom · 64,000 tokens')).toBeVisible();
  await expect(research.getByText('2,560 tokens', { exact: true })).toBeVisible();
  await expect(research.locator('header').getByText('Agent only', { exact: true })).toBeVisible();
  await expect(
    research.locator('header').getByRole('button', { name: 'Activate model' }),
  ).toBeEnabled();

  await first.getByRole('button', { name: 'Delete OpenAI API model' }).click();
  await page
    .getByRole('dialog', { name: 'Delete OpenAI API model?' })
    .getByRole('button', { name: 'Delete deployment' })
    .click();
  await expect(first).toHaveCount(0);
  await expect(research.getByText('1 agent assigned')).toBeVisible();
  await page.reload();
  await expect(research.getByText('sk-••••••5678')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});
