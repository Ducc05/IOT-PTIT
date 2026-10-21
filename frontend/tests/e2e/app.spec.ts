import { expect, test, type Locator } from '@playwright/test'
import { createMockApi } from '../../src/api/mock'
import type { Device, ListQuery } from '../../src/types/api'
import { useApiSession } from './helpers/auth'
import { fulfillDashboardLists } from './helpers/dashboardLists'

test('API switch stays inside its track while turning an unconfirmed LED on and off', async ({ page }) => {
  await useApiSession(page)
  const backend = createMockApi({ latency: 0, persist: false })
  const latest = await backend.sensorLatest()
  const trends = await backend.sensorTrends()
  const device: Device = { ...(await backend.devices())[0], name: 'LED1', current_state: 'OFF', state_confirmed_at: null }
  const actions: string[] = []
  let commandCanFinish = false
  let requestedState: 'ON' | 'OFF' = 'ON'
  async function expectThumbInside(control: Locator, frames: number) {
    const positions = await control.evaluate(async (button, count) => {
      const thumb = button.querySelector('.toggle-thumb')!
      const bounds = []
      for (let index = 0; index < count; index++) {
        const track = button.getBoundingClientRect()
        const knob = thumb.getBoundingClientRect()
        bounds.push({ left: knob.left - track.left, right: track.right - knob.right })
        await new Promise(resolve => setTimeout(resolve, 80))
      }
      return bounds
    }, frames)
    expect(positions.every(position => position.left >= 0 && position.right >= 0)).toBe(true)
  }
  await page.route('http://127.0.0.1:5174/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (await fulfillDashboardLists(route, latest, trends)) return
    if (path.endsWith('/devices/')) return route.fulfill({ json: { count: 1, next: null, previous: null, results: [device] } })
    if (path.endsWith('/devices/1/control/')) {
      const action = route.request().postDataJSON().action as 'TURN_ON' | 'TURN_OFF'
      actions.push(action)
      requestedState = action === 'TURN_ON' ? 'ON' : 'OFF'
      commandCanFinish = false
      return route.fulfill({ status: 202, json: { command_id: '1', status: 'PENDING' } })
    }
    if (path.endsWith('/device-history/1/')) {
      if (!commandCanFinish) return route.fulfill({ json: { command_id: '1', status: 'PENDING' } })
      device.current_state = requestedState
      device.state_confirmed_at = new Date().toISOString()
      return route.fulfill({ json: { command_id: '1', status: 'SUCCESS' } })
    }
    return route.fulfill({ status: 404, json: {} })
  })
  await page.goto('http://127.0.0.1:5174/dashboard')
  const switchControl = page.getByRole('switch', { name: 'Turn on LED1; state unconfirmed' })
  await expect(switchControl).toHaveAttribute('aria-checked', 'mixed')
  await expect(page.getByText('Unconfirmed', { exact: true })).toBeVisible()
  await expectThumbInside(switchControl, 1)
  expect(await switchControl.evaluate(button => button.querySelector('.toggle-thumb')!.getBoundingClientRect().left - button.getBoundingClientRect().left)).toBeLessThanOrEqual(4)
  await switchControl.click()
  await expect.poll(() => actions).toEqual(['TURN_ON'])
  await expect(switchControl.locator('.toggle-spinner')).toBeVisible()
  await expectThumbInside(switchControl, 10)
  commandCanFinish = true
  const knownSwitch = page.getByRole('switch', { name: 'Toggle LED1' })
  await expect(knownSwitch).toHaveAttribute('aria-checked', 'true')
  await expectThumbInside(knownSwitch, 1)
  await knownSwitch.click()
  await expect.poll(() => actions).toEqual(['TURN_ON', 'TURN_OFF'])
  await expect(knownSwitch.locator('.toggle-spinner')).toBeVisible()
  await expectThumbInside(knownSwitch, 10)
  commandCanFinish = true
  await expect(knownSwitch).toHaveAttribute('aria-checked', 'false')
  await expectThumbInside(knownSwitch, 1)
})

