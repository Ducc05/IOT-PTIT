import { defineStore } from 'pinia'
import { ref } from 'vue'
import { environment } from '../config/environment'
import type { DeviceAction } from '../types/api'
export interface ControlState {
  action: DeviceAction; key: string; commandId: string | null
  phase: 'pending' | 'reconciling'; message: string
}
export const useDeviceControlStore = defineStore('device-control', () => {
  const storageKey = `iot-control-${environment.source}-${environment.baseUrl}`
  const controls = ref<Record<number, ControlState>>({})
  try { controls.value = JSON.parse(sessionStorage.getItem(storageKey) || '{}') } catch { /* Empty state. */ }
  function save() { try { sessionStorage.setItem(storageKey, JSON.stringify(controls.value)) } catch { /* Memory fallback. */ } }
  function set(id: number, state: ControlState) { controls.value[id] = state; save() }
  function clear(id: number) { delete controls.value[id]; save() }
  return { controls, set, clear }
})
