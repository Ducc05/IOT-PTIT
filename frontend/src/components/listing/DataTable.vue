<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import type { TableRow } from '../../composables/useListing'
const props = defineProps<{ rows: TableRow[]; columns: { key: string; label: string }[]; pageSize: number; ordering: string; loading: boolean; hasLoaded: boolean }>()
const viewport = ref<HTMLElement>()
const rowHeight = ref(32)
let observer: ResizeObserver | undefined
onMounted(() => {
  observer = new ResizeObserver(([entry]) => {
    const headerHeight = viewport.value?.querySelector('thead')?.getBoundingClientRect().height || 36
    // Keep the ten-row layout's size when the user requests more records.
    rowHeight.value = Math.max(24, (entry.contentRect.height - headerHeight) / 10)
  })
  if (viewport.value) observer.observe(viewport.value)
})
onUnmounted(() => observer?.disconnect())
watch([() => props.rows[0]?.id, () => props.pageSize], () => { if (viewport.value) viewport.value.scrollTop = 0 })
</script>
<template>
  <div ref="viewport" class="table-viewport" :aria-busy="loading">
    <table class="listing-table" :style="{ '--listing-row-height': `${rowHeight}px` }">
      <thead><tr><th v-for="column in columns" :key="column.key" scope="col" :aria-sort="ordering.replace('-', '') === column.key ? ordering.startsWith('-') ? 'descending' : 'ascending' : undefined">
        {{ column.label }}
      </th></tr></thead>
      <tbody>
        <tr v-for="row in rows" :key="row.id"><td v-for="column in columns" :key="column.key"><slot name="cell" :row="row" :column="column.key" /></td></tr>
        <tr v-if="!rows.length"><td :colspan="columns.length" class="table-empty"><span v-if="loading && !hasLoaded" class="spinner" />{{ loading && !hasLoaded ? 'Loading records…' : 'No records match your filters.' }}</td></tr>
      </tbody>
    </table>
  </div>
</template>
