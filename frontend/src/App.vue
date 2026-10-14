<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auth } from './api/auth'
import AppShell from './app/AppShell.vue'
import { environment } from './config/environment'
const route = useRoute()
const router = useRouter()
const authScreen = computed(() => Boolean(route.meta.authScreen))
watch(auth.session, value => {
  if (environment.source === 'api' && !value && !authScreen.value) {
    void router.replace({ name: 'login', query: { redirect: route.fullPath } })
  }
})
</script>
<template><RouterView v-if="authScreen" /><AppShell v-else /></template>