for (const availability of ['OFFLINE', 'UNKNOWN', 'STALE'] as const) {
  test(`API device shows Unconnect and blocks control while ${availability}, then recovers`, async ({ page }) => {
    await useApiSession(page)
    const backend = createMockApi({ latency: 0, persist: false })
    const latest = await backend.sensorLatest()
    const trends = await backend.sensorTrends()
    const device: Device = {
      ...(await backend.devices())[0], name: 'LED1', current_state: 'ON',
      state_confirmed_at: new Date().toISOString(), availability,
    }
    let controlRequests = 0
    await page.route('http://127.0.0.1:5174/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname
      if (await fulfillDashboardLists(route, latest, trends)) return
      if (path.endsWith('/devices/')) return route.fulfill({ json: { count: 1, next: null, previous: null, results: [device] } })
      if (path.endsWith('/control/')) controlRequests++
      return route.fulfill({ status: 404, json: {} })
    })
    await page.goto('http://127.0.0.1:5174/dashboard')
    const card = page.locator('.device-card')
    const toggle = card.getByRole('switch')
    await expect(card.getByText('Unconnect', { exact: true })).toBeVisible()
    await expect(toggle).toBeDisabled()
    await expect(toggle).toHaveAttribute('aria-checked', 'mixed')
    await expect(card).not.toHaveClass(/device-on/)
    await toggle.evaluate(button => (button as HTMLButtonElement).click())
    expect(controlRequests).toBe(0)

    device.availability = 'ONLINE'
    await expect(toggle).toBeEnabled()
    await expect(toggle).toHaveAttribute('aria-checked', 'true')
    await expect(card.getByText('ON', { exact: true })).toBeVisible()

    device.availability = availability
    await expect(card.getByText('Unconnect', { exact: true })).toBeVisible()
    await expect(toggle).toBeDisabled()
    await expect(toggle).toHaveAttribute('aria-checked', 'mixed')
    expect(controlRequests).toBe(0)
  })
}

test('API rejects control after connection loss and refreshes the device to Unconnect', async ({ page }) => {
  await useApiSession(page)
  const backend = createMockApi({ latency: 0, persist: false })
  const latest = await backend.sensorLatest()
  const trends = await backend.sensorTrends()
  const device: Device = { ...(await backend.devices())[0], name: 'LED1', current_state: 'ON', state_confirmed_at: new Date().toISOString() }
  let controlRequests = 0
  await page.route('http://127.0.0.1:5174/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (await fulfillDashboardLists(route, latest, trends)) return
    if (path.endsWith('/devices/')) return route.fulfill({ json: { count: 1, next: null, previous: null, results: [device] } })
    if (path.endsWith('/control/')) {
      controlRequests++
      device.availability = 'OFFLINE'
      return route.fulfill({ status: 409, json: { error: { code: 'DEVICE_NOT_CONNECTED', message: 'ESP32 is not connected; device control is disabled.', details: { availability: 'OFFLINE' } } } })
    }
    return route.fulfill({ status: 404, json: {} })
  })
  await page.goto('http://127.0.0.1:5174/dashboard')
  const toggle = page.getByRole('switch')
  await expect(toggle).toBeEnabled()
  await toggle.click()
  await expect(page.getByText('Unconnect', { exact: true })).toBeVisible()
  await expect(toggle).toBeDisabled()
  await expect(page.getByText('ESP32 is not connected; device control is disabled.', { exact: true })).toBeVisible()
  expect(controlRequests).toBe(1)
})

