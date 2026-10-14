import { onUnmounted, ref, watch } from 'vue'
import type { ShallowRef } from 'vue'
import { api } from '../api'
import { environment } from '../config/environment'
import { useDeviceControlStore } from '../stores/deviceControl'
import { ApiError } from '../types/api'
import type { Device, DeviceAction } from '../types/api'
import { errorMessage } from '../utils/format'

export function useDeviceControls(devices: ShallowRef<Device[] | null>, refresh: () => Promise<void>) {
  const store = useDeviceControlStore()
  const errors = ref<Record<number, string>>({})
  const sessions = new Map<number, AbortController>()
  let disposed = false
  function pause(ms: number, signal: AbortSignal) {
    return new Promise<void>((resolve, reject) => {
      const abort = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }
      const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve() }, ms)
      signal.addEventListener('abort', abort, { once: true })
      if (signal.aborted) abort()
    })
  }
  async function track(id: number) {
    if (disposed || sessions.has(id) || !store.controls[id]) return
    const controller = new AbortController(); sessions.set(id, controller)
    const signal = controller.signal
    const started = Date.now()
    let terminal = false
    try {
      const intent = store.controls[id]
      if (!intent.commandId) {
        const result = await api.control(id, { action: intent.action, idempotency_key: intent.key }, signal)
        store.set(id, { ...intent, commandId: result.command_id })
      }
      while (!signal.aborted) {
        const result = await api.command(store.controls[id].commandId!, signal)
        if (result.status !== 'PENDING') {
          if (result.status !== 'SUCCESS') errors.value[id] = result.error_message || `Command ${result.status.toLowerCase()}.`
          store.clear(id); terminal = true
          break
        }
        if (Date.now() - started >= environment.commandTimeoutMs) {
          store.set(id, { ...store.controls[id], phase: 'reconciling', message: 'Result not confirmed yet. Check again.' })
          break
        }
        await pause(environment.commandPollMs, signal)
      }
    } catch (cause) {
      if (!signal.aborted) {
        if (cause instanceof ApiError && cause.status >= 400 && cause.status < 500 && cause.code !== 'DEVICE_COMMAND_IN_PROGRESS') {
          errors.value[id] = cause.message; store.clear(id)
        } else if (cause instanceof ApiError && cause.code === 'DEVICE_COMMAND_IN_PROGRESS' && typeof cause.details.command_id === 'string') {
          store.set(id, { ...store.controls[id], commandId: cause.details.command_id, phase: 'reconciling', message: 'Another command is processing. Check its result.' })
        } else if (store.controls[id]) {
          store.set(id, { ...store.controls[id], phase: 'reconciling', message: errorMessage(cause) })
        }
      }
    } finally {
      sessions.delete(id)
      if (terminal && !disposed) await refresh()
    }
  }
  function control(device: Device, action: DeviceAction) {
    if (store.controls[device.id] || device.pending_command) return
    delete errors.value[device.id]
    store.set(device.id, { action, key: `ui-${crypto.randomUUID()}`, commandId: null, phase: 'pending', message: '' })
    void track(device.id)
  }
  function retry(id: number) {
    const state = store.controls[id]
    if (!state) return
    store.set(id, { ...state, phase: 'pending', message: '' }); void track(id)
  }
  watch(devices, snapshot => {
    if (!snapshot) return
    for (const device of snapshot) {
      if (device.pending_command && !store.controls[device.id]) {
        store.set(device.id, { action: device.pending_command.requested_state === 'ON' ? 'TURN_ON' : 'TURN_OFF', key: `resume-${device.pending_command.command_id}`,
          commandId: device.pending_command.command_id, phase: 'pending', message: '' })
      }
    }
    Object.entries(store.controls).forEach(([id, state]) => { if (state.phase === 'pending') void track(Number(id)) })
  })
  onUnmounted(() => { disposed = true; sessions.forEach(controller => controller.abort()); sessions.clear() })
  return { store, control, retry, errors }
}
