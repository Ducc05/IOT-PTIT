const pad = (value: number) => String(value).padStart(2, '0')

export const dateTime = (value: string | null) => {
  if (!value) return 'No data'
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return 'No data'
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}
export const timeOnly = (value: string, seconds = false) => new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', ...(seconds ? { second: '2-digit' as const } : {}) }).format(new Date(value))
export const number = (value: number | null) => value === null ? '—' : new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(value)
export const sensorLabel = (type: string) => ({ TEMPERATURE: 'Temperature', HUMIDITY: 'Humidity', LIGHT: 'Light' }[type] || type)
export function errorMessage(error: unknown) { return error instanceof Error ? error.message : 'Something went wrong. Please try again.' }
