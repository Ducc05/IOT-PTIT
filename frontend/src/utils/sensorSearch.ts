import { ApiError } from '../types/api'
import type { ListQuery } from '../types/api'
import { parseLocalDateTime } from './dateRange'

export const sensorSearchTypes = ['TEMPERATURE', 'HUMIDITY', 'LIGHT', 'TIME']

export function sensorTimeRange(input: string): { from: string; to: string } | null {
  let text = input.trim().replace(/\s+/g, ' ')
  const displayed = /^(\d{1,2}) ([a-z]{3,4}) (\d{4}),? (\d{2}:\d{2}(?::\d{2})?)$/i.exec(text)
  if (displayed) {
    const months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
    const month = months.indexOf(displayed[2].toLowerCase().replace(/^sept$/, 'sep')) + 1
    if (!month) return null
    text = `${displayed[3]}-${String(month).padStart(2, '0')}-${displayed[1].padStart(2, '0')}T${displayed[4]}`
  }
  const match = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})(?::(\d{2}))?$/.exec(text)
  if (!match) return null
  const date = parseLocalDateTime(match[1])
  if (!date || (match[2] !== undefined && Number(match[2]) > 59)) return null
  date.setSeconds(Number(match[2] || 0))
  return { from: date.toISOString(), to: new Date(date.getTime() + (match[2] === undefined ? 60000 : 1000)).toISOString() }
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
  if (type === 'TIME') return input.trim() && !sensorTimeRange(input) ? 'Vui lòng nhập ngày giờ hợp lệ, ví dụ 21 Oct 2026, 12:34:56.' : ''
  return sensorValueError(input)
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
