<script setup lang="ts">
defineProps<{ status: string }>()
const labels: Record<string, string> = { SUCCESS: 'Success', FAILED: 'Failed', TIMEOUT: 'Timeout', PENDING: 'Pending', ONLINE: 'Online', OFFLINE: 'Offline', UNKNOWN: 'Unknown', STALE: 'Stale', OK: 'Live', NO_DATA: 'No data' }
</script>
<template><span class="status-badge" :class="status.toLowerCase()"><span class="status-dot" />{{ labels[status] || status }}</span></template>
