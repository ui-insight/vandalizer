import { useEffect, useState } from 'react'
import { AlertTriangle, X, Loader2 } from 'lucide-react'

interface ConfirmDialogProps {
  open: boolean
  title?: string
  message: React.ReactNode
  confirmLabel?: string
  cancelLabel?: string
  destructive?: boolean
  onConfirm: () => void | Promise<void>
  onCancel: () => void
}

export function ConfirmDialog({
  open,
  title = 'Are you sure?',
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  destructive = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, busy, onCancel])

  if (!open) return null

  const handleConfirm = async () => {
    try {
      setBusy(true)
      await onConfirm()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 flex items-center justify-center bg-black/50"
      style={{ zIndex: 1000 }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onCancel()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            {destructive && (
              <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-red-50">
                <AlertTriangle className="h-5 w-5 text-red-600" />
              </div>
            )}
            <h3
              id="confirm-dialog-title"
              className="text-lg font-medium text-gray-900"
              style={{ marginTop: destructive ? 6 : 0 }}
            >
              {title}
            </h3>
          </div>
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            aria-label="Close"
            className="text-gray-400 hover:text-gray-600 disabled:opacity-40"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="mb-5 text-sm text-gray-600">{message}</div>

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-md px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={busy}
            autoFocus
            className={
              destructive
                ? 'inline-flex items-center gap-2 rounded-md bg-red-600 px-3 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50'
                : 'inline-flex items-center gap-2 rounded-md bg-highlight px-3 py-2 text-sm font-bold text-highlight-text hover:brightness-90 disabled:opacity-50'
            }
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
