import * as Sentry from '@sentry/react'

export function initSentry() {
  const dsn = import.meta.env.VITE_SENTRY_DSN
  if (!dsn) return

  const environment = import.meta.env.VITE_SENTRY_ENVIRONMENT ?? import.meta.env.MODE
  const release = import.meta.env.VITE_SENTRY_RELEASE

  Sentry.init({
    dsn,
    environment,
    release,
    integrations: [
      Sentry.browserTracingIntegration(),
    ],
    // Distributed tracing: attach trace headers to same-origin /api/* calls
    // so frontend errors link to the backend request that caused them.
    tracePropagationTargets: [/^\/api\//],
    tracesSampleRate: import.meta.env.PROD ? 0.1 : 1.0,
    ignoreErrors: [
      // Internal Sentry rejection when the transport is torn down on page
      // unload — picked back up by Sentry's own unhandledrejection handler.
      'Transport destroyed',
      // Expected 401 from protected endpoints when the session has lapsed.
      // Surfaced as an ApiError; the auth/protected-route layer already
      // redirects to /landing, so an uncaught rejection here is just noise.
      'Not authenticated',
      // Transient backend unavailability: apiFetch throws ApiError('Request
      // failed') for any non-OK response with a non-JSON body (a 5xx / nginx
      // gateway page during a backend restart or FD-exhaustion blip), and
      // 'Request timed out' on a client-side timeout. These are infra events,
      // not frontend bugs — the backend's own Sentry covers the outage, and
      // any on-mount hook / fire-and-forget caller that misses a .catch()
      // would otherwise spam this as a useless single-frame unhandled
      // rejection. UI-facing callers still catch these to show a toast.
      'Request failed',
      'Request timed out',
      // pdf.js throws this when an in-flight page render is cancelled
      // (component unmount, doc close, zoom change). Normal behavior.
      'Rendering cancelled',
    ],
  })
}

export { Sentry }
