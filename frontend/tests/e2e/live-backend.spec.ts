import { execFileSync } from 'node:child_process'
import { expect, test } from '@playwright/test'

const liveUrl = process.env.IOT_LIVE_E2E_URL
const username = process.env.IOT_LIVE_E2E_USER
const password = process.env.IOT_LIVE_E2E_PASSWORD

test('real API, Celery MQTT ingest, JWT control and History work together', async ({ page }) => {
  test.skip(!liveUrl || !username || !password, 'Requires isolated backend, Celery, MQTT and a test user.')
  test.setTimeout(75000)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const readingsUrl = 'http://127.0.0.1:18003/api/v1/sensor-data/?type=TEMPERATURE&limit=1'
  const tokenResponse = await page.request.post('http://127.0.0.1:18003/api/auth/token/', {
    data: { username, password },
  })
  const access = (await tokenResponse.json()).access as string
  const headers = { Authorization: `Bearer ${access}` }
  const before = (await (await page.request.get(readingsUrl, { headers })).json()).count as number
  const sample = JSON.stringify({ success: true, temperature: 23.4, humidity: 54.0, light: 322 })
  const publish = () => execFileSync('mosquitto_pub', ['-h', '127.0.0.1', '-p', '28884', '-t', 'esp32/sensor/data', '-m', sample], { stdio: 'ignore' })
  const publisher = setInterval(publish, 1000)
  try {
    await page.goto(`${liveUrl}/dashboard`)
    await expect(page).toHaveURL(/\/login\?redirect=/)
    await expect(page.locator('.sidebar')).toHaveCount(0)
    await page.getByLabel('Username').fill(username!)
    await page.getByLabel('Password').fill(password!)
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await expect(page).toHaveURL(/\/dashboard$/)
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
    await expect.poll(async () => (await (await page.request.get(readingsUrl, { headers })).json()).count as number, { timeout: 20000 }).toBeGreaterThan(before)
    await expect(page.locator('.sensor-card.temperature .sensor-value')).toContainText('23.4', { timeout: 20000 })
    await expect(page.locator('.sensor-card.light .sensor-value')).toContainText('ADC')
    await expect(page.getByRole('img', { name: /light in ADC/ })).toBeVisible()
    await expect(page.locator('.sidebar-bottom')).toHaveCount(0)

    const readyLed = page.locator('.device-card').filter({ hasText: 'LED1' })
    await expect(readyLed.getByRole('switch')).toBeVisible()
    await readyLed.getByRole('switch').click()
    await expect(readyLed.locator('.device-state strong')).toHaveText('ON', { timeout: 20000 })
    await page.getByRole('link', { name: 'History', exact: true }).click()
    const row = page.locator('tbody tr').filter({ hasText: 'LED1' }).first()
    await expect(row).toContainText(username!)
    await expect(row).toContainText('Success')
    await page.getByRole('link', { name: 'Data', exact: true }).click()
    await page.getByLabel('Sensor type', { exact: true }).selectOption('LIGHT')
    await page.getByRole('textbox', { name: 'Sensor value' }).fill('322')
    await page.getByRole('button', { name: 'Filter', exact: true }).click()
    await expect(page.locator('tbody tr').first()).toContainText('ADC')
    await page.getByRole('link', { name: 'Dashboard', exact: true }).click()
    await expect(page.locator('.sensor-card.light .sensor-value')).toContainText('322')
    await expect(page.locator('.device-card').filter({ hasText: 'LED1' }).locator('.device-state strong')).toHaveText('ON')
    await page.screenshot({ path: '/tmp/iot-connected-dashboard-desktop.png' })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.waitForTimeout(300)
    await page.screenshot({ path: '/tmp/iot-connected-dashboard-mobile.png' })
    expect(errors).toEqual([])
  } finally { clearInterval(publisher) }
})
