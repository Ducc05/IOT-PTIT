import { auth } from './auth'
import { ApiError } from '../types/api'
import type { IoTApi, ListQuery, PageResponse, Device, SensorDataRow, SensorLatest, SensorLatestResponse, SensorRegistryRow, SensorTrendPoint, SensorTrendsResponse, SensorType } from '../types/api'

const sensorTypes: SensorType[] = ['TEMPERATURE', 'HUMIDITY', 'LIGHT']
const sensorDefaults = [{ name: 'Temperature', unit: '°C' }, { name: 'Humidity', unit: '%' }, { name: 'Light', unit: 'ADC' }]

export function createHttpApi(baseUrl: string): IoTApi {
  const base = baseUrl.replace(/\/$/, '')
  async function request<T>(path: string, signal?: AbortSignal, body?: unknown): Promise<T> {
    const timeout = AbortSignal.timeout(12000)
    const requestSignal = signal ? AbortSignal.any([signal, timeout]) : timeout
    async function send(token: string | null) {
      try {
        return await fetch(`${base}${path}`, {
          signal: requestSignal, cache: 'no-store', method: body ? 'POST' : 'GET',
          headers: { Accept: 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          ...(body ? { body: JSON.stringify(body) } : {}),
        })
      } catch (cause) {
        if (requestSignal.aborted) throw cause
        throw new ApiError('NETWORK_ERROR', 'Cannot reach the backend.')
      }
    }
    let token = auth.accessToken()
    if (!token) throw new ApiError('AUTHENTICATION_REQUIRED', 'Sign in to continue.', 401)
    let response = await send(token)
    if (response.status === 401) {
      token = await auth.refresh()
      if (!token) throw new ApiError('AUTHENTICATION_REQUIRED', 'Session expired. Sign in again.', 401)
      response = await send(token)
    }
    if (response.status === 401) auth.logout()
    const data = await response.json().catch(() => { throw new ApiError('NETWORK_ERROR', 'The server returned an invalid response.') })
    if (!response.ok) throw new ApiError(data.error?.code || 'HTTP_ERROR', data.error?.message || data.detail || 'Unable to load data.', response.status, data.error?.details)
    return data as T
  }
  function query(q: ListQuery) {
    const params = new URLSearchParams()
    Object.entries(q).forEach(([k, v]) => { if (k !== 'page' && k !== 'page_size' && v !== undefined && v !== '') params.set(k, String(v)) })
    params.set('limit', String(q.page_size))
    params.set('offset', String((q.page - 1) * q.page_size))
    return params.toString()
  }
  async function activeSensors(signal?: AbortSignal) {
    const sensors: SensorRegistryRow[] = []
    let offset = 0
    while (true) {
      const data = await request<PageResponse<SensorRegistryRow>>(`/sensors/?status=ACTIVE&limit=100&offset=${offset}`, signal)
      sensors.push(...data.results)
      if (!data.next) return sensors
      offset += 100
    }
  }
  async function sensorLatest(signal?: AbortSignal): Promise<SensorLatestResponse> {
    const sensors = await activeSensors(signal)
    const latest_sensors = await Promise.all(sensorTypes.map(async (type, index) => {
      const sensor = sensors.find(item => item.type === type)
      const row = sensor
        ? (await request<PageResponse<SensorDataRow>>(`/sensor-data/?type=${type}&sensor_status=ACTIVE&ordering=-created_at,-id&limit=1&offset=0`, signal)).results[0]
        : undefined
      const created_at = row?.created_at ?? null
      const status: SensorLatest['status'] = !row ? 'NO_DATA' : Date.now() - Date.parse(row.created_at) > 60_000 ? 'STALE' : 'OK'
      return {
        sensor_id: sensor?.id ?? null, sensor_code: null, name: sensor?.name ?? sensorDefaults[index].name,
        type, unit: sensor?.unit ?? sensorDefaults[index].unit, value: row?.value ?? null,
        created_at, measured_at: row?.measured_at ?? null, status,
      }
    }))
    return { generated_at: new Date().toISOString(), latest_sensors }
  }
  async function sensorTrends(signal?: AbortSignal): Promise<SensorTrendsResponse> {
    const rows: SensorDataRow[] = []
    const selectedTimes = new Set<string>()
    let offset = 0
    while (true) {
      const page = await request<PageResponse<SensorDataRow>>(
        `/sensor-data/?sensor_status=ACTIVE&ordering=-created_at,-id&limit=100&offset=${offset}`, signal,
      )
      for (const row of page.results) {
        rows.push(row)
        selectedTimes.add(row.created_at)
      }
      offset += page.results.length
      if (!page.next || !page.results.length) break
      if (selectedTimes.size >= 20 && page.results.at(-1)?.created_at !== [...selectedTimes][19]) break
    }
    const times = [...selectedTimes].slice(0, 20).reverse()
    const sums = new Map<string, { temperature: number[]; humidity: number[]; light: number[] }>()
    for (const time of times) sums.set(time, { temperature: [], humidity: [], light: [] })
    for (const row of rows) {
      const point = sums.get(row.created_at)
      if (point) point[row.type.toLowerCase() as 'temperature' | 'humidity' | 'light'].push(row.value)
    }
    const average = (values: number[]) => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null
    const trends: SensorTrendPoint[] = times.map(timestamp => {
      const point = sums.get(timestamp)!
      return { timestamp, temperature: average(point.temperature), humidity: average(point.humidity), light: average(point.light) }
    })
    return { generated_at: new Date().toISOString(), effective_interval: 'raw', trends }
  }
  return {
    sensorLatest,
    sensorTrends,
    sensorData: (q, signal) => request(`/sensor-data/?${query(q)}`, signal),
    history: (q, signal) => request(`/device-history/?${query(q)}`, signal),
    devices: async signal => {
      const all: Device[] = []
      let offset = 0
      while (true) {
        const data = await request<PageResponse<Device>>(`/devices/?limit=100&offset=${offset}`, signal)
        all.push(...data.results)
        if (!data.next) return all
        offset += 100
      }
    },
    control: (id, body, signal) => request(`/devices/${id}/control/`, signal, body),
    command: (id, signal) => request(`/device-history/${encodeURIComponent(id)}/`, signal),
  }
}
