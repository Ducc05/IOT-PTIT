import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { ApiError } from '../types/api'
import type { CommandResource, Device, ListQuery, PageResponse, SensorDataRow } from '../types/api'
import { useLiveResource } from './useLiveResource'
import { errorMessage } from '../utils/format'
import { validPageSize } from '../config/pagination'
import { sensorDataQuery, sensorSearchError, sensorSearchTypes } from '../utils/sensorSearch'
export interface FilterDraft { search: string; type: string; device: string; action: string; status: string }
export type TableRow = SensorDataRow | CommandResource
const empty = (): FilterDraft => ({ search: '', type: '', device: '', action: '', status: '' })
export function useListing(kind: 'data' | 'history') {
  const route = useRoute(); const router = useRouter()
  const formError = ref(''); const optionsError = ref(''); const devices = ref<Device[]>([])
  const draft = ref<FilterDraft>(empty())
  const positive = (value: string | undefined, fallback: number, max: number) => { const n = Number(value); return Number.isInteger(n) && n > 0 && n <= max ? n : fallback }
  const applied = computed<ListQuery>(() => {
    const q = Object.fromEntries(Object.entries(route.query).map(([key, value]) => [key, typeof value === 'string' ? value : undefined]))
    return {
      search: q.search?.trim().slice(0, 100) || undefined,
      type: kind === 'data' && sensorSearchTypes.includes(q.type || '') ? q.type : undefined,
      device: kind === 'history' && q.device ? positive(q.device, 0, Number.MAX_SAFE_INTEGER) || undefined : undefined,
      action: kind === 'history' && ['TURN_ON', 'TURN_OFF'].includes(q.action || '') ? q.action : undefined,
      status: kind === 'history' && ['PENDING', 'SUCCESS', 'FAILED', 'TIMEOUT'].includes(q.status || '') ? q.status : undefined,
      ordering: ['created_at', '-created_at', ...(kind === 'data' ? ['value', '-value'] : [])].includes(q.ordering || '') ? q.ordering : '-created_at',
      page: positive(q.page, 1, Number.MAX_SAFE_INTEGER), page_size: validPageSize(Number(q.page_size)) ? Number(q.page_size) : 10,
    }
  })
  const resource = useLiveResource<PageResponse<TableRow>>(async signal => {
    const query = kind === 'data' ? sensorDataQuery(applied.value) : { ...applied.value }
    if (kind === 'history') {
      try { devices.value = await api.devices(signal); optionsError.value = '' } catch (cause) { if (signal.aborted) throw cause; optionsError.value = errorMessage(cause) }
    }
    try {
      const response = await (kind === 'data' ? api.sensorData(query, signal) : api.history(query, signal))
      if (query.page > 1 && response.count > 0 && response.results.length === 0) {
        void update({ ...query, page: 1 }); signal.throwIfAborted()
      }
      return response
    }
    catch (cause) {
      if (cause instanceof ApiError && cause.code === 'PAGE_NOT_FOUND' && query.page > 1) {
        void update({ ...query, page: 1 }); signal.throwIfAborted()
      }
      throw cause
    }
  }, 0)
  function update(query: ListQuery) {
    const clean = Object.fromEntries(Object.entries(query).filter(([, v]) => v !== '' && v !== undefined).map(([k, v]) => [k, String(v)]))
    return router.replace({ query: clean })
  }
  watch(() => route.query, () => {
    const query = applied.value
    draft.value = { search: query.search || '', type: query.type || '', device: query.device ? String(query.device) : '', action: query.action || '', status: query.status || '' }
    formError.value = ''
  }, { immediate: true })
  watch(applied, () => { void resource.refresh() })
  async function apply() {
    const { search, type, device, action, status } = draft.value
    formError.value = kind === 'data' ? sensorSearchError(type, search) : ''
    if (formError.value) return
    await update({ search: search.trim() || undefined, ...(kind === 'data' ? { type: type || undefined } : { device: device ? Number(device) : undefined, action: action || undefined, status: status || undefined }),
      page: 1, page_size: applied.value.page_size, ordering: applied.value.ordering })
    void resource.refresh()
  }
  async function reset() {
    draft.value = empty(); formError.value = ''
    await update({ page: 1, page_size: applied.value.page_size, ordering: '-created_at' }); void resource.refresh()
  }
  const changePage = (page: number) => update({ ...applied.value, page })
  const changePageSize = (pageSize: number) => {
    if (validPageSize(pageSize)) return update({ ...applied.value, page: 1, page_size: pageSize })
  }
  const setOrdering = (ordering: string) => update({ ...applied.value, page: 1, ordering })
  return { ...resource, applied, draft, formError, optionsError, devices, apply, reset, changePage, changePageSize, setOrdering }
}
