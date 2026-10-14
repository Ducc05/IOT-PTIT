import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './tests/e2e', fullyParallel: true, workers: 2, timeout: 45000,
  use: { baseURL: 'http://127.0.0.1:5173', viewport: { width: 1366, height: 768 },
    screenshot: 'only-on-failure', trace: 'retain-on-failure',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {},
  },
  webServer: [
    { command: 'npm run dev -- --host 127.0.0.1', url: 'http://127.0.0.1:5173', env: { VITE_DATA_SOURCE: 'mock' }, reuseExistingServer: !process.env.CI },
    { command: 'npm run dev -- --host 127.0.0.1 --port 5174', url: 'http://127.0.0.1:5174',
      env: { VITE_DATA_SOURCE: 'api', VITE_API_BASE_URL: 'http://127.0.0.1:5174/api/v1', VITE_REFRESH_MS: '1000', VITE_TRENDS_REFRESH_MS: '30000' }, reuseExistingServer: !process.env.CI },
  ],
})
