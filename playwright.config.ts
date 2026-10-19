import { defineConfig, devices } from '@playwright/test';

/** Uses an operator-started demo workspace; never launches an exchange-enabled server. */
export default defineConfig({
  testDir: './frontend/e2e',
  fullyParallel: false,
  use: { baseURL: 'http://127.0.0.1:5173', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
