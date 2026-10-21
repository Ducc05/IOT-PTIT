import { ApiError } from '../types/api'
import type { CommandResource, ControlRequest, Device, IoTApi, ListQuery, PageResponse, SensorDataRow, SensorLatestResponse, SensorTrendsResponse, SensorType } from '../types/api'

const STORAGE_KEY = 'iot-demo-database-v2'
const types: SensorType[] = ['TEMPERATURE', 'HUMIDITY', 'LIGHT']
const names = ['Temperature', 'Humidity', 'Light']
const codes = ['TEMP_01', 'HUM_01', 'LIGHT_01']
const units = ['°C', '%', 'lux']
const mockUsers = ['admin_alex', 'operator_1', 'sarah_k', 'm.turner', 'jdoe', 'system_bot', 'alex.w']
interface Database {
  readings: SensorDataRow[]; devices: Device[]; history: CommandResource[]
}
const copy = <T>(value: T): T => structuredClone(value)
const iso = (time: number) => new Date(time).toISOString()

function readingsAt(time: number, sequence: number): SensorDataRow[] {
  return types.map((type, index) => ({
    id: sequence + index, sensor: { id: index + 1, sensor_code: codes[index], name: names[index] },
    type, unit: units[index], value: index === 0 ? +(26 + Math.sin(time / 180000) * 2.5).toFixed(1)
      : index === 1 ? +(62 + Math.cos(time / 230000) * 8).toFixed(1) : Math.round(700 + Math.sin(time / 210000) * 240),
    measured_at: iso(time), created_at: iso(time),
  }))
}

function commandFor(device: Device, action: ControlRequest['action'], id: number, time: number, status: CommandResource['status'] = 'PENDING', username = 'admin_alex'): CommandResource {
  const command_id = crypto.randomUUID()
  const requested_state = action === 'TURN_ON' ? 'ON' : 'OFF'
  return {
    id, command_id, device: { id: device.id, device_code: device.device_code, name: device.name }, user: username,
    action, requested_state, actual_state: status === 'SUCCESS' ? requested_state : null,
    current_state: device.current_state, state_confirmed_at: device.state_confirmed_at,
    status, error_code: status === 'FAILED' ? 'DEVICE_ERROR' : status === 'TIMEOUT' ? 'DEVICE_COMMAND_TIMEOUT' : null,
    error_message: status === 'FAILED' ? 'Device did not accept the command.' : status === 'TIMEOUT' ? 'Device response timed out.' : null,
    late_response: false, created_at: iso(time), expires_at: iso(time + 5000),
    completed_at: status === 'PENDING' ? null : iso(time + 1000), reported_at: status === 'SUCCESS' ? iso(time + 1000) : null,
    status_url: `/api/v1/device-history/${command_id}/`,
  }
}

function seed(): Database {
  const now = Date.now()
  const devices: Device[] = ['LED Light', 'Cooling Fan', 'Water Pump', 'Alert Buzzer'].map((name, i) => ({
    id: i + 1, name, controller_id: 'ESP32_01', device_code: ['LED_01', 'FAN_01', 'PUMP_01', 'BUZZER_01'][i],
    type: i === 0 ? 'LIGHT' : i === 1 ? 'FAN' : 'OTHER', current_state: i === 0 ? 'ON' : 'OFF',
    availability: 'ONLINE', state_confirmed_at: iso(now), pending_command: null,
  }))
  const readings: SensorDataRow[] = []
  let sequence = 1
  for (let i = 360; i >= 0; i--) { readings.push(...readingsAt(now - i * 240000, sequence)); sequence += 3 }
  const history = Array.from({ length: 100 }, (_, i) => commandFor(devices[i % 4], i % 2 ? 'TURN_OFF' : 'TURN_ON', i + 1, now - (100 - i) * 900000,
    i % 17 === 0 ? 'TIMEOUT' : i % 11 === 0 ? 'FAILED' : 'SUCCESS', mockUsers[i % mockUsers.length]))
  return { readings, devices, history }
}

