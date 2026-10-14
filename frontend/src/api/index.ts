import { environment } from '../config/environment'
import { createHttpApi } from './http'
import type { IoTApi } from '../types/api'
// Every view uses this interface. Switching source never changes the components.
export const api: IoTApi = environment.source === 'api'
  ? createHttpApi(environment.baseUrl)
  : (await import('./mock')).createMockApi()
