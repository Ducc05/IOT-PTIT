import { auth } from './auth'
import { ApiError } from '../types/api'
import type { IoTApi, ListQuery, PageResponse, Device } from '../types/api'

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
  return {
    sensorLatest: signal => request('/sensor-data/latest/', signal),
    sensorTrends: signal => request('/sensor-data/trends/?samples=20', signal),
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
