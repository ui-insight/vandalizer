import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

export type ToastType = 'success' | 'error' | 'info'

interface Toast {
  id: number
  type: ToastType
  message: string
}

interface ToastContextValue {
  toasts: Toast[]
  toast: (message: string, type?: ToastType) => void
  dismiss: (id: number) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

let nextId = 1

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const dismiss = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const toast = useCallback((message: string, type: ToastType = 'info') => {
    const id = nextId++
    setToasts(prev => [...prev, { id, type, message }])
    setTimeout(() => dismiss(id), 4000)
  }, [dismiss])

  return (
    <ToastContext.Provider value={{ toasts, toast, dismiss }}>
      {children}
      {/* Toast container */}
      {toasts.length > 0 && (
        <div style={{
          position: 'fixed', top: 16, right: 16, zIndex: 9999,
          display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 380,
        }}>
          {toasts.map(t => (
            <div
              key={t.id}
              onClick={() => dismiss(t.id)}
              style={{
                padding: '12px 16px', borderRadius: 'var(--ui-radius, 12px)',
                boxShadow: '0 4px 16px rgba(0,0,0,0.15)',
                cursor: 'pointer', fontSize: 14, fontWeight: 500,
                display: 'flex', alignItems: 'center', gap: 10,
                animation: 'toast-slide-in 0.2s ease-out',
                ...(t.type === 'success' ? { background: '#f0fdf4', border: '1px solid #bbf7d0', color: '#166534' } :
                   t.type === 'error' ? { background: '#fef2f2', border: '1px solid #fecaca', color: '#991b1b' } :
                   { background: '#fff', border: '1px solid #e5e7eb', color: '#374151' }),
              }}
            >
              <span style={{ fontSize: 16 }}>
                {t.type === 'success' ? '\u2713' : t.type === 'error' ? '\u2717' : '\u2139'}
              </span>
              {t.message}
            </div>
          ))}
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
