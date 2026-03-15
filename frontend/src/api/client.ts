export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function getCsrfToken(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : null
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
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(url, {
    ...options,
    credentials: 'include',
    headers: buildHeaders(options),
  })

  if (res.status === 401) {
    const refreshed = await refreshToken()
    if (refreshed) {
      const retry = await fetch(url, {
        ...options,
        credentials: 'include',
        headers: buildHeaders(options),
      })
      if (retry.ok) return retry.json()
    }
    throw new ApiError(401, 'Not authenticated')
  }

  if (res.status === 403) {
    const body = await res.json().catch(() => ({ detail: 'Forbidden' }))
    if (body.detail === 'DEMO_EXPIRED') {
      throw new ApiError(403, 'DEMO_EXPIRED')
    }
    throw new ApiError(403, body.detail || 'Forbidden')
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new ApiError(res.status, body.detail || 'Request failed')
  }

  return res.json()
}