test('API chart requests and plots 20 recent readings with second labels', async ({ page }) => {
  await useApiSession(page)
  const backend = createMockApi({ latency: 0, persist: false })
  const latest = await backend.sensorLatest()
  const devices = await backend.devices()
  const end = Date.now()
  latest.latest_sensors[0].status = 'STALE'
  latest.latest_sensors[0].created_at = new Date(end - 120000).toISOString()
  devices[0].availability = 'OFFLINE'
  const trends = {
    generated_at: new Date(end).toISOString(), effective_interval: 'raw' as const,
    trends: Array.from({ length: 20 }, (_, index) => ({
      timestamp: new Date(end - (19 - index) * 2000).toISOString(),
      temperature: 20 + index / 10, humidity: 60 + index / 10, light: 100 + index,
    })),
  }
  let trendUrl = ''
  await page.route('http://127.0.0.1:5174/api/v1/**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/sensor-data/') && !url.searchParams.has('type')) trendUrl = url.toString()
    if (await fulfillDashboardLists(route, latest, trends)) return
    if (url.pathname.endsWith('/devices/')) return route.fulfill({ json: { count: devices.length, next: null, previous: null, results: devices } })
    return route.fulfill({ status: 404, json: {} })
  })
  await page.goto('http://127.0.0.1:5174/dashboard')
  for (const label of ['Latest 20 readings', 'Live updates', 'Stale', 'Offline', 'Last known reading · stale', 'Environmental readings over time']) {
    await expect(page.getByText(label, { exact: true })).toHaveCount(0)
  }
  await expect(page.getByRole('switch', { name: 'LED Light unconnect' })).toBeDisabled()
  await expect.poll(() => trendUrl).toContain('sensor_status=ACTIVE')
  const path = await page.locator('.chart-plot path').first().getAttribute('d')
  expect(path?.match(/[ML]/g)).toHaveLength(20)
  const labels = await page.locator('.chart-plot text[text-anchor="middle"]').allTextContents()
  expect(labels.length).toBeGreaterThan(1)
  expect(labels.every(label => /^\d{2}:\d{2}:\d{2}$/.test(label))).toBe(true)
})

test('chart time labels stay separated when readings cluster near the end', async ({ page }) => {
  await useApiSession(page)
  const backend = createMockApi({ latency: 0, persist: false })
  const latest = await backend.sensorLatest()
  const trends = await backend.sensorTrends()
  const devices = await backend.devices()
  trends.trends = [0, 32, 64, 96, 104, 105, 106, 107].map(minute => ({
    timestamp: new Date(Date.UTC(2026, 9, 6, 12, minute)).toISOString(), temperature: 25, humidity: 60, light: 700,
  }))
  await page.route('http://127.0.0.1:5174/api/v1/**', async route => {
    if (await fulfillDashboardLists(route, latest, trends)) return
    await route.fulfill({ status: 404, json: {} })
  })
  await page.route('http://127.0.0.1:5174/api/v1/devices/', route => route.fulfill({ json: { count: devices.length, next: null, previous: null, results: devices } }))
  await page.goto('http://127.0.0.1:5174/dashboard')
  await expect(page.locator('.chart-plot path')).toHaveCount(3)
  await page.evaluate(() => document.fonts.ready)
  const labels = page.locator('.chart-plot text[text-anchor="middle"]')
  for (const viewport of [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport)
    await expect.poll(() => labels.evaluateAll(elements => {
      const bounds = elements.map(element => element.getBoundingClientRect())
      return bounds.length > 1 && bounds.every((rect, index) => !index || rect.left >= bounds[index - 1].right + 8)
    })).toBe(true)
    const text = await labels.allTextContents()
    expect(new Set(text).size).toBe(text.length)
    await page.screenshot({ path: `test-results/previews/chart-time-labels-${viewport.width}x${viewport.height}.png` })
  }
  trends.trends = [trends.trends.at(-1)!]
  await page.reload()
  await expect(labels).toHaveCount(1)
})

