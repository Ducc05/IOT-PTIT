import { expect, test } from '@playwright/test'
import { createMockApi } from '../../src/api/mock'
import type { SensorDataRow, SensorType } from '../../src/types/api'
import { useApiSession } from './helpers/auth'

test.use({ timezoneId: 'Asia/Ho_Chi_Minh' })

async function fixtures() {
  const backend = createMockApi({ latency: 0, persist: false })
  const types: SensorType[] = ['TEMPERATURE', 'HUMIDITY', 'LIGHT']
  return Promise.all(types.map(async type => (await backend.sensorData({ page: 1, page_size: 1, type })).results[0]))
}

test('Data searches exact measured values by type, keeps filters and rejects names', async ({ page }) => {
  await useApiSession(page)
  const prototypes = await fixtures()
  const rows: SensorDataRow[] = []
  const add = (type: SensorType, value: number, count: number) => {
    const prototype = prototypes.find(row => row.type === type)!
    for (let i = 0; i < count; i++) rows.push({ ...prototype, id: rows.length + 1, value })
  }
  add('TEMPERATURE', 50, 12); add('TEMPERATURE', 50.1, 3); add('TEMPERATURE', 0, 3)
  add('TEMPERATURE', 28.5, 4); add('HUMIDITY', 50, 10); add('LIGHT', 50, 6)
  const queries: URLSearchParams[] = []
  await page.route('http://127.0.0.1:5174/api/v1/sensor-data/**', route => {
    const query = new URL(route.request().url()).searchParams
    queries.push(query)
    const filtered = rows.filter(row => (!query.get('type') || row.type === query.get('type')) && (!query.has('value') || row.value === Number(query.get('value'))))
      .sort((a, b) => (query.get('ordering')?.startsWith('-') ? -1 : 1) * (a.id - b.id))
    const size = Number(query.get('limit') || 10), offset = Number(query.get('offset') || 0)
    return route.fulfill({ json: { count: filtered.length, next: null, previous: null, results: filtered.slice(offset, offset + size) } })
  })
  await page.goto('http://127.0.0.1:5174/data?from=2099-01-01T00:00:00Z&to=2099-01-02T00:00:00Z')
  await expect(page.locator('tbody .row-id')).toHaveCount(10)
  await expect(page.getByRole('button', { name: 'Date & time range', exact: true })).toHaveCount(0)
  await expect(page.getByLabel('Sensor value', { exact: true })).toHaveAttribute('placeholder', 'Enter value to search (e.g. 28.5)')
  for (const [type, label, count] of [['TEMPERATURE', 'Temp', 12], ['HUMIDITY', 'Humidity', 10], ['LIGHT', 'Light', 6]] as const) {
    await page.getByLabel('Sensor type', { exact: true }).selectOption(type)
    await page.getByLabel('Sensor value', { exact: true }).fill('50')
    await page.getByRole('button', { name: 'Filter', exact: true }).click()
    await expect(page.locator('.pagination-total')).toHaveText(`of ${count} items`)
    await expect.poll(() => page.locator('tbody .sensor-type').allTextContents()).toEqual(Array(Math.min(10, count)).fill(label))
    expect((await page.locator('.reading-value').allTextContents()).every(value => parseFloat(value) === 50)).toBe(true)
    expect(queries.at(-1)?.get('value')).toBe('50')
    expect(queries.at(-1)?.has('search')).toBe(false)
    expect(queries.at(-1)?.has('from')).toBe(false)
    expect(queries.at(-1)?.has('to')).toBe(false)
    if (type === 'TEMPERATURE') {
      await page.getByRole('button', { name: 'Next page', exact: true }).click()
      await expect(page.locator('tbody .row-id')).toHaveCount(2)
      await expect(page).toHaveURL(/page=2/)
      expect(queries.at(-1)?.get('value')).toBe('50')
      await page.reload()
      await expect(page.getByLabel('Sensor value', { exact: true })).toHaveValue('50')
      await expect(page.getByLabel('Sensor type', { exact: true })).toHaveValue('TEMPERATURE')
      await expect(page.locator('tbody .row-id')).toHaveCount(2)
    }
  }
  await page.getByLabel('Sensor type', { exact: true }).selectOption('TEMPERATURE')
  await page.getByLabel('Sensor value', { exact: true }).fill('0')
  await page.getByRole('button', { name: 'Filter', exact: true }).click()
  await expect(page.locator('.pagination-total')).toHaveText('of 3 items')
  await expect(page.locator('tbody .row-id')).toHaveCount(3)
  await page.getByLabel('Sensor value', { exact: true }).fill('28,5')
  await page.getByRole('button', { name: 'Filter', exact: true }).click()
  await expect(page.locator('.pagination-total')).toHaveText('of 4 items')
  expect(queries.at(-1)?.get('value')).toBe('28.5')
  await page.getByLabel('Sensor value', { exact: true }).fill('TEMP_01')
  await page.getByRole('button', { name: 'Filter', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('Vui lòng nhập một giá trị số, ví dụ 28.5.')
  await page.getByRole('button', { name: 'Reset filters', exact: true }).click()
  await expect(page.getByLabel('Sensor value', { exact: true })).toHaveValue('')
  await expect(page.getByLabel('Sensor type', { exact: true })).toHaveValue('')
  await expect(page.locator('.pagination-total')).toHaveText(`of ${rows.length} items`)
})

test('Time search accepts text copied from Date & Time, converts local time to UTC and restores on reload', async ({ page }) => {
  await useApiSession(page)
  const prototypes = await fixtures()
  const times = ['2026-10-07T05:34:55.999Z', '2026-10-07T05:34:56.000Z', '2026-10-07T05:34:56.500Z', '2026-10-07T05:34:57.000Z', '2026-10-07T05:35:00.000Z']
  const rows = times.map((created_at, i) => ({ ...prototypes[i % 3], id: i + 1, created_at }))
  const queries: URLSearchParams[] = []
  await page.route('http://127.0.0.1:5174/api/v1/sensor-data/**', route => {
    const query = new URL(route.request().url()).searchParams
    queries.push(query)
    const filtered = rows.filter(row => (!query.get('type') || row.type === query.get('type')) && (!query.get('from') || Date.parse(row.created_at) >= Date.parse(query.get('from')!)) && (!query.get('to') || Date.parse(row.created_at) < Date.parse(query.get('to')!)))
    return route.fulfill({ json: { count: filtered.length, next: null, previous: null, results: filtered } })
  })
  await page.goto('http://127.0.0.1:5174/data')
  await expect(page.locator('tbody .row-id')).toHaveCount(5)
  const copiedTime = await page.locator('tbody .date-cell').nth(1).innerText()
  await page.getByLabel('Sensor type', { exact: true }).selectOption('TIME')
  await expect(page.getByLabel('Sensor time', { exact: true })).toHaveAttribute('type', 'text')
  await page.getByLabel('Sensor time', { exact: true }).fill(copiedTime)
  await page.getByRole('button', { name: 'Filter', exact: true }).click()
  await expect(page.locator('tbody .row-id')).toHaveText(['#2', '#3'])
  expect(queries.at(-1)?.get('from')).toBe('2026-10-07T05:34:56.000Z')
  expect(queries.at(-1)?.get('to')).toBe('2026-10-07T05:34:57.000Z')
  expect(queries.at(-1)?.has('type')).toBe(false)
  expect(queries.at(-1)?.has('search')).toBe(false)
  expect(queries.at(-1)?.has('value')).toBe(false)
  await page.reload()
  await expect(page.getByLabel('Sensor type', { exact: true })).toHaveValue('TIME')
  await expect(page.getByLabel('Sensor time', { exact: true })).toHaveValue(copiedTime)
  await expect(page.locator('tbody .row-id')).toHaveCount(2)
  await page.getByLabel('Sensor time', { exact: true }).fill('2026-10-07T12:34')
  await page.getByRole('button', { name: 'Filter', exact: true }).click()
  await expect(page.locator('tbody .row-id')).toHaveCount(4)
  await page.getByLabel('Sensor type', { exact: true }).selectOption('TEMPERATURE')
  await expect(page.getByLabel('Sensor value', { exact: true })).toHaveValue('')
  await page.getByRole('button', { name: 'Filter', exact: true }).click()
  await expect(page.locator('tbody .row-id')).toHaveText(['#1', '#4'])
  expect(queries.at(-1)?.has('from')).toBe(false)
  expect(queries.at(-1)?.has('to')).toBe(false)
})

test('History filters by device, action, and status without Date & time range filter', async ({ page }) => {
  await useApiSession(page)
  const backend = createMockApi({ latency: 0, persist: false })
  const devices = await backend.devices()
  const historyResponse = await backend.history({ page: 1, page_size: 10 })
  const queries: URLSearchParams[] = []
  await page.route('http://127.0.0.1:5174/api/v1/**', route => {
    const url = new URL(route.request().url()), query = url.searchParams
    if (url.pathname.endsWith('/devices/')) return route.fulfill({ json: { count: devices.length, next: null, previous: null, results: devices } })
    if (url.pathname.endsWith('/device-history/')) {
      queries.push(query)
      return route.fulfill({ json: historyResponse })
    }
    return route.continue()
  })
  await page.goto('http://127.0.0.1:5174/history?from=2099-01-01T00:00:00Z&to=2099-01-02T00:00:00Z')
  await expect(page.locator('tbody .row-id')).toHaveCount(10)
  await expect(page.getByRole('button', { name: 'Date & time range', exact: true })).toHaveCount(0)
  await expect(page.getByLabel('Device', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Action', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Status', { exact: true })).toBeVisible()
  await page.getByLabel('Action', { exact: true }).selectOption('TURN_ON')
  await page.getByRole('button', { name: 'Filter', exact: true }).click()
  await expect.poll(() => queries.at(-1)?.get('action')).toBe('TURN_ON')
  expect(queries.at(-1)?.has('from')).toBe(false)
  expect(queries.at(-1)?.has('to')).toBe(false)
})
