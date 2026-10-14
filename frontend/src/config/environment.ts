function positive(value: string | undefined, fallback: number) {
  const n = Number(value)
  return Number.isFinite(n) && n >= 250 ? n : fallback
}
export const environment = {
  source: import.meta.env.VITE_DATA_SOURCE === 'mock' ? 'mock' : 'api',
  baseUrl: (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/$/, ''),
  refreshMs: positive(import.meta.env.VITE_REFRESH_MS, 4000),
  trendsRefreshMs: positive(import.meta.env.VITE_TRENDS_REFRESH_MS, 4000),
  commandPollMs: positive(import.meta.env.VITE_COMMAND_POLL_MS, 750),
  commandTimeoutMs: positive(import.meta.env.VITE_COMMAND_CLIENT_TIMEOUT_MS, 10000),
}
