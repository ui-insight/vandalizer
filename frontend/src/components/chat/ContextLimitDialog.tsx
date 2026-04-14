import { useState } from 'react'
import { Scissors, Minimize2, Trash2, X, Loader2 } from 'lucide-react'

interface ContextLimitDialogProps {
  open: boolean
  onClose: () => void
  onTruncate: () => Promise<void>
  onCompact: () => Promise<void>
  onClear: () => Promise<void>
  percent: number
}

export function ContextLimitDialog({
  open,
  onClose,
  onTruncate,
  onCompact,
  onClear,
  percent,
}: ContextLimitDialogProps) {
  const [loading, setLoading] = useState<string | null>(null)

  if (!open) return null

  const handleAction = async (action: string, fn: () => Promise<void>) => {
    setLoading(action)
    try {
      await fn()
      onClose()
    } catch {
      // Error handling is done by the caller
    } finally {
      setLoading(null)
    }
  }

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0, 0, 0, 0.3)',
          zIndex: 1000,
        }}
      />

      {/* Dialog */}
      <div
        style={{
          position: 'fixed',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          background: 'white',
          borderRadius: 'var(--ui-radius, 12px)',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          width: 420,
          maxWidth: 'calc(100vw - 32px)',
          zIndex: 1001,
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '16px 20px',
            borderBottom: '1px solid #e5e7eb',
          }}
        >
          <div>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>
              Context Window {percent >= 100 ? 'Full' : 'Nearly Full'}
            </h3>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: '#6b7280' }}>
              {percent}% of context used. Choose how to manage it.
            </p>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              padding: 4,
              color: '#9ca3af',
              display: 'flex',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Options */}
        <div style={{ padding: '12px 20px 20px' }}>
          <button
            onClick={() => handleAction('truncate', onTruncate)}
            disabled={loading !== null}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'flex-start',
              gap: 12,
              padding: '12px 14px',
              background: loading === 'truncate' ? '#f9fafb' : 'white',
              border: '1px solid #e5e7eb',
              borderRadius: 'var(--ui-radius, 12px)',
              cursor: loading ? 'not-allowed' : 'pointer',
              textAlign: 'left',
              marginBottom: 8,
              transition: 'background 0.15s, border-color 0.15s',
              opacity: loading && loading !== 'truncate' ? 0.5 : 1,
            }}
            onMouseEnter={e => {
              if (!loading) (e.currentTarget as HTMLButtonElement).style.borderColor = '#9ca3af'
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLButtonElement).style.borderColor = '#e5e7eb'
            }}
          >
            <Scissors size={18} style={{ marginTop: 2, color: '#6b7280', flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: 14, fontWeight: 600 }}>Truncate</div>
              <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                Drop older messages from context. They'll still be visible in the conversation.
              </div>
            </div>
          </button>

          <button
            onClick={() => handleAction('compact', onCompact)}
            disabled={loading !== null}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'flex-start',
              gap: 12,
              padding: '12px 14px',
              background: loading === 'compact' ? '#f9fafb' : 'white',
              border: '1px solid #e5e7eb',
              borderRadius: 'var(--ui-radius, 12px)',
              cursor: loading ? 'not-allowed' : 'pointer',
              textAlign: 'left',
              marginBottom: 8,
              transition: 'background 0.15s, border-color 0.15s',
              opacity: loading && loading !== 'compact' ? 0.5 : 1,
            }}
            onMouseEnter={e => {
              if (!loading) (e.currentTarget as HTMLButtonElement).style.borderColor = '#9ca3af'
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLButtonElement).style.borderColor = '#e5e7eb'
            }}
          >
            {loading === 'compact' ? (
              <Loader2 size={18} style={{ marginTop: 2, color: '#6b7280', flexShrink: 0, animation: 'spin 1s linear infinite' }} />
            ) : (
              <Minimize2 size={18} style={{ marginTop: 2, color: '#6b7280', flexShrink: 0 }} />
            )}
            <div>
              <div style={{ fontSize: 14, fontWeight: 600 }}>Compact</div>
              <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                Summarize the conversation into a concise context. Old messages remain visible.
              </div>
            </div>
          </button>

          <button
            onClick={() => handleAction('clear', onClear)}
            disabled={loading !== null}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'flex-start',
              gap: 12,
              padding: '12px 14px',
              background: loading === 'clear' ? '#f9fafb' : 'white',
              border: '1px solid #e5e7eb',
              borderRadius: 'var(--ui-radius, 12px)',
              cursor: loading ? 'not-allowed' : 'pointer',
              textAlign: 'left',
              transition: 'background 0.15s, border-color 0.15s',
              opacity: loading && loading !== 'clear' ? 0.5 : 1,
            }}
            onMouseEnter={e => {
              if (!loading) (e.currentTarget as HTMLButtonElement).style.borderColor = '#9ca3af'
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLButtonElement).style.borderColor = '#e5e7eb'
            }}
          >
            <Trash2 size={18} style={{ marginTop: 2, color: '#6b7280', flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: 14, fontWeight: 600 }}>Clear</div>
              <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                Start fresh. Old messages remain visible but won't be sent to the model.
              </div>
            </div>
          </button>
        </div>
      </div>
    </>
  )
}
