<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from './AppIcon.vue'
import { pageSizeOptions } from '../../config/pagination'
const props = defineProps<{ page: number; pageSize: number; total: number; disabled?: boolean }>()
defineEmits<{ change: [page: number]; 'change-size': [pageSize: number] }>()
const pages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))
const visible = computed(() => {
  if (pages.value <= 5) return Array.from({ length: pages.value }, (_, index) => index + 1)
  const first = props.page <= 3 ? 1 : props.page >= pages.value - 2 ? pages.value - 2 : props.page - 1
  const numbers = [...new Set([1, first, first + 1, first + 2, pages.value])].sort((a, b) => a - b)
  const items: (number | string)[] = []
  numbers.forEach((page, index) => {
    const previous = numbers[index - 1]
    if (previous !== undefined && page - previous === 2) items.push(previous + 1)
    else if (previous !== undefined && page - previous > 2) items.push(`gap-${previous}-${page}`)
    items.push(page)
  })
  return items
})
</script>
<template>
  <footer class="pagination">
    <div class="pagination-summary">
      <label class="rows-per-page"><span>Rows per page:</span><span class="rows-per-page-select"><select aria-label="Rows per page" :value="pageSize" :disabled="disabled" @change="$emit('change-size', Number(($event.target as HTMLSelectElement).value))"><option v-for="size in pageSizeOptions" :key="size" :value="size">{{ size }}</option></select><AppIcon name="down" :size="16" /></span></label>
      <span class="pagination-total">of {{ total.toLocaleString('en-US') }} items</span>
    </div>
    <nav class="pagination-controls" aria-label="Pagination">
      <button class="page-button page-arrow" aria-label="Previous page" :disabled="page === 1 || disabled" @click="$emit('change', page - 1)"><AppIcon name="left" :size="20" /></button>
      <template v-for="item in visible" :key="item">
        <span v-if="typeof item === 'string'" class="pagination-ellipsis" aria-hidden="true">…</span>
        <button v-else class="page-button" :class="{ selected: item === page }" :aria-label="`Page ${item}`" :aria-current="item === page ? 'page' : undefined" :disabled="disabled" @click="$emit('change', item)">{{ item }}</button>
      </template>
      <button class="page-button page-arrow" aria-label="Next page" :disabled="page >= pages || disabled" @click="$emit('change', page + 1)"><AppIcon name="right" :size="20" /></button>
    </nav>
  </footer>
</template>
