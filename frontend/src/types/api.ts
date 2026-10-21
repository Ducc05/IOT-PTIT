export type SensorType = 'TEMPERATURE' | 'HUMIDITY' | 'LIGHT'
export type DeviceState = 'ON' | 'OFF' | null
export type DeviceAction = 'TURN_ON' | 'TURN_OFF'
export type CommandStatus = 'PENDING' | 'SUCCESS' | 'FAILED' | 'TIMEOUT'
export interface SensorLatest {
  sensor_id: number | null; sensor_code: string | null; name: string; type: SensorType
  value: number | null; unit: string; measured_at: string | null; created_at: string | null
  status: 'OK' | 'STALE' | 'NO_DATA'
}
export interface SensorTrendPoint {
  timestamp: string; temperature: number | null; humidity: number | null; light: number | null
}
export interface Device {
  id: number; controller_id: string; device_code: string; name: string
  type: 'LIGHT' | 'FAN' | 'AIR_CONDITIONER' | 'OTHER'; current_state: DeviceState
  state_confirmed_at: string | null; availability: 'ONLINE' | 'OFFLINE' | 'UNKNOWN' | 'STALE'
  pending_command: { command_id: string; requested_state: 'ON' | 'OFF'; expires_at: string; status_url: string } | null
}
export interface SensorLatestResponse {
  generated_at: string; latest_sensors: SensorLatest[]
}
export interface SensorTrendsResponse {
  generated_at: string; effective_interval: 'raw' | '1m' | '5m' | '1h'; trends: SensorTrendPoint[]
}
export interface SensorDataRow {
  id: number; sensor: { id: number; sensor_code?: string | null; name: string }; type: SensorType
  value: number; unit: string; measured_at: string | null; created_at: string
}
export interface SensorRegistryRow { id: number; name: string; type: SensorType; unit: string; status: 'ACTIVE' | 'INACTIVE' }
export interface CommandResource {
  id: number; command_id: string; device: { id: number; device_code: string; name: string }
  user: string
  action: DeviceAction; requested_state: 'ON' | 'OFF'; actual_state: DeviceState; current_state: DeviceState
  state_confirmed_at: string | null; status: CommandStatus; error_code: string | null; error_message: string | null
  late_response: boolean | null; created_at: string; expires_at: string; completed_at: string | null
  reported_at: string | null; status_url: string
}
export interface PageResponse<T> { count: number; next: string | null; previous: string | null; results: T[] }
export interface ListQuery {
  search?: string; type?: string; device?: number; action?: string; status?: string
  value?: number
  from?: string; to?: string; ordering?: string; page: number; page_size: number
}
export interface ControlRequest { action: DeviceAction }
export interface IoTApi {
  sensorLatest(signal?: AbortSignal): Promise<SensorLatestResponse>
  sensorTrends(signal?: AbortSignal): Promise<SensorTrendsResponse>
  sensorData(query: ListQuery, signal?: AbortSignal): Promise<PageResponse<SensorDataRow>>
  history(query: ListQuery, signal?: AbortSignal): Promise<PageResponse<CommandResource>>
  devices(signal?: AbortSignal): Promise<Device[]>
  control(id: number, body: ControlRequest, signal?: AbortSignal): Promise<CommandResource>
  command(id: string, signal?: AbortSignal): Promise<CommandResource>
}
export class ApiError extends Error {
  constructor(public code: string, message: string, public status = 0, public details: Record<string, unknown> = {}) { super(message) }
}
