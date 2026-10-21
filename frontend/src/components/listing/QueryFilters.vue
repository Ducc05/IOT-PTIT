<script setup lang="ts">
import type { Device } from '../../types/api'
import type { FilterDraft } from '../../composables/useListing'
import AppIcon from '../common/AppIcon.vue'
import { environment } from '../../config/environment'
defineProps<{ kind: 'data' | 'history'; devices: Device[]; error: string; loading: boolean }>()
const model = defineModel<FilterDraft>({ required: true })
defineEmits<{ apply: []; reset: [] }>()
function changeType(event: Event) {
  const type = (event.target as HTMLSelectElement).value
  if ((model.value.type === 'TIME') !== (type === 'TIME')) model.value.search = ''
  model.value.type = type
}
</script>
<template>
  <form class="filter-card card" :class="{ 'history-filters': kind === 'history', 'data-filters': kind === 'data' }" @submit.prevent="$emit('apply')">
    <div class="filter-fields">
      <label class="field search-field"><span>Search</span><div class="input-icon"><AppIcon name="search" :size="17" /><input v-model="model.search" maxlength="100" type="text" :inputmode="kind === 'data' && model.type !== 'TIME' ? 'decimal' : undefined" :aria-invalid="kind === 'data' && !!error" :aria-label="kind === 'data' ? model.type === 'TIME' ? 'Sensor time' : 'Sensor value' : environment.source === 'api' ? 'History ID' : 'History ID or command UUID'" :placeholder="kind === 'data' ? model.type === 'TIME' ? 'Paste Date & Time (e.g. 21 Oct 2026, 12:34:56)' : 'Enter value to search (e.g. 28.5)' : environment.source === 'api' ? 'Enter history ID' : 'Enter ID or name to search'" /></div></label>
      <label v-if="kind === 'data'" class="field"><span>Type</span><select :value="model.type" aria-label="Sensor type" @change="changeType"><option value="">All Types</option><option value="TEMPERATURE">Temperature</option><option value="HUMIDITY">Humidity</option><option value="LIGHT">Light</option><option value="TIME">Time</option></select></label>
      <template v-else>
        <label class="field"><span>Device</span><select v-model="model.device" aria-label="Device"><option value="">All Devices</option><option v-for="device in devices" :key="device.id" :value="String(device.id)">{{ device.name }}</option></select></label>
        <label class="field"><span>Action</span><select v-model="model.action" aria-label="Action"><option value="">All Actions</option><option value="TURN_ON">Turn on</option><option value="TURN_OFF">Turn off</option></select></label>
        <label class="field"><span>Status</span><select v-model="model.status" aria-label="Status"><option value="">All Status</option><option value="SUCCESS">Success</option><option value="PENDING">Pending</option><option value="FAILED">Failed</option><option v-if="environment.source === 'mock'" value="TIMEOUT">Timeout</option></select></label>
      </template>
      <div class="filter-actions"><button class="button primary" type="submit" :disabled="loading"><AppIcon name="filter" :size="17" />Filter</button><button class="button secondary" type="button" aria-label="Reset filters" @click="$emit('reset')"><AppIcon name="reset" :size="17" /><span>Reset</span></button></div>
    </div>
    <p v-if="error" class="field-error" role="alert">{{ error }}</p>
  </form>
</template>
