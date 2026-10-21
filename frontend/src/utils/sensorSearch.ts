import { ApiError } from '../types/api'
import type { ListQuery } from '../types/api'

export const sensorSearchTypes = ['TEMPERATURE', 'HUMIDITY', 'LIGHT', 'TIME']

function parseDateComponents(
  year: number,
  month: number,
  day: number,
  hasHour: boolean,
  hasMin: boolean,
  hasSec: boolean,
  rawHour?: string,
  rawMin?: string,
  rawSec?: string,
): { from: string; to: string } | null {
  const hour = hasHour ? Number(rawHour) : 0
  const minute = hasMin ? Number(rawMin) : 0
  const second = hasSec ? Number(rawSec) : 0

  const start = new Date(year, month - 1, day, hour, minute, second, 0)
  if (
    start.getFullYear() !== year ||
    start.getMonth() !== month - 1 ||
    start.getDate() !== day ||
    start.getHours() !== hour ||
    start.getMinutes() !== minute ||
    start.getSeconds() !== second
  ) {
    return null
  }

  let end: Date
  if (hasSec) {
    end = new Date(start.getTime() + 1000)
  } else if (hasMin) {
    end = new Date(start.getTime() + 60000)
  } else if (hasHour) {
    end = new Date(start.getTime() + 3600000)
  } else {
    end = new Date(year, month - 1, day + 1, 0, 0, 0, 0)
  }

  return { from: start.toISOString(), to: end.toISOString() }
}

export function sensorTimeRange(input: string): { from: string; to: string } | null {
  let text = input.trim().replace(/\s+/g, ' ')
  text = text.replace(/:+$/, '')
  if (!text) return null

  // 1. DD/MM/YYYY [HH[:[MM[:SS]]]] (supporting / . - and : or ::)
  const dmy = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?:[ T](\d{1,2})(?::{1,2}(\d{1,2}))?(?::{1,2}(\d{1,2}))?)?$/.exec(text)
  if (dmy) {
    return parseDateComponents(
      Number(dmy[3]),
      Number(dmy[2]),
      Number(dmy[1]),
      dmy[4] !== undefined,
      dmy[5] !== undefined,
      dmy[6] !== undefined,
      dmy[4],
      dmy[5],
      dmy[6],
    )
  }

  // 2. YYYY-MM-DD [HH[:[MM[:SS]]]] (ISO style)
  const ymd = /^(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[ T](\d{1,2})(?::{1,2}(\d{1,2}))?(?::{1,2}(\d{1,2}))?)?$/.exec(text)
  if (ymd) {
    return parseDateComponents(
      Number(ymd[1]),
      Number(ymd[2]),
      Number(ymd[3]),
      ymd[4] !== undefined,
      ymd[5] !== undefined,
      ymd[6] !== undefined,
      ymd[4],
      ymd[5],
      ymd[6],
    )
  }

  // 3. MM/YYYY (full month)
  const my = /^(\d{1,2})[/.-](\d{4})$/.exec(text)
  if (my) {
    const month = Number(my[1])
    const year = Number(my[2])
    if (month < 1 || month > 12) return null
    const start = new Date(year, month - 1, 1, 0, 0, 0, 0)
    const end = new Date(year, month, 1, 0, 0, 0, 0)
    return { from: start.toISOString(), to: end.toISOString() }
  }

  // 4. YYYY (full year)
  const yOnly = /^(\d{4})$/.exec(text)
  if (yOnly) {
    const year = Number(yOnly[1])
    if (year < 1970 || year > 2100) return null
    const start = new Date(year, 0, 1, 0, 0, 0, 0)
    const end = new Date(year + 1, 0, 1, 0, 0, 0, 0)
    return { from: start.toISOString(), to: end.toISOString() }
  }

  // 5. Legacy displayed format: D Mon YYYY, [HH[:MM[:SS]]]
  const displayed = /^(\d{1,2}) ([a-z]{3,4}) (\d{4}),?(?: (\d{1,2})(?::{1,2}(\d{1,2}))?(?::{1,2}(\d{1,2}))?)?$/i.exec(text)
  if (displayed) {
    const months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
    const month = months.indexOf(displayed[2].toLowerCase().replace(/^sept$/, 'sep')) + 1
    if (!month) return null
    return parseDateComponents(
      Number(displayed[3]),
      month,
      Number(displayed[1]),
      displayed[4] !== undefined,
      displayed[5] !== undefined,
      displayed[6] !== undefined,
      displayed[4],
      displayed[5],
      displayed[6],
    )
  }

  return null
}

export function parseSensorValue(input: string): number | null {
  const text = input.trim()
  if (!/^[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)$/.test(text)) return null
  const value = Number(text.replace(',', '.'))
  return Number.isFinite(value) ? value : null
}

export function sensorValueError(input: string) {
  return input.trim() && parseSensorValue(input) === null
    ? 'Vui lòng nhập một giá trị số, ví dụ 28.5.'
    : ''
}

export function sensorSearchError(type: string | undefined, input: string) {
  if (type === 'TIME') return input.trim() && !sensorTimeRange(input) ? 'Vui lòng nhập ngày giờ hợp lệ, ví dụ 21/10/2026 12:34:56.' : ''
  return sensorValueError(input)
}

export function historySearchError(input: string): string {
  const text = input.trim()
  if (!text) return ''
  if ((/[/:]/.test(text) || /^\d{4}-\d{2}/.test(text)) && !sensorTimeRange(text)) {
    return 'Vui lòng nhập ngày giờ hợp lệ, ví dụ 21/10/2026 12:34:56.'
  }
  return ''
}

// UI search is a measured value; API search remains the legacy code/name query.
export function sensorDataQuery(input: ListQuery): ListQuery {
  // Removed Data range controls must not keep filtering through old URLs.
  const { from: _from, to: _to, ...query } = input
  const search = query.search?.trim()
  if (query.type === 'TIME') {
    const range = search ? sensorTimeRange(search) : null
    if (search && !range) throw new ApiError('VALIDATION_ERROR', sensorSearchError('TIME', search), 400)
    return { ...query, search: undefined, type: undefined, value: undefined, ...(range || {}) }
  }
  const value = search ? parseSensorValue(search) : query.value
  if (search && value === null) throw new ApiError('VALIDATION_ERROR', sensorValueError(search), 400)
  return { ...query, search: undefined, value: value ?? undefined }
}

export function historyDataQuery(input: ListQuery): ListQuery {
  const { from: _from, to: _to, ...query } = input
  const search = query.search?.trim()
  if (!search) return query
  const range = sensorTimeRange(search)
  if (range) {
    return { ...query, search: undefined, ...range }
  }
  return query
}
