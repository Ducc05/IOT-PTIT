export const dateTime = (value: string | null) => value ? new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'medium' }).format(new Date(value)) : 'No data'
export const timeOnly = (value: string, seconds = false) => new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', ...(seconds ? { second: '2-digit' as const } : {}) }).format(new Date(value))
export const number = (value: number | null) => value === null ? '—' : new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(value)
export const sensorLabel = (type: string) => ({ TEMPERATURE: 'Temperature', HUMIDITY: 'Humidity', LIGHT: 'Light' }[type] || type)
export function errorMessage(error: unknown) { return error instanceof Error ? error.message : 'Something went wrong. Please try again.' }
