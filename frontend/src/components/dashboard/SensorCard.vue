<script setup lang="ts">
import type { SensorLatest } from '../../types/api'
import { number, dateTime } from '../../utils/format'
import AppIcon from '../common/AppIcon.vue'
import StatusBadge from '../common/StatusBadge.vue'
defineProps<{ sensor: SensorLatest }>()
</script>
<template>
  <article class="sensor-card card" :class="sensor.type.toLowerCase()">
    <div class="sensor-heading"><span class="sensor-icon"><AppIcon :name="sensor.type.toLowerCase()" :size="23" /></span><span>{{ sensor.name }}</span><StatusBadge v-if="sensor.status === 'NO_DATA'" :status="sensor.status" /></div>
    <div class="sensor-value">{{ number(sensor.value) }}<span>{{ sensor.unit }}</span></div>
    <div class="sensor-caption" :title="dateTime(sensor.created_at)"><span v-if="sensor.status === 'OK'" class="live-dot" />{{ sensor.created_at ? `Updated ${new Date(sensor.created_at).toLocaleTimeString('en-GB')}` : 'Waiting for sensor data' }}</div>
  </article>
</template>
