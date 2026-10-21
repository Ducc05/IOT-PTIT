import { describe, expect, it } from 'vitest'
import { createMockApi } from '../../src/api/mock'
import { dateTime } from '../../src/utils/format'
import {
  historyDataQuery,
  historySearchError,
  parseSensorValue,
  sensorDataQuery,
  sensorSearchError,
  sensorTimeRange,
  sensorValueError,
} from '../../src/utils/sensorSearch'

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
  it('formats dateTime as DD/MM/YYYY HH:mm:ss and parses various granularity levels', () => {
    const date = new Date(2026, 9, 21, 13, 45, 30) // 21/10/2026 13:45:30
    expect(dateTime(date.toISOString())).toBe('21/10/2026 13:45:30')
    expect(dateTime(null)).toBe('No data')
    expect(dateTime('invalid-date')).toBe('No data')

    // 1. Full seconds (: and ::)
    const exact = sensorTimeRange('21/10/2026 13:45:30')!
    expect(exact.from).toBe(date.toISOString())
    expect(Date.parse(exact.to) - Date.parse(exact.from)).toBe(1000)

    const exactDoubleColon = sensorTimeRange('21/10/2026 13::45::30')!
    expect(exactDoubleColon.from).toBe(date.toISOString())
    expect(Date.parse(exactDoubleColon.to) - Date.parse(exactDoubleColon.from)).toBe(1000)

    // 2. Missing SS -> minute (: and ::)
    const minute = sensorTimeRange('21/10/2026 13:45')!
    expect(minute.from).toBe(new Date(2026, 9, 21, 13, 45, 0).toISOString())
    expect(Date.parse(minute.to) - Date.parse(minute.from)).toBe(60000)

    const minuteDoubleColon = sensorTimeRange('21/10/2026 13::45')!
    expect(minuteDoubleColon.from).toBe(new Date(2026, 9, 21, 13, 45, 0).toISOString())
    expect(Date.parse(minuteDoubleColon.to) - Date.parse(minuteDoubleColon.from)).toBe(60000)

    // 3. Missing MM & SS -> hour
    const hour = sensorTimeRange('21/10/2026 13')!
    expect(hour.from).toBe(new Date(2026, 9, 21, 13, 0, 0).toISOString())
    expect(Date.parse(hour.to) - Date.parse(hour.from)).toBe(3600000)

    const hourWithColon = sensorTimeRange('21/10/2026 13:')!
    expect(hourWithColon.from).toBe(hour.from)
    expect(hourWithColon.to).toBe(hour.to)

    // 4. Missing time -> full day
    const day = sensorTimeRange('21/10/2026')!
    expect(day.from).toBe(new Date(2026, 9, 21, 0, 0, 0).toISOString())
    expect(day.to).toBe(new Date(2026, 9, 22, 0, 0, 0).toISOString())

    // 5. Missing day -> full month
    const month = sensorTimeRange('10/2026')!
    expect(month.from).toBe(new Date(2026, 9, 1, 0, 0, 0).toISOString())
    expect(month.to).toBe(new Date(2026, 10, 1, 0, 0, 0).toISOString())

    // 6. Missing month -> full year
    const year = sensorTimeRange('2026')!
    expect(year.from).toBe(new Date(2026, 0, 1, 0, 0, 0).toISOString())
    expect(year.to).toBe(new Date(2027, 0, 1, 0, 0, 0).toISOString())

    // Calendar validations
    for (const invalid of [
      '31/02/2026',
      '29/02/2025',
      '31/04/2026',
      '21/10/2026 25:00',
      '21/10/2026 13:60',
      '21/10/2026 13:45:60',
      '13/2026',
      '00/2026',
    ]) {
      expect(sensorTimeRange(invalid)).toBeNull()
    }
    // Leap year acceptance
    expect(sensorTimeRange('29/02/2024')).not.toBeNull()
  })
  it('transforms history query for datetime searches and validates errors', () => {
    expect(historySearchError('')).toBe('')
    expect(historySearchError('42')).toBe('')
    expect(historySearchError('21/10/2026')).toBe('')
    expect(historySearchError('31/02/2026')).toBe('Vui lòng nhập ngày giờ hợp lệ, ví dụ 21/10/2026 12:34:56.')

    // Normal history ID search
    expect(historyDataQuery({ page: 1, page_size: 10, search: '42' })).toEqual({
      page: 1,
      page_size: 10,
      search: '42',
    })

    // Datetime search in history
    const transformed = historyDataQuery({ page: 1, page_size: 10, search: '21/10/2026 13:45' })
    expect(transformed.search).toBeUndefined()
    expect(transformed.from).toBe(new Date(2026, 9, 21, 13, 45, 0).toISOString())
    expect(transformed.to).toBe(new Date(2026, 9, 21, 13, 46, 0).toISOString())
  })
})
