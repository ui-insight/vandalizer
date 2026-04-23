import { useEffect, Component, type ErrorInfo, type ReactNode } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { AuthProvider } from './contexts/AuthContext'
import { TeamProvider } from './contexts/TeamContext'
import { ToastProvider } from './contexts/ToastContext'
import { CertificationPanelProvider } from './contexts/CertificationPanelContext'
import { queryClient } from './lib/queryClient'
import { Sentry } from './lib/sentry'
import { router } from './router'
import { getThemeConfig } from './api/config'
import { getContrastTextColor, getComplementaryColor, getHoverColor } from './utils/color'

class ErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: ReactNode }) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    Sentry.captureException(error, { contexts: { react: { componentStack: info.componentStack } } })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 40, textAlign: 'center' }}>
          <h1 style={{ fontSize: 24, fontWeight: 600, marginBottom: 8 }}>Something went wrong</h1>
          <p style={{ color: '#6b7280', marginBottom: 16 }}>{this.state.error?.message}</p>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '8px 16px', borderRadius: 6, border: '1px solid #d1d5db',
              background: '#fff', cursor: 'pointer', fontSize: 14,
            }}
          >
            Reload page
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function useGlobalDropPrevention() {
  useEffect(() => {
    // Prevent the browser from opening/downloading files when dropped outside a drop zone.
    // Use bubble phase (not capture) so React drop handlers run first and can
    // stopPropagation before these fallback handlers fire.
    const preventDragOver = (e: DragEvent) => {
      e.preventDefault()
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'none'
    }
    const preventDrop = (e: DragEvent) => {
      e.preventDefault()
    }
    document.addEventListener('dragover', preventDragOver as EventListener)
    document.addEventListener('drop', preventDrop as EventListener)
    return () => {
      document.removeEventListener('dragover', preventDragOver as EventListener)
      document.removeEventListener('drop', preventDrop as EventListener)
    }
  }, [])
}

function useThemeLoader() {
  useEffect(() => {
    getThemeConfig()
      .then((theme) => {
        const root = document.documentElement
        root.style.setProperty('--highlight-color', theme.highlight_color)
        root.style.setProperty('--ui-radius', theme.ui_radius)
        root.style.setProperty('--highlight-text-color', getContrastTextColor(theme.highlight_color))
        root.style.setProperty('--highlight-complement', getComplementaryColor(theme.highlight_color))
        root.style.setProperty('--highlight-hover', getHoverColor(theme.highlight_color))
      })
      .catch(() => {
        // Use CSS defaults if theme fetch fails (e.g. not logged in)
      })
  }, [])
}

export default function App() {
  useGlobalDropPrevention()
  useThemeLoader()

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <TeamProvider>
            <ToastProvider>
              <CertificationPanelProvider>
                <RouterProvider router={router} />
              </CertificationPanelProvider>
            </ToastProvider>
          </TeamProvider>
        </AuthProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
