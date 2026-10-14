import { shallowRef } from 'vue'
import { environment } from '../config/environment'
import { ApiError } from '../types/api'

interface Session { username: string; email: string; full_name: string; student_id: string | null; access: string; refresh: string }
interface CurrentUser { id: number; username: string; email: string; full_name: string; student_id: string | null }
interface TokenPair { access: string; refresh?: string; username?: string; email?: string }
interface ProfileUpdate { full_name: string; student_id: string | null; email?: string }

const storageKey = `iot-auth-${environment.baseUrl}`
const authBase = environment.baseUrl.replace(/\/api\/v1\/?$/, '')
let verifiedAccess: string | null = null
let refreshing: Promise<string | null> | null = null

function storedSession(): Session | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(storageKey) || 'null')
    return value && typeof value.username === 'string' && typeof value.access === 'string' && typeof value.refresh === 'string'
      ? { username: value.username, email: typeof value.email === 'string' ? value.email : '', full_name: typeof value.full_name === 'string' ? value.full_name : '', student_id: typeof value.student_id === 'string' ? value.student_id : null, access: value.access, refresh: value.refresh }
      : null
  } catch { return null }
}

const session = shallowRef<Session | null>(storedSession())

function save(value: Session | null) {
  verifiedAccess = null
  session.value = value
  try { if (value) sessionStorage.setItem(storageKey, JSON.stringify(value)); else sessionStorage.removeItem(storageKey) } catch { /* In-memory session. */ }
}

function requestError(response: Response, data: Record<string, any>, fallback: string) {
  return new ApiError(data.error?.code || 'AUTHENTICATION_REQUIRED', data.error?.message || data.detail || fallback, response.status, data.error?.details || {})
}

async function postJson(path: string, body: object, signal?: AbortSignal): Promise<TokenPair> {
  let response: Response
  try {
    response = await fetch(`${authBase}${path}`, { method: 'POST', cache: 'no-store', signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(12000)]) : AbortSignal.timeout(12000),
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  } catch (cause) {
    if (signal?.aborted) throw cause
    throw new ApiError('NETWORK_ERROR', 'Cannot reach the backend.')
  }
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw requestError(response, data, 'Authentication failed.')
  return data as TokenPair
}

async function currentUser(access: string, signal?: AbortSignal): Promise<CurrentUser> {
  let response: Response
  try {
    response = await fetch(`${authBase}/api/auth/me/`, { cache: 'no-store', signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(12000)]) : AbortSignal.timeout(12000),
      headers: { Accept: 'application/json', Authorization: `Bearer ${access}` } })
  } catch (cause) {
    if (signal?.aborted) throw cause
    throw new ApiError('NETWORK_ERROR', 'Cannot reach the backend.')
  }
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw requestError(response, data, 'Session verification failed.')
  return data as CurrentUser
}

export const auth = {
  session,
  accessToken: () => session.value?.access || null,
  async login(username: string, password: string, signal?: AbortSignal) {
    const data = await postJson('/api/auth/token/', { username, password }, signal)
    if (!data.access || !data.refresh) throw new ApiError('AUTHENTICATION_REQUIRED', 'Invalid token response.')
    const user = await currentUser(data.access, signal)
    save({ username: user.username, email: user.email, full_name: user.full_name || '', student_id: user.student_id || null, access: data.access, refresh: data.refresh })
    verifiedAccess = data.access
  },
  async register(username: string, email: string, password: string, passwordConfirm: string, signal?: AbortSignal) {
    const data = await postJson('/api/auth/register/', { username, email, password, password_confirm: passwordConfirm }, signal)
    if (!data.access || !data.refresh || !data.username) throw new ApiError('AUTHENTICATION_REQUIRED', 'Invalid registration response.')
    save({ username: data.username, email: data.email || '', full_name: '', student_id: null, access: data.access, refresh: data.refresh })
    verifiedAccess = data.access
  },
  async refresh(): Promise<string | null> {
    const before = session.value
    if (!before) return null
    if (refreshing) return refreshing
    refreshing = (async () => {
      try {
        const data = await postJson('/api/auth/token/refresh/', { refresh: before.refresh })
        if (!data.access || !session.value || session.value.refresh !== before.refresh) return null
        save({ ...session.value, access: data.access, refresh: data.refresh || session.value.refresh })
        return data.access
      } catch { if (session.value?.refresh === before.refresh) save(null); return null }
    })()
    try { return await refreshing } finally { refreshing = null }
  },
  async ensureAuthenticated(): Promise<boolean> {
    if (!session.value) return false
    if (verifiedAccess === session.value.access) return true
    try {
      let access = session.value.access
      let user: CurrentUser
      try { user = await currentUser(access) }
      catch (cause) {
        if (!(cause instanceof ApiError) || cause.status !== 401) throw cause
        const refreshed = await auth.refresh()
        if (!refreshed) return false
        access = refreshed
        user = await currentUser(access)
      }
      if (!session.value) return false
      save({ ...session.value, username: user.username, email: user.email, full_name: user.full_name || '', student_id: user.student_id || null })
      verifiedAccess = access
      return true
    } catch { save(null); return false }
  },
  async updateProfile(values: ProfileUpdate): Promise<CurrentUser> {
    if (!session.value) throw new ApiError('AUTHENTICATION_REQUIRED', 'Sign in to continue.', 401)
    async function send(access: string) {
      try {
        return await fetch(`${authBase}/api/auth/me/`, {
          method: 'PATCH', cache: 'no-store', signal: AbortSignal.timeout(12000),
          headers: { Accept: 'application/json', 'Content-Type': 'application/json', Authorization: `Bearer ${access}` },
          body: JSON.stringify(values),
        })
      } catch { throw new ApiError('NETWORK_ERROR', 'Cannot reach the backend.') }
    }
    let access = session.value.access
    let response = await send(access)
    if (response.status === 401) {
      const refreshed = await auth.refresh()
      if (!refreshed) throw new ApiError('AUTHENTICATION_REQUIRED', 'Session expired. Sign in again.', 401)
      access = refreshed
      response = await send(access)
    }
    const data = await response.json().catch(() => { throw new ApiError('NETWORK_ERROR', 'The server returned an invalid response.') })
    if (response.status === 401) auth.logout()
    if (!response.ok) throw requestError(response, data, 'Unable to update your profile.')
    if (!session.value) throw new ApiError('AUTHENTICATION_REQUIRED', 'Sign in to continue.', 401)
    const user = data as CurrentUser
    save({ ...session.value, username: user.username, email: user.email, full_name: user.full_name || '', student_id: user.student_id || null })
    verifiedAccess = access
    return user
  },
  logout() { save(null) },
}