for (const viewport of [{ width: 1280, height: 720 }, { width: 1366, height: 768 }, { width: 1920, height: 1080 }, { width: 390, height: 844 }]) {
  test(`all four pages fit the viewport ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    const errors: string[] = []; page.on('pageerror', error => errors.push(error.message))
    for (const route of ['dashboard', 'data', 'history', 'profile']) {
      await page.goto(`/${route}`)
      await expect(page.locator('h1')).toHaveText(route[0].toUpperCase() + route.slice(1))
      if (route === 'dashboard') await expect(page.getByRole('switch', { name: 'Toggle LED Light' })).toBeAttached()
      if (['data', 'history'].includes(route)) await expect(page.locator('tbody tr')).toHaveCount(10)
      const geometry = await page.evaluate(() => {
        const page = document.querySelector('.page')!.getBoundingClientRect()
        const key = document.querySelector('.pagination, .profile-resources, .devices-section')!.getBoundingClientRect()
        return { scroll: document.documentElement.scrollHeight, height: innerHeight, width: document.documentElement.scrollWidth, viewport: innerWidth, bottom: key.bottom, pageBottom: page.bottom }
      })
      expect(geometry.scroll).toBeLessThanOrEqual(geometry.height)
      expect(geometry.width).toBeLessThanOrEqual(geometry.viewport)
      expect(geometry.bottom).toBeLessThanOrEqual(geometry.height)
      expect(geometry.pageBottom).toBeLessThanOrEqual(geometry.height)
      if (['data', 'history'].includes(route)) await expect.poll(() => page.locator('.table-viewport').evaluate(el => el.scrollHeight <= el.clientHeight + 1)).toBe(true)
      await page.screenshot({ path: `test-results/previews/${route}-${viewport.width}x${viewport.height}.png` })
      await page.mouse.wheel(0, 700)
      expect(await page.evaluate(() => window.scrollY)).toBe(0)
    }
    expect(errors).toEqual([])
  })
}

test('sensor filters, sorting, pagination and reset work with mock data', async ({ page }) => {
  await page.goto('/data')
  await expect(page.locator('tbody .row-id').first()).toBeVisible()
  await page.getByLabel('Sensor type', { exact: true }).selectOption('TEMPERATURE')
  await page.getByRole('button', { name: 'Filter', exact: true }).click()
  await expect(page).toHaveURL(/type=TEMPERATURE/)
  await expect(page.locator('tbody .sensor-type').first()).toHaveText('Temp')
  await expect.poll(async () => {
    const values = await page.locator('tbody .sensor-type').allTextContents()
    return values.length > 0 && values.every(value => value === 'Temp')
  }).toBe(true)
  await page.getByRole('button', { name: 'Next page', exact: true }).click()
  await expect(page).toHaveURL(/page=2/)
  await expect(page.getByRole('button', { name: 'Page 2', exact: true })).toHaveAttribute('aria-current', 'page')
  await page.getByRole('combobox', { name: 'Sort by', exact: true }).selectOption('value')
  await expect(page).toHaveURL(/ordering=value/)
  await expect.poll(async () => {
    const values = (await page.locator('.reading-value').allTextContents()).map(parseFloat)
    return JSON.stringify(values) === JSON.stringify([...values].sort((a, b) => a - b))
  }).toBe(true)
  const value = parseFloat(await page.locator('.reading-value').first().innerText())
  await page.getByLabel('Sensor value', { exact: true }).fill(String(value))
  await page.getByRole('button', { name: 'Filter', exact: true }).click()
  await expect.poll(async () => (await page.locator('.reading-value').allTextContents()).every(text => parseFloat(text) === value)).toBe(true)
  await page.getByRole('button', { name: 'Reset filters' }).click()
  await expect(page.getByLabel('Sensor value', { exact: true })).toHaveValue('')
  await expect(page.getByLabel('Sensor type', { exact: true })).toHaveValue('')
})

test('Data ignores old range URLs and searches exact values', async ({ page }) => {
  await page.goto('/data?from=2099-01-01T00:00:00Z&to=2099-01-02T00:00:00Z')
  await expect(page.locator('tbody tr')).toHaveCount(10)
  await expect(page.getByRole('button', { name: 'Date & time range', exact: true })).toHaveCount(0)
  await page.getByLabel('Sensor value', { exact: true }).fill('0')
  await page.getByRole('button', { name: 'Filter', exact: true }).click()
  await expect(page.getByText('No records match your filters.')).toBeVisible()
  await expect(page).not.toHaveURL(/[?&](from|to)=/)
  await expect(page.getByRole('button', { name: 'Next page', exact: true })).toBeDisabled()
})

for (const kind of ['data', 'history'] as const) {
  test(`${kind} Rows per page updates records and preserves range, filters and ordering`, async ({ page }) => {
    const backend = createMockApi({ latency: 0, persist: false })
    const timeField = 'created_at'
    const filter = kind === 'data' ? { type: 'HUMIDITY' } : { action: 'TURN_OFF' }
    const range = kind === 'history' ? { from: '2000-01-01T00:00:00.000Z', to: '2100-01-01T00:00:00.000Z' } : {}
    const query = { ...filter, ...range, ordering: timeField, page: 2, page_size: 10 }
    const params = new URLSearchParams(Object.entries(query).map(([key, value]) => [key, String(value)]))
    await page.goto(`/${kind}?${params}`)
    await expect(page.locator('tbody .row-id')).toHaveCount(10)
    await page.evaluate(() => document.fonts.ready)
    const initialRowHeight = await page.locator('tbody tr').first().evaluate(row => row.getBoundingClientRect().height)
    const selector = page.getByRole('combobox', { name: 'Rows per page', exact: true })
    await selector.selectOption('25')
    await expect(page).toHaveURL(/page_size=25/)
    expect(new URL(page.url()).searchParams.get('page')).toBe('1')
    const expected = await (kind === 'data' ? backend.sensorData({ ...query, page: 1, page_size: 25 }) : backend.history({ ...query, page: 1, page_size: 25 }))
    await expect.poll(() => page.locator('tbody .row-id').allTextContents()).toEqual(expected.results.map(row => `#${row.id}`))
    await expect.poll(async () => Math.abs((await page.locator('tbody tr').first().evaluate(row => row.getBoundingClientRect().height)) - initialRowHeight)).toBeLessThan(0.1)
    await expect(page.locator('.pagination-total')).toHaveText(`of ${expected.count.toLocaleString('en-US')} items`)
    for (const [key, value] of Object.entries({ ...filter, ...range, ordering: timeField })) {
      expect(new URL(page.url()).searchParams.get(key)).toBe(value)
    }
    await page.getByRole('button', { name: 'Next page', exact: true }).click()
    await expect(page).toHaveURL(/page=2(?:&|$)/)
    await expect(page.locator('tbody .row-id')).toHaveCount(25)
    await page.reload()
    await expect(selector).toHaveValue('25')
    await expect(page.locator('tbody .row-id')).toHaveCount(25)
    await page.getByRole('combobox', { name: 'Sort by', exact: true }).selectOption(`-${timeField}`)
    await expect(selector).toHaveValue('25')
    await page.getByRole('button', { name: 'Filter', exact: true }).click()
    await expect(selector).toHaveValue('25')
    await expect(page.locator('tbody .row-id')).toHaveCount(25)
    await page.getByRole('button', { name: 'Reset filters', exact: true }).click()
    await expect(selector).toHaveValue('25')
    await selector.selectOption('100')
    await expect(page.locator('tbody .row-id')).toHaveCount(100)
    await expect.poll(async () => Math.abs((await page.locator('tbody tr').first().evaluate(row => row.getBoundingClientRect().height)) - initialRowHeight)).toBeLessThan(0.1)
    expect(new URL(page.url()).searchParams.get('page')).toBe('1')
    await expect(page.locator('.table-viewport')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight)).toBe(true)
    await page.getByRole('button', { name: 'Filter', exact: true }).click()
    await expect(selector).toHaveValue('100')
  })

  test(`${kind} pagination shows ellipses and navigates to the last page`, async ({ page }) => {
    const backend = createMockApi({ latency: 0, persist: false })
    const firstQuery = { page: 1, page_size: 10 }
    const first = await (kind === 'data' ? backend.sensorData(firstQuery) : backend.history(firstQuery))
    const lastPage = Math.ceil(first.count / 10)
    await page.goto(`/${kind}`)
    await expect(page.locator('tbody tr')).toHaveCount(10)
    const pagination = page.getByRole('navigation', { name: 'Pagination', exact: true })
    await expect(pagination.locator('button[aria-label^="Page "]')).toHaveText(['1', '2', '3', String(lastPage)])
    await expect(pagination.locator('.pagination-ellipsis')).toHaveCount(1)
    await expect(pagination.getByRole('button', { name: 'Previous page', exact: true })).toBeDisabled()
    await pagination.getByRole('button', { name: `Page ${lastPage}`, exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`page=${lastPage}(?:&|$)`))
    await expect(pagination.getByRole('button', { name: `Page ${lastPage}`, exact: true })).toHaveAttribute('aria-current', 'page')
    await expect(pagination.getByRole('button', { name: 'Next page', exact: true })).toBeDisabled()
    const lastQuery = { page: lastPage, page_size: 10 }
    const last = await (kind === 'data' ? backend.sensorData(lastQuery) : backend.history(lastQuery))
    await expect.poll(() => page.locator('tbody .row-id').allTextContents()).toEqual(last.results.map(row => `#${row.id}`))
    await pagination.getByRole('button', { name: 'Previous page', exact: true }).click()
    await expect(pagination.getByRole('button', { name: `Page ${lastPage - 1}`, exact: true })).toHaveAttribute('aria-current', 'page')
    await pagination.getByRole('button', { name: 'Page 1', exact: true }).click()
    await expect(pagination.getByRole('button', { name: 'Page 1', exact: true })).toHaveAttribute('aria-current', 'page')
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto(`/${kind}?page=4`)
    await expect(pagination.getByRole('button', { name: 'Page 4', exact: true })).toHaveAttribute('aria-current', 'page')
    const bounds = await pagination.boundingBox()
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390)
  })

  test(`${kind} Sort By orders time and preserves filters when resetting pagination`, async ({ page }) => {
    const backend = createMockApi({ latency: 0, persist: false })
    const timeField = 'created_at'
    const filter = kind === 'data' ? 'type=HUMIDITY' : 'action=TURN_OFF'
    await page.goto(`/${kind}?${filter}&page=2`)
    await expect(page.locator('tbody tr')).toHaveCount(10)
    const selector = page.getByRole('combobox', { name: 'Sort by', exact: true })
    await expect(selector).toHaveValue(`-${timeField}`)
    await expect(page.locator('thead button')).toHaveCount(0)
    for (const ordering of [timeField, `-${timeField}`]) {
      await selector.selectOption(ordering)
      await expect(page).toHaveURL(new RegExp(`ordering=${ordering}`))
      await expect(page).toHaveURL(/page=1(?:&|$)/)
      await expect(page).toHaveURL(new RegExp(filter))
      const query = { page: 1, page_size: 10, ordering, ...(kind === 'data' ? { type: 'HUMIDITY' } : { action: 'TURN_OFF' }) }
      const expected = await (kind === 'data' ? backend.sensorData(query) : backend.history(query))
      await expect.poll(() => page.locator('tbody .row-id').allTextContents()).toEqual(expected.results.map(row => `#${row.id}`))
      await expect(page.getByRole('columnheader', { name: 'Date & Time', exact: true })).toHaveAttribute('aria-sort', ordering.startsWith('-') ? 'descending' : 'ascending')
    }
    await page.reload()
    await expect(selector).toHaveValue(`-${timeField}`)
  })
}

