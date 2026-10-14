import type { Route } from '@playwright/test'
import type { SensorDataRow, SensorLatestResponse, SensorRegistryRow, SensorTrendsResponse, SensorType } from '../../../src/types/api'

const types: SensorType[] = ['TEMPERATURE', 'HUMIDITY', 'LIGHT']

export async function fulfillDashboardLists(route: Route, latest: SensorLatestResponse, trends: SensorTrendsResponse): Promise<boolean> {
  const url = new URL(route.request().url())
  const limit = Number(url.searchParams.get('limit') || 15)
  const offset = Number(url.searchParams.get('offset') || 0)
  const page = <T>(results: T[]) => ({
    count: results.length,
    next: offset + limit < results.length ? 'next' : null,
    previous: offset ? 'previous' : null,
    results: results.slice(offset, offset + limit),
  })
  const sensors: SensorRegistryRow[] = latest.latest_sensors.flatMap(sensor => sensor.sensor_id === null ? [] : [{
    id: sensor.sensor_id, name: sensor.name, type: sensor.type, unit: sensor.unit, status: 'ACTIVE' as const,
  }])
  if (url.pathname.endsWith('/sensors/')) {
    await route.fulfill({ json: page(sensors) })
    return true
  }
  if (!url.pathname.endsWith('/sensor-data/')) return false
  const rows: SensorDataRow[] = trends.trends.flatMap((point, timeIndex) => types.flatMap((type, typeIndex) => {
    const sensor = sensors.find(item => item.type === type)
    const value = point[type.toLowerCase() as 'temperature' | 'humidity' | 'light']
    return sensor && value !== null ? [{
      id: timeIndex * 3 + typeIndex + 1, sensor: { id: sensor.id, name: sensor.name },
      type, value, unit: sensor.unit, measured_at: null, created_at: point.timestamp,
    }] : []
  }))
  const selected = rows.filter(row => !url.searchParams.get('type') || row.type === url.searchParams.get('type'))
    .sort((left, right) => right.created_at.localeCompare(left.created_at) || right.id - left.id)
  await route.fulfill({ json: page(selected) })
  return true
}
