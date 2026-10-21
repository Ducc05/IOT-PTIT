<script setup lang="ts">
import { computed } from 'vue'
import temperatureIcon from '../../assets/sensor-types/temperature.svg'
import humidityIcon from '../../assets/sensor-types/humidity.svg'
import lightIcon from '../../assets/sensor-types/light.svg'
import ledIcon from '../../assets/device-types/led.svg'
import userIcon from '../../assets/history-user.svg'
import type { CommandResource, SensorType } from '../../types/api'
import { useListing } from '../../composables/useListing'
import { dateTime, number } from '../../utils/format'
import AppIcon from '../common/AppIcon.vue'
import PageHeader from '../common/PageHeader.vue'
import AppPagination from '../common/AppPagination.vue'
import StatusBadge from '../common/StatusBadge.vue'
import ResourceNotice from '../common/ResourceNotice.vue'
import QueryFilters from './QueryFilters.vue'
import DataTable from './DataTable.vue'
const sensorTypeIcons: Record<SensorType, { src: string; width: number; height: number; label: string }> = {
  TEMPERATURE: { src: temperatureIcon, width: 15, height: 15, label: 'Temp' },
  HUMIDITY: { src: humidityIcon, width: 14, height: 17, label: 'Humidity' },
  LIGHT: { src: lightIcon, width: 19, height: 19, label: 'Light' },
}
const props = defineProps<{ kind: 'data' | 'history' }>()
const { data, applied, draft, formError, optionsError, devices, error, loading, updatedAt, apply, reset, refresh, changePage, changePageSize, setOrdering } = useListing(props.kind)
const lightDeviceIds = computed(() => new Set(devices.value.filter(device => device.type === 'LIGHT').map(device => device.id)))
function isLedDevice(device: CommandResource['device']) {
  return lightDeviceIds.value.has(device.id) || /^LED(?:[\s_-]|$)/i.test(device.name) || /^LED(?:[\s_-]|$)/i.test(device.device_code)
}
const columns = computed(() => props.kind === 'data' ? [
  { key: 'id', label: 'ID' }, { key: 'name', label: 'Name' }, { key: 'type', label: 'Type' }, { key: 'value', label: 'Value' }, { key: 'created_at', label: 'Date & Time' },
] : [{ key: 'id', label: 'ID' }, { key: 'device', label: 'Device' }, { key: 'user', label: 'User' }, { key: 'action', label: 'Action' }, { key: 'status', label: 'Status' }, { key: 'created_at', label: 'Date & Time' }])
const sortOptions = computed(() => {
  const timeField = 'created_at'
  return [
    { value: `-${timeField}`, label: 'Time (Newest)' },
    { value: timeField, label: 'Time (Oldest)' },
    ...(props.kind === 'data' ? [{ value: 'value', label: 'Value (Lowest)' }, { value: '-value', label: 'Value (Highest)' }] : []),
  ]
})
</script>
<template>
  <div class="page listing-page">
    <PageHeader :title="kind === 'data' ? 'Data' : 'History'" :subtitle="kind === 'data' ? '' : ''" :updated-at="updatedAt" :refreshing="loading" />
    <QueryFilters v-model="draft" :kind="kind" :devices="devices" :error="formError" :loading="loading" @apply="apply" @reset="reset" />
    <ResourceNotice :error="error || optionsError" :loading="false" :empty="!data" @retry="refresh" />
    <section class="table-card card"><div class="table-card-header"><div class="table-title"><h2>{{ kind === 'data' ? 'Sensor Data Table' : 'Device History Table' }}</h2></div>
      <div class="table-header-actions">
        <label class="listing-sort"><span>Sort By:</span><span class="listing-sort-select"><select aria-label="Sort by" :value="applied.ordering" @change="setOrdering(($event.target as HTMLSelectElement).value)"><option v-for="option in sortOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select><AppIcon name="down" :size="16" /></span></label>
      </div>
    </div>
      <DataTable :rows="data?.results || []" :columns="columns" :page-size="applied.page_size" :ordering="applied.ordering || ''" :loading="loading" :has-loaded="!!data">
        <template #cell="{ row, column }">
          <span v-if="column === 'id'" class="row-id">#{{ row.id }}</span>
          <span v-if="column === 'created_at'" class="date-cell">{{ dateTime(row.created_at) }}</span>
          <template v-else-if="'sensor' in row">
            <div v-if="column === 'name'" class="name-cell"><strong>{{ row.sensor.name }}</strong></div>
            <span v-if="column === 'type'" class="sensor-type" :class="row.type.toLowerCase()"><img :src="sensorTypeIcons[row.type].src" :width="sensorTypeIcons[row.type].width" :height="sensorTypeIcons[row.type].height" alt="" aria-hidden="true" />{{ sensorTypeIcons[row.type].label }}</span>
            <strong v-if="column === 'value'" class="reading-value">{{ number(row.value) }} <span>{{ row.unit }}</span></strong>
          </template>
          <template v-else>
            <div v-if="column === 'device'" class="device-cell"><img v-if="isLedDevice(row.device)" :src="ledIcon" width="12" height="15" alt="" aria-hidden="true" /><div class="name-cell"><strong>{{ row.device.name }}</strong></div></div>
            <span v-if="column === 'user'" class="user-cell"><img :src="userIcon" width="11" height="11" alt="" aria-hidden="true" />{{ row.user || '—' }}</span>
            <span v-if="column === 'action'" class="action-badge">{{ row.action }}</span>
            <StatusBadge v-if="column === 'status'" :status="row.status" :title="row.error_message || row.command_id" />
          </template>
        </template>
      </DataTable>
      <AppPagination :page="applied.page" :page-size="applied.page_size" :total="data?.count || 0" :disabled="loading" @change="changePage" @change-size="changePageSize" />
    </section>
  </div>
</template>
