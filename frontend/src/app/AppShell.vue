<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { routeError } from './router'
import AppIcon from '../components/common/AppIcon.vue'
import brandLogo from '../assets/iot-logo.svg'
const route = useRoute()
const open = ref(false)
function reload() { window.location.reload() }
const items = [{ path: '/dashboard', label: 'Dashboard', icon: 'dashboard' }, { path: '/data', label: 'Data', icon: 'data' }, { path: '/history', label: 'History', icon: 'history' }, { path: '/profile', label: 'Profile', icon: 'profile' }]
</script>
<template>
  <a class="skip-link" href="#main-content">Skip to content</a>
  <div class="app-shell">
    <button class="mobile-menu icon-button" aria-label="Open navigation" @click="open = true"><AppIcon name="menu" /></button>
    <button v-if="open" class="nav-backdrop" aria-label="Close navigation" @click="open = false" />
    <aside class="sidebar" :class="{ open }">
      <RouterLink to="/dashboard" class="brand" @click="open = false"><span class="brand-mark"><img :src="brandLogo" width="20" height="15" alt="" aria-hidden="true" /></span><span>IoT Monitoring</span></RouterLink>
      <button class="mobile-close icon-button" aria-label="Close navigation" @click="open = false"><AppIcon name="close" /></button>
      <nav aria-label="Main navigation">
        <RouterLink v-for="item in items" :key="item.path" :to="item.path" class="nav-item" :class="{ active: route.path === item.path }" @click="open = false">
          <AppIcon :name="item.icon" /><span>{{ item.label }}</span><span v-if="route.path === item.path" class="nav-active-dot" />
        </RouterLink>
      </nav>
    </aside>
    <main id="main-content" class="main-content" tabindex="-1">
      <div v-if="routeError" class="error-banner" role="alert">{{ routeError }} <button class="text-button" @click="reload">Try again</button></div>
      <RouterView v-else />
    </main>
  </div>
</template>
