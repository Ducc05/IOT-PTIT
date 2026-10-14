import { onMounted, onUnmounted, ref, shallowRef } from 'vue'
import { environment } from '../config/environment'
import { errorMessage } from '../utils/format'

export function useLiveResource<T>(load: (signal: AbortSignal) => Promise<T>, interval = environment.source === 'api' ? environment.refreshMs : 0) {
  const data = shallowRef<T | null>(null)
  const loading = ref(false)
  const error = ref('')
  const updatedAt = ref<string | null>(null)
  let controller: AbortController | undefined
  let timer: ReturnType<typeof setTimeout> | undefined
  let generation = 0
  let disposed = false
  async function refresh() {
    clearTimeout(timer); controller?.abort()
    const current = ++generation
    controller = new AbortController()
    loading.value = true
    try {
      const result = await load(controller.signal)
      if (current !== generation || disposed) return
      data.value = result; error.value = ''; updatedAt.value = new Date().toISOString()
    } catch (cause) {
      if (current === generation && !disposed && !controller.signal.aborted) error.value = errorMessage(cause)
    } finally {
      if (current === generation && !disposed) {
        loading.value = false
        if (interval > 0 && !document.hidden) timer = setTimeout(refresh, interval)
      }
    }
  }
  function visibility() {
    if (interval <= 0) return
    if (document.hidden) { clearTimeout(timer); controller?.abort(); generation++; loading.value = false }
    else void refresh()
  }
  onMounted(() => { void refresh(); document.addEventListener('visibilitychange', visibility) })
  onUnmounted(() => { disposed = true; generation++; clearTimeout(timer); controller?.abort(); document.removeEventListener('visibilitychange', visibility) })
  return { data, loading, error, updatedAt, refresh }
}
