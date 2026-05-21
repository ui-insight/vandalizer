export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// Exported for unit testing — jsdom rejects __Host- prefix cookies (matching
// real browser behavior), so we can't drive this purely through document.cookie.
export function parseCsrfToken(cookieString: string): string | null {
  // Prefer the modern __Host- prefixed cookie. Browsers enforce its
  // uniqueness (Secure + Path=/ + no Domain), so it can't be shadowed by a
  // stale duplicate from a prior deploy or a sibling app on a shared parent
  // domain. Fall back to the legacy name for users mid-transition.
  const hostMatch = cookieString.match(/(?:^|;\s*)__Host-csrf_token=([^;]+)/)
  if (hostMatch) return decodeURIComponent(hostMatch[1])
  const legacyMatch = cookieString.match(/(?:^|;\s*)csrf_token=([^;]+)/)
  return legacyMatch ? decodeURIComponent(legacyMatch[1]) : null
}

export function getCsrfToken(): string | null {
  return parseCsrfToken(document.cookie)
}

/** Return a headers object with the CSRF token set (for raw fetch calls). */
export function csrfHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = { ...extra }
  const csrf = getCsrfToken()
  if (csrf) headers['X-CSRF-Token'] = csrf
  return headers
}

// Self-heal stale tabs whose CSRF cookie/header pairing is broken (old SPA
// bundle still in cache, browser extension stripping the cookie, etc.).
// A reload pulls a fresh index.html (which nginx serves with no-cache), the
// current hashed JS bundle, and gives the backend another chance to set the
// modern cookie. Guarded by a per-tab sessionStorage flag so a persistent
// failure surfaces as the original error instead of an infinite reload loop.
const CSRF_RELOAD_FLAG = 'vandalizer:csrf-reload-attempted'

function attemptCsrfSelfHeal(): boolean {
  if (typeof window === 'undefined') return false
  try {
    if (window.sessionStorage.getItem(CSRF_RELOAD_FLAG)) return false
    window.sessionStorage.setItem(CSRF_RELOAD_FLAG, '1')
  } catch {
    return false
  }
  window.location.reload()
  return true
}

async function refreshToken(): Promise<boolean> {
  const res = await fetch('/api/auth/refresh', {
    method: 'POST',
    credentials: 'include',
  })
  return res.ok
}

function buildHeaders(options: RequestInit): HeadersInit {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  const csrf = getCsrfToken()
  if (csrf) {
    headers['X-CSRF-Token'] = csrf
  }
  return headers
}

export async function apiFetch<T>(
  url: string,
  options: RequestInit & { timeoutMs?: number } = {},
): Promise<T> {
  const { timeoutMs = 60_000, ...fetchOptions } = options
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)

  let res: Response
  try {
    res = await fetch(url, {
      ...fetchOptions,
      credentials: 'include',
      headers: buildHeaders(fetchOptions),
      signal: controller.signal,
    })
  } catch (err) {
    clearTimeout(timer)
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ApiError(0, 'Request timed out')
    }
    throw err
  }
  clearTimeout(timer)

  if (res.status === 401) {
    const body401 = await res.json().catch(() => null)
    const detail = body401?.detail
    // Only attempt token refresh for authenticated endpoints (not login itself)
    if (!detail || detail === 'Not authenticated') {
      const refreshed = await refreshToken()
      if (refreshed) {
        const retry = await fetch(url, {
          ...options,
          credentials: 'include',
          headers: buildHeaders(options),
        })
        if (retry.ok) return retry.json()
      }
    }
    throw new ApiError(401, typeof detail === 'string' ? detail : 'Not authenticated')
  }

  if (res.status === 403) {
    const body = await res.json().catch(() => ({ detail: 'Forbidden' }))
    if (body.detail === 'DEMO_EXPIRED') {
      throw new ApiError(403, 'DEMO_EXPIRED')
    }
    if (body.detail === 'CSRF validation failed' && attemptCsrfSelfHeal()) {
      throw new ApiError(403, 'CSRF validation failed (reloading)')
    }
    throw new ApiError(403, body.detail || 'Forbidden')
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Request failed' }))
    let message = body.detail || 'Request failed'
    if (Array.isArray(message)) {
      message = message.map((e: { msg?: string }) => e.msg || String(e)).join('; ')
    } else if (typeof message !== 'string') {
      message = String(message)
    }
    throw new ApiError(res.status, message)
  }

  return res.json()
}
