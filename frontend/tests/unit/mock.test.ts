import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMockApi } from '../../src/api/mock'
import type { IoTApi, ListQuery } from '../../src/types/api'
const query: ListQuery = { page: 1, page_size: 15 }
let api: IoTApi
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-06T12:00:00Z')); api = createMockApi({ latency: 0, persist: false }) })
afterEach(() => vi.useRealTimers())
describe('Mock backend contract', () => {
  it('combines search/type/range, sorts and paginates sensor readings', async () => {
    const all = await api.sensorData({ ...query, search: 'temp_01', type: 'TEMPERATURE', from: '2026-10-06T11:00:00Z', to: '2026-10-06T12:00:00Z', ordering: 'value', page_size: 5 })
    expect(all.count).toBe(15); expect(all.results).toHaveLength(5); expect(all.next).toContain('search=temp_01')
    expect(all.results.every(r => r.type === 'TEMPERATURE' && r.created_at < '2026-10-06T12:00:00.000Z')).toBe(true)
    expect(all.results.map(r => r.value)).toEqual(all.results.map(r => r.value).sort((a, b) => a - b))
    const next = await api.sensorData({ ...query, search: 'temp_01', type: 'TEMPERATURE', from: '2026-10-06T11:00:00Z', to: '2026-10-06T12:00:00Z', ordering: 'value', page_size: 5, page: 2 })
    expect(next.results.some(r => all.results.some(a => a.id === r.id))).toBe(false)
  })
  it('enforces an exclusive upper date boundary and invalid range validation', async () => {
    const single = await api.sensorData({ ...query, from: '2026-10-06T12:00:00Z', to: '2026-10-06T12:00:01Z' })
    expect(single.count).toBe(3)
    await expect(api.sensorData({ ...query, from: '2026-10-06T12:00:00Z', to: '2026-10-06T11:00:00Z' })).rejects.toMatchObject({ code: 'INVALID_DATE_RANGE' })
    await expect(api.sensorData({ ...query, page: 999 })).rejects.toMatchObject({ code: 'PAGE_NOT_FOUND' })
  })
  it('supports exact history ID/UUID and AND filters', async () => {
    const list = await api.history({ ...query, device: 1, action: 'TURN_ON', status: 'SUCCESS' })
    expect(list.count).toBeGreaterThan(0)
    expect(list.results.every(r => r.device.id === 1 && r.action === 'TURN_ON' && r.status === 'SUCCESS')).toBe(true)
    const row = list.results[0]
    expect((await api.history({ ...query, search: String(row.id) })).results[0].command_id).toBe(row.command_id)
    expect((await api.history({ ...query, search: row.command_id })).count).toBe(1)
    expect((await api.history({ ...query, search: 'LED' })).count).toBe(0)
  })
  it('rejects controls while pending and creates a new command after completion', async () => {
    const body = { action: 'TURN_OFF' as const }
    const command = await api.control(1, body)
    expect(command.status).toBe('PENDING')
    await expect(api.control(1, body)).rejects.toMatchObject({ code: 'DEVICE_COMMAND_IN_PROGRESS' })
    await expect(api.control(1, { action: 'TURN_ON' })).rejects.toMatchObject({ code: 'DEVICE_COMMAND_IN_PROGRESS' })
    expect((await api.devices())[0].current_state).toBe('ON')
    vi.advanceTimersByTime(1600)
    expect((await api.command(command.command_id)).status).toBe('SUCCESS')
    expect((await api.devices())[0].current_state).toBe('OFF')
    expect((await api.history({ ...query, status: 'SUCCESS', search: String(command.id) })).count).toBe(1)
    const next = await api.control(1, body)
    expect(next.status).toBe('PENDING')
    expect(next.command_id).not.toBe(command.command_id)
  })
  it('keeps mock readings and history stable over time', async () => {
    const before = await api.sensorLatest(); const beforeTrends = await api.sensorTrends(); const beforeDevices = await api.devices(); const count = (await api.sensorData(query)).count
    const history = (await api.history(query)).count
    vi.advanceTimersByTime(21000)
    const after = await api.sensorLatest(); const afterTrends = await api.sensorTrends(); const afterDevices = await api.devices()
    expect(after.latest_sensors).toEqual(before.latest_sensors)
    expect(afterDevices).toEqual(beforeDevices)
    expect(afterTrends.trends).toEqual(beforeTrends.trends)
    expect((await api.sensorData(query)).count).toBe(count)
    expect((await api.history(query)).count).toBe(history)
  })
  it('respects an aborted request', async () => {
    const controller = new AbortController(); controller.abort()
    await expect(api.sensorLatest(controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
  })
})
