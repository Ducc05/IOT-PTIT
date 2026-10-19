<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auth } from '../api/auth'
import brandLogo from '../assets/iot-logo.svg'
import { ApiError } from '../types/api'
import { errorMessage } from '../utils/format'

const router = useRouter()
const route = useRoute()
const isRegister = computed(() => route.name === 'register')
const username = ref('')
const email = ref('')
const password = ref('')
const passwordConfirm = ref('')
const loading = ref(false)
const error = ref('')
const redirectQuery = computed(() => typeof route.query.redirect === 'string' ? { redirect: route.query.redirect } : {})
const destination = computed(() => {
  const target = route.query.redirect
  return typeof target === 'string' && /^\/(dashboard|data|history|profile)(?:[/?#]|$)/.test(target) ? target : '/dashboard'
})

watch(isRegister, () => { password.value = ''; passwordConfirm.value = ''; error.value = '' })

function formError(cause: unknown) {
  if (cause instanceof ApiError) {
    for (const value of Object.values(cause.details)) {
      if (typeof value === 'string') return value
      if (Array.isArray(value) && typeof value[0] === 'string') return value[0]
    }
  }
  return errorMessage(cause)
}

async function submit() {
  error.value = ''
  if (isRegister.value && password.value !== passwordConfirm.value) {
    error.value = 'Passwords do not match.'
    return
  }
  loading.value = true
  try {
    if (isRegister.value) await auth.register(username.value.trim(), email.value.trim(), password.value, passwordConfirm.value)
    else await auth.login(username.value.trim(), password.value)
    password.value = ''
    passwordConfirm.value = ''
    await router.replace(destination.value)
  } catch (cause) { error.value = formError(cause) }
  finally { loading.value = false }
}
</script>

<template>
  <div class="auth-screen">
    <main id="main-content" class="auth-main">
      <div class="auth-card">
        <div class="auth-header">
          <RouterLink class="auth-brand" to="/login">
            <span class="auth-brand-mark"><img :src="brandLogo" width="22" height="18" alt="" /></span>
            <span>IoT Monitoring</span>
          </RouterLink>
          <h1>{{ isRegister ? 'Create your account' : 'Welcome back' }}</h1>
          <p class="auth-intro">{{ isRegister ? 'Sign up to start monitoring your environment.' : 'Sign in to access your dashboard and devices.' }}</p>
        </div>

        <nav class="auth-tabs" aria-label="Account access">
          <RouterLink :to="{ name: 'login', query: redirectQuery }" :class="{ active: !isRegister }" :aria-current="!isRegister ? 'page' : undefined">Sign in</RouterLink>
          <RouterLink :to="{ name: 'register', query: redirectQuery }" :class="{ active: isRegister }" :aria-current="isRegister ? 'page' : undefined">Create account</RouterLink>
        </nav>

        <form class="auth-form" @submit.prevent="submit">
          <label class="auth-field"><span>Username</span><input v-model="username" name="username" autocomplete="username" placeholder="Your username" required maxlength="150" /></label>
          <label v-if="isRegister" class="auth-field"><span>Email <small>Optional</small></span><input v-model="email" name="email" type="email" autocomplete="email" placeholder="you@example.com" /></label>
          <label class="auth-field"><span>Password</span><input v-model="password" name="password" type="password" :autocomplete="isRegister ? 'new-password' : 'current-password'" placeholder="Enter your password" required /></label>
          <label v-if="isRegister" class="auth-field"><span>Confirm password</span><input v-model="passwordConfirm" name="password_confirm" type="password" autocomplete="new-password" placeholder="Enter your password again" required /></label>
          <p v-if="isRegister" class="auth-help">Use at least 8 characters. Avoid common passwords.</p>
          <p v-if="error" class="auth-error" role="alert">{{ error }}</p>
          <button class="auth-submit" type="submit" :disabled="loading">{{ loading ? (isRegister ? 'Creating account…' : 'Signing in…') : (isRegister ? 'Create account' : 'Sign in') }}</button>
        </form>
        <p class="auth-switch">{{ isRegister ? 'Already have an account?' : 'New to IoT Monitoring?' }} <RouterLink :to="{ name: isRegister ? 'login' : 'register', query: redirectQuery }">{{ isRegister ? 'Sign in' : 'Create an account' }}</RouterLink></p>
      </div>
    </main>
  </div>
</template>
