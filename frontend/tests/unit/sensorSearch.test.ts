import { describe, expect, it } from 'vitest'
import { createMockApi } from '../../src/api/mock'
import { dateTime } from '../../src/utils/format'
import { parseSensorValue, sensorDataQuery, sensorSearchError, sensorTimeRange, sensorValueError } from '../../src/utils/sensorSearch'

describe('Sensor value search', () => {
  it('accepts exact numeric values including zero, decimals and negatives', () => {
    expect(parseSensorValue('0')).toBe(0)
    expect(parseSensorValue(' 28.50 ')).toBe(28.5)
    expect(parseSensorValue('28,5')).toBe(28.5)
    expect(parseSensorValue('-4.2')).toBe(-4.2)
    for (const text of ['TEMP_01', 'Temperature', '50°C', 'Infinity', '1e2', '']) expect(parseSensorValue(text)).toBeNull()
    expect(sensorValueError('')).toBe('')
    expect(sensorValueError('Temperature')).not.toBe('')
  })
  it('maps UI search to an exact API value without losing type, ordering or pagination', () => {
    expect(sensorDataQuery({ search: '0', type: 'TEMPERATURE', page: 2, page_size: 25, ordering: 'value' })).toEqual({
      search: undefined, value: 0, type: 'TEMPERATURE', page: 2, page_size: 25, ordering: 'value',
    })
    expect(() => sensorDataQuery({ search: 'TEMP_01', page: 1, page_size: 10 })).toThrow('Vui lòng nhập một giá trị số')
  })
  it('combines exact value and sensor type in the mock backend', async () => {
    const backend = createMockApi({ persist: false, latency: 0 })
    const query = { page: 1, page_size: 100 }
    for (const type of ['TEMPERATURE', 'HUMIDITY', 'LIGHT']) {
      const row = (await backend.sensorData({ ...query, type })).results[0]
      const result = await backend.sensorData({ ...query, type, value: row.value })
      expect(result.count).toBeGreaterThan(0)
      expect(result.results.every(item => item.type === type && item.value === row.value)).toBe(true)
      expect((await backend.sensorData({ ...query, type, value: row.value + .01 })).count).toBe(0)
    }
    expect((await backend.sensorData({ ...query, value: 0 })).count).toBe(0)
  })
  it('maps local time to the selected minute or second without sending TIME as a sensor type', () => {
    const minute = sensorTimeRange('2026-10-07T12:34')!
    expect(minute.from).toBe(new Date(2026, 9, 7, 12, 34).toISOString())
    expect(Date.parse(minute.to) - Date.parse(minute.from)).toBe(60000)
    const second = sensorTimeRange('2026-10-07T12:34:56')!
    expect(Date.parse(second.to) - Date.parse(second.from)).toBe(1000)
    const query = sensorDataQuery({ page: 1, page_size: 10, type: 'TIME', search: '2026-10-07T12:34:56' })
    expect(query).toMatchObject(second)
    expect(query.type).toBeUndefined()
    expect(query.search).toBeUndefined()
    expect(query.value).toBeUndefined()
    for (const text of ['2026-02-30T00:00', '2026-10-07T25:00', '2026-10-07T12:34:60', '50']) expect(sensorTimeRange(text)).toBeNull()
    expect(sensorSearchError('TIME', '50')).not.toBe('')
  })
  it('ignores removed Data range parameters and keeps blank searches unfiltered', () => {
    expect(sensorDataQuery({ page: 1, page_size: 10, from: '2099-01-01', to: '2099-01-02' })).toEqual({ page: 1, page_size: 10, search: undefined, value: undefined })
    const blankTime = sensorDataQuery({ page: 1, page_size: 10, type: 'TIME', search: '' })
    expect(blankTime.from).toBeUndefined()
    expect(blankTime.to).toBeUndefined()
    expect(blankTime.type).toBeUndefined()
  })
  it('accepts Date & Time copied from the table in the browser local timezone', () => {
    for (let month = 0; month < 12; month++) {
      const date = new Date(2026, month, 7, 12, 34, 56)
      const displayed = dateTime(date.toISOString())
      const range = sensorTimeRange(`  ${displayed}  `)!
      expect(range.from).toBe(date.toISOString())
      expect(Date.parse(range.to) - Date.parse(range.from)).toBe(1000)
      expect(sensorDataQuery({ page: 1, page_size: 10, type: 'TIME', search: displayed })).toMatchObject(range)
      expect(sensorSearchError('TIME', displayed)).toBe('')
    }
    const minute = sensorTimeRange('7 Oct 2026, 12:34')!
    expect(minute.from).toBe(new Date(2026, 9, 7, 12, 34).toISOString())
    expect(Date.parse(minute.to) - Date.parse(minute.from)).toBe(60000)
    for (const invalid of ['30 Feb 2026, 12:34:56', '7 Oct 2026, 25:34:56', '7 Oct 2026, 12:34:60', '7 Fake 2026, 12:34:56']) {
      expect(sensorTimeRange(invalid)).toBeNull()
    }
  })
})
