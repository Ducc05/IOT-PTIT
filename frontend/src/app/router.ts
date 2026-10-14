import { ref } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import { auth } from '../api/auth'
import { environment } from '../config/environment'
import LoginView from '../views/LoginView.vue'
export const routeError = ref('')
export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', name: 'dashboard', component: () => import('../views/DashboardView.vue') },
    { path: '/data', name: 'data', component: () => import('../views/SensorDataView.vue') },
    { path: '/history', name: 'history', component: () => import('../views/DeviceHistoryView.vue') },
    { path: '/login', name: 'login', component: LoginView, meta: { authScreen: true } },
    { path: '/register', name: 'register', component: LoginView, meta: { authScreen: true } },
    { path: '/profile', name: 'profile', component: () => import('../views/ProfileView.vue') },
    { path: '/:pathMatch(.*)*', component: () => import('../views/NotFoundView.vue') },
  ],
})
router.beforeEach(async to => {
  if (environment.source === 'mock') return to.meta.authScreen ? { name: 'dashboard' } : true
  if (to.meta.authScreen) return await auth.ensureAuthenticated() ? { name: 'dashboard' } : true
  return await auth.ensureAuthenticated() ? true : { name: 'login', query: { redirect: to.fullPath } }
})
router.afterEach((to, _from, failure) => {
  if (failure) return
  routeError.value = ''
  try { sessionStorage.removeItem(`iot-route-retry:${to.fullPath}`) } catch { /* Storage may be unavailable. */ }
})
router.onError((cause, to) => {
  const message = String(cause)
  if (/dynamically imported module|Importing a module script failed/i.test(message)) {
    const key = `iot-route-retry:${to.fullPath}`
    try {
      if (!sessionStorage.getItem(key)) {
        sessionStorage.setItem(key, '1')
        window.location.replace(to.fullPath)
        return
      }
    } catch { /* Show the retry action below. */ }
  }
  routeError.value = 'Could not load this screen. Check your connection and try again.'
})