test('device control confirms asynchronously and appears in history filters', async ({ page }) => {
  await page.goto('/dashboard')
  const toggle = page.getByRole('switch', { name: 'Toggle LED Light' })
  await expect(toggle).toHaveAttribute('aria-checked', 'true')
  await toggle.click(); await expect(toggle).toBeDisabled()
  await expect(toggle).toHaveAttribute('aria-checked', 'false', { timeout: 10000 })
  await expect(toggle).toBeEnabled()
  await page.getByRole('link', { name: 'History', exact: true }).click()
  await expect(page.locator('tbody tr').first()).toContainText('LED Light')
  await expect(page.locator('tbody tr').first().locator('.device-cell img')).toBeVisible()
  await expect(page.locator('tbody tr').first().locator('.action-badge')).toHaveText('TURN_OFF')
  await page.getByLabel('Device', { exact: true }).selectOption('1')
  await page.getByLabel('Action', { exact: true }).selectOption('TURN_OFF')
  await page.getByLabel('Status', { exact: true }).selectOption('SUCCESS')
  await page.getByRole('button', { name: 'Filter', exact: true }).click()
  await expect(page.locator('tbody tr').first()).toContainText('Success')
  const id = (await page.locator('tbody .row-id').first().innerText()).replace('#', '')
  await page.getByLabel('History ID or command UUID').fill(id)
  await page.getByRole('button', { name: 'Filter', exact: true }).click()
  await expect(page.locator('tbody tr')).toHaveCount(1)
})

