<script setup lang="ts">
defineProps<{ title: string; subtitle: string; updatedAt?: string | null; refreshing?: boolean; live?: boolean }>()
</script>
<template>
  <header class="page-header"><div><h1>{{ title }}</h1><p>{{ subtitle }}</p></div>
  </header>
</template>
