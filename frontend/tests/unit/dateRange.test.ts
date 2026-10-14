import { afterEach, describe, expect, it, vi } from 'vitest'
import { dateRangeError, localDateTime, midnightRange, parseLocalDateTime } from '../../src/utils/dateRange'
afterEach(() => vi.useRealTimers())
describe('Date range input', () => {
  it('defaults both times to local midnight on consecutive calendar dates', () => {
    vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-06T15:22:00Z'))
    const range = midnightRange()
    expect(range.from).toMatch(/T00:00$/); expect(range.to).toMatch(/T00:00$/)
    const next = new Date(range.from); next.setDate(next.getDate() + 1)
    expect(range.to).toBe(localDateTime(next))
  })
  it('rejects incomplete, reversed and zero-duration ranges', () => {
    expect(dateRangeError('', '')).toBe('')
    expect(dateRangeError('2026-10-06T00:00', '')).not.toBe('')
    expect(dateRangeError('2026-10-06T00:00', '2026-10-06T00:00')).not.toBe('')
    expect(dateRangeError('2026-10-07T00:00', '2026-10-06T00:00')).not.toBe('')
    expect(dateRangeError('2026-10-06T00:00', '2026-10-07T00:00')).toBe('')
  })
  it('rejects invalid dates instead of accepting rolled-over calendar days', () => {
    expect(parseLocalDateTime('2026-02-30T00:00')).toBeNull()
    expect(parseLocalDateTime('2026-10-06T25:00')).toBeNull()
    expect(parseLocalDateTime('not-a-date')).toBeNull()
    expect(localDateTime('not-a-date')).toBe('')
  })
  it('uses minute precision even when a restored timestamp contains seconds', () => {
    for (const input of ['2026-10-06T00:00', '2026-10-06T12:34']) {
      expect(localDateTime(parseLocalDateTime(input)!.toISOString())).toBe(input)
    }
    expect(localDateTime(new Date(2026, 9, 6, 12, 34, 56))).toBe('2026-10-06T12:34')
    expect(parseLocalDateTime('2026-10-06T12:34')!.getSeconds()).toBe(0)
    expect(parseLocalDateTime('2026-10-06T12:34:56')).toBeNull()
  })
})
