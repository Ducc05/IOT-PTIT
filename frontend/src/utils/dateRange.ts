const pad = (value: number) => String(value).padStart(2, '0')

export function localDateTime(value: string | Date) {
  const date = value instanceof Date ? value : new Date(value)
  if (!Number.isFinite(date.getTime())) return ''
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function parseLocalDateTime(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return null
  const date = new Date(value)
  return localDateTime(date) === value ? date : null
}

export function dateRangeError(from: string, to: string) {
  if (!from && !to) return ''
  if (!from || !to) return 'Vui lòng chọn cả thời điểm bắt đầu và kết thúc.'
  const start = parseLocalDateTime(from), end = parseLocalDateTime(to)
  if (!start || !end) return 'Ngày hoặc giờ không hợp lệ.'
  if (start >= end) return 'Thời điểm kết thúc phải sau thời điểm bắt đầu.'
  return ''
}

export function midnightRange() {
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  const end = new Date(start)
  end.setDate(end.getDate() + 1)
  return { from: localDateTime(start), to: localDateTime(end) }
}
