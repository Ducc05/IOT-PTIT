<script setup lang="ts">
import { environment } from '../../config/environment'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import type { SensorTrendPoint } from '../../types/api'
import { timeOnly, dateTime, number } from '../../utils/format'
const props = defineProps<{ points: SensorTrendPoint[] }>()
const series = [
  { key: 'temperature' as const, name: 'Temperature', color: '#ef4444', unit: '°C', min: 0, max: 50 },
  { key: 'humidity' as const, name: 'Humidity', color: '#3b82f6', unit: '%', min: 0, max: 100 },
  { key: 'light' as const, name: 'Light', color: '#f59e0b', unit: 'lux', min: 0, max: 2000 },
]
const active = ref<number | null>(null)
const hidden = ref<string[]>([])
const container = ref<HTMLElement>()
const dimensions = ref({ width: 850, height: 275 })
const plot = computed(() => ({ x: 42, y: 24, w: Math.max(40, dimensions.value.width - 120), h: Math.max(30, dimensions.value.height - 58) }))
let observer: ResizeObserver | undefined
onMounted(() => {
  observer = new ResizeObserver(([entry]) => { dimensions.value = { width: Math.max(160, entry.contentRect.width), height: Math.max(90, entry.contentRect.height) } })
  if (container.value) observer.observe(container.value)
})
onUnmounted(() => observer?.disconnect())
const start = computed(() => Date.parse(props.points[0]?.timestamp || '') || 0)
const end = computed(() => Date.parse(props.points.at(-1)?.timestamp || '') || 0)
const shortWindow = computed(() => end.value - start.value < 5 * 60 * 1000)
const x = (point: SensorTrendPoint) => plot.value.x + (Date.parse(point.timestamp) - start.value) / Math.max(1, end.value - start.value) * plot.value.w
function scale(s: typeof series[number]) {
  const values = props.points.map(point => point[s.key]).filter((value): value is number => value !== null && Number.isFinite(value))
  const step = s.max / 4
  return { min: Math.floor(Math.min(s.min, ...values) / step) * step, max: Math.ceil(Math.max(s.max, ...values) / step) * step }
}
function tickValue(s: typeof series[number], tick: number) { const axis = scale(s); return number(axis.max - tick * (axis.max - axis.min) / 4) }
function path(s: typeof series[number]) {
  let connected = false
  const axis = scale(s)
  return props.points.map(p => {
    const value = p[s.key]
    if (value === null) { connected = false; return '' }
    const y = plot.value.y + plot.value.h - (value - axis.min) / (axis.max - axis.min) * plot.value.h
    const segment = `${connected ? 'L' : 'M'}${x(p).toFixed(2)},${y.toFixed(2)}`
    connected = true; return segment
  }).join(' ')
}
const ticks = computed(() => {
  if (!props.points.length) return []
  const duration = Math.max(0, end.value - start.value)
  const count = Math.min(7, Math.max(2, Math.floor(plot.value.w / 80) + 1), Math.floor(duration / (shortWindow.value ? 1000 : 60000)) + 1)
  if (count === 1) return [{ timestamp: new Date(end.value).toISOString(), x: duration ? plot.value.x + plot.value.w : plot.value.x }]
  return Array.from({ length: count }, (_, index) => {
    const fraction = index / (count - 1)
    return { timestamp: new Date(start.value + duration * fraction).toISOString(), x: plot.value.x + plot.value.w * fraction }
  })
})
const selected = computed(() => active.value === null ? null : props.points[active.value] || null)
const latest = computed(() => props.points.at(-1))
function hover(event: MouseEvent) {
  const bounds = (event.currentTarget as SVGSVGElement).getBoundingClientRect()
  const localX = (event.clientX - bounds.left) / bounds.width * dimensions.value.width
  const timestamp = start.value + Math.max(0, Math.min(1, (localX - plot.value.x) / plot.value.w)) * (end.value - start.value)
  let best = 0
  props.points.forEach((p, i) => { if (Math.abs(Date.parse(p.timestamp) - timestamp) < Math.abs(Date.parse(props.points[best].timestamp) - timestamp)) best = i })
  active.value = best
}
function toggle(key: string) { hidden.value = hidden.value.includes(key) ? hidden.value.filter(k => k !== key) : [...hidden.value, key] }
</script>
<template>
  <section class="chart-card card">
    <div class="section-card-header"><h2>Sensor Trends <span class="heading-light">(Real-time)</span></h2></div>
    <div class="chart-legend"><button v-for="s in series" :key="s.key" :class="{ muted: hidden.includes(s.key) }" :aria-pressed="!hidden.includes(s.key)" @click="toggle(s.key)"><span :style="{ background: s.color }" />{{ s.name }}</button></div>
    <div v-if="!points.length" class="empty-state">No sensor readings in this period.</div>
    <div ref="container" class="chart-plot">
      <svg v-if="points.length" :viewBox="`0 0 ${dimensions.width} ${dimensions.height}`" preserveAspectRatio="none" role="img" :aria-label="`Sensor trends: temperature in degrees Celsius, humidity in percent, and light in ${series[2].unit}`" @mousemove="hover" @mouseleave="active = null">
        <g v-for="tick in [0, 1, 2, 3, 4]" :key="tick">
          <line :x1="plot.x" :x2="plot.x + plot.w" :y1="plot.y + tick * plot.h / 4" :y2="plot.y + tick * plot.h / 4" stroke="#e7eaf0" stroke-dasharray="4 4" />
          <text x="32" :y="plot.y + tick * plot.h / 4 + 4" text-anchor="end">{{ tickValue(series[0], tick) }}</text>
          <text :x="dimensions.width - 45" :y="plot.y + tick * plot.h / 4 + 4" text-anchor="end">{{ tickValue(series[1], tick) }}</text>
          <text :x="dimensions.width - 2" :y="plot.y + tick * plot.h / 4 + 4" text-anchor="end">{{ tickValue(series[2], tick) }}</text>
        </g>
        <text x="16" y="12">°C</text><text :x="dimensions.width - 58" y="12">%</text><text :x="dimensions.width - 25" y="12">{{ series[2].unit }}</text>
        <path v-for="s in series.filter(s => !hidden.includes(s.key))" :key="s.key" :d="path(s)" fill="none" :stroke="s.color" stroke-width="2.3" vector-effect="non-scaling-stroke" stroke-linejoin="round" />
        <text v-for="tick in ticks" :key="tick.timestamp" :x="tick.x" :y="dimensions.height - 6" text-anchor="middle">{{ timeOnly(tick.timestamp, shortWindow) }}</text>
        <line v-if="selected" :x1="x(selected)" :x2="x(selected)" :y1="plot.y" :y2="plot.y + plot.h" stroke="#94a3b8" stroke-dasharray="4 4" />
      </svg>
      <div v-if="selected" class="chart-tooltip"><strong>{{ dateTime(selected.timestamp) }}</strong><div v-for="s in series" :key="s.key"><span :style="{ color: s.color }">{{ s.name }}</span> {{ number(selected[s.key]) }} {{ s.unit }}</div></div>
    </div>
    <p class="sr-only">Latest readings: temperature {{ number(latest?.temperature ?? null) }} °C, humidity {{ number(latest?.humidity ?? null) }} %, light {{ number(latest?.light ?? null) }} {{ series[2].unit }}. Missing values are gaps in the chart.</p>
  </section>
</template>