test('mock dashboard and lists stay stable with no background simulation', async ({ page }) => {
  await page.goto('/dashboard'); await expect(page.locator('.sensor-value')).toHaveCount(3)
  await expect(page.getByRole('switch', { name: 'Toggle LED Light' })).toBeAttached()
  await expect(page.getByText('Live updates', { exact: true })).toHaveCount(0)
  const values = await page.locator('.sensor-value').allTextContents()
  const timestamp = await page.locator('.sensor-caption').first().getAttribute('title')
  await page.clock.install()
  await page.clock.fastForward(25000)
  expect(await page.locator('.sensor-value').allTextContents()).toEqual(values)
  expect(await page.locator('.sensor-caption').first().getAttribute('title')).toBe(timestamp)
  await page.clock.resume()
  await page.getByRole('link', { name: 'Data', exact: true }).click()
  await expect(page.locator('tbody tr')).toHaveCount(10)
  const initialRows = await page.locator('tbody').innerText()
  await page.clock.fastForward(25000)
  expect(await page.locator('tbody').innerText()).toBe(initialRows)
  await page.clock.resume()
  await page.getByRole('link', { name: 'History', exact: true }).click()
  await expect(page.locator('tbody tr')).toHaveCount(10)
  const historyRows = await page.locator('tbody').innerText()
  await page.clock.fastForward(25000)
  expect(await page.locator('tbody').innerText()).toBe(historyRows)
})

