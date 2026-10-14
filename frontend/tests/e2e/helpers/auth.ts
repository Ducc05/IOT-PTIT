import type { Page } from '@playwright/test'

export async function useApiSession(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('iot-auth-http://127.0.0.1:5174/api/v1', JSON.stringify({
      username: 'tester', email: '', access: 'test-access', refresh: 'test-refresh',
    }))
  })
  await page.route('http://127.0.0.1:5174/api/auth/me/', route => route.fulfill({
    json: { id: 1, username: 'tester', email: '' },
  }))
}
