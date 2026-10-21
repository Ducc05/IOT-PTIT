<script setup lang="ts">
import type { Device } from '../../types/api'
import type { ControlState } from '../../stores/deviceControl'
import AppIcon from '../common/AppIcon.vue'
import StatusBadge from '../common/StatusBadge.vue'
defineProps<{ device: Device; control?: ControlState; error?: string }>()
defineEmits<{ toggle: [action: 'TURN_ON' | 'TURN_OFF']; retry: [] }>()
function connected(device: Device) { return device.availability === 'ONLINE' }
function hasState(device: Device) { return device.current_state !== null }
function icon(device: Device) { return device.type === 'LIGHT' ? 'bulb' : device.type === 'FAN' ? 'fan' : device.name.toLowerCase().includes('pump') ? 'pump' : 'buzzer' }
</script>
<template>
  <article class="device-card card" :class="{ 'device-on': device.current_state === 'ON' }">
    <div class="device-top"><span class="device-icon"><AppIcon :name="icon(device)" :size="24" /></span><StatusBadge v-if="connected(device)" :status="device.availability" /></div>
    <h3>{{ device.name }}</h3>
    <div class="device-state"><span>Status: <strong>{{ device.current_state ?? '—' }}</strong></span>
      <button class="toggle" role="switch" :aria-checked="hasState(device) ? device.current_state === 'ON' : 'mixed'" :aria-label="hasState(device) ? `Toggle ${device.name}` : `Turn on ${device.name}; state unavailable`" :disabled="!!control || !!device.pending_command" @click="$emit('toggle', device.current_state === 'ON' ? 'TURN_OFF' : 'TURN_ON')">
        <span class="toggle-thumb"><span v-if="control?.phase === 'pending'" class="toggle-spinner" aria-hidden="true" /></span>
      </button>
    </div>
    <div v-if="control?.phase === 'reconciling'" class="control-error" role="status">{{ control.message }} <button class="text-button" @click="$emit('retry')">Check again</button></div>
    <p v-else-if="error" class="control-error" role="alert">{{ error }}</p>
  </article>
</template>