test('list pages show ten records and History ignores old range URLs', async ({ page }) => {
  await page.goto('/data?type=HUMIDITY&page=2&page_size=5')
  await expect(page.locator('tbody tr')).toHaveCount(10)
  await expect(page.locator('tbody .sensor-type').first()).toHaveText('Humidity')
  await expect(page).toHaveURL(/type=HUMIDITY&page=2/)
  await expect(page.getByRole('button', { name: 'Page 2', exact: true })).toHaveAttribute('aria-current', 'page')
  expect((await page.locator('tbody .sensor-type').allTextContents()).every(value => value === 'Humidity')).toBe(true)
  await page.setViewportSize({ width: 1280, height: 720 })
  await expect(page.locator('tbody tr')).toHaveCount(10)
  await expect(page.getByRole('button', { name: 'Page 2', exact: true })).toHaveAttribute('aria-current', 'page')
  await page.goto('/history?from=2099-01-01T00:00:00Z&to=2099-01-02T00:00:00Z')
  await expect(page.locator('tbody tr')).toHaveCount(10)
  await expect(page.getByRole('button', { name: 'Date & time range', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Filter', exact: true })).toBeEnabled()
})

test('API mode refreshes Dashboard and lists without reload and keeps filters', async ({ page }) => {
  await useApiSession(page)
  const backend = createMockApi({ latency: 0, persist: false })
  const baseLatest = await backend.sensorLatest()
  const baseTrends = await backend.sensorTrends()
  const baseDevices = await backend.devices()
  const calls = { latest: 0, trends: 0, data: 0, history: 0 }
  const dataQueries: URLSearchParams[] = []
  await page.route('http://127.0.0.1:5174/api/v1/**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/sensors/')) return void await fulfillDashboardLists(route, baseLatest, baseTrends)
    if (url.pathname.endsWith('/devices/')) return route.fulfill({ json: { count: baseDevices.length, next: null, previous: null, results: baseDevices } })
    const pageSize = Number(url.searchParams.get('limit') || 10)
    const query: ListQuery = { ...Object.fromEntries(url.searchParams), page: Math.floor(Number(url.searchParams.get('offset') || 0) / pageSize) + 1, page_size: pageSize }
    if (url.pathname.endsWith('/sensor-data/')) {
      if (url.searchParams.get('sensor_status') === 'ACTIVE' && !url.searchParams.has('type')) calls.trends++
      else dataQueries.push(url.searchParams)
      const data = await backend.sensorData(query)
      if (url.searchParams.get('sensor_status') === 'ACTIVE' && url.searchParams.get('type') === 'TEMPERATURE') data.results[0].value = 20 + ++calls.latest
      else data.results[0].id += ++calls.data * 10000
      return route.fulfill({ json: data })
    }
    if (url.pathname.endsWith('/device-history/')) {
      const data = await backend.history(query)
      data.results[0].id += ++calls.history * 10000
      return route.fulfill({ json: data })
    }
    return route.fulfill({ status: 404, json: {} })
  })
  await page.goto('http://127.0.0.1:5174/dashboard')
  await expect(page.getByText('Live updates', { exact: true })).toHaveCount(0)
  let documentLoads = 0
  page.on('request', request => { if (request.isNavigationRequest() && request.frame() === page.mainFrame()) documentLoads++ })
  const before = await page.locator('.sensor-value').first().innerText()
  await expect.poll(() => page.locator('.sensor-value').first().innerText()).not.toBe(before)
  expect(calls.trends).toBeGreaterThan(0)
  await page.getByRole('link', { name: 'Data', exact: true }).click()
  await expect(page.locator('tbody tr')).toHaveCount(10)
  await page.getByLabel('Sensor type', { exact: true }).selectOption('HUMIDITY')
  await page.getByRole('button', { name: 'Filter', exact: true }).click()
  await expect(page).toHaveURL(/type=HUMIDITY/)
  await expect(page.getByRole('button', { name: 'Next page', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: 'Next page', exact: true }).click()
  await expect(page).toHaveURL(/page=2/)
  await expect(page.locator('tbody .sensor-type').first()).toHaveText('Humidity')
  const dataId = await page.locator('tbody .row-id').first().innerText()
  await expect.poll(() => page.locator('tbody .row-id').first().innerText()).not.toBe(dataId)
  await expect(page.getByRole('button', { name: 'Page 2', exact: true })).toHaveAttribute('aria-current', 'page')
  expect(dataQueries.at(-1)?.get('offset')).toBe('10')
  expect(dataQueries.at(-1)?.get('type')).toBe('HUMIDITY')
  expect(dataQueries.at(-1)?.get('limit')).toBe('10')
  await page.getByRole('link', { name: 'History', exact: true }).click()
  await expect(page.locator('tbody tr')).toHaveCount(10)
  const historyId = await page.locator('tbody .row-id').first().innerText()
  await expect.poll(() => page.locator('tbody .row-id').first().innerText()).not.toBe(historyId)
  expect(documentLoads).toBe(0)
})