export function createMockApi(options: { latency?: number; persist?: boolean } = {}): IoTApi {
  const persist = options.persist !== false
  const latency = options.latency ?? 180
  let db = seed()
  try {
    const stored = persist ? localStorage.getItem(STORAGE_KEY) : null
    if (stored) db = JSON.parse(stored) as Database
  } catch { /* Storage may be unavailable; the in-memory backend still works. */ }
  // Upgrade existing mock records without replacing readings or command state.
  db.history.forEach(command => {
    if (command.user === undefined) command.user = mockUsers[(command.id - 1) % mockUsers.length]
  })
  function save() { try { if (persist) localStorage.setItem(STORAGE_KEY, JSON.stringify(db)) } catch { /* Memory fallback. */ } }
  function sync() {
    const now = Date.now()
    for (const command of db.history.filter(h => h.status === 'PENDING')) {
      if (now - Date.parse(command.created_at) < 1400) continue
      const device = db.devices.find(d => d.id === command.device.id)!
      command.status = 'SUCCESS'; command.actual_state = command.requested_state
      command.completed_at = iso(now); command.reported_at = iso(now)
      device.current_state = command.requested_state; device.state_confirmed_at = iso(now); device.pending_command = null
    }
    db.history.forEach(h => {
      const d = db.devices.find(device => device.id === h.device.id)!
      h.current_state = d.current_state; h.state_confirmed_at = d.state_confirmed_at
    })
    save()
  }
  async function respond<T>(get: () => T, signal?: AbortSignal): Promise<T> {
    signal?.throwIfAborted()
    if (latency) await new Promise<void>((resolve, reject) => {
      const abort = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }
      const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve() }, latency)
      signal?.addEventListener('abort', abort, { once: true })
    })
    signal?.throwIfAborted(); sync()
    return copy(get())
  }
  function page<T>(rows: T[], q: ListQuery, endpoint: string): PageResponse<T> {
    if (!Number.isInteger(q.page) || q.page < 1 || !Number.isInteger(q.page_size) || q.page_size < 1 || q.page_size > 100)
      throw new ApiError('VALIDATION_ERROR', 'Invalid pagination.', 400)
    if (q.page > Math.max(1, Math.ceil(rows.length / q.page_size))) throw new ApiError('PAGE_NOT_FOUND', 'This page no longer exists.', 404)
    const link = (n: number) => `/api/v1/${endpoint}/?${new URLSearchParams(Object.entries({ ...q, page: n }).filter(([, v]) => v !== '' && v !== undefined).map(([k, v]) => [k, String(v)]))}`
    return { count: rows.length, next: q.page * q.page_size < rows.length ? link(q.page + 1) : null,
      previous: q.page > 1 ? link(q.page - 1) : null, results: rows.slice((q.page - 1) * q.page_size, q.page * q.page_size) }
  }
  function inRange(time: string, q: ListQuery) {
    if ((q.from && !Number.isFinite(Date.parse(q.from))) || (q.to && !Number.isFinite(Date.parse(q.to))) || (q.from && q.to && Date.parse(q.from) >= Date.parse(q.to)))
      throw new ApiError('INVALID_DATE_RANGE', 'From must be earlier than To.', 400)
    return (!q.from || Date.parse(time) >= Date.parse(q.from)) && (!q.to || Date.parse(time) < Date.parse(q.to))
  }
  function sorted<T extends { id: number }>(rows: T[], ordering: string, value: (row: T) => number) {
    const direction = ordering.startsWith('-') ? -1 : 1
    return rows.sort((a, b) => direction * (value(a) - value(b) || a.id - b.id))
  }
  return {
    sensorLatest: signal => respond<SensorLatestResponse>(() => ({
      generated_at: iso(Date.now()),
      latest_sensors: types.map((type, i) => {
        const row = db.readings.findLast(r => r.type === type)!
        return { sensor_id: row.sensor.id, sensor_code: row.sensor.sensor_code ?? null, name: names[i], type,
          value: row.value, unit: row.unit, measured_at: row.measured_at, created_at: row.created_at, status: 'OK' }
      }),
    }), signal),
    sensorTrends: signal => respond<SensorTrendsResponse>(() => ({
      generated_at: iso(Date.now()), effective_interval: 'raw',
      trends: db.readings.filter(r => r.type === 'TEMPERATURE').slice(-20).map(row => {
        const group = db.readings.filter(r => r.created_at === row.created_at)
        return { timestamp: row.created_at, temperature: row.value, humidity: group.find(r => r.type === 'HUMIDITY')?.value ?? null, light: group.find(r => r.type === 'LIGHT')?.value ?? null }
      }),
    }), signal),
    sensorData: (q, signal) => respond(() => {
      const search = q.search?.trim().toLowerCase() || ''
      if (q.value !== undefined && !Number.isFinite(q.value)) throw new ApiError('VALIDATION_ERROR', 'Giá trị tìm kiếm phải là số.', 400)
      const rows = db.readings.filter(r => (!q.type || r.type === q.type) && (q.value === undefined || r.value === q.value) && (!search || `${r.sensor.sensor_code} ${r.sensor.name}`.toLowerCase().includes(search)) && inRange(r.created_at, q))
      return page(sorted(rows, q.ordering || '-created_at', r => q.ordering?.includes('value') ? r.value : Date.parse(r.created_at)), q, 'sensor-data')
    }, signal),
    history: (q, signal) => respond(() => {
      const search = q.search?.trim() || ''
      const rows = db.history.filter(r => (!search || (/^\d+$/.test(search) ? r.id === Number(search) : r.command_id.toLowerCase() === search.toLowerCase())) && (!q.device || r.device.id === q.device)
        && (!q.action || r.action === q.action) && (!q.status || r.status === q.status) && inRange(r.created_at, q))
      return page(sorted(rows, q.ordering || '-created_at', r => Date.parse(r.created_at)), q, 'device-history')
    }, signal),
    devices: signal => respond(() => db.devices, signal),
    control: (id, body, signal) => respond(() => {
      const device = db.devices.find(d => d.id === id)
      if (!device) throw new ApiError('DEVICE_NOT_FOUND', 'Device not found.', 404)
      if (device.pending_command) throw new ApiError('DEVICE_COMMAND_IN_PROGRESS', 'A command is already processing.', 409, { command_id: device.pending_command.command_id })
      const command = commandFor(device, body.action, (db.history.at(-1)?.id ?? 0) + 1, Date.now())
      device.pending_command = { command_id: command.command_id, requested_state: command.requested_state, expires_at: command.expires_at, status_url: command.status_url }
      db.history.push(command); save()
      return command
    }, signal),
    command: (id, signal) => respond(() => {
      const command = db.history.find(h => h.command_id === id)
      if (!command) throw new ApiError('COMMAND_NOT_FOUND', 'Command not found.', 404)
      return command
    }, signal),
  }
}
