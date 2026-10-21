import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173';
const serverPort = new URL(baseURL).port || '5173';

export default defineConfig({
  testDir: '..',
  testMatch: ['e2e/**/*.spec.ts', 'frontend/e2e/**/*.spec.ts'],
  timeout: 30_000,
  preserveOutput: process.env.E2E_NO_ARTIFACTS === '1' ? 'never' : 'always',
  expect: {
    timeout: 5_000,
  },
  use: {
    baseURL,
    trace: 'on-first-retry',
  },
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${serverPort} --strictPort`,
    url: baseURL,
    // A shared port may belong to another checkout and serve different source.
    reuseExistingServer: false,
    timeout: 120_000,
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        ...(process.env.E2E_BROWSER_CHANNEL ? { channel: process.env.E2E_BROWSER_CHANNEL } : {}),
      },
    },
  ],
});
