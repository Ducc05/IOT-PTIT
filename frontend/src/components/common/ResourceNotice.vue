<script setup lang="ts">
defineProps<{ error: string; loading: boolean; empty: boolean }>()
defineEmits<{ retry: [] }>()
</script>
<template>
  <div v-if="error" class="error-banner" role="alert">{{ error }}<button class="text-button" @click="$emit('retry')">Try again</button></div>
  <div v-else-if="loading && empty" class="empty-state" role="status"><span class="spinner" /> Loading data…</div>
</template>
