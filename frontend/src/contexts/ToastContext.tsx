import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

export type ToastType = 'success' | 'error' | 'info'

interface ToastAction {
  label: string
  onClick: () => void
}

interface Toast {
  id: number
  type: ToastType
  message: string
  action?: ToastAction
}

interface ToastContextValue {
  toasts: Toast[]
  toast: (message: string, type?: ToastType, action?: ToastAction) => void
  dismiss: (id: number) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

let nextId = 1

// Errors no longer auto-dismiss, so a repeatedly-failing background job could
// otherwise pile toasts past the bottom of the viewport. Keep the newest few.
const MAX_TOASTS = 5

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const dismiss = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const toast = useCallback((message: string, type: ToastType = 'info', action?: ToastAction) => {
    const id = nextId++
    setToasts(prev => [...prev, { id, type, message, action }].slice(-MAX_TOASTS))
    // Errors are the longest messages and often need to be read carefully or
    // copied into a support ticket, so they stay until the user closes them.
    if (type !== 'error') {
      setTimeout(() => dismiss(id), action ? 8000 : 4000)
    }
  }, [dismiss])

  return (
    <ToastContext.Provider value={{ toasts, toast, dismiss }}>
      {children}
      {/* Toast container */}
      {toasts.length > 0 && (
        <div
          role="region"
          aria-label="Notifications"
          style={{
            position: 'fixed', top: 16, right: 16, zIndex: 9999,
            display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 380,
          }}
        >
          {toasts.map(t => {
            // Errors persist until dismissed, so clicking the body must not close
            // them \u2014 the user needs to select and copy the text.
            const isError = t.type === 'error'
            return (
            <div
              key={t.id}
              // Error toasts interrupt (assertive); success/info wait (polite).
              role={isError ? 'alert' : 'status'}
              aria-live={isError ? 'assertive' : 'polite'}
              onClick={isError ? undefined : () => dismiss(t.id)}
              style={{
                padding: '12px 16px', borderRadius: 'var(--ui-radius, 12px)',
                boxShadow: '0 4px 16px rgba(0,0,0,0.15)',
                cursor: isError ? 'default' : 'pointer', fontSize: 14, fontWeight: 500,
                userSelect: isError ? 'text' : undefined,
                display: 'flex', alignItems: isError ? 'flex-start' : 'center', gap: 10,
                animation: 'toast-slide-in 0.2s ease-out',
                ...(t.type === 'success' ? { background: '#f0fdf4', border: '1px solid #bbf7d0', color: '#166534' } :
                   isError ? { background: '#fef2f2', border: '1px solid #fecaca', color: '#991b1b' } :
                   { background: '#fff', border: '1px solid #e5e7eb', color: '#374151' }),
              }}
            >
              <span style={{ fontSize: 16 }}>
                {t.type === 'success' ? '\u2713' : isError ? '\u2717' : '\u2139'}
              </span>
              <span style={{ flex: 1, wordBreak: 'break-word' }}>
                {t.message}
                {t.action && (
                  <button
                    onClick={(e) => { e.stopPropagation(); t.action!.onClick(); dismiss(t.id) }}
                    style={{
                      display: 'inline', marginLeft: 8,
                      background: 'none', border: 'none', padding: 0,
                      font: 'inherit', fontSize: 'inherit', fontWeight: 600,
                      color: 'inherit', textDecoration: 'underline', cursor: 'pointer',
                    }}
                  >
                    {t.action.label}
                  </button>
                )}
              </span>
              {isError && (
                <button
                  type="button"
                  aria-label="Dismiss error"
                  title="Dismiss"
                  onClick={(e) => { e.stopPropagation(); dismiss(t.id) }}
                  style={{
                    flexShrink: 0, marginLeft: 4, marginTop: -2,
                    background: 'none', border: 'none', padding: '0 2px',
                    fontSize: 16, lineHeight: 1, color: 'inherit',
                    opacity: 0.7, cursor: 'pointer',
                  }}
                >
                  {'\u2715'}
                </button>
              )}
            </div>
            )
          })}
        </div>
      )}
      <style>{`
        @keyframes toast-slide-in {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}</style>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
