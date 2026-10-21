<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { auth } from '../api/auth'
import { environment } from '../config/environment'
import { api } from '../api'
import { useLiveResource } from '../composables/useLiveResource'
import { useDeviceControls } from '../composables/useDeviceControls'
import PageHeader from '../components/common/PageHeader.vue'
import ResourceNotice from '../components/common/ResourceNotice.vue'
import SensorCard from '../components/dashboard/SensorCard.vue'
import DeviceCard from '../components/dashboard/DeviceCard.vue'
import SensorTrendsChart from '../components/dashboard/SensorTrendsChart.vue'
import type { SensorLatest, SensorType } from '../types/api'
const router = useRouter()
const { data: latestData, error: latestError, loading: latestLoading, refresh: refreshLatest } = useLiveResource(signal => api.sensorLatest(signal))
const { data: devices, error: devicesError, loading: devicesLoading, refresh: refreshDevices } = useLiveResource(signal => api.devices(signal), 0)
const { data: trendsData, error: trendsError, loading: trendsLoading, refresh: refreshTrends } = useLiveResource(
  signal => api.sensorTrends(signal), environment.source === 'api' ? environment.trendsRefreshMs : 0,
)
const { store, control, retry, errors } = useDeviceControls(devices, refreshDevices)
const sensors = computed<SensorLatest[]>(() => (['TEMPERATURE', 'HUMIDITY', 'LIGHT'] as SensorType[]).map((type, i) => latestData.value?.latest_sensors.find(s => s.type === type) || {
  sensor_id: null, sensor_code: null, name: ['Temperature', 'Humidity', 'Light'][i], type, value: null,
  unit: ['°C', '%', 'lux'][i], measured_at: null, created_at: null, status: 'NO_DATA',
}))
function controlDevice(device: import('../types/api').Device, action: import('../types/api').DeviceAction) {
  if (environment.source === 'api' && !auth.session.value) { void router.push('/login?redirect=/dashboard'); return }
  control(device, action)
}
</script>
<template>
  <div class="page dashboard-page">
    <PageHeader title="Dashboard" subtitle="" />
    <ResourceNotice :error="latestError" :loading="latestLoading" :empty="!latestData" @retry="refreshLatest" />
    <div v-if="latestData" class="sensor-grid"><SensorCard v-for="sensor in sensors" :key="sensor.type" :sensor="sensor" /></div>
    <ResourceNotice :error="trendsError" :loading="trendsLoading" :empty="!trendsData" @retry="refreshTrends" />
    <SensorTrendsChart v-if="trendsData" :points="trendsData.trends" />
    <ResourceNotice :error="devicesError" :loading="devicesLoading" :empty="!devices" @retry="refreshDevices" />
    <section v-if="devices" class="devices-section"><div class="section-heading"><h2>Device Controls</h2><span>{{ devices.length }} devices</span></div>
      <div v-if="devices.length" class="device-grid"><DeviceCard v-for="device in devices" :key="device.id" :device="device" :control="store.controls[device.id]" :error="errors[device.id]" @toggle="controlDevice(device, $event)" @retry="retry(device.id)" /></div>
      <div v-else class="card empty-state">No devices have been provisioned.</div>
    </section>
  </div>
</template>
