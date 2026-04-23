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
  })
}

export { Sentry }
